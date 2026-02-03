"""Tests for Slack slash commands."""

import hashlib
import hmac
import time
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.slack_commands.commands import CommandContext, CommandHandler
from src.slack_commands.responses import BlockKitBuilder
from src.slack_commands.router import verify_slack_signature


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def command_handler():
    return CommandHandler()


class TestBlockKitBuilder:
    def test_help_response(self):
        response = BlockKitBuilder.help_response()
        assert response["response_type"] == "ephemeral"
        assert "blocks" in response

    def test_status_response_empty(self):
        response = BlockKitBuilder.status_response([], {"total": 0})
        assert response["response_type"] == "ephemeral"

    def test_error_response(self):
        response = BlockKitBuilder.error_response("Test error")
        assert response["response_type"] == "ephemeral"
        assert "Error" in response["text"]

    def test_make_public(self):
        response = BlockKitBuilder.help_response()
        public = BlockKitBuilder.make_public(response)
        assert public["response_type"] == "in_channel"


class TestSignatureVerification:
    def test_valid_signature(self):
        secret = "test_secret"
        timestamp = str(int(time.time()))
        body = b"token=test"
        sig_base = f"v0:{timestamp}:{body.decode()}"
        sig = (
            "v0="
            + hmac.new(secret.encode(), sig_base.encode(), hashlib.sha256).hexdigest()
        )
        assert verify_slack_signature(body, timestamp, sig, secret)

    def test_invalid_signature(self):
        assert not verify_slack_signature(
            b"test", str(int(time.time())), "v0=invalid", "secret"
        )

    def test_no_secret_allows_request(self):
        assert verify_slack_signature(b"test", str(int(time.time())), "any", "")


class TestCommandHandler:
    @pytest.fixture
    def ctx(self):
        return CommandContext(
            user_id="U123",
            channel_id="C123",
            team_id="T123",
            command="/incident",
            text="",
            response_url="https://test",
        )

    @pytest.mark.asyncio
    async def test_help_command(self, command_handler, ctx):
        ctx.text = "help"
        response = await command_handler.handle(ctx)
        assert response["response_type"] == "ephemeral"

    @pytest.mark.asyncio
    async def test_empty_shows_help(self, command_handler, ctx):
        ctx.text = ""
        response = await command_handler.handle(ctx)
        assert response["response_type"] == "ephemeral"

    @pytest.mark.asyncio
    async def test_unknown_command(self, command_handler, ctx):
        ctx.text = "unknown"
        response = await command_handler.handle(ctx)
        assert "Error" in response["text"]

    @pytest.mark.asyncio
    async def test_public_flag(self, command_handler, ctx):
        ctx.text = "help --public"
        response = await command_handler.handle(ctx)
        assert response["response_type"] == "in_channel"


class TestSlackCommandsEndpoint:
    def test_health_endpoint(self, client):
        response = client.get("/slack/commands/health")
        assert response.status_code == 200

    def test_command_help(self, client):
        form = "token=t&team_id=T&channel_id=C&user_id=U&command=/incident&text=help&response_url=http://test"
        response = client.post(
            "/slack/commands",
            content=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        assert response.json()["response_type"] == "ephemeral"
