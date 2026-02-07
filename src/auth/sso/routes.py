"""FastAPI routes for SSO (SAML and OIDC) authentication."""

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from src.config import get_settings

from .models import (
    OIDC_PROVIDER_PRESETS,
    IdentityProvider,
    IdentityProviderType,
    OIDCSettings,
    SAMLSettings,
    SSOConfig,
    SSOSession,
)
from .oidc import OIDCProvider
from .saml import SAMLProvider

logger = structlog.get_logger()

router = APIRouter(prefix="/auth/sso", tags=["sso"])

# In-memory storage (replace with database in production)
_sso_configs: dict[str, SSOConfig] = {}
_sso_sessions: dict[str, SSOSession] = {}  # state -> session


def get_or_create_sso_config(tenant_id: str) -> SSOConfig:
    """Get or create an SSO configuration for a tenant."""
    if tenant_id not in _sso_configs:
        _sso_configs[tenant_id] = SSOConfig(tenant_id=tenant_id)
    return _sso_configs[tenant_id]


def save_sso_session(session: SSOSession) -> None:
    """Save an SSO session for later retrieval."""
    _sso_sessions[session.state] = session


def get_sso_session(state: str) -> SSOSession | None:
    """Get and remove an SSO session by state.

    Sessions are removed after retrieval (single-use).
    Returns None if session doesn't exist or is expired.
    """
    session = _sso_sessions.pop(state, None)
    if session and session.is_expired():
        return None
    return session


def get_app_url() -> str:
    """Get the application base URL from settings."""
    return get_settings().app_url


# --- Configuration Routes ---


@router.get("/config/{tenant_id}")
async def get_sso_config(tenant_id: str) -> dict[str, Any]:
    """Get SSO configuration for a tenant."""
    config = get_or_create_sso_config(tenant_id)

    return {
        "tenant_id": config.tenant_id,
        "sso_enabled": config.sso_enabled,
        "sso_required": config.sso_required,
        "jit_provisioning_enabled": config.jit_provisioning_enabled,
        "identity_providers": [
            {
                "id": idp.id,
                "name": idp.name,
                "slug": idp.slug,
                "provider_type": idp.provider_type.value,
                "is_active": idp.is_active,
                "is_default": idp.is_default,
                "email_domains": idp.email_domains,
            }
            for idp in config.identity_providers
        ],
    }


@router.post("/config/{tenant_id}/enable")
async def enable_sso(tenant_id: str) -> dict[str, Any]:
    """Enable SSO for a tenant."""
    if tenant_id not in _sso_configs:
        raise HTTPException(status_code=404, detail="SSO configuration not found")

    config = _sso_configs[tenant_id]

    if not config.identity_providers:
        raise HTTPException(
            status_code=400,
            detail="Cannot enable SSO without at least one identity provider",
        )

    config.sso_enabled = True
    config.updated_at = datetime.utcnow()

    return {"message": "SSO enabled", "tenant_id": tenant_id}


@router.post("/config/{tenant_id}/disable")
async def disable_sso(tenant_id: str) -> dict[str, Any]:
    """Disable SSO for a tenant."""
    config = get_or_create_sso_config(tenant_id)
    config.sso_enabled = False
    config.updated_at = datetime.utcnow()

    return {"message": "SSO disabled", "tenant_id": tenant_id}


@router.post("/config/{tenant_id}/idp")
async def add_identity_provider(
    tenant_id: str,
    idp_data: dict[str, Any],
) -> dict[str, Any]:
    """Add a new identity provider to a tenant."""
    config = get_or_create_sso_config(tenant_id)

    provider_type = IdentityProviderType(idp_data.get("provider_type", "oidc"))

    idp = IdentityProvider(
        tenant_id=tenant_id,
        name=idp_data["name"],
        slug=idp_data["slug"],
        provider_type=provider_type,
        email_domains=idp_data.get("email_domains", []),
        is_default=idp_data.get("is_default", False),
        role_mapping=idp_data.get("role_mapping", {}),
    )

    if provider_type == IdentityProviderType.SAML:
        saml_data = idp_data.get("saml_settings", {})
        idp.saml_settings = SAMLSettings(**saml_data)
    else:
        oidc_data = idp_data.get("oidc_settings", {})

        # Apply preset if specified
        preset_type = oidc_data.get("provider_type")
        if preset_type and preset_type in OIDC_PROVIDER_PRESETS:
            preset = OIDC_PROVIDER_PRESETS[preset_type]
            for key, value in preset.items():
                if key not in oidc_data:
                    oidc_data[key] = value

        idp.oidc_settings = OIDCSettings(**oidc_data)

    config.identity_providers.append(idp)
    config.updated_at = datetime.utcnow()

    logger.info(
        "idp_added",
        tenant_id=tenant_id,
        idp_id=idp.id,
        provider_type=provider_type.value,
    )

    return {
        "message": "Identity provider added",
        "idp_id": idp.id,
        "tenant_id": tenant_id,
    }


