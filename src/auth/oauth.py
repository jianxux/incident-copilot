"""OAuth providers for authentication."""

import secrets
from abc import ABC, abstractmethod
from urllib.parse import urlencode

import httpx
import structlog

from ..config import get_settings

logger = structlog.get_logger()


class OAuthUser:
    """User info from OAuth provider."""

    def __init__(
        self,
        provider: str,
        id: str,
        email: str,
        name: str,
        avatar_url: str | None = None,
    ):
        self.provider = provider
        self.id = id
        self.email = email
        self.name = name
        self.avatar_url = avatar_url


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'github', 'google')."""
        pass

    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Get the URL to redirect users to for authorization."""
        pass

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> str | None:
        """Exchange authorization code for access token."""
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUser | None:
        """Get user info using access token."""
        pass

    @classmethod
    def generate_state(cls) -> str:
        """Generate a random state parameter for OAuth."""
        return secrets.token_urlsafe(32)


class GitHubOAuth(OAuthProvider):
    """GitHub OAuth provider."""

    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(self, client_id: str = None, client_secret: str = None):
        settings = get_settings()
        self.client_id = client_id or settings.github_oauth_client_id
        self.client_secret = client_secret or settings.github_oauth_client_secret

    @property
    def name(self) -> str:
        return "github"

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str | None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                logger.error(
                    "github_oauth_token_error",
                    status=response.status_code,
                    body=response.text,
                )
                return None

            data = response.json()
            return data.get("access_token")

    async def get_user_info(self, access_token: str) -> OAuthUser | None:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            # Get user profile
            user_response = await client.get(self.USER_URL, headers=headers)
            if user_response.status_code != 200:
                logger.error(
                    "github_oauth_user_error",
                    status=user_response.status_code,
                )
                return None

            user_data = user_response.json()

            # Get primary email if not public
            email = user_data.get("email")
            if not email:
                emails_response = await client.get(self.EMAILS_URL, headers=headers)
                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    primary = next(
                        (e for e in emails if e.get("primary") and e.get("verified")),
                        None,
                    )
                    if primary:
                        email = primary["email"]

            if not email:
                logger.error("github_oauth_no_email")
                return None

            return OAuthUser(
                provider="github",
                id=str(user_data["id"]),
                email=email,
                name=user_data.get("name") or user_data.get("login"),
                avatar_url=user_data.get("avatar_url"),
            )


class GoogleOAuth(OAuthProvider):
    """Google OAuth provider."""

    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, client_id: str = None, client_secret: str = None):
        settings = get_settings()
        self.client_id = client_id or settings.google_oauth_client_id
        self.client_secret = client_secret or settings.google_oauth_client_secret

    @property
    def name(self) -> str:
        return "google"

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str | None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

            if response.status_code != 200:
                logger.error(
                    "google_oauth_token_error",
                    status=response.status_code,
                    body=response.text,
                )
                return None

            data = response.json()
            return data.get("access_token")

    async def get_user_info(self, access_token: str) -> OAuthUser | None:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(self.USER_URL, headers=headers)

            if response.status_code != 200:
                logger.error(
                    "google_oauth_user_error",
                    status=response.status_code,
                )
                return None

            data = response.json()

            email = data.get("email")
            if not email:
                logger.error("google_oauth_no_email")
                return None

            return OAuthUser(
                provider="google",
                id=data["id"],
                email=email,
                name=data.get("name") or email.split("@")[0],
                avatar_url=data.get("picture"),
            )


# Provider registry
_providers: dict[str, OAuthProvider] = {}


def get_oauth_provider(name: str) -> OAuthProvider | None:
    """Get an OAuth provider by name."""
    if name not in _providers:
        if name == "github":
            _providers[name] = GitHubOAuth()
        elif name == "google":
            _providers[name] = GoogleOAuth()

    provider = _providers.get(name)
    if provider and provider.is_configured:
        return provider
    return None


def get_available_providers() -> list[str]:
    """Get list of configured OAuth providers."""
    providers = []

    github = GitHubOAuth()
    if github.is_configured:
        providers.append("github")

    google = GoogleOAuth()
    if google.is_configured:
        providers.append("google")

    return providers
