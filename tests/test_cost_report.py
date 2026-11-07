"""비용 보고서 cost-report-v1과 cfp ledger 명령 테스트(명세 §24.5, FR-69, LLD §22.2 D).

합성 원장 행만 쓰며 공급자를 부르지 않는다.
"""

import json
from datetime import UTC, datetime

import pytest

from character_factory_poc.cli import main
from character_factory_poc.common import cost_report
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.pipeline.context import Context

PRICE_SOL = {
    "table": "price-table-v1",
    "model": "gpt-6.1-sol",
    "effectiveFrom": "2026-11-04",
    "effectiveTo": None,
    "source": "https://developers.openai.com/api/docs/pricing",
    "basis": "table",
}
API = {"route": "api", "family": "openai", "class": "api_billed"}
RELAY = {"route": "opencodex", "family": "gemini", "class": "relay_equivalent"}
FAKE = {"route": "fake", "family": None, "class": "none"}


def call(ledger, stage, model, **kw):
    base = dict(
        stage=stage,
        kind="AGENT",
        provider="openai_compat",
        model=model,
        input_tokens=None,
        output_tokens=None,
        ms=1,
        ok=True,
        ref=f"cf-x/{stage}",
    )
    ledger.record_call(**(base | kw))


def fill(ledger: Ledger) -> None:
    gpt = dict(input_tokens=1000, cached_input_tokens=200, cache_write_tokens=100)
    gpt |= dict(output_tokens=500)
    gpt |= dict(reasoning_tokens=300, finish_reason="stop", usage_source="completion_tokens")
    call(ledger, "s7", "gpt-6.1-sol", **gpt, est_cost_usd=0.00667, price=PRICE_SOL, billing=API)
    relay = dict(input_tokens=2000, output_tokens=1000, finish_reason="length")
    relay |= dict(price={**PRICE_SOL, "model": "gemini-3.8-flash"}, billing=RELAY)
    call(ledger, "s7", "google-antigravity/gemini-3.8-flash", **relay, est_cost_usd=0.00525)
    # 비용 기록 이전의 중계 행: billing·price가 없고 비용 칸이 비었다.
    argon = "google-antigravity/gemini-4-argon"
    call(ledger, "s8", argon, input_tokens=1000, output_tokens=100, text_binding={"model": argon})
    call(ledger, "s8", "fake-text", provider="fake", input_tokens=3, output_tokens=2, billing=FAKE)
    call(ledger, "s8", "gpt-6.1-sol", ok=False, error_status=400, billing=API)
    call(ledger, "s4", "gpt-image", kind="IMAGE", images=1, est_cost_usd=0.04)
    # codex exec 실행은 단가표 범위 밖이다(PRD §20.5). 비용이 비어도 미확인으로 세지 않는다.
    call(ledger, "s1", "gpt-6.1-sol", provider="codex_exec", input_tokens=900, output_tokens=90)
    call(ledger, "s1", "gpt-6.1-sol", provider="fake_codex", kind="AGENT_TAINTED", ok=False)