@router.delete("/config/{tenant_id}/idp/{idp_id}")
async def remove_identity_provider(
    tenant_id: str,
    idp_id: str,
) -> dict[str, Any]:
    """Remove an identity provider from a tenant."""
    config = get_or_create_sso_config(tenant_id)

    idp = config.get_idp_by_id(idp_id)
    if not idp:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    config.identity_providers = [p for p in config.identity_providers if p.id != idp_id]
    config.updated_at = datetime.utcnow()

    # Disable SSO if no providers left
    if not config.identity_providers:
        config.sso_enabled = False

    logger.info(
        "idp_removed",
        tenant_id=tenant_id,
        idp_id=idp_id,
    )

    return {"message": "Identity provider removed", "idp_id": idp_id}


# --- Discovery Route ---


@router.get("/discover")
async def discover_idp(
    email: str = Query(..., description="User email to discover IdP for"),
) -> dict[str, Any]:
    """Discover the identity provider for a given email address."""
    domain = email.split("@")[-1].lower()

    for config in _sso_configs.values():
        if not config.sso_enabled:
            continue

        idp = config.get_idp_for_email(email)
        if idp:
            return {
                "tenant_id": config.tenant_id,
                "idp_id": idp.id,
                "idp_name": idp.name,
                "provider_type": idp.provider_type.value,
                "login_url": f"/auth/sso/{idp.provider_type.value}/login/{config.tenant_id}?idp={idp.slug}",
            }

    raise HTTPException(
        status_code=404,
        detail=f"No SSO configured for domain: {domain}",
    )


# --- SAML Routes ---


@router.get("/saml/login/{tenant_id}")
async def saml_login(
    tenant_id: str,
    idp: str | None = Query(None, description="IdP slug"),
    return_to: str | None = Query(None, description="URL to return to after login"),
) -> RedirectResponse:
    """Initiate SAML login flow."""
    config = get_or_create_sso_config(tenant_id)

    if not config.sso_enabled:
        raise HTTPException(status_code=400, detail="SSO is not enabled for this tenant")

    # Get identity provider
    identity_provider = None
    if idp:
        identity_provider = config.get_idp_by_slug(idp)
    else:
        identity_provider = config.get_default_idp()

    if not identity_provider:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    if identity_provider.provider_type != IdentityProviderType.SAML:
        raise HTTPException(status_code=400, detail="IdP is not a SAML provider")

    # Create session
    session = SAMLProvider.create_session_for_auth(
        tenant_id=tenant_id,
        idp_id=identity_provider.id,
        relay_state=return_to,
    )
    save_sso_session(session)

    # Generate auth URL
    provider = SAMLProvider(identity_provider, get_app_url())
    auth_url = provider.generate_auth_request(session)

    logger.info(
        "saml_login_initiated",
        tenant_id=tenant_id,
        idp_id=identity_provider.id,
    )

    return RedirectResponse(url=auth_url, status_code=302)


@router.post("/saml/init")
async def saml_init(
    tenant_id: str = Form(...),
    idp_slug: str | None = Form(None),
    return_to: str | None = Form(None),
) -> dict[str, Any]:
    """Start SAML flow (POST variant for form submission)."""
    config = get_or_create_sso_config(tenant_id)

    if not config.sso_enabled:
        raise HTTPException(status_code=400, detail="SSO is not enabled for this tenant")

    identity_provider = None
    if idp_slug:
        identity_provider = config.get_idp_by_slug(idp_slug)
    else:
        identity_provider = config.get_default_idp()

    if not identity_provider:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    if identity_provider.provider_type != IdentityProviderType.SAML:
        raise HTTPException(status_code=400, detail="IdP is not a SAML provider")

    # Create session
    session = SAMLProvider.create_session_for_auth(
        tenant_id=tenant_id,
        idp_id=identity_provider.id,
        relay_state=return_to,
    )
    save_sso_session(session)

    # Generate auth URL
    provider = SAMLProvider(identity_provider, get_app_url())
    auth_url = provider.generate_auth_request(session)

    return {
        "redirect_url": auth_url,
        "state": session.state,
    }


