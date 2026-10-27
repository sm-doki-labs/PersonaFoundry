"""지금 시작할 수 있는 단계 계산과 유료 단계 판정 (D-0049, LLD §6.6·§6.7)."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.pipeline.scheduler import (
    extra_needs_for,
    paid_providers,
    paid_stage,
    ready_stages,
    until_scope,
)
from character_factory_poc.pipeline.state import StateFile

RUNNERS = {sid: (lambda: None) for sid in STAGES if sid != "s3r"}
AXIS = extra_needs_for(True)


def _state(tmp_path: Path) -> StateFile:
    return StateFile(tmp_path / "c" / "state.json", "c")


def _done(st: StateFile, sid: str, gate: str | None = None, rev: str = "r1") -> None:
    st.transition(sid, "RUNNING", rev=rev)
    if gate:
        st.transition(sid, "AWAITING_HUMAN", rev=rev)
        st.set_gate(gate, "APPROVED", rev, f"gates/{gate}-{rev}.json")
        st.transition(sid, "APPROVED", rev=rev)
    else:
        st.transition(sid, "APPROVED", rev=rev)


def _waiting(st: StateFile, sid: str, gate: str, rev: str = "r1") -> None:
    st.transition(sid, "RUNNING", rev=rev)
    st.transition(sid, "AWAITING_HUMAN", rev=rev)
    st.set_gate(gate, "AWAITING_HUMAN", rev, None)


def test_ready_stages_follow_the_turn_table(tmp_path: Path) -> None:
    st = _state(tmp_path)
    assert ready_stages(st, RUNNERS, set(), AXIS) == ["s1"]
    _waiting(st, "s1", "G1")
    assert ready_stages(st, RUNNERS, set(), AXIS) == []
    st.set_gate("G1", "APPROVED", "r1", "gates/G1-r1.json")
    st.transition("s1", "APPROVED", rev="r1")
    assert ready_stages(st, RUNNERS, set(), AXIS) == ["s2"]
    _done(st, "s2")
    assert ready_stages(st, RUNNERS, set(), AXIS) == ["s3", "s5"]
    _waiting(st, "s3", "G3")
    _waiting(st, "s5", "G5")
    assert ready_stages(st, RUNNERS, set(), AXIS) == []
    st.set_gate("G3", "APPROVED", "r1", "gates/G3-r1.json")
    st.transition("s3", "APPROVED", rev="r1")
    assert ready_stages(st, RUNNERS, set(), AXIS) == ["s4a", "s7"]
    # 이번 실행에서 이미 시도한 단계는 다시 고르지 않는다
    assert ready_stages(st, RUNNERS, {"s4a"}, AXIS) == ["s7"]


def test_persona_first_path_starts_s3_without_s2(tmp_path: Path) -> None:
    st = _state(tmp_path)
    runners = {sid: (lambda: None) for sid in ("s3", "s7", "s8")}
    assert ready_stages(st, runners, set(), extra_needs_for(False)) == ["s3"]
    assert ready_stages(st, runners, set(), AXIS) == []


def test_until_scope_matches_sequential_stop(tmp_path: Path) -> None:
    assert until_scope("G6")[-1] == "s8"
    assert until_scope("s5")[-1] == "s5"
    assert until_scope("sx")[-1] == "sx"


def test_paid_stage_needs_a_non_fake_paid_provider(tmp_path: Path) -> None:
    (tmp_path / "factory.toml").write_text(
        '[providers.video]\nadapter = "xai_video"\nmodel = "grok-imagine-video"\npaid = true\n'
        '[providers.image]\nadapter = "fake"\npaid = true\n',
        encoding="utf-8",
    )
    ctx = Context.load(tmp_path, execute=False)
    assert paid_stage(ctx, "s5") and paid_stage(ctx, "s6")
    assert paid_providers(ctx, "s5") == ["video: xai_video/grok-imagine-video"]
    assert not paid_stage(ctx, "s4")  # 이미지는 fake라 유료 표시를 무시한다
    assert not paid_stage(ctx, "s3")
