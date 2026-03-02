"""Onboarding API routes and integration workflows."""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ...auth.middleware import AuthContext, get_auth_context
from ...config import get_settings
from ...integrations.slack_manifest import generate_manifest, generate_manifest_url
from .common import logger, router, tenant_slug_from_auth


@router.get("/integrations/slack/manifest")
async def slack_manifest():
    """Return the Slack App Manifest JSON for this deployment."""
    return generate_manifest(get_settings().app_url)


@router.get("/integrations/slack/install")
async def slack_install():
    """Redirect to Slack's app creation page with the manifest pre-filled."""
    return RedirectResponse(url=generate_manifest_url(get_settings().app_url))


class DashboardServiceCreateRequest(BaseModel):
    """Create request for onboarding wizard service list."""

    name: str = Field(min_length=1, max_length=120)


@router.get("/api/services")
async def dashboard_list_services(
    auth: AuthContext = Depends(get_auth_context),
):
    """List services for onboarding wizard via dashboard-scoped API."""
    from ...services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    services = await get_service_catalog_store().list_services(tenant_slug=tenant_slug)
    return {
        "services": [
            {
                "id": service.id,
                "name": service.name,
                "description": service.description,
                "team": service.team,
                "source": (service.metadata or {}).get("source", "manual"),
                "metadata": service.metadata or {},
                "created_at": service.created_at.isoformat() if service.created_at else None,
            }
            for service in services
        ]
    }


