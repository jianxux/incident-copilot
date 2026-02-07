"""
Push notification integration for FCM (Android) and APNS (iOS).
Async patterns with retry logic and device token management.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from .models import Platform, Severity, DeviceRegistration

logger = logging.getLogger(__name__)


# === Configuration ===

@dataclass
class PushConfig:
    """Push notification service configuration."""
    fcm_server_key: str | None = None
    fcm_project_id: str | None = None
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_bundle_id: str | None = None
    apns_key_path: str | None = None
    apns_use_sandbox: bool = False
    max_retries: int = 3
    retry_delay: float = 1.0
    batch_size: int = 500


# === Device Token Store ===

class DeviceTokenStore:
    """
    In-memory device token store. 
    Replace with Redis/DB in production.
    """
    
    def __init__(self):
        self._tokens: dict[str, DeviceRegistration] = {}
        self._user_devices: dict[str, set[str]] = {}  # user_id -> device_ids
        self._invalid_tokens: set[str] = set()
    
    async def register(self, user_id: str, device: DeviceRegistration) -> bool:
        """Register a device token for a user."""
        self._tokens[device.device_id] = device
        if user_id not in self._user_devices:
            self._user_devices[user_id] = set()
        self._user_devices[user_id].add(device.device_id)
        self._invalid_tokens.discard(device.token)
        logger.info(f"Registered device {device.device_id} for user {user_id}")
        return True
    
    async def unregister(self, device_id: str) -> bool:
        """Unregister a device."""
        if device_id in self._tokens:
            device = self._tokens.pop(device_id)
            for user_devices in self._user_devices.values():
                user_devices.discard(device_id)
            logger.info(f"Unregistered device {device_id}")
            return True
        return False
    
    async def get_user_devices(self, user_id: str) -> list[DeviceRegistration]:
        """Get all devices for a user."""
        device_ids = self._user_devices.get(user_id, set())
        return [self._tokens[did] for did in device_ids if did in self._tokens]
    
    async def mark_invalid(self, token: str) -> None:
        """Mark a token as invalid (unregistered)."""
        self._invalid_tokens.add(token)
        # Remove devices with this token
        to_remove = [did for did, dev in self._tokens.items() if dev.token == token]
        for did in to_remove:
            await self.unregister(did)
    
    async def is_valid(self, token: str) -> bool:
        """Check if token is known to be invalid."""
        return token not in self._invalid_tokens


# === Push Payload ===

@dataclass
class PushPayload:
    """Platform-agnostic push notification payload."""
    title: str
    body: str
    incident_id: str | None = None
    severity: Severity | None = None
    action: str | None = None
    badge: int | None = None
    sound: str = "default"
    data: dict[str, Any] = field(default_factory=dict)
    priority: str = "high"  # high, normal
    ttl: int = 3600  # seconds
    collapse_key: str | None = None
    
    def to_fcm(self) -> dict[str, Any]:
        """Convert to FCM payload format."""
        payload = {
            "notification": {
                "title": self.title,
                "body": self.body,
            },
            "data": {
                "incident_id": self.incident_id or "",
                "severity": self.severity.value if self.severity else "",
                "action": self.action or "",
                "click_action": "OPEN_INCIDENT",
                **{k: str(v) for k, v in self.data.items()},
            },
            "android": {
                "priority": self.priority,
                "ttl": f"{self.ttl}s",
                "notification": {
                    "sound": self.sound,
                    "channel_id": f"incidents_{self.severity.value}" if self.severity else "incidents",
                },
            },
        }
        if self.collapse_key:
            payload["android"]["collapse_key"] = self.collapse_key
        return payload
    
    def to_apns(self) -> dict[str, Any]:
        """Convert to APNS payload format."""
        aps = {
            "alert": {
                "title": self.title,
                "body": self.body,
            },
            "sound": self.sound,
            "mutable-content": 1,
            "category": "INCIDENT_CATEGORY",
        }
        if self.badge is not None:
            aps["badge"] = self.badge
        
        payload = {
            "aps": aps,
            "incident_id": self.incident_id,
            "severity": self.severity.value if self.severity else None,
            "action": self.action,
            **self.data,
        }
        return payload


# === Push Result ===

class PushStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INVALID_TOKEN = "invalid_token"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


@dataclass
class PushResult:
    """Result of a push notification attempt."""
    device_id: str
    status: PushStatus
    message_id: str | None = None
    error: str | None = None


# === Abstract Provider ===

class PushProvider(ABC):
    """Abstract push notification provider."""
    
    @abstractmethod
    async def send(self, token: str, payload: PushPayload) -> PushResult:
        """Send a notification to a single device."""
        pass
    
    @abstractmethod
    async def send_batch(self, tokens: list[str], payload: PushPayload) -> list[PushResult]:
        """Send a notification to multiple devices."""
        pass


# === FCM Provider ===

class FCMProvider(PushProvider):
    """Firebase Cloud Messaging provider."""
    
    FCM_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    
    def __init__(self, config: PushConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires: float = 0
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token for FCM v1 API."""
        # In production, use google-auth library
        # This is a simplified placeholder
        if self._access_token and time.time() < self._token_expires:
            return self._access_token
        
        # Placeholder - implement proper OAuth2 flow
        self._access_token = self.config.fcm_server_key or ""
        self._token_expires = time.time() + 3600
        return self._access_token
    
    async def send(self, token: str, payload: PushPayload) -> PushResult:
        """Send notification via FCM."""
        client = await self._get_client()
        access_token = await self._get_access_token()
        
        url = self.FCM_URL.format(project_id=self.config.fcm_project_id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        body = {"message": {"token": token, **payload.to_fcm()}}
        
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post(url, json=body, headers=headers)
                
                if resp.status_code == 200:
                    data = resp.json()
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.SUCCESS,
                        message_id=data.get("name"),
                    )
                elif resp.status_code == 404:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.INVALID_TOKEN,
                        error="Token not registered",
                    )
                elif resp.status_code == 429:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                else:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.FAILED,
                        error=f"HTTP {resp.status_code}",
                    )
                    
            except httpx.TimeoutException:
                if attempt == self.config.max_retries - 1:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.TIMEOUT,
                        error="Request timeout",
                    )
                await asyncio.sleep(self.config.retry_delay)
            except Exception as e:
                logger.exception(f"FCM send error: {e}")
                return PushResult(
                    device_id=token[:20],
                    status=PushStatus.FAILED,
                    error=str(e),
                )
        
        return PushResult(
            device_id=token[:20],
            status=PushStatus.FAILED,
            error="Max retries exceeded",
        )
    
    async def send_batch(self, tokens: list[str], payload: PushPayload) -> list[PushResult]:
        """Send to multiple FCM tokens concurrently."""
        tasks = [self.send(token, payload) for token in tokens]
        return await asyncio.gather(*tasks)


