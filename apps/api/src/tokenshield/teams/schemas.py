from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from tokenshield.core.schemas import ApiModel


class TeamIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=2000)


class TeamUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class TeamOut(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    created_at: datetime
    project_count: int = 0
