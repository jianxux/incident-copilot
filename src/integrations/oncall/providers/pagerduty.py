"""PagerDuty on-call schedule provider."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx
from zoneinfo import ZoneInfo

from ..models import (
    OnCallSchedule,
    OnCallShift,
    OnCallUser,
    OnCallOverride,
    Rotation,
    RotationType,
    ProviderType,
    ScheduleSyncResult,
    OverrideStatus,
)


class PagerDutyProvider:
    """PagerDuty schedule sync provider."""

    BASE_URL = "https://api.pagerduty.com"

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Token token={self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL, headers=self.headers, timeout=self.timeout
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_schedules(self) -> list[OnCallSchedule]:
        """Fetch all schedules from PagerDuty."""
        client = await self._get_client()
        schedules = []

        resp = await client.get("/schedules", params={"limit": 100})
        resp.raise_for_status()
        data = resp.json()

        for sched in data.get("schedules", []):
            schedule = OnCallSchedule(
                id=f"pd_{sched['id']}",
                name=sched["name"],
                description=sched.get("description"),
                team_id=sched.get("teams", [{}])[0].get("id", "default"),
                provider=ProviderType.PAGERDUTY,
                provider_schedule_id=sched["id"],
                timezone=sched.get("time_zone", "UTC"),
                rotations=[],
            )
            schedules.append(schedule)

        return schedules

    async def get_oncall_now(self, schedule_id: str) -> list[OnCallUser]:
        """Get currently on-call users for a schedule."""
        client = await self._get_client()
        now = datetime.utcnow()

        params = {
            "schedule_ids[]": schedule_id,
            "since": now.isoformat() + "Z",
            "until": (now + timedelta(minutes=1)).isoformat() + "Z",
        }

        resp = await client.get("/oncalls", params=params)
        resp.raise_for_status()
        data = resp.json()

        users = []
        for oncall in data.get("oncalls", []):
            user_data = oncall.get("user", {})
            if user_data:
                users.append(
                    OnCallUser(
                        id=f"pd_{user_data['id']}",
                        name=user_data.get("name", "Unknown"),
                        email=user_data.get("email", ""),
                        phone=(
                            user_data.get("contact_methods", [{}])[0].get("address")
                            if user_data.get("contact_methods")
                            else None
                        ),
                        timezone=user_data.get("time_zone", "UTC"),
                        avatar_url=user_data.get("avatar_url"),
                    )
                )

        return users

    async def get_schedule_shifts(
        self, schedule_id: str, since: datetime, until: datetime
    ) -> list[OnCallShift]:
        """Get shifts for a schedule within a time range."""
        client = await self._get_client()

        params = {
            "since": since.isoformat() + "Z",
            "until": until.isoformat() + "Z",
            "overflow": "true",
        }

        resp = await client.get(f"/schedules/{schedule_id}", params=params)
        resp.raise_for_status()
        data = resp.json()

        shifts = []
        schedule_data = data.get("schedule", {})
        tz = schedule_data.get("time_zone", "UTC")

        for entry in schedule_data.get("final_schedule", {}).get(
            "rendered_schedule_entries", []
        ):
            user_data = entry.get("user", {})
            if not user_data:
                continue

            user = OnCallUser(
                id=f"pd_{user_data['id']}",
                name=user_data.get("name", "Unknown"),
                email=user_data.get("email", ""),
                timezone=tz,
            )

            shifts.append(
                OnCallShift(
                    id=f"pd_shift_{entry.get('id', user_data['id'])}_{entry['start']}",
                    user=user,
                    schedule_id=f"pd_{schedule_id}",
                    start_time=datetime.fromisoformat(
                        entry["start"].replace("Z", "+00:00")
                    ),
                    end_time=datetime.fromisoformat(
                        entry["end"].replace("Z", "+00:00")
                    ),
                    timezone=tz,
                )
            )

        return shifts

    async def create_override(
        self, schedule_id: str, override: OnCallOverride
    ) -> OnCallOverride:
        """Create a schedule override in PagerDuty."""
        client = await self._get_client()

        # Extract PagerDuty user ID from our internal ID
        pd_user_id = override.override_user.id.replace("pd_", "")

        payload = {
            "override": {
                "start": override.start_time.isoformat() + "Z",
                "end": override.end_time.isoformat() + "Z",
                "user": {"id": pd_user_id, "type": "user_reference"},
            }
        }

        resp = await client.post(f"/schedules/{schedule_id}/overrides", json=payload)
        resp.raise_for_status()
        data = resp.json()

        override.status = OverrideStatus.ACTIVE
        return override

    async def delete_override(self, schedule_id: str, override_id: str) -> bool:
        """Delete a schedule override."""
        client = await self._get_client()
        resp = await client.delete(f"/schedules/{schedule_id}/overrides/{override_id}")
        return resp.status_code == 204

    async def sync_schedule(self, schedule_id: str) -> ScheduleSyncResult:
        """Full sync of a PagerDuty schedule."""
        errors = []
        shifts_count = 0

        try:
            now = datetime.utcnow()
            shifts = await self.get_schedule_shifts(
                schedule_id,
                since=now - timedelta(days=7),
                until=now + timedelta(days=30),
            )
            shifts_count = len(shifts)
        except Exception as e:
            errors.append(f"Failed to sync shifts: {str(e)}")

        return ScheduleSyncResult(
            schedule_id=f"pd_{schedule_id}",
            provider=ProviderType.PAGERDUTY,
            success=len(errors) == 0,
            shifts_synced=shifts_count,
            errors=errors,
        )
