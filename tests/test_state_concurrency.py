"""상태 파일 동시 쓰기와 관문 사건 기록 (D-0049, LLD §6.6)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from character_factory_poc.pipeline.state import StateFile, gate_events_path


def _cycle(path: Path, sid: str, n: int, errors: list) -> None:
    try:
        for i in range(n):
            st = StateFile(path, "c1")
            st.transition(sid, "RUNNING", rev=f"r{i}")
            st.transition(sid, "AWAITING_HUMAN", rev=f"r{i}")
            st.transition(sid, "APPROVED", rev=f"r{i}")
    except Exception as e:  # pragma: no cover - 실패 내용을 시험이 본다
        errors.append(e)


def test_two_threads_do_not_lose_each_others_transitions(tmp_path: Path) -> None:
    path = tmp_path / "c1" / "state.json"
    errors: list = []
    threads = [
        threading.Thread(target=_cycle, args=(path, sid, 100, errors)) for sid in ("s3", "s5")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    final = StateFile(path, "c1")
    for sid in ("s3", "s5"):
        st = final.stage(sid)
        assert st.status == "APPROVED"
        assert st.currentRev == "r99"
        assert st.attempts == 100


def test_stale_instance_keeps_other_writers_changes(tmp_path: Path) -> None:
    path = tmp_path / "c1" / "state.json"
    a = StateFile(path, "c1")
    b = StateFile(path, "c1")  # a가 쓰기 전에 읽은 낡은 사본
    a.transition("s3", "RUNNING", rev="pr1")
    b.set_gate("G5", "AWAITING_HUMAN", "iv1", None)
    fresh = StateFile(path, "c1")
    assert fresh.stage("s3").status == "RUNNING"
    assert fresh.gate("G5").status == "AWAITING_HUMAN"


def test_gate_events_record_open_and_decide_once(tmp_path: Path) -> None:
    path = tmp_path / "c1" / "state.json"
    st = StateFile(path, "c1")
    st.set_gate("G3", "AWAITING_HUMAN", "pr1", None)
    st.set_gate("G3", "AWAITING_HUMAN", "pr1", None)  # 같은 rev로 다시 열어도 한 번만
    st.set_gate("G3", "APPROVED", "pr1", "gates/G3-pr1.json")
    st.set_gate("G3", "AWAITING_HUMAN", "pr2", None)
    lines = gate_events_path(tmp_path / "c1").read_text("utf-8").splitlines()
    events = [(e["gate"], e["rev"], e["event"]) for e in map(json.loads, lines)]
    assert events == [
        ("G3", "pr1", "opened"),
        ("G3", "pr1", "decided"),
        ("G3", "pr2", "opened"),
    ]
