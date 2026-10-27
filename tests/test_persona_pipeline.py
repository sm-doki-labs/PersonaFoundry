"""오프라인 페르소나 흐름: plan import → S7 → S8 → G6 승인 (가짜 모델)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.cli import main
from character_factory_poc.common.errors import GateNotApprovedError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s3_plan.importer import import_plan
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.approve import approve_g6
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.synthetic import PLAN, prompter_output, trait_sheet


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context.load(tmp_path, execute=True)


def _import(ctx: Context, tmp_path: Path) -> str:
    src = tmp_path / "plan.json"
    src.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
    plan = import_plan(ctx, "haneul", src)
    return plan.characterId


def test_plan_import_records_g3(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    st = ctx.state(cid)
    assert st.gate("G3").status == "APPROVED"
    assert st.stage("s3").status == "APPROVED"
    rec = json.loads((ctx.character_dir(cid) / "gates" / "G3-pr1.json").read_text("utf-8"))
    assert rec["reviewer"] == "user" and "manual-plan" in rec["reasons"]
    plan_path = ctx.character_dir(cid) / "s3-plan" / "pr1" / "plan.json"
    plan = json.loads(plan_path.read_text("utf-8"))
    assert plan["evidence"]["coreTraits"][0]["kind"] == "USER"


def test_s7_requires_g3(ctx):
    with pytest.raises(ValueError):
        run_s7(ctx, "cf-20260101-nope")


def _fake_models(cid: str):
    text = FakeTextModel()
    text.add(
        "AGENT",
        lambda req: trait_sheet(cid, "pr1") if req.stage == "s7" else prompter_output(),
    )
    text.add("PROBE", lambda req: "그럼 이렇게 하자. 내일 아침에 같이 보자.")
    judge = FakeTextModel(model="fake-judge")
    judge.add("JUDGE", {"pick": "A", "reasons": "선택이 더 맞는다"})
    return text, judge


def test_full_persona_flow(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)

    sheet_path = run_s7(ctx, cid)
    assert sheet_path.exists()
    assert ctx.state(cid).stage("s7").status == "AWAITING_HUMAN"

    rev_dir = run_s8(ctx, cid, ["시험 망쳤어.", "너 발표 잘하더라."])
    pair = json.loads((rev_dir / "prompt-pair.json").read_text("utf-8"))
    assert pair["shortAdopted"] is False
    assert pair["short"]["chars"] < pair["long"]["chars"]
    assert (rev_dir / "gate-G6.html").exists()
    probe = json.loads((rev_dir / "prompt-probe.json").read_text("utf-8"))
    assert len(probe["probes"]) == 2
    picks = {"LONG", "SHORT", "TIE", "BOTH_BAD", "NONE"}
    assert all(p["judge"]["pick"] in picks for p in probe["probes"])
    # 판정 입력에 조건 이름·revision이 들어가지 않는다 (NFR-02)
    for req in judge.requests:
        joined = " ".join(m.content for m in req.messages)
        assert "LONG" not in joined and "SHORT" not in joined and "pv1" not in joined
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"

    out = approve_g6(ctx, cid, {"decision": "APPROVE", "reviewer": "user", "minutes": 3})
    pv = json.loads((out / "persona-version.json").read_text("utf-8"))
    assert pv["personaVersion"] == "pv1"
    st = ctx.state(cid)
    assert st.gate("G6").status == "APPROVED"
    assert st.stage("s8").status == "APPROVED" and st.stage("s7").status == "APPROVED"
    rep = ctx.ledger(cid).report()
    assert rep["totalCalls"] == 1 + 1 + 2 * 2 + 2  # s7, s8, probes(2x2), judge(2)
    assert rep["humanMinutes"] == 3
    assert main(["--root", str(tmp_path), "verify", cid]) == 0


def test_s7_retries_on_check_failure_then_passes(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    bad = trait_sheet(cid, "pr1")
    bad["choice"]["attention"] = "밝음, 솔직함"
    good = trait_sheet(cid, "pr1")
    text = FakeTextModel()
    text.add("AGENT", [bad, good])
    ctx.use_models(text)
    run_s7(ctx, cid)
    assert len(text.requests) == 2
    assert "낱말 나열" in text.requests[1].messages[-1].content


def test_s7_check_failed_after_retries(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    bad = trait_sheet(cid, "pr1")
    bad["choice"]["switchConditions"] = ["하나만 있다. 조건이 생기면 바꾼다."]
    text = FakeTextModel()
    text.add("AGENT", bad)
    ctx.use_models(text)
    with pytest.raises(SystemExit):
        run_s7(ctx, cid)
    assert ctx.state(cid).stage("s7").status == "CHECK_FAILED"


def test_s8_rejects_section_mismatch(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    bad = prompter_output()
    del bad["short"]["PERSONA / VOICE"]
    text = FakeTextModel()
    text.add("AGENT", lambda req: trait_sheet(cid, "pr1") if req.stage == "s7" else bad)
    ctx.use_models(text)
    run_s7(ctx, cid)
    with pytest.raises(SystemExit):
        run_s8(ctx, cid, [])
    assert ctx.state(cid).stage("s8").status == "CHECK_FAILED"


def test_s8_requires_s7(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    with pytest.raises((GateNotApprovedError, ValueError)):
        run_s8(ctx, cid, [])


def test_cli_dry_run_prints_plan(ctx, tmp_path, capsys):
    cid = _import(ctx, tmp_path)
    assert main(["--root", str(tmp_path), "persona", "traits", cid]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "s7" in out
    assert main(["--root", str(tmp_path), "status", cid]) == 0
