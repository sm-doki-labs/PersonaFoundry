"""물결 실행 (D-0049, LLD §6.6).

- 가짜 단계 실행 함수로 동시 실행·갈래 분리를 본다.
- 전체 흐름(가짜 공급자)으로 순차(max_parallel=1)와 물결(3)의 최종 상태가 같은지 본다.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from tests import test_offline_pipeline as flow


def _approved(ctx: Context, cid: str, sid: str, gate: str | None) -> None:
    st = ctx.state(cid)
    st.transition(sid, "RUNNING", rev="r1")
    if gate:
        st.transition(sid, "AWAITING_HUMAN", rev="r1")
        st.set_gate(gate, "APPROVED", "r1", f"gates/{gate}-r1.json")
    st.transition(sid, "APPROVED", rev="r1")


def _opens(ctx: Context, cid: str, sid: str, barrier: threading.Barrier | None = None):
    gate = STAGES[sid].gate

    def run():
        if barrier is not None:
            barrier.wait(timeout=5)  # 둘이 동시에 돌지 않으면 시간 초과로 실패한다
        st = ctx.state(cid)
        st.transition(sid, "RUNNING", rev="r1")
        st.transition(sid, "AWAITING_HUMAN" if gate else "APPROVED", rev="r1")
        if gate:
            st.set_gate(gate, "AWAITING_HUMAN", "r1", None)
        return Path(sid)

    return run


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context.load(tmp_path, execute=True)


def test_independent_stages_run_at_the_same_time(ctx, monkeypatch) -> None:
    cid = "c1"
    for sid, gate in (("s1", "G1"), ("s2", None)):
        _approved(ctx, cid, sid, gate)
    barrier = threading.Barrier(2)
    runners = {
        "s3": _opens(ctx, cid, "s3", barrier),
        "s5": _opens(ctx, cid, "s5", barrier),
    }
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda c, i, o: runners)
    log = run_until(ctx, cid, RunOptions(until="sx", max_parallel=3))
    assert log.waves == [["s3", "s5"]]
    assert log.waiting == ["G3", "G5"]
    assert set(log.timings) == {"s3", "s5"}


def test_check_failure_stops_only_its_own_branch(ctx, monkeypatch) -> None:
    cid = "c2"
    for sid, gate in (("s1", "G1"), ("s2", None), ("s3", "G3")):
        _approved(ctx, cid, sid, gate)

    def broken():
        raise CheckFailed("s4a", ["배경 검사 실패(시험)"])

    runners = {
        "s4a": broken,
        "s7": _opens(ctx, cid, "s7"),
        "s8": _opens(ctx, cid, "s8"),
    }
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda c, i, o: runners)
    log = run_until(ctx, cid, RunOptions(until="sx", max_parallel=3))
    assert log.waves == [["s4a", "s7"], ["s8"]]
    assert "s4a" in log.blocked
    assert log.waiting == ["G6"]
    # 기록 순서는 실행 순서와 상관없이 STAGES 순서다
    first = [line.split(":")[0] for line in log.steps if line.endswith(": 실행")]
    assert first == ["s4a", "s7", "s8"]


def _drive(root: Path, parallel: int) -> tuple:
    ctx, cid = flow.setup(root, "female")
    opt = RunOptions(
        until="sx",
        ranking=flow.ranking_for("female"),
        seed=flow.SEED,
        voice_probes=list(flow.PROBES),
        submit_training=True,
        max_parallel=parallel,
    )
    waves: list[list[str]] = []
    seen: dict = {}
    rounds = 0
    with flow.TestClient(flow.create_app(root)) as client:
        for _ in range(flow.MAX_ROUNDS):
            rounds += 1
            log = run_until(ctx, cid, opt)
            waves.extend(log.waves)
            if ctx.state(cid).stage("sx").status == "APPROVED" or not log.waiting:
                break
            for gate in log.waiting:
                flow.decide(client, cid, gate, seen)
    state = ctx.state(cid)
    final = {
        "stages": {sid: state.stage(sid).status for sid in STAGES},
        "gates": {g: state.gate(g).status for g in GATES},
    }
    return final, rounds, waves


def test_waves_reach_the_same_end_as_sequential(tmp_path: Path) -> None:
    seq, seq_rounds, _ = _drive(tmp_path / "seq", 1)
    par, par_rounds, waves = _drive(tmp_path / "par", 3)
    assert par == seq
    assert par["stages"]["sx"] == "APPROVED"
    assert par_rounds == seq_rounds
    together = [set(w) for w in waves]
    for pair in ({"s3", "s5"}, {"s4a", "s7"}, {"s4b", "s9s"}, {"s4", "s9"}, {"s6", "s10t"}):
        assert any(pair <= w for w in together), (pair, waves)
