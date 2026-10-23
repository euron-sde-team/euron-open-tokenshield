from typing import Any

from tokenshield.cache.keys import (
    check_eligibility,
    exact_key,
    partition,
    request_fingerprint,
    response_cacheable,
    semantic_partition,
)

BODY: dict[str, Any] = {
    "model": "chat-small",
    "temperature": 0,
    "messages": [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "What is photosynthesis?"},
    ],
}


def key(body: dict[str, Any] | None = None, alias: str = "chat-small", part: str = "p1") -> str:
    return exact_key(body or BODY, alias, part)


def test_identical_requests_share_a_key_whitespace_ignored() -> None:
    body = {
        **BODY,
        "messages": [
            BODY["messages"][0],
            {"role": "user", "content": "  What is photosynthesis?  "},
        ],
        "user": "u1",
        "stream": True,
    }
    assert key(body) == key()


def test_everything_that_changes_the_answer_changes_the_key() -> None:
    base = key()
    assert key(alias="chat-large") != base
    assert key(part="p2") != base
    assert key({**BODY, "temperature": 0.5}) != base
    assert key({**BODY, "max_tokens": 10}) != base
    assert key({**BODY, "tools": [{"type": "function", "function": {"name": "f"}}]}) != base
    assert key({**BODY, "response_format": {"type": "json_object"}}) != base
    system = {
        **BODY,
        "messages": [{"role": "system", "content": "Be verbose."}, BODY["messages"][1]],
    }
    assert key(system) != base


def test_partition_isolates_projects_and_scopes() -> None:
    assert partition("proj", None) != partition("proj", "user:a")
    assert partition("proj", "user:a") != partition("proj", "user:b")
    assert partition("proj-a", None) != partition("proj-b", None)


def test_semantic_partition_ignores_last_user_turn_only() -> None:
    a = semantic_partition(BODY, "chat-small", "p")
    reworded = {
        **BODY,
        "messages": [BODY["messages"][0], {"role": "user", "content": "Explain photosynthesis"}],
    }
    assert semantic_partition(reworded, "chat-small", "p") == a
    other_system = {
        **BODY,
        "messages": [{"role": "system", "content": "Pirate voice"}, BODY["messages"][1]],
    }
    assert semantic_partition(other_system, "chat-small", "p") != a


def test_fingerprint_is_scope_independent() -> None:
    assert request_fingerprint(BODY, "chat-small") == request_fingerprint(BODY, "chat-small")
    assert request_fingerprint(BODY, "chat-small") != request_fingerprint(BODY, "chat-large")


def elig(body: dict[str, Any], **kw: Any) -> bool:
    args = {"project_cache_enabled": True, "allow_nondeterministic": False, "header": None} | kw
    return check_eligibility(body, **args).eligible


def test_eligibility_rules() -> None:
    assert elig(BODY)
    assert not elig({**BODY, "temperature": 0.7})
    assert not elig({k: v for k, v in BODY.items() if k != "temperature"}), (
        "absent temperature means sampled"
    )
    assert elig({**BODY, "temperature": 0.7}, allow_nondeterministic=True)
    assert not elig(BODY, project_cache_enabled=False)
    for header in ("off", "no-store", "BYPASS", "0"):
        assert not elig(BODY, header=header)
    assert not elig({**BODY, "n": 2})
    assert not elig({**BODY, "logprobs": True})


def test_only_complete_text_answers_are_cacheable() -> None:
    ok = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    assert response_cacheable(ok)
    assert not response_cacheable(
        {"choices": [{"message": {"content": "hi"}, "finish_reason": "length"}]}
    )
    assert not response_cacheable(
        {
            "choices": [
                {"message": {"content": None, "tool_calls": [{}]}, "finish_reason": "tool_calls"}
            ]
        }
    )
    assert not response_cacheable({"choices": []})
