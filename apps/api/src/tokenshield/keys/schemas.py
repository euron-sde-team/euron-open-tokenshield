from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from tokenshield.core.schemas import ApiModel


class KeyIn(ApiModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    rpm_limit: int | None = Field(None, ge=1, le=1_000_000)
    tpm_limit: int | None = Field(None, ge=1, le=1_000_000_000)
    concurrency_limit: int | None = Field(None, ge=1, le=10_000)
    expires_at: datetime | None = None


class KeyUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    rpm_limit: int | None = Field(None, ge=1, le=1_000_000)
    tpm_limit: int | None = Field(None, ge=1, le=1_000_000_000)
    concurrency_limit: int | None = Field(None, ge=1, le=10_000)
    expires_at: datetime | None = None


class KeyOut(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    name: str
    prefix: str
    display: str = Field(description="Safe identifier: tsk_<prefix>_****")
    rpm_limit: int | None
    tpm_limit: int | None
    concurrency_limit: int | None
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class KeyCreated(KeyOut):
    key: str = Field(description="The full key. Shown once; store it now")
