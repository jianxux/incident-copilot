"""
PagerDuty API Client
====================

Async HTTP client for PagerDuty REST API v2.
"""

import asyncio
from datetime import datetime
from typing import Any, Optional

import httpx

from .models import (
    CreateIncidentRequest,
    PagerDutyConfig,
    PDEscalationPolicy,
    PDEventsAPIPayload,
    PDIncident,
    PDOnCall,
    PDSchedule,
    PDService,
    PDStatus,
    PDUser,
    UpdateIncidentRequest,
)


class PagerDutyClient:
    """
    Async client for PagerDuty REST API.

    Supports both REST API and Events API.
    """

    BASE_URL = "https://api.pagerduty.com"
    EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, config: PagerDutyConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Token token={self.config.api_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ==================== Incidents ====================

    async def list_incidents(
        self,
        service_ids: Optional[list[str]] = None,
        statuses: Optional[list[PDStatus]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 25,
        offset: int = 0,
        sort_by: str = "created_at:desc",
    ) -> list[PDIncident]:
        """
        List incidents with optional filters.

        Args:
            service_ids: Filter by service IDs
            statuses: Filter by statuses
            since: Filter by created_at since
            until: Filter by created_at until
            limit: Maximum results (1-100)
            offset: Pagination offset
            sort_by: Sort field and direction

        Returns:
            List of incidents
        """
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
            "sort_by": sort_by,
        }

        if service_ids:
            params["service_ids[]"] = service_ids
        if statuses:
            params["statuses[]"] = [s.value for s in statuses]
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        response = await self.client.get("/incidents", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDIncident(**inc) for inc in data.get("incidents", [])]

    async def get_incident(self, incident_id: str) -> PDIncident:
        """Get a single incident by ID."""
        response = await self.client.get(f"/incidents/{incident_id}")
        response.raise_for_status()

        data = response.json()
        return PDIncident(**data["incident"])

    async def create_incident(
        self,
        request: CreateIncidentRequest,
        from_email: str,
    ) -> PDIncident:
        """
        Create a new incident via REST API.

        Args:
            request: Incident creation request
            from_email: Email of the user creating the incident

        Returns:
            Created incident
        """
        incident_data = {
            "type": "incident",
            "title": request.title,
            "service": {
                "id": request.service_id,
                "type": "service_reference",
            },
            "urgency": request.urgency.value,
        }

        if request.body:
            incident_data["body"] = {
                "type": "incident_body",
                "details": request.body,
            }

        if request.priority_id:
            incident_data["priority"] = {
                "id": request.priority_id,
                "type": "priority_reference",
            }

        if request.escalation_policy_id:
            incident_data["escalation_policy"] = {
                "id": request.escalation_policy_id,
                "type": "escalation_policy_reference",
            }

        if request.assignments:
            incident_data["assignments"] = [
                {"assignee": {"id": uid, "type": "user_reference"}}
                for uid in request.assignments
            ]

        if request.conference_bridge:
            incident_data["conference_bridge"] = request.conference_bridge

        if request.incident_key:
            incident_data["incident_key"] = request.incident_key

        response = await self.client.post(
            "/incidents",
            json={"incident": incident_data},
            headers={"From": from_email},
        )
        response.raise_for_status()

        data = response.json()
        return PDIncident(**data["incident"])

    async def update_incident(
        self,
        incident_id: str,
        request: UpdateIncidentRequest,
        from_email: str,
    ) -> PDIncident:
        """
        Update an existing incident.

        Args:
            incident_id: Incident ID to update
            request: Update request
            from_email: Email of the user making the update

        Returns:
            Updated incident
        """
        incident_data: dict[str, Any] = {
            "id": incident_id,
            "type": "incident",
        }

        if request.status:
            incident_data["status"] = request.status.value
        if request.title:
            incident_data["title"] = request.title
        if request.urgency:
            incident_data["urgency"] = request.urgency.value
        if request.priority_id:
            incident_data["priority"] = {
                "id": request.priority_id,
                "type": "priority_reference",
            }
        if request.escalation_policy_id:
            incident_data["escalation_policy"] = {
                "id": request.escalation_policy_id,
                "type": "escalation_policy_reference",
            }
        if request.escalation_level is not None:
            incident_data["escalation_level"] = request.escalation_level
        if request.assignments is not None:
            incident_data["assignments"] = [
                {"assignee": {"id": uid, "type": "user_reference"}}
                for uid in request.assignments
            ]
        if request.resolution:
            incident_data["resolution"] = request.resolution

        response = await self.client.put(
            f"/incidents/{incident_id}",
            json={"incident": incident_data},
            headers={"From": from_email},
        )
        response.raise_for_status()

        data = response.json()
        return PDIncident(**data["incident"])

    async def acknowledge_incident(
        self,
        incident_id: str,
        from_email: str,
    ) -> PDIncident:
        """Acknowledge an incident."""
        return await self.update_incident(
            incident_id,
            UpdateIncidentRequest(status=PDStatus.ACKNOWLEDGED),
            from_email,
        )

    async def resolve_incident(
        self,
        incident_id: str,
        from_email: str,
        resolution: Optional[str] = None,
    ) -> PDIncident:
        """Resolve an incident."""
        return await self.update_incident(
            incident_id,
            UpdateIncidentRequest(status=PDStatus.RESOLVED, resolution=resolution),
            from_email,
        )

    async def add_note(
        self,
        incident_id: str,
        content: str,
        from_email: str,
    ) -> dict:
        """Add a note to an incident."""
        response = await self.client.post(
            f"/incidents/{incident_id}/notes",
            json={"note": {"content": content}},
            headers={"From": from_email},
        )
        response.raise_for_status()
        return response.json()["note"]

    # ==================== Services ====================

    async def list_services(
        self,
        query: Optional[str] = None,
        team_ids: Optional[list[str]] = None,
        include: Optional[list[str]] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PDService]:
        """List services with optional filters."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if query:
            params["query"] = query
        if team_ids:
            params["team_ids[]"] = team_ids
        if include:
            params["include[]"] = include

        response = await self.client.get("/services", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDService(**svc) for svc in data.get("services", [])]

    async def get_service(self, service_id: str) -> PDService:
        """Get a single service by ID."""
        response = await self.client.get(f"/services/{service_id}")
        response.raise_for_status()

        data = response.json()
        return PDService(**data["service"])

    async def create_service(
        self,
        name: str,
        escalation_policy_id: str,
        description: Optional[str] = None,
        auto_resolve_timeout: Optional[int] = None,
        acknowledgement_timeout: Optional[int] = None,
    ) -> PDService:
        """Create a new service."""
        service_data = {
            "type": "service",
            "name": name,
            "escalation_policy": {
                "id": escalation_policy_id,
                "type": "escalation_policy_reference",
            },
        }

        if description:
            service_data["description"] = description
        if auto_resolve_timeout:
            service_data["auto_resolve_timeout"] = auto_resolve_timeout
        if acknowledgement_timeout:
            service_data["acknowledgement_timeout"] = acknowledgement_timeout

        response = await self.client.post(
            "/services",
            json={"service": service_data},
        )
        response.raise_for_status()

        data = response.json()
        return PDService(**data["service"])

    # ==================== Users ====================

    async def list_users(
        self,
        query: Optional[str] = None,
        team_ids: Optional[list[str]] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PDUser]:
        """List users with optional filters."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if query:
            params["query"] = query
        if team_ids:
            params["team_ids[]"] = team_ids

        response = await self.client.get("/users", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDUser(**user) for user in data.get("users", [])]

    async def get_user(self, user_id: str) -> PDUser:
        """Get a single user by ID."""
        response = await self.client.get(f"/users/{user_id}")
        response.raise_for_status()

        data = response.json()
        return PDUser(**data["user"])

    async def get_current_user(self) -> PDUser:
        """Get the current authenticated user."""
        response = await self.client.get("/users/me")
        response.raise_for_status()

        data = response.json()
        return PDUser(**data["user"])

    # ==================== Escalation Policies ====================

    async def list_escalation_policies(
        self,
        query: Optional[str] = None,
        user_ids: Optional[list[str]] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PDEscalationPolicy]:
        """List escalation policies."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if query:
            params["query"] = query
        if user_ids:
            params["user_ids[]"] = user_ids

        response = await self.client.get("/escalation_policies", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDEscalationPolicy(**ep) for ep in data.get("escalation_policies", [])]

    async def get_escalation_policy(self, policy_id: str) -> PDEscalationPolicy:
        """Get a single escalation policy by ID."""
        response = await self.client.get(f"/escalation_policies/{policy_id}")
        response.raise_for_status()

        data = response.json()
        return PDEscalationPolicy(**data["escalation_policy"])

    # ==================== Schedules ====================

    async def list_schedules(
        self,
        query: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PDSchedule]:
        """List schedules."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if query:
            params["query"] = query

        response = await self.client.get("/schedules", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDSchedule(**sched) for sched in data.get("schedules", [])]

    async def get_schedule(
        self,
        schedule_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> PDSchedule:
        """Get a schedule with optional time range for final schedule."""
        params: dict[str, Any] = {}

        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        response = await self.client.get(
            f"/schedules/{schedule_id}",
            params=params if params else None,
        )
        response.raise_for_status()

        data = response.json()
        return PDSchedule(**data["schedule"])

    # ==================== On-Calls ====================

    async def list_oncalls(
        self,
        schedule_ids: Optional[list[str]] = None,
        user_ids: Optional[list[str]] = None,
        escalation_policy_ids: Optional[list[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PDOnCall]:
        """List on-call entries."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if schedule_ids:
            params["schedule_ids[]"] = schedule_ids
        if user_ids:
            params["user_ids[]"] = user_ids
        if escalation_policy_ids:
            params["escalation_policy_ids[]"] = escalation_policy_ids
        if since:
            params["since"] = since.isoformat()
        if until:
            params["until"] = until.isoformat()

        response = await self.client.get("/oncalls", params=params)
        response.raise_for_status()

        data = response.json()
        return [PDOnCall(**oc) for oc in data.get("oncalls", [])]

    async def get_current_oncall(
        self,
        escalation_policy_id: str,
    ) -> Optional[PDOnCall]:
        """Get the current on-call for an escalation policy."""
        now = datetime.utcnow()
        oncalls = await self.list_oncalls(
            escalation_policy_ids=[escalation_policy_id],
            since=now,
            until=now,
        )

        # Return the first level on-call
        for oc in oncalls:
            if oc.escalation_level == 1:
                return oc

        return oncalls[0] if oncalls else None

    # ==================== Events API ====================

    async def send_event(
        self,
        event_action: str,
        routing_key: Optional[str] = None,
        dedup_key: Optional[str] = None,
        summary: Optional[str] = None,
        source: Optional[str] = None,
        severity: str = "critical",
        custom_details: Optional[dict] = None,
    ) -> dict:
        """
        Send an event via Events API v2.

        Args:
            event_action: trigger, acknowledge, or resolve
            routing_key: Integration key (defaults to config)
            dedup_key: Deduplication key for the alert
            summary: Alert summary (required for trigger)
            source: Source of the alert
            severity: critical, error, warning, or info
            custom_details: Additional details

        Returns:
            API response with status and dedup_key
        """
        routing_key = routing_key or self.config.integration_key
        if not routing_key:
            raise ValueError("No integration key configured for Events API")

        payload = {
            "routing_key": routing_key,
            "event_action": event_action,
        }

        if dedup_key:
            payload["dedup_key"] = dedup_key

        if event_action == "trigger":
            if not summary:
                raise ValueError("Summary required for trigger events")

            payload["payload"] = {
                "summary": summary,
                "source": source or "incident-copilot",
                "severity": severity,
            }

            if custom_details:
                payload["payload"]["custom_details"] = custom_details

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.EVENTS_URL,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def trigger_event(
        self,
        summary: str,
        source: str = "incident-copilot",
        severity: str = "critical",
        dedup_key: Optional[str] = None,
        custom_details: Optional[dict] = None,
    ) -> dict:
        """Trigger a new event/alert."""
        return await self.send_event(
            event_action="trigger",
            summary=summary,
            source=source,
            severity=severity,
            dedup_key=dedup_key,
            custom_details=custom_details,
        )

    async def acknowledge_event(self, dedup_key: str) -> dict:
        """Acknowledge an event/alert."""
        return await self.send_event(
            event_action="acknowledge",
            dedup_key=dedup_key,
        )

    async def resolve_event(self, dedup_key: str) -> dict:
        """Resolve an event/alert."""
        return await self.send_event(
            event_action="resolve",
            dedup_key=dedup_key,
        )
