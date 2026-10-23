from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from tokenshield.core.schemas import ApiModel


class ProjectIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=2000)
    team_id: uuid.UUID | None = None
    cache_enabled: bool = True
    cache_ttl_s: int = Field(3600, ge=10, le=30 * 86400)
    cache_nondeterministic: bool = False
    semantic_cache_enabled: bool = False
    allowed_models: list[str] | None = Field(
        None, description="Model aliases this project may use; null allows every unrestricted model"
    )


class ProjectUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    team_id: uuid.UUID | None = None
    cache_enabled: bool | None = None
    cache_ttl_s: int | None = Field(None, ge=10, le=30 * 86400)
    cache_nondeterministic: bool | None = None
    semantic_cache_enabled: bool | None = None
    allowed_models: list[str] | None = None
    archived: bool | None = None


class ProjectOut(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    team_id: uuid.UUID | None
    team_name: str | None = None
    cache_enabled: bool
    cache_ttl_s: int
    cache_nondeterministic: bool
    semantic_cache_enabled: bool
    allowed_models: list[str] | None
    archived: bool
    created_at: datetime
    key_count: int = 0
