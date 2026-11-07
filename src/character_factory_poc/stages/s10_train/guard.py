"""S10t 임대 GPU 분리 감시(guard) (D-0077, 머스크 N3b guard.py 방식).

drive가 GPU를 빌리기 전에 새 세션의 별도 프로세스로 띄운다. drive가 죽거나 터미널이 닫혀도 남아서
provider 폴더의 lease.json을 주기적으로 읽고, 다음 가운데 하나면 GPU를 지운 뒤 기록하고 끝난다.

- 마감 시각(시작 + 학습 벽시계 상한 + GPU 준비 대기 상한 + 회수 여유)을 넘었다.
- Vast 잔액이 하한(시작 잔액 − 예산 − 예비) 밑으로 내려갔다.

lease가 DESTROYED가 되면(회수·중단·정리로 이미 지움) 그냥 끝난다. 아직 임대 전(NONE)인데 drive가
끝났거나 임대를 포기했으면 끝난다. 삭제 확인에 실패하면 끝나지 않고 다음 주기에 다시 지운다.

guard.json(마감·하한)은 처음 한 번만 정하고, 다시 이어 갈 때도 마감을 늦추지 않는다.
시험은 프로세스를 띄우지 않고 guard_loop를 가짜 시계·가짜 vastai로 직접 부른다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.providers.training.errors import RemoteHostError, TrainingError
from character_factory_poc.providers.training.vast import VastLease

PLAN_FILE = "guard.json"
STATE_FILE = "guard-state.json"
LOG_FILE = "guard.log"
LEASE_FILE = "lease.json"
LABEL_ONLY = {"CREATING", "UNRESOLVED", "AMBIGUOUS"}


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds")


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_plan(plan_dir: Path) -> dict[str, Any]:
    return _read(plan_dir / PLAN_FILE)


def read_state(plan_dir: Path) -> dict[str, Any]:
    return _read(plan_dir / STATE_FILE)


def write_plan(
    plan_dir: Path, limits: dict[str, float], *, now: float, owner_pid: int | None = None
) -> dict[str, Any]:
    """마감·예산을 처음 한 번만 정한다. 이미 있으면 소유 프로세스만 바꾸고 마감은 그대로 둔다."""
    path = plan_dir / PLAN_FILE
    plan = _read(path)
    if not plan:
        deadline = (
            now
            + float(limits["wallSeconds"])
            + float(limits["readyTimeoutS"])
            + float(limits["collectMarginS"])
        )
        plan = {
            "createdAt": _iso(now),
            "deadlineEpoch": deadline,
            "deadlineAt": _iso(deadline),
            "wallSeconds": float(limits["wallSeconds"]),
            "readyTimeoutS": float(limits["readyTimeoutS"]),
            "collectMarginS": float(limits["collectMarginS"]),
            "budgetUsd": float(limits["budgetUsd"]),
            "reserveUsd": float(limits["reserveUsd"]),
            "pollS": float(limits.get("pollS", 60.0)),
        }
    plan["ownerPid"] = owner_pid if owner_pid is not None else os.getpid()
    plan.pop("closed", None)
    _write(path, plan)
    return plan


def close_if_unleased(plan_dir: Path) -> None:
    """임대하지 않고 끝난 drive가 guard에게 그만 기다리라고 알린다."""
    plan = read_plan(plan_dir)
    if not plan:
        return
    lease = _read(plan_dir / LEASE_FILE)
    if str(lease.get("status") or "NONE") == "NONE":
        plan["closed"] = True
        _write(plan_dir / PLAN_FILE, plan)


def is_running(plan_dir: Path, now: float) -> bool:
    state = read_state(plan_dir)
    if not state.get("ready") or state.get("ended"):
        return False
    if not pid_alive(state.get("pid")):
        return False
    poll = float(read_plan(plan_dir).get("pollS", 60.0))
    beat = float(state.get("heartbeatEpoch") or 0.0)
    return now - beat <= max(3 * poll, 180.0)


def _stop(lease: VastLease) -> list[str]:
    if lease.instance_id:
        ident = lease.instance_id
        lease.destroy()
        return [ident]
    if lease.status in LABEL_ONLY or lease.label:
        return lease.destroy_by_label()
    return []


def guard_loop(
    plan_dir: Path,
    extra: dict[str, Any],
    *,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[Any], bool] = pid_alive,
    log: Callable[[str], None] = print,
    max_checks: int | None = None,
) -> str:
    """감시 루프. 돌려주는 값: STOPPED·DESTROYED·NO_LEASE·EXPIRED·RUNNING(max_checks 도달)."""
    lease_path = plan_dir / LEASE_FILE
    plan = read_plan(plan_dir)
    if not plan:
        raise TrainingError(f"guard 계획이 없다: {plan_dir / PLAN_FILE}")
    cli = VastLease.from_extra(lease_path, extra).cli
    if plan.get("creditStart") is None:
        # 첫 잔액을 못 읽으면 준비 완료를 쓰지 않는다 → drive가 임대하지 않는다.
        credit = cli.credit()
        plan["creditStart"] = credit
        plan["creditFloor"] = credit - float(plan["budgetUsd"]) - float(plan["reserveUsd"])
        _write(plan_dir / PLAN_FILE, plan)
    floor = float(plan["creditFloor"])
    deadline = float(plan["deadlineEpoch"])
    poll = float(plan.get("pollS", 60.0))
    state: dict[str, Any] = {
        "pid": os.getpid(),
        "ready": True,
        "startedAt": _iso(clock()),
        "deadlineAt": plan.get("deadlineAt"),
        "creditFloor": floor,
        "heartbeatEpoch": clock(),
    }
    _write(plan_dir / STATE_FILE, state)
    log(f"guard 시작: 마감 {plan.get('deadlineAt')}, 잔액 하한 ${floor:.2f}")

    def finish(result: str, **extra_state: Any) -> str:
        state.update(ended=result, endedAt=_iso(clock()), **extra_state)
        _write(plan_dir / STATE_FILE, state)
        log(f"guard 종료: {result}")
        return result

    checks = 0
    while True:
        plan = read_plan(plan_dir)
        lease = VastLease.from_extra(lease_path, extra)
        now = clock()
        if lease.status == "DESTROYED":
            return finish("DESTROYED")
        unleased = lease.status == "NONE"
        if unleased and (plan.get("closed") or not alive(plan.get("ownerPid"))):
            return finish("NO_LEASE")
        credit: float | None
        try:
            credit = cli.credit()
        except RemoteHostError:
            credit = None
        reason = None
        if now >= deadline:
            reason = f"마감 {plan.get('deadlineAt')}을 넘었다"
        elif credit is not None and credit < floor:
            reason = f"Vast 잔액 ${credit:.2f}가 하한 ${floor:.2f} 밑이다"
        state.update(heartbeatEpoch=now, lastCredit=credit, lease=lease.status)
        _write(plan_dir / STATE_FILE, state)
        log(json.dumps({"time": _iso(now), "credit": credit, "lease": lease.status}))
        if reason and unleased:
            return finish("EXPIRED", reason=reason)
        if reason:
            log(f"guard 정지: {reason}. GPU를 지운다")
            try:
                removed = _stop(lease)
            except RemoteHostError as exc:
                log(f"삭제 확인 실패, 다음 주기에 다시 지운다: {exc}")
            else:
                stop = {"reason": reason, "at": _iso(clock()), "removed": removed}
                lease.load()
                lease.record(guardStop=stop)
                return finish("STOPPED", stop=stop)
        checks += 1
        if max_checks is not None and checks >= max_checks:
            return "RUNNING"
        sleep(poll)


def start_guard(
    root: Path,
    cid: str,
    adapter: str,
    plan_dir: Path,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    timeout_s: float = 30.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """guard를 새 세션의 프로세스로 띄우고 준비 기록이 생길 때까지 기다린다. 실패하면 예외."""
    argv = [
        sys.executable,
        "-c",
        "from character_factory_poc.stages.s10_train.guard import main; raise SystemExit(main())",
        "--root",
        str(root),
        "--character",
        cid,
        "--provider",
        adapter,
        "--plan-dir",
        str(plan_dir),
    ]
    plan_dir.mkdir(parents=True, exist_ok=True)
    with (plan_dir / LOG_FILE).open("a", encoding="utf-8") as out:
        proc = popen(
            argv,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(root),
            start_new_session=True,
        )
    limit = clock() + timeout_s
    while clock() < limit:
        if proc.poll() is not None:
            raise TrainingError(
                f"guard가 시작 직후 끝났다({plan_dir / LOG_FILE} 확인). GPU를 빌리지 않는다"
            )
        state = read_state(plan_dir)
        if state.get("pid") == proc.pid and state.get("ready"):
            return int(proc.pid)
        sleep(0.2)
    try:
        proc.terminate()
    except OSError:
        pass
    raise TrainingError("guard 시작을 확인하지 못했다. GPU를 빌리지 않는다")


def ensure_guard(
    root: Path,
    cid: str,
    adapter: str,
    plan_dir: Path,
    limits: dict[str, float],
    *,
    clock: Callable[[], float] = time.time,
) -> str:
    """guard가 돌고 있지 않으면 띄운다. 돌려주는 값: running·started."""
    write_plan(plan_dir, limits, now=clock())
    if is_running(plan_dir, clock()):
        return "running"
    start_guard(root, cid, adapter, plan_dir)
    return "started"


def run_guard(root: Path, cid: str, adapter: str, plan_dir: Path) -> str:
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.stages.s10_train.io import resolve_providers

    ctx = Context.load(root, execute=True)
    [item] = resolve_providers(ctx, [adapter])
    return guard_loop(plan_dir, item.cfg.extra, log=lambda m: print(m, flush=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cfp-train-guard")
    parser.add_argument("--root", required=True)
    parser.add_argument("--character", required=True)
    parser.add_argument("--provider", default="gemma_qlora")
    parser.add_argument("--plan-dir", required=True)
    args = parser.parse_args(argv)
    run_guard(Path(args.root), args.character, args.provider, Path(args.plan_dir))
    return 0
