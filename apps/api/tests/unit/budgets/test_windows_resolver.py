import uuid
from datetime import UTC, datetime

import pytest

from tokenshield.budgets.resolver import Subject, applicable, counter_key
from tokenshield.budgets.windows import window_end, window_label, window_start, window_ttl_s
from tokenshield.gateway.catalog import BudgetInfo

NOW = datetime(2026, 10, 23, 15, 30, tzinfo=UTC)  # a Friday


@pytest.mark.parametrize(
    ("period", "start", "end"),
    [
        ("daily", datetime(2026, 10, 23, tzinfo=UTC), datetime(2026, 10, 24, tzinfo=UTC)),
        ("weekly", datetime(2026, 10, 19, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC)),
        ("monthly", datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)),
    ],
)
def test_windows(period: str, start: datetime, end: datetime) -> None:
    assert window_start(period, NOW) == start
    assert window_end(period, NOW) == end
    assert window_label(period, NOW) == start.strftime("%Y%m%d")
    assert window_ttl_s(period, NOW) == int((end - NOW).total_seconds()) + 86400


def test_december_rolls_into_next_year() -> None:
    assert window_end("monthly", datetime(2026, 12, 31, 23, tzinfo=UTC)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )


def test_total_period_never_expires() -> None:
    assert window_start("total", NOW) is None
    assert window_label("total", NOW) == "all"
    assert window_ttl_s("total", NOW) == 0


def test_unknown_period_raises() -> None:
    with pytest.raises(ValueError, match="unknown period"):
        window_start("hourly", NOW)


def _budget(scope: str, scope_id: str | None, mode: str = "hard") -> BudgetInfo:
    return BudgetInfo(uuid.uuid4(), f"{scope} budget", scope, scope_id, "monthly", 10, mode, 80)


def test_applicable_matches_each_scope() -> None:
    project, team, key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    s = Subject(project, team, key, "user-7", "chat-small")
    budgets = (
        _budget("global", None),
        _budget("project", str(project)),
        _budget("project", str(uuid.uuid4())),
        _budget("team", str(team)),
        _budget("api_key", str(key)),
        _budget("end_user", "*"),
        _budget("end_user", "user-8"),
        _budget("model", "chat-small"),
        _budget("model", "chat-large", mode="soft"),
    )
    applied = applicable(budgets, s, NOW)
    assert {a.budget.scope_type for a in applied} == {
        "global",
        "project",
        "team",
        "api_key",
        "end_user",
        "model",
    }
    assert len(applied) == 6
    per_user = next(a for a in applied if a.budget.scope_type == "end_user")
    assert per_user.counter.key.endswith(":user-7")


def test_per_user_budget_needs_a_user() -> None:
    s = Subject(uuid.uuid4(), None, None, None, "m")
    assert applicable((_budget("end_user", "*"), _budget("team", str(uuid.uuid4()))), s, NOW) == []


def test_counter_keys_change_with_window() -> None:
    bid = uuid.uuid4()
    oct_key = counter_key(bid, "monthly", NOW, "all")
    nov_key = counter_key(bid, "monthly", datetime(2026, 11, 2, tzinfo=UTC), "all")
    assert oct_key != nov_key and str(bid) in oct_key
