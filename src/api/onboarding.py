"""Onboarding API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr

from ..auth.middleware import AuthContext, get_auth_context, require_role
from ..auth.models import UserRole
from ..onboarding import checklist_store
from ..onboarding.analytics import onboarding_analytics
from ..onboarding.email_verification import email_verification_service
from ..onboarding.invites import invite_service

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class InviteRequest(BaseModel):
    """Request to send an onboarding invite."""

    email: EmailStr
    role: UserRole = UserRole.MEMBER


class InviteAcceptRequest(BaseModel):
    """Request to accept an onboarding invite."""

    token: str
    name: str
    password: str | None = None


class VerificationRequest(BaseModel):
    """Request to send a verification email."""

    email: EmailStr | None = None


class VerificationConfirmRequest(BaseModel):
    """Request to confirm a verification token."""

    token: str


@router.post("/invite")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def send_invite(
    request: InviteRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send a team invite."""
    if not auth.tenant_id or not auth.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    token = await invite_service.send_invite(
        email=str(request.email),
        tenant_id=auth.tenant_id,
        role=request.role,
        invited_by=auth.user.id,
    )

    return {"token": token}


@router.post("/invite/accept")
async def accept_invite(request: InviteAcceptRequest):
    """Accept an onboarding invite."""
    try:
        user = await invite_service.accept_invite(
            token=request.token,
            user_data={"name": request.name, "password": request.password},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        }
    }


@router.get("/invites")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def list_invites(auth: AuthContext = Depends(get_auth_context)):
    """List pending invites for the current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    invites = await invite_service.list_pending(auth.tenant_id)

    return {
        "invites": [invite.model_dump() for invite in invites],
        "count": len(invites),
    }


@router.post("/verify-email")
async def send_verification_email(
    request: VerificationRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send a verification email for the current user."""
    if not auth.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    email = str(request.email or auth.user.email)
    token = await email_verification_service.send_verification_email(
        user_id=auth.user.id,
        email=email,
    )

    return {"token": token}


@router.post("/verify-email/confirm")
async def confirm_verification(request: VerificationConfirmRequest):
    """Confirm a verification token."""
    verified = await email_verification_service.verify_email(request.token)
    if not verified:
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")

    return {"verified": True}


@router.get("/checklist")
async def get_checklist(auth: AuthContext = Depends(get_auth_context)):
    """Return the onboarding checklist for the current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    checklist = await checklist_store.get(auth.tenant_id)
    return checklist.to_dict()


@router.post("/checklist/{step}")
async def update_checklist_step(
    step: str,
    done: bool = True,
    auth: AuthContext = Depends(get_auth_context),
):
    """Update a checklist step for the current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    try:
        checklist = await checklist_store.set_step(auth.tenant_id, step, done)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return checklist.to_dict()


@router.get("/analytics/funnel")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def get_funnel_report(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    """Return funnel conversion rates."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    report = onboarding_analytics.get_funnel((start_date, end_date))
    return report.model_dump()


@router.get("/analytics/drop-offs")
@require_role(UserRole.OWNER, UserRole.ADMIN)
async def get_drop_off_report(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    """Return onboarding drop-off report."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    report = onboarding_analytics.get_drop_off_report((start_date, end_date))
    return {"drop_offs": [item.model_dump() for item in report]}


@router.get("/analytics/time-to-value")
async def get_time_to_value(auth: AuthContext = Depends(get_auth_context)):
    """Return average time to first context card."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    average = onboarding_analytics.get_average_time_to_value()
    return {
        "average_seconds": average.total_seconds() if average else None,
    }
