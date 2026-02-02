"""Context orchestrator - the core of the incident copilot."""

import asyncio
import time
from datetime import datetime

import structlog

from .ai import LogSummarizer
from .config import Settings
from .integrations import CloudWatchAdapter, DatadogAdapter, GitHubAdapter, GitLabAdapter, SlackAdapter
from .models import ContextCard, PagerDutyIncident, RunbookLink
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

        # Determine SCM provider based on configuration
        # Prefer GitHub if configured, fall back to GitLab
        self.scm_provider = self._detect_scm_provider()
        logger.info("scm_provider_initialized", provider=self.scm_provider)

        # Initialize log provider based on configuration
        self.log_provider = settings.log_provider.lower()
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
        scm_task = asyncio.create_task(
            self._fetch_scm_context(incident.service_name)
        )
        datadog_task = asyncio.create_task(
            self._fetch_log_context(incident.service_name)
        )

        # Wait for both with timeout
        try:
            scm_ctx, datadog_ctx = await asyncio.wait_for(
                asyncio.gather(scm_task, datadog_task, return_exceptions=True),
                timeout=8.0,  # Leave room for AI + Slack
            )

            # Handle exceptions from gather
            if isinstance(scm_ctx, Exception):
                scm_name = "GitHub" if self.scm_provider == "github" else "GitLab"
                logger.error("scm_fetch_error", provider=self.scm_provider, error=str(scm_ctx))
                errors.append(f"{scm_name}: {str(scm_ctx)}")
                scm_ctx = None

            if isinstance(datadog_ctx, Exception):
                provider_names = {
                    "cloudwatch": "CloudWatch",
                    "loki": "Loki",
                    "datadog": "Datadog",
                }
                provider_name = provider_names.get(self.log_provider, "Datadog")
                logger.error(
                    "log_fetch_error",
                    provider=self.log_provider,
                    error=str(datadog_ctx),
                )
                errors.append(f"{provider_name}: {str(datadog_ctx)}")
                datadog_ctx = None

        except TimeoutError:
            logger.warning("context_fetch_timeout")
            errors.append("Context fetch timed out")
            scm_ctx = scm_task.result() if scm_task.done() else None
            datadog_ctx = datadog_task.result() if datadog_task.done() else None
        
        # Extract GitHub context for backward compatibility
        github_ctx = scm_ctx if self.scm_provider == "github" else None
        gitlab_ctx = scm_ctx if self.scm_provider == "gitlab" else None

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
        codeowners = []
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
            ai_summary=ai_summary,
            similar_incidents=[],  # TODO: implement similarity search
            runbooks=runbook_links,
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
            has_ai=ai_summary is not None,
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
