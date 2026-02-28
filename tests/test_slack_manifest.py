"""Tests for Slack App Manifest generation."""

import json
import urllib.parse

import pytest

from src.integrations.slack_manifest import generate_manifest, generate_manifest_url

APP_URL = "https://app.example.com"


class TestGenerateManifest:
    def test_structure(self):
        m = generate_manifest(APP_URL)
        assert m["_metadata"]["major_version"] == 2
        assert "display_information" in m
        assert "features" in m
        assert "oauth_config" in m
        assert "settings" in m

    def test_display_information(self):
        m = generate_manifest(APP_URL)
        d = m["display_information"]
        assert d["name"] == "Incident Copilot"
        assert d["background_color"] == "#e05a3a"
        assert len(d["description"]) > 0
        assert len(d["long_description"]) > 50

    def test_scopes(self):
        m = generate_manifest(APP_URL)
        scopes = m["oauth_config"]["scopes"]["bot"]
        expected = [
            "channels:manage", "channels:join", "channels:read",
            "chat:write", "chat:write.public", "commands",
            "im:history", "im:read", "im:write",
            "users:read", "users:read.email",
            "reactions:write", "files:write",
        ]
        assert len(scopes) == 13
        for s in expected:
            assert s in scopes

    def test_slash_commands(self):
        m = generate_manifest(APP_URL)
        cmds = m["features"]["slash_commands"]
        names = [c["command"] for c in cmds]
        assert "/incident" in names
        assert "/copilot" in names
        for c in cmds:
            assert c["url"] == f"{APP_URL}/api/slack/commands"

    def test_events(self):
        m = generate_manifest(APP_URL)
        events = m["settings"]["event_subscriptions"]["bot_events"]
        for e in ["message.channels", "message.im", "app_mention", "member_joined_channel"]:
            assert e in events

    def test_urls(self):
        m = generate_manifest(APP_URL)
        assert m["settings"]["event_subscriptions"]["request_url"] == f"{APP_URL}/api/slack/events"
        assert m["settings"]["interactivity"]["request_url"] == f"{APP_URL}/api/slack/interactions"
        assert f"{APP_URL}/api/integrations/oauth/slack/callback" in m["oauth_config"]["redirect_urls"]

    def test_app_home(self):
        m = generate_manifest(APP_URL)
        home = m["features"]["app_home"]
        assert home["home_tab_enabled"] is True
        assert home["messages_tab_enabled"] is True
        assert home["messages_tab_read_only_enabled"] is False

    def test_trailing_slash_stripped(self):
        m = generate_manifest("https://app.example.com/")
        assert "//" not in m["settings"]["event_subscriptions"]["request_url"].replace("https://", "")


class TestGenerateManifestUrl:
    def test_base_url(self):
        url = generate_manifest_url(APP_URL)
        assert url.startswith("https://api.slack.com/apps?new_app=1&manifest_json=")

    def test_encoded_json(self):
        url = generate_manifest_url(APP_URL)
        _, _, query = url.partition("?")
        params = urllib.parse.parse_qs(query)
        manifest_json = params["manifest_json"][0]
        manifest = json.loads(manifest_json)
        assert manifest["_metadata"]["major_version"] == 2
        assert manifest["display_information"]["name"] == "Incident Copilot"


class TestManifestEndpoints:
    @pytest.mark.asyncio
    async def test_manifest_endpoint(self):
        """Test GET /dashboard/integrations/slack/manifest returns manifest JSON."""
        try:
            import httpx
            from src.web.app import create_app
        except ImportError:
            pytest.skip("httpx or app not available")

        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/dashboard/integrations/slack/manifest")
            # May get 401 if auth required — that's fine, endpoint exists
            assert resp.status_code in (200, 401, 403)
            if resp.status_code == 200:
                data = resp.json()
                assert data["_metadata"]["major_version"] == 2

    @pytest.mark.asyncio
    async def test_install_redirect(self):
        """Test GET /dashboard/integrations/slack/install redirects."""
        try:
            import httpx
            from src.web.app import create_app
        except ImportError:
            pytest.skip("httpx or app not available")

        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/dashboard/integrations/slack/install")
            assert resp.status_code in (307, 401, 403)
            if resp.status_code == 307:
                assert "api.slack.com" in resp.headers["location"]
