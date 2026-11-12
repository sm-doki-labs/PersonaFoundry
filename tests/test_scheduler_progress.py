"""Completion-driven scheduling with synthetic runners and no provider traffic."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.demo import write_demo_mode
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.origin import write_origin
from tests.test_run_waves import _approved, _opens


@pytest.fixture
def ctx(tmp_path):
    return Context.load(tmp_path, execute=True)


def prepared(ctx):
    cid = "progress"
    for sid, gate in (("s1", "G1"), ("s2", None), ("s3", "G3")):
        _approved(ctx, cid, sid, gate)
    return cid


@pytest.mark.parametrize("demo", [False, True])
def test_prompt_successor_starts_while_video_is_waiting(ctx, monkeypatch, demo):
    cid = prepared(ctx)
    if demo:
        write_demo_mode(ctx.character_dir(cid), enabled=True, publish=False)
        monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
        monkeypatch.setattr(
            "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
        )
    video_started, release_video, prompt_started = (threading.Event() for _ in range(3))

    def video():
        video_started.set()
        assert release_video.wait(5)
        return _opens(ctx, cid, "s5")()

    def traits():
        assert video_started.wait(5)
        return _opens(ctx, cid, "s7")()

    def prompt():
        prompt_started.set()
        return _opens(ctx, cid, "s8")()

    runners = {"s5": video, "s7": traits, "s8": prompt}
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda *a: runners)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run_until, ctx, cid, RunOptions(until="G6", max_parallel=3))
        try:
            assert video_started.wait(2)
            assert prompt_started.wait(2), "S8 must start before the blocked video finishes"
            assert not future.done()
        finally:
            release_video.set()
        future.result(timeout=5)
    assert ctx.state(cid).stage("s8").status == "AWAITING_HUMAN"


def test_auto_review_parallel_preserves_prompt_scope_and_paid_confirmation(ctx, monkeypatch):
    cid = "source"
    write_origin(ctx.character_dir(cid), "SOURCE", auto_review=True)
    _approved(ctx, cid, "s0", "G0")
    _approved(ctx, cid, "s3", "G3")
    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-paid", extra={"paid": True})
    calls = []
    runners = {sid: lambda sid=sid: calls.append(sid) for sid in ("s2", "s5", "s7", "s8", "s8c")}
    monkeypatch.setattr(orchestrator, "_stage_runners", lambda *a: runners)
    log = run_until(ctx, cid, RunOptions(until="G6", max_parallel=3, web=True))
    assert calls == []
    assert log.held == ["s7"]
    assert log.waves, "auto_review must use the scheduler without expanding scope"


def test_web_parallel_default_and_explicit_serial(tmp_path):
    from character_factory_poc.web.events import EventHub
    from character_factory_poc.web.jobs import Job, JobManager
    from character_factory_poc.web.runtime import _resume_settings
    from character_factory_poc.web.settings import load_settings

    for config, expected in (("", 3), ("[orchestrator]\nmax_parallel=1\n", 1)):
        (tmp_path / "factory.toml").write_text(config)
        settings = load_settings(tmp_path, None)
        jobs = JobManager(tmp_path, settings, EventHub())
        options = jobs.run_options(Job("test", "synthetic"), object())
        assert options.max_parallel == expected
        assert _resume_settings(tmp_path, settings)["maxParallel"] == expected
    assert RunOptions(max_parallel=1).max_parallel == 1


@pytest.mark.parametrize("real_demo", [False, True])
def test_slots_are_reused_without_exceeding_parallel_limit(ctx, monkeypatch, real_demo):
    cid = prepared(ctx)
    ctx.config.orchestrator["parallel_stage_cost_cap_usd"] = 20
    if real_demo:
        write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=40, publish=False)
        ctx.config.providers["video"] = ProviderConfig(adapter="synthetic-real")
        monkeypatch.setattr(
            "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
        )
        monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
    video_started, image_started, traits_started, prompt_started = (
        threading.Event() for _ in range(4)
    )
    release_video, release_image = threading.Event(), threading.Event()

    def blocked(sid, started, release):
        def run():
            started.set()
            assert release.wait(5)
            return _opens(ctx, cid, sid)()

        return run

    def traits():
        traits_started.set()
        return _opens(ctx, cid, "s7")()

    def prompt():
        prompt_started.set()
        return _opens(ctx, cid, "s8")()

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": blocked("s5", video_started, release_video),
            "s4a": blocked("s4a", image_started, release_image),
            "s7": traits,
            "s8": prompt,
        },
    )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(
            run_until, ctx, cid, RunOptions(until="s8", max_parallel=3 if real_demo else 2)
        )
        try:
            assert video_started.wait(2) and image_started.wait(2)
            assert not traits_started.is_set()
            release_image.set()
            assert prompt_started.wait(2)
            assert not future.done()
        finally:
            release_image.set()
            release_video.set()
        log = future.result(timeout=5)
    if not real_demo:
        assert log.stopped_at == "s8"


def test_human_gate_blocks_its_descendant_but_not_prompt_lane(ctx, monkeypatch):
    cid = prepared(ctx)
    forbidden = []
    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s4a": _opens(ctx, cid, "s4a"),
            "s4b": lambda: forbidden.append("s4b"),
            "s7": _opens(ctx, cid, "s7"),
            "s8": _opens(ctx, cid, "s8"),
        },
    )
    log = run_until(ctx, cid, RunOptions(until="G6", max_parallel=3))
    assert not forbidden and ctx.state(cid).stage("s4b").status == "PENDING"
    assert "G4a" in log.waiting
    assert ctx.state(cid).stage("s8").status == "AWAITING_HUMAN"


@pytest.mark.parametrize("parallel", [1, 3])
def test_demo_checks_settled_cost_before_starting_another_real_stage(ctx, monkeypatch, parallel):
    cid = prepared(ctx)
    ctx.config.orchestrator["parallel_stage_cost_cap_usd"] = 20
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=25, publish=False)
    # Only configuration is non-fake: the runners below are synthetic and do no I/O.
    ctx.config.providers["video"] = ProviderConfig(adapter="synthetic-real")
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
    spent = [0.0]
    monkeypatch.setattr("character_factory_poc.pipeline.demo.spent_since", lambda *a: spent[0])
    called = []

    def video():
        called.append("s5")
        spent[0] = 26.0
        return _opens(ctx, cid, "s5")()

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": video,
            "s7": lambda: called.append("s7"),
        },
    )
    log = run_until(ctx, cid, RunOptions(max_parallel=parallel))
    assert called == ["s5"]
    expected = "s3r" if parallel == 1 else "s7"
    assert log.held == [expected] and log.stopped_at == expected
    assert any("시연 예산 상한" in line for line in log.steps)


def test_until_does_not_launch_later_ready_stages(ctx, monkeypatch):
    cid = prepared(ctx)
    called = []
    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": _opens(ctx, cid, "s5"),
            "s7": lambda: called.append("s7"),
        },
    )
    log = run_until(ctx, cid, RunOptions(until="s5", max_parallel=3))
    assert log.stopped_at == "s5" and not called


def test_auto_review_approves_existing_gate_then_runs_dependent_stage(ctx, monkeypatch):
    from character_factory_poc.pipeline.graph import TWIN_STAGES

    cid = "source-approval"
    write_origin(ctx.character_dir(cid), "SOURCE", auto_review=True)
    st = ctx.state(cid)
    st.transition("s0", "RUNNING", rev="r1")
    st.transition("s0", "AWAITING_HUMAN", rev="r1")
    st.set_gate("G0", "AWAITING_HUMAN", "r1", None)
    approved = []

    def approve(c, i, gate):
        approved.append(gate)
        sid = next(sid for sid, stage in TWIN_STAGES.items() if stage.gate == gate)
        state = c.state(i)
        state.set_gate(gate, "APPROVED", "r1", "synthetic.json")
        state.transition(sid, "APPROVED", rev="r1")

    monkeypatch.setattr(orchestrator, "approve_text_gate", approve)
    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s0": lambda: pytest.fail("existing source must not regenerate"),
            "s3": _opens(ctx, cid, "s3"),
            "s2": lambda: pytest.fail("prompt scope must not include photos"),
        },
    )
    log = run_until(ctx, cid, RunOptions(until="G3", max_parallel=3, web=True))
    assert approved == ["G0", "G3"]
    assert ctx.state(cid).stage("s3").status == "APPROVED"
    assert log.stopped_at == "G3"


def test_dependency_waits_for_worker_completion_not_early_state_update(ctx, monkeypatch):
    cid = prepared(ctx)
    traits_written, release_traits, prompt_started, video_done = (
        threading.Event() for _ in range(4)
    )

    def video():
        assert traits_written.wait(5)
        result = _opens(ctx, cid, "s5")()
        video_done.set()
        return result

    def traits():
        result = _opens(ctx, cid, "s7")()
        traits_written.set()
        assert release_traits.wait(5)
        return result

    def prompt():
        prompt_started.set()
        return _opens(ctx, cid, "s8")()

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": video,
            "s7": traits,
            "s8": prompt,
        },
    )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run_until, ctx, cid, RunOptions(until="G6", max_parallel=3))
        try:
            assert video_done.wait(2)
            assert not prompt_started.wait(0.2), "state publication is not worker completion"
        finally:
            release_traits.set()
        future.result(timeout=5)
    assert prompt_started.is_set()


def test_demo_check_failure_isolated_from_prompt_branch(ctx, monkeypatch):
    from character_factory_poc.common.errors import CheckFailed

    cid = prepared(ctx)
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=25, publish=False)
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)

    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-real")

    def broken():
        ctx.state(cid).transition("s4a", "RUNNING", rev="r1")
        raise CheckFailed("s4a", ["synthetic image failure"])

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s4a": broken,
            "s7": _opens(ctx, cid, "s7"),
            "s8": _opens(ctx, cid, "s8"),
        },
    )
    log = run_until(ctx, cid, RunOptions(max_parallel=3))
    assert ctx.state(cid).stage("s4a").status == "CHECK_FAILED"
    assert ctx.state(cid).stage("s8").status == "AWAITING_HUMAN"
    assert "s4a" in log.blocked


def test_real_provider_demo_runs_s8_while_video_holds_a_budget_reservation(ctx, monkeypatch):
    from dataclasses import replace

    cid = prepared(ctx)
    ctx.config = replace(ctx.config, budget=replace(ctx.config.budget, max_cost_usd_per_command=30))
    ctx.config.orchestrator["parallel_stage_cost_cap_usd"] = 10
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=40, publish=False)
    ctx.config.providers["video"] = ProviderConfig(adapter="synthetic-real-video")
    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-real-text")
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
    video_started, release_video, prompt_started = (threading.Event() for _ in range(3))

    def video():
        video_started.set()
        assert release_video.wait(5)
        return _opens(ctx, cid, "s5")()

    def traits():
        assert video_started.wait(5)
        return _opens(ctx, cid, "s7")()

    def prompt():
        prompt_started.set()
        return _opens(ctx, cid, "s8")()

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": video,
            "s7": traits,
            "s8": prompt,
        },
    )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run_until, ctx, cid, RunOptions(max_parallel=3))
        try:
            assert video_started.wait(2)
            assert prompt_started.wait(2), "real config must not force serial demo execution"
            assert not future.done()
        finally:
            release_video.set()
        future.result(timeout=5)


def test_demo_released_reservation_still_counts_settled_ledger_cost(ctx, monkeypatch):
    cid = prepared(ctx)
    ctx.config.orchestrator["parallel_stage_cost_cap_usd"] = 20
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=25, publish=False)
    ctx.config.providers["video"] = ProviderConfig(adapter="synthetic-real")
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
    called = []

    def video():
        called.append("s5")
        ctx.ledger(cid).record_call(
            stage="s5",
            kind="video",
            provider="synthetic",
            model="synthetic",
            input_tokens=None,
            output_tokens=None,
            ms=0,
            ok=True,
            ref="synthetic",
            est_cost_usd=10.0,
        )
        return _opens(ctx, cid, "s5")()

    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s5": video,
            "s7": lambda: called.append("s7"),
        },
    )
    log = run_until(ctx, cid, RunOptions(max_parallel=3))
    assert called == ["s5"]
    assert log.held == ["s7"] and log.stopped_at == "s7"
    assert any("단계 예약 $20.00" in line for line in log.steps)


def test_parallel_demo_worker_enforces_unknown_stage_cost_cap(ctx, monkeypatch):
    from dataclasses import replace

    from character_factory_poc.common.budget import CallPlan
    from character_factory_poc.common.errors import BudgetExceeded

    cid = prepared(ctx)
    ctx.config = replace(ctx.config, budget=replace(ctx.config.budget, max_cost_usd_per_command=30))
    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-real")
    ctx.config.orchestrator["parallel_stage_cost_cap_usd"] = 10
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=40, publish=False)
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    called = []

    def runners(worker, *args):
        def traits():
            worker.budget().check_plan([CallPlan("s7", "synthetic", 1, 11)])
            called.append("provider")
            return _opens(worker, cid, "s7")()

        return {"s7": traits}

    monkeypatch.setattr(orchestrator, "_stage_runners", runners)
    with pytest.raises(BudgetExceeded, match="11.00.*10"):
        run_until(ctx, cid, RunOptions(max_parallel=3))
    assert called == []
    assert ctx.config.budget.max_cost_usd_per_command == 30


@pytest.mark.parametrize("shared", [False, True])
def test_unknown_worker_cap_preserves_shared_call_budget(ctx, shared):
    from dataclasses import replace

    from character_factory_poc.common.budget import Budget, CallPlan
    from character_factory_poc.common.errors import BudgetExceeded
    from character_factory_poc.pipeline.scheduler import _demo_stage_budget

    cid = prepared(ctx)
    ctx.config = replace(ctx.config, budget=replace(ctx.config.budget, max_cost_usd_per_command=30))
    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-real")
    if shared:
        ctx._run_budget = Budget(ctx.config.budget)
    worker, reserved = _demo_stage_budget(ctx, cid, "s7")
    assert reserved == 10 and worker.config.budget.max_cost_usd_per_command == 10
    with pytest.raises(BudgetExceeded):
        worker.budget().check_plan([CallPlan("s7", "synthetic", 1, 11)])
    worker.budget().consume()
    if shared:
        assert ctx._run_budget.used_calls == 1
    assert ctx.config.budget.max_cost_usd_per_command == 30


@pytest.mark.parametrize("stage", ["s5", "s6"])
def test_known_video_plans_keep_command_cap_and_reserve_estimate(ctx, stage):
    from dataclasses import replace

    from character_factory_poc.pipeline.origin import write_signature
    from character_factory_poc.pipeline.scheduler import _demo_stage_budget

    cid = "known-video"
    write_origin(ctx.character_dir(cid), "SOURCE")
    from character_factory_poc.pipeline.origin import write_video_tier

    write_video_tier(ctx.character_dir(cid), "light")
    write_signature(ctx.character_dir(cid), {"title": "wave", "motion": "wave", "useWhen": ""})
    ctx.config = replace(ctx.config, budget=replace(ctx.config.budget, max_cost_usd_per_command=30))
    ctx.config.providers["video"] = ProviderConfig(
        adapter="xai_video",
        model="synthetic",
        extra={"price_per_second": {"synthetic": {"720p": 0.4 if stage == "s6" else 1.0}}},
    )
    worker, reserved = _demo_stage_budget(ctx, cid, stage)
    assert 10 < reserved < 30
    assert worker.config.budget.max_cost_usd_per_command == 30
    assert not ctx.ledger(cid).calls()


def test_completed_gate_needs_no_new_cost_reservation(ctx):
    from character_factory_poc.pipeline.scheduler import _demo_stage_budget

    cid = prepared(ctx)
    ctx.config.providers["text"] = ProviderConfig(adapter="synthetic-real")
    _opens(ctx, cid, "s8")()
    for sid in ("s3", "s8"):
        worker, reserved = _demo_stage_budget(ctx, cid, sid)
        assert reserved == 0 and worker is ctx


def test_video_plan_preflight_failure_does_not_stop_prompt_branch(ctx, monkeypatch):
    from character_factory_poc.pipeline.origin import write_video_tier

    cid = prepared(ctx)
    write_origin(ctx.character_dir(cid), "SOURCE")
    write_video_tier(ctx.character_dir(cid), "light")  # Missing signature fails S6 preflight.
    _approved(ctx, cid, "s4", "G4")
    ctx.config.providers["video"] = ProviderConfig(adapter="xai_video")
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=40, publish=False)
    monkeypatch.setattr(
        "character_factory_poc.pipeline.demo_flow.after_demo_run", lambda *a, **k: None
    )
    monkeypatch.setattr("character_factory_poc.pipeline.demo.approve_demo", lambda *a: None)
    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s6": lambda: pytest.fail("invalid video plan must not reach the provider"),
            "s7": _opens(ctx, cid, "s7"),
            "s8": _opens(ctx, cid, "s8"),
        },
    )
    log = run_until(ctx, cid, RunOptions(max_parallel=3))
    assert "s6" in log.blocked
    assert ctx.state(cid).stage("s8").status == "AWAITING_HUMAN"
