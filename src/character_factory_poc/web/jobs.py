"""작업 큐 (PoC 계획서 §6).

POST /api/jobs가 받은 요청을 한 캐릭터당 하나로 묶어 백그라운드 스레드에서 기존 오케스트레이터
(cli run이 부르는 run_until)를 돌린다. 단계·관문 상태 변화는 SSE로 밀어 준다.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import os
import re
import sys
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.config import load_config
from character_factory_poc.contracts.common import State
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, run_until
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.events import EventHub
from character_factory_poc.web.settings import WebSettings

MAX_LOG_LINES = 2000
MAX_HISTORY = 200
MAX_CREATOR_BRIEF_CHARS = 20_000
# D-0130: train = 유료 학습 제출·완료까지(비용 확인 필요).
# skip-training = 학습 없이 진행을 고르고 이어서 실행한다.
VIDEO_TRIGGERS = {"videos", "videos-with-chat"}
ACTIONS = {"run", "train", "skip-training"}
TRAIN_STARTABLE = {"plan", "stopped", "fail", "hold", "done", "skip"}
SKIP_ALLOWED = {"plan", "stopped", "fail"}
_JOB_ID_RE = re.compile(r"^job-[A-Za-z0-9-]{1,64}$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_job_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"job-{stamp}-{uuid.uuid4().hex[:4]}"


def _sort_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


class CharacterLocks:
    """캐릭터 하나에 관문 결정과 작업이 동시에 쓰지 않게 막는다."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def get(self, character_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(character_id, threading.Lock())

    @contextlib.contextmanager
    def hold(self, character_id: str) -> Iterator[None]:
        lock = self.get(character_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()


@dataclass
class Job:
    job_id: str
    character_id: str
    action: str = "run"
    until: str = "G6"
    status: str = "queued"
    created_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    stopped_at: str | None = None
    waiting: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    # D-0049(LLD §6.7): 무엇이 시작했나(manual|gate), 사람이 실행을 확인한 단계, 확인을 기다린 단계
    trigger: str = "manual"
    confirm: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    ran_stages: list[str] | None = None
    seq: int = 0  # 같은 초에 만든 작업의 순서(기록에는 남기지 않는다)

    def as_dict(self, *, include_log: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "jobId": self.job_id,
            "characterId": self.character_id,
            "action": self.action,
            "until": self.until,
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "error": self.error,
            "stoppedAt": self.stopped_at,
            "waiting": list(self.waiting),
            "blocked": list(self.blocked),
            "trigger": self.trigger,
            "confirm": list(self.confirm),
            "held": list(self.held),
            "ranStages": self.ran_stages,
            "logLines": len(self.log),
            "result": {
                "stoppedAt": self.stopped_at,
                "waiting": list(self.waiting),
                "blocked": list(self.blocked),
                "held": list(self.held),
            },
        }
        if include_log:
            data["log"] = list(self.log)
            data["steps"] = list(self.steps)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        def text(key: str, default: str = "") -> str:
            value = data.get(key, default)
            return value if isinstance(value, str) else default

        def texts(key: str) -> list[str]:
            value = data.get(key, [])
            return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

        return cls(
            job_id=text("jobId"),
            character_id=text("characterId"),
            action=text("action", "run"),
            until=text("until", "G6"),
            status=text("status", "queued"),
            created_at=text("createdAt", now_iso()),
            started_at=text("startedAt") or None,
            finished_at=text("finishedAt") or None,
            error=text("error") or None,
            log=texts("log"),
            steps=texts("steps"),
            stopped_at=text("stoppedAt") or None,
            waiting=texts("waiting"),
            blocked=texts("blocked"),
            trigger=text("trigger", "manual"),
            confirm=texts("confirm"),
            held=texts("held"),
            ran_stages=texts("ranStages") if isinstance(data.get("ranStages"), list) else None,
        )


Runner = Callable[[Job, "_JobStream"], RunLog]


class JobManager:
    def __init__(
        self,
        root: Path,
        settings: WebSettings,
        hub: EventHub,
        runner: Runner | None = None,
        locks: CharacterLocks | None = None,
    ):
        self.root = Path(root)
        self.settings = settings
        self.hub = hub
        self.locks = locks or CharacterLocks()
        self._runner: Runner = runner or self._run_default
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: dict[str, str] = {}
        self._rerun: dict[str, bool] = {}
        self._seq = itertools.count(1)
        self._signatures: dict[str, str] = {}
        self._router: _StdoutRouter | None = None
        self._load_history()

    # ---- 조회 ----

    def get(self, job_id: str) -> dict[str, Any]:
        if not _JOB_ID_RE.match(job_id or ""):
            raise WebError(400, f"작업 id 형식이 아니다: {job_id!r}")
        job = self._lookup(job_id)
        if job is None:
            raise WebError(404, f"작업이 없다: {job_id}")
        return job.as_dict()

    def list(self, character_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        if character_id:
            jobs = [j for j in jobs if j.character_id == character_id]
        jobs.sort(key=lambda j: (j.created_at, j.seq, j.job_id), reverse=True)
        return [j.as_dict(include_log=False) for j in jobs[: max(1, min(limit, MAX_HISTORY))]]

    def active_for(self, character_id: str) -> dict[str, Any] | None:
        with self._lock:
            job_id = self._active.get(character_id)
            job = self._jobs.get(job_id) if job_id else None
        return job.as_dict(include_log=False) if job else None

    def active_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [self._jobs[jid] for jid in self._active.values() if jid in self._jobs]
        return [j.as_dict(include_log=False) for j in jobs]

    # ---- 시작 ----

    def submit(
        self,
        character_id: str,
        action: str = "run",
        until: str | None = None,
        *,
        confirm: list[str] | None = None,
        trigger: str = "manual",
    ) -> dict:
        char_dir = reads.character_dir(self.root, character_id)
        if self.settings.server_mode and not char_dir.is_relative_to(self.root):
            raise WebError(403, "공장 루트 밖에서는 작업을 실행할 수 없다")
        state_path = char_dir / "state.json"
        if state_path.is_symlink() or (
            state_path.exists() and not state_path.resolve().is_relative_to(char_dir.resolve())
        ):
            raise WebError(409, "진행 상태 파일이 캐릭터 폴더 밖을 가리켜 실행할 수 없다")
        if state_path.exists():
            raw_state, state_error = reads.read_state(char_dir)
            if state_error:
                raise WebError(409, f"진행 상태가 손상되어 실행할 수 없다: {state_error}")
            try:
                parsed_state = State.model_validate(raw_state)
            except ValueError as exc:
                raise WebError(409, "진행 상태가 state-v1 형식에 맞지 않아 실행할 수 없다") from exc
            if parsed_state.subjectId != character_id:
                raise WebError(409, "진행 상태의 캐릭터 ID가 달라 실행할 수 없다")
        action = (action or "").strip()
        if action not in ACTIONS:
            raise WebError(400, f"action은 {', '.join(sorted(ACTIONS))}만 받는다: {action!r}")
        gate_or_stage = (until or self.settings.default_until or "G6").strip()
        stages, gates, _ = reads.graph_parts(char_dir)
        if gate_or_stage not in stages and gate_or_stage not in gates:
            raise WebError(
                400,
                f"until은 이 캐릭터의 단계나 관문 중 하나다: {gate_or_stage!r}",
            )
        confirmed = list(confirm or [])
        bad = [s for s in confirmed if not isinstance(s, str) or s not in stages]
        if bad:
            raise WebError(400, f"confirm은 단계 ID 목록이다: {bad!r}")
        if action in {"train", "skip-training"}:
            self._check_training_action(char_dir, action, confirmed)
        with self._lock:
            running = self._active.get(character_id)
            if running:
                raise WebError(409, f"이 캐릭터는 이미 작업이 돈다: {running}")
            job = Job(
                job_id=new_job_id(),
                character_id=character_id,
                action=action,
                until=gate_or_stage,
                trigger=trigger,
                confirm=confirmed,
                seq=next(self._seq),
            )
            self._jobs[job.job_id] = job
            self._active[character_id] = job.job_id
        self._persist(job)
        self._publish_job(job)
        thread = threading.Thread(
            target=self._run,
            args=(job,),
            name=f"cfp-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job.as_dict(include_log=False)

    def _check_training_action(self, char_dir: Path, action: str, confirmed: list[str]) -> None:
        """학습 조작이 지금 상태에서 말이 되는지 본다(D-0130)."""
        from character_factory_poc.web.model_path import training_view

        state = reads.read_state(char_dir)[0]
        kind = training_view(char_dir, state)["state"]
        if action == "train":
            if "s10t" not in confirmed:
                raise WebError(
                    400, "유료 학습은 비용을 확인한 뒤 시작해요(confirm에 s10t가 필요하다)"
                )
            if kind not in TRAIN_STARTABLE:
                raise WebError(409, f"지금은 학습을 시작할 수 없어요(학습 상태 {kind})")
        elif kind not in SKIP_ALLOWED:
            raise WebError(409, f"지금은 학습 없이 진행을 고를 수 없어요(학습 상태 {kind})")

    def request_resume(self, character_id: str) -> dict | None:
        """관문 결정 뒤 이어서 돌린다(D-0049, LLD §6.7). 이미 돌고 있으면 끝난 뒤 한 번 더."""
        settings = self._orchestrator()
        if not settings.get("auto_resume", False):
            return None
        with self._lock:
            if self._active.get(character_id):
                self._rerun[character_id] = True
                return None
        until = str(settings.get("resume_until", "sx"))
        try:
            return self.submit(character_id, until=until, trigger="gate")
        except WebError as exc:
            if exc.status != 409:
                raise
            with self._lock:
                self._rerun[character_id] = True
            return None

    def _orchestrator(self) -> dict[str, Any]:
        try:
            return dict(load_config(self.root, self.settings.config_path).orchestrator)
        except (OSError, ValueError):
            return {}

    def _run(self, job: Job) -> None:
        self._run_locked(job)
        with self._lock:
            again = self._rerun.pop(job.character_id, False)
        # 학습이 끝나면 평가부터 이어서 돈다(자동 재개 설정일 때). 평가가 GPU를 빌려야 하면
        # 오케스트레이터가 실행 확인을 받는다(D-0130).
        trained = job.action == "train" and job.status == "succeeded" and job.stopped_at == "s10t"
        if again or trained:
            self.request_resume(job.character_id)

    def _run_locked(self, job: Job) -> None:
        with self.locks.hold(job.character_id):
            job.status = "running"
            job.started_at = now_iso()
            self._persist(job)
            self._publish_job(job)
            stream = _JobStream(self, job)
            router = self._stdout_router()
            router.register(stream)
            try:
                log = self._dispatch(job, stream)
                job.stopped_at = log.stopped_at
                job.ran_stages = list(log.timings)
                job.steps = list(log.steps)
                job.waiting = list(log.waiting)
                job.blocked = list(log.blocked)
                job.held = list(getattr(log, "held", []))
                job.status = "succeeded"
            except (Exception, SystemExit) as exc:  # 작업 실패를 기록하고 서버는 계속 돈다
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                self._append_log(job, f"작업 실패: {job.error}")
            finally:
                router.unregister()
                job.finished_at = now_iso()
                stream.flush_lines()
                self._persist(job)
                with self._lock:
                    if self._active.get(job.character_id) == job.job_id:
                        del self._active[job.character_id]
                self._publish_job(job)
                self.publish_state(job.character_id, force=True)

    def run_options(self, job: Job, stream: _JobStream, **over: Any) -> RunOptions:
        """워크숍 실행의 RunOptions(D-0049): 물결 실행, 유료 단계 확인, 작업 스레드 로그 연결."""
        orch = self._orchestrator()
        router = self._stdout_router()

        def wrap(fn: Callable) -> Callable:
            def inner(*args: Any, **kwargs: Any) -> Any:
                router.register(stream)
                try:
                    return fn(*args, **kwargs)
                finally:
                    router.unregister()

            return inner

        values: dict[str, Any] = {
            "until": job.until,
            "max_parallel": int(orch.get("max_parallel", 1)),
            "web": True,
            "confirmed": set(job.confirm),
            "wrap_worker": wrap,
        }
        values.update(over)
        return RunOptions(**values)

    def _dispatch(self, job: Job, stream: _JobStream) -> RunLog:
        if job.action == "train":
            return self._run_train(job)
        if job.action == "skip-training":
            self._choose_skip(job.character_id)
        return self._runner(job, stream)

    def _choose_skip(self, character_id: str) -> None:
        from character_factory_poc.stages.s10_train.io import choose_skip

        rev = self._train_rev(character_id)
        if rev is None:
            raise RuntimeError("학습 계획이 없어 '학습 없이 진행'을 남길 수 없다")
        choose_skip(rev, now_iso())
        self._append_log_line(character_id, "s10t: 학습 없이 진행을 골랐다")

    def _train_rev(self, character_id: str) -> Path | None:
        from character_factory_poc.web.model_path import _latest

        return _latest(reads.character_dir(self.root, character_id) / "s10-train", "tr")

    def _run_train(self, job: Job) -> RunLog:
        """유료 학습: 최신 계획이 그대로면 그 계획으로, 아니면 새 계획을 세워 끝까지 몬다(D-0130).

        GPU 임대·감시·회수·반납 규칙은 cfp train drive와 같다. 화면의 중단 요청은
        stop-request.json으로 들어와 drive가 GPU를 반납하고 멈춘다.
        """
        from character_factory_poc.stages.s10_train.drive import DriveStopped, drive_s10t
        from character_factory_poc.stages.s10_train.io import (
            clear_skip,
            read_run,
            resolve_providers,
            run_path,
        )
        from character_factory_poc.stages.s10_train.run import run_s10t

        config = load_config(self.root, self.settings.config_path)
        ctx = Context(config=config, execute=True)
        cid = job.character_id
        log = RunLog()
        rev = self._train_rev(cid)
        if rev is not None:
            clear_skip(rev)
        planned = rev is not None and all(
            run_path(rev, item.adapter).is_file()
            and read_run(run_path(rev, item.adapter)).status == "PLANNED"
            for item in resolve_providers(ctx, None)
        )
        which = f"({rev.name} 계획)" if planned and rev else "(새 계획)"
        log.add("s10t: 학습 실행" + which)
        try:
            out = drive_s10t(ctx, cid) if planned else run_s10t(ctx, cid)
        except DriveStopped:
            log.add("s10t: 사람이 학습을 중단했다. GPU를 반납했다")
            log.stopped_at = "stopped"
            return log
        log.add(f"s10t: 학습 끝 → {out}")
        log.stopped_at = "s10t"
        return log

    def _append_log_line(self, character_id: str, line: str) -> None:
        with self._lock:
            job_id = self._active.get(character_id)
            job = self._jobs.get(job_id) if job_id else None
        if job is not None:
            self._append_log(job, line)

    def _run_default(self, job: Job, stream: _JobStream) -> RunLog:
        """cli run과 같은 경로: 설정을 읽어 Context를 만들고 run_until을 돌린다."""
        brief = self._creator_brief(job.character_id)
        config = load_config(self.root, self.settings.config_path)
        ctx = Context(config=config, execute=True)
        options = self.run_options(job, stream)
        if brief is not None:
            options = replace(options, brief_text=brief)
        if job.trigger in VIDEO_TRIGGERS:
            if job.trigger == "videos-with-chat":
                chat = run_until(
                    ctx, job.character_id, replace(options, until="s8c", confirmed=set())
                )
                if (
                    chat.stopped_at != "s8c"
                    or ctx.state(job.character_id).gate("G6").status != "APPROVED"
                ):
                    raise ValueError("대화 준비를 마치지 못했어요.")
            options = replace(options, video_only=True)
        log = run_until(ctx, job.character_id, options)
        if job.trigger in VIDEO_TRIGGERS and (
            log.stopped_at != "G5b" or ctx.state(job.character_id).gate("G5b").status != "APPROVED"
        ):
            raise ValueError("영상 만들기를 마치지 못했어요.")
        if job.until == "s8c" and ctx.state(job.character_id).stage("s8c").status != "APPROVED":
            state = ctx.state(job.character_id)
            if (log.waiting or log.held) and not any(
                state.stage(sid).status == "CHECK_FAILED" for sid in log.blocked
            ):
                return log
            raise ValueError("대화 준비를 마치지 못했어요. 멈춘 단계의 작업 기록을 확인해 주세요.")
        return log

    def _creator_brief(self, character_id: str) -> str | None:
        """생성 요청이 고정한 브리프를 읽는다. 없는 파일은 기존 CLI 입력 동작을 지킨다."""
        char_dir = reads.character_dir(self.root, character_id)
        folder = char_dir / "creator-input"
        path = folder / "brief-r1.md"
        if not folder.exists() and not folder.is_symlink():
            return None
        if folder.is_symlink():
            raise ValueError("creator-input가 심볼릭 링크라 브리프를 읽을 수 없다")
        if not path.exists() and not path.is_symlink():
            return None
        if path.is_symlink():
            raise ValueError("brief-r1.md가 심볼릭 링크라 브리프를 읽을 수 없다")
        resolved = path.resolve()
        if not resolved.is_relative_to(char_dir.resolve()):
            raise ValueError("brief-r1.md가 캐릭터 폴더 밖을 가리킨다")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ValueError("brief-r1.md를 읽지 못했다") from exc
        if size > MAX_CREATOR_BRIEF_CHARS * 4:
            raise ValueError(f"브리프는 {MAX_CREATOR_BRIEF_CHARS}자 이하여야 한다")
        try:
            with path.open("r", encoding="utf-8") as handle:
                brief = handle.read(MAX_CREATOR_BRIEF_CHARS + 1)
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError("brief-r1.md를 UTF-8로 읽지 못했다") from exc
        if len(brief) > MAX_CREATOR_BRIEF_CHARS:
            raise ValueError(f"브리프는 {MAX_CREATOR_BRIEF_CHARS}자 이하여야 한다")
        if not brief.strip():
            raise ValueError("브리프가 비어 있다")
        return brief

    def _stdout_router(self) -> _StdoutRouter:
        """여러 캐릭터가 동시에 돌아도 각 작업의 print가 자기 로그로만 가게 한 번만 감싼다."""
        if self._router is None:
            self._router = _StdoutRouter(sys.stdout)
            sys.stdout = self._router
        return self._router

    # ---- 기록·이벤트 ----

    def publish_state(self, character_id: str, force: bool = False) -> None:
        try:
            char_dir = reads.character_dir(self.root, character_id)
            signature = reads.state_signature(self.root, character_id)
            summary = reads.character_summary(char_dir)
        except WebError:
            return
        with self._lock:
            if not force and self._signatures.get(character_id) == signature:
                return
            self._signatures[character_id] = signature
        self.hub.publish(
            "state",
            {"type": "state", "characterId": character_id, "character": summary},
            character_id,
        )

    def _publish_job(self, job: Job) -> None:
        self.hub.publish(
            "job",
            {
                "type": "job",
                "characterId": job.character_id,
                "job": job.as_dict(include_log=False),
                "logTail": list(job.log[-8:]),
            },
            job.character_id,
        )

    def _append_log(self, job: Job, line: str) -> None:
        with self._lock:
            job.log.append(line)
            if len(job.log) > MAX_LOG_LINES:
                del job.log[: len(job.log) - MAX_LOG_LINES]
        self._publish_job(job)
        self.publish_state(job.character_id)

    def _persist(self, job: Job) -> None:
        folder = self.settings.jobs_path
        try:
            if job.trigger in VIDEO_TRIGGERS:
                from character_factory_poc.common.source_store import atomic_write, inside
                from character_factory_poc.pipeline.origin import read_video_tier

                char_dir = reads.character_dir(self.root, job.character_id)
                marker = {"tier": read_video_tier(char_dir), "status": job.status}
                if job.error:
                    marker["error"] = job.error
                atomic_write(inside(char_dir, "video-job.json"), json.dumps(marker).encode())
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{job.job_id}.json"
            tmp = path.with_suffix(".json.tmp")
            payload = json.dumps(job.as_dict(), ensure_ascii=False, indent=2) + "\n"
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:  # 저장이 안 돼도 작업은 계속한다
            print(f"작업 기록을 쓰지 못했다: {exc}", file=sys.__stdout__ or sys.stdout)

    def _lookup(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        data = reads.read_json_file(self.settings.jobs_path / f"{job_id}.json")
        if data is None:
            return None
        return Job.from_dict(data)

    def _load_history(self) -> None:
        folder = self.settings.jobs_path
        if not folder.is_dir():
            return
        paths = sorted(folder.glob("job-*.json"), key=_sort_mtime, reverse=True)
        for path in paths[:MAX_HISTORY]:
            data = reads.read_json_file(path)
            if not data:
                continue
            job = Job.from_dict(data)
            if not job.job_id:
                job.job_id = path.stem
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = "서버가 다시 시작되어 작업이 중단됐다"
                job.finished_at = job.finished_at or now_iso()
                if (
                    job.trigger in VIDEO_TRIGGERS
                    and (self.root / "runs/characters" / job.character_id).is_dir()
                ):
                    self._persist(job)
            self._jobs.setdefault(job.job_id, job)


class _JobStream:
    """작업 하나의 print를 작업 로그로 옮긴다. 터미널 출력은 _StdoutRouter가 맡는다."""

    def __init__(self, manager: JobManager, job: Job):
        self._manager = manager
        self._job = job
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            self._buffer += text
            lines = self._buffer.split("\n")
            self._buffer = lines.pop()
        self._emit(lines)
        return len(text)

    def flush_lines(self) -> None:
        """작업이 끝났을 때 남은 부분 줄을 로그에 넣는다."""
        with self._lock:
            rest = self._buffer
            self._buffer = ""
        self._emit([rest])

    def _emit(self, lines: list[str]) -> None:
        for line in lines:
            clean = line.rstrip("\r")
            if clean.strip():
                self._manager._append_log(self._job, clean)


class _StdoutRouter(io.TextIOBase):
    """sys.stdout을 한 번 감싸, 작업 스레드의 출력만 그 작업 로그로 복사한다."""

    def __init__(self, origin):
        self._origin = origin
        self._sinks: dict[int, _JobStream] = {}
        self._lock = threading.Lock()

    def register(self, sink: _JobStream) -> None:
        with self._lock:
            self._sinks[threading.get_ident()] = sink

    def unregister(self) -> None:
        with self._lock:
            self._sinks.pop(threading.get_ident(), None)

    def write(self, text: str) -> int:
        try:
            self._origin.write(text)
        except (OSError, ValueError, AttributeError):
            pass
        with self._lock:
            sink = self._sinks.get(threading.get_ident())
        if sink is not None:
            sink.write(text)
        return len(text)

    def flush(self) -> None:
        try:
            self._origin.flush()
        except (OSError, ValueError, AttributeError):
            pass

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False
