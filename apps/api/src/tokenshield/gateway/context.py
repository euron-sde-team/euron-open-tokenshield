"""Per-request state carried through the pipeline."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from tokenshield.gateway.catalog import KeyInfo, ProjectInfo


@dataclass(slots=True)
class RequestContext:
    request_id: str
    project: ProjectInfo
    key: KeyInfo | None
    source: str = "api"  # api | playground
    end_user: str | None = None
    task_id: str | None = None
    cache_header: str | None = None
    cache_scope: str | None = None
    idempotency_key: str | None = None
    started: float = field(default_factory=time.perf_counter)
    upstream_s: float = 0.0

    @property
    def api_key_id(self) -> uuid.UUID | None:
        return self.key.id if self.key else None

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)
