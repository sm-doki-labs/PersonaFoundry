"""대기열 정렬 (LLD §6.10, 명세 §7.4, FR-47, D-0049).

그래프와 state 파일, 관문 사건 기록만으로 정렬이 결정되는지 본다. 네트워크·LLM을 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.contracts.common import State
from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.pipeline.queue import downstream_stages, gate_queue

CID = "cf-20261028-queue"


def write_char(
    tmp_path: Path,
    gates: dict[str, dict],
    stages: dict[str, dict] | None = None,
    events: list[dict] | None = None,
) -> Path:
    char = tmp_path / "runs" / "characters" / CID
    char.mkdir(parents=True)
    state = {
        "schemaVersion": "state-v1",
        "subjectId": CID,
        "stages": stages or {},
        "gates": gates,
    }
    (char / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if events:
        ledger = char / "ledger"
        ledger.mkdir()
        rows = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in events)
        (ledger / "gate-events.jsonl").write_text(rows, encoding="utf-8")
    return char


def gate(status: str, rev: str) -> dict:
    return {"status": status, "rev": rev, "recordRef": None}


def opened(gate_id: str, rev: str, at: str) -> dict:
    return {"at": at, "gate": gate_id, "rev": rev, "event": "opened", "status": "AWAITING_HUMAN"}


def test_downstream_stages_follows_gate_to_gate() -> None:
    g3 = downstream_stages("G3")
    for sid in ("s4a", "s7", "s8", "s9s", "s11", "sx"):
        assert sid in g3, sid
    # 그 관문이 결정하는 단계 자체(s3)는 풀어 주는 뒤쪽 단계가 아니다.
    assert "s3" not in g3
    # STAGES 순서를 지킨다.
    assert g3 == [sid for sid in STAGES if sid in set(g3)]
    # 소개 영상 관문은 패키지와 내보내기만 연다.
    assert downstream_stages("G5") == ["s11", "sx"]


def test_g3_waits_before_g5_because_it_unblocks_more(tmp_path: Path) -> None:
    char = write_char(
        tmp_path,
        gates={"G3": gate("AWAITING_HUMAN", "pr1"), "G5": gate("AWAITING_HUMAN", "vi1")},
        events=[
            # G5가 먼저 열렸어도 뒤쪽 단계가 많은 G3가 앞선다.
            opened("G5", "vi1", "2026-10-28T00:00:00+00:00"),
            opened("G3", "pr1", "2026-10-28T00:30:00+00:00"),
        ],
    )
    queue = gate_queue(char, json.loads((char / "state.json").read_text("utf-8")))
    assert [item.gate for item in queue] == ["G3", "G5"]
    assert queue[0].unblocks > queue[1].unblocks
    assert queue[0].unblocks == len(queue[0].unblockedStages)
    assert queue[0].rev == "pr1" and queue[0].stage == "s3"
    assert queue[0].openedAt == "2026-10-28T00:30:00+00:00"
    assert queue[1].openedAt == "2026-10-28T00:00:00+00:00"
    assert queue[1].unblockedStages == ["s11", "sx"]


def test_same_count_uses_the_gate_opened_earlier(tmp_path: Path) -> None:
    # G5와 G8은 뒤쪽 단계가 둘씩이라 같은 수다.
    char = write_char(
        tmp_path,
        gates={"G5": gate("AWAITING_HUMAN", "vi1"), "G8": gate("AWAITING_HUMAN", "ev1")},
        events=[
            opened("G5", "vi1", "2026-10-28T02:00:00+00:00"),
            opened("G8", "ev1", "2026-10-28T01:00:00+00:00"),
        ],
    )
    state = State.model_validate(json.loads((char / "state.json").read_text("utf-8")))
    queue = gate_queue(char, state)
    assert [item.gate for item in queue] == ["G8", "G5"]
    assert [item.unblocks for item in queue] == [2, 2]


def test_same_count_and_same_time_uses_gate_order(tmp_path: Path) -> None:
    at = "2026-10-28T01:00:00+00:00"
    char = write_char(
        tmp_path,
        gates={"G5": gate("AWAITING_HUMAN", "vi1"), "G8": gate("AWAITING_HUMAN", "ev1")},
        events=[opened("G5", "vi1", at), opened("G8", "ev1", at)],
    )
    queue = gate_queue(char, json.loads((char / "state.json").read_text("utf-8")))
    assert [item.gate for item in queue] == ["G5", "G8"]


def test_opened_at_falls_back_to_the_stage_updated_at(tmp_path: Path) -> None:
    char = write_char(
        tmp_path,
        gates={"G5": gate("AWAITING_HUMAN", "vi1"), "G8": gate("AWAITING_HUMAN", "ev1")},
        stages={
            "s10": {
                "status": "AWAITING_HUMAN",
                "currentRev": "ev1",
                "updatedAt": "2026-10-28T05:00:00+00:00",
            },
            "s5": {
                "status": "AWAITING_HUMAN",
                "currentRev": "vi1",
                "updatedAt": "2026-10-28T04:00:00+00:00",
            },
        },
    )
    queue = gate_queue(char, json.loads((char / "state.json").read_text("utf-8")))
    assert [item.gate for item in queue] == ["G5", "G8"]  # 사건 없이 단계 시각 비교
    assert queue[0].openedAt == "2026-10-28T04:00:00+00:00"


def test_only_awaiting_gates_are_queued_and_done_stages_do_not_count(tmp_path: Path) -> None:
    char = write_char(
        tmp_path,
        gates={
            "G3": gate("AWAITING_HUMAN", "pr1"),
            "G5": gate("APPROVED", "vi1"),
            "G8": gate("AWAITING_HUMAN", "ev1"),
        },
        stages={
            "s3r": {"status": "SKIPPED", "currentRev": "rf1"},
            "s4a": {"status": "APPROVED", "currentRev": "bg1"},
            "s7": {"status": "PENDING"},
        },
    )
    queue = gate_queue(char, json.loads((char / "state.json").read_text("utf-8")))
    assert [item.gate for item in queue] == ["G3", "G8"]
    g3 = queue[0]
    for sid in ("s3r", "s4a"):
        assert sid not in g3.unblockedStages  # 이미 끝난 단계는 세지 않는다
    assert "s7" in g3.unblockedStages
    assert g3.unblocks == len(g3.unblockedStages)


def test_empty_state_gives_an_empty_queue(tmp_path: Path) -> None:
    char = write_char(tmp_path, gates={})
    assert gate_queue(char, {}) == []
