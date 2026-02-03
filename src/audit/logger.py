"""Audit logger with convenience methods for common events."""

import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any

from .models import AuditEvent, EventCategory, EventType, Outcome
from .store import AuditStore
from .store import audit_store as default_store


class AuditLogger:
    """High-level audit logging interface.

    Provides convenience methods for logging common audit events
    with proper categorization and metadata.
    """

    def __init__(self, store: AuditStore | None = None):
        self.store = store or default_store

    # -------------------------------------------------------------------------
    # Core logging methods
    # -------------------------------------------------------------------------

    async def log_event(
        self,
        category: EventCategory,
        event_type: EventType,
        action: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        user_email: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: Outcome = Outcome.SUCCESS,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        request_path: str | None = None,
        request_method: str | None = None,
        api_key_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log a generic audit event."""
        event = AuditEvent(
            category=category,
            event_type=event_type,
            action=action,
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            request_path=request_path,
            request_method=request_method,
            api_key_id=api_key_id,
            session_id=session_id,
            metadata=metadata or {},
            timestamp=datetime.utcnow(),
        )

        return await self.store.store_event(event)

    def log_event_sync(
        self,
        category: EventCategory,
        event_type: EventType,
        action: str,
        **kwargs: Any,
    ) -> AuditEvent:
        """Synchronous version of log_event for non-async contexts."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule in the running loop
            future = asyncio.ensure_future(
                self.log_event(category, event_type, action, **kwargs)
            )
            return future  # type: ignore
        else:
            return loop.run_until_complete(
                self.log_event(category, event_type, action, **kwargs)
            )

    # -------------------------------------------------------------------------
    # Context managers for automatic timing
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def timed_operation(
        self,
        category: EventCategory,
        event_type: EventType,
        action: str,
        **kwargs: Any,
    ):
        """Async context manager that automatically logs duration.

        Usage:
            async with logger.timed_operation(
                EventCategory.DATA_ACCESS,
                EventType.LOGS_ACCESSED,
                "Fetching logs for incident",
                tenant_id="tenant-123",
            ) as ctx:
                # Do work
                ctx["metadata"]["log_count"] = 150

        The duration_ms will be automatically added to metadata.
        """
        start = time.perf_counter()
        context: dict[str, Any] = {
            "metadata": kwargs.pop("metadata", None) or {},
            "outcome": Outcome.SUCCESS,
        }

        try:
            yield context
        except Exception as e:
            context["outcome"] = Outcome.ERROR
            context["metadata"]["error"] = str(e)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            context["metadata"]["duration_ms"] = round(duration_ms, 2)

            await self.log_event(
                category,
                event_type,
                action,
                outcome=context["outcome"],
                metadata=context["metadata"],
                **kwargs,
            )

    @contextmanager
    def timed_operation_sync(
        self,
        category: EventCategory,
        event_type: EventType,
        action: str,
        **kwargs: Any,
    ):
        """Sync context manager that schedules audit log after completion."""
        start = time.perf_counter()
        context: dict[str, Any] = {
            "metadata": kwargs.pop("metadata", None) or {},
            "outcome": Outcome.SUCCESS,
        }

        try:
            yield context
        except Exception as e:
            context["outcome"] = Outcome.ERROR
            context["metadata"]["error"] = str(e)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            context["metadata"]["duration_ms"] = round(duration_ms, 2)

            self.log_event_sync(
                category,
                event_type,
                action,
                outcome=context["outcome"],
                metadata=context["metadata"],
                **kwargs,
            )

    # -------------------------------------------------------------------------
    # Authentication events
    # -------------------------------------------------------------------------

    async def log_login_success(
        self,
        *,
        tenant_id: str,
        user_id: str,
        user_email: str,
        provider: str = "local",
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: str | None = None,
    ) -> AuditEvent:
        """Log a successful login."""
        return await self.log_event(
            EventCategory.AUTHENTICATION,
            EventType.LOGIN_SUCCESS,
            f"User {user_email} logged in via {provider}",
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            metadata={"provider": provider},
        )

    async def log_login_failure(
        self,
        *,
        email: str,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> AuditEvent:
        """Log a failed login attempt."""
        return await self.log_event(
            EventCategory.AUTHENTICATION,
            EventType.LOGIN_FAILURE,
            f"Failed login attempt for {email}: {reason}",
            tenant_id=tenant_id,
            user_email=email,
            outcome=Outcome.FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": reason, "email": email},
        )

    async def log_logout(
        self,
        *,
        tenant_id: str,
        user_id: str,
        user_email: str | None = None,
        session_id: str | None = None,
    ) -> AuditEvent:
        """Log a logout event."""
        return await self.log_event(
            EventCategory.AUTHENTICATION,
            EventType.LOGOUT,
            f"User logged out",
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            session_id=session_id,
        )

    async def log_session_created(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log session creation."""
        return await self.log_event(
            EventCategory.AUTHENTICATION,
            EventType.SESSION_CREATED,
            "Session created",
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            resource_type="session",
            resource_id=session_id,
        )

    async def log_token_refresh(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str | None = None,
    ) -> AuditEvent:
        """Log token refresh."""
        return await self.log_event(
            EventCategory.AUTHENTICATION,
            EventType.TOKEN_REFRESH,
            "Access token refreshed",
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    # -------------------------------------------------------------------------
    # Authorization events
    # -------------------------------------------------------------------------

    async def log_access_denied(
        self,
        *,
        tenant_id: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        reason: str,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log an access denied event."""
        return await self.log_event(
            EventCategory.AUTHORIZATION,
            EventType.ACCESS_DENIED,
            f"Access denied for {action} on {resource_type}/{resource_id}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=Outcome.DENIED,
            ip_address=ip_address,
            metadata={"action": action, "reason": reason},
        )

    async def log_access_granted(
        self,
        *,
        tenant_id: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
    ) -> AuditEvent:
        """Log access granted."""
        return await self.log_event(
            EventCategory.AUTHORIZATION,
            EventType.ACCESS_GRANTED,
            f"Access granted for {action} on {resource_type}/{resource_id}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata={"action": action},
        )

    async def log_role_assigned(
        self,
        *,
        tenant_id: str,
        assigned_by_user_id: str,
        target_user_id: str,
        role: str,
    ) -> AuditEvent:
        """Log role assignment."""
        return await self.log_event(
            EventCategory.AUTHORIZATION,
            EventType.ROLE_ASSIGNED,
            f"Role '{role}' assigned to user",
            tenant_id=tenant_id,
            user_id=assigned_by_user_id,
            resource_type="user",
            resource_id=target_user_id,
            metadata={"role": role, "target_user_id": target_user_id},
        )

    # -------------------------------------------------------------------------
    # Data access events
    # -------------------------------------------------------------------------

    async def log_incident_viewed(
        self,
        *,
        tenant_id: str,
        user_id: str,
        incident_id: str,
    ) -> AuditEvent:
        """Log incident view."""
        return await self.log_event(
            EventCategory.DATA_ACCESS,
            EventType.INCIDENT_VIEWED,
            f"Viewed incident {incident_id}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="incident",
            resource_id=incident_id,
        )

    async def log_incident_created(
        self,
        *,
        tenant_id: str,
        user_id: str,
        incident_id: str,
        title: str | None = None,
    ) -> AuditEvent:
        """Log incident creation."""
        return await self.log_event(
            EventCategory.DATA_ACCESS,
            EventType.INCIDENT_CREATED,
            f"Created incident {incident_id}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="incident",
            resource_id=incident_id,
            metadata={"title": title} if title else {},
        )

    async def log_logs_accessed(
        self,
        *,
        tenant_id: str,
        user_id: str,
        service: str,
        log_count: int = 0,
        duration_ms: float | None = None,
    ) -> AuditEvent:
        """Log when logs are accessed."""
        metadata: dict[str, Any] = {"service": service, "log_count": log_count}
        if duration_ms:
            metadata["duration_ms"] = duration_ms

        return await self.log_event(
            EventCategory.DATA_ACCESS,
            EventType.LOGS_ACCESSED,
            f"Accessed logs for service {service}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="logs",
            resource_id=service,
            metadata=metadata,
        )

    # -------------------------------------------------------------------------
    # Configuration events
    # -------------------------------------------------------------------------

    async def log_settings_updated(
        self,
        *,
        tenant_id: str,
        user_id: str,
        setting_name: str,
        old_value: Any = None,
        new_value: Any = None,
    ) -> AuditEvent:
        """Log settings update."""
        return await self.log_event(
            EventCategory.CONFIGURATION,
            EventType.SETTINGS_UPDATED,
            f"Updated setting '{setting_name}'",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="setting",
            resource_id=setting_name,
            metadata={
                "setting_name": setting_name,
                "old_value": old_value,
                "new_value": new_value,
            },
        )

    async def log_feature_enabled(
        self,
        *,
        tenant_id: str,
        user_id: str,
        feature_name: str,
    ) -> AuditEvent:
        """Log feature enablement."""
        return await self.log_event(
            EventCategory.CONFIGURATION,
            EventType.FEATURE_ENABLED,
            f"Enabled feature '{feature_name}'",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="feature",
            resource_id=feature_name,
        )

    # -------------------------------------------------------------------------
    # API Key events
    # -------------------------------------------------------------------------

    async def log_api_key_created(
        self,
        *,
        tenant_id: str,
        user_id: str,
        api_key_id: str,
        key_name: str,
        scopes: list[str] | None = None,
    ) -> AuditEvent:
        """Log API key creation."""
        return await self.log_event(
            EventCategory.API_KEY,
            EventType.API_KEY_CREATED,
            f"Created API key '{key_name}'",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="api_key",
            resource_id=api_key_id,
            metadata={
                "key_name": key_name,
                "scopes": scopes or [],
            },
        )

    async def log_api_key_revoked(
        self,
        *,
        tenant_id: str,
        user_id: str,
        api_key_id: str,
        key_name: str,
        reason: str | None = None,
    ) -> AuditEvent:
        """Log API key revocation."""
        return await self.log_event(
            EventCategory.API_KEY,
            EventType.API_KEY_REVOKED,
            f"Revoked API key '{key_name}'",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="api_key",
            resource_id=api_key_id,
            metadata={
                "key_name": key_name,
                "reason": reason,
            },
        )

    async def log_api_key_used(
        self,
        *,
        tenant_id: str,
        api_key_id: str,
        endpoint: str,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log API key usage."""
        return await self.log_event(
            EventCategory.API_KEY,
            EventType.API_KEY_USED,
            f"API key used for {endpoint}",
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            resource_type="api_key",
            resource_id=api_key_id,
            ip_address=ip_address,
            metadata={"endpoint": endpoint},
        )

    # -------------------------------------------------------------------------
    # Webhook events
    # -------------------------------------------------------------------------

    async def log_webhook_received(
        self,
        *,
        tenant_id: str,
        webhook_type: str,
        source: str,
        event_id: str | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log webhook receipt."""
        return await self.log_event(
            EventCategory.WEBHOOK,
            EventType.WEBHOOK_RECEIVED,
            f"Received {source} webhook: {webhook_type}",
            tenant_id=tenant_id,
            ip_address=ip_address,
            metadata={
                "webhook_type": webhook_type,
                "source": source,
                "event_id": event_id,
            },
        )

    async def log_webhook_processed(
        self,
        *,
        tenant_id: str,
        webhook_type: str,
        source: str,
        event_id: str | None = None,
        processing_time_ms: float | None = None,
    ) -> AuditEvent:
        """Log successful webhook processing."""
        metadata: dict[str, Any] = {
            "webhook_type": webhook_type,
            "source": source,
            "event_id": event_id,
        }
        if processing_time_ms:
            metadata["processing_time_ms"] = processing_time_ms

        return await self.log_event(
            EventCategory.WEBHOOK,
            EventType.WEBHOOK_PROCESSED,
            f"Processed {source} webhook: {webhook_type}",
            tenant_id=tenant_id,
            metadata=metadata,
        )

    async def log_webhook_failed(
        self,
        *,
        tenant_id: str,
        webhook_type: str,
        source: str,
        error: str,
        event_id: str | None = None,
    ) -> AuditEvent:
        """Log webhook processing failure."""
        return await self.log_event(
            EventCategory.WEBHOOK,
            EventType.WEBHOOK_FAILED,
            f"Failed to process {source} webhook: {error}",
            tenant_id=tenant_id,
            outcome=Outcome.ERROR,
            metadata={
                "webhook_type": webhook_type,
                "source": source,
                "event_id": event_id,
                "error": error,
            },
        )

    # -------------------------------------------------------------------------
    # User management events
    # -------------------------------------------------------------------------

    async def log_user_created(
        self,
        *,
        tenant_id: str,
        created_by_user_id: str,
        new_user_id: str,
        new_user_email: str,
        role: str = "member",
    ) -> AuditEvent:
        """Log user creation."""
        return await self.log_event(
            EventCategory.USER_MANAGEMENT,
            EventType.USER_CREATED,
            f"Created user {new_user_email} with role {role}",
            tenant_id=tenant_id,
            user_id=created_by_user_id,
            resource_type="user",
            resource_id=new_user_id,
            metadata={
                "new_user_email": new_user_email,
                "role": role,
            },
        )

    async def log_user_invited(
        self,
        *,
        tenant_id: str,
        invited_by_user_id: str,
        invitee_email: str,
        role: str = "member",
    ) -> AuditEvent:
        """Log user invitation."""
        return await self.log_event(
            EventCategory.USER_MANAGEMENT,
            EventType.USER_INVITED,
            f"Invited {invitee_email} with role {role}",
            tenant_id=tenant_id,
            user_id=invited_by_user_id,
            metadata={
                "invitee_email": invitee_email,
                "role": role,
            },
        )

    async def log_user_deleted(
        self,
        *,
        tenant_id: str,
        deleted_by_user_id: str,
        deleted_user_id: str,
        deleted_user_email: str,
    ) -> AuditEvent:
        """Log user deletion."""
        return await self.log_event(
            EventCategory.USER_MANAGEMENT,
            EventType.USER_DELETED,
            f"Deleted user {deleted_user_email}",
            tenant_id=tenant_id,
            user_id=deleted_by_user_id,
            resource_type="user",
            resource_id=deleted_user_id,
            metadata={"deleted_user_email": deleted_user_email},
        )

    # -------------------------------------------------------------------------
    # Billing events
    # -------------------------------------------------------------------------

    async def log_subscription_created(
        self,
        *,
        tenant_id: str,
        user_id: str,
        plan: str,
        subscription_id: str,
    ) -> AuditEvent:
        """Log subscription creation."""
        return await self.log_event(
            EventCategory.BILLING,
            EventType.SUBSCRIPTION_CREATED,
            f"Created subscription for plan: {plan}",
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={"plan": plan},
        )

    async def log_payment_succeeded(
        self,
        *,
        tenant_id: str,
        amount: float,
        currency: str,
        payment_id: str,
    ) -> AuditEvent:
        """Log successful payment."""
        return await self.log_event(
            EventCategory.BILLING,
            EventType.PAYMENT_SUCCEEDED,
            f"Payment of {amount} {currency} succeeded",
            tenant_id=tenant_id,
            resource_type="payment",
            resource_id=payment_id,
            metadata={
                "amount": amount,
                "currency": currency,
            },
        )

    async def log_payment_failed(
        self,
        *,
        tenant_id: str,
        amount: float,
        currency: str,
        payment_id: str,
        reason: str,
    ) -> AuditEvent:
        """Log failed payment."""
        return await self.log_event(
            EventCategory.BILLING,
            EventType.PAYMENT_FAILED,
            f"Payment of {amount} {currency} failed: {reason}",
            tenant_id=tenant_id,
            outcome=Outcome.FAILURE,
            resource_type="payment",
            resource_id=payment_id,
            metadata={
                "amount": amount,
                "currency": currency,
                "reason": reason,
            },
        )

    # -------------------------------------------------------------------------
    # System events
    # -------------------------------------------------------------------------

    async def log_audit_exported(
        self,
        *,
        tenant_id: str,
        user_id: str,
        export_format: str,
        event_count: int,
        date_range: str | None = None,
    ) -> AuditEvent:
        """Log audit log export."""
        return await self.log_event(
            EventCategory.SYSTEM,
            EventType.AUDIT_LOG_EXPORTED,
            f"Exported {event_count} audit events as {export_format}",
            tenant_id=tenant_id,
            user_id=user_id,
            metadata={
                "format": export_format,
                "event_count": event_count,
                "date_range": date_range,
            },
        )

    async def log_rate_limit_exceeded(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        api_key_id: str | None = None,
        endpoint: str,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Log rate limit exceeded."""
        return await self.log_event(
            EventCategory.SYSTEM,
            EventType.RATE_LIMIT_EXCEEDED,
            f"Rate limit exceeded for {endpoint}",
            tenant_id=tenant_id,
            user_id=user_id,
            api_key_id=api_key_id,
            ip_address=ip_address,
            outcome=Outcome.DENIED,
            metadata={"endpoint": endpoint},
        )


# Global instance
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    return audit_logger
