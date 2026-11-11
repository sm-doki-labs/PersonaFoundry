"""state.json 읽기·쓰기·전이 (LLD §6.2, §6.6).

D-0049: 단계가 동시에 돌 수 있으므로 쓰기는 파일 잠금(state.json.lock) 아래 디스크의 최신
state.json을 다시 읽고 그 위에 변경을 적용한다. 관문이 열리고 결정된 사건은
ledger/gate-events.jsonl에 남긴다.

D-0101: 단계 상태가 바뀔 때마다 ledger/stage-events.jsonl에 한 줄을 덧붙인다. state.json은
updatedAt 하나만 덮어쓰므로 시작·종료 시각과 회차별 실패 이유는 이 기록에서 읽는다.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from character_factory_poc.common.errors import GateNotApprovedError, StateTransitionError
from character_factory_poc.common.ledger import append_jsonl
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.contracts.common import GateState, StageState, State

_ALLOWED = {
    "PENDING": {"RUNNING", "SKIPPED"},
    "RUNNING": {"CHECK_FAILED", "AWAITING_HUMAN", "RUNNING", "APPROVED"},
    "CHECK_FAILED": {"RUNNING"},
    "AWAITING_HUMAN": {"APPROVED", "REJECTED"},
    "REJECTED": {"RUNNING"},
    "APPROVED": {"RUNNING"},  # 새 revision
    "SKIPPED": {"RUNNING"},
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


GATE_EVENTS = "gate-events.jsonl"
STAGE_EVENTS = "stage-events.jsonl"


def gate_events_path(char_dir: Path) -> Path:
    """관문 사건 기록(LLD §6.6). 원장 폴더에 한 줄씩 덧붙인다."""
    return Path(char_dir) / "ledger" / GATE_EVENTS


def stage_events_path(char_dir: Path) -> Path:
    """단계 상태 전이 기록(D-0101, LLD §23). 원장 폴더에 한 줄씩 덧붙인다."""
    return Path(char_dir) / "ledger" / STAGE_EVENTS


class StateFile:
    def __init__(self, path: Path, subject_id: str):
        self.path = Path(path)
        self.state: State = self._read() or State(subjectId=subject_id)

    def _read(self) -> State | None:
        if not self.path.exists():
            return None
        return validate("state-v1", json.loads(self.path.read_text("utf-8")))  # type: ignore[return-value]

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """같은 캐릭터의 state.json을 쓰는 스레드·프로세스끼리 순서를 지킨다(D-0049)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _reload(self) -> None:
        """디스크의 최신 내용으로 바꾼다. 메모리에서 읽기만 한 칸(기본값)은 그대로 남겨 저장한다."""
        fresh = self._read()
        if fresh is None:
            return
        for sid in self.state.stages:
            fresh.stages.setdefault(sid, StageState())
        for gid in self.state.gates:
            fresh.gates.setdefault(gid, GateState())
        self.state = fresh

    def save(self) -> None:
        with self._locked():
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{id(self)}.tmp")
        tmp.write_text(
            json.dumps(dump(self.state), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def stage(self, sid: str) -> StageState:
        return self.state.stages.setdefault(sid, StageState())

    def gate(self, gid: str) -> GateState:
        return self.state.gates.setdefault(gid, GateState())

    def transition(self, sid: str, new: str, *, rev: str | None = None, error: str | None = None):
        with self._locked():
            self._reload()
            st = self.stage(sid)
            if new not in _ALLOWED[st.status]:
                raise StateTransitionError(f"{sid}: {st.status} → {new} 전이는 허용되지 않는다")
            old = st.status
            if new == "RUNNING":
                st.attempts += 1
            st.status = new
            if rev is not None:
                st.currentRev = rev
            st.lastError = error
            st.updatedAt = _now()
            self._write()
            event = {
                "at": st.updatedAt,
                "stage": sid,
                "from": old,
                "to": new,
                "rev": st.currentRev,
                "attempt": st.attempts,
                "error": error,
            }
        # 이력은 화면용 보조 기록이다. 덧붙이기가 실패해도 상태 전이는 이미 저장됐다.
        with contextlib.suppress(OSError):
            append_jsonl(stage_events_path(self.path.parent), event)

    def require_deps(self, sid: str) -> None:
        """의존 관문·단계가 승인됐고 선행 단계가 끝났는지 (FR-02, D-0042)."""
        from character_factory_poc.pipeline.origin import stage_def

        # D-0128: 모티브 캐릭터는 갈래 그래프의 의존을 본다. 오리지널은 STAGES 그대로다.
        s = stage_def(self.path.parent, sid)
        for g in sorted(s.deps):
            if self.gate(g).status != "APPROVED":
                raise GateNotApprovedError(
                    f"{sid}는 {g} 승인이 필요하다(현재 {self.gate(g).status})"
                )
        for n in sorted(s.needs):
            if self.stage(n).status != "APPROVED":
                raise GateNotApprovedError(
                    f"{sid}는 {n} 승인이 필요하다(현재 {self.stage(n).status})"
                )
        for a in sorted(s.after):
            if self.stage(a).status not in {"AWAITING_HUMAN", "APPROVED"}:
                raise GateNotApprovedError(
                    f"{sid}는 {a} 완료가 필요하다(현재 {self.stage(a).status})"
                )

    def set_gate(self, gid: str, status: str, rev: str | None, record_ref: str | None) -> None:
        with self._locked():
            self._reload()
            g = self.gate(gid)
            changed = (g.status, g.rev) != (status, rev)
            g.status = status  # type: ignore[assignment]
            g.rev = rev
            g.recordRef = record_ref
            self._write()
        if changed and status in {"AWAITING_HUMAN", "APPROVED", "REJECTED"}:
            event = "opened" if status == "AWAITING_HUMAN" else "decided"
            append_jsonl(
                gate_events_path(self.path.parent),
                {"at": _now(), "gate": gid, "rev": rev, "event": event, "status": status},
            )
