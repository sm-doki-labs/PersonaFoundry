"""S10t 실행 몰기: 감시 시작 → 제출 → 상태 확인 → 회수·체크포인트 선택 → GPU 반납 (D-0077).

임대 GPU는 쉬는 동안에도 비용이 든다. 그래서 학습이 끝날 때까지 이 함수가 상태를 확인하고, 끝나면
바로 회수해 GPU를 지운다. 비용 안전 규칙은 다음과 같다.

- 임대 전에 분리 감시(guard) 프로세스를 띄우고, 시작이 확인되지 않으면 빌리지 않는다. drive가
  죽어도 guard가 마감·잔액 하한에서 GPU를 지운다.
- 제출(임대·업로드 포함)과 학습 중 예외·중단(Ctrl-C, SIGTERM, SIGHUP)은 로그를 남기고 GPU를 지운다.
- 회수 단계 실패는 학습 결과를 잃지 않도록 GPU를 남기고 collectError를 기록한 뒤 멈춘다. 다음
  명령은 cfp train collect --execute, 그다음 cfp train cleanup이다. guard 마감은 그대로 지킨다.
- 회수가 끝나 GPU가 이미 지워진 뒤의 체크포인트 선택 실패는 GPU와 무관하므로 그대로 올린다.
  다시 실행하면 원격 상태를 묻지 않고 선택만 다시 한다.
"""

from __future__ import annotations

import json
import signal
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import NeedsInputError
from character_factory_poc.common.store import write_manifest
from character_factory_poc.contracts.training import TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training import make_training_provider
from character_factory_poc.providers.training.errors import (
    RemoteHostError,
    TrainingError,
    TrainingLimitError,
)
from character_factory_poc.stages.s10_train import guard as guard_mod
from character_factory_poc.stages.s10_train.collect import collect_s10t
from character_factory_poc.stages.s10_train.io import (
    build_request,
    ensure_failed,
    latest_rev,
    load_approved_dataset,
    read_run,
    resolve_providers,
    run_path,
    stop_requested,
    train_root,
    write_run,
)
from character_factory_poc.stages.s10_train.submit import submit_s10t

FINAL = {"FAILED", "CANCELLED"}
PENDING = "PENDING"


class DriveSignal(BaseException):  # noqa: N818 - KeyboardInterrupt처럼 중단으로 다룬다
    """SIGTERM·SIGHUP을 받아 drive를 중단한다. abort 경로를 타도록 BaseException이다."""

    def __init__(self, signum: int):
        super().__init__(f"신호 {signal.Signals(signum).name}")
        self.signum = signum


class DriveStopped(BaseException):  # noqa: N818 - 중단 경로(abort)를 타도록 BaseException이다
    """사람이 화면에서 학습 중단을 눌렀다(stop-request.json, D-0130)."""


def _check_stop(rev_dir: Path) -> None:
    if stop_requested(rev_dir):
        raise DriveStopped("사람이 학습을 중단했다")


def _wait(sleep: Callable[[float], None], interval: float, rev_dir: Path) -> None:
    """다음 상태 확인까지 쉰다. 실제 시계로 오래 쉴 때는 중단 요청을 2초마다 본다."""
    if sleep is not time.sleep or interval <= 2:
        sleep(interval)
        return
    end = time.monotonic() + interval
    while (left := end - time.monotonic()) > 0:
        sleep(min(2.0, left))
        if stop_requested(rev_dir):
            return


class CollectPendingError(TrainingError):
    """결과 회수에 실패해 GPU를 남겨 둔 채 멈췄다(회수 대기)."""


# ---- 실행 기록 판정 -------------------------------------------------------------------------


def selection_decision(run: TrainingRun) -> str | None:
    selection = run.appliedConfig.get("selection")
    if isinstance(selection, dict) and selection.get("decision"):
        return str(selection["decision"])
    return None


def is_done(run: TrainingRun) -> bool:
    """더 할 일이 없는 실행인가: 실패·취소, 또는 회수 뒤 선택 결과가 정해졌거나 binding이 있다."""
    if run.status in FINAL:
        return True
    if run.status != "SUCCEEDED":
        return False
    if run.modelBinding is not None:
        return True
    decision = selection_decision(run)
    return decision is not None and decision != PENDING


