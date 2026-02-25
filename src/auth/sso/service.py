"""SSO service layer for managing identity providers and user provisioning."""

from datetime import datetime, UTC
from typing import Any

import structlog

from src.auth.models import UserRole
from src.auth.service import auth_service

from .models import (
    OIDC_PROVIDER_PRESETS,
    IdentityProvider,
    IdentityProviderType,
    OIDCSettings,
    SAMLSettings,
    SSOConfig,
    SSOUserInfo,
)
from .oidc import OIDCProvider
from .saml import SAMLProvider

logger = structlog.get_logger()


class SSOService:
    """Service for managing SSO configuration and user provisioning.

    Provides:
    - Identity provider CRUD operations
    - JIT (Just-In-Time) user provisioning
    - SSO attribute mapping
    - Tenant-specific SSO configuration
    """

    def __init__(self):
        """Initialize the SSO service."""
        # In-memory storage (replace with database in production)
        self._configs: dict[str, SSOConfig] = {}

    # --- Configuration Management ---

    async def get_config(self, tenant_id: str) -> SSOConfig | None:
        """Get SSO configuration for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            SSO configuration or None if not found
        """
        return self._configs.get(tenant_id)

    async def get_or_create_config(self, tenant_id: str) -> SSOConfig:
        """Get or create SSO configuration for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            SSO configuration (existing or newly created)
        """
        if tenant_id not in self._configs:
            self._configs[tenant_id] = SSOConfig(tenant_id=tenant_id)
            logger.info("sso_config_created", tenant_id=tenant_id)

        return self._configs[tenant_id]

    async def update_config(
        self,
        tenant_id: str,
        sso_enabled: bool | None = None,
        sso_required: bool | None = None,
        jit_provisioning_enabled: bool | None = None,
        jit_default_role: str | None = None,
        session_lifetime_hours: int | None = None,
    ) -> SSOConfig:
        """Update SSO configuration for a tenant.

        Args:
            tenant_id: Tenant ID
            sso_enabled: Whether SSO is enabled
            sso_required: Whether SSO is required (no password login)
            jit_provisioning_enabled: Whether JIT provisioning is enabled
            jit_default_role: Default role for JIT-provisioned users
            session_lifetime_hours: Session lifetime in hours

        Returns:
            Updated SSO configuration
        """
        config = await self.get_or_create_config(tenant_id)

        if sso_enabled is not None:
            # Validate before enabling
            if sso_enabled and not config.identity_providers:
                raise ValueError("Cannot enable SSO without identity providers")
            config.sso_enabled = sso_enabled

        if sso_required is not None:
            config.sso_required = sso_required

        if jit_provisioning_enabled is not None:
            config.jit_provisioning_enabled = jit_provisioning_enabled

        if jit_default_role is not None:
            config.jit_default_role = jit_default_role

        if session_lifetime_hours is not None:
            config.session_lifetime_hours = session_lifetime_hours

        config.updated_at = datetime.now(UTC)

        logger.info(
            "sso_config_updated",
            tenant_id=tenant_id,
            sso_enabled=config.sso_enabled,
        )

        return config

    async def delete_config(self, tenant_id: str) -> bool:
        """Delete SSO configuration for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if deleted, False if not found
        """
        if tenant_id in self._configs:
            del self._configs[tenant_id]
            logger.info("sso_config_deleted", tenant_id=tenant_id)
            return True
        return False

    # --- Identity Provider Management ---

    async def list_identity_providers(
        self,
        tenant_id: str,
        active_only: bool = False,
    ) -> list[IdentityProvider]:
        """List identity providers for a tenant.

        Args:
            tenant_id: Tenant ID
            active_only: Whether to only return active providers

        Returns:
            List of identity providers
        """
        config = await self.get_or_create_config(tenant_id)

        if active_only:
            return [idp for idp in config.identity_providers if idp.is_active]

        return config.identity_providers

    async def get_identity_provider(
        self,
        tenant_id: str,
        idp_id: str | None = None,
        slug: str | None = None,
    ) -> IdentityProvider | None:
        """Get an identity provider by ID or slug.

        Args:
            tenant_id: Tenant ID
            idp_id: Identity provider ID
            slug: Identity provider slug

        Returns:
            Identity provider or None if not found
        """
        config = await self.get_or_create_config(tenant_id)

        if idp_id:
            return config.get_idp_by_id(idp_id)
        elif slug:
            return config.get_idp_by_slug(slug)

        return None

    async def create_identity_provider(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        provider_type: IdentityProviderType,
        saml_settings: SAMLSettings | None = None,
        oidc_settings: OIDCSettings | None = None,
        email_domains: list[str] | None = None,
        role_mapping: dict[str, str] | None = None,
        is_default: bool = False,
        is_active: bool = True,
    ) -> IdentityProvider:
        """Create a new identity provider.

        Args:
            tenant_id: Tenant ID
            name: Human-friendly name
            slug: URL-safe identifier
            provider_type: SAML or OIDC
            saml_settings: SAML configuration (required for SAML)
            oidc_settings: OIDC configuration (required for OIDC)
            email_domains: Email domains for automatic IdP selection
            role_mapping: IdP group/role to local role mapping
            is_default: Whether this is the default IdP
            is_active: Whether this IdP is active

        Returns:
            Newly created identity provider

        Raises:
            ValueError: If settings don't match provider type
        """
        config = await self.get_or_create_config(tenant_id)

        # Validate slug uniqueness
        if config.get_idp_by_slug(slug):
            raise ValueError(f"Identity provider with slug '{slug}' already exists")

        # Validate settings
        if provider_type == IdentityProviderType.SAML and not saml_settings:
            raise ValueError("SAML settings required for SAML provider")

        if provider_type == IdentityProviderType.OIDC and not oidc_settings:
            raise ValueError("OIDC settings required for OIDC provider")

        # If making this default, remove default from others
        if is_default:
            for idp in config.identity_providers:
                idp.is_default = False

        idp = IdentityProvider(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            provider_type=provider_type,
            saml_settings=saml_settings,
            oidc_settings=oidc_settings,
            email_domains=email_domains or [],
            role_mapping=role_mapping or {},
            is_default=is_default,
            is_active=is_active,
        )

        config.identity_providers.append(idp)
        config.updated_at = datetime.now(UTC)

        logger.info(
            "idp_created",
            tenant_id=tenant_id,
            idp_id=idp.id,
            provider_type=provider_type.value,
            name=name,
        )

        return idp

    async def create_oidc_provider_from_preset(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        preset: str,
        client_id: str,
        client_secret: str,
        issuer: str | None = None,
        email_domains: list[str] | None = None,
        is_default: bool = False,
    ) -> IdentityProvider:
        """Create an OIDC provider using a preset configuration.

        Args:
            tenant_id: Tenant ID
            name: Human-friendly name
            slug: URL-safe identifier
            preset: Preset name (google, okta, azure_ad, auth0)
            client_id: OAuth client ID
            client_secret: OAuth client secret
            issuer: OIDC issuer URL (required for some presets)
            email_domains: Email domains for automatic IdP selection
            is_default: Whether this is the default IdP

        Returns:
            Newly created identity provider
        """
        if preset not in OIDC_PROVIDER_PRESETS:
            raise ValueError(f"Unknown preset: {preset}")

        preset_config = OIDC_PROVIDER_PRESETS[preset].copy()

        # Some presets require issuer
        if not preset_config.get("issuer") and not issuer:
            raise ValueError(f"Issuer URL required for preset: {preset}")

        oidc_settings = OIDCSettings(
            issuer=issuer or preset_config.get("issuer"),
            client_id=client_id,
            client_secret=client_secret,
            scopes=preset_config.get("scopes", ["openid", "email", "profile"]),
            claim_mapping=preset_config.get("claim_mapping", {}),
            provider_type=preset,
        )

        return await self.create_identity_provider(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            provider_type=IdentityProviderType.OIDC,
            oidc_settings=oidc_settings,
            email_domains=email_domains,
            is_default=is_default,
        )

    async def update_identity_provider(
        self,
        tenant_id: str,
        idp_id: str,
        name: str | None = None,
        email_domains: list[str] | None = None,
        role_mapping: dict[str, str] | None = None,
        is_default: bool | None = None,
        is_active: bool | None = None,
    ) -> IdentityProvider:
        """Update an identity provider.

        Args:
            tenant_id: Tenant ID
            idp_id: Identity provider ID
            name: New name
            email_domains: New email domains
            role_mapping: New role mapping
            is_default: Set as default
            is_active: Set active status

        Returns:
            Updated identity provider
        """
        config = await self.get_or_create_config(tenant_id)
        idp = config.get_idp_by_id(idp_id)

        if not idp:
            raise ValueError(f"Identity provider {idp_id} not found")

        if name is not None:
            idp.name = name

        if email_domains is not None:
            idp.email_domains = email_domains

        if role_mapping is not None:
            idp.role_mapping = role_mapping

        if is_default is not None:
            if is_default:
                # Remove default from others
                for other in config.identity_providers:
                    other.is_default = False
            idp.is_default = is_default

        if is_active is not None:
            idp.is_active = is_active

        idp.updated_at = datetime.now(UTC)
        config.updated_at = datetime.now(UTC)

        logger.info(
            "idp_updated",
            tenant_id=tenant_id,
            idp_id=idp_id,
        )

        return idp

    async def delete_identity_provider(
        self,
        tenant_id: str,
        idp_id: str,
    ) -> bool:
        """Delete an identity provider.

        Args:
            tenant_id: Tenant ID
            idp_id: Identity provider ID

        Returns:
            True if deleted, False if not found
        """
        config = await self.get_or_create_config(tenant_id)

        idp = config.get_idp_by_id(idp_id)
        if not idp:
            return False

        config.identity_providers = [
            p for p in config.identity_providers if p.id != idp_id
        ]
        config.updated_at = datetime.now(UTC)

        # Disable SSO if no providers left
        if not config.identity_providers:
            config.sso_enabled = False

        logger.info(
            "idp_deleted",
            tenant_id=tenant_id,
            idp_id=idp_id,
        )

        return True

    # --- User Provisioning ---

    async def provision_user(
        self,
        tenant_id: str,
        user_info: SSOUserInfo,
        idp: IdentityProvider,
    ) -> tuple[Any, bool]:
        """Provision a user from SSO (JIT provisioning).

        Args:
            tenant_id: Tenant ID
            user_info: User information from SSO
            idp: Identity provider used for authentication

        Returns:
            Tuple of (user, is_new) where is_new indicates if user was created
        """
        config = await self.get_or_create_config(tenant_id)

        # Check if user exists
        existing_user = await auth_service.get_user_by_email(user_info.email)

        if existing_user:
            # Update existing user with SSO info
            existing_user.last_login = datetime.now(UTC)

            # Optionally update name/avatar from SSO
            if user_info.name and not existing_user.name:
                existing_user.name = user_info.name

            if user_info.avatar_url:
                existing_user.avatar_url = user_info.avatar_url

            logger.info(
                "sso_user_login",
                user_id=existing_user.id,
                email=user_info.email,
                idp_id=idp.id,
            )

            return existing_user, False

        # JIT provisioning
        if not config.jit_provisioning_enabled:
            raise ValueError(
                f"User {user_info.email} not found and JIT provisioning is disabled"
            )

        # Determine role from SSO groups
        role = self._map_sso_role(user_info, idp, config.jit_default_role)

        # Create user
        user = await auth_service.create_user(
            email=user_info.email,
            name=user_info.display_name,
            tenant_id=tenant_id,
            role=role,
            oauth_provider=f"sso:{idp.provider_type.value}",
            oauth_id=user_info.subject_id,
        )

        if user_info.avatar_url:
            user.avatar_url = user_info.avatar_url

        logger.info(
            "sso_user_provisioned",
            user_id=user.id,
            email=user_info.email,
            idp_id=idp.id,
            role=role.value,
        )

        return user, True

    def _map_sso_role(
        self,
        user_info: SSOUserInfo,
        idp: IdentityProvider,
        default_role: str,
    ) -> UserRole:
        """Map SSO groups to a local role.

        Args:
            user_info: User information with groups
            idp: Identity provider with role mapping
            default_role: Default role if no mapping matches

        Returns:
            Mapped user role
        """
        # Check role mapping
        if idp.role_mapping and user_info.groups:
            for group in user_info.groups:
                if group in idp.role_mapping:
                    role_name = idp.role_mapping[group]
                    try:
                        return UserRole(role_name)
                    except ValueError:
                        logger.warning(
                            "invalid_role_mapping",
                            group=group,
                            mapped_role=role_name,
                        )

        # Return default role
        try:
            return UserRole(default_role)
        except ValueError:
            return UserRole.MEMBER

    # --- SSO Helpers ---

    async def find_idp_for_email(
        self,
        email: str,
    ) -> tuple[SSOConfig, IdentityProvider] | None:
        """Find the SSO configuration and IdP for an email address.

        Args:
            email: User email address

        Returns:
            Tuple of (config, idp) or None if not found
        """
        for config in self._configs.values():
            if not config.sso_enabled:
                continue

            idp = config.get_idp_for_email(email)
            if idp:
                return config, idp

        return None

    async def get_provider(
        self,
        idp: IdentityProvider,
        app_url: str,
    ) -> SAMLProvider | OIDCProvider:
        """Get the appropriate provider instance for an IdP.

        Args:
            idp: Identity provider
            app_url: Application base URL

        Returns:
            Provider instance (SAMLProvider or OIDCProvider)
        """
        if idp.provider_type == IdentityProviderType.SAML:
            return SAMLProvider(idp, app_url)
        else:
            return OIDCProvider(idp, app_url)


# Global SSO service instance
sso_service = SSOService()
