"""Linear integration for incident ticket management.

Creates and updates Linear issues when incidents are detected,
providing a seamless workflow for tracking and resolution.
Uses Linear's GraphQL API.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings

logger = structlog.get_logger()


class LinearPriority(Enum):
    """Linear priority levels (0 = No priority, 1 = Urgent, 4 = Low)."""

    NO_PRIORITY = 0
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class LinearIssue(BaseModel):
    """Linear issue model."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    identifier: str  # e.g., "ENG-123"
    title: str
    url: str
    state: str | None = None
    priority: int | None = None


class LinearCreateIssueRequest(BaseModel):
    """Request model for creating a Linear issue."""

    team_id: str
    title: str
    description: str | None = None
    priority: int | None = None  # 0-4 (0=no priority, 1=urgent, 4=low)
    project_id: str | None = None
    label_ids: list[str] = Field(default_factory=list)
    assignee_id: str | None = None
    state_id: str | None = None  # Workflow state ID


class LinearWorkflowState(BaseModel):
    """Linear workflow state model."""

    id: str
    name: str
    type: str  # triage, unstarted, started, completed, canceled


class LinearComment(BaseModel):
    """Linear comment model."""

    id: str
    body: str
    created_at: datetime | None = None


class LinearLabel(BaseModel):
    """Linear label model."""

    id: str
    name: str
    color: str | None = None


class LinearTeam(BaseModel):
    """Linear team model."""

    id: str
    name: str
    key: str  # Short identifier, e.g., "ENG"


