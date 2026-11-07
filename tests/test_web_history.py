"""단계 이력·관문 대기 시각·비용 합계·유료 단계 표시 (D-0101, LLD §23).

state.json 전이가 ledger/stage-events.jsonl에 남고, 읽기 API가 그 기록으로 시작·종료 시각과
회차 이력을 돌려주는지 본다. 공급자·모델 호출은 없다.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from character_factory_poc.pipeline.state import StateFile, stage_events_path
from character_factory_poc.web import reads
from character_factory_poc.web.app import create_app

CID = "cf-20261107-history"


def _char(root: Path) -> StateFile:
    char = root / "runs" / "characters" / CID
    char.mkdir(parents=True)
    return StateFile(char / "state.json", CID)


def _events(root: Path) -> list[dict]:
    path = stage_events_path(root / "runs" / "characters" / CID)
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_every_transition_is_appended_with_attempt_and_error(tmp_path: Path) -> None:
    st = _char(tmp_path)
    st.transition("s3", "RUNNING", rev="pr1")
    st.transition("s3", "CHECK_FAILED", error="형식 검사 실패")
    st.transition("s3", "RUNNING", rev="pr1")
    st.transition("s3", "AWAITING_HUMAN", rev="pr1")

    rows = _events(tmp_path)
    assert [(r["from"], r["to"], r["attempt"]) for r in rows] == [
        ("PENDING", "RUNNING", 1),
        ("RUNNING", "CHECK_FAILED", 1),
        ("CHECK_FAILED", "RUNNING", 2),
        ("RUNNING", "AWAITING_HUMAN", 2),
    ]
    assert rows[1]["error"] == "형식 검사 실패"
    assert all(r["stage"] == "s3" and r["at"] for r in rows)


def test_timeline_splits_attempts_and_keeps_failure_reasons(tmp_path: Path) -> None:
    st = _char(tmp_path)
    st.transition("s3", "RUNNING", rev="pr1")
    st.transition("s3", "CHECK_FAILED", error="형식 검사 실패")
    st.transition("s3", "RUNNING", rev="pr1")
    st.transition("s3", "AWAITING_HUMAN", rev="pr1")
    st.set_gate("G3", "AWAITING_HUMAN", "pr1", None)
    st.transition("s3", "APPROVED", rev="pr1")
    st.set_gate("G3", "APPROVED", "pr1", "gates/G3-pr1.json")

    char_dir = tmp_path / "runs" / "characters" / CID
    s3 = reads.stage_timeline(char_dir)["s3"]
    first, second = s3["attempts"]
    assert first["result"] == "CHECK_FAILED" and first["error"] == "형식 검사 실패"
    assert second["result"] == "AWAITING_HUMAN" and second["decision"] == "APPROVED"
    assert s3["startedAt"] == second["startedAt"] and s3["endedAt"] == second["endedAt"]
    assert s3["decidedAt"]
    gate = reads.gate_timeline(char_dir)["G3"]
    assert gate["openedAt"] and gate["decidedAt"] and gate["decision"] == "APPROVED"


def test_old_characters_without_history_read_as_unknown_times(tmp_path: Path) -> None:
    _char(tmp_path).save()
    char_dir = tmp_path / "runs" / "characters" / CID
    (char_dir / "ledger").mkdir()
    (char_dir / "ledger" / "stage-events.jsonl").write_text("{깨진 줄\n", encoding="utf-8")
    summary = reads.character_summary(char_dir)
    assert all(row["startedAt"] is None for row in summary["stages"])
    assert all(row["openedAt"] is None for row in summary["gates"])


def test_detail_api_returns_times_history_waiting_gate_and_cost(tmp_path: Path) -> None:
    (tmp_path / "factory.toml").write_text("", encoding="utf-8")
    st = _char(tmp_path)
    st.transition("s3", "RUNNING", rev="pr1")
    st.transition("s3", "AWAITING_HUMAN", rev="pr1")
    st.set_gate("G3", "AWAITING_HUMAN", "pr1", None)
    ledger = tmp_path / "runs" / "characters" / CID / "ledger" / "calls.jsonl"
    rows = [
        {"stage": "s3", "kind": "text", "provider": "openai", "ok": True, "estCostUsd": 0.12},
        {
            "stage": "s3",
            "kind": "text",
            "provider": "openai",
            "ok": True,
            "estCostUsd": None,
            "billing": {"class": "api_billed"},
        },
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    with TestClient(create_app(tmp_path)) as client:
        body = client.get(f"/api/characters/{CID}").json()

    s3 = next(row for row in body["stages"] if row["id"] == "s3")
    assert s3["startedAt"] and s3["endedAt"]
    assert body["pendingGates"][0]["id"] == "G3" and body["pendingGates"][0]["openedAt"]
    assert body["history"]["s3"][0]["result"] == "AWAITING_HUMAN"
    assert body["cost"] == {"estUsd": 0.12, "calls": 2, "unpricedCalls": 1}


def test_retry_in_the_same_status_changes_the_push_signature(tmp_path: Path) -> None:
    st = _char(tmp_path)
    st.transition("s3", "RUNNING", rev="pr1")
    before = reads.state_signature(tmp_path, CID)
    st.transition("s3", "RUNNING", rev="pr1")
    assert reads.state_signature(tmp_path, CID) != before


def test_lane_shows_waiting_human_before_running_work(tmp_path: Path) -> None:
    st = _char(tmp_path)
    st.transition("s4a", "RUNNING", rev="bg1")
    st.transition("s4a", "AWAITING_HUMAN", rev="bg1")
    st.set_gate("G4a", "AWAITING_HUMAN", "bg1", None)
    st.transition("s4b", "RUNNING", rev="ps1")
    summary = reads.character_summary(tmp_path / "runs" / "characters" / CID)
    scene = next(lane for lane in summary["lanes"] if lane["id"] == "scene")
    assert scene["status"] == "gate"


def test_graph_marks_paid_stages_from_config(tmp_path: Path) -> None:
    (tmp_path / "factory.toml").write_text(
        '[providers.video]\nadapter = "xai_video"\nmodel = "grok-video"\npaid = true\n',
        encoding="utf-8",
    )
    with TestClient(create_app(tmp_path)) as client:
        stages = client.get("/api/runtime/graph").json()["stages"]
    paid = {row["id"]: row["paid"] for row in stages if row["paid"]}
    assert set(paid) == {"s5", "s6"}
    assert paid["s6"] == ["video: xai_video/grok-video"]


def test_studio_serves_the_new_factory_page(tmp_path: Path) -> None:
    studio = tmp_path / "visual"
    studio.mkdir()
    (studio / "factory.html").write_text("<main>공장</main>", encoding="utf-8")
    (tmp_path / "factory.toml").write_text(
        "[web]\nstudio_dir=" + json.dumps(str(studio)) + "\n", encoding="utf-8"
    )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/studio/factory.html").status_code == 200
