"""워크숍 화면의 대기열·실행 확인 값 (LLD §6.7·§6.10, FR-47, D-0049).

GET /api/characters/{id}가 대기 관문을 대기열 순서(queue)로 싣는지, 마지막 작업이 확인을 기다린
유료 단계를 held: [{stage, providers}]로 싣는지 본다. 가짜 설정만 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from character_factory_poc.web import create_app

CID = "cf-20261028-queue"

FACTORY_TOML = """
[providers.text]
adapter = "fake"

[providers.judge]
adapter = "fake"

[providers.image]
adapter = "fake"

[providers.video]
adapter = "xai_video"
model = "grok-video"
paid = true

[web]
jobs_dir = "work/web-jobs"
"""


def write_char(tmp_path: Path, state: dict, events: list[dict] | None = None) -> Path:
    root = tmp_path / "factory"
    root.mkdir()
    (root / "factory.toml").write_text(FACTORY_TOML, encoding="utf-8")
    char = root / "runs" / "characters" / CID
    char.mkdir(parents=True)
    (char / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    if events:
        ledger = char / "ledger"
        ledger.mkdir()
        rows = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in events)
        (ledger / "gate-events.jsonl").write_text(rows, encoding="utf-8")
    return root


def test_character_detail_carries_the_gate_queue_in_order(tmp_path: Path) -> None:
    root = write_char(
        tmp_path,
        {
            "schemaVersion": "state-v1",
            "subjectId": CID,
            "stages": {"s5": {"status": "AWAITING_HUMAN", "currentRev": "vi1"}},
            "gates": {
                "G5": {"status": "AWAITING_HUMAN", "rev": "vi1", "recordRef": None},
                "G8": {"status": "AWAITING_HUMAN", "rev": "ev1", "recordRef": None},
            },
        },
        events=[
            {"at": "2026-10-28T01:00:00+00:00", "gate": "G5", "rev": "vi1", "event": "opened"},
            {"at": "2026-10-28T00:00:00+00:00", "gate": "G8", "rev": "ev1", "event": "opened"},
        ],
    )
    with TestClient(create_app(root)) as client:
        detail = client.get(f"/api/characters/{CID}").json()
        projects = client.get("/api/projects").json()

    # G5·G8은 뒤쪽 단계가 둘씩이라, 먼저 열린 G8이 앞선다(GATES 순서와 반대).
    assert [item["gate"] for item in detail["queue"]] == ["G8", "G5"]
    assert [item["gate"] for item in projects["characters"][0]["queue"]] == ["G8", "G5"]
    first = detail["queue"][0]
    assert first["stage"] == "s10"
    assert first["rev"] == "ev1"
    assert first["unblocks"] == 2
    assert first["unblockedStages"] == ["s11", "sx"]
    assert first["openedAt"] == "2026-10-28T00:00:00+00:00"
    # 두 목록 모두 같은 값이다.
    assert projects["characters"][0]["queue"] == detail["queue"]


def test_held_stages_come_with_the_paid_providers(tmp_path: Path) -> None:
    root = write_char(
        tmp_path,
        {
            "schemaVersion": "state-v1",
            "subjectId": CID,
            "stages": {"s5": {"status": "PENDING"}},
            "gates": {},
        },
    )
    jobs = root / "work" / "web-jobs"
    jobs.mkdir(parents=True)
    (jobs / "job-held1.json").write_text(
        json.dumps(
            {
                "jobId": "job-held1",
                "characterId": CID,
                "action": "run",
                "until": "G5",
                "status": "failed",
                "createdAt": "2026-10-28T00:00:00+00:00",
                "held": ["s5"],
                "trigger": "gate",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with TestClient(create_app(root)) as client:
        detail = client.get(f"/api/characters/{CID}").json()
        listed = client.get("/api/projects").json()["characters"]
    assert detail["held"] == [{"stage": "s5", "providers": ["video: xai_video/grok-video"]}]
    # 목록도 같은 기준으로 싣는다(개요·받은 일이 모든 캐릭터의 유료 확인을 센다).
    assert next(c for c in listed if c["id"] == CID)["held"] == detail["held"]

    # 실행을 확인하면 같은 단계가 held에서 빠진다(끝난 단계는 싣지 않는다).
    char = root / "runs" / "characters" / CID
    state = json.loads((char / "state.json").read_text(encoding="utf-8"))
    state["stages"]["s5"] = {"status": "AWAITING_HUMAN", "currentRev": "vi1"}
    (char / "state.json").write_text(json.dumps(state), encoding="utf-8")
    with TestClient(create_app(root)) as client:
        assert client.get(f"/api/characters/{CID}").json()["held"] == []
