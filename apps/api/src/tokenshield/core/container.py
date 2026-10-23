"""Process-wide services, built once in the app lifespan and shared by every request.

Holding them in one object (on ``app.state``) instead of module globals keeps the app
factory re-entrant and lets tests build an isolated container per app.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from tokenshield.budgets.ledger import BudgetLedger
from tokenshield.core.aws import aws_client
from tokenshield.core.cache import ConfigCache
from tokenshield.core.config import Settings
from tokenshield.core.db import Database
from tokenshield.core.redis_client import create_redis
from tokenshield.core.sealing import KeySealer, KmsSealer, LocalSealer
from tokenshield.core.storage import LocalStorage, ObjectStorage, S3Storage
from tokenshield.providers.adapters.http import build_client
from tokenshield.providers.adapters.registry import AdapterRegistry


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    http: httpx.AsyncClient
    config_cache: ConfigCache
    ledger: BudgetLedger
    adapters: AdapterRegistry
    sealer: KeySealer
    storage: ObjectStorage

    @classmethod
    def build(cls, settings: Settings) -> Container:
        redis = create_redis(settings.redis_url)
        http = build_client()
        sealer: KeySealer = (
            KmsSealer(aws_client(settings, "kms"), settings.kms_key_id)
            if settings.key_mode == "kms"
            else LocalSealer(settings.local_master_key)
        )
        storage: ObjectStorage = (
            S3Storage(
                aws_client(settings, "s3"),
                settings.exports_bucket,
                aws_client(settings, "s3", public=True),
            )
            if settings.storage == "s3"
            else LocalStorage(settings.local_storage_dir)
        )
        return cls(
            settings=settings,
            db=Database(settings.database_url),
            redis=redis,
            http=http,
            config_cache=ConfigCache(redis),
            ledger=BudgetLedger(redis),
            adapters=AdapterRegistry(http),
            sealer=sealer,
            storage=storage,
        )

    async def close(self) -> None:
        await self.http.aclose()
        await self.redis.aclose()
        await self.db.dispose()
