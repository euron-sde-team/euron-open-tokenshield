from tokenshield.providers.adapters.anthropic import to_anthropic, to_openai, usage_from
from tokenshield.providers.adapters.openai import parse_usage


def test_openai_request_translates_to_messages_api() -> None:
    body = {
        "model": "claude-sonnet",
        "max_tokens": 300,
        "temperature": 0.2,
        "stop": "END",
        "user": "u-1",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "and"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            },
            {
                "role": "assistant",
                "content": "Calling",
                "tool_calls": [
                    {
                        "id": "t1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "result"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "d",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "tool_choice": "required",
    }
    out = to_anthropic(body, "claude-x")
    assert out["model"] == "claude-x"
    assert out["system"] == "Be brief."
    assert out["max_tokens"] == 300 and out["temperature"] == 0.2
    assert out["stop_sequences"] == ["END"]
    assert out["metadata"] == {"user_id": "u-1"}
    roles = [m["role"] for m in out["messages"]]
    assert roles == ["user", "assistant", "user"], "consecutive user turns merge"
    merged_user = out["messages"][0]["content"]
    assert any(b.get("type") == "image" and b["source"]["type"] == "base64" for b in merged_user)
    assistant = out["messages"][1]["content"]
    assert assistant[1] == {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "x"}}
    assert out["messages"][2]["content"][0]["type"] == "tool_result"
    assert out["tools"][0]["input_schema"] == {"type": "object"}
    assert out["tool_choice"] == {"type": "any"}


def test_default_max_tokens_and_tool_choice_variants() -> None:
    assert to_anthropic({"messages": [{"role": "user", "content": "x"}]}, "m")["max_tokens"] == 1024
    named = to_anthropic(
        {
            "messages": [],
            "tools": [{"type": "function", "function": {"name": "f"}}],
            "tool_choice": {"type": "function", "function": {"name": "f"}},
        },
        "m",
    )
    assert named["tool_choice"] == {"type": "tool", "name": "f"}


def test_response_translates_to_chat_completion() -> None:
    data = {
        "id": "msg_1",
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "Let me check"},
            {"type": "tool_use", "id": "t", "name": "f", "input": {"a": 1}},
        ],
        "usage": {
            "input_tokens": 100,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 10,
            "output_tokens": 20,
        },
    }
    out = to_openai(data, "claude-sonnet")
    choice = out["choices"][0]
    assert out["model"] == "claude-sonnet"
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] == "Let me check"
    assert choice["message"]["tool_calls"][0]["function"] == {"name": "f", "arguments": '{"a":1}'}
    assert out["usage"] == {
        "prompt_tokens": 160,
        "completion_tokens": 20,
        "total_tokens": 180,
        "prompt_tokens_details": {"cached_tokens": 50},
    }


def test_usage_parsers() -> None:
    u = usage_from({"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 3})
    assert (u.input_tokens, u.cached_input_tokens, u.output_tokens) == (15, 5, 3)
    o = parse_usage(
        {"prompt_tokens": 7, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 4}}
    )
    assert o is not None and (o.input_tokens, o.cached_input_tokens, o.output_tokens) == (7, 4, 2)
    assert parse_usage(None) is None
