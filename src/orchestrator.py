"""Context orchestrator - the core of the incident copilot."""

import asyncio
import time
from datetime import datetime
from typing import cast

import structlog

from .ai import LogSummarizer, VerdictEngine
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
from .memory import IncidentMemoryConfig, IncidentMemoryStore, IncidentRecall, RecallQuery
from .memory.models import IncidentRecallResult
from .metrics.latency_tracker import LatencyTracker, Phase
from .models import (
    ContextCard,
    DatadogContext,
    GitHubContext,
    GitLabContext,
    OnCallRoster,
    PastIncident,
    PagerDutyIncident,
    RunbookLink,
    TopologyContext,
)
from .runbooks import RunbookLinker
from .similarity import SimilaritySearch

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

        # AI Verdict Engine — opinionated root cause assessment
        self.verdict_engine = VerdictEngine(settings)

        # Similarity search for past incidents
        self.similarity_search = SimilaritySearch(settings)
        self.memory_config = IncidentMemoryConfig.from_settings(settings)
        self.memory_store: IncidentMemoryStore | None = None
        self.incident_recall: IncidentRecall | None = None
        if self.memory_config.enabled:
            try:
                self.memory_store = IncidentMemoryStore(
                    database_url=self.memory_config.database_url,
                    config=self.memory_config,
                )
                self.incident_recall = IncidentRecall(
                    settings=settings,
                    store=self.memory_store,
                    config=self.memory_config,
                )
            except Exception as e:
                logger.warning("incident_memory_init_failed", error=str(e))
                self.memory_store = None
                self.incident_recall = None

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

        # Initialize latency tracker — T₀ is when the alert originally fired
        tracker = LatencyTracker(incident.incident_id, incident.service_name)
        tracker.set_alert_fired_at(incident.triggered_at)
        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        logger.info(
            "processing_incident",
            incident_id=incident.incident_id,
            service=incident.service_name,
        )

        tracker.start(Phase.CONTEXT_FETCH_START)

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

        tracker.end(Phase.CONTEXT_FETCH_START)

        # Find similar past incidents (Incident Memory recall first)
        similar_incidents: list[PastIncident] = []
        similar_from_memory = await self._recall_similar_incidents_from_memory(
            incident=incident,
            github_ctx=github_ctx,
            gitlab_ctx=gitlab_ctx,
            datadog_ctx=datadog_ctx,
            errors=errors,
        )
        if similar_from_memory:
            similar_incidents = similar_from_memory
        else:
            # Fallback to legacy similarity search when memory recall is unavailable
            # or returns no relevant results.
            similar_incidents = await self._fallback_similarity_search(
                incident=incident,
                datadog_ctx=datadog_ctx,
                errors=errors,
            )

        # AI summarization (if we have logs)
        ai_summary = None
        if datadog_ctx and datadog_ctx.logs:
            tracker.start(Phase.AI_SUMMARIZE)
            try:
                ai_summary = await asyncio.wait_for(
                    self.summarizer.summarize(
                        datadog_ctx.logs,
                        incident.service_name,
                        similar_incidents=similar_incidents,
                    ),
                    timeout=5.0,
                )
                tracker.end(Phase.AI_SUMMARIZE)
            except TimeoutError:
                tracker.end(Phase.AI_SUMMARIZE, success=False, error="timeout")
                logger.warning("ai_summarization_timeout")
                errors.append("AI summarization timed out")
            except Exception as e:
                tracker.end(Phase.AI_SUMMARIZE, success=False, error=str(e))
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

        # Generate AI Verdict — the opinionated root cause assessment
        verdict = None
        tracker.start(Phase.AI_VERDICT)
        try:
            # Prepare deploy data for the verdict engine
            deploy_data = None
            if github_ctx and github_ctx.recent_deploys:
                deploy_data = [d.model_dump() for d in github_ctx.recent_deploys]
            elif gitlab_ctx and gitlab_ctx.recent_deploys:
                deploy_data = [d.model_dump() for d in gitlab_ctx.recent_deploys]

            log_summary_data = ai_summary.model_dump() if ai_summary else None
            metrics_data = (
                datadog_ctx.metrics.model_dump()
                if datadog_ctx and datadog_ctx.metrics
                else None
            )
            topology_data = topology_ctx.model_dump() if topology_ctx else None

            verdict = await asyncio.wait_for(
                self.verdict_engine.generate_verdict(
                    title=incident.title,
                    service_name=incident.service_name,
                    severity=incident.severity.value,
                    triggered_at=incident.triggered_at,
                    recent_deploys=deploy_data,
                    log_summary=log_summary_data,
                    metrics=metrics_data,
                    topology=topology_data,
                ),
                timeout=5.0,
            )
            tracker.end(Phase.AI_VERDICT)
        except TimeoutError:
            tracker.end(Phase.AI_VERDICT, success=False, error="timeout")
            logger.warning("verdict_generation_timeout")
            errors.append("AI verdict timed out")
        except Exception as e:
            tracker.end(Phase.AI_VERDICT, success=False, error=str(e))
            logger.error("verdict_generation_error", error=str(e))
            errors.append(f"Verdict: {str(e)}")

        # Extract inline runbook steps from matched runbooks
        runbook_steps: list[str] = []
        if runbook_links:
            try:
                runbook_steps = self._extract_runbook_steps(
                    runbook_links, incident.service_name
                )
            except Exception as e:
                logger.error("runbook_step_extraction_error", error=str(e))

        # Assemble context card
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Get codeowners from whichever SCM is configured
        codeowners: list[str] = []
        if github_ctx:
            codeowners = github_ctx.codeowners
        elif gitlab_ctx:
            codeowners = gitlab_ctx.codeowners

        tracker.start(Phase.CARD_ASSEMBLED)

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
            verdict=verdict,
            similar_incidents=similar_incidents,
            runbooks=runbook_links,
            runbook_steps=runbook_steps,
            oncall=oncall_roster,
            owners=codeowners if codeowners else incident.assigned_to,
            assembled_at=datetime.utcnow(),
            assembly_time_ms=elapsed_ms,
            errors=errors,
        )

        tracker.end(Phase.CARD_ASSEMBLED)

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
        tracker.start(Phase.CARD_DELIVERED)
        await self.slack.send_context_card(card, channel=slack_channel)
        tracker.end(Phase.CARD_DELIVERED)

        # Finalize latency report
        latency_report = tracker.log_report()
        card.latency_report = latency_report

        return card

    async def _recall_similar_incidents_from_memory(
        self,
        incident: PagerDutyIncident,
        github_ctx: GitHubContext | None,
        gitlab_ctx: GitLabContext | None,
        datadog_ctx: DatadogContext | None,
        errors: list[str],
    ) -> list[PastIncident]:
        """Recall similar incidents from Incident Memory."""
        if not self.incident_recall:
            return []

        try:
            recall_query = RecallQuery(
                narrative=self._build_recall_narrative(
                    incident=incident,
                    github_ctx=github_ctx,
                    gitlab_ctx=gitlab_ctx,
                    datadog_ctx=datadog_ctx,
                ),
                services=[incident.service_name],
                severity=incident.severity.value,
                lookback_days=180,
                limit=3,
            )
            recalled = await asyncio.wait_for(
                self.incident_recall.recall(recall_query),
                timeout=5.0,
            )
            similar_incidents = self._map_recall_results_to_past_incidents(recalled)
            logger.info(
                "incident_memory_recall_completed",
                incident_id=incident.incident_id,
                count=len(similar_incidents),
            )
            return similar_incidents
        except TimeoutError:
            logger.warning("incident_memory_recall_timeout")
            errors.append("Incident memory recall timed out")
            return []
        except Exception as e:
            logger.warning("incident_memory_recall_failed", error=str(e))
            errors.append(f"Incident memory: {str(e)}")
            return []

    async def _fallback_similarity_search(
        self,
        incident: PagerDutyIncident,
        datadog_ctx: DatadogContext | None,
        errors: list[str],
    ) -> list[PastIncident]:
        """Fallback to legacy similarity search when memory recall misses."""
        try:
            error_logs = None
            if datadog_ctx and datadog_ctx.logs:
                error_logs = [log.message for log in datadog_ctx.logs[:20]]

            similar_incidents = await asyncio.wait_for(
                self.similarity_search.store_and_search(
                    incident_id=incident.incident_id,
                    title=incident.title,
                    service_name=incident.service_name,
                    occurred_at=incident.triggered_at,
                    description=incident.description,
                    error_logs=error_logs,
                    top_n=3,
                ),
                timeout=5.0,
            )
            logger.info(
                "similar_incidents_found",
                incident_id=incident.incident_id,
                count=len(similar_incidents),
                source="similarity_search_fallback",
            )
            return similar_incidents
        except TimeoutError:
            logger.warning("similarity_search_timeout")
            errors.append("Similarity search timed out")
            return []
        except Exception as e:
            logger.error("similarity_search_error", error=str(e))
            errors.append(f"Similarity: {str(e)}")
            return []

    def _build_recall_narrative(
        self,
        incident: PagerDutyIncident,
        github_ctx: GitHubContext | None,
        gitlab_ctx: GitLabContext | None,
        datadog_ctx: DatadogContext | None,
    ) -> str:
        """Build recall narrative from current incident context."""
        parts = [incident.title]
        if incident.description:
            parts.append(incident.description)
        parts.append(f"service={incident.service_name}")
        parts.append(f"severity={incident.severity.value}")

        deploys = []
        if github_ctx and github_ctx.recent_deploys:
            deploys = github_ctx.recent_deploys
        elif gitlab_ctx and gitlab_ctx.recent_deploys:
            deploys = gitlab_ctx.recent_deploys
        if deploys:
            parts.append("recent_deploys:")
            for deploy in deploys[:3]:
                parts.append(
                    f"- {deploy.short_sha} {deploy.author} {deploy.message[:120]}"
                )

        if datadog_ctx and datadog_ctx.logs:
            parts.append("recent_error_logs:")
            for log in datadog_ctx.logs[:20]:
                if log.level.upper() in {"ERROR", "WARN"}:
                    parts.append(f"- {log.level}: {log.message[:220]}")

        if datadog_ctx and datadog_ctx.metrics:
            metrics = datadog_ctx.metrics
            if metrics.error_rate is not None:
                parts.append(f"error_rate={metrics.error_rate}")
            if metrics.latency_p99_ms is not None:
                parts.append(f"latency_p99_ms={metrics.latency_p99_ms}")

        return "\n".join(parts)

    def _map_recall_results_to_past_incidents(
        self, recalled: list[IncidentRecallResult]
    ) -> list[PastIncident]:
        """Map Incident Memory recall results to ContextCard past incidents."""
        mapped: list[PastIncident] = []
        for item in recalled[:3]:
            record = item.record
            service = (
                record.services_affected[0]
                if record.services_affected
                else "unknown-service"
            )
            resolution = record.resolution_summary
            if not resolution and record.resolution_steps:
                resolution = "; ".join(record.resolution_steps[:3])

            mapped.append(
                PastIncident(
                    incident_id=record.id,
                    title=record.title,
                    service=service,
                    severity=record.severity,
                    root_cause=record.root_cause_summary,
                    resolution=resolution,
                    occurred_at=record.created_at,
                    resolved_at=record.resolved_at,
                    similarity_score=self._normalize_similarity_percent(item.score),
                )
            )
        return mapped

    @staticmethod
    def _normalize_similarity_percent(raw_score: float | None) -> float | None:
        """Normalize similarity score to a display percent (0..100)."""
        if raw_score is None:
            return None
        if raw_score <= 1.0:
            return round(max(raw_score, 0.0) * 100, 1)
        return round(min(raw_score, 100.0), 1)

    def _extract_runbook_steps(
        self, runbook_links: list[RunbookLink], service_name: str
    ) -> list[str]:
        """Extract the first actionable steps from the top-matched runbook.

        Parses markdown content to find numbered/bulleted steps, commands,
        or action items. Returns up to 3 steps for inline display.
        """
        import re

        # Get the top-scoring runbook's content from the index
        if not runbook_links:
            return []

        top_link = runbook_links[0]
        index = self.runbook_linker.indexer.load_index()
        if not index:
            return []

        # Find the runbook content by matching title/URL
        runbook_content = None
        for rb in index.runbooks:
            if rb.title == top_link.title or rb.url == top_link.url:
                runbook_content = rb.content
                break

        if not runbook_content:
            return []

        # Extract steps from markdown content
        steps: list[str] = []

        # Look for numbered steps (1. Step, 2. Step) or bullet steps (- Step, * Step)
        # Also look for lines after headers like "## Steps" or "## Resolution"
        lines = runbook_content.split("\n")
        in_steps_section = False

        for line in lines:
            stripped = line.strip()

            # Detect step sections
            if re.match(
                r"^#{1,3}\s*(steps|resolution|troubleshoot|fix|remediat|action|procedure)",
                stripped,
                re.IGNORECASE,
            ):
                in_steps_section = True
                continue

            # New header ends the section
            if in_steps_section and re.match(r"^#{1,3}\s", stripped):
                break

            # Extract numbered steps
            step_match = re.match(r"^\d+[.)]\s+(.+)", stripped)
            if step_match:
                steps.append(step_match.group(1).strip())
                in_steps_section = True  # We're in a step list

            # Extract bullet steps in a steps section
            elif in_steps_section and re.match(r"^[-*]\s+(.+)", stripped):
                bullet_match = re.match(r"^[-*]\s+(.+)", stripped)
                if bullet_match:
                    steps.append(bullet_match.group(1).strip())

            # Extract code blocks as commands (useful for runbooks)
            elif (
                in_steps_section and stripped.startswith("`") and stripped.endswith("`")
            ):
                steps.append(stripped)

            if len(steps) >= 3:
                break

        return steps[:3]

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
