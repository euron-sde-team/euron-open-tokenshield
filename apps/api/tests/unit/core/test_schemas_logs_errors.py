import json
import logging

import pytest
from pydantic import BaseModel, ValidationError

from tokenshield.core.errors import BudgetExceededError, RateLimitedError
from tokenshield.core.logs import JsonFormatter, request_id_var
from tokenshield.core.schemas import Email, decode_cursor, encode_cursor
from tokenshield.core.text import slugify


class EmailModel(BaseModel):
    email: Email


def test_cursor_round_trip_and_garbage() -> None:
    assert decode_cursor(encode_cursor(12345)) == "12345"
    assert decode_cursor(None) is None
    assert decode_cursor("@@@") in (None, "")


def test_email_accepts_internal_domains_and_lowercases() -> None:
    assert EmailModel(email=" Admin@Corp.Local ").email == "admin@corp.local"
    with pytest.raises(ValidationError):
        EmailModel(email="not-an-email")


def test_slugify() -> None:
    assert slugify("Alpha Tutor!") == "alpha-tutor"
    assert slugify("***") == "item"
    assert len(slugify("x" * 200)) == 64


def test_error_body_is_openai_compatible() -> None:
    err = BudgetExceededError("over", details={"budget": "b"})
    body = err.body()["error"]
    assert body == {
        "code": "budget_exceeded",
        "type": "budget_error",
        "message": "over",
        "details": {"budget": "b"},
    }
    assert err.status_code == 402
    assert RateLimitedError("x", headers={"retry-after": "3"}).headers["retry-after"] == "3"


def test_json_logs_redact_secrets_and_carry_request_id() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.authorization = "Bearer tsk_abc"
    record.path = "/v1/chat"
    token = request_id_var.set("rid-1")
    try:
        out = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert out["authorization"] == "[redacted]"
    assert out["path"] == "/v1/chat"
    assert out["request_id"] == "rid-1"
    assert out["msg"] == "hello"
