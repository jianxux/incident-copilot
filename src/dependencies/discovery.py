"""Auto-discover service dependencies from various sources."""

import re
import uuid
from datetime import datetime
from pathlib import Path

import structlog

from .models import (
    Dependency,
    DependencyType,
    DiscoveryResult,
    Service,
    ServiceTier,
)

logger = structlog.get_logger()


class DependencyDiscovery:
    """
    Auto-discover service dependencies from various configuration sources.

    Supported sources:
    - Docker Compose files
    - Kubernetes manifests
    - Terraform configurations
    - Package.json / requirements.txt
    - GitHub repository analysis
    """

    def __init__(self):
        """Initialize the discovery engine."""
        self._service_patterns: dict[str, DependencyType] = {
            r"postgres|postgresql|pg": DependencyType.DATABASE,
            r"mysql|mariadb": DependencyType.DATABASE,
            r"mongodb|mongo": DependencyType.DATABASE,
            r"redis": DependencyType.CACHE,
            r"memcached": DependencyType.CACHE,
            r"kafka": DependencyType.QUEUE,
            r"rabbitmq|rabbit": DependencyType.QUEUE,
            r"sqs|sns": DependencyType.QUEUE,
            r"elasticsearch|elastic|opensearch": DependencyType.DATABASE,
            r"s3|minio|gcs|blob": DependencyType.STORAGE,
            r"api|service|svc": DependencyType.API,
        }

    def _generate_id(self, prefix: str = "svc") -> str:
        """Generate a unique ID."""
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def _infer_dependency_type(self, name: str) -> DependencyType:
        """Infer dependency type from service name."""
        name_lower = name.lower()
        for pattern, dep_type in self._service_patterns.items():
            if re.search(pattern, name_lower):
                return dep_type
        return DependencyType.API

    def _normalize_service_name(self, name: str) -> str:
        """Normalize service name to a consistent format."""
        # Remove common suffixes
        name = re.sub(r"[_-]?(service|svc|api|app)$", "", name, flags=re.IGNORECASE)
        # Convert to kebab-case
        name = re.sub(r"[_\s]+", "-", name)
        name = re.sub(r"([a-z])([A-Z])", r"\1-\2", name)
        return name.lower().strip("-")

    async def discover_from_docker_compose(
        self,
        content: str,
        file_path: str | None = None,
    ) -> DiscoveryResult:
        """
        Discover services and dependencies from a Docker Compose file.

        Args:
            content: Docker Compose YAML content
            file_path: Optional path to the file (for logging)

        Returns:
            DiscoveryResult with discovered services and dependencies
        """
        import yaml

        result = DiscoveryResult(source_type="docker_compose")

        try:
            compose_data = yaml.safe_load(content)
        except Exception as e:
            result.errors.append(f"Failed to parse YAML: {e}")
            return result

        if not compose_data or "services" not in compose_data:
            result.errors.append("No services found in docker-compose file")
            return result

        services_map: dict[str, Service] = {}

        # First pass: create services
        for service_name, service_config in compose_data.get("services", {}).items():
            normalized_name = self._normalize_service_name(service_name)
            service_id = normalized_name

            # Infer tier from labels or environment
            tier = ServiceTier.TIER_3
            labels = service_config.get("labels", {})
            if isinstance(labels, dict):
                tier_label = labels.get("tier") or labels.get("criticality")
                if tier_label:
                    tier_map = {
                        "1": ServiceTier.TIER_1,
                        "2": ServiceTier.TIER_2,
                        "3": ServiceTier.TIER_3,
                        "4": ServiceTier.TIER_4,
                        "critical": ServiceTier.TIER_1,
                        "high": ServiceTier.TIER_2,
                    }
                    tier = tier_map.get(str(tier_label).lower(), ServiceTier.TIER_3)

            # Extract team from labels
            team_owner = None
            if isinstance(labels, dict):
                team_owner = labels.get("team") or labels.get("owner")

            service = Service(
                id=service_id,
                name=service_name,
                description=f"Discovered from docker-compose: {file_path or 'unknown'}",
                team_owner=team_owner,
                tier=tier,
                tags=["docker-compose", "auto-discovered"],
                metadata={
                    "image": service_config.get("image", ""),
                    "discovered_from": file_path or "docker-compose",
                },
            )
            services_map[service_name] = service
            result.services_discovered.append(service)

        # Second pass: discover dependencies
        for service_name, service_config in compose_data.get("services", {}).items():
            source_service = services_map.get(service_name)
            if not source_service:
                continue

            # depends_on
            depends_on = service_config.get("depends_on", [])
            if isinstance(depends_on, dict):
                depends_on = list(depends_on.keys())
            elif isinstance(depends_on, str):
                depends_on = [depends_on]

            for dep_name in depends_on:
                target_service = services_map.get(dep_name)
                if target_service:
                    dep = Dependency(
                        id=self._generate_id("dep"),
                        source_service_id=source_service.id,
                        target_service_id=target_service.id,
                        dependency_type=self._infer_dependency_type(dep_name),
                        discovered_via="docker_compose.depends_on",
                        confidence=0.9,
                        last_observed_at=datetime.utcnow(),
                    )
                    result.dependencies_discovered.append(dep)

            # links (legacy)
            links = service_config.get("links", [])
            for link in links:
                link_name = link.split(":")[0]
                target_service = services_map.get(link_name)
                if target_service:
                    dep = Dependency(
                        id=self._generate_id("dep"),
                        source_service_id=source_service.id,
                        target_service_id=target_service.id,
                        dependency_type=self._infer_dependency_type(link_name),
                        discovered_via="docker_compose.links",
                        confidence=0.8,
                        last_observed_at=datetime.utcnow(),
                    )
                    result.dependencies_discovered.append(dep)

            # Environment variables referencing other services
            environment = service_config.get("environment", {})
            if isinstance(environment, list):
                environment = dict(
                    e.split("=", 1) for e in environment if "=" in e
                )

            for env_key, env_value in environment.items() if environment else []:
                if not env_value:
                    continue
                env_value_str = str(env_value)
                # Look for service names in env values
                for other_name in services_map.keys():
                    if other_name != service_name and other_name in env_value_str:
                        target_service = services_map.get(other_name)
                        if target_service:
                            dep = Dependency(
                                id=self._generate_id("dep"),
                                source_service_id=source_service.id,
                                target_service_id=target_service.id,
                                dependency_type=self._infer_dependency_type(other_name),
                                discovered_via=f"docker_compose.environment.{env_key}",
                                confidence=0.7,
                                last_observed_at=datetime.utcnow(),
                            )
                            result.dependencies_discovered.append(dep)

        logger.info(
            "docker_compose_discovery_complete",
            services=len(result.services_discovered),
            dependencies=len(result.dependencies_discovered),
            file=file_path,
        )

        return result

    async def discover_from_kubernetes(
        self,
        manifests: list[str],
        namespace: str | None = None,
    ) -> DiscoveryResult:
        """
        Discover services and dependencies from Kubernetes manifests.

        Args:
            manifests: List of Kubernetes YAML manifest contents
            namespace: Optional namespace filter

        Returns:
            DiscoveryResult with discovered services and dependencies
        """
        import yaml

        result = DiscoveryResult(source_type="kubernetes")
        services_map: dict[str, Service] = {}

        for manifest_content in manifests:
            try:
                docs = list(yaml.safe_load_all(manifest_content))
            except Exception as e:
                result.errors.append(f"Failed to parse manifest: {e}")
                continue

            for doc in docs:
                if not doc or "kind" not in doc:
                    continue

                kind = doc.get("kind", "")
                metadata = doc.get("metadata", {})
                name = metadata.get("name", "")
                ns = metadata.get("namespace", "default")

                if namespace and ns != namespace:
                    continue

                # Handle Deployments, Services, StatefulSets
                if kind in ["Deployment", "StatefulSet", "DaemonSet", "Service"]:
                    service_id = self._normalize_service_name(name)

                    # Extract labels
                    labels = metadata.get("labels", {})
                    annotations = metadata.get("annotations", {})

                    tier = ServiceTier.TIER_3
                    tier_label = labels.get("tier") or annotations.get(
                        "incident-copilot.io/tier"
                    )
                    if tier_label:
                        tier_map = {
                            "1": ServiceTier.TIER_1,
                            "2": ServiceTier.TIER_2,
                            "3": ServiceTier.TIER_3,
                            "4": ServiceTier.TIER_4,
                        }
                        tier = tier_map.get(str(tier_label), ServiceTier.TIER_3)

                    team_owner = labels.get("team") or annotations.get(
                        "incident-copilot.io/team"
                    )

                    if service_id not in services_map:
                        service = Service(
                            id=service_id,
                            name=name,
                            description=f"Discovered from Kubernetes {kind}",
                            team_owner=team_owner,
                            tier=tier,
                            kubernetes_namespace=ns,
                            tags=["kubernetes", "auto-discovered", kind.lower()],
                            metadata={
                                "kind": kind,
                                "namespace": ns,
                                "labels": labels,
                            },
                        )
                        services_map[service_id] = service
                        result.services_discovered.append(service)

        # Second pass: find dependencies from environment variables
        for manifest_content in manifests:
            try:
                docs = list(yaml.safe_load_all(manifest_content))
            except Exception:
                continue

            for doc in docs:
                if not doc:
                    continue

                kind = doc.get("kind", "")
                if kind not in ["Deployment", "StatefulSet", "DaemonSet"]:
                    continue

                metadata = doc.get("metadata", {})
                name = metadata.get("name", "")
                source_id = self._normalize_service_name(name)

                if source_id not in services_map:
                    continue

                # Extract containers
                spec = doc.get("spec", {})
                template_spec = spec.get("template", {}).get("spec", {})
                containers = template_spec.get("containers", [])

                for container in containers:
                    env_vars = container.get("env", [])
                    for env in env_vars:
                        env_value = env.get("value", "")
                        if not env_value:
                            continue

                        # Look for references to other services
                        for other_id, other_service in services_map.items():
                            if (
                                other_id != source_id
                                and other_service.name in str(env_value)
                            ):
                                dep = Dependency(
                                    id=self._generate_id("dep"),
                                    source_service_id=source_id,
                                    target_service_id=other_id,
                                    dependency_type=self._infer_dependency_type(
                                        other_service.name
                                    ),
                                    discovered_via=f"kubernetes.env.{env.get('name', '')}",
                                    confidence=0.7,
                                    last_observed_at=datetime.utcnow(),
                                )
                                result.dependencies_discovered.append(dep)

        logger.info(
            "kubernetes_discovery_complete",
            services=len(result.services_discovered),
            dependencies=len(result.dependencies_discovered),
        )

        return result

    async def discover_from_terraform(
        self,
        content: str,
        file_path: str | None = None,
    ) -> DiscoveryResult:
        """
        Discover services and dependencies from Terraform configuration.

        Parses HCL to find resources that represent services and their
        relationships.

        Args:
            content: Terraform HCL content
            file_path: Optional path to the file

        Returns:
            DiscoveryResult with discovered services and dependencies
        """
        result = DiscoveryResult(source_type="terraform")

        # Simple regex-based parsing (full HCL parsing would need hcl2 library)
        # Find resource blocks
        resource_pattern = r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^}]+)\}'
        resources = re.findall(resource_pattern, content, re.DOTALL)

        services_map: dict[str, Service] = {}

        # Service-related resource types
        service_types = [
            "aws_ecs_service",
            "aws_ecs_task_definition",
            "aws_lambda_function",
            "aws_api_gateway_rest_api",
            "kubernetes_deployment",
            "kubernetes_service",
            "google_cloud_run_service",
            "azurerm_function_app",
        ]

        for resource_type, resource_name, resource_body in resources:
            if resource_type in service_types:
                service_id = self._normalize_service_name(resource_name)
                service = Service(
                    id=service_id,
                    name=resource_name,
                    description=f"Discovered from Terraform: {resource_type}",
                    tier=ServiceTier.TIER_3,
                    tags=["terraform", "auto-discovered", resource_type],
                    metadata={
                        "terraform_type": resource_type,
                        "discovered_from": file_path or "terraform",
                    },
                )
                services_map[resource_name] = service
                result.services_discovered.append(service)

        # Find references between resources
        for resource_type, resource_name, resource_body in resources:
            if resource_type not in service_types:
                continue

            source_id = self._normalize_service_name(resource_name)
            if source_id not in [s.id for s in services_map.values()]:
                continue

            # Look for references to other resources
            ref_pattern = r'([a-z_]+\.[a-z_0-9]+)\.([a-z_]+)'
            refs = re.findall(ref_pattern, resource_body)

            for ref_type_name, ref_attr in refs:
                parts = ref_type_name.split(".")
                if len(parts) == 2:
                    ref_name = parts[1]
                    if ref_name in services_map and ref_name != resource_name:
                        target_service = services_map[ref_name]
                        dep = Dependency(
                            id=self._generate_id("dep"),
                            source_service_id=source_id,
                            target_service_id=target_service.id,
                            dependency_type=DependencyType.API,
                            discovered_via="terraform.reference",
                            confidence=0.8,
                            last_observed_at=datetime.utcnow(),
                        )
                        result.dependencies_discovered.append(dep)

        logger.info(
            "terraform_discovery_complete",
            services=len(result.services_discovered),
            dependencies=len(result.dependencies_discovered),
            file=file_path,
        )

        return result

    async def discover_from_file(self, file_path: str | Path) -> DiscoveryResult:
        """
        Auto-detect file type and discover dependencies.

        Args:
            file_path: Path to the configuration file

        Returns:
            DiscoveryResult with discovered services and dependencies
        """
        path = Path(file_path)

        if not path.exists():
            return DiscoveryResult(
                source_type="unknown",
                errors=[f"File not found: {file_path}"],
            )

        content = path.read_text()
        file_name = path.name.lower()

        # Detect file type and use appropriate parser
        if "docker-compose" in file_name or file_name in [
            "compose.yml",
            "compose.yaml",
        ]:
            return await self.discover_from_docker_compose(content, str(path))
        elif file_name.endswith(".tf"):
            return await self.discover_from_terraform(content, str(path))
        elif file_name.endswith((".yml", ".yaml")):
            # Try to detect if it's Kubernetes
            if "apiVersion:" in content and "kind:" in content:
                return await self.discover_from_kubernetes([content])
            # Otherwise try docker-compose
            return await self.discover_from_docker_compose(content, str(path))
        else:
            return DiscoveryResult(
                source_type="unknown",
                errors=[f"Unsupported file type: {file_name}"],
            )

    async def merge_results(
        self,
        results: list[DiscoveryResult],
    ) -> DiscoveryResult:
        """
        Merge multiple discovery results, deduplicating services and dependencies.

        Args:
            results: List of DiscoveryResult to merge

        Returns:
            Merged DiscoveryResult
        """
        merged = DiscoveryResult(source_type="merged")

        seen_services: dict[str, Service] = {}
        seen_deps: set[tuple[str, str]] = set()

        for result in results:
            merged.errors.extend(result.errors)
            merged.warnings.extend(result.warnings)

            for service in result.services_discovered:
                if service.id not in seen_services:
                    seen_services[service.id] = service
                    merged.services_discovered.append(service)

            for dep in result.dependencies_discovered:
                key = (dep.source_service_id, dep.target_service_id)
                if key not in seen_deps:
                    seen_deps.add(key)
                    merged.dependencies_discovered.append(dep)

        return merged


# Global discovery instance
dependency_discovery = DependencyDiscovery()
