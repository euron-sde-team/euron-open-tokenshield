"""Integration harness: the real app in-process against real Postgres and Redis, with the
mock LLM served over real HTTP from a background thread.

    make test-integration      (starts Postgres and Redis containers if needed)

Safety: the suite truncates every table, so it refuses any database whose name does not
contain "test", and any non-local host unless ALLOW_REMOTE_TEST_DB=true.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
import uvicorn
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tokenshield.core.config import Settings
from tokenshield.main import create_app

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://tokenshield:tokenshield@localhost:4142/tokenshield_test",
)
TEST_REDIS = os.environ.get("TEST_REDIS_URL", "redis://localhost:4179/15")
OWNER = {"email": "owner@example.test", "password": "Owner-Pass-123"}
TABLES = (
    "usage_rollups_hourly, reconciliation_events, budget_reservations, usage_events, cache_entries, "
    "semantic_cache, alerts, exports, audit_log, policy_rules, budgets, model_prices, models, "
    "providers, api_keys, projects, teams, users"
)


def _guard(url: str) -> None:
    parsed = urlparse(url.replace("+asyncpg", ""))
    if "test" not in (parsed.path or ""):
        raise RuntimeError(
            f"refusing to run against {parsed.path!r}: database name must contain 'test'"
        )
    if (
        parsed.hostname not in ("localhost", "127.0.0.1", "postgres")
        and os.environ.get("ALLOW_REMOTE_TEST_DB") != "true"
    ):
        raise RuntimeError("refusing a non-local test database (set ALLOW_REMOTE_TEST_DB=true)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def mock_url() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config("mockllm.app:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[str]:
    _guard(TEST_DB)
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    name = TEST_DB.rsplit("/", 1)[1]
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    from tokenshield.migrations.runner import upgrade

    await asyncio.to_thread(upgrade, TEST_DB)
    yield TEST_DB


@pytest.fixture
def settings(database: str, tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=database,
        redis_url=TEST_REDIS,
        session_secret="test-only-session-secret-with-32-plus-bytes",
        api_key_pepper="test-only-api-key-pepper-with-32-plus-bytes",
        local_master_key="test-only-master-key-with-32-plus-bytes-ok",
        local_storage_dir=str(tmp_path / "exports"),
        upstream_timeout_s=5,
        coalesce_wait_s=5,
        uncertain_settle_after_s=0,
        # The option matrix (make test-matrix) reruns the suite against Floci-backed KMS and S3.
        key_mode=os.environ.get("TEST_KEY_MODE", "local"),
        storage=os.environ.get("TEST_STORAGE", "local"),
        aws_endpoint_url=os.environ.get("TEST_AWS_ENDPOINT"),
        s3_public_endpoint=os.environ.get("TEST_AWS_ENDPOINT"),
        s3_force_path_style=True,
        kms_key_id=os.environ.get("TEST_KMS_KEY_ID", "alias/tokenshield-local"),
        exports_bucket=os.environ.get("TEST_EXPORTS_BUCKET", "tokenshield-local-exports"),
    )


async def _reset(settings: Settings, mock_url: str) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    await engine.dispose()
    from redis.asyncio import Redis

    redis = Redis.from_url(settings.redis_url)
    await redis.flushdb()
    await redis.aclose()
    async with httpx.AsyncClient() as client:
        await client.post(f"{mock_url}/stats/reset")


@dataclass
class Api:
    """A signed-in admin client plus helpers for common setup."""

    client: httpx.AsyncClient
    app: FastAPI
    mock_url: str

    async def mock_calls(self) -> dict[str, int]:
        async with httpx.AsyncClient() as c:
            data: dict[str, int] = (await c.get(f"{self.mock_url}/stats")).json()
            return data

    async def post(self, path: str, json: Any = None, **kw: Any) -> httpx.Response:
        return await self.client.post(path, json=json, **kw)

    async def drain(self) -> int:
        """Write buffered usage events to Postgres, as the worker does continuously."""
        from tokenshield.worker import Worker

        worker = Worker(self.app.state.container)
        total = 0
        while written := await worker.drain_usage():
            total += written
        return total

    async def ok(self, method: str, path: str, json: Any = None, status: int | None = None) -> Any:
        await self.drain()
        resp = await self.client.request(method, path, json=json)
        expected = status or (201 if method == "POST" and resp.status_code == 201 else 200)
        assert resp.status_code == expected, f"{method} {path}: {resp.status_code} {resp.text}"
        return resp.json() if resp.content else None

    async def fetch(self, url: str) -> httpx.Response:
        """GET a download link: presigned S3 URLs are real HTTP, API paths are in-process."""
        if url.startswith("http"):
            async with httpx.AsyncClient() as client:
                return await client.get(url)
        return await self.client.get(url)

    async def gateway(
        self, key: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        return await self.client.post(
            "/v1/chat/completions",
            json=body,
            headers={"authorization": f"Bearer {key}", **(headers or {})},
        )


async def _bootstrap_owner(settings: Settings) -> None:
    from tokenshield.core.db import Database
    from tokenshield.core.security import hash_password
    from tokenshield.users.models import User

    db = Database(settings.database_url, pool_size=1, max_overflow=0)
    async with db.sessionmaker() as session:
        session.add(
            User(
                email=OWNER["email"],
                name="Owner",
                role="owner",
                password_hash=hash_password(OWNER["password"]),
            )
        )
        await session.commit()
    await db.dispose()


@pytest.fixture
async def app(settings: Settings, mock_url: str) -> AsyncIterator[FastAPI]:
    await _reset(settings, mock_url)
    await _bootstrap_owner(settings)
    application = create_app(settings)
    async with LifespanManager(application, startup_timeout=60, shutdown_timeout=30):
        yield application


@pytest.fixture
async def api(app: FastAPI, mock_url: str) -> AsyncIterator[Api]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=30
    ) as client:
        resp = await client.post("/api/v1/auth/login", json=OWNER)
        assert resp.status_code == 200, resp.text
        client.headers["authorization"] = f"Bearer {resp.json()['session_token']}"
        yield Api(client, app, mock_url)


@dataclass
class World:
    """A configured gateway: providers, priced models, a team, a project and a key."""

    provider_id: str
    anthropic_id: str
    project_id: str
    team_id: str
    key: str
    key_id: str
    models: dict[str, str]


PRICES = {
    "chat-small": {"input_per_m": "1.00", "cached_input_per_m": "0.50", "output_per_m": "2.00"},
    "chat-large": {"input_per_m": "10.00", "cached_input_per_m": None, "output_per_m": "30.00"},
    "claude": {"input_per_m": "3.00", "cached_input_per_m": "0.30", "output_per_m": "15.00"},
}


@pytest.fixture
async def world(api: Api) -> World:
    provider = await api.ok(
        "POST",
        "/api/v1/providers",
        {
            "name": "Mock OpenAI",
            "kind": "openai",
            "base_url": f"{api.mock_url}/v1",
            "api_key": "sk-test-only-123456",
            "timeout_s": 3,
        },
    )
    anthropic = await api.ok(
        "POST",
        "/api/v1/providers",
        {
            "name": "Mock Anthropic",
            "kind": "anthropic",
            "base_url": api.mock_url,
            "api_key": "sk-ant-test-only",
        },
    )
    models = {}
    for alias, upstream, prov in (
        ("chat-small", "mock-small", provider),
        ("chat-large", "mock-large", provider),
        ("claude", "mock-claude", anthropic),
    ):
        m = await api.ok(
            "POST",
            "/api/v1/models",
            {
                "alias": alias,
                "provider_id": prov["id"],
                "upstream_model": upstream,
                "price": PRICES[alias],
                "max_output_tokens": 4096,
            },
        )
        models[alias] = m["id"]
    embed = await api.ok(
        "POST",
        "/api/v1/models",
        {
            "alias": "embed-small",
            "provider_id": provider["id"],
            "upstream_model": "mock-embed",
            "kind": "embedding",
            "price": {"input_per_m": "0.02", "output_per_m": "0"},
        },
    )
    models["embed-small"] = embed["id"]
    team = await api.ok("POST", "/api/v1/teams", {"name": "Learning"})
    project = await api.ok(
        "POST", "/api/v1/projects", {"name": "Alpha Tutor", "team_id": team["id"]}
    )
    key = await api.ok("POST", "/api/v1/keys", {"project_id": project["id"], "name": "prod"})
    return World(
        provider["id"], anthropic["id"], project["id"], team["id"], key["key"], key["id"], models
    )


def chat(
    content: str = "What is photosynthesis?", model: str = "chat-small", **extra: Any
) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": content}],
        **extra,
    }
