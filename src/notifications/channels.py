"""Channel implementations for sending notifications."""

import asyncio
import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

from .models import ChannelType, NotificationChannel, NotificationPayload
from .templates import TemplateRenderer

logger = logging.getLogger(__name__)


class ChannelError(Exception):
    """Base exception for channel errors."""
    pass


class ChannelDeliveryError(ChannelError):
    """Failed to deliver notification."""
    pass


class ChannelConfigError(ChannelError):
    """Channel configuration error."""
    pass


class BaseChannel(ABC):
    """Abstract base class for notification channels."""
    
    channel_type: ChannelType
    
    def __init__(self, config: NotificationChannel, renderer: TemplateRenderer | None = None):
        self.config = config
        self.renderer = renderer or TemplateRenderer()
        self._client: httpx.AsyncClient | None = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @abstractmethod
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send a notification. Returns delivery metadata."""
        pass
    
    async def validate_config(self) -> bool:
        """Validate channel configuration."""
        return bool(self.config.address)
    
    def _render(self, payload: NotificationPayload) -> dict[str, Any]:
        """Render notification content for this channel."""
        return self.renderer.render_for_channel(
            notification_type=payload.type,
            channel_type=self.channel_type,
            title=payload.title,
            severity=payload.severity,
            description=payload.message,
            incident_id=payload.incident_id,
            service=payload.service,
            team=payload.team,
            created_at=payload.created_at,
            incident_url=payload.data.get("incident_url", ""),
            **payload.data,
        )


class EmailChannel(BaseChannel):
    """Email notification channel."""
    
    channel_type = ChannelType.EMAIL
    
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send email notification."""
        rendered = self._render(payload)
        
        # Get SMTP settings from config
        smtp_host = self.config.settings.get("smtp_host", "localhost")
        smtp_port = self.config.settings.get("smtp_port", 587)
        smtp_user = self.config.settings.get("smtp_user", "")
        smtp_pass = self.config.settings.get("smtp_pass", "")
        from_addr = self.config.settings.get("from_address", "notifications@example.com")
        
        try:
            # Using httpx for email API (e.g., SendGrid, Mailgun, SES)
            api_url = self.config.settings.get("api_url")
            api_key = self.config.settings.get("api_key")
            
            if api_url and api_key:
                # Use email API
                response = await self.client.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "to": self.config.address,
                        "from": from_addr,
                        "subject": rendered.get("subject", "Notification"),
                        "text": rendered.get("text", rendered.get("body", "")),
                        "html": rendered.get("html"),
                    },
                )
                response.raise_for_status()
                return {"message_id": response.json().get("id"), "status": "sent"}
            else:
                # Simulate SMTP send (actual implementation would use aiosmtplib)
                logger.info(f"Email to {self.config.address}: {rendered.get('subject')}")
                return {"status": "sent", "simulated": True}
                
        except httpx.HTTPError as e:
            raise ChannelDeliveryError(f"Failed to send email: {e}") from e
    
    async def validate_config(self) -> bool:
        """Validate email address format."""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, self.config.address))


class SlackChannel(BaseChannel):
    """Slack notification channel."""
    
    channel_type = ChannelType.SLACK
    
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send Slack notification."""
        rendered = self._render(payload)
        
        webhook_url = self.config.settings.get("webhook_url") or self.config.address
        bot_token = self.config.settings.get("bot_token")
        channel = self.config.settings.get("channel", self.config.address)
        
        try:
            if bot_token:
                # Use Slack API with bot token
                response = await self.client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel,
                        "blocks": rendered.get("blocks"),
                        "text": rendered.get("text", payload.title),
                    },
                )
                data = response.json()
                if not data.get("ok"):
                    raise ChannelDeliveryError(f"Slack API error: {data.get('error')}")
                return {"ts": data.get("ts"), "channel": data.get("channel")}
            else:
                # Use incoming webhook
                response = await self.client.post(
                    webhook_url,
                    json={
                        "blocks": rendered.get("blocks"),
                        "text": rendered.get("text", payload.title),
                    },
                )
                response.raise_for_status()
                return {"status": "sent"}
                
        except httpx.HTTPError as e:
            raise ChannelDeliveryError(f"Failed to send Slack message: {e}") from e


class SMSChannel(BaseChannel):
    """SMS notification channel (Twilio integration)."""
    
    channel_type = ChannelType.SMS
    
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send SMS notification."""
        rendered = self._render(payload)
        
        account_sid = self.config.settings.get("account_sid")
        auth_token = self.config.settings.get("auth_token")
        from_number = self.config.settings.get("from_number")
        
        if not all([account_sid, auth_token, from_number]):
            raise ChannelConfigError("Missing Twilio configuration")
        
        try:
            response = await self.client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={
                    "To": self.config.address,
                    "From": from_number,
                    "Body": rendered.get("text", payload.title)[:160],
                },
            )
            response.raise_for_status()
            data = response.json()
            return {"sid": data.get("sid"), "status": data.get("status")}
            
        except httpx.HTTPError as e:
            raise ChannelDeliveryError(f"Failed to send SMS: {e}") from e
    
    async def validate_config(self) -> bool:
        """Validate phone number format."""
        import re
        # E.164 format
        phone_pattern = r'^\+[1-9]\d{1,14}$'
        return bool(re.match(phone_pattern, self.config.address))


