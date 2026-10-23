from tokenshield.gateway.tokens import (
    IMAGE_TOKENS,
    count_text,
    estimate_chat_input,
    estimate_embedding_input,
    last_user_text,
)


def test_tiktoken_counts() -> None:
    assert count_text("hello world", "o200k_base") == 2
    assert count_text("", "o200k_base") == 0


def test_fallback_estimate_is_chars_over_four_rounded_up() -> None:
    assert count_text("abcde", "llama") == 2
    assert count_text("abcd", "unknown") == 1


def test_chat_estimate_counts_framing_tools_and_images() -> None:
    simple = {"messages": [{"role": "user", "content": "hello world"}]}
    assert estimate_chat_input(simple, "o200k_base") == 3 + 3 + 2
    with_tools = {
        **simple,
        "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
    }
    assert estimate_chat_input(with_tools, "o200k_base") > estimate_chat_input(simple, "o200k_base")
    image = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this"},
                    {"type": "image_url", "image_url": {"url": "x"}},
                ],
            }
        ]
    }
    assert estimate_chat_input(image, "o200k_base") >= IMAGE_TOKENS


def test_embedding_estimate() -> None:
    assert estimate_embedding_input({"input": "hello world"}, "o200k_base") == 2
    assert estimate_embedding_input({"input": ["a b", "c"]}, "o200k_base") >= 2
    assert estimate_embedding_input({"input": None}, "o200k_base") == 0


def test_last_user_text() -> None:
    body = {
        "messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "x"},
            {"role": "user", "content": [{"type": "text", "text": "second"}]},
        ]
    }
    assert last_user_text(body) == "second"
    assert last_user_text({"messages": []}) == ""
