"""캐릭터 단위 병렬 실행. 보고서에는 원문·공급자 응답을 복사하지 않는다."""

from __future__ import annotations

import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from character_factory_poc.common.ids import character_id
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.batch import BatchCharacter, BatchSpec
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import CREATED, TRAIN, stages_for
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.origin import (
    CLI_NAMES,
    MODE_CLI_NAMES,
    read_model_mode,
    read_origin,
    write_model_mode,
    write_origin,
)
from character_factory_poc.pipeline.state import stage_events_path
from character_factory_poc.providers.tracked import WAIT_FILE
from character_factory_poc.stages.s3_plan.common import new_character


@dataclass
class CharacterReport:
    characterId: str
    origin: str
    modelMode: str
    until: str
    maxParallel: int
    status: str = "planned"
    stages: list[dict] = field(default_factory=list)
    waitingGates: list[str] = field(default_factory=list)
    failedStages: list[str] = field(default_factory=list)
    blockedStages: list[str] = field(default_factory=list)
    providerWaitSeconds: float = 0
    error: str | None = None


@dataclass
class BatchReport:
    batchId: str | None
    maxParallel: int
    characters: list[CharacterReport]

    def table(self) -> str:
        rows = [
            f"동시 캐릭터: 최대 {self.maxParallel}명",
            "캐릭터 | 출신 / 모델 | 목표 | 동시 단계 | 상태 | 대기 관문 | 공급자 대기(초) | 실패",
        ]
        for row in self.characters:
            rows.append(
                f"{row.characterId} | {row.origin} / {row.modelMode} | {row.until} | "
                f"{row.maxParallel} | {row.status} | {', '.join(row.waitingGates) or '-'} | "
                f"{row.providerWaitSeconds:.3f} | {', '.join(row.failedStages) or row.error or '-'}"
            )
        if any(r.stages for r in self.characters):
            rows.extend(["", "캐릭터 | 단계 | 시작(UTC) | 종료(UTC)"])
            for row in self.characters:
                for stage in row.stages:
                    rows.append(
                        f"{row.characterId} | {stage['stage']} | "
                        f"{stage['start']} | {stage['end'] or '-'}"
                    )
        return "\n".join(rows)


def _plan(ctx, item: BatchCharacter, base: Path):
    cid = item.character_id or character_id(item.slug)
    folder = ctx.character_dir(cid)
    if (
        folder.is_symlink()
        or folder.resolve().parent != (ctx.config.runs_dir / "characters").resolve()
    ):
        raise ValueError(f"캐릭터 폴더가 올바르지 않다: {cid}")
    if item.slug:
        if folder.exists():
            raise ValueError(f"이미 있는 캐릭터다: {cid}")
        origin = CLI_NAMES[item.origin or "original"]
        mode = MODE_CLI_NAMES[item.model_mode or "train"]
    else:
        if not (folder / "state.json").is_file() or ctx.state(cid).state.subjectId != cid:
            raise ValueError(f"기존 캐릭터 상태를 확인할 수 없다: {cid}")
        origin, mode = read_origin(folder), read_model_mode(folder)
        if (item.origin and CLI_NAMES[item.origin] != origin) or (
            item.model_mode and MODE_CLI_NAMES[item.model_mode] != mode
        ):
            raise ValueError(f"기존 캐릭터 출신·모델 방식과 다르다: {cid}")
    if origin == CREATED and (mode != TRAIN or item.source_pack):
        raise ValueError("오리지널은 TRAIN만 가능하며 source_pack을 받지 않는다")
    graph = stages_for(origin, mode)
    if item.until not in graph and item.until not in {s.gate for s in graph.values()}:
        raise ValueError(f"{cid}: 이 그래프에 없는 실행 목표: {item.until}")
    pack = (base / item.source_pack).resolve() if item.source_pack else None
    if pack is not None and not pack.is_file():
        raise ValueError(f"{cid}: 출처 묶음 파일이 없다")
    if item.slug and origin != CREATED and pack is None:
        raise ValueError(f"{cid}: 새 모티브는 source_pack이 필요하다")
    return item, CharacterReport(cid, origin, mode, item.until, item.max_parallel), pack