class LinearClient:
    """Async client for Linear GraphQL API."""

    GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
    ):
        """Initialize Linear client.

        Args:
            api_key: Linear API key (created at https://linear.app/settings/api)
            team_id: Default team ID for creating issues
        """
        settings = get_settings()

        self.api_key = api_key or settings.linear_api_key
        self.default_team_id = team_id or settings.linear_team_id
        self.default_label_ids = settings.linear_label_ids or []

        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if Linear integration is properly configured."""
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _execute_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            ValueError: If Linear is not configured
            httpx.HTTPError: If the request fails
        """
        if not self.is_configured:
            raise ValueError("Linear integration not configured")

        client = await self._get_client()

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await client.post(self.GRAPHQL_ENDPOINT, json=payload)
        response.raise_for_status()

        result = response.json()

        if "errors" in result:
            errors = result["errors"]
            error_msg = "; ".join(e.get("message", str(e)) for e in errors)
            logger.error("linear_graphql_error", errors=errors)
            raise ValueError(f"Linear API error: {error_msg}")

        return result.get("data", {})

    async def create_issue(
        self,
        request: LinearCreateIssueRequest,
    ) -> LinearIssue:
        """Create a new Linear issue.

        Args:
            request: Issue creation request with details

        Returns:
            Created issue with identifier and ID
        """
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                    priority
                }
            }
        }
        """

        input_data: dict[str, Any] = {
            "teamId": request.team_id,
            "title": request.title,
        }

        if request.description:
            input_data["description"] = request.description

        if request.priority is not None:
            input_data["priority"] = request.priority

        if request.project_id:
            input_data["projectId"] = request.project_id

        if request.label_ids:
            input_data["labelIds"] = request.label_ids

        if request.assignee_id:
            input_data["assigneeId"] = request.assignee_id

        if request.state_id:
            input_data["stateId"] = request.state_id

        logger.info(
            "linear_creating_issue",
            team_id=request.team_id,
            title=request.title[:50],
        )

        data = await self._execute_query(mutation, {"input": input_data})

        issue_data = data["issueCreate"]["issue"]
        issue = LinearIssue(
            id=issue_data["id"],
            identifier=issue_data["identifier"],
            title=issue_data["title"],
            url=issue_data["url"],
            state=issue_data.get("state", {}).get("name"),
            priority=issue_data.get("priority"),
        )

        logger.info(
            "linear_issue_created",
            issue_identifier=issue.identifier,
            issue_id=issue.id,
        )

        return issue

    async def get_issue(self, issue_id: str) -> LinearIssue:
        """Get issue details by ID or identifier.

        Args:
            issue_id: Issue ID or identifier (e.g., "ENG-123")

        Returns:
            Issue details
        """
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                url
                state {
                    name
                }
                priority
            }
        }
        """

        data = await self._execute_query(query, {"id": issue_id})

        issue_data = data["issue"]
        return LinearIssue(
            id=issue_data["id"],
            identifier=issue_data["identifier"],
            title=issue_data["title"],
            url=issue_data["url"],
            state=issue_data.get("state", {}).get("name"),
            priority=issue_data.get("priority"),
        )

    async def update_issue(
        self,
        issue_id: str,
        state_id: str | None = None,
        priority: int | None = None,
        assignee_id: str | None = None,
        label_ids: list[str] | None = None,
    ) -> LinearIssue:
        """Update an existing issue.

        Args:
            issue_id: Issue ID to update
            state_id: New workflow state ID
            priority: New priority (0-4)
            assignee_id: New assignee ID
            label_ids: New label IDs (replaces existing)

        Returns:
            Updated issue
        """
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                    priority
                }
            }
        }
        """

        input_data: dict[str, Any] = {}

        if state_id is not None:
            input_data["stateId"] = state_id

        if priority is not None:
            input_data["priority"] = priority

        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id

        if label_ids is not None:
            input_data["labelIds"] = label_ids

        data = await self._execute_query(mutation, {"id": issue_id, "input": input_data})

        issue_data = data["issueUpdate"]["issue"]
        issue = LinearIssue(
            id=issue_data["id"],
            identifier=issue_data["identifier"],
            title=issue_data["title"],
            url=issue_data["url"],
            state=issue_data.get("state", {}).get("name"),
            priority=issue_data.get("priority"),
        )

        logger.info(
            "linear_issue_updated",
            issue_identifier=issue.identifier,
            new_state=issue.state,
        )

        return issue

    async def add_comment(
        self,
        issue_id: str,
        body: str,
    ) -> LinearComment:
        """Add a comment to an issue.

        Args:
            issue_id: Issue ID
            body: Comment body (supports Markdown)

        Returns:
            Created comment
        """
        mutation = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment {
                    id
                    body
                    createdAt
                }
            }
        }
        """

        data = await self._execute_query(
            mutation,
            {"input": {"issueId": issue_id, "body": body}},
        )

        comment_data = data["commentCreate"]["comment"]

        logger.info("linear_comment_added", issue_id=issue_id)

        return LinearComment(
            id=comment_data["id"],
            body=comment_data["body"],
            created_at=comment_data.get("createdAt"),
        )

    async def get_workflow_states(self, team_id: str | None = None) -> list[LinearWorkflowState]:
        """Get workflow states for a team.

        Args:
            team_id: Team ID (uses default if not specified)

        Returns:
            List of workflow states
        """
        team_id = team_id or self.default_team_id
        if not team_id:
            raise ValueError("Team ID required to get workflow states")

        query = """
        query GetWorkflowStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                    }
                }
            }
        }
        """

        data = await self._execute_query(query, {"teamId": team_id})

        states = []
        for state_data in data["team"]["states"]["nodes"]:
            states.append(
                LinearWorkflowState(
                    id=state_data["id"],
                    name=state_data["name"],
                    type=state_data["type"],
                )
            )

        return states

    async def get_team(self, team_id: str | None = None) -> LinearTeam:
        """Get team details.

        Args:
            team_id: Team ID (uses default if not specified)

        Returns:
            Team details
        """
        team_id = team_id or self.default_team_id
        if not team_id:
            raise ValueError("Team ID required")

        query = """
        query GetTeam($id: String!) {
            team(id: $id) {
                id
                name
                key
            }
        }
        """

        data = await self._execute_query(query, {"id": team_id})

        team_data = data["team"]
        return LinearTeam(
            id=team_data["id"],
            name=team_data["name"],
            key=team_data["key"],
        )

    async def get_labels(self, team_id: str | None = None) -> list[LinearLabel]:
        """Get labels for a team.

        Args:
            team_id: Team ID (uses default if not specified)

        Returns:
            List of labels
        """
        team_id = team_id or self.default_team_id
        if not team_id:
            raise ValueError("Team ID required to get labels")

        query = """
        query GetLabels($teamId: String!) {
            team(id: $teamId) {
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
            }
        }
        """

        data = await self._execute_query(query, {"teamId": team_id})

        labels = []
        for label_data in data["team"]["labels"]["nodes"]:
            labels.append(
                LinearLabel(
                    id=label_data["id"],
                    name=label_data["name"],
                    color=label_data.get("color"),
                )
            )

        return labels

    async def link_issues(
        self,
        issue_id: str,
        related_issue_id: str,
    ) -> None:
        """Link two issues together.

        Args:
            issue_id: Source issue ID
            related_issue_id: Related issue ID
        """
        mutation = """
        mutation CreateIssueRelation($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
            }
        }
        """

        await self._execute_query(
            mutation,
            {
                "input": {
                    "issueId": issue_id,
                    "relatedIssueId": related_issue_id,
                    "type": "related",
                }
            },
        )

        logger.info(
            "linear_issues_linked",
            issue_id=issue_id,
            related_issue_id=related_issue_id,
        )

    async def search_issues(
        self,
        query: str,
        team_id: str | None = None,
        limit: int = 50,
    ) -> list[LinearIssue]:
        """Search for issues.

        Args:
            query: Search query string
            team_id: Filter by team ID
            limit: Maximum number of results

        Returns:
            List of matching issues
        """
        gql_query = """
        query SearchIssues($filter: IssueFilter, $first: Int) {
            issues(filter: $filter, first: $first) {
                nodes {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                    priority
                }
            }
        }
        """

        filter_data: dict[str, Any] = {}

        if query:
            filter_data["title"] = {"containsIgnoreCase": query}

        if team_id:
            filter_data["team"] = {"id": {"eq": team_id}}
        elif self.default_team_id:
            filter_data["team"] = {"id": {"eq": self.default_team_id}}

        data = await self._execute_query(
            gql_query,
            {"filter": filter_data if filter_data else None, "first": limit},
        )

        issues = []
        for issue_data in data["issues"]["nodes"]:
            issues.append(
                LinearIssue(
                    id=issue_data["id"],
                    identifier=issue_data["identifier"],
                    title=issue_data["title"],
                    url=issue_data["url"],
                    state=issue_data.get("state", {}).get("name"),
                    priority=issue_data.get("priority"),
                )
            )

        return issues