# === APNS Provider ===

class APNSProvider(PushProvider):
    """Apple Push Notification Service provider."""
    
    APNS_PROD = "https://api.push.apple.com"
    APNS_SANDBOX = "https://api.sandbox.push.apple.com"
    
    def __init__(self, config: PushConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
    
    @property
    def base_url(self) -> str:
        return self.APNS_SANDBOX if self.config.apns_use_sandbox else self.APNS_PROD
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # In production, configure HTTP/2 and client certificates
            self._client = httpx.AsyncClient(
                http2=True,
                timeout=30.0,
            )
        return self._client
    
    def _create_jwt(self) -> str:
        """Create JWT for APNS authentication."""
        # Simplified - use PyJWT in production
        header = {"alg": "ES256", "kid": self.config.apns_key_id}
        claims = {
            "iss": self.config.apns_team_id,
            "iat": int(time.time()),
        }
        # Placeholder - implement proper ES256 signing
        return f"placeholder.{self.config.apns_key_id}.token"
    
    async def send(self, token: str, payload: PushPayload) -> PushResult:
        """Send notification via APNS."""
        client = await self._get_client()
        jwt = self._create_jwt()
        
        url = f"{self.base_url}/3/device/{token}"
        headers = {
            "authorization": f"bearer {jwt}",
            "apns-topic": self.config.apns_bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10" if payload.priority == "high" else "5",
            "apns-expiration": str(int(time.time()) + payload.ttl),
        }
        if payload.collapse_key:
            headers["apns-collapse-id"] = payload.collapse_key
        
        body = payload.to_apns()
        
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post(url, json=body, headers=headers)
                
                if resp.status_code == 200:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.SUCCESS,
                        message_id=resp.headers.get("apns-id"),
                    )
                elif resp.status_code in (400, 410):
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.INVALID_TOKEN,
                        error="Bad device token",
                    )
                elif resp.status_code == 429:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                else:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.FAILED,
                        error=f"HTTP {resp.status_code}",
                    )
                    
            except httpx.TimeoutException:
                if attempt == self.config.max_retries - 1:
                    return PushResult(
                        device_id=token[:20],
                        status=PushStatus.TIMEOUT,
                        error="Request timeout",
                    )
                await asyncio.sleep(self.config.retry_delay)
            except Exception as e:
                logger.exception(f"APNS send error: {e}")
                return PushResult(
                    device_id=token[:20],
                    status=PushStatus.FAILED,
                    error=str(e),
                )
        
        return PushResult(
            device_id=token[:20],
            status=PushStatus.FAILED,
            error="Max retries exceeded",
        )
    
    async def send_batch(self, tokens: list[str], payload: PushPayload) -> list[PushResult]:
        """Send to multiple APNS tokens concurrently."""
        tasks = [self.send(token, payload) for token in tokens]
        return await asyncio.gather(*tasks)


