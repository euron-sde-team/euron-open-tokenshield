"""Runtime configuration, validated once at boot.

Every setting comes from the environment. Security-relevant settings are checked by
``Settings.guard`` so a misconfigured production deployment refuses to start instead of
running with demo secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_SECRETS = {"", "change-me", "replace-with-output-of-make-env", "dev", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    cloud: Literal["local", "floci", "aws"] = Field("local", alias="TOKENSHIELD_CLOUD")
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://tokenshield:tokenshield@localhost:4142/tokenshield"
    redis_url: str = "redis://localhost:4179/0"

    # Signing secret for dashboard sessions and pepper for API key hashes. Separate values so
    # rotating sessions does not invalidate every gateway key.
    session_secret: str = "dev-session-secret-not-for-production"  # noqa: S105 dev default, refused in production by guard()
    api_key_pepper: str = "dev-api-key-pepper-not-for-production"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    # NoDecode: read the env value as a plain comma-separated string, not JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4110"]
    )

    # Provider credentials are sealed before they reach the database.
    # local: AES-GCM with LOCAL_MASTER_KEY. kms: AWS KMS (Floci locally).
    key_mode: Literal["local", "kms"] = "local"
    local_master_key: str = "dev-local-master-key-not-for-production"
    kms_key_id: str = "alias/tokenshield-local"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_force_path_style: bool = False
    s3_public_endpoint: str | None = None
    exports_bucket: str = "tokenshield-local-exports"
    storage: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./.data/exports"

    # Gateway behaviour
    upstream_timeout_s: float = 60.0
    # Without a Redis answer we cannot prove a hard budget has room, so the default is to
    # refuse. Set to "open" only for deployments where availability beats spend control.
    budget_failure_mode: Literal["closed", "open"] = "closed"
    default_max_output_tokens: int = 1024
    cache_default_ttl_s: int = 3600
    coalesce_wait_s: float = 30.0
    uncertain_settle_after_s: int = 900
    semantic_cache: bool = False
    semantic_threshold: float = 0.92
    semantic_embedding_model: str = "embed-small"
    store_content: bool = False

    otel_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def guard(self) -> None:
        """Refuse to boot in production with demo secrets or unsafe options."""
        if self.environment != "production":
            return
        problems: list[str] = []
        for name in ("session_secret", "api_key_pepper"):
            value = getattr(self, name)
            if value in INSECURE_SECRETS or "not-for-production" in value or len(value) < 32:
                problems.append(f"{name.upper()} must be a random value of at least 32 chars")
        if self.key_mode == "local" and (
            "not-for-production" in self.local_master_key or len(self.local_master_key) < 32
        ):
            problems.append("LOCAL_MASTER_KEY must be set (or use KEY_MODE=kms)")
        if self.session_secret == self.api_key_pepper:
            problems.append("SESSION_SECRET and API_KEY_PEPPER must differ")
        if self.cloud == "aws" and self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL must be unset when TOKENSHIELD_CLOUD=aws")
        if self.cloud == "aws" and self.budget_failure_mode == "open":
            problems.append("BUDGET_FAILURE_MODE=open is refused on aws; hard budgets fail closed")
        if problems:
            raise RuntimeError("unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.guard()
    return settings