class PushChannel(BaseChannel):
    """Push notification channel (Firebase/APNs)."""
    
    channel_type = ChannelType.PUSH
    
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send push notification."""
        rendered = self._render(payload)
        
        provider = self.config.settings.get("provider", "firebase")
        
        if provider == "firebase":
            return await self._send_firebase(rendered, payload)
        elif provider == "apns":
            return await self._send_apns(rendered, payload)
        else:
            raise ChannelConfigError(f"Unknown push provider: {provider}")
    
    async def _send_firebase(self, rendered: dict, payload: NotificationPayload) -> dict[str, Any]:
        """Send via Firebase Cloud Messaging."""
        server_key = self.config.settings.get("server_key")
        
        if not server_key:
            raise ChannelConfigError("Missing Firebase server key")
        
        try:
            response = await self.client.post(
                "https://fcm.googleapis.com/fcm/send",
                headers={
                    "Authorization": f"key={server_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": self.config.address,  # Device token
                    "notification": {
                        "title": rendered.get("title", payload.title),
                        "body": rendered.get("body", payload.message),
                    },
                    "data": rendered.get("data", {}),
                },
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            raise ChannelDeliveryError(f"Failed to send push notification: {e}") from e
    
    async def _send_apns(self, rendered: dict, payload: NotificationPayload) -> dict[str, Any]:
        """Send via Apple Push Notification service."""
        # APNs requires JWT authentication - simplified here
        key_id = self.config.settings.get("key_id")
        team_id = self.config.settings.get("team_id")
        bundle_id = self.config.settings.get("bundle_id")
        
        if not all([key_id, team_id, bundle_id]):
            raise ChannelConfigError("Missing APNs configuration")
        
        # In production, would use httpx with HTTP/2 to api.push.apple.com
        logger.info(f"APNs push to {self.config.address}: {rendered.get('title')}")
        return {"status": "sent", "simulated": True}


class WebhookChannel(BaseChannel):
    """Generic webhook notification channel."""
    
    channel_type = ChannelType.WEBHOOK
    
    async def send(self, payload: NotificationPayload) -> dict[str, Any]:
        """Send webhook notification."""
        webhook_url = self.config.address
        secret = self.config.settings.get("secret")
        headers = self.config.settings.get("headers", {})
        method = self.config.settings.get("method", "POST").upper()
        
        # Build webhook payload
        webhook_payload = {
            "id": payload.id,
            "type": payload.type.value,
            "severity": payload.severity.value,
            "title": payload.title,
            "message": payload.message,
            "incident_id": payload.incident_id,
            "service": payload.service,
            "team": payload.team,
            "tags": payload.tags,
            "timestamp": payload.created_at.isoformat(),
            "data": payload.data,
        }
        
        body = json.dumps(webhook_payload)
        
        # Sign payload if secret is configured
        if secret:
            signature = hmac.new(
                secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Signature-256"] = f"sha256={signature}"
        
        headers["Content-Type"] = "application/json"
        
        try:
            if method == "POST":
                response = await self.client.post(webhook_url, headers=headers, content=body)
            elif method == "PUT":
                response = await self.client.put(webhook_url, headers=headers, content=body)
            else:
                raise ChannelConfigError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            return {
                "status_code": response.status_code,
                "response": response.text[:200] if response.text else None,
            }
            
        except httpx.HTTPError as e:
            raise ChannelDeliveryError(f"Webhook delivery failed: {e}") from e
    
    async def validate_config(self) -> bool:
        """Validate webhook URL."""
        try:
            from urllib.parse import urlparse
            result = urlparse(self.config.address)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False


# Channel factory
CHANNEL_CLASSES: dict[ChannelType, type[BaseChannel]] = {
    ChannelType.EMAIL: EmailChannel,
    ChannelType.SLACK: SlackChannel,
    ChannelType.SMS: SMSChannel,
    ChannelType.PUSH: PushChannel,
    ChannelType.WEBHOOK: WebhookChannel,
}


def create_channel(config: NotificationChannel, renderer: TemplateRenderer | None = None) -> BaseChannel:
    """Factory function to create a channel instance."""
    channel_class = CHANNEL_CLASSES.get(config.type)
    if not channel_class:
        raise ChannelConfigError(f"Unknown channel type: {config.type}")
    return channel_class(config, renderer)


class ChannelManager:
    """Manages multiple notification channels."""
    
    def __init__(self, renderer: TemplateRenderer | None = None):
        self.renderer = renderer or TemplateRenderer()
        self._channels: dict[str, BaseChannel] = {}
    
    def register(self, name: str, config: NotificationChannel) -> BaseChannel:
        """Register a channel configuration."""
        channel = create_channel(config, self.renderer)
        self._channels[name] = channel
        return channel
    
    def get(self, name: str) -> BaseChannel | None:
        """Get a registered channel by name."""
        return self._channels.get(name)
    
    async def send(
        self,
        payload: NotificationPayload,
        channel_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send notification through specified or all channels."""
        targets = channel_names or list(self._channels.keys())
        results = {}
        
        async def send_to_channel(name: str, channel: BaseChannel) -> tuple[str, Any]:
            try:
                result = await channel.send(payload)
                return name, {"success": True, "result": result}
            except ChannelError as e:
                logger.error(f"Channel {name} failed: {e}")
                return name, {"success": False, "error": str(e)}
        
        # Send to all channels concurrently
        tasks = [
            send_to_channel(name, self._channels[name])
            for name in targets
            if name in self._channels
        ]
        
        for coro in asyncio.as_completed(tasks):
            name, result = await coro
            results[name] = result
        
        return results
    
    async def close_all(self) -> None:
        """Close all channel connections."""
        for channel in self._channels.values():
            await channel.close()
