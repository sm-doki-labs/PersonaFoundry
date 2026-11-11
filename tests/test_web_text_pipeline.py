"""텍스트 공정 연결 API 테스트 (계획표 A).

가짜 작업 목록과 합성 runs 폴더만 쓴다. 설정은 실제 factory.toml/selection 파일을 읽고,
원장과 자료도 실제 임시 파일로 만든다. 네트워크·모델 호출은 하지 않는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from character_factory_poc.web.settings import load_settings
from character_factory_poc.web.text_pipeline import install_text_pipeline_routes

CID = "cf-20261030-test"
STAGE_IDS = [
    "brief",
    "personality",
    "consistency",
    "voice",
    "scenarios",
    "sft_answers",
    "screening",
    "adjudication",
    "repair",
]

TOML = """
[text_pipeline]
enabled = true
profile = "basic_test"
route = "opencodex"

[text_pipeline.routes.opencodex]
adapter = "openai_compat"
base_url = "http://127.0.0.1:10100/v1"
api_key_env = "CFP_SHOULD_NOT_LEAK"

[text_pipeline.routes.test]
adapter = "openai_compat"
base_url = ""
api_key_env = "CFP_TEST_KEY"
"""


class ActiveJobs:
    """설치 함수가 쓰는 작업 큐 표면만 흉내 낸다."""

    def __init__(self, active: list[dict] | None = None):
        self._active = list(active or [])

    def active_jobs(self) -> list[dict]:
        return list(self._active)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_root(tmp_path: Path, toml: str = TOML) -> Path:
    root = tmp_path / "factory"
    root.mkdir(parents=True)
    write(root / "factory.toml", toml)
    return root


def client_for(root: Path, jobs: ActiveJobs | None = None) -> TestClient:
    app = FastAPI()
    install_text_pipeline_routes(app, root, load_settings(root), jobs or ActiveJobs())
    return TestClient(app)


def selection(root: Path) -> dict:
    return json.loads((root / "work" / "text-pipeline-selection.json").read_text("utf-8"))


def make_character(root: Path, cid: str = CID, name: str | None = "윤하린") -> Path:
    char = root / "runs" / "characters" / cid
    state = {
        "schemaVersion": "state-v1",
        "subjectId": cid,
        "stages": {
            "s1": {"status": "APPROVED", "currentRev": "rf1"},
            "s3": {"status": "APPROVED", "currentRev": "pr1"},
            "s7": {"status": "APPROVED", "currentRev": "tr1"},
            "s8": {"status": "AWAITING_HUMAN", "currentRev": "pv1"},
            "s9s": {"status": "PENDING", "currentRev": None},
            "s9": {"status": "APPROVED", "currentRev": "dr1"},
        },
        "gates": {
            "G3": {"status": "APPROVED", "rev": "pr1", "recordRef": None},
            "G4": {"status": "PENDING", "rev": None, "recordRef": None},
            "G6": {"status": "AWAITING_HUMAN", "rev": "pv1", "recordRef": None},
            "G7a": {"status": "PENDING", "rev": None, "recordRef": None},
            "G7": {"status": "APPROVED", "rev": "dr1", "recordRef": None},
        },
    }
    write(char / "state.json", json.dumps(state, ensure_ascii=False))
    if name is not None:
        write(
            char / "s3-plan" / "pr1" / "plan.json",
            json.dumps({"name": name, "job": "책방 직원"}, ensure_ascii=False),
        )
    return char


def test_snapshot_lists_deck_profiles_routes_and_tasks(tmp_path):
    root = make_root(tmp_path)
    with client_for(root) as client:
        response = client.get("/api/text-pipeline")
        assert response.status_code == 200
        body = response.json()

    assert body["enabled"] is True
    assert body["profile"] == "basic_test"
    assert body["route"] == "opencodex"
    assert body["completionCheck"] == "NOT_RUN"
    assert body["activeJobs"] == 0
    assert [p["id"] for p in body["profiles"]] == [
        "basic_test",
        "demo",
        "pre_demo_completion_check",
    ]
    assert [p["label"] for p in body["profiles"]] == ["개발 확인", "시연", "시연 전 최종 점검"]
    routes = {r["id"]: r for r in body["routes"]}
    assert routes["opencodex"] == {
        "id": "opencodex",
        "label": "개발 연결",
        "available": True,
        "reason": "",
    }
    assert routes["test"]["available"] is False
    assert routes["test"]["reason"] == "주소·인증 설정이 필요합니다"
    assert [t["id"] for t in body["tasks"]] == STAGE_IDS
    tasks = {t["id"]: t for t in body["tasks"]}
    assert tasks["brief"]["model"] == "gpt-6.1-sol"
    assert tasks["brief"]["reasoningEffort"] == "high"
    assert tasks["voice"]["model"] == "google-antigravity/gemini-3.8-flash"
    assert tasks["scenarios"]["reasoningEffort"] == "medium"
    dumped = json.dumps(body)
    assert "CFP_SHOULD_NOT_LEAK" not in dumped
    assert "CFP_TEST_KEY" not in dumped
    assert "10100" not in dumped


def test_selection_switches_profile_and_route_with_real_config_files(tmp_path):
    root = make_root(tmp_path)
    with client_for(root) as client:
        chosen = client.post("/api/text-pipeline/selection", json={"profile": "demo"})
        assert chosen.status_code == 200
        assert chosen.json()["profile"] == "demo"
        voice = next(t for t in chosen.json()["tasks"] if t["id"] == "voice")
        assert voice["model"] == "google-antigravity/gemini-4-argon"
        assert selection(root) == {"profile": "demo", "route": "opencodex"}

        # 미설정 test 경로·모르는 값은 400이고, 실패 전 선택을 보존한다.
        for bad in ({"route": "test"}, {"profile": "nope"}, {"profile": "demo", "extra": 1}, {}):
            assert client.post("/api/text-pipeline/selection", json=bad).status_code == 400
        assert selection(root) == {"profile": "demo", "route": "opencodex"}
        assert client.get("/api/text-pipeline").json()["profile"] == "demo"

        # test 경로를 실제로 채우고 모델 매핑이 선택 결과에 반영되는지 확인한다.
        test_toml = (
            TOML.replace('base_url = ""', 'base_url = "https://test.example/v1"')
            + """
