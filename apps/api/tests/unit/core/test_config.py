import pytest

from tokenshield.core.config import Settings

STRONG = "x" * 40


def prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "session_secret": STRONG,
        "api_key_pepper": "y" * 40,
        "local_master_key": "z" * 40,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_development_defaults_boot() -> None:
    Settings().guard()


def test_production_with_strong_secrets_boots() -> None:
    prod().guard()


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"session_secret": "dev-session-secret-not-for-production"}, "SESSION_SECRET"),
        ({"api_key_pepper": "short"}, "API_KEY_PEPPER"),
        ({"local_master_key": "dev-local-master-key-not-for-production"}, "LOCAL_MASTER_KEY"),
        ({"api_key_pepper": STRONG}, "must differ"),
        ({"TOKENSHIELD_CLOUD": "aws", "aws_endpoint_url": "http://floci:4566"}, "AWS_ENDPOINT_URL"),
        ({"TOKENSHIELD_CLOUD": "aws", "budget_failure_mode": "open"}, "fail closed"),
    ],
)
def test_production_guards(overrides: dict[str, object], fragment: str) -> None:
    with pytest.raises(RuntimeError, match=fragment):
        prod(**overrides).guard()


def test_kms_mode_does_not_need_local_master_key() -> None:
    prod(key_mode="kms", local_master_key="dev-local-master-key-not-for-production").guard()


def test_cors_origins_accept_comma_string() -> None:
    s = Settings(cors_origins="http://a.test, http://b.test")  # type: ignore[arg-type]
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:4110,http://127.0.0.1:4110")
    assert Settings().cors_origins == ["http://localhost:4110", "http://127.0.0.1:4110"]
