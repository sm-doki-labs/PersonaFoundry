"""Reference-master graph scheduling with deterministic synthetic workers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions
from character_factory_poc.pipeline.origin import (
    graph_for_dir,
    write_origin,
    write_reference_image,
    write_video_tier,
)
from character_factory_poc.pipeline.scheduler import ready_stages, run_waves, until_scope
from tests.test_run_waves import _approved, _opens


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, execute=True)
    cid = "master-scheduler"
    folder = ctx.character_dir(cid)
    write_origin(folder, "SOURCE")
    write_video_tier(folder, "light")
    write_reference_image(folder, {})
    for sid, gate in (("s0", "G0"), ("s2", "G1s"), ("s3", "G3")):
        _approved(ctx, cid, sid, gate)

    # Keep stage work synthetic while retaining actual graph readiness and state transitions.
    def step(worker, cid, sid, opt, runners, log, **kwargs):
        state = worker.state(cid)
        if state.stage(sid).status == "APPROVED":
            return
        state.require_deps(sid)
        if state.stage(sid).status != "AWAITING_HUMAN":
            runners[sid]()
        gate = graph_for_dir(worker.character_dir(cid))[sid].gate
        if gate and worker.state(cid).gate(gate).status == "AWAITING_HUMAN":
            log.waiting.append(gate)

    monkeypatch.setattr(orchestrator, "_step", step)
    return ctx, cid


def test_actual_graph_omits_scene_workers_and_uses_source_approval(prepared, monkeypatch):
    ctx, cid = prepared
    graph = graph_for_dir(ctx.character_dir(cid))
    scope = until_scope("G4", graph=graph)
    assert scope[-1] == "s4" and "s4a" not in scope and "s4b" not in scope
    runners = {"s4": _opens(ctx, cid, "s4")}
    assert ready_stages(ctx.state(cid), runners, set()) == ["s4"]
    ctx.state(cid).set_gate("G1s", "AWAITING_HUMAN", "r1", None)
    assert ready_stages(ctx.state(cid), runners, set()) == []
    ctx.state(cid).set_gate("G1s", "APPROVED", "r1", None)
    runners.update({sid: lambda: pytest.fail("legacy scene stage ran") for sid in ("s4a", "s4b")})
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda *a: runners)
    log = run_waves(ctx, cid, RunOptions(until="G4", max_parallel=3))
    assert log.waves == [["s4"]]
    assert log.waiting == ["G4"]
    assert ctx.state(cid).stage("s6").status == "PENDING"


def test_external_g4_approval_unblocks_video_on_completion_and_clears_waiting(
    prepared, monkeypatch
):
    ctx, cid = prepared
    # A master already waits for a human; the persona worker remains active.
    _opens(ctx, cid, "s4")()
    persona_started, release_persona, video_started = Event(), Event(), Event()

    def persona():
        persona_started.set()
        assert release_persona.wait(5)
        return _opens(ctx, cid, "s7")()

    def video():
        assert ctx.state(cid).gate("G4").status == "APPROVED"
        video_started.set()
        return _opens(ctx, cid, "s6")()

    def chapter():
        _approved(ctx, cid, "s8c", None)

    runners = {
        "s4": lambda: pytest.fail("master must not regenerate"),
        "s6": video,
        "s7": persona,
        "s8": _opens(ctx, cid, "s8"),
        "s8c": chapter,
    }
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda *a: runners)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(
            run_waves,
            ctx,
            cid,
            RunOptions(until="G4", videos_with_chat=True, max_parallel=3),
            scope=set(runners),
        )
        try:
            assert persona_started.wait(2), "video target must retain the full chat scope"
            assert not video_started.is_set(), "G4 review must block S6"
            # Simulate the separate human approval handler, while persona work is running.
            ctx.state(cid).set_gate("G4", "APPROVED", "r1", "gates/G4-r1.json")
            ctx.state(cid).transition("s4", "APPROVED", rev="r1")
        finally:
            release_persona.set()
        log = future.result(timeout=5)
    assert video_started.is_set()
    assert "G4" not in log.waiting
    assert "G5b" in log.waiting and "G6" in log.waiting
    assert ctx.state(cid).stage("s8c").status == "APPROVED"
