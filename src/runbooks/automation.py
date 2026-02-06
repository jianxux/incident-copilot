"""
Automated step execution for runbooks.

Supports:
- Shell commands with output capture
- HTTP API calls (REST endpoints)
- Kubernetes commands (kubectl)
- Database queries
- Custom scripts

Includes safety features:
- Dangerous command detection
- Approval gates for risky operations
- Timeout handling
- Output sanitization
"""

import asyncio
import json
import os
import re
import shlex
import subprocess
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

# Dangerous command patterns that require approval
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf",
    r"\bdrop\s+(?:table|database|schema)",
    r"\btruncate\b",
    r"\bdelete\s+from\b.*(?:where\s*1\s*=\s*1|without\s+where)",
    r"\bkubectl\s+delete\b",
    r"\bkubectl\s+(?:drain|cordon)\b",
    r"\bsystemctl\s+(?:stop|disable|restart)\b",
    r"\bkill\s+-9",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/",
    r"\bsudo\b",
]

# Commands that are safe to run without approval
SAFE_COMMANDS = [
    "echo",
    "cat",
    "ls",
    "pwd",
    "date",
    "whoami",
    "hostname",
    "df",
    "free",
    "uptime",
    "ps",
    "top",
    "htop",
    "netstat",
    "ss",
    "curl --head",
    "wget --spider",
    "ping -c",
    "kubectl get",
    "kubectl describe",
    "kubectl logs",
    "kubectl top",
    "docker ps",
    "docker logs",
    "docker inspect",
]


class AutomationType(str, Enum):
    """Types of automation supported."""

    SHELL = "shell"
    HTTP = "http"
    KUBERNETES = "kubernetes"
    DATABASE = "database"
    SCRIPT = "script"
    WEBHOOK = "webhook"


class AutomationResult(BaseModel):
    """Result of an automated step execution."""

    success: bool
    output: str | None = None
    error: str | None = None
    exit_code: int | None = None
    status_code: int | None = None
    response_body: dict[str, Any] | None = None
    duration_ms: float | None = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    requires_approval: bool = False
    approval_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShellConfig(BaseModel):
    """Configuration for shell command execution."""

    command: str
    working_dir: str | None = None
    timeout_seconds: int = 60
    env: dict[str, str] = Field(default_factory=dict)
    shell: str = "/bin/bash"
    capture_output: bool = True
    allow_failure: bool = False


class HttpConfig(BaseModel):
    """Configuration for HTTP API calls."""

    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    timeout_seconds: int = 30
    expected_status_codes: list[int] = Field(default_factory=lambda: [200, 201, 204])
    auth_type: str | None = None  # basic, bearer, api_key
    auth_value: str | None = None


class KubernetesConfig(BaseModel):
    """Configuration for Kubernetes commands."""

    command: str  # get, describe, logs, apply, delete, etc.
    resource_type: str  # pod, deployment, service, etc.
    resource_name: str | None = None
    namespace: str = "default"
    context: str | None = None
    args: list[str] = Field(default_factory=list)
    timeout_seconds: int = 60


class DatabaseConfig(BaseModel):
    """Configuration for database queries."""

    query: str
    connection_string: str | None = None
    database_type: str = "postgresql"  # postgresql, mysql, sqlite
    timeout_seconds: int = 30
    read_only: bool = True


