"""워크숍 관문 상세 화면 API 테스트 (K-0037, LLD §6.5).

합성 흐름과 가짜 공급자만 쓴다. 네트워크도 실제 공급자도 부르지 않는다. 관문 결정은 기존
`pipeline.approve.approve_gate` 경로를 그대로 지나는지(기록 파일·상태 전이)를 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.web import create_app, gate_fixtures, reads
from tests.support.web_gates import answer_for, build

GATE_CASES = [
    ("G1", "faces", "G1"),
    ("G3", "planVariants", "G3"),
    ("G4a", "backgrounds", "G4a"),
    ("G4b", "poses", "G4b"),
    ("G4", "frames", "G4"),
    ("G5", "intro", "G5"),
    ("G5b", "actions", "G5b"),
    ("G6", "prompts", "G6"),
]

LATE_GATES = [
    ("G7a", "samples"),
    ("G7", "dataset"),
    ("G8", "eval"),
    ("G9", "package"),
]


def _client(root: Path) -> TestClient:
    return TestClient(create_app(root))


def _view(client: TestClient, cid: str, gate: str) -> dict:
    res = client.get(f"/api/characters/{cid}/gates/{gate}")
    assert res.status_code == 200, res.text
    return res.json()


def _state(root: Path, cid: str) -> dict:
    path = root / "runs" / "characters" / cid / "state.json"
    return json.loads(path.read_text("utf-8"))


def test_stage_dirs_and_lane_names_follow_lld():
    assert reads.STAGE_DIRS["s9s"] == "s9-data"
    assert reads.STAGE_DIRS["s9"] == "s9-data"
    assert reads.STAGE_DIRS["s10t"] == "s10-train"
    assert reads.STAGE_DIRS["s10"] == "s10-eval"
    assert reads.STAGE_DIRS["s11"] == "s11-release"
    assert reads.STAGE_DIRS["sx"] == "sx-export"
    assert reads.known_gates() == [
        "G1",
        "G3",
        "G4a",
        "G4b",
        "G4",
        "G5",
        "G5b",
        "G6",
        "G7a",
        "G7",
        "G8",
        "G9",
    ]
    assert [lane["label"] for lane in reads.LANES] == [
        "외모",
        "기획",
        "장면",
        "영상",
        "페르소나",
        "데이터",
        "학습",
        "패키지",
    ]


@pytest.mark.parametrize("gate,kind,until", GATE_CASES)
def test_gate_view_returns_screen_items(tmp_path, gate, kind, until):
    _ctx, cid = build(tmp_path, until)
    with _client(tmp_path) as client:
        view = _view(client, cid, gate)
    assert view["gate"] == gate
    assert view["kind"] == kind
    assert view["items"]["kind"] == kind
    assert view["connected"] is True
    assert view["synthetic"] is False
    assert view["status"] == "AWAITING_HUMAN"
    assert view["missing"] == []
    assert view["rev"]
    assert view["decisions"]
    assert view["stageDir"].startswith(f"runs/characters/{cid}/")


def test_g1_view_lists_cluster_faces_with_recommendation(tmp_path):
    _ctx, cid = build(tmp_path, "G1")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G1")
        items = view["items"]
        assert items["recommended"]
        clusters = items["clusters"]
        assert clusters and clusters[0]["faces"]
        face = clusters[0]["faces"][0]
        assert face["previewId"] and face["file"]["url"].startswith("/api/files/")
        assert clusters[0]["tags"]
        image = client.get(face["file"]["url"])
        assert image.status_code == 200
        assert clusters[0]["members"]


def test_g3_view_has_three_variants_and_edit_fields(tmp_path):
    _ctx, cid = build(tmp_path, "G3")
    with _client(tmp_path) as client:
        items = _view(client, cid, "G3")["items"]
    assert items["mode"] == "variants"
    assert [c["variantId"] for c in items["candidates"]] == ["v1", "v2", "v3"]
    assert "tagline" in items["editableFields"]
    assert items["candidates"][0]["choices"]
    assert items["axisNote"]


def test_g3_own_revision_is_listed_as_candidate(tmp_path):
    _ctx, cid = build(tmp_path, "G3", own=True)
    with _client(tmp_path) as client:
        view = _view(client, cid, "G3")
    items = view["items"]
    assert items["mode"] == "own"
    assert [c["variantId"] for c in items["candidates"]] == ["u1"]
    assert items["candidates"][0]["name"] == "윤하린"


@pytest.mark.parametrize(
    "gate,until,check",
    [
        ("G4a", "G4a", "backgrounds"),
        ("G4b", "G4b", "poses"),
        ("G4", "G4", "frames"),
        ("G5", "G5", "intro"),
        ("G5b", "G5b", "actions"),
    ],
)
def test_scene_and_video_views_offer_choices(tmp_path, gate, until, check):
    _ctx, cid = build(tmp_path, until)
    with _client(tmp_path) as client:
        items = _view(client, cid, gate)["items"]
    if check == "backgrounds":
        assert [c["chapterId"] for c in items["chapters"]] == ["ch1", "ch2", "ch3"]
        assert len(items["chapters"][0]["candidates"]) == 3
        assert items["chapters"][0]["candidates"][0]["plate"]["url"]
    if check == "poses":
        assert items["poseFields"][0] == "body"
        assert items["chapters"][0]["candidates"][0]["poseId"] == "ch1-p1"
        assert items["chapters"][0]["sceneFacts"]
    if check == "frames":
        assert [f["chapterId"] for f in items["frames"]] == ["ch1", "ch2", "ch3"]
        assert items["frames"][0]["file"]["url"].endswith("png")
        assert items["referenceImage"]["url"]
    if check == "intro":
        assert [c["candidateId"] for c in items["candidates"]] == ["v1", "v2"]
        assert items["candidates"][0]["file"]["url"].endswith(".mp4")
        assert items["firstFrame"]["url"] and items["prompt"]
    if check == "actions":
        assert items["chapters"] and items["chapters"][0]["actions"]
        action = items["chapters"][0]["actions"][0]
        assert action["actionId"].startswith("ch1-")
        assert action["candidates"][0]["file"]["url"].endswith(".mp4")


def test_g6_view_has_long_short_prompts_and_probes(tmp_path):
    _ctx, cid = build(tmp_path, "G6")
    with _client(tmp_path) as client:
        items = _view(client, cid, "G6")["items"]
    assert items["long"]["chars"] > items["short"]["chars"]
    assert len(items["probes"]) == 2
    assert items["probes"][0]["longResponse"] and items["probes"][0]["shortResponse"]
    assert items["traitSheet"]["url"].endswith("trait-sheet.json")


@pytest.mark.parametrize("gate,until", [(gate, until) for gate, _k, until in GATE_CASES])
def test_decision_posts_through_approve_path(tmp_path, gate, until):
    _ctx, cid = build(tmp_path, until)
    with _client(tmp_path) as client:
        view = _view(client, cid, gate)
        answer = answer_for(gate, view["items"])
        res = client.post(f"/api/characters/{cid}/gates/{gate}/decision", json=answer)
        assert res.status_code == 200, res.text
        data = res.json()
        rev = view["rev"]
        assert data["recordRef"] == f"gates/{gate}-{rev}.json"
        assert data["state"]["gates"][gate]["status"] == "APPROVED"
        assert data["character"]["gates"]
        record = json.loads(
            (tmp_path / "runs" / "characters" / cid / f"gates/{gate}-{rev}.json").read_text("utf-8")
        )
        assert record["schemaVersion"] == "gate-record-v1"
        assert record["decision"] in {data["decision"], answer["decision"]}
        assert record["reviewer"] == "tester"
        assert record["decidedAt"]
        again = client.post(f"/api/characters/{cid}/gates/{gate}/decision", json=answer)
        assert again.status_code == 409


def test_g1_select_keeps_one_face_and_opens_s2(tmp_path):
    _ctx, cid = build(tmp_path, "G1")
    with _client(tmp_path) as client:
        items = _view(client, cid, "G1")["items"]
        answer = answer_for("G1", items)
        res = client.post(f"/api/characters/{cid}/gates/G1/decision", json=answer)
        assert res.status_code == 200, res.text
        record = res.json()["record"]
        assert record["selections"][1] == answer["referencePreviews"][0]
        assert res.json()["state"]["stages"]["s1"]["status"] == "APPROVED"
        assert res.json()["state"]["stages"]["s2"]["status"] == "PENDING"


def test_g3_select_with_edits_writes_plan(tmp_path):
    _ctx, cid = build(tmp_path, "G3")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G3")
        answer = answer_for("G3", view["items"])
        res = client.post(f"/api/characters/{cid}/gates/G3/decision", json=answer)
        assert res.status_code == 200, res.text
    plan = json.loads(
        (tmp_path / "runs" / "characters" / cid / "s3-plan" / view["rev"] / "plan.json").read_text(
            "utf-8"
        )
    )
    assert plan["variantId"] == "v2"
    assert plan["tagline"] == "고른 책은 끝까지 읽는다"
    selection = json.loads(
        (
            tmp_path / "runs" / "characters" / cid / "s3-plan" / view["rev"] / "selection.json"
        ).read_text("utf-8")
    )
    assert selection["editedFields"] == ["tagline"]


def test_g4_request_changes_records_chapter_notes(tmp_path):
    _ctx, cid = build(tmp_path, "G4")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G4")
        answer = {
            "decision": "REQUEST_CHANGES",
            "requestedChanges": [{"field": "ch2", "note": "손을 무릎 위로 내려 주세요"}],
            "reviewer": "tester",
        }
        res = client.post(f"/api/characters/{cid}/gates/G4/decision", json=answer)
        assert res.status_code == 200, res.text
        record = res.json()["record"]
        assert record["decision"] == "REQUEST_CHANGES"
        assert record["requestedChanges"] == [
            {"field": "ch2", "note": "손을 무릎 위로 내려 주세요"}
        ]
        assert res.json()["state"]["gates"]["G4"]["status"] == "REJECTED"
        assert view["rev"]


def test_g5_select_writes_approved_intro(tmp_path):
    _ctx, cid = build(tmp_path, "G5")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G5")
        answer = answer_for("G5", view["items"])
        res = client.post(f"/api/characters/{cid}/gates/G5/decision", json=answer)
        assert res.status_code == 200, res.text
    approved = json.loads(
        (
            tmp_path
            / "runs"
            / "characters"
            / cid
            / "s5-intro"
            / view["rev"]
            / "approved-intro.json"
        ).read_text("utf-8")
    )
    assert approved["video"]["id"] == answer["selections"][0]


def test_g5b_select_writes_approved_actions(tmp_path):
    _ctx, cid = build(tmp_path, "G5b")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G5b")
        answer = answer_for("G5b", view["items"])
        res = client.post(f"/api/characters/{cid}/gates/G5b/decision", json=answer)
        assert res.status_code == 200, res.text
    approved = json.loads(
        (
            tmp_path
            / "runs"
            / "characters"
            / cid
            / "s6-actions"
            / view["rev"]
            / "approved-actions.json"
        ).read_text("utf-8")
    )
    assert {c["chapterId"] for c in approved["clips"]} == {"ch1", "ch2", "ch3"}
    assert len(approved["clips"]) == len(answer["picks"])


def test_g6_approve_issues_persona_version(tmp_path):
    _ctx, cid = build(tmp_path, "G6")
    with _client(tmp_path) as client:
        view = _view(client, cid, "G6")
        res = client.post(
            f"/api/characters/{cid}/gates/G6/decision",
            json=answer_for("G6", view["items"]),
        )
        assert res.status_code == 200, res.text
    pair = json.loads(
        (
            tmp_path
            / "runs"
            / "characters"
            / cid
            / "s8-prompts"
            / view["rev"]
            / "persona-version.json"
        ).read_text("utf-8")
    )
    assert pair["personaVersion"] == view["rev"]
    assert _state(tmp_path, cid)["stages"]["s8"]["status"] == "APPROVED"


@pytest.mark.parametrize("gate,kind", LATE_GATES)
def test_late_gates_are_connected_and_wait_for_their_stage(tmp_path, gate, kind):
    """G7a~G9는 H 갈래에서 연결됐다. 단계가 돌기 전에는 revision이 없다고 알리고 결정을 거절한다."""
    _ctx, cid = build(tmp_path, "G1")
    with _client(tmp_path) as client:
        view = _view(client, cid, gate)
        assert view["connected"] is True
        assert view["kind"] == kind
        assert view["items"]["source"] == "artifacts"
        assert view["items"]["problems"]
        res = client.post(
            f"/api/characters/{cid}/gates/{gate}/decision",
            json={"decision": view["decisions"][0], "reviewer": "tester"},
        )
        assert res.status_code in (400, 409), res.text


def test_g7a_fixture_has_clusters_and_samples():
    items = gate_fixtures.fixture_for("G7a", "cf-x")
    assert [c["clusterId"] for c in items["clusters"]] == [
        "base",
        "situation",
        "history",
        "ownership",
        "conflict",
    ]
    handoff = items["clusters"][0]["handoff"]
    assert handoff["schemaVersion"] == "data-handoff-v1"
    assert handoff["behaviorTable"][0]["situation"]
    sample = items["clusters"][0]["samples"][0]
    assert sample["messages"][0]["role"] == "user"
    assert items["plan"]["targetTrainConversations"] == 640


def test_g7_fixture_has_twenty_samples():
    items = gate_fixtures.fixture_for("G7", "cf-x")
    assert len(items["samples"]) == 20
    assert items["dataset"]["schemaVersion"] == "dataset-rev-v2"
    assert items["dataset"]["blockingFailures"] == 0


def test_g8_fixture_blind_pairs_hide_condition_names():
    items = gate_fixtures.fixture_for("G8", "cf-x")
    pairs = items["pairs"]
    assert len(pairs) == 20
    for pair in pairs:
        assert set(pair) == {"pairId", "prompt", "a", "b"}
    text = json.dumps(pairs, ensure_ascii=False)
    for arm in ("LONG_BASE", "SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT"):
        assert arm not in text
    assert items["report"]["metrics"]


def test_g9_fixture_summarises_package():
    items = gate_fixtures.fixture_for("G9", "cf-x")
    package = items["package"]
    assert package["schemaVersion"] == "character-package-v1"
    assert len(package["chapters"]) == 3
    assert items["verification"]["disposableDb"] is True


def test_gate_screen_static_files_are_served(tmp_path):
    _ctx, cid = build(tmp_path, "G1")
    with _client(tmp_path) as client:
        page = client.get("/gate.html")
        assert page.status_code == 200
        assert "shared/gate.js" in page.text
        script = client.get("/shared/gate.js")
        assert script.status_code == 200
        assert "data-decide" in script.text
        style = client.get("/shared/gate.css")
        assert style.status_code == 200
        workroom = client.get("/c-glass.html")
        assert "shared/live.js" in workroom.text


def test_projects_expose_lanes_and_job_queue(tmp_path):
    _ctx, cid = build(tmp_path, "G3")
    with _client(tmp_path) as client:
        data = client.get("/api/projects").json()
    character = next(c for c in data["characters"] if c["id"] == cid)
    lanes = {lane["id"]: lane for lane in character["lanes"]}
    assert set(lanes) == {
        "appearance",
        "plan",
        "scene",
        "video",
        "persona",
        "data",
        "training",
        "release",
    }
    assert lanes["appearance"]["done"] == 2
    assert lanes["appearance"]["percent"] == 100
    assert lanes["plan"]["pendingGates"] == ["G3"]
    assert lanes["data"]["implemented"] is True
    assert "jobs" in data
    assert data["totals"]["runningJobs"] == 0


def test_unknown_gate_and_missing_revision_are_reported(tmp_path):
    _ctx, cid = build(tmp_path, "G1")
    with _client(tmp_path) as client:
        assert client.get(f"/api/characters/{cid}/gates/G2").status_code == 404
        assert (
            client.post(
                f"/api/characters/{cid}/gates/G2/decision",
                json={"decision": "APPROVE", "reviewer": "t"},
            ).status_code
            == 404
        )
        view = _view(client, cid, "G6")
    assert view["connected"] is True
    assert view["status"] == "PENDING"
    assert view["missing"]
    assert view["items"]["problems"]
