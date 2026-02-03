"""ServiceNow ITSM integration for incident management."""

import base64
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings

logger = structlog.get_logger()


class IncidentState(int, Enum):
    """ServiceNow incident states."""

    NEW = 1
    IN_PROGRESS = 2
    ON_HOLD = 3
    RESOLVED = 6
    CLOSED = 7
    CANCELED = 8


class IncidentImpact(int, Enum):
    """ServiceNow incident impact levels."""

    HIGH = 1
    MEDIUM = 2
    LOW = 3


class IncidentUrgency(int, Enum):
    """ServiceNow incident urgency levels."""

    HIGH = 1
    MEDIUM = 2
    LOW = 3


class ServiceNowAdapter:
    """Adapter for ServiceNow REST API.

    Supports CRUD operations on incidents, problems, changes, and CIs.
    Uses the Table API for most operations.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.instance_url = (
            settings.servicenow_instance.rstrip("/")
            if settings.servicenow_instance
            else ""
        )
        self.username = settings.servicenow_username
        self.password = settings.servicenow_password
        self.api_key = settings.servicenow_api_key
        self.assignment_group = settings.servicenow_assignment_group
        self.caller_id = settings.servicenow_caller_id

    @property
    def api_url(self) -> str:
        """Get the ServiceNow API base URL."""
        return f"{self.instance_url}/api/now"

    def _get_headers(self) -> dict:
        """Get auth headers for ServiceNow API."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.username and self.password:
            credentials = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    def _severity_to_impact(self, severity: str) -> IncidentImpact:
        """Map alert severity to ServiceNow impact."""
        mapping = {
            "critical": IncidentImpact.HIGH,
            "high": IncidentImpact.HIGH,
            "error": IncidentImpact.HIGH,
            "warning": IncidentImpact.MEDIUM,
            "medium": IncidentImpact.MEDIUM,
            "low": IncidentImpact.LOW,
            "info": IncidentImpact.LOW,
        }
        return mapping.get(severity.lower(), IncidentImpact.MEDIUM)

    def _severity_to_urgency(self, severity: str) -> IncidentUrgency:
        """Map alert severity to ServiceNow urgency."""
        mapping = {
            "critical": IncidentUrgency.HIGH,
            "high": IncidentUrgency.HIGH,
            "error": IncidentUrgency.HIGH,
            "warning": IncidentUrgency.MEDIUM,
            "medium": IncidentUrgency.MEDIUM,
            "low": IncidentUrgency.LOW,
            "info": IncidentUrgency.LOW,
        }
        return mapping.get(severity.lower(), IncidentUrgency.MEDIUM)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_incident(
        self,
        short_description: str,
        description: str,
        severity: str = "medium",
        service_name: str | None = None,
        alert_id: str | None = None,
        context_summary: str | None = None,
        additional_fields: dict | None = None,
    ) -> dict:
        """Create a new incident in ServiceNow.

        Args:
            short_description: Brief summary of the incident
            description: Detailed description
            severity: Alert severity (critical, high, medium, low)
            service_name: Affected service name
            alert_id: Original alert ID for correlation
            context_summary: AI-generated context summary
            additional_fields: Additional ServiceNow fields to set

        Returns:
            Created incident data including sys_id and number
        """
        if not self.instance_url:
            logger.warning("ServiceNow instance not configured")
            return {}

        impact = self._severity_to_impact(severity)
        urgency = self._severity_to_urgency(severity)

        # Build full description with context
        full_description = description
        if context_summary:
            full_description += f"\n\n--- AI Context Summary ---\n{context_summary}"
        if alert_id:
            full_description += f"\n\nOriginal Alert ID: {alert_id}"

        incident_data = {
            "short_description": short_description[:160],  # ServiceNow limit
            "description": full_description,
            "impact": impact.value,
            "urgency": urgency.value,
            "state": IncidentState.NEW.value,
            "category": "Software",
            "subcategory": "Application",
        }

        if self.assignment_group:
            incident_data["assignment_group"] = self.assignment_group
        if self.caller_id:
            incident_data["caller_id"] = self.caller_id
        if service_name:
            incident_data["cmdb_ci"] = service_name  # Configuration Item
            incident_data["u_service_name"] = service_name  # Custom field

        # Add any additional fields
        if additional_fields:
            incident_data.update(additional_fields)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/table/incident",
                    headers=self._get_headers(),
                    json=incident_data,
                )
                response.raise_for_status()
                result = response.json()
                incident = result.get("result", {})

                logger.info(
                    "Created ServiceNow incident",
                    number=incident.get("number"),
                    sys_id=incident.get("sys_id"),
                )

                return incident

        except httpx.HTTPStatusError as e:
            logger.error(
                "ServiceNow API error",
                status_code=e.response.status_code,
                detail=e.response.text,
            )
            return {}
        except Exception as e:
            logger.error("Error creating ServiceNow incident", error=str(e))
            return {}

    async def get_incident(self, sys_id: str) -> dict:
        """Get an incident by sys_id.

        Args:
            sys_id: ServiceNow sys_id of the incident

        Returns:
            Incident data or empty dict if not found
        """
        if not self.instance_url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/table/incident/{sys_id}",
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                result = response.json()
                return result.get("result", {})

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {}
            logger.error("ServiceNow API error", status_code=e.response.status_code)
            return {}
        except Exception as e:
            logger.error("Error getting ServiceNow incident", error=str(e))
            return {}

    async def update_incident(
        self,
        sys_id: str,
        updates: dict,
    ) -> dict:
        """Update an existing incident.

        Args:
            sys_id: ServiceNow sys_id of the incident
            updates: Fields to update

        Returns:
            Updated incident data
        """
        if not self.instance_url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"{self.api_url}/table/incident/{sys_id}",
                    headers=self._get_headers(),
                    json=updates,
                )
                response.raise_for_status()
                result = response.json()
                incident = result.get("result", {})

                logger.info(
                    "Updated ServiceNow incident",
                    number=incident.get("number"),
                    sys_id=sys_id,
                )

                return incident

        except Exception as e:
            logger.error("Error updating ServiceNow incident", error=str(e))
            return {}

    async def resolve_incident(
        self,
        sys_id: str,
        resolution_code: str = "Solved (Permanently)",
        resolution_notes: str = "",
        close_notes: str = "",
    ) -> dict:
        """Resolve an incident.

        Args:
            sys_id: ServiceNow sys_id of the incident
            resolution_code: Resolution code/category
            resolution_notes: Notes about the resolution
            close_notes: Additional close notes

        Returns:
            Updated incident data
        """
        updates = {
            "state": IncidentState.RESOLVED.value,
            "close_code": resolution_code,
            "close_notes": close_notes or resolution_notes,
        }

        if resolution_notes:
            updates["resolution_notes"] = resolution_notes

        return await self.update_incident(sys_id, updates)

    async def add_work_note(
        self,
        sys_id: str,
        note: str,
    ) -> dict:
        """Add a work note to an incident.

        Args:
            sys_id: ServiceNow sys_id of the incident
            note: Work note text

        Returns:
            Updated incident data
        """
        return await self.update_incident(
            sys_id,
            {"work_notes": note},
        )

    async def add_comment(
        self,
        sys_id: str,
        comment: str,
    ) -> dict:
        """Add a customer-visible comment to an incident.

        Args:
            sys_id: ServiceNow sys_id of the incident
            comment: Comment text (visible to customer)

        Returns:
            Updated incident data
        """
        return await self.update_incident(
            sys_id,
            {"comments": comment},
        )

    async def search_incidents(
        self,
        query: str | None = None,
        state: IncidentState | None = None,
        service_name: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search for incidents.

        Args:
            query: Full-text search query
            state: Filter by incident state
            service_name: Filter by service/CI name
            limit: Maximum results to return

        Returns:
            List of matching incidents
        """
        if not self.instance_url:
            return []

        # Build encoded query
        query_parts = []

        if query:
            query_parts.append(f"short_descriptionLIKE{query}^ORdescriptionLIKE{query}")
        if state:
            query_parts.append(f"state={state.value}")
        if service_name:
            query_parts.append(f"cmdb_ciLIKE{service_name}")

        encoded_query = "^".join(query_parts) if query_parts else ""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "sysparm_limit": limit,
                    "sysparm_display_value": "true",
                }
                if encoded_query:
                    params["sysparm_query"] = encoded_query

                response = await client.get(
                    f"{self.api_url}/table/incident",
                    headers=self._get_headers(),
                    params=params,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("result", [])

        except Exception as e:
            logger.error("Error searching ServiceNow incidents", error=str(e))
            return []

    async def get_similar_incidents(
        self,
        short_description: str,
        service_name: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Find similar past incidents.

        Args:
            short_description: Description to match against
            service_name: Optional service filter
            limit: Maximum results

        Returns:
            List of similar incidents
        """
        # Extract key terms for search
        terms = short_description.split()[:5]  # First 5 words
        query = " ".join(terms)

        return await self.search_incidents(
            query=query,
            service_name=service_name,
            limit=limit,
        )

    async def get_cmdb_ci(self, name: str) -> dict | None:
        """Look up a Configuration Item by name.

        Args:
            name: CI name to look up

        Returns:
            CI data or None if not found
        """
        if not self.instance_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/table/cmdb_ci",
                    headers=self._get_headers(),
                    params={
                        "sysparm_query": f"nameLIKE{name}",
                        "sysparm_limit": 1,
                    },
                )
                response.raise_for_status()
                result = response.json()
                items = result.get("result", [])
                return items[0] if items else None

        except Exception as e:
            logger.error("Error looking up CMDB CI", error=str(e))
            return None

    async def create_change_request(
        self,
        short_description: str,
        description: str,
        service_name: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        change_type: str = "Normal",
        risk: str = "Moderate",
    ) -> dict:
        """Create a change request.

        Args:
            short_description: Brief summary
            description: Detailed description
            service_name: Affected CI/service
            start_date: Planned start date
            end_date: Planned end date
            change_type: Normal, Standard, or Emergency
            risk: Low, Moderate, or High

        Returns:
            Created change request data
        """
        if not self.instance_url:
            return {}

        change_data = {
            "short_description": short_description[:160],
            "description": description,
            "type": change_type,
            "risk": risk,
            "category": "Software",
        }

        if service_name:
            change_data["cmdb_ci"] = service_name
        if start_date:
            change_data["start_date"] = start_date.strftime("%Y-%m-%d %H:%M:%S")
        if end_date:
            change_data["end_date"] = end_date.strftime("%Y-%m-%d %H:%M:%S")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/table/change_request",
                    headers=self._get_headers(),
                    json=change_data,
                )
                response.raise_for_status()
                result = response.json()
                change = result.get("result", {})

                logger.info(
                    "Created ServiceNow change request",
                    number=change.get("number"),
                    sys_id=change.get("sys_id"),
                )

                return change

        except Exception as e:
            logger.error("Error creating change request", error=str(e))
            return {}

    async def get_recent_changes(
        self,
        service_name: str | None = None,
        hours_back: int = 24,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent change requests.

        Args:
            service_name: Filter by service/CI
            hours_back: How far back to look
            limit: Maximum results

        Returns:
            List of recent changes
        """
        if not self.instance_url:
            return []

        query_parts = [
            f"sys_created_on>=javascript:gs.hoursAgoStart({hours_back})",
        ]
        if service_name:
            query_parts.append(f"cmdb_ciLIKE{service_name}")

        encoded_query = "^".join(query_parts)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/table/change_request",
                    headers=self._get_headers(),
                    params={
                        "sysparm_query": f"{encoded_query}^ORDERBYDESCsys_created_on",
                        "sysparm_limit": limit,
                        "sysparm_display_value": "true",
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("result", [])

        except Exception as e:
            logger.error("Error getting recent changes", error=str(e))
            return []

    async def get_health(self) -> dict:
        """Check ServiceNow connection health."""
        if not self.instance_url:
            return {"status": "unconfigured"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.api_url}/table/sys_properties",
                    headers=self._get_headers(),
                    params={"sysparm_limit": 1},
                )
                response.raise_for_status()

                return {
                    "status": "healthy",
                    "instance": self.instance_url,
                }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def link_incident_to_alert(
        self,
        incident_sys_id: str,
        alert_id: str,
        alert_source: str,
        alert_url: str | None = None,
    ) -> bool:
        """Link an incident to an external alert for correlation.

        Args:
            incident_sys_id: ServiceNow incident sys_id
            alert_id: External alert ID
            alert_source: Alert source (PagerDuty, Opsgenie, etc.)
            alert_url: Optional URL to the alert

        Returns:
            True if link was created successfully
        """
        work_note = f"Linked to {alert_source} Alert: {alert_id}"
        if alert_url:
            work_note += f"\nURL: {alert_url}"

        result = await self.add_work_note(incident_sys_id, work_note)
        return bool(result)
