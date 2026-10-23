"""Gateway overhead benchmark: ``make bench`` against the running stack.

Compares the same request sent straight to the mock provider and through TokenShield (with
a hard budget applied, so the reservation path is included). The mock answers instantly
for prompts marked ``[[fast]]``, so the difference is the gateway's own cost: auth, policy,
token estimation, cache lookup, budget reservation, accounting.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid

import httpx

API = os.environ.get("TOKENSHIELD_API_URL", "http://localhost:4130")
MOCK = os.environ.get("MOCK_LLM_URL", "http://localhost:4150")
EMAIL = os.environ.get("BENCH_EMAIL", "admin@tokenshield.local")
PASSWORD = os.environ.get("DEMO_PASSWORD") or os.environ.get("TS_DEMO_PASSWORD") or "ShieldDemo2026"
N = int(os.environ.get("BENCH_REQUESTS", "400"))
CONCURRENCY = int(os.environ.get("BENCH_CONCURRENCY", "16"))


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


async def timed(
    client: httpx.AsyncClient, url: str, body: dict[str, object], headers: dict[str, str]
) -> float:
    t0 = time.perf_counter()
    resp = await client.post(url, json=body, headers=headers)
    resp.raise_for_status()
    return (time.perf_counter() - t0) * 1000


async def run_batch(make: object, n: int) -> tuple[list[float], float]:
    sem = asyncio.Semaphore(CONCURRENCY)
    latencies: list[float] = []

    async def one(i: int) -> None:
        async with sem:
            latencies.append(await make(i))  # type: ignore[operator]

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)))
    return latencies, n / (time.perf_counter() - t0)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=64)) as client:
        login = await client.post(
            f"{API}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        login.raise_for_status()
        admin = {"authorization": f"Bearer {login.json()['session_token']}"}
        tag = uuid.uuid4().hex[:6]
        project = (
            await client.post(
                f"{API}/api/v1/projects", json={"name": f"bench-{tag}"}, headers=admin
            )
        ).json()
        key = (
            await client.post(
                f"{API}/api/v1/keys",
                json={"project_id": project["id"], "name": "bench"},
                headers=admin,
            )
        ).json()
        await client.post(
            f"{API}/api/v1/budgets",
            json={
                "name": f"bench-{tag}",
                "scope_type": "project",
                "scope_id": project["id"],
                "period": "daily",
                "limit_usd": "1000",
            },
            headers=admin,
        )
        gw = {"authorization": f"Bearer {key['key']}"}

        def body(i: int) -> dict[str, object]:
            return {
                "model": "chat-small",
                "temperature": 0,
                "messages": [{"role": "user", "content": f"bench {tag} {i} [[fast]]"}],
            }

        # Warm up connections and the gateway's config cache.
        await run_batch(
            lambda i: timed(client, f"{API}/v1/chat/completions", body(10_000 + i), gw), 40
        )

        direct, direct_rps = await run_batch(
            lambda i: timed(client, f"{MOCK}/v1/chat/completions", body(i), {}), N
        )
        miss, miss_rps = await run_batch(
            lambda i: timed(client, f"{API}/v1/chat/completions", body(i), gw), N
        )
        hit, hit_rps = await run_batch(
            lambda i: timed(client, f"{API}/v1/chat/completions", body(i), gw), N
        )

        overhead = [m - statistics.median(direct) for m in miss]
        print(f"requests per run: {N}, concurrency: {CONCURRENCY}")
        print(
            f"provider direct    p50 {pct(direct, 0.5):6.1f} ms   p95 {pct(direct, 0.95):6.1f} ms   {direct_rps:7.0f} req/s"
        )
        print(
            f"gateway, miss      p50 {pct(miss, 0.5):6.1f} ms   p95 {pct(miss, 0.95):6.1f} ms   {miss_rps:7.0f} req/s"
        )
        print(
            f"gateway, cache hit p50 {pct(hit, 0.5):6.1f} ms   p95 {pct(hit, 0.95):6.1f} ms   {hit_rps:7.0f} req/s"
        )
        print(
            f"gateway overhead   p50 {pct(overhead, 0.5):6.1f} ms   p95 {pct(overhead, 0.95):6.1f} ms"
        )
        await client.patch(
            f"{API}/api/v1/projects/{project['id']}", json={"archived": True}, headers=admin
        )


if __name__ == "__main__":
    asyncio.run(main())
