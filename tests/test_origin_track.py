"""오리지널·트윈 갈래 뼈대 (D-0116, D-0127, D-0128).

- 오리지널 그래프는 지금 그래프(STAGES)와 같은 객체다.
- 트윈 그래프는 s1이 없고 s0·s9h가 있으며, s2·s3는 G0 뒤에 돈다. 뒤쪽 단계의 의존은 같다.
- 출신은 캐릭터마다 한 번만 쓴다.
- 트윈 캐릭터는 아직 구현 전인 단계(s0·s2·s3·s9h)를 실행하지 않고 건너뜀 문장을 남긴다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import GATES, STAGES, gates_for, stages_for
from character_factory_poc.pipeline.orchestrator import (
    RunOptions,
    run_until,
    validate_auto_approve,
)
from character_factory_poc.pipeline.origin import (
    CREATED,
    SOURCE,
    origin_label,
    read_origin,
    write_origin,
)
from character_factory_poc.pipeline.scheduler import ready_stages, until_scope


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context.load(tmp_path, execute=True)


def _twin(ctx: Context, cid: str = "twin1") -> str:
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    ctx.state(cid).save()
    write_origin(ctx.character_dir(cid), SOURCE)
    return cid


def test_original_graph_is_unchanged() -> None:
    assert stages_for(CREATED) is STAGES
    assert gates_for(CREATED) == GATES


def test_twin_graph_replaces_front_and_keeps_back() -> None:
    twin = stages_for(SOURCE)
    assert "s1" not in twin
    assert list(twin)[0] == "s0"
    assert twin["s0"].gate == "G0"
    assert twin["s2"].deps == frozenset({"G0"}) and twin["s2"].gate == "G1s"
    assert twin["s3"].deps == frozenset({"G0"}) and twin["s3"].gate == "G3"
    assert twin["s9h"].deps == frozenset({"G0"})
    # 뒤쪽 단계는 오리지널과 같은 정의를 쓴다.
    # s10은 트윈에서 비교 세트(s9h)도 기다리므로 따로 본다(D-0118).
    back = ("s3r", "s4a", "s4b", "s4", "s5", "s6", "s7", "s8", "s9s", "s9", "s10t")
    for sid in (*back, "s11", "sx"):
        assert twin[sid] is STAGES[sid]
    assert twin["s10"].after == frozenset({"s10t", "s9h"})
    gates = gates_for(SOURCE)
    assert gates[:2] == ["G0", "G1s"] and "G1" not in gates


def test_origin_defaults_to_original_and_is_written_once(ctx: Context) -> None:
    char_dir = ctx.character_dir("c1")
    assert read_origin(char_dir) == CREATED
    write_origin(char_dir, SOURCE)
    assert read_origin(char_dir) == SOURCE
    write_origin(char_dir, SOURCE)  # 같은 값은 그대로 둔다
    with pytest.raises(FactoryError):
        write_origin(char_dir, CREATED)
    assert origin_label(SOURCE) == "트윈" and origin_label(CREATED) == "오리지널"


def test_twin_dependencies_follow_twin_graph(ctx: Context) -> None:
    cid = _twin(ctx)
    state = ctx.state(cid)
    with pytest.raises(GateNotApprovedError):
        state.require_deps("s3")
    with pytest.raises(GateNotApprovedError):
        state.require_deps("s2")  # G1이 아니라 G0을 기다린다
    state.set_gate("G0", "APPROVED", "sp1", "gates/G0-sp1.json")
    ctx.state(cid).require_deps("s3")
    ctx.state(cid).require_deps("s2")
    # 오리지널 캐릭터의 s3는 관문 의존이 없다.
    ctx.character_dir("orig").mkdir(parents=True, exist_ok=True)
    ctx.state("orig").require_deps("s3")


def test_twin_scope_and_ready_stages_skip_unimplemented(ctx: Context) -> None:
    cid = _twin(ctx)
    assert until_scope("G3", SOURCE)[:3] == ["s0", "s2", "s3"]
    assert "s1" not in until_scope("G6", SOURCE)
    calls: list[str] = []
    runners = {sid: (lambda sid=sid: calls.append(sid)) for sid in stages_for(SOURCE)}
    # 구현 전 단계는 실행 함수가 있어도 시작 목록에 들지 않는다. s0은 구현돼 바로 시작할 수 있다.
    ready = set(ready_stages(ctx.state(cid), runners, set()))
    assert "s0" in ready and not {"s2", "s3", "s9h"} & ready


def test_twin_run_does_not_touch_original_front(ctx: Context) -> None:
    cid = _twin(ctx)
    log = run_until(ctx, cid, RunOptions(until="G6"))
    text = "\n".join(log.steps)
    assert not any(step.startswith("s1:") for step in log.steps)
    assert "s0: 사람 입력 대기 — 트윈 s0: 출처 묶음이 필요하다" in text
    assert "s3: 시작 불가 — s3는 G0 승인이 필요하다" in text
    state = ctx.state(cid)
    for sid in ("s0", "s2", "s3"):
        assert state.stage(sid).status == "PENDING"


def test_twin_run_rejects_ranking(ctx: Context) -> None:
    cid = _twin(ctx)
    with pytest.raises(FactoryError):
        run_until(ctx, cid, RunOptions(until="G6", ranking={"lists": []}))


def test_twin_gates_are_human_only() -> None:
    for gate in ("G0", "G1s"):
        with pytest.raises(FactoryError):
            validate_auto_approve({gate})


def test_cli_creates_twin_and_keeps_origin(tmp_path: Path, capsys) -> None:
    from character_factory_poc.cli import main

    rc = main(
        [
            "--root",
            str(tmp_path),
            "run",
            "x",
            "--new-slug",
            "son",
            "--origin",
            "twin",
            "--until",
            "G3",
            "--execute",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "(트윈)" in out
    ctx = Context.load(tmp_path, execute=True)
    (char_dir,) = (ctx.config.runs_dir / "characters").iterdir()
    assert read_origin(char_dir) == SOURCE
    with pytest.raises(SystemExit):
        main(
            [
                "--root",
                str(tmp_path),
                "run",
                char_dir.name,
                "--origin",
                "original",
                "--execute",
            ]
        )
