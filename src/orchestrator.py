"""Context orchestrator - the core of the incident copilot."""

import asyncio
import time
from datetime import datetime
from typing import cast

import structlog

from .ai import LogSummarizer
from .ai.log_compressor import CompressedLogs, LogCompressor
from .config import Settings
from .dependencies.service import DependencyService
from .integrations import (
    CloudWatchAdapter,
    DatadogAdapter,
    GitHubAdapter,
    GitLabAdapter,
    SlackAdapter,
)
from .integrations.oncall_legacy import OnCallAdapter
from .models import (
    ContextCard,
    DatadogContext,
    GitHubContext,
    GitLabContext,
    OnCallRoster,
    PagerDutyIncident,
    RunbookLink,
    TopologyContext,
)
from .runbooks import RunbookLinker

logger = structlog.get_logger()


class ContextOrchestrator:
    """
    Orchestrates context assembly from multiple sources.

    When an incident is received:
    1. Fan-out: Fetch data from GitHub, Datadog in parallel
    2. AI: Summarize logs
    3. Assemble: Combine into context card
    4. Deliver: Send to Slack
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.github = GitHubAdapter(settings)
        self.gitlab = GitLabAdapter(settings)
        self.slack = SlackAdapter(settings)
        self.summarizer = LogSummarizer(settings)
        self.runbook_linker = RunbookLinker()
        self.oncall = OnCallAdapter(settings)

        # New: Log compressor for better context compression
        self.log_compressor = LogCompressor()

        # New: Dependency service for topology context
        self.dependencies = DependencyService()

        # Determine SCM provider based on configuration
        # Prefer GitHub if configured, fall back to GitLab
        self.scm_provider = self._detect_scm_provider()
        logger.info("scm_provider_initialized", provider=self.scm_provider)

        # Initialize log provider based on configuration
        self.log_provider = settings.log_provider.lower()
        self.log_adapter: CloudWatchAdapter | DatadogAdapter
        if self.log_provider == "cloudwatch":
            self.log_adapter = CloudWatchAdapter(settings)
            logger.info("log_provider_initialized", provider="cloudwatch")
        else:
            self.log_adapter = DatadogAdapter(settings)
            logger.info("log_provider_initialized", provider="datadog")

        # Keep datadog reference for backward compatibility
        self.datadog = (
            self.log_adapter
            if self.log_provider == "datadog"
            else DatadogAdapter(settings)
        )

    def _detect_scm_provider(self) -> str:
        """Detect which SCM provider to use based on configuration."""
        if self.settings.github_token:
            return "github"
        elif self.settings.gitlab_token:
            return "gitlab"
        else:
            return "none"

    async def process_incident(
        self, incident: PagerDutyIncident, slack_channel: str | None = None
    ) -> ContextCard:
        """
        Process an incident and deliver context card.

        Returns the assembled context card.
        """
        start_time = time.monotonic()
        errors: list[str] = []

        logger.info(
            "processing_incident",
            incident_id=incident.incident_id,
            service=incident.service_name,
        )

        # Fan-out: fetch from multiple sources in parallel
        scm_task = asyncio.create_task(self._fetch_scm_context(incident.service_name))
        datadog_task = asyncio.create_task(
            self._fetch_log_context(incident.service_name)
        )
        oncall_task = asyncio.create_task(
            self._fetch_oncall_roster(incident.service_name)
        )
        topology_task = asyncio.create_task(
            self._fetch_topology_context(incident.service_name)
        )

        # Wait for all with timeout
        scm_ctx: GitHubContext | GitLabContext | None = None
        datadog_ctx: DatadogContext | None = None
        oncall_roster: OnCallRoster | None = None
        topology_ctx: TopologyContext | None = None

        try:
            scm_ctx_raw, log_ctx_raw, oncall_raw, topology_raw = await asyncio.wait_for(
                asyncio.gather(
                    scm_task,
                    datadog_task,
                    oncall_task,
                    topology_task,
                    return_exceptions=True,
                ),
                timeout=8.0,  # Leave room for AI + Slack
            )

            # Handle exceptions from gather
            if isinstance(scm_ctx_raw, Exception):
                scm_name = "GitHub" if self.scm_provider == "github" else "GitLab"
                logger.error(
                    "scm_fetch_error",
                    provider=self.scm_provider,
                    error=str(scm_ctx_raw),
                )
                errors.append(f"{scm_name}: {str(scm_ctx_raw)}")
                scm_ctx = None
            else:
                scm_ctx = cast(GitHubContext | GitLabContext | None, scm_ctx_raw)

            if isinstance(log_ctx_raw, Exception):
                provider_names = {
                    "cloudwatch": "CloudWatch",
                    "loki": "Loki",
                    "datadog": "Datadog",
                }
                provider_name = provider_names.get(self.log_provider, "Datadog")
                logger.error(
                    "log_fetch_error",
                    provider=self.log_provider,
                    error=str(log_ctx_raw),
                )
                errors.append(f"{provider_name}: {str(log_ctx_raw)}")
                datadog_ctx = None
            else:
                datadog_ctx = cast(DatadogContext | None, log_ctx_raw)

            if isinstance(oncall_raw, Exception):
                logger.error("oncall_fetch_error", error=str(oncall_raw))
                errors.append(f"On-Call: {str(oncall_raw)}")
                oncall_roster = None
            else:
                oncall_roster = cast(OnCallRoster | None, oncall_raw)

            if isinstance(topology_raw, Exception):
                logger.error("topology_fetch_error", error=str(topology_raw))
                errors.append(f"Topology: {str(topology_raw)}")
                topology_ctx = None
            else:
                topology_ctx = cast(TopologyContext | None, topology_raw)

        except TimeoutError:
            logger.warning("context_fetch_timeout")
            errors.append("Context fetch timed out")
            scm_ctx = scm_task.result() if scm_task.done() else None
            datadog_ctx = datadog_task.result() if datadog_task.done() else None
            oncall_roster = oncall_task.result() if oncall_task.done() else None
            topology_ctx = topology_task.result() if topology_task.done() else None

        # Extract GitHub/GitLab context (narrowed types for mypy)
        github_ctx: GitHubContext | None = (
            cast(GitHubContext | None, scm_ctx)
            if self.scm_provider == "github"
            else None
        )
        gitlab_ctx: GitLabContext | None = (
            cast(GitLabContext | None, scm_ctx)
            if self.scm_provider == "gitlab"
            else None
        )

        # AI summarization (if we have logs)
        ai_summary = None
        if datadog_ctx and datadog_ctx.logs:
            try:
                ai_summary = await asyncio.wait_for(
                    self.summarizer.summarize(
                        datadog_ctx.logs,
                        incident.service_name,
                    ),
                    timeout=5.0,
                )
            except TimeoutError:
                logger.warning("ai_summarization_timeout")
                errors.append("AI summarization timed out")
            except Exception as e:
                logger.error("ai_summarization_error", error=str(e))
                errors.append(f"AI: {str(e)}")

        # Link relevant runbooks
        runbook_links = []
        try:
            matches = self.runbook_linker.find_relevant_runbooks(
                query=f"{incident.title} {incident.description or ''}",
                service_name=incident.service_name,
                top_k=3,
            )
            runbook_links = [
                RunbookLink(
                    title=m.title,
                    url=m.url,
                    source=f"{m.source_type.value}:{m.source_name}",
                    relevance_score=m.relevance_score,
                    matched_terms=m.matched_terms,
                )
                for m in matches
            ]
            logger.info(
                "runbooks_linked",
                incident_id=incident.incident_id,
                runbook_count=len(runbook_links),
            )
        except Exception as e:
            logger.error("runbook_linking_error", error=str(e))
            errors.append(f"Runbooks: {str(e)}")

        # Assemble context card
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Get codeowners from whichever SCM is configured
        codeowners: list[str] = []
        if github_ctx:
            codeowners = github_ctx.codeowners
        elif gitlab_ctx:
            codeowners = gitlab_ctx.codeowners

        card = ContextCard(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity,
            service_name=incident.service_name,
            triggered_at=incident.triggered_at,
            alert_url=incident.html_url,
            github=github_ctx,
            gitlab=gitlab_ctx,
            datadog=datadog_ctx,
            topology=topology_ctx,
            ai_summary=ai_summary,
            similar_incidents=[],  # TODO: implement similarity search
            runbooks=runbook_links,
            oncall=oncall_roster,
            owners=codeowners if codeowners else incident.assigned_to,
            assembled_at=datetime.utcnow(),
            assembly_time_ms=elapsed_ms,
            errors=errors,
        )

        logger.info(
            "context_assembled",
            incident_id=incident.incident_id,
            elapsed_ms=elapsed_ms,
            scm_provider=self.scm_provider,
            has_github=github_ctx is not None,
            has_gitlab=gitlab_ctx is not None,
            has_datadog=datadog_ctx is not None,
            has_topology=topology_ctx is not None,
            blast_radius=topology_ctx.blast_radius_count if topology_ctx else 0,
            has_ai=ai_summary is not None,
            has_oncall=oncall_roster is not None,
            oncall_count=len(oncall_roster.oncall_persons) if oncall_roster else 0,
            error_count=len(errors),
        )

        # Deliver to Slack
        await self.slack.send_context_card(card, channel=slack_channel)

        return card

    async def _fetch_scm_context(self, service_name: str):
        """Fetch SCM context from GitHub or GitLab based on configuration."""
        if self.scm_provider == "github":
            return await self._fetch_github_context(service_name)
        elif self.scm_provider == "gitlab":
            return await self._fetch_gitlab_context(service_name)
        else:
            return None

    async def _fetch_github_context(self, service_name: str):
        """Fetch GitHub context with error handling."""
        try:
            return await self.github.get_context(service_name)
        except Exception as e:
            logger.error("github_context_failed", service=service_name, error=str(e))
            return None

    async def _fetch_gitlab_context(self, service_name: str):
        """Fetch GitLab context with error handling."""
        try:
            return await self.gitlab.get_context(service_name)
        except Exception as e:
            logger.error("gitlab_context_failed", service=service_name, error=str(e))
            return None

    async def _fetch_log_context(self, service_name: str):
        """Fetch log context from configured provider (Datadog or CloudWatch)."""
        try:
            return await self.log_adapter.get_context(service_name)
        except Exception as e:
            logger.error(
                "log_context_failed",
                service=service_name,
                provider=self.log_provider,
                error=str(e),
            )
            return None

    async def _fetch_datadog_context(self, service_name: str):
        """Fetch Datadog context with error handling. Deprecated: use _fetch_log_context."""
        return await self._fetch_log_context(service_name)

    async def _fetch_oncall_roster(self, service_name: str) -> OnCallRoster | None:
        """Fetch on-call roster for the service."""
        if not getattr(self.settings, "oncall_enabled", True):
            return None

        try:
            roster = await self.oncall.get_oncall_for_service(service_name)
            if roster:
                logger.info(
                    "oncall_roster_fetched",
                    service=service_name,
                    schedule_id=roster.schedule_id,
                    oncall_count=len(roster.oncall_persons),
                    oncall_names=roster.oncall_names,
                )
            return roster
        except Exception as e:
            logger.error(
                "oncall_roster_failed",
                service=service_name,
                error=str(e),
            )
            return None

    async def _fetch_topology_context(
        self, service_name: str
    ) -> TopologyContext | None:
        """
        Fetch topology context - upstream/downstream dependencies and blast radius.

        Returns TopologyContext with:
        - upstream_services: Services this depends on
        - downstream_services: Services that depend on this (blast radius)
        - critical_paths: Critical dependency chains
        """
        try:
            # Get service by name (may need to look up by ID)
            service = await self.dependencies.get_service(service_name)
            if not service:
                logger.debug("service_not_in_topology", service=service_name)
                return None

            # Get blast radius (what breaks if this service fails)
            blast_radius = await self.dependencies.calculate_blast_radius(service.id)

            # Get upstream/downstream dependencies
            deps = await self.dependencies.get_service_dependencies(service.id)
            upstream = deps.get("upstream", [])
            downstream = deps.get("downstream", [])

            # Get critical services affected
            critical_affected = blast_radius.critical_affected if blast_radius else []

            # Build critical paths from impact paths
            critical_paths = []
            if blast_radius and blast_radius.impact_paths:
                for path in blast_radius.impact_paths[:5]:
                    if path.has_critical_hop:
                        critical_paths.append(path.path)

            topology = TopologyContext(
                service_id=service.id,
                service_name=service.name,
                criticality=(
                    service.criticality.value if service.criticality else "unknown"
                ),
                team=service.team,
                upstream_services=upstream,
                downstream_services=downstream,
                blast_radius_count=blast_radius.affected_count if blast_radius else 0,
                critical_services_affected=critical_affected,
                risk_score=blast_radius.risk_score if blast_radius else 0.0,
                critical_paths=critical_paths,
            )

            logger.info(
                "topology_context_fetched",
                service=service_name,
                upstream_count=len(upstream),
                downstream_count=len(downstream),
                blast_radius=topology.blast_radius_count,
                risk_score=topology.risk_score,
            )

            return topology

        except Exception as e:
            logger.error(
                "topology_context_failed",
                service=service_name,
                error=str(e),
            )
            return None

    def compress_logs(self, logs: list[str], service_name: str) -> CompressedLogs:
        """
        Compress logs using the log compressor pipeline.

        Returns structured, deduplicated log patterns for efficient LLM consumption.
        """
        return self.log_compressor.compress(
            logs=logs,
            service_name=service_name,
            max_patterns=30,
        )
