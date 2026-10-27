"""state.json 읽기·쓰기·전이 (LLD §6.2)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from character_factory_poc.common.errors import GateNotApprovedError, StateTransitionError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.contracts.common import GateState, StageState, State
from character_factory_poc.pipeline.graph import STAGES

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


class StateFile:
    def __init__(self, path: Path, subject_id: str):
        self.path = Path(path)
        if self.path.exists():
            self.state: State = validate("state-v1", json.loads(self.path.read_text("utf-8")))
        else:
            self.state = State(subjectId=subject_id)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
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
        st = self.stage(sid)
        if new not in _ALLOWED[st.status]:
            raise StateTransitionError(f"{sid}: {st.status} → {new} 전이는 허용되지 않는다")
        if new == "RUNNING":
            st.attempts += 1
        st.status = new
        if rev is not None:
            st.currentRev = rev
        st.lastError = error
        st.updatedAt = _now()
        self.save()

    def require_deps(self, sid: str) -> None:
        """의존 관문·단계가 승인됐고 선행 단계가 끝났는지 (FR-02, D-0042)."""
        s = STAGES[sid]
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
        g = self.gate(gid)
        g.status = status  # type: ignore[assignment]
        g.rev = rev
        g.recordRef = record_ref
        self.save()
