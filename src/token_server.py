"""Public demo token endpoint for the browser-based receptionist."""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

logger = logging.getLogger("token_server")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ACTION = "voice-demo"
TOKEN_TTL = timedelta(minutes=10)
TokenVerifier = Callable[[str, "TokenSettings", str | None], Awaitable[bool]]


@dataclass(frozen=True)
class TokenSettings:
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    agent_name: str = ""
    turnstile_secret_key: str = ""
    turnstile_allowed_hostname: str = ""
    frontend_origin: str = ""

    @classmethod
    def from_environment(cls) -> "TokenSettings":
        return cls(
            livekit_url=os.getenv("LIVEKIT_URL", ""),
            livekit_api_key=os.getenv("LIVEKIT_API_KEY", ""),
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", ""),
            agent_name=os.getenv("LIVEKIT_AGENT_NAME", ""),
            turnstile_secret_key=os.getenv("TURNSTILE_SECRET_KEY", ""),
            turnstile_allowed_hostname=os.getenv("TURNSTILE_ALLOWED_HOSTNAME", ""),
            frontend_origin=os.getenv("FRONTEND_ORIGIN", ""),
        )

    @property
    def is_configured(self) -> bool:
        origin = urlsplit(self.frontend_origin)
        livekit_url = urlsplit(self.livekit_url)
        secure_origin = origin.scheme == "https" or (
            origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1"}
        )
        return all(
            (
                livekit_url.scheme in {"ws", "wss"},
                bool(livekit_url.netloc),
                bool(self.livekit_api_key),
                bool(self.livekit_api_secret),
                bool(self.agent_name),
                bool(self.turnstile_secret_key),
                bool(self.turnstile_allowed_hostname),
                secure_origin,
                bool(origin.netloc),
                origin.hostname == self.turnstile_allowed_hostname,
            )
        )


class TokenRequest(BaseModel):
    room_name: str | None = None


class TokenRateLimiter:
    """Small per-process sliding-window limiter for public demo token requests."""

    def __init__(
        self,
        max_requests: int = 3,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, client_id: str) -> bool:
        now = self._clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            requests = self._requests[client_id]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                return False
            requests.append(now)
            return True


async def verify_turnstile(
    token: str,
    settings: TokenSettings,
    remote_ip: str | None,
) -> bool:
    """Verify a single-use Turnstile token and its expected site/action."""
    form_data = {
        "secret": settings.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        form_data["remoteip"] = remote_ip

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
        response = await client.post(TURNSTILE_VERIFY_URL, data=form_data)
        response.raise_for_status()

    result = response.json()
    return (
        isinstance(result, dict)
        and result.get("success") is True
        and result.get("action") == TURNSTILE_ACTION
        and result.get("hostname") == settings.turnstile_allowed_hostname
    )


def _valid_demo_room(room_name: str) -> bool:
    prefix = "smilecare-demo-"
    if not room_name.startswith(prefix):
        return False
    try:
        return (
            str(UUID(room_name.removeprefix(prefix)))
            == room_name.removeprefix(prefix).lower()
        )
    except ValueError:
        return False


def create_app(
    settings: TokenSettings | None = None,
    *,
    turnstile_verifier: TokenVerifier = verify_turnstile,
    rate_limiter: TokenRateLimiter | None = None,
) -> FastAPI:
    settings = settings or TokenSettings.from_environment()
    rate_limiter = rate_limiter or TokenRateLimiter()
    app = FastAPI(title="SmileCare demo token service")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin] if settings.frontend_origin else [],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Turnstile-Token"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/token", status_code=201)
    async def create_token(
        body: TokenRequest,
        request: Request,
        turnstile_token: str = Header(alias="X-Turnstile-Token"),
    ) -> dict[str, str]:
        if not settings.is_configured:
            raise HTTPException(
                status_code=503,
                detail="The demo token service is not configured.",
            )

        client_id = request.client.host if request.client else "unknown"
        if not await rate_limiter.allow(client_id):
            raise HTTPException(
                status_code=429,
                detail="Too many demo calls. Please wait before trying again.",
                headers={"Retry-After": str(rate_limiter.window_seconds)},
            )

        room_name = body.room_name or f"smilecare-demo-{uuid4()}"
        if not _valid_demo_room(room_name):
            raise HTTPException(
                status_code=400,
                detail="A valid demo room name is required.",
            )

        try:
            challenge_valid = await turnstile_verifier(
                turnstile_token,
                settings,
                client_id,
            )
        except httpx.HTTPError:
            logger.exception("Turnstile verification service is unavailable")
            raise HTTPException(
                status_code=503,
                detail="Human verification is temporarily unavailable.",
            ) from None

        if not challenge_valid:
            raise HTTPException(
                status_code=403,
                detail="Human verification failed. Please try again.",
            )

        try:
            token = (
                api.AccessToken(
                    settings.livekit_api_key,
                    settings.livekit_api_secret,
                )
                .with_identity(f"visitor-{uuid4().hex}")
                .with_name("Website visitor")
                .with_ttl(TOKEN_TTL)
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=room_name,
                        can_publish=True,
                        can_subscribe=True,
                        can_publish_data=False,
                    )
                )
                .with_room_config(
                    api.RoomConfiguration(
                        agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)]
                    )
                )
                .to_jwt()
            )
        except ValueError:
            logger.exception("Could not generate a LiveKit demo token")
            raise HTTPException(
                status_code=500,
                detail="Could not start the demo session.",
            ) from None

        return {
            "server_url": settings.livekit_url,
            "participant_token": token,
        }

    return app


app = create_app()
