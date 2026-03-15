"""
Synthetic Incident Generator - Generate test incidents with known root causes.

Used for:
1. Eval harness testing
2. Demo scenarios
3. Integration testing
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4


@dataclass
class SyntheticIncident:
    """A synthetic incident with known ground truth."""

    # Incident metadata
    incident_id: str
    title: str
    service_name: str
    severity: str
    triggered_at: datetime

    # Ground truth (what the copilot should find)
    actual_root_cause: str
    expected_evidence: list[str]
    valid_actions: list[str]

    # Synthetic data
    logs: list[str]
    metrics: dict[str, list[tuple[datetime, float]]]
    recent_deploys: list[dict]

    # Scenario metadata
    scenario_type: str
    difficulty: str  # easy, medium, hard


@dataclass
class ScenarioTemplate:
    """Template for generating incidents."""

    name: str
    description: str
    root_cause_template: str
    evidence_patterns: list[str]
    valid_actions: list[str]
    log_patterns: list[str]
    metric_behavior: dict
    difficulty: str


class SyntheticIncidentGenerator:
    """
    Generates synthetic incidents for testing.

    Scenarios cover common incident types:
    - Database connection issues
    - Memory leaks / OOM
    - Bad deployments
    - Upstream dependency failures
    - Configuration errors
    """

    SERVICES = [
        "payments-api",
        "user-service",
        "order-service",
        "inventory-api",
        "notification-service",
        "auth-service",
    ]

    SCENARIOS: list[ScenarioTemplate] = [
        ScenarioTemplate(
            name="database_connection_exhaustion",
            description="Database connection pool exhausted",
            root_cause_template="Database connection pool exhausted due to {cause}",
            evidence_patterns=[
                "connection timeout",
                "pool exhausted",
                "max connections",
                "cannot acquire connection",
            ],
            valid_actions=[
                "Check connection pool settings",
                "Look for connection leaks",
                "Restart affected pods",
                "Increase max_connections temporarily",
            ],
            log_patterns=[
                "ERROR Connection timeout to database after {duration}ms",
                "ERROR Failed to acquire connection from pool: pool exhausted",
                "WARN Connection pool at {pct}% capacity",
                "ERROR org.postgresql.util.PSQLException: Connection refused",
            ],
            metric_behavior={
                "db_connections": "spike_and_plateau",
                "request_latency_p99": "gradual_increase",
                "error_rate": "step_increase",
            },
            difficulty="medium",
        ),
        ScenarioTemplate(
            name="memory_leak_oom",
            description="Memory leak causing OOM kills",
            root_cause_template="Memory leak in {component} causing OOM",
            evidence_patterns=[
                "oom",
                "killed",
                "memory",
                "heap",
                "gc overhead",
            ],
            valid_actions=[
                "Restart pods to recover",
                "Check recent code changes for memory issues",
                "Increase memory limits temporarily",
                "Enable heap dump on OOM",
            ],
            log_patterns=[
                "FATAL Container killed due to OOM",
                "ERROR java.lang.OutOfMemoryError: Java heap space",
                "WARN GC overhead limit exceeded",
                "ERROR Process exited with signal SIGKILL (9)",
            ],
            metric_behavior={
                "memory_usage": "linear_increase",
                "gc_pause_time": "gradual_increase",
                "container_restarts": "step_increase",
            },
            difficulty="easy",
        ),
        ScenarioTemplate(
            name="bad_deployment",
            description="Recent deployment introduced bug",
            root_cause_template="Deployment {sha} introduced {bug_type}",
            evidence_patterns=[
                "deploy",
                "release",
                "version",
                "rollback",
                "recent change",
            ],
            valid_actions=[
                "Rollback to previous version",
                "Check deployment diff",
                "Contact the deploy author",
            ],
            log_patterns=[
                "ERROR NullPointerException in PaymentProcessor.process",
                "ERROR undefined is not a function",
                "FATAL panic: runtime error: index out of range",
                "ERROR TypeError: Cannot read property 'id' of undefined",
            ],
            metric_behavior={
                "error_rate": "step_increase_after_deploy",
                "request_latency_p99": "step_increase_after_deploy",
            },
            difficulty="easy",
        ),
        ScenarioTemplate(
            name="upstream_timeout",
            description="Upstream service timeout",
            root_cause_template="Upstream service {upstream} timing out",
            evidence_patterns=[
                "timeout",
                "upstream",
                "downstream",
                "circuit breaker",
                "retry",
            ],
            valid_actions=[
                "Check upstream service health",
                "Enable circuit breaker if not active",
                "Increase timeout temporarily",
                "Check for upstream deployments",
            ],
            log_patterns=[
                "ERROR Timeout waiting for response from {upstream}",
                "WARN Circuit breaker OPEN for {upstream}",
                "ERROR HttpTimeoutException: request timed out after 30s",
                "WARN Retrying request to {upstream} (attempt 3/3)",
            ],
            metric_behavior={
                "upstream_latency": "spike",
                "request_latency_p99": "follows_upstream",
                "timeout_rate": "step_increase",
            },
            difficulty="medium",
        ),
        ScenarioTemplate(
            name="config_error",
            description="Configuration error after change",
            root_cause_template="Invalid configuration: {config_issue}",
            evidence_patterns=[
                "config",
                "configuration",
                "environment",
                "missing",
                "invalid",
            ],
            valid_actions=[
                "Check recent config changes",
                "Verify environment variables",
                "Rollback config change",
                "Check config in version control",
            ],
            log_patterns=[
                "FATAL Failed to parse configuration: {error}",
                "ERROR Missing required environment variable: {var}",
                "ERROR Invalid value for config key: {key}",
                "FATAL Application failed to start: configuration error",
            ],
            metric_behavior={
                "startup_failures": "all_fail",
                "healthy_pods": "drop_to_zero",
            },
            difficulty="medium",
        ),
    ]

    def __init__(self, seed: int | None = None):
        if seed:
            random.seed(seed)

    def generate(
        self,
        scenario_name: str | None = None,
        service_name: str | None = None,
        incident_time: datetime | None = None,
    ) -> SyntheticIncident:
        """
        Generate a synthetic incident.

        Args:
            scenario_name: Specific scenario to generate (random if None)
            service_name: Service name (random if None)
            incident_time: When incident occurred (now if None)
        """
        # Select scenario
        if scenario_name:
            scenario = next(
                (s for s in self.SCENARIOS if s.name == scenario_name),
                random.choice(self.SCENARIOS),
            )
        else:
            scenario = random.choice(self.SCENARIOS)

        # Select service
        service = service_name or random.choice(self.SERVICES)

        # Set time
        incident_time = incident_time or datetime.now(UTC)

        # Generate incident ID
        incident_id = f"INC-{uuid4().hex[:8].upper()}"

        # Generate root cause with specific details
        root_cause = self._generate_root_cause(scenario, service)

        # Generate logs
        logs = self._generate_logs(scenario, service, incident_time)

        # Generate metrics
        metrics = self._generate_metrics(scenario, service, incident_time)

        # Generate deploy history
        deploys = self._generate_deploys(scenario, service, incident_time)

        return SyntheticIncident(
            incident_id=incident_id,
            title=f"{scenario.description} on {service}",
            service_name=service,
            severity=random.choice(["P1", "P2"]),
            triggered_at=incident_time,
            actual_root_cause=root_cause,
            expected_evidence=scenario.evidence_patterns,
            valid_actions=scenario.valid_actions,
            logs=logs,
            metrics=metrics,
            recent_deploys=deploys,
            scenario_type=scenario.name,
            difficulty=scenario.difficulty,
        )

    def generate_batch(self, count: int = 20) -> list[SyntheticIncident]:
        """Generate a batch of diverse synthetic incidents."""
        incidents = []

        # Ensure we cover all scenarios at least once
        for scenario in self.SCENARIOS:
            incidents.append(self.generate(scenario_name=scenario.name))

        # Fill remaining with random
        while len(incidents) < count:
            incidents.append(self.generate())

        return incidents[:count]

    def _generate_root_cause(self, scenario: ScenarioTemplate, service: str) -> str:
        """Generate specific root cause from template."""
        template = scenario.root_cause_template

        substitutions = {
            "cause": random.choice(
                [
                    "connection leak in ORM",
                    "missing connection close",
                    "long-running transactions",
                ]
            ),
            "component": random.choice(
                [
                    "request handler",
                    "cache layer",
                    "session manager",
                ]
            ),
            "sha": f"abc{random.randint(1000, 9999)}",
            "bug_type": random.choice(
                [
                    "null pointer exception",
                    "type error",
                    "panic",
                ]
            ),
            "upstream": random.choice(
                [
                    "auth-service",
                    "user-service",
                    "inventory-api",
                ]
            ),
            "config_issue": random.choice(
                [
                    "missing DATABASE_URL",
                    "invalid JSON in config",
                    "wrong port number",
                ]
            ),
        }

        for key, value in substitutions.items():
            template = template.replace(f"{{{key}}}", value)

        return template

    def _generate_logs(
        self,
        scenario: ScenarioTemplate,
        service: str,
        incident_time: datetime,
    ) -> list[str]:
        """Generate realistic log lines for scenario."""
        logs = []

        # Generate logs for 30 minutes before incident
        for minutes_ago in range(30, 0, -1):
            timestamp = incident_time - timedelta(minutes=minutes_ago)
            ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # More errors closer to incident time
            error_probability = 0.1 + (30 - minutes_ago) * 0.02

            for pattern in scenario.log_patterns:
                if random.random() < error_probability:
                    log_line = self._fill_log_pattern(pattern, service)
                    logs.append(f"{ts_str} [{service}] {log_line}")

        # Add some noise
        for _ in range(50):
            timestamp = incident_time - timedelta(minutes=random.randint(1, 30))
            ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            logs.append(f"{ts_str} [{service}] INFO Health check passed")
            logs.append(
                f"{ts_str} [{service}] DEBUG Processing request {uuid4().hex[:8]}"
            )

        # Sort by timestamp
        logs.sort()

        return logs

    def _fill_log_pattern(self, pattern: str, service: str) -> str:
        """Fill in pattern variables."""
        substitutions = {
            "duration": str(random.randint(5000, 30000)),
            "pct": str(random.randint(80, 100)),
            "upstream": random.choice(["auth-service", "user-service"]),
            "error": random.choice(["invalid syntax", "missing field"]),
            "var": random.choice(["DATABASE_URL", "API_KEY"]),
            "key": random.choice(["port", "host", "timeout"]),
        }

        for key, value in substitutions.items():
            pattern = pattern.replace(f"{{{key}}}", value)

        return pattern

    def _generate_metrics(
        self,
        scenario: ScenarioTemplate,
        service: str,
        incident_time: datetime,
    ) -> dict[str, list[tuple[datetime, float]]]:
        """Generate metric time series for scenario."""
        metrics = {}

        for metric_name, behavior in scenario.metric_behavior.items():
            series = []

            for minutes_ago in range(60, 0, -1):
                timestamp = incident_time - timedelta(minutes=minutes_ago)

                if behavior == "spike_and_plateau":
                    if minutes_ago > 30:
                        value = 10 + random.random() * 5
                    else:
                        value = 90 + random.random() * 10
                elif behavior == "gradual_increase":
                    value = 10 + (60 - minutes_ago) * 1.5 + random.random() * 5
                elif behavior == "step_increase":
                    if minutes_ago > 20:
                        value = 5 + random.random() * 2
                    else:
                        value = 50 + random.random() * 10
                elif behavior == "linear_increase":
                    value = (60 - minutes_ago) * 2 + random.random() * 5
                else:
                    value = random.random() * 100

                series.append((timestamp, value))

            metrics[f"{service}.{metric_name}"] = series

        return metrics

    def _generate_deploys(
        self,
        scenario: ScenarioTemplate,
        service: str,
        incident_time: datetime,
    ) -> list[dict]:
        """Generate recent deployment history."""
        deploys = []

        # Deploy 30 minutes before incident (potential culprit)
        if "deployment" in scenario.name or random.random() > 0.5:
            deploys.append(
                {
                    "sha": f"abc{random.randint(1000, 9999)}",
                    "message": "feat: Update payment processing logic",
                    "author": "developer@example.com",
                    "timestamp": (incident_time - timedelta(minutes=30)).isoformat(),
                    "files_changed": random.randint(5, 20),
                }
            )

        # Older deploys
        for days_ago in [1, 3, 7]:
            deploys.append(
                {
                    "sha": f"xyz{random.randint(1000, 9999)}",
                    "message": random.choice(
                        [
                            "chore: Update dependencies",
                            "fix: Minor bug fixes",
                            "docs: Update README",
                        ]
                    ),
                    "author": "developer@example.com",
                    "timestamp": (incident_time - timedelta(days=days_ago)).isoformat(),
                    "files_changed": random.randint(1, 10),
                }
            )

        return deploys
