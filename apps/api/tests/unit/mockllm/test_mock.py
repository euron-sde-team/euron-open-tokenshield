from mockllm.app import _answer, _cached, _embed, _truncate


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_embeddings_are_similar_for_similar_questions() -> None:
    a = _embed("What is photosynthesis?")
    b = _embed("Please explain photosynthesis")
    c = _embed("How do I reset my password?")
    assert _cos(a, b) > 0.9 > _cos(a, c)


def test_answers_are_deterministic_and_truncate() -> None:
    assert _answer("What is photosynthesis?") == _answer("what is PHOTOSYNTHESIS")
    _text, tokens, finish = _truncate("one two three four five six", 3)
    assert tokens == 3 and finish == "length"
    assert _truncate("short", None)[2] == "stop"


def test_cached_tokens_only_for_long_prompts() -> None:
    assert _cached(500) == 0
    assert _cached(4096) == 2048