def needs_selection_only(run: TrainingRun) -> bool:
    """회수와 원격 정리는 끝났고(GPU 없음) 체크포인트 선택만 남았다."""
    return (
        run.status == "SUCCEEDED"
        and bool(run.appliedConfig.get("remoteDeleted"))
        and not is_done(run)
    )


def lease_alive(plan_dir: Path) -> bool:
    """provider 폴더의 lease.json이 지우지 않은 GPU를 가리킬 수 있는가."""
    path = plan_dir / "lease.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return True  # 읽을 수 없는 기록은 살아 있다고 보고 새로 빌리지 않는다
    status = str(data.get("status") or "NONE")
    return status not in {"NONE", "DESTROYED"} and bool(data.get("instanceId") or data.get("label"))


def needs_drive(run: TrainingRun, plan_dir: Path) -> bool:
    """새 계획(=새 GPU) 대신 이 실행을 이어서 몰아야 하는가."""
    alive = lease_alive(plan_dir)
    if is_done(run):
        return alive  # 끝났지만 GPU 기록이 남았으면 drive가 정리한다
    if run.status in {"SUBMITTED", "RUNNING", "SUCCEEDED"}:
        return True
    return alive  # PLANNED여도 임대 기록이 남았으면 그 GPU로 이어 간다


# ---- 신호 ------------------------------------------------------------------------------------


