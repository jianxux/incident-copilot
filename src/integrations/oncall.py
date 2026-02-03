"""On-Call Roster integration adapter.

Provides unified access to on-call schedules from:
- PagerDuty Schedules API
- Opsgenie Schedules API
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import structlog

from ..config import Settings
from ..models import OnCallPerson, OnCallRoster

logger = structlog.get_logger()

# API Base URLs
PAGERDUTY_API_URL = "https://api.pagerduty.com"
OPSGENIE_API_URLS = {
    "us": "https://api.opsgenie.com/v2",
    "eu": "https://api.eu.opsgenie.com/v2",
}


class OnCallProvider(str, Enum):
    """On-call provider types."""

    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    NONE = "none"


class OnCallAdapter:
    """
    Unified adapter for fetching on-call schedules.

    Supports both PagerDuty and Opsgenie, with automatic provider detection
    based on configuration.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = self._detect_provider()
        self._setup_api_config()
        logger.info("oncall_adapter_initialized", provider=self.provider.value)

    def _detect_provider(self) -> OnCallProvider:
        """Detect on-call provider based on configuration."""
        oncall_provider = getattr(self.settings, "oncall_provider", "auto").lower()

        if oncall_provider == "pagerduty":
            return OnCallProvider.PAGERDUTY
        elif oncall_provider == "opsgenie":
            return OnCallProvider.OPSGENIE
        elif oncall_provider == "auto":
            # Auto-detect based on available credentials
            if self.settings.pagerduty_api_key:
                return OnCallProvider.PAGERDUTY
            elif self.settings.opsgenie_api_key:
                return OnCallProvider.OPSGENIE
        return OnCallProvider.NONE

    def _setup_api_config(self) -> None:
        """Set up API configuration based on provider."""
        if self.provider == OnCallProvider.PAGERDUTY:
            self.api_base = PAGERDUTY_API_URL
            self.api_key = self.settings.pagerduty_api_key
            self.headers = {
                "Authorization": f"Token token={self.api_key}",
                "Content-Type": "application/json",
            }
        elif self.provider == OnCallProvider.OPSGENIE:
            region = getattr(self.settings, "opsgenie_region", "us")
            self.api_base = OPSGENIE_API_URLS.get(region, OPSGENIE_API_URLS["us"])
            self.api_key = self.settings.opsgenie_api_key
            self.headers = {
                "Authorization": f"GenieKey {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.api_base = ""
            self.api_key = ""
            self.headers = {}

    async def get_current_oncall(
        self,
        schedule_id: str | None = None,
        service_name: str | None = None,
    ) -> OnCallRoster | None:
        """
        Get the current on-call roster.

        Args:
            schedule_id: Explicit schedule ID to query
            service_name: Service name to look up schedule mapping

        Returns:
            OnCallRoster with current on-call persons, or None if unavailable
        """
        if self.provider == OnCallProvider.NONE:
            logger.debug("oncall_provider_not_configured")
            return None

        # Resolve schedule ID from mapping if not provided
        effective_schedule_id = self._resolve_schedule_id(schedule_id, service_name)
        if not effective_schedule_id:
            logger.debug(
                "no_schedule_id_found",
                schedule_id=schedule_id,
                service_name=service_name,
            )
            return None

        try:
            if self.provider == OnCallProvider.PAGERDUTY:
                return await self._get_pagerduty_oncall(effective_schedule_id)
            elif self.provider == OnCallProvider.OPSGENIE:
                return await self._get_opsgenie_oncall(effective_schedule_id)
        except Exception as e:
            logger.error(
                "oncall_fetch_failed",
                provider=self.provider.value,
                schedule_id=effective_schedule_id,
                error=str(e),
            )
            return None

        return None

    def _resolve_schedule_id(
        self,
        schedule_id: str | None,
        service_name: str | None,
    ) -> str | None:
        """Resolve schedule ID from explicit value or service mapping."""
        if schedule_id:
            return schedule_id

        # Check service-to-schedule mapping first (more specific)
        if service_name:
            schedule_map = getattr(self.settings, "oncall_schedule_map", {})
            if service_name in schedule_map:
                return schedule_map[service_name]

        # Fall back to default schedule ID from config
        default_schedule = getattr(self.settings, "oncall_schedule_id", "")
        if default_schedule:
            return default_schedule

        return None

    async def _get_pagerduty_oncall(self, schedule_id: str) -> OnCallRoster | None:
        """
        Fetch on-call users from PagerDuty Schedules API.

        API: GET /schedules/{id}/users
        Docs: https://developer.pagerduty.com/api-reference/846ecf84402bb-list-users-on-call
        """
        url = f"{self.api_base}/schedules/{schedule_id}/users"
        now = datetime.now(UTC)

        params = {
            "since": now.isoformat(),
            "until": now.isoformat(),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()

        users = data.get("users", [])
        schedule_data = await self._get_pagerduty_schedule_info(schedule_id)

        oncall_persons = []
        for user in users:
            person = OnCallPerson(
                id=user.get("id", ""),
                name=user.get("name", "Unknown"),
                email=user.get("email"),
                phone=self._extract_phone(user),
                avatar_url=user.get("avatar_url"),
                slack_user_id=self._extract_slack_id(user),
                provider=OnCallProvider.PAGERDUTY.value,
                raw_data=user,
            )
            oncall_persons.append(person)

        logger.info(
            "pagerduty_oncall_fetched",
            schedule_id=schedule_id,
            oncall_count=len(oncall_persons),
        )

        return OnCallRoster(
            schedule_id=schedule_id,
            schedule_name=(
                schedule_data.get("name", schedule_id) if schedule_data else schedule_id
            ),
            provider=OnCallProvider.PAGERDUTY.value,
            oncall_persons=oncall_persons,
            fetched_at=now,
            schedule_url=f"https://app.pagerduty.com/schedules/{schedule_id}",
        )

    async def _get_pagerduty_schedule_info(
        self, schedule_id: str
    ) -> dict[str, Any] | None:
        """Fetch schedule metadata from PagerDuty."""
        url = f"{self.api_base}/schedules/{schedule_id}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("schedule", {})
        except Exception as e:
            logger.debug("pagerduty_schedule_info_failed", error=str(e))
            return None

    async def _get_opsgenie_oncall(self, schedule_id: str) -> OnCallRoster | None:
        """
        Fetch on-call users from Opsgenie Schedules API.

        API: GET /v2/schedules/{identifier}/on-calls
        Docs: https://docs.opsgenie.com/docs/schedule-on-call-api
        """
        url = f"{self.api_base}/schedules/{schedule_id}/on-calls"

        params = {
            "scheduleIdentifierType": "id",
            "flat": "true",  # Get flat list of participants
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()

        oncall_data = data.get("data", {})
        participants = oncall_data.get("onCallParticipants", [])

        oncall_persons = []
        for participant in participants:
            # Opsgenie returns user info directly
            person = OnCallPerson(
                id=participant.get("id", ""),
                name=participant.get("name", "Unknown"),
                email=self._extract_opsgenie_email(participant),
                phone=None,  # Need separate API call for contact info
                avatar_url=None,
                slack_user_id=None,
                provider=OnCallProvider.OPSGENIE.value,
                raw_data=participant,
            )
            oncall_persons.append(person)

        # Get schedule metadata
        schedule_info = await self._get_opsgenie_schedule_info(schedule_id)
        schedule_name = (
            schedule_info.get("name", schedule_id) if schedule_info else schedule_id
        )

        logger.info(
            "opsgenie_oncall_fetched",
            schedule_id=schedule_id,
            oncall_count=len(oncall_persons),
        )

        return OnCallRoster(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            provider=OnCallProvider.OPSGENIE.value,
            oncall_persons=oncall_persons,
            fetched_at=datetime.now(UTC),
            schedule_url=f"https://app.opsgenie.com/schedule#/{schedule_id}",
        )

    async def _get_opsgenie_schedule_info(
        self, schedule_id: str
    ) -> dict[str, Any] | None:
        """Fetch schedule metadata from Opsgenie."""
        url = f"{self.api_base}/schedules/{schedule_id}"

        params = {"identifierType": "id"}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                return data.get("data", {})
        except Exception as e:
            logger.debug("opsgenie_schedule_info_failed", error=str(e))
            return None

    def _extract_phone(self, user: dict) -> str | None:
        """Extract phone number from PagerDuty user contact methods."""
        contact_methods = user.get("contact_methods", [])
        for method in contact_methods:
            if method.get("type") == "phone_contact_method":
                return method.get("address")
        return None

    def _extract_slack_id(self, user: dict) -> str | None:
        """Extract Slack user ID from PagerDuty user (if available via integration)."""
        # PagerDuty stores Slack info in user's contact methods or via webhooks
        contact_methods = user.get("contact_methods", [])
        for method in contact_methods:
            # Some PagerDuty setups store Slack ID in push notification contact
            label = method.get("label", "").lower()
            if "slack" in label:
                return method.get("address")
        return None

    def _extract_opsgenie_email(self, participant: dict) -> str | None:
        """Extract email from Opsgenie participant."""
        # Opsgenie participant type can be 'user' or 'team'
        participant_type = participant.get("type", "")
        if participant_type == "user":
            # For users, name is often the email
            name = participant.get("name", "")
            if "@" in name:
                return name
        return None

    async def get_oncall_for_service(self, service_name: str) -> OnCallRoster | None:
        """
        Convenience method to get on-call for a specific service.

        Uses service-to-schedule mapping from configuration.
        """
        return await self.get_current_oncall(service_name=service_name)

    async def list_schedules(self) -> list[dict[str, Any]]:
        """List available schedules (for configuration discovery)."""
        if self.provider == OnCallProvider.PAGERDUTY:
            return await self._list_pagerduty_schedules()
        elif self.provider == OnCallProvider.OPSGENIE:
            return await self._list_opsgenie_schedules()
        return []

    async def _list_pagerduty_schedules(self) -> list[dict[str, Any]]:
        """List all PagerDuty schedules."""
        url = f"{self.api_base}/schedules"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("schedules", [])
        except Exception as e:
            logger.error("pagerduty_list_schedules_failed", error=str(e))
            return []

    async def _list_opsgenie_schedules(self) -> list[dict[str, Any]]:
        """List all Opsgenie schedules."""
        url = f"{self.api_base}/schedules"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
        except Exception as e:
            logger.error("opsgenie_list_schedules_failed", error=str(e))
            return []