@router.post("/saml/acs/{tenant_id}")
async def saml_acs(
    tenant_id: str,
    SAMLResponse: str = Form(...),  # noqa: N803
    RelayState: str | None = Form(None),  # noqa: N803
) -> RedirectResponse:
    """SAML Assertion Consumer Service (ACS) endpoint."""
    app_url = get_app_url()

    # Get session from RelayState
    session = get_sso_session(RelayState) if RelayState else None

    if not session:
        logger.warning("saml_acs_no_session", tenant_id=tenant_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_session_expired",
            status_code=302,
        )

    config = get_or_create_sso_config(tenant_id)
    idp = config.get_idp_by_id(session.idp_id)

    if not idp:
        logger.error("saml_acs_idp_not_found", tenant_id=tenant_id, idp_id=session.idp_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_config_error",
            status_code=302,
        )

    try:
        provider = SAMLProvider(idp, app_url)
        user_info = provider.process_response(
            saml_response=SAMLResponse,
            expected_request_id=session.saml_request_id,
        )

        # Update IdP last login
        idp.last_login_at = datetime.utcnow()

        logger.info(
            "saml_login_success",
            tenant_id=tenant_id,
            email=user_info.email,
        )

        # Build success redirect URL
        params = {
            "sso": "success",
            "email": user_info.email,
            "provider": "saml",
            "idp": idp.slug,
        }

        return_url = session.relay_state or f"{app_url}/dashboard"
        separator = "&" if "?" in return_url else "?"

        return RedirectResponse(
            url=f"{return_url}{separator}{urlencode(params)}",
            status_code=302,
        )

    except Exception as e:
        logger.error("saml_acs_error", error=str(e), tenant_id=tenant_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_validation_error&message={str(e)}",
            status_code=302,
        )


