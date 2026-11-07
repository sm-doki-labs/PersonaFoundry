"""호출 추적 래퍼의 비용 기록과 형성 예산 단가 테스트(명세 §24.5·§24.6, LLD §22.2 D).

가짜 HTTP 응답과 monkeypatch만 쓰며 네트워크·유료 호출을 하지 않는다. 키 값은 테스트용 문자열이다.
"""

import json
from datetime import datetime

import httpx
import pytest

from character_factory_poc.common.budget import RunBudget
from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import BudgetExceeded, ProviderRequestError
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.pipeline import context as context_module
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers import tracked
from character_factory_poc.providers.base import (
    ChatRequest,
    ChatResponse,
    Message,
    VisionRequest,
    VisionResult,
)
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.tracked import TrackedTextModel, TrackedVisionModel

OPENAI_SECRET = "sk-test-openai-cost-value"
GEMINI_SECRET = "gm-test-gemini-cost-value"
API_BILLED = {"route": "api", "family": "openai", "class": "api_billed"}


def at(day: str):
    return lambda: datetime.fromisoformat(day + "T03:00:00+00:00")


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """단가표 기간 안의 날짜로 고정한다(확인일 2026-11-04 이후, 행사가 기간 안)."""
    monkeypatch.setattr(tracked, "_utc_now", at("2026-11-10"))
    monkeypatch.setattr(context_module, "_utc_now", at("2026-11-10"))
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def configured(tmp_path, *, route="api", profile="basic_test", extra=""):
    (tmp_path / "factory.toml").write_text(
        f'[text_pipeline]\nenabled=true\nprofile="{profile}"\nroute="{route}"\n' + extra,
        encoding="utf-8",
    )
    return load_config(tmp_path)


def request(ref="cf-x/c1", max_output_tokens=2000):
    return ChatRequest("AGENT", "s7", (Message("user", "json"),), ref, max_output_tokens)


def http_reply(replies):
    """URL 호스트별 가짜 chat/completions 응답. 보낸 요청을 sent에 모은다."""
    sent = []

    def post(client, url, **kw):
        sent.append((url, kw))
        status, body = replies(url, kw["json"])
        return httpx.Response(status, request=httpx.Request("POST", url), json=body)

    return post, sent


def completion(model, usage, finish="stop"):
    return {
        "model": model,
        "choices": [{"message": {"content": "{}"}, "finish_reason": finish}],
        "usage": usage,
    }


def test_api_route_records_openai_and_gemini_cost_price_and_billing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_SECRET)

    def replies(url, body):
        if "api.openai.com" in url:
            usage = {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
                "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
                "completion_tokens_details": {"reasoning_tokens": 300},
            }
            return 200, completion(body["model"], usage)
        # Gemini 호환 응답: completion_tokens에 생각 토큰이 빠져 total로 보정한다(Q-0023).
        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1400}
        return 200, completion(body["model"], usage, finish="length")

    post, sent = http_reply(replies)
    monkeypatch.setattr(httpx.Client, "post", post)
    ctx = Context(configured(tmp_path), execute=True)
    ctx.task_model("cf-x", ctx.budget(), "brief").complete(request("cf-x/a"))
    ctx.task_model("cf-x", ctx.budget(), "voice").complete(request("cf-x/b"))
    assert [u for u, _ in sent] == [
        "https://api.openai.com/v1/chat/completions",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ]
    gpt, gemini = ctx.ledger("cf-x").calls()

    assert gpt["billing"] == {"route": "api", "family": "openai", "class": "api_billed"}
    assert (gpt["inputTokens"], gpt["cachedInputTokens"], gpt["outputTokens"]) == (1000, 200, 500)
    assert gpt["cacheWriteTokens"] == 100
    assert gpt["reasoningTokens"] == 300 and gpt["finishReason"] == "stop"
    assert gpt["usageSource"] == "completion_tokens"
    # 캐시 쓰기는 입력 단가의 1.25배다: (700 × 2 + 200 × 0.10 + 100 × 2.5 + 500 × 10) / 1e6
    assert gpt["estCostUsd"] == pytest.approx(0.00667)
    assert gpt["price"] == {
        "table": "price-table-v1",
        "model": "gpt-6.1-sol",
        "effectiveFrom": "2026-11-04",
        "effectiveTo": None,
        "source": gpt["price"]["source"],
        "basis": "table",
    }

    assert gemini["billing"]["class"] == "api_billed" and gemini["billing"]["family"] == "gemini"
    assert gemini["outputTokens"] == 400 and gemini["usageSource"] == "total_minus_prompt"
    assert gemini["finishReason"] == "length"
    for unknown in ("cachedInputTokens", "cacheWriteTokens", "reasoningTokens"):
        assert unknown not in gemini
    # (1000 × 0.75 + 400 × 3.75) / 1e6
    assert gemini["estCostUsd"] == pytest.approx(0.00225)
    assert gemini["price"]["model"] == "gemini-3.8-flash"
    assert gemini["price"]["effectiveTo"] == "2026-12-31"
    ledger_text = ctx.ledger("cf-x").calls_path.read_text("utf-8")
    assert OPENAI_SECRET not in ledger_text and GEMINI_SECRET not in ledger_text
    assert "OPENAI_API_KEY" not in ledger_text