def test_report_groups_by_stage_model_and_billing(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    fill(ledger)
    report = cost_report.build(ledger.calls())
    assert report["schema"] == "cost-report-v1" and report["basis"] == "원장 기록"
    totals = report["totals"]
    assert totals["calls"] == 8
    assert totals["inputTokens"] == 4903 and totals["cachedInputTokens"] == 200
    assert totals["cacheWriteTokens"] == 100 and totals["outputTokens"] == 1692
    assert totals["estCostUsd"] == pytest.approx(0.00667 + 0.00525 + 0.04)
    # 미확인은 이전 중계 행 하나다. 가짜 공급자·실패·이미지·codex exec 행은 세지 않는다.
    assert (totals["unpricedCalls"], totals["truncatedCalls"], totals["failedCalls"]) == (1, 1, 2)
    assert totals["api_billed"] == pytest.approx(0.00667)
    assert totals["relay_equivalent"] == pytest.approx(0.00525)

    by_billing = report["byBilling"]
    assert set(by_billing) == {"api_billed", "relay_equivalent", "unknown", "none"}
    assert by_billing["api_billed"]["calls"] == 2 and by_billing["api_billed"]["failedCalls"] == 1
    assert by_billing["unknown"]["calls"] == 4  # 이전 중계 행 + 이미지 행 + codex exec 두 행
    assert by_billing["unknown"]["unpricedCalls"] == 1
    assert by_billing["none"]["estCostUsd"] == 0.0 and by_billing["none"]["unpricedCalls"] == 0
    assert report["billingLabels"]["relay_equivalent"] == "API 환산(중계 호출)"

    assert report["byStage"]["s7"]["calls"] == 2
    assert report["byStage"]["s7"]["truncatedCalls"] == 1
    assert report["byStage"]["s4"]["estCostUsd"] == pytest.approx(0.04)
    assert report["byStage"]["s1"]["unpricedCalls"] == 0
    assert report["byModel"]["gpt-6.1-sol"]["calls"] == 4
    assert "recomputedAt" not in report


def test_legacy_rows_without_billing_infer_fake_and_deck_route():
    fake = {"provider": "fake", "model": "fake-text", "ok": True}
    relay = {"provider": "openai_compat", "textBinding": {"route": "opencodex"}, "ok": True}
    old = {"provider": "openai_compat", "model": "gpt-6.1-sol", "ok": True}
    assert cost_report.billing_class(fake) == "none"
    assert cost_report.billing_class(relay) == "relay_equivalent"
    assert cost_report.billing_class(old) == "unknown"
    explicit = dict(relay, billing={"class": "api_billed"})
    assert cost_report.billing_class(explicit) == "api_billed"


def test_ledger_report_counts_unpriced_without_adding_zero(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    fill(ledger)
    report = ledger.report()
    assert set(report) >= {"totalCalls", "byStage", "humanMinutes", "humanByGate"}
    assert report["unpricedCalls"] == 1
    assert report["byStage"]["s8"]["unpricedCalls"] == 1
    assert report["byStage"]["s8"]["estCostUsd"] == 0.0
    assert report["byStage"]["s1"]["unpricedCalls"] == 0
    assert report["byStage"]["s4"]["unpricedCalls"] == 0


def test_recompute_uses_current_prices_without_touching_ledger(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    fill(ledger)
    before = ledger.calls_path.read_bytes()
    november = cost_report.build(
        ledger.calls(), recompute=True, at=datetime(2026, 11, 10, tzinfo=UTC)
    )
    assert ledger.calls_path.read_bytes() == before
    assert november["basis"] == "현재 단가 환산"
    assert november["recomputedAt"] == "2026-11-10T00:00:00+00:00"
    assert november["priceTables"] == ["price-table-v1"]
    # 이전 중계 행은 덱 해석 모델(Argon 2/10)로 환산된다: (1000 × 2 + 100 × 10) / 1e6
    assert november["byStage"]["s8"]["estCostUsd"] == pytest.approx(0.003)
    assert november["byStage"]["s8"]["unpricedCalls"] == 0
    # 이미지 행은 기록된 비용을 그대로 쓴다.
    assert november["byStage"]["s4"]["estCostUsd"] == pytest.approx(0.04)
    # codex exec 행은 같은 모델 ID여도 재계산하지 않는다. 텍스트 호출(kind AGENT)은 재계산한다.
    assert november["byStage"]["s1"] == cost_report.build(ledger.calls())["byStage"]["s1"]
    assert november["byStage"]["s1"]["estCostUsd"] == 0.0
    assert november["totals"]["api_billed"] == pytest.approx(0.00667)
    relay_usd = (2000 * 0.75 + 1000 * 3.75) / 1e6
    assert november["totals"]["relay_equivalent"] == pytest.approx(relay_usd)

    # 재계산은 호출 시각이 아니라 at 기준이다. 12월 Argon 단가 4/20을 적용한다.
    december = cost_report.build(
        ledger.calls(), recompute=True, at=datetime(2026, 12, 5, tzinfo=UTC)
    )
    assert december["byStage"]["s8"]["estCostUsd"] == pytest.approx(0.006)
    overridden = cost_report.build(
        ledger.calls(),
        recompute=True,
        at=datetime(2026, 11, 10, tzinfo=UTC),
        overrides={"gemini-4-argon": {"input_per_million": 1, "output_per_million": 1}},
    )
    assert overridden["byStage"]["s8"]["estCostUsd"] == pytest.approx(0.0011)
    assert ledger.calls_path.read_bytes() == before


@pytest.fixture
def root(tmp_path):
    (tmp_path / "factory.toml").write_text(
        '[text_pipeline]\nenabled=true\nprofile="basic_test"\nroute="opencodex"\n',
        encoding="utf-8",
    )
    fill(Context.load(tmp_path, execute=False).ledger("cf-x"))
    return tmp_path


def test_cli_ledger_report_includes_cost(root, capsys):
    assert main(["--root", str(root), "ledger", "report", "cf-x"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["totalCalls"] == 8 and out["unpricedCalls"] == 1
    assert out["cost"]["schema"] == "cost-report-v1"
    assert out["cost"]["totals"]["api_billed"] == pytest.approx(0.00667)


def test_cli_ledger_cost_by_id_path_and_out(root, capsys):
    calls = Context.load(root, execute=False).ledger("cf-x").calls_path
    before = calls.read_bytes()
    argv = ["--root", str(root), "ledger", "cost", "cf-x", "--recompute"]
    assert main([*argv, "--out", "work/cost-cf-x.json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads((root / "work/cost-cf-x.json").read_text("utf-8"))
    assert printed == saved and saved["basis"] == "현재 단가 환산"
    assert "recomputedAt" in saved
    assert calls.read_bytes() == before

    assert main(["--root", str(root), "ledger", "cost", str(calls)]) == 0
    by_path = json.loads(capsys.readouterr().out)
    assert by_path["basis"] == "원장 기록" and by_path["totals"]["calls"] == 8

    inside = calls.parent / "cost.json"
    assert main(["--root", str(root), "ledger", "cost", "cf-x", "--out", str(inside)]) == 1
    assert not inside.exists()
    assert main(["--root", str(root), "ledger", "cost", "cf-missing"]) == 1


def test_cli_models_select_accepts_api_route(root, capsys):
    assert main(["--root", str(root), "models", "select", "--route", "api"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert all(b["route"] == "api" for b in out["bindings"])
