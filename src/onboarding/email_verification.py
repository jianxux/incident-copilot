"""Email verification flow for onboarding."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from pydantic import BaseModel, Field

from ..auth.service import auth_service
from ..config import get_settings

logger = structlog.get_logger()

VERIFICATION_EXPIRY = timedelta(hours=24)


class EmailVerificationToken(BaseModel):
    """Email verification token record."""

    user_id: str
    email: str
    token: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    def is_expired(self) -> bool:
        """Return True when token is past expiry."""
        return datetime.now(UTC) > self.expires_at


class EmailVerificationService:
    """Service for issuing and validating email verification tokens."""

    def __init__(self):
        self._tokens: dict[str, EmailVerificationToken] = {}

    async def send_verification_email(self, user_id: str, email: str) -> str:
        """Create and log a verification email token."""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + VERIFICATION_EXPIRY
        record = EmailVerificationToken(
            user_id=user_id,
            email=email,
            token=token,
            expires_at=expires_at,
        )
        self._tokens[token] = record

        settings = get_settings()
        verify_url = (
            f"{settings.app_url}/dashboard/onboarding/verify-email?token={token}"
        )
        logger.info(
            "email_verification_sent",
            user_id=user_id,
            email=email,
            verify_url=verify_url,
        )

        return token

    async def verify_email(self, token: str) -> bool:
        """Verify a token and return True when valid."""
        record = self._tokens.get(token)
        if not record:
            return False
        if record.is_expired():
            self._tokens.pop(token, None)
            return False
        self._tokens.pop(token, None)
        user = await auth_service.get_user(record.user_id)
        if user:
            user.email_verified = True
        return True


email_verification_service = EmailVerificationService()