# === Push Service ===

class PushService:
    """
    Unified push notification service.
    Routes to appropriate provider based on platform.
    """
    
    def __init__(self, config: PushConfig):
        self.config = config
        self.token_store = DeviceTokenStore()
        self._fcm = FCMProvider(config) if config.fcm_project_id else None
        self._apns = APNSProvider(config) if config.apns_bundle_id else None
    
    def _get_provider(self, platform: Platform) -> PushProvider | None:
        if platform == Platform.ANDROID:
            return self._fcm
        elif platform == Platform.IOS:
            return self._apns
        return None
    
    async def register_device(self, user_id: str, device: DeviceRegistration) -> bool:
        """Register a device for push notifications."""
        return await self.token_store.register(user_id, device)
    
    async def unregister_device(self, device_id: str) -> bool:
        """Unregister a device."""
        return await self.token_store.unregister(device_id)
    
    async def send_to_user(
        self,
        user_id: str,
        payload: PushPayload,
    ) -> list[PushResult]:
        """Send notification to all user devices."""
        devices = await self.token_store.get_user_devices(user_id)
        if not devices:
            logger.debug(f"No devices registered for user {user_id}")
            return []
        
        results = []
        for device in devices:
            provider = self._get_provider(device.platform)
            if not provider:
                logger.warning(f"No provider for platform {device.platform}")
                continue
            
            result = await provider.send(device.token, payload)
            result.device_id = device.device_id
            
            # Handle invalid tokens
            if result.status == PushStatus.INVALID_TOKEN:
                await self.token_store.mark_invalid(device.token)
            
            results.append(result)
        
        return results
    
    async def send_to_users(
        self,
        user_ids: list[str],
        payload: PushPayload,
    ) -> dict[str, list[PushResult]]:
        """Send notification to multiple users."""
        tasks = {uid: self.send_to_user(uid, payload) for uid in user_ids}
        results = {}
        for uid, task in tasks.items():
            results[uid] = await task
        return results
    
    async def broadcast_incident(
        self,
        incident_id: str,
        title: str,
        body: str,
        severity: Severity,
        user_ids: list[str] | None = None,
    ) -> dict[str, list[PushResult]]:
        """Broadcast an incident notification."""
        payload = PushPayload(
            title=title,
            body=body,
            incident_id=incident_id,
            severity=severity,
            action="view_incident",
            collapse_key=f"incident_{incident_id}",
            priority="high" if severity in (Severity.CRITICAL, Severity.HIGH) else "normal",
        )
        
        if user_ids:
            return await self.send_to_users(user_ids, payload)
        
        # Broadcast to all registered devices
        all_users = list(self.token_store._user_devices.keys())
        return await self.send_to_users(all_users, payload)


# === Factory ===

_push_service: PushService | None = None


def get_push_service(config: PushConfig | None = None) -> PushService:
    """Get or create the push service singleton."""
    global _push_service
    if _push_service is None:
        _push_service = PushService(config or PushConfig())
    return _push_service