# Module-level client instance
_linear_client: LinearClient | None = None


def get_linear_client() -> LinearClient:
    """Get the Linear client singleton."""
    global _linear_client
    if _linear_client is None:
        _linear_client = LinearClient()
    return _linear_client


def _severity_to_priority(severity: str) -> int:
    """Map incident severity to Linear priority.

    Linear priorities: 0=No priority, 1=Urgent, 2=High, 3=Normal, 4=Low

    Args:
        severity: Incident severity string

    Returns:
        Linear priority integer
    """
    severity_map = {
        "SEV1": LinearPriority.URGENT.value,
        "CRITICAL": LinearPriority.URGENT.value,
        "HIGH": LinearPriority.HIGH.value,
        "SEV2": LinearPriority.HIGH.value,
        "MEDIUM": LinearPriority.NORMAL.value,
        "SEV3": LinearPriority.NORMAL.value,
        "LOW": LinearPriority.LOW.value,
        "SEV4": LinearPriority.LOW.value,
    }
    return severity_map.get(severity.upper(), LinearPriority.NORMAL.value)


async def create_incident_ticket(
    service_name: str,
    alert_summary: str,
    severity: str,
    context_card_url: str | None = None,
    deployments: list[dict] | None = None,
    log_summary: str | None = None,
    similar_incidents: list[dict] | None = None,
    runbook_url: str | None = None,
) -> LinearIssue | None:
    """Create a Linear incident ticket with context.

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
        Created Linear issue, or None if Linear is not configured
    """
    client = get_linear_client()

    if not client.is_configured:
        logger.debug("linear_not_configured_skipping_ticket_creation")
        return None

    if not client.default_team_id:
        logger.warning("linear_no_team_id_configured")
        return None

    # Build description in Markdown
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
        description_parts.extend([
            "## Log Analysis",
            log_summary,
            "",
        ])

    if deployments:
        description_parts.append("## Recent Deployments")
        for deploy in deployments[:5]:
            sha = deploy.get("sha", "")[:7] if deploy.get("sha") else "unknown"
            author = deploy.get("author", "unknown")
            message = deploy.get("message", "")[:50]
            description_parts.append(f"- `{sha}` by {author}: {message}")
        description_parts.append("")

    if similar_incidents:
        description_parts.append("## Similar Past Incidents")
        for incident in similar_incidents[:3]:
            description_parts.append(
                f"- {incident.get('title', 'Untitled')} - "
                f"Similarity: {incident.get('score', 0):.0%}"
            )
        description_parts.append("")

    if runbook_url:
        description_parts.append(f"## Runbook\n{runbook_url}")

    description = "\n".join(description_parts)

    # Map severity to Linear priority
    priority = _severity_to_priority(severity)

    # Create the issue
    request = LinearCreateIssueRequest(
        team_id=client.default_team_id,
        title=f"[{severity}] {service_name}: {alert_summary[:80]}",
        description=description,
        priority=priority,
        label_ids=client.default_label_ids,
    )

    try:
        issue = await client.create_issue(request)

        logger.info(
            "linear_incident_ticket_created",
            issue_identifier=issue.identifier,
            service=service_name,
            severity=severity,
        )

        return issue

    except Exception as e:
        logger.error(
            "linear_ticket_creation_failed",
            error=str(e),
            service=service_name,
        )
        return None