def _offset(path):
    return path.stat().st_size if path.exists() else 0


def _added(path, offset):
    if path.exists():
        with path.open("rb") as handle:
            handle.seek(offset)
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def _run_one(ctx, job):
    item, row, pack = job
    cid = row.characterId
    folder = ctx.character_dir(cid)
    events = stage_events_path(folder)
    waits = folder / "ledger" / WAIT_FILE
    try:
        ctx = ctx.for_character(cid)
        if item.slug:
            folder.mkdir(parents=True, exist_ok=False)
        # 같은 캐릭터를 다른 배치가 동시에 재개해 원장을 섞지 못하게 한다.
        with (folder / ".batch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if item.slug:
                if new_character(ctx, item.slug) != cid:
                    raise ValueError("실행 중 캐릭터 발급 날짜가 바뀌었다")
                write_origin(folder, row.origin)
                write_model_mode(folder, row.modelMode, reason="cfp batch run")
            event_start, wait_start = _offset(events), _offset(waits)
            try:
                log = run_until(
                    ctx,
                    cid,
                    RunOptions(until=item.until, source_pack=pack, max_parallel=item.max_parallel),
                )
                # 입력 검사 중 실패하면 RUNNING 전이라 stage-events가 없을 수 있다.
                row.failedStages = [
                    sid
                    for sid in log.blocked
                    if any(line.startswith(f"{sid}: 검사 실패 —") for line in log.steps)
                ]
                row.blockedStages = [sid for sid in log.blocked if sid not in row.failedStages]
            finally:
                attempts = {}
                for event in _added(events, event_start):
                    sid = event["stage"]
                    key = (sid, event["attempt"])
                    if event["to"] == "RUNNING":
                        attempts[key] = {
                            "stage": sid,
                            "attempt": event["attempt"],
                            "start": event["at"],
                            "end": None,
                        }
                    elif key in attempts and attempts[key]["end"] is None:
                        attempts[key].update(end=event["at"], result=event["to"])
                    if event["to"] == "CHECK_FAILED" and sid not in row.failedStages:
                        row.failedStages.append(sid)
                row.stages = list(attempts.values())
                row.providerWaitSeconds = sum(w["seconds"] for w in _added(waits, wait_start))
                state = ctx.state(cid).state
                row.waitingGates = [
                    g for g, s in state.gates.items() if s.status == "AWAITING_HUMAN"
                ]
            row.status = (
                "failed"
                if row.failedStages
                else "waiting"
                if row.waitingGates
                else "blocked"
                if row.blockedStages
                else "done"
            )
    except (Exception, SystemExit) as exc:
        row.status = "failed"
        row.error = type(exc).__name__  # 원문을 포함할 수 있는 공급자 메시지는 복사하지 않는다.


def run_batch(ctx: Context, spec: BatchSpec | dict | Path) -> BatchReport:
    """파일 입력의 source_pack은 spec 기준, 객체 입력은 설정 루트 기준이다."""
    base = ctx.config.root
    if isinstance(spec, Path):
        base = spec.resolve().parent
        spec = BatchSpec.model_validate_json(spec.read_bytes())
    spec = BatchSpec.model_validate(spec)
    jobs = [_plan(ctx, item, base) for item in spec.characters]
    rows = [row for _, row, _ in jobs]
    if len({r.characterId for r in rows}) != len(rows):
        raise ValueError("캐릭터 ID가 배치에서 겹친다")
    report = BatchReport(None, spec.max_parallel, rows)
    if ctx.execute:
        report.batchId = uuid4().hex
        with ThreadPoolExecutor(
            max_workers=spec.max_parallel, thread_name_prefix="cfp-batch"
        ) as pool:
            list(pool.map(lambda job: _run_one(ctx, job), jobs))
        path = ctx.config.runs_dir / "batches" / report.batchId / "batch-report.json"
        write_once_json(path, asdict(report))
    return report