@contextmanager
def signals_as_exceptions() -> Iterator[None]:
    """SIGTERM·SIGHUP을 DriveSignal 예외로 바꾼다. 두 번째 신호부터는 정리를 끊지 않게 무시한다.

    메인 스레드가 아니면(웹 서버 작업 스레드 등) 처리기를 바꿀 수 없으므로 그대로 둔다.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    fired: list[int] = []

    def handler(signum: int, _frame: Any) -> None:
        if fired:
            return
        fired.append(signum)
        raise DriveSignal(signum)

    previous: dict[int, Any] = {}
    for name in ("SIGTERM", "SIGHUP"):
        signum = getattr(signal, name, None)
        if signum is not None:
            previous[signum] = signal.signal(signum, handler)
    try:
        yield
    finally:
        for signum, old in previous.items():
            signal.signal(signum, old)


# ---- 중단·정리 --------------------------------------------------------------------------------


def _abort_all(ctx: Context, cid: str, providers: list[str] | None, reason: str) -> None:
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        return
    dataset, dataset_dir = load_approved_dataset(ctx, cid)
    for item in resolve_providers(ctx, providers):
        path = run_path(rev_dir, item.adapter)
        if not path.exists():
            continue
        run = read_run(path)
        if is_done(run) and not lease_alive(rev_dir / item.adapter):
            continue
        if run.appliedConfig.get("remoteDeleted"):
            continue  # 회수가 끝나 GPU가 없다. 선택만 남은 기록을 취소로 덮지 않는다
        provider = make_training_provider(item.adapter, item.cfg)
        abort = getattr(provider, "abort", None)
        if abort is None:
            continue
        request = build_request(
            rev_dir, rev_dir.name, item.adapter, dataset, dataset_dir, run.budgetUsd
        )
        try:
            abort(run, request)
        finally:
            if run.status not in FINAL and not is_done(run):
                write_run(
                    path,
                    run.model_copy(
                        update={
                            "status": "CANCELLED",
                            "appliedConfig": {**run.appliedConfig, "error": reason[:500]},
                        }
                    ),
                )


def _start_guards(
    ctx: Context, cid: str, rev_dir: Path, resolved: list, log: Callable[[str], None]
) -> list[Path]:
    """임대 모드 공급자마다 GPU를 빌리기 전에 guard를 띄운다. 시작이 확인되지 않으면 예외."""
    guarded: list[Path] = []
    for item in resolved:
        provider = make_training_provider(item.adapter, item.cfg)
        limits_fn = getattr(provider, "guard_limits", None)
        if not getattr(provider, "uses_lease", False) or limits_fn is None:
            continue
        plan_dir = rev_dir / item.adapter
        run = read_run(run_path(rev_dir, item.adapter))
        if not needs_drive(run, plan_dir) and run.status != "PLANNED":
            continue
        if needs_selection_only(run) and not lease_alive(plan_dir):
            continue
        result = guard_mod.ensure_guard(
            ctx.config.root, cid, item.adapter, plan_dir, limits_fn(run)
        )
        plan = guard_mod.read_plan(plan_dir)
        log(f"{item.adapter}: guard {result}, 마감 {plan.get('deadlineAt')}")
        guarded.append(plan_dir)
    return guarded


def _collect_or_hold(
    ctx: Context, cid: str, adapter: str, path: Path, log: Callable[[str], None]
) -> None:
    """회수·선택을 부른다. 회수 실패면 GPU를 남기고 CollectPendingError, 선택 실패면 그대로 올린다.

    호출한 쪽은 이 함수가 올린 Exception에 대해 abort하지 않는다.
    """
    try:
        collect_s10t(ctx, cid, [adapter])
    except Exception as exc:
        run = read_run(path)
        if run.appliedConfig.get("remoteDeleted"):
            raise  # 선택 단계 실패: GPU는 이미 지웠다
        message = f"{type(exc).__name__}: {exc}"[:500]
        write_run(
            path,
            run.model_copy(
                update={
                    "appliedConfig": {
                        **run.appliedConfig,
                        "collectError": message,
                        "collectPending": True,
                    }
                }
            ),
        )
        deadline = guard_mod.read_plan(path.parent).get("deadlineAt")
        hint = f" guard가 마감 {deadline}에 GPU를 지운다." if deadline else ""
        log(f"{adapter}: 회수 실패 — GPU를 남겨 둔다({message})")
        raise CollectPendingError(
            f"{adapter}: 결과 회수에 실패해 GPU를 남겨 두었다({message}). "
            f"다음 명령: cfp train collect {cid} --execute 로 다시 회수하고, 그다음 "
            f"cfp train cleanup {cid} --execute 로 남은 GPU를 지운다.{hint}"
        ) from exc
    run = read_run(path)
    if run.appliedConfig.get("collectPending"):
        applied = {k: v for k, v in run.appliedConfig.items() if k != "collectPending"}
        if "collectError" in applied:
            applied["lastCollectError"] = applied.pop("collectError")
        write_run(path, run.model_copy(update={"appliedConfig": applied}))


# ---- drive -------------------------------------------------------------------------------------


def drive_s10t(
    ctx: Context,
    cid: str,
    providers: list[str] | None = None,
    *,
    poll_s: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> Path:
    """학습이 끝날 때까지 몰고 간다. 반환은 최신 학습 revision 폴더다."""
    if not ctx.execute:
        raise TrainingLimitError("학습 실행은 --execute가 있어야 한다(기본은 plan dry run)")
    interval = float(ctx.config.stage("s10t").get("poll_s", 60.0) if poll_s is None else poll_s)
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        raise NeedsInputError("s10t 계획이 없다")
    dataset, dataset_dir = load_approved_dataset(ctx, cid)
    resolved = resolve_providers(ctx, providers)
    state = ctx.state(cid)
    keep_gpu = False  # 회수·선택 단계 예외는 GPU를 지우지 않는다
    guarded: list[Path] = []
    with signals_as_exceptions():
        try:
            _check_stop(rev_dir)
            guarded = _start_guards(ctx, cid, rev_dir, resolved, log)
            submit_s10t(ctx, cid, providers)
            while True:
                _check_stop(rev_dir)
                pending: list[str] = []
                for item in resolved:
                    path = run_path(rev_dir, item.adapter)
                    run = read_run(path)
                    provider = make_training_provider(item.adapter, item.cfg)
                    request = build_request(
                        rev_dir, rev_dir.name, item.adapter, dataset, dataset_dir, run.budgetUsd
                    )
                    if is_done(run):
                        if lease_alive(request.plan_dir):
                            log(f"{item.adapter}: 끝난 실행의 GPU 기록이 남아 지운다")
                            if run.status in FINAL and getattr(provider, "abort", None):
                                provider.abort(run, request)
                            elif getattr(provider, "release", None):
                                provider.release(request)
                        continue
                    if needs_selection_only(run):
                        log(f"{item.adapter}: 회수는 끝났다. 체크포인트 선택만 다시 한다")
                        keep_gpu = True
                        collect_s10t(ctx, cid, [item.adapter])
                        keep_gpu = False
                        continue
                    if run.status == "SUCCEEDED":
                        updated = run  # 학습은 끝났고 회수가 남았다(회수 대기에서 이어 감)
                    else:
                        updated = provider.status(run, request)
                        write_run(path, updated)
                    if updated.status == "SUCCEEDED":
                        log(f"{item.adapter}: 학습 완료, 회수와 체크포인트 선택")
                        keep_gpu = True
                        _collect_or_hold(ctx, cid, item.adapter, path, log)
                        keep_gpu = False
                    elif updated.status in FINAL:
                        reason = str(updated.appliedConfig.get("error") or updated.status)
                        log(f"{item.adapter}: 실패 — {reason}. 로그를 남기고 GPU를 지운다")
                        abort = getattr(provider, "abort", None)
                        if abort is not None:
                            abort(updated, request)
                        ensure_failed(state, rev_dir.name, f"{item.adapter}: {reason}")
                    else:
                        pending.append(f"{item.adapter}={updated.status}")
                if not pending:
                    break
                log("학습 진행 중: " + ", ".join(pending))
                _wait(sleep, interval, rev_dir)
        except BaseException as exc:
            if not (keep_gpu and isinstance(exc, Exception)):
                _abort_all(ctx, cid, providers, f"실행 중단: {type(exc).__name__}: {exc}")
            if isinstance(exc, DriveStopped):
                ensure_failed(state, rev_dir.name, "사람이 학습을 중단했다")
            raise
        finally:
            for plan_dir in guarded:
                guard_mod.close_if_unleased(plan_dir)
    write_manifest(rev_dir)
    return rev_dir


# ---- cleanup -----------------------------------------------------------------------------------


def _lease_paths(ctx: Context, cid: str) -> list[tuple[Path, str | None]]:
    """정리할 lease.json: 모든 학습 revision의 공급자 폴더와 평가 inference 폴더."""
    found: list[tuple[Path, str | None]] = []
    root = train_root(ctx, cid)
    if root.is_dir():
        for rev in sorted(p for p in root.glob("tr*") if p.is_dir()):
            for path in sorted(rev.glob("*/**/lease.json")):
                found.append((path, path.relative_to(rev).parts[0]))
    eval_root = ctx.character_dir(cid) / "s10-eval"
    if eval_root.is_dir():
        for path in sorted(eval_root.glob("*/inference/**/lease.json")):
            found.append((path, None))
    return found


def cleanup_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> list[str]:
    """남은 임대 GPU 기록을 모두 찾아 지운다. 지운 인스턴스 ID 목록을 돌려준다.

    옛 학습 revision과 평가 GPU 세션까지 훑는다. 인스턴스 ID 없이 남은 생성 기록
    (CREATING·UNRESOLVED·AMBIGUOUS)은 라벨로 Vast 목록에서 찾아 지운다. 하나가 실패해도 나머지를
    마저 지우고, 실패가 있으면 끝에 모아서 알린다.
    """
    from character_factory_poc.providers.training.vast import VastLease

    configs = {item.adapter: item.cfg.extra for item in resolve_providers(ctx, providers)}
    default_extra = configs.get("gemma_qlora")
    if default_extra is None:
        [gemma] = resolve_providers(ctx, ["gemma_qlora"])
        default_extra = gemma.cfg.extra
    removed: list[str] = []
    failures: list[str] = []
    for path, adapter in _lease_paths(ctx, cid):
        extra = configs.get(adapter or "", default_extra)
        lease = VastLease.from_extra(path, extra)
        if not lease.is_alive():
            continue
        try:
            if lease.instance_id:
                ident = lease.instance_id
                lease.destroy()
                removed.append(ident)
            else:
                removed += lease.destroy_by_label()
        except RemoteHostError as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        raise RemoteHostError(
            "GPU 정리 일부 실패(지운 것: "
            + (", ".join(removed) or "없음")
            + "): "
            + "; ".join(failures)
        )
    return removed