def test_relay_route_records_api_equivalent_cost(tmp_path, monkeypatch):
    def replies(url, body):
        usage = {"prompt_tokens": 2000, "completion_tokens": 1000, "total_tokens": 3000}
        return 200, completion(body["model"], usage)

    post, _ = http_reply(replies)
    monkeypatch.setattr(httpx.Client, "post", post)
    ctx = Context(configured(tmp_path, route="opencodex"), execute=True)
    ctx.task_model("cf-x", ctx.budget(), "voice").complete(request())
    row = ctx.ledger("cf-x").calls()[0]
    assert row["billing"] == {"route": "opencodex", "family": "gemini", "class": "relay_equivalent"}
    assert row["model"] == "google-antigravity/gemini-3.8-flash"
    assert row["price"]["model"] == "gemini-3.8-flash"
    assert row["estCostUsd"] == pytest.approx((2000 * 0.75 + 1000 * 3.75) / 1e6)


def test_fake_provider_has_no_cost_and_no_price(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    model = TrackedTextModel(FakeTextModel(responses={"*": "응"}), ledger, budget_stub())
    model.complete(request())
    row = ledger.calls()[0]
    assert row["estCostUsd"] is None and "price" not in row
    assert row["billing"]["class"] == "none"
    assert row["usageSource"] == "legacy_fields"
    assert ledger.report()["unpricedCalls"] == 0


class Stub:
    """usage-v1을 직접 돌려주는 공급자 대역."""

    name = "openai_compat"

    def __init__(self, model, usage=None, input_tokens=10, output_tokens=5, error=None):
        self.model = model
        self.usage = usage
        self.tokens = (input_tokens, output_tokens)
        self.error = error

    def complete(self, req):
        if self.error is not None:
            raise self.error
        return ChatResponse(
            "{}", *self.tokens, 3, self.model, self.name, finish_reason="stop", usage=self.usage
        )

    def judge(self, req):
        if self.error is not None:
            raise self.error
        return VisionResult("{}", *self.tokens, 3, self.model, self.name, usage=self.usage)


def budget_stub():
    class Plain:
        def consume(self, n=1):
            pass

    return Plain()


def test_unknown_price_keeps_cost_none_and_counts_unpriced(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    TrackedTextModel(Stub("gpt-unlisted"), ledger, budget_stub(), billing=API_BILLED).complete(
        request()
    )
    # 항목은 있으나 출력 단가가 비었으면 미확인이다.
    TrackedTextModel(
        Stub("gpt-unlisted"),
        ledger,
        budget_stub(),
        price_overrides={"gpt-unlisted": {"input_per_million": 1}},
    ).complete(request("cf-x/c2"))
    rows = ledger.calls()
    assert [r["estCostUsd"] for r in rows] == [None, None]
    assert "price" not in rows[0]
    # 항목은 있으나 출력 단가가 비었으면 적용 항목과 미확인 이유를 함께 남긴다.
    assert rows[1]["price"]["basis"] == "config_override"
    assert rows[1]["price"]["costReason"] == "missing_rate"
    assert ledger.report()["unpricedCalls"] == 2
    assert ledger.report()["byStage"]["s7"]["estCostUsd"] == 0.0


def test_price_override_and_cached_upper_bound_are_recorded(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    overrides = {"gpt-unlisted": {"input_per_million": 1, "output_per_million": 4}}
    usage = dict(
        inputTokens=100,
        cachedInputTokens=40,
        outputTokens=10,
        reasoningTokens=None,
        finishReason="stop",
        usageSource="completion_tokens",
    )
    TrackedTextModel(
        Stub("gpt-unlisted", usage=usage),
        ledger,
        budget_stub(),
        billing=API_BILLED,
        price_overrides=overrides,
    ).complete(request())
    row = ledger.calls()[0]
    assert row["price"]["basis"] == "config_override"
    assert row["price"]["upperBound"] is True  # 캐시 단가가 없어 입력 단가를 적용했다.
    assert row["estCostUsd"] == pytest.approx((100 * 1 + 10 * 4) / 1e6)


def test_cache_write_tokens_without_write_rate_stay_unpriced(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    usage = dict(inputTokens=100, cachedInputTokens=20, cacheWriteTokens=30, outputTokens=10)
    overrides = {"gpt-unlisted": {"input_per_million": 1, "output_per_million": 4}}
    TrackedTextModel(
        Stub("gpt-unlisted", usage=usage | {"usageSource": "completion_tokens"}),
        ledger,
        budget_stub(),
        billing=API_BILLED,
        price_overrides=overrides,
    ).complete(request())
    priced = dict(overrides["gpt-unlisted"], cache_write_per_million=1.25)
    TrackedTextModel(
        Stub("gpt-unlisted", usage=usage),
        ledger,
        budget_stub(),
        billing=API_BILLED,
        price_overrides={"gpt-unlisted": priced},
    ).complete(request("cf-x/c2"))
    missing, written = ledger.calls()
    assert missing["cacheWriteTokens"] == 30 and missing["estCostUsd"] is None
    assert missing["price"]["costReason"] == "missing_rate"
    # (100 − 20 − 30) × 1 + 20 × 1(캐시 읽기 단가 없음, 상한) + 30 × 1.25 + 10 × 4
    assert written["estCostUsd"] == pytest.approx((50 + 20 + 37.5 + 40) / 1e6)
    assert written["price"]["upperBound"] is True
    assert ledger.report()["unpricedCalls"] == 1


def test_missing_key_error_names_task_and_family_without_env_name(tmp_path):
    secret_like = "SK_LIVE_LOOKS_LIKE_A_KEY"
    extra = f'[text_pipeline.routes.api.families.openai]\napi_key_env="{secret_like}"\n'
    ctx = Context(configured(tmp_path, extra=extra), execute=True)
    with pytest.raises(ValueError) as caught:
        ctx.task_model("cf-x", ctx.budget(), "brief")
    message = str(caught.value)
    assert "brief" in message and "openai" in message
    assert secret_like not in message and "API_KEY" not in message


def test_vision_wrapper_records_cost_with_billing(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    vision = TrackedVisionModel(
        Stub("gpt-6.1-terra", input_tokens=1000, output_tokens=100),
        ledger,
        budget_stub(),
        billing=API_BILLED,
    )
    vision.judge(VisionRequest("s4", "cf-x/v1", "판정", ()))
    row = ledger.calls()[0]
    assert row["kind"] == "VISION" and row["billing"]["class"] == "api_billed"
    assert row["estCostUsd"] == pytest.approx((1000 * 1 + 100 * 5) / 1e6)


def test_provider_request_error_records_status_without_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_SECRET)

    def replies(url, body):
        return 400, {"error": {"message": f"Unsupported parameter: temperature {OPENAI_SECRET}"}}

    post, _ = http_reply(replies)
    monkeypatch.setattr(httpx.Client, "post", post)
    ctx = Context(configured(tmp_path), execute=True)
    with pytest.raises(ProviderRequestError):
        ctx.task_model("cf-x", ctx.budget(), "brief").complete(request())
    row = ctx.ledger("cf-x").calls()[0]
    assert row["ok"] is False and row["errorStatus"] == 400
    assert row["estCostUsd"] is None and "price" not in row
    assert row["billing"]["class"] == "api_billed"
    assert OPENAI_SECRET not in ctx.ledger("cf-x").calls_path.read_text("utf-8")
    # 다른 예외는 상태 코드를 남기지 않는다.
    ledger = Ledger(tmp_path / "other")
    with pytest.raises(RuntimeError):
        TrackedTextModel(
            Stub("gpt-6.1-sol", error=RuntimeError("x")), ledger, budget_stub()
        ).complete(request())
    assert "errorStatus" not in ledger.calls()[0]


def run_budget(path):
    return RunBudget(
        path,
        max_calls=5,
        max_tokens=100_000,
        max_cost_usd=1,
        input_rate_per_million=1,
        output_rate_per_million=2,
    )


def test_run_budget_settles_with_corrected_output_tokens(tmp_path):
    budget = run_budget(tmp_path / "b.json")
    usage = dict(
        inputTokens=50,
        cachedInputTokens=None,
        outputTokens=400,
        reasoningTokens=None,
        finishReason="stop",
        usageSource="total_minus_prompt",
    )
    # 기존 output_tokens(100)는 생각 토큰이 빠진 값이고 usage-v1의 보정값은 400이다.
    inner = Stub("gemini-3.8-flash", usage=usage, input_tokens=50, output_tokens=100)
    TrackedTextModel(inner, Ledger(tmp_path / "ledger"), budget).complete(request())
    assert budget.used_tokens == 450
    state = json.loads((tmp_path / "b.json").read_text("utf-8"))
    (row,) = state["reservations"].values()
    assert row["status"] == "SETTLED"
    assert row["chargedCost"] == pytest.approx((50 * 1 + 400 * 2) / 1e6)


def test_usage_over_reservation_is_still_recorded_in_ledger(tmp_path):
    budget = run_budget(tmp_path / "b.json")
    usage = dict(inputTokens=10, outputTokens=5000, finishReason="stop", usageSource="x")
    ledger = Ledger(tmp_path / "ledger")
    model = TrackedTextModel(Stub("gpt-6.1-sol", usage=usage), ledger, budget)
    with pytest.raises(BudgetExceeded, match="exceeded reserved"):
        model.complete(request(max_output_tokens=100))
    assert ledger.calls()[0]["outputTokens"] == 5000


def test_rejected_request_releases_reservation_but_not_the_request_id(tmp_path):
    budget = run_budget(tmp_path / "b.json")
    ledger = Ledger(tmp_path / "ledger")
    rejected = Stub("gpt-6.1-sol", error=ProviderRequestError(400, "Unsupported parameter"))
    model = TrackedTextModel(rejected, ledger, budget, billing=API_BILLED)
    with pytest.raises(ProviderRequestError):
        model.complete(request())
    (row,) = json.loads((tmp_path / "b.json").read_text("utf-8"))["reservations"].values()
    assert row["status"] == "SETTLED" and row["chargedTokens"] == 0 and row["chargedCost"] == 0
    assert budget.used_tokens == 0
    # 같은 요청의 재시도는 지금 규칙대로 중복 예약으로 막는다(재추첨 금지).
    with pytest.raises(BudgetExceeded, match="duplicate"):
        model.complete(request())

    # 전송 오류·5xx·429는 생성 여부를 모르므로 예약을 그대로 둔다.
    for i, error in enumerate([RuntimeError("timeout"), ProviderRequestError(429, "slow")]):
        failing = TrackedTextModel(Stub("gpt-6.1-sol", error=error), ledger, budget)
        with pytest.raises(type(error)):
            failing.complete(request(f"cf-x/r{i}"))
    state = json.loads((tmp_path / "b.json").read_text("utf-8"))["reservations"]
    assert sorted(r["status"] for r in state.values()) == ["RESERVED", "RESERVED", "SETTLED"]


def test_formation_budget_uses_highest_deck_rates(tmp_path, monkeypatch):
    cfg = configured(tmp_path, route="opencodex", profile="demo")
    budget = Context(cfg, execute=True).formation_budget()
    # 2026-11-10 demo 덱: sol 입력 2·캐시 쓰기 2.5/출력 10, argon 2/10, flash 0.75/3.75,
    # terra 1·1.25/5. 입력 상한은 캐시 쓰기 단가까지 본다.
    assert (budget.limits["inputRate"], budget.limits["outputRate"]) == (2.5, 10)

    monkeypatch.setattr(context_module, "_utc_now", at("2026-12-05"))
    (tmp_path / "fresh").mkdir()
    fresh = configured(tmp_path / "fresh", route="opencodex", profile="demo")
    budget = Context(fresh, execute=True).formation_budget()
    assert (budget.limits["inputRate"], budget.limits["outputRate"]) == (4, 20)


def test_resume_rejects_envelope_below_current_rates(tmp_path, monkeypatch):
    cfg = configured(tmp_path, route="opencodex", profile="demo")
    Context(cfg, execute=True).formation_budget()  # 2026-11-10 단가 2.5/10으로 봉투를 만든다.
    before = (tmp_path / "runs/budgets/choice-voice.json").read_bytes()
    # 12월에는 Argon 단가가 4/20으로 올라 기존 봉투로는 상한을 지킬 수 없다.
    monkeypatch.setattr(context_module, "_utc_now", at("2026-12-05"))
    with pytest.raises(ValueError, match="budget_run_id"):
        Context(cfg, execute=True).formation_budget()
    assert (tmp_path / "runs/budgets/choice-voice.json").read_bytes() == before
    # 새 budget_run_id는 새 봉투를 지금 단가로 만든다.
    renamed = configured(
        tmp_path, route="opencodex", profile="demo", extra='[stages.s7]\nbudget_run_id="dec"\n'
    )
    budget = Context(renamed, execute=True).formation_budget()
    assert (budget.limits["inputRate"], budget.limits["outputRate"]) == (4, 20)


def test_resume_keeps_envelope_rates_when_current_rates_are_lower(tmp_path, monkeypatch):
    monkeypatch.setattr(context_module, "_utc_now", at("2026-12-05"))
    december = configured(tmp_path, route="opencodex", profile="demo")
    Context(december, execute=True).formation_budget()
    # basic_test 덱은 Argon을 쓰지 않아 12월 상한이 2.5/10이다. 봉투 단가 4/20을 그대로 쓴다.
    cheaper = configured(tmp_path, route="opencodex", profile="basic_test")
    budget = Context(cheaper, execute=True).formation_budget()
    assert (budget.limits["inputRate"], budget.limits["outputRate"]) == (4, 20)


def test_formation_budget_rejects_unpriced_deck_model(tmp_path):
    extra = (
        '[text_pipeline.routes.test]\nbase_url="http://127.0.0.1:9/v1"\n'
        '[text_pipeline.routes.test.models]\n"gpt-6.1-terra"="gpt-unlisted-screening"\n'
    )
    cfg = configured(tmp_path, route="test", extra=extra)
    with pytest.raises(ValueError, match="gpt-unlisted-screening") as caught:
        Context(cfg, execute=True).formation_budget()
    assert "gpt-6.1-sol" not in str(caught.value)
    assert not (tmp_path / "runs/budgets").exists()


def test_formation_budget_prefers_configured_rates(tmp_path, monkeypatch):
    monkeypatch.setattr(context_module, "_utc_now", at("2027-01-05"))
    extra = "[stages.s7]\ninput_rate_upper_per_million=3\noutput_rate_upper_per_million=30\n"
    cfg = configured(tmp_path, route="opencodex", extra=extra)
    budget = Context(cfg, execute=True).formation_budget()
    assert (budget.limits["inputRate"], budget.limits["outputRate"]) == (3, 30)