@router.get("/saml/metadata/{tenant_id}")
async def saml_metadata(
    tenant_id: str,
    idp: str | None = Query(None, description="IdP slug"),
) -> Response:
    """Get SP metadata for SAML configuration."""
    config = get_or_create_sso_config(tenant_id)

    # Get identity provider
    identity_provider = None
    if idp:
        identity_provider = config.get_idp_by_slug(idp)
    else:
        # Find first SAML provider
        for p in config.identity_providers:
            if p.provider_type == IdentityProviderType.SAML:
                identity_provider = p
                break

    if not identity_provider:
        # Return generic metadata
        app_url = get_app_url()
        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{app_url}/auth/sso/saml/metadata/{tenant_id}">
    <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
                        WantAssertionsSigned="true"
                        AuthnRequestsSigned="true">
        <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
        <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                     Location="{app_url}/auth/sso/saml/acs/{tenant_id}"
                                     index="0"
                                     isDefault="true"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>"""
    else:
        provider = SAMLProvider(identity_provider, get_app_url())
        metadata = provider.generate_metadata()

    return Response(
        content=metadata,
        media_type="application/xml",
    )


# --- OIDC Routes ---


@router.get("/oidc/login/{tenant_id}")
async def oidc_login(
    tenant_id: str,
    idp: str | None = Query(None, description="IdP slug"),
    return_to: str | None = Query(None, description="URL to return to after login"),
) -> RedirectResponse:
    """Initiate OIDC login flow."""
    config = get_or_create_sso_config(tenant_id)

    if not config.sso_enabled:
        raise HTTPException(status_code=400, detail="SSO is not enabled for this tenant")

    # Get identity provider
    identity_provider = None
    if idp:
        identity_provider = config.get_idp_by_slug(idp)
    else:
        identity_provider = config.get_default_idp()

    if not identity_provider:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    if identity_provider.provider_type != IdentityProviderType.OIDC:
        raise HTTPException(status_code=400, detail="IdP is not an OIDC provider")

    app_url = get_app_url()
    redirect_uri = f"{app_url}/auth/sso/oidc/callback/{tenant_id}"

    # Create session with PKCE
    use_pkce = identity_provider.oidc_settings.use_pkce if identity_provider.oidc_settings else True
    session = OIDCProvider.create_session_for_auth(
        tenant_id=tenant_id,
        idp_id=identity_provider.id,
        redirect_uri=redirect_uri,
        relay_state=return_to,
        use_pkce=use_pkce,
    )
    save_sso_session(session)

    # Generate auth URL
    provider = OIDCProvider(identity_provider, app_url)
    auth_url = await provider.generate_auth_url(session)

    logger.info(
        "oidc_login_initiated",
        tenant_id=tenant_id,
        idp_id=identity_provider.id,
    )

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/oidc/authorize")
async def oidc_authorize(
    tenant_id: str = Query(...),
    idp_slug: str | None = Query(None),
    return_to: str | None = Query(None),
) -> RedirectResponse:
    """Start OIDC authorization flow (alternative endpoint)."""
    return await oidc_login(
        tenant_id=tenant_id,
        idp=idp_slug,
        return_to=return_to,
    )


@router.get("/oidc/callback/{tenant_id}")
async def oidc_callback(
    tenant_id: str,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
) -> RedirectResponse:
    """OIDC callback endpoint."""
    app_url = get_app_url()

    # Handle error responses
    if error:
        logger.warning(
            "oidc_callback_error",
            tenant_id=tenant_id,
            error=error,
            description=error_description,
        )
        error_code = "sso_denied" if error == "access_denied" else "sso_error"
        return RedirectResponse(
            url=f"{app_url}/login?error={error_code}&message={error_description or error}",
            status_code=302,
        )

    # Get session
    session = get_sso_session(state) if state else None

    if not session:
        logger.warning("oidc_callback_no_session", tenant_id=tenant_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_session_expired",
            status_code=302,
        )

    config = get_or_create_sso_config(tenant_id)
    idp = config.get_idp_by_id(session.idp_id)

    if not idp:
        logger.error("oidc_callback_idp_not_found", tenant_id=tenant_id, idp_id=session.idp_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_config_error",
            status_code=302,
        )

    try:
        provider = OIDCProvider(idp, app_url)
        user_info = await provider.process_response(
            response_data={"code": code},
            session=session,
        )

        # Update IdP last login
        idp.last_login_at = datetime.utcnow()

        logger.info(
            "oidc_login_success",
            tenant_id=tenant_id,
            email=user_info.email,
        )

        # Build success redirect URL
        params = {
            "sso": "success",
            "email": user_info.email,
            "provider": "oidc",
            "idp": idp.slug,
        }

        return_url = session.relay_state or f"{app_url}/dashboard"
        separator = "&" if "?" in return_url else "?"

        return RedirectResponse(
            url=f"{return_url}{separator}{urlencode(params)}",
            status_code=302,
        )

    except Exception as e:
        logger.error("oidc_callback_error", error=str(e), tenant_id=tenant_id)
        return RedirectResponse(
            url=f"{app_url}/login?error=sso_validation_error&message={str(e)}",
            status_code=302,
        )


# --- Provider Preset Routes ---


@router.get("/presets")
async def list_presets() -> dict[str, Any]:
    """List available OIDC provider presets."""
    return {
        "presets": {
            name: {
                "name": name.replace("_", " ").title(),
                "issuer": preset.get("issuer"),
                "scopes": preset.get("scopes", ["openid", "email", "profile"]),
            }
            for name, preset in OIDC_PROVIDER_PRESETS.items()
        }
    }


@router.get("/presets/{preset_name}")
async def get_preset(preset_name: str) -> dict[str, Any]:
    """Get a specific OIDC provider preset configuration."""
    if preset_name not in OIDC_PROVIDER_PRESETS:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")

    preset = OIDC_PROVIDER_PRESETS[preset_name]

    # Add provider-specific setup instructions
    instructions = {
        "google": {
            "setup_url": "https://console.cloud.google.com/apis/credentials",
            "docs_url": "https://developers.google.com/identity/openid-connect/openid-connect",
            "required_scopes": ["openid", "email", "profile"],
        },
        "okta": {
            "setup_url": "https://developer.okta.com/docs/guides/sign-into-web-app-redirect",
            "issuer_format": "https://{your-okta-domain}",
            "required_scopes": ["openid", "email", "profile", "groups"],
        },
        "azure_ad": {
            "setup_url": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
            "docs_url": "https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-protocols-oidc",
            "issuer_format": "https://login.microsoftonline.com/{tenant-id}/v2.0",
        },
        "auth0": {
            "setup_url": "https://manage.auth0.com/",
            "docs_url": "https://auth0.com/docs/authenticate/protocols/openid-connect-protocol",
            "issuer_format": "https://{your-domain}.auth0.com",
        },
    }

    return {
        "name": preset_name,
        "config": preset,
        "instructions": instructions.get(preset_name, {}),
    }