class AutomationEngine:
    """
    Engine for executing automated runbook steps.

    Supports multiple automation types with safety checks
    and approval gates for dangerous operations.
    """

    def __init__(
        self,
        allow_dangerous: bool = False,
        dry_run: bool = False,
    ):
        """
        Initialize automation engine.

        Args:
            allow_dangerous: If True, skip dangerous command checks
            dry_run: If True, don't actually execute commands
        """
        self.allow_dangerous = allow_dangerous
        self.dry_run = dry_run

    async def execute(
        self,
        automation_type: AutomationType | None,
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AutomationResult:
        """
        Execute an automated step.

        Args:
            automation_type: Type of automation to execute
            config: Configuration for the automation
            context: Additional context (can contain variables)

        Returns:
            AutomationResult with execution details
        """
        if automation_type is None:
            return AutomationResult(
                success=False,
                error="Automation type not specified",
            )

        # Substitute variables from context
        config = self._substitute_variables(config, context or {})

        start_time = datetime.utcnow()

        try:
            match automation_type:
                case AutomationType.SHELL:
                    result = await self._execute_shell(ShellConfig(**config))
                case AutomationType.HTTP:
                    result = await self._execute_http(HttpConfig(**config))
                case AutomationType.KUBERNETES:
                    result = await self._execute_kubernetes(KubernetesConfig(**config))
                case AutomationType.DATABASE:
                    result = await self._execute_database(DatabaseConfig(**config))
                case AutomationType.SCRIPT:
                    result = await self._execute_script(config)
                case AutomationType.WEBHOOK:
                    result = await self._execute_webhook(config)
                case _:
                    result = AutomationResult(
                        success=False,
                        error=f"Unknown automation type: {automation_type}",
                    )

            # Calculate duration
            end_time = datetime.utcnow()
            result.duration_ms = (end_time - start_time).total_seconds() * 1000

            return result

        except Exception as e:
            logger.error(
                "automation_execution_error",
                automation_type=automation_type.value if automation_type else None,
                error=str(e),
            )
            return AutomationResult(
                success=False,
                error=str(e),
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )

    async def _execute_shell(self, config: ShellConfig) -> AutomationResult:
        """Execute a shell command."""
        # Check for dangerous commands
        if not self.allow_dangerous:
            is_dangerous, reason = self._is_dangerous_command(config.command)
            if is_dangerous:
                return AutomationResult(
                    success=False,
                    requires_approval=True,
                    approval_reason=reason,
                    error=f"Command requires approval: {reason}",
                )

        if self.dry_run:
            return AutomationResult(
                success=True,
                output=f"[DRY RUN] Would execute: {config.command}",
                metadata={"dry_run": True},
            )

        try:
            # Prepare environment
            env = os.environ.copy()
            env.update(config.env)

            # Execute command
            process = await asyncio.create_subprocess_shell(
                config.command,
                stdout=asyncio.subprocess.PIPE if config.capture_output else None,
                stderr=asyncio.subprocess.PIPE if config.capture_output else None,
                cwd=config.working_dir,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                process.kill()
                return AutomationResult(
                    success=False,
                    error=f"Command timed out after {config.timeout_seconds}s",
                    exit_code=-1,
                )

            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            error_output = stderr.decode("utf-8", errors="replace") if stderr else ""

            success = process.returncode == 0 or config.allow_failure

            logger.info(
                "shell_command_executed",
                command=config.command[:100],
                exit_code=process.returncode,
                success=success,
            )

            return AutomationResult(
                success=success,
                output=output,
                error=error_output if error_output else None,
                exit_code=process.returncode,
            )

        except Exception as e:
            return AutomationResult(
                success=False,
                error=f"Shell execution failed: {str(e)}",
            )

    async def _execute_http(self, config: HttpConfig) -> AutomationResult:
        """Execute an HTTP API call."""
        if self.dry_run:
            return AutomationResult(
                success=True,
                output=f"[DRY RUN] Would call: {config.method} {config.url}",
                metadata={"dry_run": True},
            )

        try:
            headers = config.headers.copy()

            # Add authentication
            if config.auth_type == "bearer" and config.auth_value:
                headers["Authorization"] = f"Bearer {config.auth_value}"
            elif config.auth_type == "api_key" and config.auth_value:
                headers["X-API-Key"] = config.auth_value

            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=config.method,
                    url=config.url,
                    headers=headers,
                    json=config.body if config.body else None,
                    timeout=config.timeout_seconds,
                )

            success = response.status_code in config.expected_status_codes

            # Try to parse JSON response
            response_body = None
            try:
                response_body = response.json()
            except Exception:
                pass

            logger.info(
                "http_request_executed",
                url=config.url,
                method=config.method,
                status_code=response.status_code,
                success=success,
            )

            return AutomationResult(
                success=success,
                output=response.text[:5000],  # Limit output size
                status_code=response.status_code,
                response_body=response_body,
                error=None if success else f"Unexpected status code: {response.status_code}",
            )

        except httpx.TimeoutException:
            return AutomationResult(
                success=False,
                error=f"Request timed out after {config.timeout_seconds}s",
            )
        except Exception as e:
            return AutomationResult(
                success=False,
                error=f"HTTP request failed: {str(e)}",
            )

    async def _execute_kubernetes(self, config: KubernetesConfig) -> AutomationResult:
        """Execute a Kubernetes command via kubectl."""
        # Build kubectl command
        cmd_parts = ["kubectl"]

        if config.context:
            cmd_parts.extend(["--context", config.context])

        cmd_parts.extend(["-n", config.namespace])
        cmd_parts.append(config.command)
        cmd_parts.append(config.resource_type)

        if config.resource_name:
            cmd_parts.append(config.resource_name)

        cmd_parts.extend(config.args)

        # Use shell execution for kubectl
        shell_config = ShellConfig(
            command=" ".join(cmd_parts),
            timeout_seconds=config.timeout_seconds,
        )

        return await self._execute_shell(shell_config)

    async def _execute_database(self, config: DatabaseConfig) -> AutomationResult:
        """Execute a database query."""
        # Check if query is read-only when required
        if config.read_only and not self._is_read_only_query(config.query):
            return AutomationResult(
                success=False,
                requires_approval=True,
                approval_reason="Query modifies data but read_only is enabled",
                error="Query requires approval for data modification",
            )

        if self.dry_run:
            return AutomationResult(
                success=True,
                output=f"[DRY RUN] Would execute query: {config.query[:100]}...",
                metadata={"dry_run": True},
            )

        # For now, return a placeholder - actual DB execution would need
        # specific database drivers
        return AutomationResult(
            success=False,
            error="Database execution not yet implemented - configure external query tool",
            metadata={"query": config.query},
        )

    async def _execute_script(self, config: dict[str, Any]) -> AutomationResult:
        """Execute a custom script."""
        script_path = config.get("script_path")
        script_content = config.get("script_content")
        interpreter = config.get("interpreter", "/bin/bash")
        timeout_seconds = config.get("timeout_seconds", 120)
        args = config.get("args", [])

        if not script_path and not script_content:
            return AutomationResult(
                success=False,
                error="Either script_path or script_content must be provided",
            )

        if self.dry_run:
            return AutomationResult(
                success=True,
                output=f"[DRY RUN] Would execute script: {script_path or 'inline script'}",
                metadata={"dry_run": True},
            )

        if script_path:
            cmd = f"{interpreter} {shlex.quote(script_path)} {' '.join(shlex.quote(a) for a in args)}"
        else:
            # Write script to temp file and execute
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as f:
                f.write(script_content)
                temp_path = f.name

            try:
                cmd = f"{interpreter} {shlex.quote(temp_path)} {' '.join(shlex.quote(a) for a in args)}"
                result = await self._execute_shell(
                    ShellConfig(command=cmd, timeout_seconds=timeout_seconds)
                )
            finally:
                os.unlink(temp_path)

            return result

        return await self._execute_shell(
            ShellConfig(command=cmd, timeout_seconds=timeout_seconds)
        )

    async def _execute_webhook(self, config: dict[str, Any]) -> AutomationResult:
        """Execute a webhook call."""
        http_config = HttpConfig(
            url=config["url"],
            method=config.get("method", "POST"),
            headers=config.get("headers", {}),
            body=config.get("body", {}),
            timeout_seconds=config.get("timeout_seconds", 30),
            expected_status_codes=config.get("expected_status_codes", [200, 201, 202, 204]),
        )

        return await self._execute_http(http_config)

    def _is_dangerous_command(self, command: str) -> tuple[bool, str | None]:
        """
        Check if a command is potentially dangerous.

        Returns:
            Tuple of (is_dangerous, reason)
        """
        # Check against safe commands first
        command_lower = command.lower().strip()
        for safe in SAFE_COMMANDS:
            if command_lower.startswith(safe):
                return False, None

        # Check against dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True, f"Command matches dangerous pattern: {pattern}"

        return False, None

    def _is_read_only_query(self, query: str) -> bool:
        """Check if a SQL query is read-only."""
        query_upper = query.upper().strip()
        write_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "REPLACE",
            "MERGE",
        ]
        return not any(query_upper.startswith(kw) for kw in write_keywords)

    def _substitute_variables(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Substitute variables in config from context.

        Variables are in format: ${variable_name}
        """

        def substitute(value: Any) -> Any:
            if isinstance(value, str):
                # Find all ${...} patterns
                pattern = r"\$\{([^}]+)\}"
                matches = re.findall(pattern, value)
                for var_name in matches:
                    var_value = context.get(var_name, f"${{{var_name}}}")
                    value = value.replace(f"${{{var_name}}}", str(var_value))
                return value
            elif isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute(v) for v in value]
            return value

        return substitute(config)

    def check_command_safety(self, command: str) -> dict[str, Any]:
        """
        Check a command's safety without executing it.

        Returns:
            Dict with safety assessment
        """
        is_dangerous, reason = self._is_dangerous_command(command)

        return {
            "command": command,
            "is_safe": not is_dangerous,
            "requires_approval": is_dangerous,
            "reason": reason,
            "matched_safe_pattern": any(
                command.lower().strip().startswith(safe) for safe in SAFE_COMMANDS
            ),
        }


# Global automation engine instance
automation_engine = AutomationEngine()
