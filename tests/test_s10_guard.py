"""S10t 분리 감시(guard) 시험. 프로세스 없이 guard_loop를 가짜 시계·가짜 vastai로 부른다."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from character_factory_poc.providers.training.errors import TrainingError
from character_factory_poc.stages.s10_train import guard
from tests.test_vast_lease import FakeVast

LIMITS = {
    "wallSeconds": 3600.0,
    "readyTimeoutS": 1800.0,
    "collectMarginS": 7200.0,
    "budgetUsd": 10.0,
    "reserveUsd": 0.5,
    "pollS": 60.0,
}
START = 1_000_000.0
DEADLINE = START + 3600 + 1800 + 7200


class Clock:
    def __init__(self, now: float = START) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def setup_dir(tmp_path: Path, lease: dict[str, Any] | None) -> Path:
    plan_dir = tmp_path / "tr1" / "gemma_qlora"
    guard.write_plan(plan_dir, LIMITS, now=START, owner_pid=os.getpid())
    if lease is not None:
        (plan_dir / "lease.json").write_text(json.dumps(lease), "utf-8")
    return plan_dir


def extra(vast: FakeVast) -> dict[str, Any]:
    return {"vast_runner": vast, "lease_sleep": lambda _s: None}


def lease_file(plan_dir: Path) -> dict[str, Any]:
    return json.loads((plan_dir / "lease.json").read_text("utf-8"))


def run_loop(plan_dir: Path, vast: FakeVast, clock: Clock, **kw: Any) -> str:
    return guard.guard_loop(
        plan_dir, extra(vast), clock=clock, sleep=clock.sleep, log=lambda _m: None, **kw
    )


def ready_lease(**more: Any) -> dict[str, Any]:
    return {"status": "READY", "instanceId": 7001, "label": "cfp-a", "preexisting": [900], **more}


def test_plan_fixes_deadline_once_and_records_start_credit(tmp_path: Path) -> None:
    vast = FakeVast(credit=50.0)
    vast.instances.append({"id": 7001, "label": "cfp-a"})
    plan_dir = setup_dir(tmp_path, ready_lease())
    # 다시 이어 가도 마감은 늦춰지지 않는다.
    guard.write_plan(plan_dir, {**LIMITS, "wallSeconds": 99_999.0}, now=START + 5000)
    clock = Clock()

    assert run_loop(plan_dir, vast, clock, max_checks=2) == "RUNNING"

    plan = guard.read_plan(plan_dir)
    assert plan["deadlineEpoch"] == DEADLINE
    assert plan["creditStart"] == 50.0
    assert plan["creditFloor"] == pytest.approx(50.0 - 10.0 - 0.5)
    assert vast.args("destroy", "instance") == []
    assert clock.sleeps == [60.0]
    state = guard.read_state(plan_dir)
    assert state["ready"] is True and state["pid"] == os.getpid()


def test_deadline_destroys_instance_and_ends(tmp_path: Path) -> None:
    vast = FakeVast()
    vast.instances.append({"id": 7001, "label": "cfp-a"})
    plan_dir = setup_dir(tmp_path, ready_lease())
    clock = Clock(DEADLINE + 1)

    assert run_loop(plan_dir, vast, clock) == "STOPPED"

    assert vast.args("destroy", "instance") == [
        ["vastai", "destroy", "instance", "7001", "--yes", "--raw"]
    ]
    data = lease_file(plan_dir)
    assert data["status"] == "DESTROYED"
    assert "마감" in data["guardStop"]["reason"]
    assert guard.read_state(plan_dir)["ended"] == "STOPPED"


def test_credit_below_floor_destroys_instance(tmp_path: Path) -> None:
    vast = FakeVast(credit=50.0)
    vast.instances.append({"id": 7001, "label": "cfp-a"})
    plan_dir = setup_dir(tmp_path, ready_lease())
    clock = Clock()

    class Draining:
        """두 번째 확인부터 잔액이 하한(39.5) 밑으로 떨어진다."""

        def __init__(self) -> None:
            self.reads = 0

        def __call__(self, argv: list[str], timeout: float) -> Any:
            if argv[1:3] == ["show", "user"]:
                self.reads += 1
                vast.credit = 50.0 if self.reads <= 2 else 39.0
            return vast(argv, timeout)

    result = guard.guard_loop(
        plan_dir,
        {"vast_runner": Draining(), "lease_sleep": lambda _s: None},
        clock=clock,
        sleep=clock.sleep,
        log=lambda _m: None,
    )

    assert result == "STOPPED"
    assert len(vast.args("destroy", "instance")) == 1
    assert "잔액" in lease_file(plan_dir)["guardStop"]["reason"]


def test_destroyed_lease_ends_guard_without_vast_destroy(tmp_path: Path) -> None:
    vast = FakeVast()
    plan_dir = setup_dir(tmp_path, ready_lease(status="DESTROYED"))

    assert run_loop(plan_dir, vast, Clock(DEADLINE + 1)) == "DESTROYED"

    assert vast.args("destroy", "instance") == []
    assert guard.read_state(plan_dir)["ended"] == "DESTROYED"


def test_unresolved_create_is_destroyed_by_label(tmp_path: Path) -> None:
    vast = FakeVast()
    vast.instances.append({"id": 7005, "label": "cfp-lost"})
    plan_dir = setup_dir(
        tmp_path, {"status": "UNRESOLVED", "label": "cfp-lost", "preexisting": [900]}
    )

    assert run_loop(plan_dir, vast, Clock(DEADLINE)) == "STOPPED"

    assert vast.args("destroy", "instance")[0][3] == "7005"
    assert lease_file(plan_dir)["status"] == "DESTROYED"


def test_failed_destroy_keeps_guard_retrying(tmp_path: Path) -> None:
    vast = FakeVast(destroy_works=False)
    vast.instances.append({"id": 7001, "label": "cfp-a"})
    plan_dir = setup_dir(tmp_path, ready_lease())

    assert run_loop(plan_dir, vast, Clock(DEADLINE + 1), max_checks=2) == "RUNNING"

    assert len(vast.args("destroy", "instance")) == 2  # 끝내지 않고 다음 주기에 다시 지운다
    assert lease_file(plan_dir)["status"] == "DESTROY_UNVERIFIED"


def test_guard_ends_when_drive_closed_without_lease(tmp_path: Path) -> None:
    vast = FakeVast()
    plan_dir = setup_dir(tmp_path, None)
    guard.close_if_unleased(plan_dir)

    assert run_loop(plan_dir, vast, Clock()) == "NO_LEASE"
    assert vast.args("destroy", "instance") == []


def test_guard_without_start_credit_never_reports_ready(tmp_path: Path) -> None:
    def broken(argv: list[str], timeout: float) -> Any:
        import subprocess

        return subprocess.CompletedProcess(argv, 1, "", "network down")

    plan_dir = setup_dir(tmp_path, None)
    with pytest.raises(TrainingError):
        guard.guard_loop(plan_dir, {"vast_runner": broken}, log=lambda _m: None)
    assert guard.read_state(plan_dir) == {}


class FakeProc:
    def __init__(self, pid: int, code: int | None) -> None:
        self.pid = pid
        self.code = code
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True


def test_start_guard_detaches_and_waits_for_ready(tmp_path: Path) -> None:
    plan_dir = tmp_path / "p"
    seen: dict[str, Any] = {}

    def popen(argv: list[str], **kw: Any) -> FakeProc:
        seen.update(argv=argv, **kw)
        guard._write(plan_dir / guard.STATE_FILE, {"pid": 4321, "ready": True})
        return FakeProc(4321, None)

    assert guard.start_guard(tmp_path, "cf", "gemma_qlora", plan_dir, popen=popen) == 4321
    assert seen["start_new_session"] is True
    assert seen["stdout"].name == str(plan_dir / "guard.log")
    assert "--plan-dir" in seen["argv"]


@pytest.mark.parametrize("code", [1, None])
def test_start_guard_refuses_when_not_confirmed(tmp_path: Path, code: int | None) -> None:
    proc = FakeProc(4321, code)
    clock = Clock(0.0)
    with pytest.raises(TrainingError, match="GPU를 빌리지 않는다"):
        guard.start_guard(
            tmp_path,
            "cf",
            "gemma_qlora",
            tmp_path / "p",
            popen=lambda argv, **kw: proc,
            clock=clock,
            sleep=clock.sleep,
            timeout_s=1.0,
        )
    assert proc.terminated is (code is None)


def test_ensure_guard_skips_start_when_heartbeat_is_fresh(tmp_path: Path, monkeypatch) -> None:
    started: list[Path] = []
    monkeypatch.setattr(guard, "start_guard", lambda *a, **k: started.append(a[3]) or 1)
    plan_dir = tmp_path / "p"

    assert guard.ensure_guard(tmp_path, "cf", "gemma_qlora", plan_dir, LIMITS) == "started"
    guard._write(
        plan_dir / guard.STATE_FILE,
        {"pid": os.getpid(), "ready": True, "heartbeatEpoch": 10_000.0},
    )
    assert (
        guard.ensure_guard(tmp_path, "cf", "gemma_qlora", plan_dir, LIMITS, clock=lambda: 10_060.0)
        == "running"
    )
    assert (
        guard.ensure_guard(tmp_path, "cf", "gemma_qlora", plan_dir, LIMITS, clock=lambda: 99_999.0)
        == "started"
    )
    assert started == [plan_dir, plan_dir]