@router.post("/api/services", status_code=201)
async def dashboard_create_service(
    request: DashboardServiceCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create a service for onboarding wizard via dashboard-scoped API."""
    from ...onboarding import checklist_store
    from ...services.models import ServiceCreate
    from ...services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    tenant_id = auth.tenant_id or "default"
    service_name = request.name.strip()
    if not service_name:
        raise HTTPException(status_code=400, detail="service_name_required")

    service = await get_service_catalog_store().create_service(
        ServiceCreate(name=service_name, metadata={"source": "manual"}),
        tenant_slug=tenant_slug,
    )

    await checklist_store.set_step(tenant_id, "add_services", True)
    return {
        "id": service.id,
        "name": service.name,
        "source": (service.metadata or {}).get("source", "manual"),
        "metadata": service.metadata or {},
        "created_at": service.created_at.isoformat() if service.created_at else None,
    }


@router.delete("/api/services/{service_id}", status_code=204)
async def dashboard_delete_service(
    service_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Delete a service for onboarding wizard via dashboard-scoped API."""
    from ...onboarding import checklist_store
    from ...services.store import get_service_catalog_store

    tenant_slug = tenant_slug_from_auth(auth)
    tenant_id = auth.tenant_id or "default"
    store = get_service_catalog_store()

    deleted = await store.delete_service(service_id, tenant_slug=tenant_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="service_not_found")

    remaining = await store.list_services(tenant_slug=tenant_slug)
    await checklist_store.set_step(tenant_id, "add_services", bool(remaining))


@router.get("/api/onboarding/checklist")
async def get_onboarding_checklist(
    auth: AuthContext = Depends(get_auth_context),
):
    """Get current tenant onboarding checklist (auto-syncs from integrations)."""
    from ...onboarding import checklist_store

    tenant_id = auth.tenant_id or "default"

    # Auto-sync: check oauth_token_store + integration_configs and mark steps done
    providers: set[str] = set()
    try:
        from ...integrations.oauth_tokens import oauth_token_store

        for p in ("pagerduty", "slack", "github", "datadog"):
            tok = await oauth_token_store.get_token(tenant_id, p)
            if tok and tok.access_token:
                providers.add(p)
    except Exception:
        pass
    try:
        from ...db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = (
            db.client.table("integration_configs")
            .select("type")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        if rows.data:
            providers.update(r["type"] for r in rows.data if r.get("type"))
    except Exception:
        pass
    try:
        if "pagerduty" in providers or "opsgenie" in providers:
            await checklist_store.set_step(tenant_id, "connect_alerting", True)
        if "slack" in providers:
            await checklist_store.set_step(tenant_id, "connect_slack", True)
        if "github" in providers:
            await checklist_store.set_step(tenant_id, "connect_github", True)
        if "datadog" in providers:
            await checklist_store.set_step(tenant_id, "connect_datadog", True)
    except Exception as e:
        logger.warning(
            "onboarding_integration_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    # Also sync services
    try:
        from ...services.store import get_service_catalog_store

        store = get_service_catalog_store()
        tenant_slug = tenant_slug_from_auth(auth)
        services = await store.list_services(tenant_slug=tenant_slug)
        if services:
            await checklist_store.set_step(tenant_id, "add_services", True)
    except Exception as e:
        logger.warning(
            "onboarding_service_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    # Mark create_account done if authenticated
    if auth.user:
        await checklist_store.set_step(tenant_id, "create_account", True)

    checklist = await checklist_store.get(tenant_id)
    return checklist.to_dict()


@router.post("/api/onboarding/checklist/{step}")
async def set_onboarding_step(
    step: str,
    done: bool = True,
    auth: AuthContext = Depends(get_auth_context),
):
    """Mark an onboarding checklist step as done/undone."""
    from ...onboarding import checklist_store

    tenant_id = auth.tenant_id or "default"
    checklist = await checklist_store.set_step(tenant_id, step, done)
    return checklist.to_dict()


@router.get("/api/onboarding/status")
async def get_onboarding_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return a lightweight status for the wizard UI."""
    tenant_id = auth.tenant_id or "default"

    # Check in-memory tenant store first
    tenant = auth.tenant
    integrations = tenant.integrations if tenant else {}

    def connected(name: str) -> bool:
        v = integrations.get(name)
        if not v:
            return False
        return bool(v.get("encrypted") if isinstance(v, dict) else v)

    result = {
        "pagerduty": connected("pagerduty"),
        "slack": connected("slack"),
        "github": connected("github"),
        "datadog": connected("datadog"),
    }

    # Check oauth_token_store (new normalized store used by generic OAuth flow)
    details: dict[str, dict] = {}
    oauth_dates: dict[str, str] = {}  # track oauth_token_store dates (authoritative)
    try:
        from ...integrations.oauth_tokens import oauth_token_store

        for provider_name in result:
            token_rec = await oauth_token_store.get_token(tenant_id, provider_name)
            if token_rec and token_rec.access_token:
                result[provider_name] = True
                date_str = token_rec.created_at.isoformat() if token_rec.created_at else ""
                oauth_dates[provider_name] = date_str
                details[provider_name] = {
                    "scopes": token_rec.scopes,
                    "connected_at": date_str,
                }
    except Exception as e:
        logger.warning("oauth_token_store_check_failed", error=str(e))

    # Also check Supabase integration_configs for OAuth connections
    try:
        from ...db.supabase_db import get_db
        from ...security.crypto import decrypt_json

        db = get_db(use_admin=True)
        rows = (
            db.client.table("integration_configs")
            .select("type,config")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        if rows.data:
            for row in rows.data:
                provider = row.get("type")
                if provider and provider in result:
                    result[provider] = True
                    # Extract display info from encrypted config
                    try:
                        config = row.get("config", {})
                        encrypted = (
                            config.get("encrypted", "") if isinstance(config, dict) else ""
                        )
                        if encrypted:
                            decrypted = decrypt_json(encrypted)
                            oauth = decrypted.get("oauth", {})
                            team = oauth.get("team", {})
                            detail = {}
                            if team and isinstance(team, dict):
                                detail["workspace"] = team.get("name", "")
                            if decrypted.get("subdomain"):
                                detail["subdomain"] = decrypted["subdomain"]
                            if oauth.get("scope"):
                                detail["scopes"] = oauth["scope"]
                            # Prefer oauth_token_store date (updated on reconnect)
                            detail["connected_at"] = oauth_dates.get(
                                provider, decrypted.get("connected_at", "")
                            )
                            details[provider] = detail
                    except Exception:
                        details[provider] = {}
    except Exception as e:
        logger.warning(
            "onboarding_status_sync_failed",
            error=str(e),
            error_type=type(e).__name__,
            tenant_id=tenant_id,
        )

    # Load Slack channel preference
    try:
        from ...db.supabase_db import get_db as _get_db

        _db = _get_db(use_admin=True)
        slack_settings = (
            _db.client.table("integration_configs")
            .select("config")
            .eq("tenant_id", tenant_id)
            .eq("type", "slack_settings")
            .limit(1)
            .execute()
        )
        if slack_settings.data:
            cfg = slack_settings.data[0].get("config", {})
            if "slack" not in details:
                details["slack"] = {}
            details["slack"]["incidents_channel"] = cfg.get("incidents_channel", "#incidents")
    except Exception:
        pass

    return {
        "authenticated": True,
        "tenant": {"id": tenant_id},
        "integrations": result,
        "details": details,
    }


@router.post("/api/onboarding/integrations/slack/channel")
async def save_slack_channel(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Save the Slack incidents channel preference for the tenant."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    channel = (body.get("channel") or "#incidents").strip()

    try:
        from ...db.supabase_db import get_db

        db = get_db(use_admin=True)
        # Store channel preference in integration_configs as type=slack_settings
        existing = (
            db.client.table("integration_configs")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("type", "slack_settings")
            .limit(1)
            .execute()
        )
        row = {
            "tenant_id": tenant_id,
            "type": "slack_settings",
            "config": {"incidents_channel": channel},
            "is_active": True,
        }
        if existing.data:
            (
                db.client.table("integration_configs")
                .update(row)
                .eq("tenant_id", tenant_id)
                .eq("type", "slack_settings")
                .execute()
            )
        else:
            db.client.table("integration_configs").insert(row).execute()
        return {"ok": True, "channel": channel}
    except Exception as e:
        logger.warning("save_slack_channel_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/onboarding/test-integration/{provider}")
async def test_integration(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Test an integration connection by making a lightweight API call."""
    tenant_id = auth.tenant_id or "default"

    try:
        from ...security.crypto import decrypt_json

        # Check integration_tokens first (generic OAuth flow), then integration_configs (legacy)
        oauth = {}
        decrypted = {}

        from ...integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, provider)
        if token_rec:
            oauth = {"access_token": token_rec.access_token}
            decrypted = {"oauth": oauth}
        else:
            rows = None
            try:
                from ...db.supabase_db import get_db

                db = get_db(use_admin=True)
                rows = (
                    db.client.table("integration_configs")
                    .select("config")
                    .eq("tenant_id", tenant_id)
                    .eq("type", provider)
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )
            except Exception as exc:
                logger.warning(
                    "integration_config_lookup_failed", provider=provider, error=str(exc)
                )

            if rows and rows.data:
                config = rows.data[0].get("config", {})
                encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                if encrypted:
                    decrypted = decrypt_json(encrypted)
                oauth = decrypted.get("oauth", {})
            elif provider != "pagerduty":
                raise HTTPException(status_code=404, detail=f"{provider} not connected")

        if provider == "pagerduty":
            import httpx

            oauth_token = oauth.get("access_token", "")
            api_key = decrypted.get("api_key", "")
            subdomain = decrypted.get("subdomain")

            def _legacy_scopes() -> list[str]:
                raw = oauth.get("scope")
                if isinstance(raw, str):
                    return [
                        s.strip()
                        for s in raw.replace(",", " ").split(" ")
                        if s.strip()
                    ]
                if isinstance(raw, list):
                    return [str(s).strip() for s in raw if str(s).strip()]
                return []

            details = {
                "subdomain": subdomain,
                "scopes": token_rec.scopes if token_rec else _legacy_scopes(),
                "connected_at": decrypted.get("connected_at")
                or (token_rec.created_at.isoformat() if token_rec else None),
            }

            async def _fetch_pd_subdomain(access_token: str) -> str | None:
                """Fetch PagerDuty account subdomain via /services (we have services_read scope)."""
                try:
                    async with httpx.AsyncClient(timeout=10) as hc:
                        resp = await hc.get(
                            "https://api.pagerduty.com/services?limit=1",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/vnd.pagerduty+json;version=2",
                            },
                        )
                        if resp.status_code == 200:
                            services = resp.json().get("services", [])
                            if services:
                                html_url = services[0].get("html_url", "")
                                # html_url: https://acme.pagerduty.com/services/PXXXXXX
                                if "pagerduty.com" in html_url:
                                    from urllib.parse import urlparse

                                    host = urlparse(html_url).hostname or ""
                                    sub = host.replace(".pagerduty.com", "")
                                    if sub and sub != "app":
                                        return sub
                        else:
                            logger.warning(
                                "pagerduty_services_status",
                                status=resp.status_code,
                                body=resp.text[:200],
                            )
                except Exception as exc:
                    logger.warning("pagerduty_subdomain_fetch_failed", error=str(exc))
                return None

            # Prefer normalized OAuth token store record.
            if token_rec and token_rec.access_token:
                now = datetime.now(UTC)
                if not token_rec.token_expiry or token_rec.token_expiry > now:
                    if not details.get("subdomain"):
                        details["subdomain"] = await _fetch_pd_subdomain(
                            token_rec.access_token
                        )
                    return {"ok": True, "details": details}

                # Expired token: attempt refresh.
                from ...integrations.oauth_providers import get_provider_credentials

                if not token_rec.refresh_token:
                    return {
                        "ok": False,
                        "details": "PagerDuty token is expired and refresh failed",
                    }

                client_id, client_secret = get_provider_credentials("pagerduty")
                if not client_id or not client_secret:
                    return {
                        "ok": False,
                        "details": "PagerDuty token is expired and refresh failed",
                    }

                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        refresh_resp = await client.post(
                            "https://identity.pagerduty.com/oauth/token",
                            data={
                                "grant_type": "refresh_token",
                                "refresh_token": token_rec.refresh_token,
                                "client_id": client_id,
                                "client_secret": client_secret,
                            },
                            headers={"Accept": "application/json"},
                        )
                except Exception as exc:
                    logger.warning("pagerduty_refresh_error", error=str(exc))
                    return {
                        "ok": False,
                        "details": "PagerDuty token is expired and refresh failed",
                    }

                if refresh_resp.status_code != 200:
                    return {
                        "ok": False,
                        "details": "PagerDuty token is expired and refresh failed",
                    }

                new_tokens = refresh_resp.json()
                new_access_token = new_tokens.get("access_token", "")
                if not new_access_token:
                    return {
                        "ok": False,
                        "details": "PagerDuty token is expired and refresh failed",
                    }

                new_expiry = None
                try:
                    expires_in = new_tokens.get("expires_in")
                    expires_in_value = int(expires_in) if expires_in is not None else None
                except (TypeError, ValueError):
                    expires_in_value = None
                if expires_in_value and expires_in_value > 0:
                    new_expiry = datetime.now(UTC) + timedelta(seconds=expires_in_value)

                new_scope = new_tokens.get("scope")
                if isinstance(new_scope, str):
                    new_scopes = [
                        s.strip()
                        for s in new_scope.replace(",", " ").split(" ")
                        if s.strip()
                    ]
                else:
                    new_scopes = token_rec.scopes

                updated = await oauth_token_store.upsert_token(
                    tenant_id=tenant_id,
                    provider="pagerduty",
                    access_token=new_access_token,
                    refresh_token=new_tokens.get("refresh_token", token_rec.refresh_token),
                    token_expiry=new_expiry,
                    scopes=new_scopes,
                )
                details["scopes"] = updated.scopes
                details["refreshed_at"] = datetime.now(UTC).isoformat()
                return {"ok": True, "details": details}

            # Legacy config path: accept configured OAuth/API key as connected.
            if oauth_token or api_key:
                return {"ok": True, "details": details}

            return {"ok": False, "details": "PagerDuty is not connected"}

        elif provider == "slack":
            import httpx

            token = oauth.get("access_token", "")
            team = oauth.get("team", {})
            team_name = team.get("name", "unknown") if isinstance(team, dict) else "unknown"
            if not token:
                return {"ok": True, "details": f"Connected to {team_name} (no token to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if data.get("ok"):
                return {
                    "ok": True,
                    "details": f"Slack - {data.get('team', team_name)} as {data.get('user', 'bot')}",
                }
            return {
                "ok": False,
                "details": f"Slack auth.test failed: {data.get('error', 'unknown')}",
            }

        elif provider == "github":
            import httpx

            token = decrypted.get("token") or oauth.get("access_token", "")
            if not token:
                return {"ok": True, "details": "GitHub connected (no token to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
            if resp.status_code == 200:
                user = resp.json()
                return {
                    "ok": True,
                    "details": f"GitHub - authenticated as {user.get('login', 'unknown')}",
                }
            return {"ok": False, "details": f"GitHub API returned {resp.status_code}"}

        elif provider == "datadog":
            import httpx

            api_key = decrypted.get("api_key", "")
            app_key = decrypted.get("app_key", "")
            if not api_key:
                return {"ok": True, "details": "Datadog connected (no key to verify)"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.datadoghq.com/api/v1/validate",
                    headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
                )
            if resp.status_code == 200:
                return {"ok": True, "details": "Datadog - API key valid"}
            return {"ok": False, "details": f"Datadog returned {resp.status_code}"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("test_integration_failed", provider=provider, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/onboarding/integrations/pagerduty/import-services")
async def import_pagerduty_services(
    auth: AuthContext = Depends(get_auth_context),
):
    """Import services from the connected PagerDuty account."""
    tenant_id = auth.tenant_id or "default"

    try:
        # Try oauth_token_store first (new normalized store), then legacy integration_configs
        from ...integrations.oauth_tokens import oauth_token_store

        token_rec = await oauth_token_store.get_token(tenant_id, "pagerduty")
        oauth_token = ""
        api_key = ""

        if token_rec and token_rec.access_token:
            oauth_token = token_rec.access_token
        else:
            try:
                from ...db.supabase_db import get_db
                from ...security.crypto import decrypt_json

                db = get_db(use_admin=True)
                rows = (
                    db.client.table("integration_configs")
                    .select("config")
                    .eq("tenant_id", tenant_id)
                    .eq("type", "pagerduty")
                    .eq("is_active", True)
                    .limit(1)
                    .execute()
                )

                if rows.data:
                    config = rows.data[0].get("config", {})
                    encrypted = config.get("encrypted", "") if isinstance(config, dict) else ""
                    if encrypted:
                        decrypted = decrypt_json(encrypted)
                        oauth = decrypted.get("oauth", {})
                        oauth_token = oauth.get("access_token", "")
                        api_key = decrypted.get("api_key", "")
            except Exception as exc:
                logger.warning("import_services_legacy_lookup_failed", error=str(exc))

        token = oauth_token or api_key
        if not token:
            raise HTTPException(status_code=404, detail="PagerDuty not connected")

        # PagerDuty uses "Bearer" for OAuth tokens, "Token token=" for API keys
        if oauth_token:
            pd_auth = f"Bearer {oauth_token}"
        else:
            pd_auth = f"Token token={api_key}"

        # Fetch services from PagerDuty API
        import httpx

        imported = 0
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pagerduty.com/services",
                headers={
                    "Authorization": pd_auth,
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.pagerduty+json;version=2",
                },
                params={"limit": 100},
            )
            if resp.status_code != 200:
                logger.warning(
                    "import_pd_services_api_error",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
                return {
                    "ok": False,
                    "error": f"PagerDuty API returned {resp.status_code}",
                    "details": resp.text[:200],
                }

            pd_services = resp.json().get("services", [])

        # Import into service catalog
        from ...services.models import ServiceCreate, ServiceCriticality
        from ...services.store import get_service_catalog_store

        store = get_service_catalog_store()
        tenant_slug = tenant_slug_from_auth(auth)

        for pd_svc in pd_services:
            name = pd_svc.get("name", "").strip()
            if not name:
                continue
            req = ServiceCreate(
                name=name,
                description=pd_svc.get("description") or f"Imported from PagerDuty",
                team=pd_svc.get("teams", [{}])[0].get("summary")
                if pd_svc.get("teams")
                else None,
                criticality=ServiceCriticality.CRITICAL
                if pd_svc.get("alert_creation") == "create_alerts_and_incidents"
                else ServiceCriticality.MEDIUM,
                metadata={
                    "source": "pagerduty",
                    "pagerduty_id": pd_svc.get("id"),
                    "pagerduty_url": pd_svc.get("html_url"),
                },
            )
            await store.create_service(req, tenant_slug=tenant_slug)
            imported += 1

        # Mark onboarding step done
        from ...onboarding import checklist_store

        await checklist_store.set_step(tenant_id, "add_services", True)

        return {"ok": True, "imported": imported, "total_pd_services": len(pd_services)}

    except HTTPException as he:
        logger.warning(
            "import_pagerduty_services_http_error", status=he.status_code, detail=he.detail
        )
        return {"ok": False, "error": he.detail}
    except Exception as exc:
        logger.warning(
            "import_pagerduty_services_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"ok": False, "error": str(exc)}


@router.post("/api/onboarding/integrations/github")
async def save_github_integration(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Save GitHub PAT and org for deploy and repo context."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    token_val = body.get("token", "").strip()
    org = body.get("org", "").strip()

    if not token_val:
        raise HTTPException(status_code=400, detail="GitHub token is required")

    try:
        from ...db.supabase_db import get_db
        from ...security.crypto import encrypt_json

        db = get_db(use_admin=True)
        encrypted = encrypt_json({"token": token_val, "org": org})
        (
            db.client.table("integration_configs")
            .upsert(
                {
                    "tenant_id": tenant_id,
                    "type": "github",
                    "config": {"encrypted": encrypted},
                    "is_active": True,
                },
                on_conflict="tenant_id,type",
            )
            .execute()
        )

        from ...onboarding import checklist_store

        await checklist_store.set_step(tenant_id, "connect_github", True)

        return {"ok": True, "provider": "github"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("save_github_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/onboarding/integrations/datadog")
async def save_datadog_integration(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Save Datadog API/App keys."""
    tenant_id = auth.tenant_id or "default"
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    app_key = body.get("app_key", "").strip()
    site = body.get("site", "datadoghq.com").strip()

    if not api_key:
        raise HTTPException(status_code=400, detail="Datadog API key is required")

    try:
        from ...db.supabase_db import get_db
        from ...security.crypto import encrypt_json

        db = get_db(use_admin=True)
        encrypted = encrypt_json({"api_key": api_key, "app_key": app_key, "site": site})
        (
            db.client.table("integration_configs")
            .upsert(
                {
                    "tenant_id": tenant_id,
                    "type": "datadog",
                    "config": {"encrypted": encrypted},
                    "is_active": True,
                },
                on_conflict="tenant_id,type",
            )
            .execute()
        )

        from ...onboarding import checklist_store

        await checklist_store.set_step(tenant_id, "connect_datadog", True)

        return {"ok": True, "provider": "datadog"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("save_datadog_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/onboarding/test-incident/{incident_id}")
async def get_test_incident_status(
    incident_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Poll for test incident processing status.

    Checks both the Supabase DB directly and the in-memory incident store
    to handle cases where one persistence layer succeeded but the other didn't.
    """
    resolved_status = "processing"
    resolved_title = None
    resolved_verdict = None

    # 1. Try Supabase DB directly
    try:
        from ...db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = (
            db.client.table("incidents")
            .select("id,status,title,verdict")
            .eq("id", incident_id)
            .limit(1)
            .execute()
        )

        if rows.data:
            incident = rows.data[0]
            db_status = (incident.get("status") or "").lower()
            resolved_title = incident.get("title")
            resolved_verdict = incident.get("verdict")
            if db_status in ("completed", "resolved"):
                resolved_status = "completed"
            elif db_status == "error":
                resolved_status = "error"
    except Exception:
        pass

    # 2. Also check the incident_store (covers in-memory fallback)
    if resolved_status == "processing":
        try:
            from ...web.store import incident_store

            stored = await incident_store.get_incident(incident_id)
            if stored:
                resolved_title = resolved_title or stored.title
                if stored.status == "completed":
                    resolved_status = "completed"
                elif stored.status == "error":
                    resolved_status = "error"
        except Exception:
            pass

    return {
        "incident_id": incident_id,
        "status": resolved_status,
        "title": resolved_title,
        "verdict": resolved_verdict,
    }


@router.post("/api/onboarding/disconnect/{provider}")
async def disconnect_integration(
    provider: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Disconnect an OAuth integration."""
    tenant_id = auth.tenant_id or "default"
    try:
        # Remove from oauth_token_store
        try:
            from ...integrations.oauth_tokens import oauth_token_store

            await oauth_token_store.delete_token(tenant_id, provider)
        except Exception:
            pass  # store may not have this token

        # Remove from legacy integration_configs
        try:
            from ...db.supabase_db import get_db

            db = get_db(use_admin=True)
            (
                db.client.table("integration_configs")
                .delete()
                .eq("tenant_id", tenant_id)
                .eq("type", provider)
                .execute()
            )
        except Exception:
            pass

        return {"ok": True, "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/onboarding/test-incident")
async def run_onboarding_test_incident(
    service_name: str = "payments-api",
    auth: AuthContext = Depends(get_auth_context),
):
    """Start a synthetic incident to validate the pipeline."""
    from ...models import Severity
    from ...onboarding.test_incident import start_test_incident

    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_required",
        )
    tenant_id = auth.tenant_id

    incident_id = await start_test_incident(
        service_name=service_name,
        severity=Severity.HIGH,
        tenant_id=tenant_id,
    )

    return {"incident_id": incident_id, "status": "processing"}
