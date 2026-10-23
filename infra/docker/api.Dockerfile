# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# API: the gateway and admin API (`tokenshield serve`), the background worker
# (`tokenshield worker`), the one-off CLI (`migrate`, `seed-demo`, `create-owner`)
# and the deterministic mock LLM upstream used by the demo and the tests
# (`uvicorn mockllm.app:app --port 4150`). Same image, different command.
#   docker build -f infra/docker/api.Dockerfile -t tokenshield-api apps/api
# ─────────────────────────────────────────────────────────────────────────────
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.9.17 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /bin/
# Bytecode is compiled here because the runtime root filesystem is read-only.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first, from the lockfile only, so source edits reuse this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src src
# Installed as a wheel (not editable): the runtime stage copies only /opt/venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable
# tiktoken downloads its encodings on first use; fetch them now so the container
# needs no internet access to count tokens and starts with a warm cache.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN /opt/venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken TZ=UTC PORT=8080
# tini reaps zombies and forwards SIGTERM so uvicorn drains in-flight completions (and
# releases their budget reservations) and the worker finishes its current job.
# /data/exports holds exports with STORAGE=local; a named volume mounted there inherits
# its ownership. With STORAGE=s3 it stays empty.
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 tokenshield \
 && useradd --system --uid 10001 --gid tokenshield --home-dir /app --no-create-home \
      --shell /usr/sbin/nologin tokenshield \
 && mkdir -p /data/exports && chown tokenshield:tokenshield /data/exports
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/tiktoken /opt/tiktoken
# Nothing else to copy: the Alembic migrations ship inside the tokenshield package and
# `tokenshield migrate` runs them programmatically.
USER 10001:10001
EXPOSE 8080 4150
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8080'), timeout=2).status == 200 else 1)"
ENTRYPOINT ["/usr/bin/tini", "--", "tokenshield"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
