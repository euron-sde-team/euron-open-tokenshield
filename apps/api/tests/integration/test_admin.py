"""Dashboard API: authentication, roles, CSRF, guards, audit, and every resource's CRUD."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import OWNER, Api, World

pytestmark = pytest.mark.integration


async def login(api: Api, email: str, password: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    ) as c:
        return await c.post("/api/v1/auth/login", json={"email": email, "password": password})


async def as_user(api: Api, role: str) -> httpx.AsyncClient:
    email = f"{role}@example.test"
    await api.ok(
        "POST",
        "/api/v1/users",
        {"email": email, "name": role.title(), "role": role, "password": "Role-Pass-1234"},
        status=201,
    )
    token = (await login(api, email, "Role-Pass-1234")).json()["session_token"]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app),
        base_url="http://testserver",
        headers={"authorization": f"Bearer {token}"},
    )


async def test_login_me_logout(api: Api) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    ) as c:
        resp = await c.post(
            "/api/v1/auth/login",
            json={"email": "OWNER@example.test", "password": OWNER["password"]},
        )
        assert resp.status_code == 200 and "ts_session" in resp.cookies
        assert (await c.get("/api/v1/auth/me")).json()["role"] == "owner"
        await c.post("/api/v1/auth/logout", headers={"x-tokenshield-csrf": "1"})
        c.cookies.clear()
        assert (await c.get("/api/v1/auth/me")).status_code == 401


async def test_cookie_mutations_need_csrf_header(api: Api) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    ) as c:
        await c.post("/api/v1/auth/login", json=OWNER)
        assert (await c.post("/api/v1/teams", json={"name": "x"})).json()["error"][
            "code"
        ] == "csrf_required"
        assert (
            await c.post("/api/v1/teams", json={"name": "x"}, headers={"x-tokenshield-csrf": "1"})
        ).status_code == 201
        assert (await c.get("/api/v1/teams")).status_code == 200


async def test_wrong_password_lockout(api: Api) -> None:
    for _ in range(5):
        assert (await login(api, OWNER["email"], "wrong")).json()["error"][
            "code"
        ] == "invalid_credentials"
    locked = await login(api, OWNER["email"], OWNER["password"])
    assert locked.status_code == 401 and locked.json()["error"]["code"] == "account_locked"


async def test_unknown_user_gets_same_error(api: Api) -> None:
    assert (await login(api, "nobody@example.test", "x")).json()["error"][
        "code"
    ] == "invalid_credentials"


async def test_password_change_ends_other_sessions(api: Api) -> None:
    old = (await login(api, OWNER["email"], OWNER["password"])).json()["session_token"]
    resp = await api.post(
        "/api/v1/auth/password",
        {"current_password": OWNER["password"], "new_password": "Brand-New-Pass-9"},
    )
    assert resp.status_code == 200
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    ) as c:
        assert (
            await c.get("/api/v1/auth/me", headers={"authorization": f"Bearer {old}"})
        ).status_code == 401
    weak = await api.post(
        "/api/v1/auth/password",
        {"current_password": "Brand-New-Pass-9", "new_password": "weakpassword"},
    )
    assert weak.status_code in (400, 401)


async def test_viewer_is_read_only(api: Api, world: World) -> None:
    viewer = await as_user(api, "viewer")
    async with viewer:
        for path in (
            "/api/v1/projects",
            "/api/v1/budgets",
            "/api/v1/usage/events",
            "/api/v1/analytics/overview",
            "/api/v1/models",
        ):
            assert (await viewer.get(path)).status_code == 200, path
        assert (await viewer.post("/api/v1/teams", json={"name": "x"})).status_code == 403
        assert (await viewer.post(f"/api/v1/keys/{world.key_id}/revoke")).status_code == 403
        assert (await viewer.get("/api/v1/audit")).status_code == 403
        assert (await viewer.get("/api/v1/users")).status_code == 403


async def test_admin_cannot_manage_users(api: Api) -> None:
    admin = await as_user(api, "admin")
    async with admin:
        assert (await admin.post("/api/v1/teams", json={"name": "ok"})).status_code == 201
        resp = await admin.post(
            "/api/v1/users",
            json={
                "email": "x@example.test",
                "name": "x",
                "role": "viewer",
                "password": "Some-Pass-123",
            },
        )
        assert resp.status_code == 403


async def test_owner_guards(api: Api) -> None:
    me = await api.ok("GET", "/api/v1/auth/me")
    assert (
        await api.client.patch(f"/api/v1/users/{me['id']}", json={"role": "viewer"})
    ).status_code == 403
    other = await api.ok(
        "POST",
        "/api/v1/users",
        {"email": "o2@example.test", "name": "O2", "role": "owner", "password": "Owner-Two-123"},
        status=201,
    )
    await api.ok("PATCH", f"/api/v1/users/{other['id']}", {"disabled": True})
    assert (await login(api, "o2@example.test", "Owner-Two-123")).json()["error"][
        "code"
    ] == "account_disabled"
    dup = await api.post(
        "/api/v1/users",
        {"email": "O2@example.test", "name": "x", "role": "viewer", "password": "Some-Pass-123"},
    )
    assert dup.status_code == 409


async def test_role_change_invalidates_sessions(api: Api) -> None:
    async with await as_user(api, "admin") as admin:
        users = await api.ok("GET", "/api/v1/users")
        target = next(u for u in users if u["role"] == "admin")
        await api.ok("PATCH", f"/api/v1/users/{target['id']}", {"role": "viewer"})
        assert (await admin.get("/api/v1/auth/me")).status_code == 401


async def test_resource_crud_and_audit(api: Api, world: World) -> None:
    team = await api.ok("POST", "/api/v1/teams", {"name": "Growth"}, status=201)
    await api.ok("PATCH", f"/api/v1/teams/{team['id']}", {"description": "copy"})
    project = await api.ok(
        "POST", "/api/v1/projects", {"name": "Growth bot", "team_id": team["id"]}, status=201
    )
    conflict = await api.client.delete(f"/api/v1/teams/{team['id']}")
    assert conflict.status_code == 409
    await api.ok("PATCH", f"/api/v1/projects/{project['id']}", {"archived": True})
    assert (await api.client.delete(f"/api/v1/teams/{team['id']}")).status_code == 204
    teams = await api.ok("GET", "/api/v1/teams")
    assert all(t["id"] != team["id"] for t in teams)
    assert (
        await api.post("/api/v1/projects", {"name": "x", "allowed_models": ["nope"]})
    ).status_code == 400

    key = await api.ok(
        "POST", "/api/v1/keys", {"project_id": world.project_id, "name": "ci"}, status=201
    )
    assert key["key"].startswith("tsk_") and key["display"].endswith("_****")
    listed = await api.ok("GET", f"/api/v1/keys?project_id={world.project_id}")
    assert all("key" not in k for k in listed), "plaintext is shown once"
    await api.ok("PATCH", f"/api/v1/keys/{key['id']}", {"rpm_limit": 10})

    b = await api.ok(
        "POST",
        "/api/v1/budgets",
        {
            "name": "x",
            "scope_type": "project",
            "scope_id": world.project_id,
            "period": "weekly",
            "limit_usd": "3",
        },
        status=201,
    )
    await api.ok("PATCH", f"/api/v1/budgets/{b['id']}", {"limit_usd": "4", "mode": "soft"})
    assert (
        await api.post(
            "/api/v1/budgets",
            {
                "name": "x",
                "scope_type": "project",
                "scope_id": "not-a-uuid",
                "period": "weekly",
                "limit_usd": "3",
            },
        )
    ).status_code == 400
    assert (
        await api.post(
            "/api/v1/budgets",
            {"name": "x", "scope_type": "team", "period": "weekly", "limit_usd": "3"},
        )
    ).status_code == 422
    assert (await api.client.delete(f"/api/v1/budgets/{b['id']}")).status_code == 204

    p = await api.ok(
        "POST",
        "/api/v1/policies",
        {"name": "cap", "kind": "max_output_tokens", "params": {"limit": 100}, "action": "cap"},
        status=201,
    )
    await api.ok("PATCH", f"/api/v1/policies/{p['id']}", {"enabled": False})
    bad = await api.client.patch(f"/api/v1/policies/{p['id']}", json={"action": "throttle"})
    assert bad.status_code == 400
    assert (await api.client.delete(f"/api/v1/policies/{p['id']}")).status_code == 204

    audit = await api.ok("GET", "/api/v1/audit?limit=200")
    actions = {e["action"] for e in audit["items"]}
    assert {
        "team.created",
        "project.updated",
        "api_key.created",
        "budget.deleted",
        "policy.created",
        "auth.login",
    } <= actions
    assert all(e["actor_email"] for e in audit["items"])
    page = await api.ok("GET", "/api/v1/audit?limit=3")
    nxt = await api.ok("GET", f"/api/v1/audit?limit=3&cursor={page['next_cursor']}")
    assert page["items"][-1]["id"] > nxt["items"][0]["id"]


async def test_providers_models_and_price_versions(api: Api, world: World) -> None:
    providers = await api.ok("GET", "/api/v1/providers")
    mock = next(p for p in providers if p["id"] == world.provider_id)
    assert mock["has_key"] and mock["key_hint"] == "...3456" and "api_key" not in mock
    check = await api.ok("POST", f"/api/v1/providers/{world.provider_id}/test")
    assert check["ok"] and check["message"] == "Connected"
    v2 = await api.ok(
        "POST",
        f"/api/v1/models/{world.models['chat-small']}/prices",
        {"input_per_m": "2", "output_per_m": "4"},
        status=201,
    )
    assert v2["version"] == 2
    history = await api.ok("GET", f"/api/v1/models/{world.models['chat-small']}/prices")
    assert [h["version"] for h in history] == [2, 1]
    models = await api.ok("GET", "/api/v1/models")
    assert next(m for m in models if m["alias"] == "chat-small")["price"]["version"] == 2
    assert (
        await api.post(
            "/api/v1/models",
            {"alias": "chat-small", "provider_id": world.provider_id, "upstream_model": "x"},
        )
    ).status_code == 409
    await api.ok("PATCH", f"/api/v1/providers/{world.provider_id}", {"api_key": ""})
    providers = await api.ok("GET", "/api/v1/providers")
    assert not next(p for p in providers if p["id"] == world.provider_id)["has_key"]


async def test_new_price_applies_to_new_requests_only(api: Api, world: World) -> None:
    body = {
        "model": "chat-small",
        "messages": [{"role": "user", "content": "price check"}],
        "temperature": 0,
    }
    old = await api.gateway(world.key, body, {"x-tokenshield-cache": "off"})
    await api.ok(
        "POST",
        f"/api/v1/models/{world.models['chat-small']}/prices",
        {"input_per_m": "100", "output_per_m": "200"},
        status=201,
    )
    new = await api.gateway(world.key, body, {"x-tokenshield-cache": "off"})
    assert float(new.headers["x-tokenshield-cost-usd"]) == pytest.approx(
        float(old.headers["x-tokenshield-cost-usd"]) * 100, rel=0.01
    )
    old_event = await api.ok(
        "GET", f"/api/v1/usage/events/{old.headers['x-tokenshield-request-id']}"
    )
    assert old_event["price_version"] == 1


async def test_system_health_and_playground(api: Api, world: World) -> None:
    assert (await api.client.get("/healthz")).json() == {"status": "ok"}
    ready = await api.client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["checks"]["postgres"]["ok"]
    info = await api.ok("GET", "/api/v1/system")
    assert info["version"] == "0.1.0" and info["active_keys"] == 1
    metrics = await api.client.get("/metrics")
    assert "tokenshield_requests_total" in metrics.text
    resp = await api.post(
        "/api/v1/playground/chat",
        {
            "project_id": world.project_id,
            "model": "chat-small",
            "messages": [{"role": "user", "content": "hello from playground"}],
        },
    )
    assert resp.status_code == 200 and resp.headers["x-tokenshield-cache"] == "MISS"
    event = await api.ok("GET", f"/api/v1/usage/events/{resp.headers['x-tokenshield-request-id']}")
    assert event["source"] == "playground" and event["api_key_id"] is None
    assert resp.headers["x-content-type-options"] == "nosniff" and resp.headers["x-request-id"]
