import pytest

from character_factory_poc.common.budget import RunBudget
from character_factory_poc.common.errors import BudgetExceeded
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.tracked import TrackedTextModel


def budget(path, **changes):
    return RunBudget(
        path,
        max_calls=2,
        max_tokens=5000,
        max_cost_usd=1,
        input_rate_per_million=1,
        output_rate_per_million=2,
        **changes,
    )


def test_resume_does_not_reset_shared_budget(tmp_path):
    path = tmp_path / "budget.json"
    first = budget(path)
    first.reserve("one", input_tokens=20, output_tokens=100)
    second = budget(path)
    assert second.used_calls == 1
    second.reserve("two", input_tokens=20, output_tokens=100)
    with pytest.raises(BudgetExceeded):
        first.reserve("three", input_tokens=1, output_tokens=1)


def test_unknown_price_is_not_zero_cost(tmp_path):
    with pytest.raises(ValueError, match="price|rate"):
        RunBudget(
            tmp_path / "b.json",
            max_calls=2,
            max_tokens=1000,
            max_cost_usd=1,
            input_rate_per_million=None,
            output_rate_per_million=None,
        )


def test_consumer_budget_counts_reasoning_tokens(tmp_path):
    b = RunBudget(
        tmp_path / "b.json",
        max_calls=2,
        max_tokens=200,
        max_cost_usd=1,
        input_rate_per_million=1,
        output_rate_per_million=1,
    )
    b.reserve("one", input_tokens=20, output_tokens=180)
    with pytest.raises(BudgetExceeded):
        b.reserve("two", input_tokens=1, output_tokens=1)
    b.settle("one", input_tokens=20, output_tokens=170)
    assert b.used_tokens == 190


def test_tracked_call_reserves_and_settles_shared_budget(tmp_path):
    b = budget(tmp_path / "b.json")
    inner = FakeTextModel(responses={"*": "응"})
    model = TrackedTextModel(inner, Ledger(tmp_path / "ledger"), b)
    req = ChatRequest("DIALOGUE", "test", (Message("user", "안녕"),), "one", max_output_tokens=100)
    assert model.complete(req).text == "응"
    assert b.used_calls == 1
    with pytest.raises(BudgetExceeded, match="duplicate"):
        model.complete(req)
    assert len(inner.requests) == 1


def test_unsettled_failed_request_keeps_reservation(tmp_path):
    b = budget(tmp_path / "b.json")
    b.reserve("one", input_tokens=20, output_tokens=100)
    before = b.used_tokens
    assert budget(tmp_path / "b.json").used_tokens == before
    with pytest.raises(BudgetExceeded):
        b.reserve("one", input_tokens=20, output_tokens=100)


def test_corrupted_budget_cannot_reset_usage(tmp_path):
    path = tmp_path / "b.json"
    b = budget(path)
    b.reserve("one", input_tokens=20, output_tokens=100)
    path.write_text("")
    with pytest.raises(ValueError, match="corrupt|empty"):
        budget(path)
