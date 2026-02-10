"""Team invite flow for onboarding."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import structlog
from pydantic import BaseModel, Field

from ..auth.models import User, UserRole
from ..auth.service import auth_service
from ..config import get_settings

logger = structlog.get_logger()

INVITE_EXPIRY = timedelta(hours=72)


class InviteStatus(StrEnum):
    """Invite status values."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class InviteRecord(BaseModel):
    """Invite record for team onboarding."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    email: str
    tenant_id: str
    role: UserRole
    invited_by: str
    token: str
    status: InviteStatus = InviteStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    def is_expired(self) -> bool:
        """Return True when invite is past expiry."""
        return datetime.now(UTC) > self.expires_at


class InviteService:
    """Service for issuing and accepting team invites."""

    def __init__(self):
        self._invites_by_token: dict[str, InviteRecord] = {}

    def _expire_if_needed(self, invite: InviteRecord) -> InviteRecord:
        if invite.status == InviteStatus.PENDING and invite.is_expired():
            invite.status = InviteStatus.EXPIRED
        return invite

    async def send_invite(
        self, email: str, tenant_id: str, role: UserRole, invited_by: str
    ) -> str:
        """Send an invite and return the invite token."""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + INVITE_EXPIRY
        invite = InviteRecord(
            email=email,
            tenant_id=tenant_id,
            role=role,
            invited_by=invited_by,
            token=token,
            expires_at=expires_at,
        )
        self._invites_by_token[token] = invite

        settings = get_settings()
        invite_url = f"{settings.app_url}/dashboard/onboarding/invite?token={token}"
        logger.info(
            "onboarding_invite_sent",
            email=email,
            tenant_id=tenant_id,
            role=role.value,
            invite_url=invite_url,
        )

        return token

    async def verify_invite(self, token: str) -> InviteRecord:
        """Verify invite token and return its record."""
        invite = self._invites_by_token.get(token)
        if not invite:
            raise ValueError("Invite not found")
        return self._expire_if_needed(invite)

    async def accept_invite(self, token: str, user_data: dict) -> User:
        """Accept an invite and create the user."""
        invite = await self.verify_invite(token)
        if invite.status != InviteStatus.PENDING:
            raise ValueError(f"Invite is {invite.status.value}")

        user = await auth_service.create_user(
            email=invite.email,
            name=str(user_data.get("name") or invite.email),
            tenant_id=invite.tenant_id,
            role=invite.role,
            password=user_data.get("password"),
        )

        invite.status = InviteStatus.ACCEPTED
        logger.info(
            "onboarding_invite_accepted",
            token=token,
            tenant_id=invite.tenant_id,
            user_id=user.id,
        )
        return user

    async def list_pending(self, tenant_id: str) -> list[InviteRecord]:
        """List pending invites for a tenant."""
        records = []
        for invite in self._invites_by_token.values():
            invite = self._expire_if_needed(invite)
            if invite.tenant_id == tenant_id and invite.status == InviteStatus.PENDING:
                records.append(invite)
        return records


invite_service = InviteService()
