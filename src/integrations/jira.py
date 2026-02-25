"""Jira integration for incident ticket management.

Creates and updates Jira issues when incidents are detected,
providing a seamless workflow for tracking and resolution.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings

logger = structlog.get_logger()


class JiraIssue(BaseModel):
    """Jira issue model."""

    key: str
    id: str
    self_url: str = Field(alias="self")
    summary: str | None = None
    status: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class JiraCreateIssueRequest(BaseModel):
    """Request model for creating a Jira issue."""

    project_key: str
    summary: str
    description: str
    issue_type: str = "Bug"  # Could be "Incident" if configured
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    assignee: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class JiraTransition(BaseModel):
    """Jira issue transition."""

    id: str
    name: str


class JiraComment(BaseModel):
    """Jira comment model."""

    body: str
    author: str | None = None
    created: datetime | None = None


class JiraClient:
    """Async client for Jira Cloud REST API v3."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        """Initialize Jira client.

        Args:
            base_url: Jira instance URL (e.g., https://yourcompany.atlassian.net)
            email: Jira user email for authentication
            api_token: Jira API token (created at https://id.atlassian.com/manage-profile/security/api-tokens)
        """
        settings = get_settings()

        self.base_url = (base_url or settings.jira_base_url or "").rstrip("/")
        self.email = email or settings.jira_email
        self.api_token = api_token or settings.jira_api_token
        self.default_project = settings.jira_default_project

        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if Jira integration is properly configured."""
        return bool(self.base_url and self.email and self.api_token)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            import base64

            # Jira Cloud uses Basic auth with email:api_token
            auth_string = f"{self.email}:{self.api_token}"
            auth_bytes = base64.b64encode(auth_string.encode()).decode()

            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/rest/api/3",
                headers={
                    "Authorization": f"Basic {auth_bytes}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def create_issue(
        self,
        request: JiraCreateIssueRequest,
    ) -> JiraIssue:
        """Create a new Jira issue.

        Args:
            request: Issue creation request with details

        Returns:
            Created issue with key and ID
        """
        if not self.is_configured:
            raise ValueError("Jira integration not configured")

        client = await self._get_client()

        # Build Atlassian Document Format (ADF) for description
        description_adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": request.description,
                        }
                    ],
                }
            ],
        }

        # Build issue payload
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": request.project_key},
                "summary": request.summary,
                "description": description_adf,
                "issuetype": {"name": request.issue_type},
            }
        }

        # Add optional fields
        if request.priority:
            payload["fields"]["priority"] = {"name": request.priority}

        if request.labels:
            payload["fields"]["labels"] = request.labels

        if request.components:
            payload["fields"]["components"] = [{"name": c} for c in request.components]

        if request.assignee:
            payload["fields"]["assignee"] = {"accountId": request.assignee}

        # Add custom fields
        for field_id, value in request.custom_fields.items():
            payload["fields"][field_id] = value

        logger.info(
            "jira_creating_issue",
            project=request.project_key,
            summary=request.summary[:50],
        )

        response = await client.post("/issue", json=payload)
        response.raise_for_status()

        data = response.json()

        issue = JiraIssue(
            key=data["key"],
            id=data["id"],
            self=data["self"],
            summary=request.summary,
        )

        logger.info(
            "jira_issue_created",
            issue_key=issue.key,
            issue_id=issue.id,
        )

        return issue

    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Get issue details by key.

        Args:
            issue_key: Issue key (e.g., PROJ-123)

        Returns:
            Issue details
        """
        client = await self._get_client()

        response = await client.get(f"/issue/{issue_key}")
        response.raise_for_status()

        data = response.json()

        return JiraIssue(
            key=data["key"],
            id=data["id"],
            self=data["self"],
            summary=data["fields"]["summary"],
            status=data["fields"]["status"]["name"],
        )

    async def add_comment(
        self,
        issue_key: str,
        comment: str,
    ) -> dict:
        """Add a comment to an issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            comment: Comment text

        Returns:
            Created comment data
        """
        client = await self._get_client()

        # ADF format for comment
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment,
                            }
                        ],
                    }
                ],
            }
        }

        response = await client.post(
            f"/issue/{issue_key}/comment",
            json=payload,
        )
        response.raise_for_status()

        logger.info("jira_comment_added", issue_key=issue_key)

        return response.json()

    async def get_transitions(self, issue_key: str) -> list[JiraTransition]:
        """Get available transitions for an issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)

        Returns:
            List of available transitions
        """
        client = await self._get_client()

        response = await client.get(f"/issue/{issue_key}/transitions")
        response.raise_for_status()

        data = response.json()

        return [
            JiraTransition(id=t["id"], name=t["name"])
            for t in data.get("transitions", [])
        ]

    async def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: str | None = None,
    ) -> None:
        """Transition an issue to a new status.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            transition_id: Transition ID to apply
            comment: Optional comment to add during transition
        """
        client = await self._get_client()

        payload: dict[str, Any] = {"transition": {"id": transition_id}}

        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }

        response = await client.post(
            f"/issue/{issue_key}/transitions",
            json=payload,
        )
        response.raise_for_status()

        logger.info(
            "jira_issue_transitioned",
            issue_key=issue_key,
            transition_id=transition_id,
        )

    async def link_issues(
        self,
        inward_issue: str,
        outward_issue: str,
        link_type: str = "Relates",
    ) -> None:
        """Link two issues together.

        Args:
            inward_issue: Inward issue key
            outward_issue: Outward issue key
            link_type: Link type name (e.g., "Relates", "Blocks", "Causes")
        """
        client = await self._get_client()

        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue},
        }

        response = await client.post("/issueLink", json=payload)
        response.raise_for_status()

        logger.info(
            "jira_issues_linked",
            inward=inward_issue,
            outward=outward_issue,
            link_type=link_type,
        )

    async def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> list[JiraIssue]:
        """Search for issues using JQL.

        Args:
            jql: JQL query string
            max_results: Maximum number of results
            fields: Fields to return (None for default)

        Returns:
            List of matching issues
        """
        client = await self._get_client()

        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
        }

        if fields:
            params["fields"] = ",".join(fields)

        response = await client.get("/search", params=params)
        response.raise_for_status()

        data = response.json()

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(
                JiraIssue(
                    key=issue_data["key"],
                    id=issue_data["id"],
                    self=issue_data["self"],
                    summary=issue_data["fields"].get("summary"),
                    status=issue_data["fields"].get("status", {}).get("name"),
                )
            )

        return issues


# Module-level client instance
_jira_client: JiraClient | None = None


def get_jira_client() -> JiraClient:
    """Get the Jira client singleton."""
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient()
    return _jira_client


async def create_incident_ticket(
    service_name: str,
    alert_summary: str,
    severity: str,
    context_card_url: str | None = None,
    deployments: list[dict] | None = None,
    log_summary: str | None = None,
    similar_incidents: list[dict] | None = None,
    runbook_url: str | None = None,
) -> JiraIssue | None:
    """Create a Jira incident ticket with context.

    This is the main integration point called from the orchestrator
    when a new incident is detected.

    Args:
        service_name: Name of the affected service
        alert_summary: Summary of the alert
        severity: Incident severity (HIGH, MEDIUM, LOW)
        context_card_url: URL to the context card (if available)
        deployments: Recent deployments
        log_summary: AI-generated log summary
        similar_incidents: Similar past incidents
        runbook_url: Linked runbook URL

    Returns:
        Created Jira issue, or None if Jira is not configured
    """
    client = get_jira_client()

    if not client.is_configured:
        logger.debug("jira_not_configured_skipping_ticket_creation")
        return None

    # Build description
    description_parts = [
        f"**Service:** {service_name}",
        f"**Alert:** {alert_summary}",
        f"**Severity:** {severity}",
        f"**Triggered:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    if context_card_url:
        description_parts.append(f"**Context Card:** {context_card_url}")
        description_parts.append("")

    if log_summary:
        description_parts.extend(
            [
                "## Log Analysis",
                log_summary,
                "",
            ]
        )

    if deployments:
        description_parts.append("## Recent Deployments")
        for deploy in deployments[:5]:
            sha = deploy.get("sha", "")[:7] if deploy.get("sha") else "unknown"
            author = deploy.get("author", "unknown")
            message = deploy.get("message", "")[:50]
            description_parts.append(f"- {sha} by {author}: {message}")
        description_parts.append("")

    if similar_incidents:
        description_parts.append("## Similar Past Incidents")
        for incident in similar_incidents[:3]:
            description_parts.append(
                f"- [{incident.get('title', 'Untitled')}] - "
                f"Similarity: {incident.get('score', 0):.0%}"
            )
        description_parts.append("")

    if runbook_url:
        description_parts.append(f"## Runbook\n{runbook_url}")

    description = "\n".join(description_parts)

    # Map severity to Jira priority
    priority_map = {
        "SEV1": "Highest",
        "HIGH": "High",
        "SEV2": "High",
        "MEDIUM": "Medium",
        "SEV3": "Medium",
        "LOW": "Low",
        "SEV4": "Low",
    }
    priority = priority_map.get(severity.upper(), "Medium")

    # Create the issue
    request = JiraCreateIssueRequest(
        project_key=client.default_project or "INCIDENT",
        summary=f"[{severity}] {service_name}: {alert_summary[:80]}",
        description=description,
        issue_type="Bug",  # Or "Incident" if configured
        priority=priority,
        labels=["incident", "auto-created", f"service-{service_name.lower()}"],
    )

    try:
        issue = await client.create_issue(request)

        logger.info(
            "incident_ticket_created",
            issue_key=issue.key,
            service=service_name,
            severity=severity,
        )

        return issue

    except Exception as e:
        logger.error(
            "jira_ticket_creation_failed",
            error=str(e),
            service=service_name,
        )
        return None


async def update_incident_resolved(
    issue_key: str,
    resolution_summary: str,
    resolved_by: str | None = None,
) -> None:
    """Update a Jira incident ticket when resolved.

    Args:
        issue_key: Jira issue key (e.g., PROJ-123)
        resolution_summary: Summary of how the incident was resolved
        resolved_by: Name/email of person who resolved it
    """
    client = get_jira_client()

    if not client.is_configured:
        return

    try:
        # Add resolution comment
        comment = f"**Incident Resolved**\n\n{resolution_summary}"
        if resolved_by:
            comment += f"\n\nResolved by: {resolved_by}"

        await client.add_comment(issue_key, comment)

        # Try to transition to "Done" or "Resolved"
        transitions = await client.get_transitions(issue_key)

        done_transition = None
        for t in transitions:
            if t.name.lower() in ("done", "resolved", "closed"):
                done_transition = t
                break

        if done_transition:
            await client.transition_issue(issue_key, done_transition.id)
            logger.info(
                "incident_ticket_resolved",
                issue_key=issue_key,
                transition=done_transition.name,
            )
        else:
            logger.warning(
                "jira_no_done_transition_found",
                issue_key=issue_key,
                available_transitions=[t.name for t in transitions],
            )

    except Exception as e:
        logger.error(
            "jira_update_failed",
            issue_key=issue_key,
            error=str(e),
        )
