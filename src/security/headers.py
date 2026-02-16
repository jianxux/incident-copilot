"""Security headers middleware."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Add basic security headers to HTTP responses."""

    def __init__(self, app: ASGIApp, *, content_security_policy: str | None = None):
        self.app = app
        self.csp = content_security_policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])

                def add(name: str, value: str) -> None:
                    headers.append((name.encode("latin-1"), value.encode("latin-1")))

                add("X-Frame-Options", "DENY")
                add("X-Content-Type-Options", "nosniff")
                # Deprecated in modern browsers, but kept for defense-in-depth / scanners.
                add("X-XSS-Protection", "1; mode=block")
                add("Referrer-Policy", "strict-origin-when-cross-origin")

                # HSTS: only meaningful over HTTPS, but safe to emit (browsers ignore on HTTP).
                add(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )

                add(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=(), payment=()",
                )

                if self.csp:
                    add("Content-Security-Policy", self.csp)

            await send(message)

        await self.app(scope, receive, send_wrapper)