async def update_incident_resolved(
    issue_id: str,
    resolution_summary: str,
    resolved_by: str | None = None,
) -> None:
    """Update a Linear incident ticket when resolved.

    Args:
        issue_id: Linear issue ID or identifier
        resolution_summary: Summary of how the incident was resolved
        resolved_by: Name/email of person who resolved it
    """
    client = get_linear_client()

    if not client.is_configured:
        return

    try:
        # Add resolution comment
        comment = f"**Incident Resolved**\n\n{resolution_summary}"
        if resolved_by:
            comment += f"\n\nResolved by: {resolved_by}"

        await client.add_comment(issue_id, comment)

        # Try to find and transition to "Done" or "Completed" state
        if client.default_team_id:
            states = await client.get_workflow_states(client.default_team_id)

            done_state = None
            for state in states:
                if state.type == "completed" or state.name.lower() in (
                    "done",
                    "resolved",
                    "completed",
                ):
                    done_state = state
                    break

            if done_state:
                await client.update_issue(issue_id, state_id=done_state.id)
                logger.info(
                    "linear_incident_ticket_resolved",
                    issue_id=issue_id,
                    new_state=done_state.name,
                )
            else:
                logger.warning(
                    "linear_no_done_state_found",
                    issue_id=issue_id,
                    available_states=[s.name for s in states],
                )
        else:
            logger.warning(
                "linear_cannot_transition_no_team_id",
                issue_id=issue_id,
            )

    except Exception as e:
        logger.error(
            "linear_update_failed",
            issue_id=issue_id,
            error=str(e),
        )


async def transition_issue_status(
    issue_id: str,
    status: str,
    comment: str | None = None,
) -> LinearIssue | None:
    """Transition an issue to a specific status.

    Args:
        issue_id: Linear issue ID or identifier
        status: Target status name (e.g., "In Progress", "Done")
        comment: Optional comment to add with the transition

    Returns:
        Updated issue, or None on failure
    """
    client = get_linear_client()

    if not client.is_configured:
        return None

    try:
        if not client.default_team_id:
            logger.warning("linear_cannot_transition_no_team_id")
            return None

        # Find the target state
        states = await client.get_workflow_states(client.default_team_id)

        target_state = None
        for state in states:
            if state.name.lower() == status.lower():
                target_state = state
                break

        if not target_state:
            logger.warning(
                "linear_target_state_not_found",
                status=status,
                available_states=[s.name for s in states],
            )
            return None

        # Update the issue
        issue = await client.update_issue(issue_id, state_id=target_state.id)

        # Add comment if provided
        if comment:
            await client.add_comment(issue_id, comment)

        return issue

    except Exception as e:
        logger.error(
            "linear_transition_failed",
            issue_id=issue_id,
            target_status=status,
            error=str(e),
        )
        return None
