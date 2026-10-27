"""대기열 (LLD §6.10, 명세 §7.4, FR-47, D-0049).

기다리는 관문을 "뒤쪽 단계를 많이 풀어 주는 순서"로 세운다. 그래프(graph.py)와 state 파일,
관문 사건 기록만 보고 계산하는 결정적 함수이며 LLM을 쓰지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from character_factory_poc.contracts.common import State
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.state import gate_events_path

# 이 상태면 그 단계는 더 풀어 줄 것이 없다(명세 §7, LLD §6.10).
DONE_STATUSES = frozenset({"APPROVED", "SKIPPED"})


@dataclass(frozen=True)
class QueueItem:
    """대기 관문 한 줄. 화면 칩과 정렬 근거를 함께 담는다."""

    gate: str
    stage: str
    rev: str | None
    openedAt: str | None
    unblocks: int
    unblockedStages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "stage": self.stage,
            "rev": self.rev,
            "openedAt": self.openedAt,
            "unblocks": self.unblocks,
            "unblockedStages": list(self.unblockedStages),
        }


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """State 모델과 state.json에서 읽은 dict를 같은 방식으로 읽는다."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _rows(raw: Any, rev_key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        out[str(key)] = {
            "status": str(_field(value, "status", "PENDING")),
            "rev": _field(value, rev_key),
            "updatedAt": _field(value, "updatedAt"),
        }
    return out


def stage_rows(state: State | Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _rows(_field(state, "stages", {}), "currentRev")


def gate_rows(state: State | Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _rows(_field(state, "gates", {}), "rev")


def reachable_stages(gate: str) -> set[str]:
    """그 관문에서 그래프를 따라 앞으로 닿는 단계 집합.

    deps(관문 → 단계)와 needs·after(단계 → 단계)로 단계에 닿고, 닿은 단계의 gate(단계 →
    관문)로 다음 관문에 이어진 뒤 다시 deps를 본다.
    """
    stages: set[str] = set()
    gates: set[str] = {gate}
    changed = True
    while changed:
        changed = False
        for sid, stage in STAGES.items():
            if sid in stages:
                continue
            if not (stage.deps & gates or stage.needs & stages or stage.after & stages):
                continue
            stages.add(sid)
            changed = True
            if stage.gate and stage.gate not in gates:
                gates.add(stage.gate)
                changed = True
    return stages


def downstream_stages(gate: str) -> list[str]:
    """그 관문이 풀어 주는 뒤쪽 단계와 그 단계들의 관문이 여는 단계(STAGES 순서)."""
    reached = reachable_stages(gate)
    return [sid for sid in STAGES if sid in reached]


def opened_events(char_dir: Path) -> dict[tuple[str, str | None], str]:
    """관문 사건 기록의 opened 사건. (gate, rev) → 가장 이른 at(UTC ISO)."""
    path = gate_events_path(Path(char_dir))
    out: dict[tuple[str, str | None], str] = {}
    if not path.exists():
        return out
    try:
        lines = path.read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("event") != "opened":
            continue
        gate, at = row.get("gate"), row.get("at")
        if not isinstance(gate, str) or not isinstance(at, str):
            continue
        rev = row.get("rev")
        key = (gate, rev if isinstance(rev, str) else None)
        if key not in out or at < out[key]:
            out[key] = at
    return out


def _time_key(value: str | None) -> tuple[int, float]:
    """오래 기다린 순서. 시각을 읽을 수 없으면 뒤로 보낸다."""
    if not isinstance(value, str) or not value:
        return (1, 0.0)
    try:
        return (0, datetime.fromisoformat(value).timestamp())
    except ValueError:
        return (1, 0.0)


def gate_stage(gate: str) -> str:
    """그 관문이 결정하는 단계."""
    return next((sid for sid, s in STAGES.items() if s.gate == gate), "")


def gate_queue(char_dir: Path, state: State | Mapping[str, Any]) -> list[QueueItem]:
    """기다리는 관문(AWAITING_HUMAN)을 뒤쪽 단계 수 내림차순으로 세운다.

    같으면 오래 기다린 순서(openedAt 오름차순), 그다음 GATES 순서다. openedAt은
    ledger/gate-events.jsonl의 그 관문·rev opened 사건이고, 없으면 그 단계의 updatedAt이다.
    """
    char_dir = Path(char_dir)
    stages = stage_rows(state)
    gates = gate_rows(state)
    opened = opened_events(char_dir)
    order = {gate: i for i, gate in enumerate(GATES)}
    items: list[QueueItem] = []
    for gate in GATES:
        row = gates.get(gate)
        if row is None or row["status"] != "AWAITING_HUMAN":
            continue
        rev = row["rev"] if isinstance(row["rev"], str) else None
        sid = gate_stage(gate)
        left = [
            s
            for s in downstream_stages(gate)
            if stages.get(s, {}).get("status", "PENDING") not in DONE_STATUSES
        ]
        opened_at = opened.get((gate, rev))
        if opened_at is None:
            updated = stages.get(sid, {}).get("updatedAt")
            opened_at = updated if isinstance(updated, str) else None
        items.append(
            QueueItem(
                gate=gate,
                stage=sid,
                rev=rev,
                openedAt=opened_at,
                unblocks=len(left),
                unblockedStages=left,
            )
        )
    items.sort(key=lambda it: (-it.unblocks, _time_key(it.openedAt), order[it.gate]))
    return items
