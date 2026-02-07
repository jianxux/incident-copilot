"""Opsgenie on-call schedule provider."""

from datetime import datetime, timedelta
from typing import Optional

import httpx

from ..models import (
    OnCallOverride,
    OnCallSchedule,
    OnCallShift,
    OnCallUser,
    OverrideStatus,
    ProviderType,
    Rotation,
    RotationType,
    ScheduleSyncResult,
)


class OpsgenieProvider:
    """Opsgenie schedule sync provider."""

    BASE_URL = "https://api.opsgenie.com/v2"

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"GenieKey {self.api_key}",
            "Content-Type": "application/json",
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
        """Fetch all schedules from Opsgenie."""
        client = await self._get_client()
        schedules = []

        resp = await client.get("/schedules")
        resp.raise_for_status()
        data = resp.json()

        for sched in data.get("data", []):
            schedule = OnCallSchedule(
                id=f"og_{sched['id']}",
                name=sched["name"],
                description=sched.get("description"),
                team_id=sched.get("ownerTeam", {}).get("id", "default"),
                provider=ProviderType.OPSGENIE,
                provider_schedule_id=sched["id"],
                timezone=sched.get("timezone", "UTC"),
                rotations=[],
            )
            schedules.append(schedule)

        return schedules

    async def get_oncall_now(self, schedule_id: str) -> list[OnCallUser]:
        """Get currently on-call users for a schedule."""
        client = await self._get_client()

        resp = await client.get(
            f"/schedules/{schedule_id}/on-calls", params={"flat": "true"}
        )
        resp.raise_for_status()
        data = resp.json()

        users = []
        for participant in data.get("data", {}).get("onCallParticipants", []):
            users.append(
                OnCallUser(
                    id=f"og_{participant.get('id', participant.get('name', 'unknown'))}",
                    name=participant.get("name", "Unknown"),
                    email=participant.get("email", ""),
                    timezone="UTC",
                )
            )

        return users

    async def get_schedule_timeline(
        self, schedule_id: str, since: datetime, until: datetime
    ) -> list[OnCallShift]:
        """Get schedule timeline (shifts) for a date range."""
        client = await self._get_client()

        params = {
            "date": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval": (until - since).days,
            "intervalUnit": "days",
        }

        resp = await client.get(f"/schedules/{schedule_id}/timeline", params=params)
        resp.raise_for_status()
        data = resp.json()

        shifts = []
        timeline = data.get("data", {})
        tz = timeline.get("timezone", "UTC")

        for rotation in timeline.get("finalTimeline", {}).get("rotations", []):
            for period in rotation.get("periods", []):
                recipient = period.get("recipient", {})
                if not recipient:
                    continue

                user = OnCallUser(
                    id=f"og_{recipient.get('id', 'unknown')}",
                    name=recipient.get("name", "Unknown"),
                    email=recipient.get("email", ""),
                    timezone=tz,
                )

                shifts.append(
                    OnCallShift(
                        id=f"og_shift_{recipient.get('id')}_{period['startDate']}",
                        user=user,
                        schedule_id=f"og_{schedule_id}",
                        start_time=datetime.fromisoformat(
                            period["startDate"].replace("Z", "+00:00")
                        ),
                        end_time=datetime.fromisoformat(
                            period["endDate"].replace("Z", "+00:00")
                        ),
                        timezone=tz,
                    )
                )

        return shifts

    async def get_rotations(self, schedule_id: str) -> list[Rotation]:
        """Get rotation configurations for a schedule."""
        client = await self._get_client()

        resp = await client.get(f"/schedules/{schedule_id}")
        resp.raise_for_status()
        data = resp.json()

        rotations = []
        schedule_data = data.get("data", {})
        tz = schedule_data.get("timezone", "UTC")

        for idx, rot in enumerate(schedule_data.get("rotations", [])):
            rot_type = RotationType.WEEKLY
            if rot.get("type") == "daily":
                rot_type = RotationType.DAILY
            elif rot.get("length", 1) == 14:
                rot_type = RotationType.BIWEEKLY

            participants = []
            for p in rot.get("participants", []):
                participants.append(
                    OnCallUser(
                        id=f"og_{p.get('id', 'unknown')}",
                        name=p.get("name", "Unknown"),
                        email=p.get("email", ""),
                        timezone=tz,
                    )
                )

            start_date = (
                datetime.fromisoformat(rot["startDate"].replace("Z", "+00:00"))
                if rot.get("startDate")
                else datetime.utcnow()
            )

            rotations.append(
                Rotation(
                    id=f"og_rot_{schedule_id}_{idx}",
                    name=rot.get("name", f"Rotation {idx + 1}"),
                    type=rot_type,
                    participants=participants,
                    handoff_time=rot.get("startHour", "09:00"),
                    timezone=tz,
                    start_date=start_date,
                    layer=idx + 1,
                )
            )

        return rotations

    async def create_override(
        self, schedule_id: str, override: OnCallOverride
    ) -> OnCallOverride:
        """Create a schedule override in Opsgenie."""
        client = await self._get_client()

        og_user_id = override.override_user.id.replace("og_", "")

        payload = {
            "user": {"id": og_user_id, "type": "user"},
            "startDate": override.start_time.isoformat() + "Z",
            "endDate": override.end_time.isoformat() + "Z",
        }

        # Find the rotation to override (use first one by default)
        rotations = await self.get_rotations(schedule_id)
        if rotations:
            rotation_id = rotations[0].id.replace(f"og_rot_{schedule_id}_", "")
            resp = await client.post(
                f"/schedules/{schedule_id}/rotations/{rotation_id}/overrides",
                json=payload,
            )
            resp.raise_for_status()

        override.status = OverrideStatus.ACTIVE
        return override

    async def delete_override(
        self, schedule_id: str, rotation_id: str, override_alias: str
    ) -> bool:
        """Delete a schedule override."""
        client = await self._get_client()
        resp = await client.delete(
            f"/schedules/{schedule_id}/rotations/{rotation_id}/overrides/{override_alias}"
        )
        return resp.status_code == 200

    async def sync_schedule(self, schedule_id: str) -> ScheduleSyncResult:
        """Full sync of an Opsgenie schedule."""
        errors = []
        shifts_count = 0

        try:
            now = datetime.utcnow()
            shifts = await self.get_schedule_timeline(
                schedule_id,
                since=now - timedelta(days=7),
                until=now + timedelta(days=30),
            )
            shifts_count = len(shifts)
        except Exception as e:
            errors.append(f"Failed to sync timeline: {str(e)}")

        return ScheduleSyncResult(
            schedule_id=f"og_{schedule_id}",
            provider=ProviderType.OPSGENIE,
            success=len(errors) == 0,
            shifts_synced=shifts_count,
            errors=errors,
        )
