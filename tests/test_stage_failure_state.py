"""단계가 형식·검사 실패로 끝나면 실행 중으로 남지 않고 CHECK_FAILED가 된다(K-0089)."""

from __future__ import annotations

from pathlib import Path

import pytest

from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from tests import test_offline_pipeline as flow
from tests.support import flow as support
from tests.support.web_gates import trait_sheet_for


def _drive(root: Path) -> tuple:
    ctx, cid = flow.setup(root, "female")
    opt = RunOptions(
        until="G6",
        ranking=flow.ranking_for("female"),
        seed=flow.SEED,
        auto_approve={"G1", "G3"},
        voice_probes=list(flow.PROBES),
    )
    return ctx, cid, run_until(ctx, cid, opt)


def _break_s7(monkeypatch, respond) -> None:
    original = support.StageAgents.__call__

    def call(self, req):
        if req.stage == "s7":
            self.calls.append(req.stage)
            return respond(req)
        return original(self, req)

    monkeypatch.setattr(support.StageAgents, "__call__", call)


@pytest.mark.parametrize("kind", ["format", "check"])
def test_s7_failure_is_recorded_and_other_lanes_continue(tmp_path: Path, monkeypatch, kind) -> None:
    holder: dict = {}
    if kind == "format":
        _break_s7(monkeypatch, lambda req: {"broken": True})
    else:
        # 형식은 맞지만 기획서 핵심 성격을 하나도 담지 않아 검사(check_matches_plan)에 걸린다.
        # run_s7은 이때 SystemExit(메시지)을 던진다.
        def unrelated(req):
            sheet = trait_sheet_for(holder["ctx"], holder["cid"])
            sheet["card"]["expressedTraits"]["core"] = ["무관"]
            sheet["card"]["stance"] = "무관"
            sheet["choice"]["primaryResponse"] = "무관"
            return sheet

        _break_s7(monkeypatch, unrelated)
        original_setup = flow.setup

        def setup(root, gender):
            ctx, cid = original_setup(root, gender)
            holder.update(ctx=ctx, cid=cid)
            return ctx, cid

        monkeypatch.setattr(flow, "setup", setup)

    ctx, cid, log = _drive(tmp_path / "root")

    st = ctx.state(cid).stage("s7")
    assert st.status == "CHECK_FAILED"
    assert st.lastError
    expected = "형식 실패" if kind == "format" else "핵심 성격"
    assert expected in st.lastError
    assert "s7" in log.blocked
    # 다른 갈래(장면)는 계속 돌아 사람 검토에서 멈춘다(D-0035)
    assert ctx.state(cid).stage("s4a").status == "AWAITING_HUMAN"
    assert ctx.state(cid).stage("s8").status == "PENDING"
