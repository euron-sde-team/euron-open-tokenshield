from decimal import Decimal

from tokenshield.pricing.engine import Price, actual_cost, worst_case_cost

PRICE = Price(
    id=1,
    version=1,
    input_per_m=Decimal("2.50"),
    cached_input_per_m=Decimal("1.25"),
    output_per_m=Decimal("10"),
)


def test_actual_cost_splits_cached_input() -> None:
    # 2000 input (1200 cached) + 500 output
    expected = 800 * 2500 + 1200 * 1250 + 500 * 10000
    assert actual_cost(PRICE, 2000, 1200, 500) == expected


def test_cached_tokens_fall_back_to_input_price() -> None:
    p = Price(2, 1, Decimal("2.5"), None, Decimal("10"))
    assert actual_cost(p, 1000, 400, 0) == 1000 * 2500


def test_cached_tokens_are_clamped_to_input() -> None:
    assert actual_cost(PRICE, 100, 500, 0) == 100 * 1250


def test_worst_case_assumes_no_cache_and_full_output() -> None:
    assert worst_case_cost(PRICE, 2000, 1024) == 2000 * 2500 + 1024 * 10000
    assert worst_case_cost(PRICE, 2000, 1024) >= actual_cost(PRICE, 2000, 1200, 500)


def test_unpriced_model_costs_zero_and_is_flagged_elsewhere() -> None:
    assert actual_cost(None, 1000, 0, 1000) == 0
    assert worst_case_cost(None, 1000, 1000) == 0
