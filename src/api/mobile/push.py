"""Push notification integration for FCM and APNS."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import httpx
from .models import Platform, Severity, DeviceRegistration

logger = logging.getLogger(__name__)


@dataclass
class PushConfig:
    fcm_server_key: str | None = None
    fcm_project_id: str | None = None
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_bundle_id: str | None = None
    apns_use_sandbox: bool = False
    max_retries: int = 3


class DeviceTokenStore:
    """In-memory device token store. Replace with Redis/DB in production."""

    def __init__(self):
        self._tokens: dict[str, DeviceRegistration] = {}
        self._user_devices: dict[str, set[str]] = {}

    async def register(self, user_id: str, device: DeviceRegistration) -> bool:
        self._tokens[device.device_id] = device
        self._user_devices.setdefault(user_id, set()).add(device.device_id)
        return True

    async def unregister(self, device_id: str) -> bool:
        if device_id in self._tokens:
            self._tokens.pop(device_id)
            for devices in self._user_devices.values():
                devices.discard(device_id)
            return True
        return False

    async def get_user_devices(self, user_id: str) -> list[DeviceRegistration]:
        device_ids = self._user_devices.get(user_id, set())
        return [self._tokens[did] for did in device_ids if did in self._tokens]


@dataclass
class PushPayload:
    title: str
    body: str
    incident_id: str | None = None
    severity: Severity | None = None
    action: str | None = None
    priority: str = "high"
    collapse_key: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_fcm(self) -> dict:
        return {
            "notification": {"title": self.title, "body": self.body},
            "data": {"incident_id": self.incident_id or "", **self.data},
            "android": {"priority": self.priority},
        }

    def to_apns(self) -> dict:
        return {
            "aps": {"alert": {"title": self.title, "body": self.body}, "sound": "default"},
            "incident_id": self.incident_id,
        }


class PushStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INVALID_TOKEN = "invalid_token"


@dataclass
class PushResult:
    device_id: str
    status: PushStatus
    error: str | None = None


class PushService:
    """Unified push notification service."""

    def __init__(self, config: PushConfig):
        self.config = config
        self.token_store = DeviceTokenStore()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def register_device(self, user_id: str, device: DeviceRegistration) -> bool:
        return await self.token_store.register(user_id, device)

    async def unregister_device(self, device_id: str) -> bool:
        return await self.token_store.unregister(device_id)

    async def _send_fcm(self, token: str, payload: PushPayload) -> PushResult:
        client = await self._get_client()
        url = f"https://fcm.googleapis.com/v1/projects/{self.config.fcm_project_id}/messages:send"
        try:
            resp = await client.post(
                url,
                json={"message": {"token": token, **payload.to_fcm()}},
                headers={"Authorization": f"Bearer {self.config.fcm_server_key}"},
            )
            if resp.status_code == 200:
                return PushResult(token[:20], PushStatus.SUCCESS)
            if resp.status_code == 404:
                return PushResult(token[:20], PushStatus.INVALID_TOKEN)
            return PushResult(token[:20], PushStatus.FAILED, f"HTTP {resp.status_code}")
        except Exception as e:
            return PushResult(token[:20], PushStatus.FAILED, str(e))

    async def _send_apns(self, token: str, payload: PushPayload) -> PushResult:
        client = await self._get_client()
        base = (
            "https://api.sandbox.push.apple.com"
            if self.config.apns_use_sandbox
            else "https://api.push.apple.com"
        )
        try:
            resp = await client.post(
                f"{base}/3/device/{token}",
                json=payload.to_apns(),
                headers={"apns-topic": self.config.apns_bundle_id, "apns-push-type": "alert"},
            )
            if resp.status_code == 200:
                return PushResult(token[:20], PushStatus.SUCCESS)
            if resp.status_code in (400, 410):
                return PushResult(token[:20], PushStatus.INVALID_TOKEN)
            return PushResult(token[:20], PushStatus.FAILED, f"HTTP {resp.status_code}")
        except Exception as e:
            return PushResult(token[:20], PushStatus.FAILED, str(e))

    async def send_to_user(self, user_id: str, payload: PushPayload) -> list[PushResult]:
        devices = await self.token_store.get_user_devices(user_id)
        results = []
        for device in devices:
            if device.platform == Platform.ANDROID:
                results.append(await self._send_fcm(device.token, payload))
            else:
                results.append(await self._send_apns(device.token, payload))
        return results

    async def broadcast_incident(
        self,
        incident_id: str,
        title: str,
        body: str,
        severity: Severity,
        user_ids: list[str] | None = None,
    ) -> dict[str, list[PushResult]]:
        payload = PushPayload(title=title, body=body, incident_id=incident_id, severity=severity)
        targets = user_ids or list(self.token_store._user_devices.keys())
        return {uid: await self.send_to_user(uid, payload) for uid in targets}


_push_service: PushService | None = None


def get_push_service(config: PushConfig | None = None) -> PushService:
    global _push_service
    if not _push_service:
        _push_service = PushService(config or PushConfig())
    return _push_service