[text_pipeline.routes.test.models]
"google-antigravity/gemini-3.8-flash" = "server-flash-id"
"""
        )
        write(root / "factory.toml", test_toml)
        switched = client.post(
            "/api/text-pipeline/selection", json={"profile": "basic_test", "route": "test"}
        )
        assert switched.status_code == 200
        body = switched.json()
        assert body["profile"] == "basic_test"
        assert body["route"] == "test"
        assert {r["id"]: r["available"] for r in body["routes"]}["test"] is True
        assert next(t for t in body["tasks"] if t["id"] == "voice")["model"] == "server-flash-id"
        assert selection(root) == {"profile": "basic_test", "route": "test"}


def test_selection_is_denied_while_jobs_are_active(tmp_path):
    root = make_root(tmp_path)
    with client_for(root, ActiveJobs([{"jobId": "job-1"}])) as client:
        response = client.post("/api/text-pipeline/selection", json={"profile": "demo"})
        assert response.status_code == 409
        assert client.get("/api/text-pipeline").json()["activeJobs"] == 1
    assert not (root / "work" / "text-pipeline-selection.json").exists()


def test_disabled_pipeline_keeps_shape_and_rejects_selection(tmp_path):
    root = make_root(tmp_path, "[text_pipeline]\nenabled = false\n")
    with client_for(root) as client:
        body = client.get("/api/text-pipeline").json()
        assert body["enabled"] is False
        assert body["profile"] is None and body["route"] is None
        assert body["tasks"] == []
        assert body["completionCheck"] == "NOT_RUN"
        denied = client.post("/api/text-pipeline/selection", json={"profile": "demo"})
        assert denied.status_code == 400


def test_broken_settings_are_explicit_http_errors(tmp_path):
    root = make_root(tmp_path)
    write(root / "work" / "text-pipeline-selection.json", "{깨진 JSON")
    with client_for(root) as client:
        response = client.get("/api/text-pipeline")
        assert response.status_code == 503
        assert "설정" in response.json()["detail"]

    other = make_root(tmp_path / "other")
    write(other / "factory.toml", TOML.replace('profile = "basic_test"', 'profile = "missing"'))
    with client_for(other) as client:
        assert client.get("/api/text-pipeline").status_code == 503


def test_characters_lists_only_safe_character_folders(tmp_path):
    root = make_root(tmp_path)
    make_character(root, "cf-ok", "윤하린")
    make_character(root, "cf-noname", None)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "runs" / "characters" / "cf-link")
    (root / "runs" / "characters" / "bad id").mkdir()

    with client_for(root) as client:
        response = client.get("/api/text-pipeline/characters")
        assert response.status_code == 200
        rows = {c["id"]: c["name"] for c in response.json()["characters"]}
    assert rows == {"cf-noname": "cf-noname", "cf-ok": "윤하린"}


def test_character_detail_reads_known_artifacts_and_recent_calls(tmp_path):
    root = make_root(tmp_path)
    char = make_character(root)
    write(char / "s7-traits" / "tr1" / "trait-sheet.json", '{"card": "특질"}')
    write(
        char / "s7-traits" / "tr1" / "text-deck-binding.json",
        json.dumps(
            {
                "status": "recorded",
                "binding": {"profile": "basic_test", "route": "opencodex"},
                "responseModel": "actual-trait-model",
            }
        ),
    )
    write(char / "s8-prompts" / "pv1" / "long.md", "페르소나 본문 " + "가" * 7000)
    write(
        char / "s8-prompts" / "pv1" / "text-deck-binding.json",
        json.dumps(
            {
                "selectedConfiguration": {
                    "profile": "demo",
                    "route": "opencodex",
                    "model": "google-antigravity/gemini-4-argon",
                },
                "sourceGeneration": {
                    "status": "recorded",
                    "responseModel": "flash-source-model",
                    "binding": {"profile": "basic_test", "route": "opencodex"},
                },
                "completionCheck": "NOT_RUN",
            }
        ),
    )
    write(char / "s9-data" / "dr1" / "check-report.json", '{"blocking": [], "warnings": 1}')
    calls = char / "ledger" / "calls.jsonl"
    lines = []
    for i in range(60):
        record = {
            "callId": f"c{i}",
            "at": "2026-10-30T00:00:00+00:00",
            "stage": "s8",
            "kind": "AGENT",
            "provider": "openai_compat",
            "model": f"actual-{i:02d}",
            "ok": i != 59,
            "ref": f"{CID}/s8-prompts/pv1#{i}",
            "textBinding": {
                "task": "voice" if i != 59 else "screening",
                "profile": "demo" if i == 59 else "basic_test",
                "route": "test" if i == 59 else "opencodex",
            },
        }
        if i == 58:
            record["ref"] = "/Users/johnhuh619/.env"
        lines.append(json.dumps(record, ensure_ascii=False))
    write(calls, "\n".join(lines) + "\n")

    with client_for(root) as client:
        response = client.get(f"/api/text-pipeline/characters/{CID}")
        assert response.status_code == 200
        body = response.json()

    assert body["characterId"] == CID
    assert body["name"] == "윤하린"
    assert [s["id"] for s in body["stages"]] == ["s3", "s7", "s8", "s9s", "s9"]
    assert [g["id"] for g in body["gates"]] == ["G3", "G6", "G7a", "G7"]
    assert {g["id"]: g["status"] for g in body["gates"]} == {
        "G3": "APPROVED",
        "G6": "AWAITING_HUMAN",
        "G7a": "PENDING",
        "G7": "APPROVED",
    }
    assert len(body["calls"]) == 50
    assert body["calls"][0]["model"] == "actual-10"
    assert body["calls"][-1] == {
        "task": "screening",
        "stage": "s8",
        "model": "actual-59",
        "profile": "demo",
        "route": "test",
        "ok": False,
        "ref": f"{CID}/s8-prompts/pv1#59",
    }
    artifacts = {a["label"]: a for a in body["artifacts"]}
    assert list(artifacts) == ["기획서", "특질 시트", "페르소나 프롬프트", "데이터 검수 보고서"]
    prompt = artifacts["페르소나 프롬프트"]
    assert prompt["revision"] == "pv1"
    assert prompt["sourceModel"] == "flash-source-model"
    assert prompt["sourceProfile"] == "basic_test"
    assert prompt["completionCheck"] == "NOT_RUN"
    assert prompt["text"].startswith("페르소나 본문")
    assert len(prompt["text"]) == 6001
    assert prompt["textTruncated"] is True
    assert artifacts["특질 시트"]["sourceModel"] == "actual-trait-model"
    assert body["workshopUrl"] == f"/studio/factory.html#c/{CID}"
    dumped = json.dumps(body, ensure_ascii=False)
    assert "gemini-4-argon" not in dumped
    assert "/Users/" not in dumped


def test_missing_or_unsafe_artifacts_are_omitted(tmp_path):
    root = make_root(tmp_path)
    char = make_character(root, "cf-bare", None)
    outside = tmp_path / "secret.md"
    write(outside, "공장 밖 비밀")
    (char / "s8-prompts" / "pv1").mkdir(parents=True)
    os.symlink(outside, char / "s8-prompts" / "pv1" / "long.md")

    with client_for(root) as client:
        body = client.get("/api/text-pipeline/characters/cf-bare").json()
        assert body["name"] == "cf-bare"
        assert body["artifacts"] == []
        assert body["calls"] == []
        assert "공장 밖 비밀" not in json.dumps(body, ensure_ascii=False)
        assert client.get("/api/text-pipeline/characters/bad%20id").status_code == 400
        assert client.get("/api/text-pipeline/characters/cf-missing").status_code == 404


def test_recent_calls_excludes_media_generation_from_text_history(tmp_path):
    root = make_root(tmp_path)
    char = make_character(root)
    rows = [
        {"stage": "s7", "kind": "AGENT", "model": "actual-text", "ok": True, "ref": "tr1"},
        {"stage": "s4", "kind": "IMAGE", "model": "image-model", "ok": True, "ref": "fr1"},
        {"stage": "s6", "kind": "VIDEO", "model": "video-model", "ok": True, "ref": "va1"},
    ]
    write(char / "ledger" / "calls.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    with client_for(root) as client:
        body = client.get(f"/api/text-pipeline/characters/{CID}").json()
    assert [c["model"] for c in body["calls"]] == ["actual-text"]
