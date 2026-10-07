"""Tests for the public demo token endpoint."""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from livekit import api

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import token_server
from token_server import (
    TokenRateLimiter,
    TokenSettings,
    create_app,
    verify_turnstile,
)

SETTINGS = TokenSettings(
    livekit_url="wss://example.livekit.cloud",
    livekit_api_key="demo-key",
    livekit_api_secret="demo-secret-only-for-tests-with-32-bytes",
    agent_name="voice-ai-receptionist",
    turnstile_secret_key="turnstile-secret",
    turnstile_allowed_hostname="aj23101.github.io",
    frontend_origin="https://aj23101.github.io",
)


async def verify_valid_challenge(token, settings, remote_ip):
    return token == "human-token"


def make_client(settings=SETTINGS, **kwargs):
    app = create_app(
        settings,
        turnstile_verifier=verify_valid_challenge,
        **kwargs,
    )
    return TestClient(app)


def test_health_check_does_not_expose_configuration():
    response = make_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_token_endpoint_rejects_missing_turnstile_header():
    response = make_client().post(
        "/api/token",
        json={"room_name": "smilecare-demo-77ee2a1d-1e1d-47a4-9477-7c0c74ee2d70"},
    )

    assert response.status_code == 422


def test_token_endpoint_rejects_invalid_turnstile_response():
    response = make_client().post(
        "/api/token",
        headers={"X-Turnstile-Token": "not-human"},
        json={"room_name": "smilecare-demo-77ee2a1d-1e1d-47a4-9477-7c0c74ee2d70"},
    )

    assert response.status_code == 403


def test_token_endpoint_issues_a_limited_agent_session_token():
    room_name = "smilecare-demo-77ee2a1d-1e1d-47a4-9477-7c0c74ee2d70"
    response = make_client().post(
        "/api/token",
        headers={"X-Turnstile-Token": "human-token"},
        json={"room_name": room_name},
    )

    assert response.status_code == 201
    assert response.json()["server_url"] == SETTINGS.livekit_url
    claims = api.TokenVerifier(
        SETTINGS.livekit_api_key,
        SETTINGS.livekit_api_secret,
    ).verify(response.json()["participant_token"])
    assert claims.video.room == room_name
    assert claims.video.room_join is True
    assert claims.video.can_publish is True
    assert claims.video.can_subscribe is True
    assert claims.room_config.agents[0].agent_name == SETTINGS.agent_name


def test_token_endpoint_rejects_room_names_outside_demo_namespace():
    response = make_client().post(
        "/api/token",
        headers={"X-Turnstile-Token": "human-token"},
        json={"room_name": "shared-production-room"},
    )

    assert response.status_code == 400


def test_token_endpoint_returns_unavailable_when_secrets_are_missing():
    settings = TokenSettings(
        livekit_url="",
        livekit_api_key="",
        livekit_api_secret="",
        agent_name="",
        turnstile_secret_key="",
        turnstile_allowed_hostname="",
        frontend_origin="",
    )

    response = make_client(settings).post(
        "/api/token",
        headers={"X-Turnstile-Token": "human-token"},
        json={"room_name": "smilecare-demo-77ee2a1d-1e1d-47a4-9477-7c0c74ee2d70"},
    )

    assert response.status_code == 503


def test_token_endpoint_applies_a_per_client_rate_limit():
    client = make_client(rate_limiter=TokenRateLimiter(max_requests=1))
    request = {
        "headers": {"X-Turnstile-Token": "human-token"},
        "json": {"room_name": "smilecare-demo-77ee2a1d-1e1d-47a4-9477-7c0c74ee2d70"},
    }

    assert client.post("/api/token", **request).status_code == 201
    assert client.post("/api/token", **request).status_code == 429


def test_token_endpoint_allows_only_the_configured_frontend_origin():
    client = make_client()
    allowed = client.options(
        "/api/token",
        headers={
            "Origin": SETTINGS.frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-turnstile-token",
        },
    )
    denied = client.options(
        "/api/token",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-turnstile-token",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == SETTINGS.frontend_origin
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    "challenge,expected",
    [
        (
            {
                "success": True,
                "action": "voice-demo",
                "hostname": "aj23101.github.io",
            },
            True,
        ),
        (
            {
                "success": True,
                "action": "other-action",
                "hostname": "aj23101.github.io",
            },
            False,
        ),
        (
            {
                "success": True,
                "action": "voice-demo",
                "hostname": "untrusted.example",
            },
            False,
        ),
    ],
)
def test_turnstile_verification_checks_success_action_and_hostname(
    challenge,
    expected,
    monkeypatch,
):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return challenge

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            assert url == token_server.TURNSTILE_VERIFY_URL
            assert data == {
                "secret": SETTINGS.turnstile_secret_key,
                "response": "human-token",
                "remoteip": "127.0.0.1",
            }
            return Response()

    monkeypatch.setattr(token_server.httpx, "AsyncClient", lambda **kwargs: Client())

    result = asyncio.run(verify_turnstile("human-token", SETTINGS, "127.0.0.1"))

    assert result is expected
