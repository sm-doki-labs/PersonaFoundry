"""모델 준비 방식(D-0118): 저장·이력, 방식별 모티브 그래프, 오리지널 제한."""

from __future__ import annotations

from pathlib import Path

import pytest

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import (
    BIND_EXISTING,
    PROMPT_ONLY,
    SOURCE,
    STAGES,
    TRAIN,
    stages_for,
)
from character_factory_poc.pipeline.origin import read_model_mode, write_model_mode, write_origin
from character_factory_poc.pipeline.scheduler import until_scope


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context.load(tmp_path, execute=True)


def _char(ctx: Context, cid: str, origin: str | None = SOURCE) -> Path:
    char_dir = ctx.character_dir(cid)
    char_dir.mkdir(parents=True, exist_ok=True)
    ctx.state(cid).save()
    if origin:
        write_origin(char_dir, origin)
    return char_dir


def test_default_train_and_history(ctx: Context) -> None:
    char_dir = _char(ctx, "t1")
    assert read_model_mode(char_dir) == TRAIN
    write_model_mode(char_dir, PROMPT_ONLY, reason="부모님 원문이 적다")
    write_model_mode(char_dir, BIND_EXISTING)
    assert read_model_mode(char_dir) == BIND_EXISTING
    events = (char_dir / "ledger" / "model-mode-events.jsonl").read_text("utf-8").splitlines()
    assert len(events) == 2 and '"from": "TRAIN"' in events[0]


def test_original_only_train(ctx: Context) -> None:
    char_dir = _char(ctx, "o1", origin=None)
    with pytest.raises(FactoryError):
        write_model_mode(char_dir, PROMPT_ONLY)
    write_model_mode(char_dir, TRAIN)
    assert stages_for("CREATED", TRAIN) is STAGES


@pytest.mark.parametrize("mode", [BIND_EXISTING, PROMPT_ONLY])
def test_twin_without_training_skips_training_stages(ctx: Context, mode: str) -> None:
    graph = stages_for(SOURCE, mode)
    assert not {"s9s", "s9", "s10t"} & set(graph)
    assert graph["s10"].deps == frozenset({"G6"}) and graph["s10"].after == frozenset({"s9h"})
    assert "s10t" not in until_scope("G8", SOURCE, mode)


def test_twin_s10_waits_g6_and_holdout_set(ctx: Context) -> None:
    char_dir = _char(ctx, "t2")
    write_model_mode(char_dir, PROMPT_ONLY)
    state = ctx.state("t2")
    with pytest.raises(GateNotApprovedError, match="G6"):
        state.require_deps("s10")
    state.set_gate("G6", "APPROVED", "pv1", "gates/G6-pv1.json")
    with pytest.raises(GateNotApprovedError, match="s9h"):
        ctx.state("t2").require_deps("s10")


def test_cli_model_mode(tmp_path: Path, capsys) -> None:
    from character_factory_poc.cli import main

    ctx = Context.load(tmp_path, execute=True)
    _char(ctx, "t3")
    assert (
        main(["--root", str(tmp_path), "model", "mode", "t3", "prompt", "--reason", "원문이 적다"])
        == 0
    )
    assert read_model_mode(ctx.character_dir("t3")) == PROMPT_ONLY
    main(["--root", str(tmp_path), "model", "mode", "t3"])
    assert capsys.readouterr().out.strip().endswith("PROMPT_ONLY")
    _char(ctx, "o2", origin=None)
    assert main(["--root", str(tmp_path), "model", "mode", "o2", "bind"]) != 0
    assert read_model_mode(ctx.character_dir("o2")) == "TRAIN"
