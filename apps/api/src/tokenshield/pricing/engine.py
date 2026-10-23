"""Cost calculation. Pure functions over integer nano-dollars.

    cost = (input - cached) * P_in + cached * P_cached + output * P_out     (per token)

Cached input falls back to the ordinary input price when the catalog has no cached rate.
Worst-case estimates (used for reservations) assume no cache discount and the full output
allowance, so a reservation can only overstate the final cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tokenshield.core.money import tokens_cost_nusd


@dataclass(frozen=True, slots=True)
class Price:
    id: int
    version: int
    input_per_m: Decimal
    cached_input_per_m: Decimal | None
    output_per_m: Decimal


def worst_case_cost(price: Price | None, input_tokens: int, max_output_tokens: int) -> int:
    if price is None:
        return 0
    return tokens_cost_nusd(input_tokens, price.input_per_m) + tokens_cost_nusd(
        max_output_tokens, price.output_per_m
    )


def actual_cost(
    price: Price | None, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> int:
    if price is None:
        return 0
    cached = max(0, min(cached_input_tokens, input_tokens))
    cached_rate = (
        price.cached_input_per_m if price.cached_input_per_m is not None else price.input_per_m
    )
    return (
        tokens_cost_nusd(input_tokens - cached, price.input_per_m)
        + tokens_cost_nusd(cached, cached_rate)
        + tokens_cost_nusd(output_tokens, price.output_per_m)
    )
