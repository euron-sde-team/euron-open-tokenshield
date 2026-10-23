"""The request pipeline: attribute, estimate, police, cache, reserve, call, reconcile.

Order matters and is deliberate:

1. Model and policy checks run first because they are free (no I/O beyond Redis).
2. Cached responses never bypass authorization, rate limits or waste rules; they are
   checked after those and before any spend is reserved.
3. Budget reservation is the last gate before the provider, so a request that would
   breach a hard budget is refused with **zero** upstream calls.
4. Reconciliation replaces the reservation with the provider-reported cost. A request
   whose outcome is unknown (timeout after sending) keeps its reservation as UNCERTAIN;
   it is never recorded as free.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import secrets
import time
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, NoReturn

import orjson
from fastapi.responses import JSONResponse, Response, StreamingResponse
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

from tokenshield.alerts.service import AlertService
from tokenshield.budgets.resolver import AppliedBudget, CounterHydrator, Subject, applicable
from tokenshield.cache.keys import (
    check_eligibility,
    exact_key,
    partition,
    request_fingerprint,
    response_cacheable,
    semantic_partition,
)
from tokenshield.cache.semantic import SemanticIndex
from tokenshield.cache.store import CachedResponse, ResponseCache
from tokenshield.core.container import Container
from tokenshield.core.errors import (
    AppError,
    BudgetExceededError,
    ConflictError,
    DependencyUnavailableError,
    NotFoundError,
    PermissionDeniedError,
    PolicyViolationError,
    RateLimitedError,
    UpstreamError,
    UpstreamTimeoutError,
)
from tokenshield.core.money import nusd_to_usd
from tokenshield.core.tracing import tracer
from tokenshield.gateway import metrics
from tokenshield.gateway.catalog import Catalog, ModelInfo
from tokenshield.gateway.context import RequestContext
from tokenshield.gateway.tokens import (
    count_text,
    estimate_chat_input,
    estimate_embedding_input,
    last_user_text,
)
from tokenshield.limits.limiter import Limiter
from tokenshield.policies.engine import RequestFacts, Violation, evaluate_static
from tokenshield.policies.stateful import StatefulPolicies
from tokenshield.pricing.engine import actual_cost, worst_case_cost
from tokenshield.providers.adapters.base import (
    StreamState,
    UpstreamHTTPError,
    UpstreamNotSentError,
    UpstreamTarget,
    UpstreamUncertainError,
    Usage,
)
from tokenshield.providers.adapters.http import SSE_DONE, sse
from tokenshield.usage.recorder import ReservationRow, UsageRecord, UsageRecorder

log = logging.getLogger("tokenshield.gateway")

IDEMPOTENCY_TTL_S = 86400
POLICY_HITS_KEY = "ts:policy:hits"
_background: set[asyncio.Task[Any]] = set()


def _spawn(coro: Coroutine[Any, Any, Any]) -> None:
    """Fire-and-forget with a strong reference, so the task is not garbage collected."""
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def new_request_id() -> str:
    return "req_" + secrets.token_hex(12)


def idempotent_request_id(project_id: str, key: str) -> str:
    return "req_" + hashlib.sha256(f"{project_id}|{key}".encode()).hexdigest()[:24]


@dataclass(slots=True)
class Admission:
    """What the pre-call phase established about a request."""

    model: ModelInfo
    body: dict[str, Any]
    input_estimate: int
    max_output: int
    estimate_nusd: int
    applied: list[AppliedBudget] = field(default_factory=list)
    reserved: bool = False
    task_keys: list[str] = field(default_factory=list)
    concurrency_name: str | None = None
    tpm_name: str | None = None
    tpm_reserved: int = 0
    # True once TPM reflects real usage; otherwise the reserved tokens are returned.
    tokens_settled: bool = False
    cache_key: str | None = None
    cache_ttl_s: int = 0
    semantic_partition: str | None = None
    semantic_vector: list[float] | None = None
    leading: bool = False
    facts: RequestFacts | None = None


class GatewayService:
    def __init__(self, container: Container, catalog: Catalog) -> None:
        self.c = container
        self.catalog = catalog
        self.limiter = Limiter(container.redis)
        self.stateful = StatefulPolicies(container.redis)
        self.cache = ResponseCache(
            container.redis, coalesce_wait_s=container.settings.coalesce_wait_s
        )
        self.recorder = UsageRecorder(container.db.sessionmaker, container.redis)
        self.alerts = AlertService(container.db.sessionmaker)
        self.settings = container.settings

    # ── Entry points ────────────────────────────────────────────────────────

    async def chat(self, ctx: RequestContext, body: dict[str, Any]) -> Response:
        with tracer.start_as_current_span("gateway.chat") as span:
            span.set_attribute("tokenshield.request_id", ctx.request_id)
            span.set_attribute("tokenshield.model", str(body.get("model") or ""))
            span.set_attribute("tokenshield.project_id", str(ctx.project.id))
            return await self._chat(ctx, body)

    async def _chat(self, ctx: RequestContext, body: dict[str, Any]) -> Response:
        stream = bool(body.get("stream"))
        alias = str(body.get("model") or "")
        idem_lock: str | None = None
        try:
            if ctx.idempotency_key:
                replay, idem_lock = await self._idempotency_begin(ctx)
                if replay is not None:
                    return replay
            with tracer.start_as_current_span("gateway.admit"):
                adm = await self._admit(ctx, body)
        except AppError as err:
            await self._release_idem(idem_lock)
            await self._record_rejection(ctx, alias, err, stream=stream)
            raise
        streaming_handoff = False
        try:
            with tracer.start_as_current_span("gateway.cache_lookup"):
                hit = await self._cache_lookup(ctx, adm)
            if hit is not None:
                cached, status = hit
                return await self._serve_cached(ctx, adm, cached, status, stream)
            try:
                await self._check_retry_storm(ctx, adm)
                with tracer.start_as_current_span("gateway.reserve"):
                    await self._reserve(ctx, adm)
            except AppError as err:
                await self._record_rejection(ctx, alias, err, stream=stream, adm=adm)
                raise
            if stream:
                streaming_handoff = True
                return self._stream(ctx, adm, idem_lock)
            response = await self._call(ctx, adm)
            if idem_lock:
                await self._idempotency_store(idem_lock, response)
                idem_lock = None
            return response
        finally:
            if not streaming_handoff:
                await self._finish(adm)
                await self._release_idem(idem_lock)

    async def embeddings(self, ctx: RequestContext, body: dict[str, Any]) -> Response:
        """Embeddings pass through the same attribution, limits and budgets; no caching."""
        alias = str(body.get("model") or "")
        try:
            model = self._model(ctx, alias, kind="embedding")
            input_est = estimate_embedding_input(body, model.tokenizer)
            adm = Admission(
                model=model,
                body={**body},
                input_estimate=input_est,
                max_output=0,
                estimate_nusd=worst_case_cost(model.price, input_est, 0),
            )
            try:
                await self._check_limits(ctx, adm)
                await self._reserve(ctx, adm)
            except BaseException:
                await self._finish(adm)
                raise
        except AppError as err:
            await self._record_rejection(ctx, alias, err, endpoint="embeddings")
            raise
        try:
            target = self._target(adm.model)
            adapter = self.c.adapters.get(adm.model.provider_kind)
            t0 = time.perf_counter()
            try:
                data, usage = await adapter.embeddings(target, adm.body)
            except (UpstreamNotSentError, UpstreamHTTPError, UpstreamUncertainError) as exc:
                await self._upstream_failed(ctx, adm, exc, endpoint="embeddings")
            ctx.upstream_s = time.perf_counter() - t0
            if not usage.input_tokens:
                usage = Usage(input_tokens=input_est, source="estimate")
            data["model"] = alias
            await self._settle_success(ctx, adm, usage, endpoint="embeddings")
            return JSONResponse(data, headers=self._headers(ctx, "BYPASS", adm))
        finally:
            await self._finish(adm)

    # ── Admission ───────────────────────────────────────────────────────────

    def _model(self, ctx: RequestContext, alias: str, *, kind: str) -> ModelInfo:
        model = self.catalog.models.get(alias)
        if model is None or model.kind != kind:
            raise NotFoundError(
                f"Model '{alias}' is not configured on this gateway",
                code="model_not_found",
                details={"model": alias},
            )
        return model

    def _facts(
        self, ctx: RequestContext, model: ModelInfo, body: dict[str, Any], est: int
    ) -> RequestFacts:
        requested = body.get("max_completion_tokens") or body.get("max_tokens")
        return RequestFacts(
            project_id=str(ctx.project.id),
            team_id=str(ctx.project.team_id) if ctx.project.team_id else None,
            api_key_id=str(ctx.api_key_id) if ctx.api_key_id else None,
            model_alias=model.alias,
            model_restricted=model.restricted,
            allowed_models=ctx.project.allowed_models,
            input_tokens=est,
            requested_max_output=int(requested) if requested else None,
            model_max_output=model.max_output_tokens,
            context_window=model.context_window,
            default_max_output=self.settings.default_max_output_tokens,
            user_texts=tuple(
                last_user_text({"messages": [m]})
                for m in body.get("messages") or []
                if m.get("role") == "user"
            ),
        )

    async def _admit(self, ctx: RequestContext, body: dict[str, Any]) -> Admission:
        if not isinstance(body.get("messages"), list) or not body["messages"]:
            raise AppError("'messages' must be a non-empty list", code="invalid_request")
        model = self._model(ctx, str(body.get("model") or ""), kind="chat")
        est = estimate_chat_input(body, model.tokenizer)
        facts = self._facts(ctx, model, body, est)

        static = evaluate_static(self.catalog.rules, facts)
        self._alert_all(static.alerts)
        if static.block:
            raise self._violation_error(static.block)

        body = {**body}
        if "max_completion_tokens" in body:
            body["max_completion_tokens"] = static.max_output_tokens
        else:
            body["max_tokens"] = static.max_output_tokens

        adm = Admission(
            model=model,
            body=body,
            input_estimate=est,
            max_output=static.max_output_tokens,
            estimate_nusd=worst_case_cost(model.price, est, static.max_output_tokens),
        )
        try:
            await self._check_limits(ctx, adm)
            await self._stateful_checks(ctx, adm, facts)
        except BaseException:
            await self._finish(adm)
            raise
        return adm

    async def _stateful_checks(
        self, ctx: RequestContext, adm: Admission, facts: RequestFacts
    ) -> None:
        adm.facts = facts
        body = adm.body
        try:
            task_block, task_alerts, adm.task_keys = await self.stateful.check_agent_task(
                self.catalog.rules, facts, ctx.task_id, body, adm.estimate_nusd
            )
            self._alert_all(task_alerts)
            if task_block:
                raise self._violation_error(task_block)
        except RedisError as exc:
            raise DependencyUnavailableError(
                "Policy state unavailable", code="policy_service_unavailable"
            ) from exc

    async def _check_retry_storm(self, ctx: RequestContext, adm: Admission) -> None:
        """Runs only for requests that will reach the provider.

        Identical prompts answered from cache cost nothing, and many users asking the same
        question is normal traffic, so the rule counts repeats per caller (key plus end
        user) and only on the paid path.
        """
        if adm.facts is None:
            return
        try:
            storm, alerts = await self.stateful.check_retry_storm(
                self.catalog.rules,
                adm.facts,
                request_fingerprint(adm.body, adm.model.alias),
                ctx.end_user,
            )
        except RedisError as exc:
            raise DependencyUnavailableError(
                "Policy state unavailable", code="policy_service_unavailable"
            ) from exc
        self._alert_all(alerts)
        if storm:
            raise self._violation_error(storm)

    async def _check_limits(self, ctx: RequestContext, adm: Admission) -> None:
        key = ctx.key
        if key is None:
            return
        try:
            if key.rpm_limit:
                d = await self.limiter.hit(f"rpm:{key.id}", key.rpm_limit)
                if not d.allowed:
                    raise RateLimitedError(
                        f"Rate limit of {key.rpm_limit} requests per minute reached",
                        code="rpm_limit",
                        details={"limit": key.rpm_limit, "window_s": 60},
                        headers={"retry-after": str(d.retry_after_s)},
                    )
            if key.tpm_limit:
                tokens = adm.input_estimate + adm.max_output
                d = await self.limiter.hit(f"tpm:{key.id}", key.tpm_limit, tokens)
                if not d.allowed:
                    raise RateLimitedError(
                        f"Token rate limit of {key.tpm_limit} tokens per minute reached",
                        code="tpm_limit",
                        details={"limit": key.tpm_limit, "requested": tokens},
                        headers={"retry-after": str(d.retry_after_s)},
                    )
                adm.tpm_name, adm.tpm_reserved = f"tpm:{key.id}", tokens
            if key.concurrency_limit:
                name = f"key:{key.id}"
                ttl = int(self.settings.upstream_timeout_s * 2) + 30
                if not await self.limiter.acquire(name, key.concurrency_limit, ttl):
                    raise RateLimitedError(
                        f"Concurrency limit of {key.concurrency_limit} in-flight requests reached",
                        code="concurrency_limit",
                        details={"limit": key.concurrency_limit},
                        headers={"retry-after": "1"},
                    )
                adm.concurrency_name = name
        except RedisError as exc:
            raise DependencyUnavailableError(
                "Rate limiter unavailable", code="rate_limiter_unavailable"
            ) from exc

    def _violation_error(self, v: Violation) -> AppError:
        if v.rule_id:
            _spawn(self._count_rule(v.rule_id))
        details = {"rule": v.rule_name, "kind": v.kind, **v.details}
        headers = {"retry-after": str(v.retry_after_s)} if v.retry_after_s else None
        if v.status == 429:
            return RateLimitedError(v.message, code=v.code, details=details, headers=headers)
        if v.status == 403:
            return PermissionDeniedError(v.message, code=v.code, details=details)
        return PolicyViolationError(v.message, code=v.code, details=details)

    async def _count_rule(self, rule_id: str) -> None:
        with contextlib.suppress(RedisError):
            await self.c.redis.hincrby(POLICY_HITS_KEY, rule_id, 1)

    def _alert_all(self, alerts: list[Violation]) -> None:
        hour = datetime.now(UTC).strftime("%Y%m%d%H")
        for v in alerts:
            if v.rule_id:
                _spawn(self._count_rule(v.rule_id))
            _spawn(
                self.alerts.raise_alert(
                    "policy",
                    f"Policy '{v.rule_name}' matched: {v.message}",
                    dedupe_key=f"policy:{v.rule_id}:{v.code}:{hour}",
                )
            )

    # ── Cache ───────────────────────────────────────────────────────────────

    async def _cache_lookup(
        self, ctx: RequestContext, adm: Admission
    ) -> tuple[CachedResponse, str] | None:
        project = ctx.project
        elig = check_eligibility(
            adm.body,
            project_cache_enabled=project.cache_enabled,
            allow_nondeterministic=project.cache_nondeterministic,
            header=ctx.cache_header,
        )
        if not elig.eligible:
            return None
        scope = ctx.cache_scope
        if scope == "user":
            scope = f"user:{ctx.end_user}" if ctx.end_user else None
            if scope is None:
                return None  # user-scoped caching without a user id would share answers
        part = partition(str(project.id), scope)
        adm.cache_key = exact_key(adm.body, adm.model.alias, part)
        adm.cache_ttl_s = project.cache_ttl_s or self.settings.cache_default_ttl_s

        streaming = bool(adm.body.get("stream"))
        if streaming:
            # Streams are not coalesced: a follower would wait for the whole answer.
            hit = await self.cache.get(adm.cache_key)
            leading = False
        else:
            hit, leading = await self.cache.get_or_lead(adm.cache_key)
            adm.leading = leading
        if hit is not None:
            return hit, "HIT"

        if self.settings.semantic_cache and project.semantic_cache_enabled:
            semantic = await self._semantic_lookup(ctx, adm, part)
            if semantic is not None:
                return semantic, "SEMANTIC_HIT"

        if not streaming and not leading:
            waited = await self.cache.wait_for(adm.cache_key)
            if waited is not None:
                return waited, "COALESCED"
            # The leader gave up: take over so later identical requests can wait on us.
            adm.leading = await self.cache.try_lead(adm.cache_key)
        return None

    async def _semantic_lookup(
        self, ctx: RequestContext, adm: Admission, part: str
    ) -> CachedResponse | None:
        emb_model = self.catalog.models.get(self.settings.semantic_embedding_model)
        text = last_user_text(adm.body)
        if emb_model is None or emb_model.kind != "embedding" or not text:
            return None
        try:
            data, _ = await self.c.adapters.get(emb_model.provider_kind).embeddings(
                self._target(emb_model), {"model": emb_model.alias, "input": text}
            )
            vector = [float(x) for x in data["data"][0]["embedding"]]
        except (UpstreamHTTPError, UpstreamNotSentError, UpstreamUncertainError, KeyError):
            return None
        index = SemanticIndex(self.c.db.sessionmaker, self.settings.semantic_threshold)
        adm.semantic_partition = semantic_partition(adm.body, adm.model.alias, part)
        adm.semantic_vector = vector
        match = await index.nearest(adm.semantic_partition, vector)
        if match is None:
            return None
        return await self.cache.get(match[0])

    async def _serve_cached(
        self,
        ctx: RequestContext,
        adm: Admission,
        cached: CachedResponse,
        status: str,
        stream: bool,
    ) -> Response:
        avoided = actual_cost(
            adm.model.price, cached.input_tokens, cached.cached_input_tokens, cached.output_tokens
        )
        body = {**cached.body, "id": f"chatcmpl-{ctx.request_id}", "created": int(time.time())}
        body["model"] = adm.model.alias
        rec = self._base_record(ctx, adm, "SUCCESS", 200) | {
            "cache_status": status,
            "avoided_cost_nusd": avoided,
            "usage_source": "cache",
            "estimated_input_tokens": adm.input_estimate,
        }
        # One round trip: hit statistics and the usage event together.
        pipe = self.c.redis.pipeline(transaction=False)
        if adm.cache_key and status in ("HIT", "SEMANTIC_HIT"):
            ResponseCache.record_hit(
                pipe, adm.cache_key, cached.input_tokens + cached.output_tokens, avoided
            )
        self.recorder.enqueue(pipe, rec)
        try:
            await pipe.execute()
        except RedisError:
            await self.recorder.write([rec])
        metrics.REQUESTS.labels(adm.model.alias, "SUCCESS", status).inc()
        metrics.AVOIDED.labels(adm.model.alias).inc(nusd_to_usd(avoided))
        headers = self._headers(ctx, status, adm, avoided=avoided)
        if stream:
            return StreamingResponse(
                self._replay(body), media_type="text/event-stream", headers=headers
            )
        return JSONResponse(body, headers=headers)

    @staticmethod
    async def _replay(body: dict[str, Any]) -> AsyncIterator[bytes]:
        """Serve a cached completion as an SSE stream in the OpenAI chunk format."""
        base = {
            "id": body.get("id"),
            "object": "chat.completion.chunk",
            "created": body.get("created"),
            "model": body.get("model"),
        }
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        yield sse(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "finish_reason": None,
                    }
                ],
            }
        )
        yield sse(
            {
                **base,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            }
        )
        yield sse(
            {
                **base,
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason", "stop")}
                ],
            }
        )
        yield SSE_DONE

    # ── Budget reservation ──────────────────────────────────────────────────

    async def _reserve(self, ctx: RequestContext, adm: Admission) -> None:
        now = datetime.now(UTC)
        subject = Subject(
            project_id=ctx.project.id,
            team_id=ctx.project.team_id,
            api_key_id=ctx.api_key_id,
            end_user=ctx.end_user,
            model_alias=adm.model.alias,
        )
        adm.applied = applicable(self.catalog.budgets, subject, now)
        if not adm.applied:
            return
        hard = [a for a in adm.applied if a.counter.hard]
        if adm.model.price is None and hard:
            raise PolicyViolationError(
                f"Model '{adm.model.alias}' has no price in the catalog, so its cost cannot be "
                "checked against hard budgets. Add a price under Models",
                code="model_unpriced",
                details={"model": adm.model.alias, "budgets": [a.budget.name for a in hard]},
            )
        try:
            outcome = await self.c.ledger.reserve(
                [a.counter for a in adm.applied],
                adm.estimate_nusd,
                CounterHydrator(self.c.db.sessionmaker, adm.applied),
            )
        except DependencyUnavailableError:
            if self.settings.budget_failure_mode == "open" or not hard:
                log.warning("budget service down; proceeding (failure mode open or soft only)")
                adm.applied = []
                return
            raise
        if not outcome.ok and outcome.blocked is not None:
            blocked = next(a for a in adm.applied if a.counter.key == outcome.blocked.key)
            b = blocked.budget
            remaining = max(0, b.limit_nusd - outcome.current_nusd)
            raise BudgetExceededError(
                f"Budget '{b.name}' cannot cover this request: estimated "
                f"${nusd_to_usd(adm.estimate_nusd):.6f}, remaining ${nusd_to_usd(remaining):.6f} "
                f"of ${nusd_to_usd(b.limit_nusd):.2f} ({b.period})",
                details={
                    "budget": b.name,
                    "budget_id": str(b.id),
                    "scope": b.scope_type,
                    "period": b.period,
                    "limit_usd": nusd_to_usd(b.limit_nusd),
                    "spent_usd": nusd_to_usd(outcome.current_nusd),
                    "remaining_usd": nusd_to_usd(remaining),
                    "estimated_cost_usd": nusd_to_usd(adm.estimate_nusd),
                },
            )
        adm.reserved = True

    def _counter_keys(self, adm: Admission) -> list[str]:
        return [a.counter.key for a in adm.applied] if adm.reserved else []

    def _reservation_rows(
        self, adm: Admission, actual: int | None, status: str
    ) -> list[ReservationRow]:
        if not adm.reserved:
            return []
        return [
            ReservationRow(a.counter.budget_id, a.counter.key, adm.estimate_nusd, actual, status)
            for a in adm.applied
        ]

    # ── Upstream call ───────────────────────────────────────────────────────

    def _target(self, model: ModelInfo) -> UpstreamTarget:
        return UpstreamTarget(
            base_url=model.base_url,
            api_key=self.catalog.provider_keys.get(model.provider_id),
            upstream_model=model.upstream_model,
            timeout_s=model.timeout_s or self.settings.upstream_timeout_s,
        )

    async def _call(self, ctx: RequestContext, adm: Admission) -> Response:
        adapter = self.c.adapters.get(adm.model.provider_kind)
        t0 = time.perf_counter()
        try:
            with tracer.start_as_current_span("gateway.upstream") as span:
                span.set_attribute("tokenshield.provider", adm.model.provider_name)
                result = await adapter.chat(self._target(adm.model), adm.body)
        except (UpstreamNotSentError, UpstreamHTTPError, UpstreamUncertainError) as exc:
            await self._upstream_failed(ctx, adm, exc)
        ctx.upstream_s = time.perf_counter() - t0
        usage = result.usage
        if usage.source == "estimate" or (not usage.input_tokens and not usage.output_tokens):
            content = ((result.body.get("choices") or [{}])[0].get("message") or {}).get("content")
            usage = Usage(
                input_tokens=adm.input_estimate,
                output_tokens=count_text(content or "", adm.model.tokenizer),
                source="estimate",
            )
        result.body["model"] = adm.model.alias
        cacheable = bool(adm.cache_key) and response_cacheable(result.body)
        cost = await self._settle_success(
            ctx, adm, usage, cache_body=result.body if cacheable else None
        )
        return JSONResponse(
            result.body,
            headers=self._headers(ctx, "MISS" if adm.cache_key else "BYPASS", adm, cost=cost),
        )

    def _stream(
        self, ctx: RequestContext, adm: Admission, idem_lock: str | None
    ) -> StreamingResponse:
        adapter = self.c.adapters.get(adm.model.provider_kind)
        state = StreamState()
        cache_status = "MISS" if adm.cache_key else "BYPASS"

        async def generate() -> AsyncIterator[bytes]:
            t0 = time.perf_counter()
            sent_any = False
            outcome = "pending"
            try:
                async for chunk in adapter.chat_stream(self._target(adm.model), adm.body, state):
                    sent_any = True
                    yield chunk
                outcome = "done"
            except (UpstreamNotSentError, UpstreamHTTPError, UpstreamUncertainError) as exc:
                outcome = "failed"
                try:
                    await self._upstream_failed(ctx, adm, exc, stream=True, partial=sent_any)
                except AppError as err:
                    yield sse(err.body())
                    yield SSE_DONE
            finally:
                ctx.upstream_s = time.perf_counter() - t0
                # Starlette cancels this generator when the client disconnects. Accounting
                # must still complete, so it runs as a shielded task.
                cleanup = asyncio.ensure_future(finalize(outcome))
                _background.add(cleanup)
                cleanup.add_done_callback(_background.discard)
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(cleanup)

        async def finalize(outcome: str) -> None:
            try:
                if outcome == "done":
                    usage = state.usage or Usage(
                        input_tokens=adm.input_estimate,
                        output_tokens=count_text("".join(state.text), adm.model.tokenizer),
                        source="estimate",
                    )
                    body: dict[str, Any] | None = None
                    if adm.cache_key and state.finish_reason == "stop" and not state.tool_calls:
                        body = {
                            "id": state.response_id or "",
                            "object": "chat.completion",
                            "created": state.created or int(time.time()),
                            "model": adm.model.alias,
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": "".join(state.text),
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                    await self._settle_success(ctx, adm, usage, stream=True, cache_body=body)
                elif outcome == "pending":
                    # Client disconnected mid-stream. The provider may keep generating and
                    # billing, so the cost is unknown: hold the reservation as UNCERTAIN.
                    adm.tokens_settled = True
                    await self._record_uncertain(
                        ctx, adm, "client disconnected mid-stream", stream=True
                    )
            except Exception:
                log.exception("stream accounting failed", extra={"request_id": ctx.request_id})
            finally:
                await self._finish(adm)
                await self._release_idem(idem_lock)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers=self._headers(ctx, cache_status, adm),
        )

    async def _upstream_failed(
        self,
        ctx: RequestContext,
        adm: Admission,
        exc: Exception,
        *,
        endpoint: str = "chat",
        stream: bool = False,
        partial: bool = False,
    ) -> NoReturn:
        """Account for a failed provider call, then raise the client-facing error."""
        if isinstance(exc, UpstreamUncertainError) or partial:
            adm.tokens_settled = True  # unknown usage: keep the TPM charge
            await self._record_uncertain(
                ctx, adm, f"upstream: {exc}", stream=stream, endpoint=endpoint
            )
            raise UpstreamTimeoutError(
                "The provider did not answer in time. The request may still have been "
                "processed; its cost is held until reconciled",
                details={"request_id": ctx.request_id},
            )
        # Not sent, or an error status: the provider did not bill a completion.
        await self.c.ledger.adjust(self._counter_keys(adm), -adm.estimate_nusd)
        if isinstance(exc, UpstreamHTTPError):
            status = exc.status if exc.status in (400, 401, 403, 404, 409, 422, 429) else 502
            message = f"Provider error: {exc.message}"
        else:
            status, message = 502, f"Provider unreachable: {exc}"
        rec = self._base_record(ctx, adm, "ERROR", status) | {
            "reason": message[:500],
            "estimated_input_tokens": adm.input_estimate,
            "estimated_cost_nusd": adm.estimate_nusd,
            "stream": stream,
            "endpoint": endpoint,
            "reservations": self._reservation_rows(adm, 0, "released"),
        }
        await self.recorder.record(rec)
        metrics.REQUESTS.labels(adm.model.alias, "ERROR", "BYPASS").inc()
        err = UpstreamError(
            message,
            code="upstream_error",
            details={"provider_status": getattr(exc, "status", None)},
        )
        err.status_code = status
        raise err

    async def _record_uncertain(
        self,
        ctx: RequestContext,
        adm: Admission,
        reason: str,
        *,
        stream: bool,
        endpoint: str = "chat",
    ) -> None:
        rec = self._base_record(ctx, adm, "UNCERTAIN", 504) | {
            "reason": reason[:500],
            "estimated_input_tokens": adm.input_estimate,
            "estimated_cost_nusd": adm.estimate_nusd,
            "usage_source": "none",
            "stream": stream,
            "endpoint": endpoint,
            "reservations": self._reservation_rows(adm, None, "uncertain"),
        }
        await self.recorder.record(rec)
        metrics.REQUESTS.labels(adm.model.alias, "UNCERTAIN", "BYPASS").inc()

    async def _settle_success(
        self,
        ctx: RequestContext,
        adm: Admission,
        usage: Usage,
        *,
        endpoint: str = "chat",
        stream: bool = False,
        cache_body: dict[str, Any] | None = None,
    ) -> int:
        """Reconcile, account and cache in a single Redis round trip."""
        price = adm.model.price
        cost = actual_cost(
            price, usage.input_tokens, usage.cached_input_tokens, usage.output_tokens
        )
        pipe = self.c.redis.pipeline(transaction=False)
        self.c.ledger.adjust_in(pipe, self._counter_keys(adm), cost - adm.estimate_nusd)
        if adm.tpm_name:
            adm.tokens_settled = True
            self.limiter.correct_in(
                pipe, adm.tpm_name, usage.input_tokens + usage.output_tokens - adm.tpm_reserved
            )
        if adm.task_keys:
            _spawn(self.stateful.charge_tasks(adm.task_keys, cost))
        rec = self._base_record(ctx, adm, "SUCCESS", 200) | {
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_input_tokens": adm.input_estimate,
            "usage_source": usage.source,
            "estimated_cost_nusd": adm.estimate_nusd,
            "actual_cost_nusd": cost,
            "cache_status": "MISS" if adm.cache_key else "BYPASS",
            "stream": stream,
            "endpoint": endpoint,
            "reservations": self._reservation_rows(adm, cost, "settled"),
        }
        self.recorder.enqueue(pipe, rec)
        if cache_body is not None and adm.cache_key:
            await self._store_cache(ctx, adm, cache_body, usage, pipe)
            if adm.leading:
                ResponseCache.release_lead_in(pipe, adm.cache_key)
                adm.leading = False
        try:
            await pipe.execute()
        except RedisError:
            # Counters stay at the reservation (the safe direction); the record is not lost.
            log.warning("settlement pipeline failed; recording directly")
            await self.recorder.write([rec])
        model = adm.model.alias
        metrics.REQUESTS.labels(model, "SUCCESS", rec.cache_status).inc()
        metrics.TOKENS.labels(model, "input").inc(usage.input_tokens)
        metrics.TOKENS.labels(model, "output").inc(usage.output_tokens)
        metrics.COST.labels(model).inc(nusd_to_usd(cost))
        metrics.UPSTREAM_LATENCY.labels(model).observe(ctx.upstream_s)
        metrics.OVERHEAD.observe(max(0.0, (time.perf_counter() - ctx.started) - ctx.upstream_s))
        if adm.reserved:
            _spawn(self._threshold_alerts(adm))
        return cost

    async def _store_cache(
        self,
        ctx: RequestContext,
        adm: Admission,
        body: dict[str, Any],
        usage: Usage,
        pipe: Pipeline | None = None,
    ) -> None:
        assert adm.cache_key is not None
        excerpt = last_user_text(adm.body)[:200] if self.settings.store_content else None
        await self.cache.put(
            adm.cache_key,
            body,
            ttl_s=adm.cache_ttl_s,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            output_tokens=usage.output_tokens,
            project_id=str(ctx.project.id),
            model_alias=adm.model.alias,
            excerpt=excerpt,
            pipe=pipe,
        )
        if adm.semantic_partition and adm.semantic_vector:
            index = SemanticIndex(self.c.db.sessionmaker, self.settings.semantic_threshold)
            _spawn(
                index.add(
                    adm.semantic_partition, adm.cache_key, adm.semantic_vector, adm.cache_ttl_s
                )
            )

    async def _threshold_alerts(self, adm: Admission) -> None:
        try:
            values = await self.c.ledger.current([a.counter.key for a in adm.applied])
        except RedisError:
            return
        for a, value in zip(adm.applied, values, strict=True):
            if value is None:
                continue
            b = a.budget
            pct = value * 100 // max(1, b.limit_nusd)
            if pct < b.alert_threshold_pct and not (b.mode == "soft" and value > b.limit_nusd):
                continue
            over = value > b.limit_nusd
            level = "exceeded" if over else f"{b.alert_threshold_pct}%"
            await self.alerts.raise_alert(
                "budget",
                f"Budget '{b.name}' is at {pct}% (${nusd_to_usd(value):.2f} of "
                f"${nusd_to_usd(b.limit_nusd):.2f}, {b.period})",
                dedupe_key=f"budget:{a.counter.key}:{level}",
                severity="critical" if over else "warning",
                budget_id=b.id,
            )

    # ── Accounting helpers ──────────────────────────────────────────────────

    def _base_record(
        self, ctx: RequestContext, adm: Admission | None, status: str, http_status: int
    ) -> _Rec:
        model = adm.model if adm else None
        return _Rec(
            request_id=ctx.request_id,
            status=status,
            http_status=http_status,
            project_id=ctx.project.id,
            team_id=ctx.project.team_id,
            api_key_id=ctx.api_key_id,
            source=ctx.source,
            end_user=ctx.end_user,
            task_id=ctx.task_id,
            model_alias=model.alias if model else None,
            provider=model.provider_name if model else None,
            upstream_model=model.upstream_model if model else None,
            price_id=model.price.id if model and model.price else None,
            priced=bool(model and model.price) if model else True,
            latency_ms=ctx.elapsed_ms(),
            prompt_excerpt=(
                last_user_text(adm.body)[:500] if adm and self.settings.store_content else None
            ),
        )

    async def _record_rejection(
        self,
        ctx: RequestContext,
        alias: str,
        err: AppError,
        *,
        stream: bool = False,
        endpoint: str = "chat",
        adm: Admission | None = None,
    ) -> None:
        if err.code == "request_in_progress":
            return
        model = self.catalog.models.get(alias)
        rec = UsageRecord(
            request_id=ctx.request_id if err.code != "idempotent_replay" else new_request_id(),
            status="REJECTED",
            http_status=err.status_code,
            project_id=ctx.project.id,
            team_id=ctx.project.team_id,
            api_key_id=ctx.api_key_id,
            source=ctx.source,
            end_user=ctx.end_user,
            task_id=ctx.task_id,
            endpoint=endpoint,
            model_alias=alias or None,
            provider=model.provider_name if model else None,
            upstream_model=model.upstream_model if model else None,
            estimated_input_tokens=adm.input_estimate if adm else 0,
            estimated_cost_nusd=adm.estimate_nusd if adm else 0,
            priced=bool(model.price) if model else True,
            rule=err.code[:40],
            reason=err.message[:500],
            latency_ms=ctx.elapsed_ms(),
            stream=stream,
        )
        try:
            await self.recorder.record(rec)
        except Exception:  # accounting of a rejection must never mask the rejection itself
            log.exception("failed to record rejection")
        metrics.REQUESTS.labels(alias or "unknown", "REJECTED", "BYPASS").inc()
        metrics.REJECTIONS.labels(err.code).inc()
        log.info(
            "request rejected",
            extra={
                "event": "budget_rejected" if err.code == "budget_exceeded" else "request_rejected",
                "rule": err.code,
                "status": err.status_code,
                "project_id": str(ctx.project.id),
            },
        )

    def _headers(
        self,
        ctx: RequestContext,
        cache: str,
        adm: Admission,
        *,
        cost: int | None = None,
        avoided: int | None = None,
    ) -> dict[str, str]:
        headers = {
            "x-tokenshield-request-id": ctx.request_id,
            "x-tokenshield-cache": cache,
            "x-tokenshield-estimated-cost-usd": f"{nusd_to_usd(adm.estimate_nusd):.9f}",
        }
        if cost is not None:
            headers["x-tokenshield-cost-usd"] = f"{nusd_to_usd(cost):.9f}"
        if avoided is not None:
            headers["x-tokenshield-avoided-cost-usd"] = f"{nusd_to_usd(avoided):.9f}"
        if adm.model.price is None:
            headers["x-tokenshield-priced"] = "false"
        return headers

    async def _finish(self, adm: Admission | None) -> None:
        if adm is None:
            return
        if adm.tpm_name and not adm.tokens_settled:
            with contextlib.suppress(RedisError):
                await self.limiter.correct(adm.tpm_name, -adm.tpm_reserved)
            adm.tpm_name = None
        if adm.concurrency_name:
            try:
                await self.limiter.release(adm.concurrency_name)
            except RedisError:
                log.warning("could not release concurrency slot; it expires on its own")
            adm.concurrency_name = None
        if adm.leading and adm.cache_key:
            await self.cache.release_lead(adm.cache_key)
            adm.leading = False

    # ── Idempotency ─────────────────────────────────────────────────────────

    async def _idempotency_begin(self, ctx: RequestContext) -> tuple[Response | None, str | None]:
        rid = ctx.request_id
        redis = self.c.redis
        try:
            stored = await redis.get(f"ts:idem:resp:{rid}")
            if stored is not None:
                data = orjson.loads(stored)
                return JSONResponse(
                    data["body"],
                    status_code=data["status"],
                    headers={
                        "x-tokenshield-request-id": rid,
                        "x-tokenshield-idempotent-replay": "true",
                    },
                ), None
            if not await redis.set(
                f"ts:idem:lock:{rid}", b"1", nx=True, ex=int(self.settings.upstream_timeout_s) + 60
            ):
                raise ConflictError(
                    "A request with this Idempotency-Key is still in progress",
                    code="request_in_progress",
                    details={"request_id": rid},
                )
        except RedisError as exc:
            raise DependencyUnavailableError("Idempotency store unavailable") from exc
        return None, rid

    async def _idempotency_store(self, rid: str, response: Response) -> None:
        if not isinstance(response, JSONResponse):
            return
        try:
            await self.c.redis.set(
                f"ts:idem:resp:{rid}",
                orjson.dumps(
                    {"status": response.status_code, "body": orjson.loads(bytes(response.body))}
                ),
                ex=IDEMPOTENCY_TTL_S,
            )
        except RedisError:
            log.warning("could not store idempotent response")
        await self._release_idem(rid)

    async def _release_idem(self, rid: str | None) -> None:
        if rid is None:
            return
        try:
            await self.c.redis.delete(f"ts:idem:lock:{rid}")
        except RedisError:
            return


class _Rec(UsageRecord):
    """UsageRecord with ``|`` to derive a variant with some fields replaced."""

    def __or__(self, changes: dict[str, Any]) -> _Rec:
        return replace(self, **changes)
