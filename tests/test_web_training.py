"""모델 만들기 화면의 서버 쪽(D-0130): 학습 진행 읽기, 웹 학습 시작·중단·반납, 학습 없이 진행.

가짜 공급자 합성 캐릭터를 학습 계획(s10t dry run)까지 한 번 만들고 시험마다 복사해 쓴다.
실제 GPU·네트워크 호출은 없다.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.web import create_app
from tests import test_offline_pipeline as flow


@pytest.fixture(scope="module")
def planned_root(tmp_path_factory) -> tuple[Path, str]:
    root = tmp_path_factory.mktemp("planned") / "root"
    ctx, cid = flow.setup(root, "female")
    opt = RunOptions(
        until="s10t",
        ranking=flow.ranking_for("female"),
        seed=flow.SEED,
        voice_probes=list(flow.PROBES),
    )
    seen: dict = {}
    with TestClient(create_app(root)) as client:
        for _ in range(flow.MAX_ROUNDS):
            log = run_until(ctx, cid, opt)
            if ctx.state(cid).stage("s10t").status == "AWAITING_HUMAN":
                break
            for gate in log.waiting:
                flow.decide(client, cid, gate, seen)
    assert ctx.state(cid).stage("s10t").status == "AWAITING_HUMAN"
    return root, cid


@pytest.fixture
def planned(planned_root, tmp_path) -> tuple[Path, str]:
    src, cid = planned_root
    root = tmp_path / "root"
    shutil.copytree(src, root)
    return root, cid


def _fake_training(root: Path, **extra: object) -> None:
    """가짜 학습을 천천히·실패하게 만든다. poll_s는 0.05초."""
    path = root / "factory.toml"
    text = path.read_text("utf-8").replace(
        'providers = ["fake"]\n', 'providers = ["fake"]\npoll_s = 0.05\n', 1
    )
    text += "[stages.s10t.fake]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in extra.items())
    path.write_text(text, "utf-8")


def _wait_idle(client: TestClient, cid: str, timeout: float = 30.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        detail = client.get(f"/api/characters/{cid}").json()
        if not detail["job"]:
            return detail
        time.sleep(0.05)
    raise AssertionError("작업이 끝나지 않았다")


def _state(root: Path, cid: str) -> dict:
    return json.loads((root / "runs" / "characters" / cid / "state.json").read_text("utf-8"))


def test_plan_view_and_web_run_waits_for_training_choice(planned) -> None:
    root, cid = planned
    with TestClient(create_app(root)) as client:
        mp = client.get(f"/api/characters/{cid}/model-path").json()
        assert mp["training"]["state"] == "plan"
        assert [p["key"] for p in mp["training"]["phases"]] == [
            "guard", "lease", "upload", "train", "screen", "collect", "select",
        ]  # fmt: skip
        assert mp["dataset"]["gates"]["G7"]["status"] == "APPROVED"
        assert {c["id"] for c in mp["dataset"]["clusters"]} >= {"base", "conflict"}
        # D-0135: 흐름 뼈대만 쓰고 양쪽을 새로 쓴다. 원본 겹침과 뼈대 예시가 보인다.
        assert mp["material"]["rewrite"] == "SKELETON" and mp["material"]["warehouse"] is False
        src = mp["material"]["sources"]
        assert src["overlap"]["limit"] == 10 and src["overlap"]["max"] < 10
        assert len(src["example"]["beats"]) >= 3
        # D-0138·D-0139: 학습용 짧은 프롬프트 요약(관계 4종·채널 4종).
        tp = mp["dataset"]["trainingPrompt"]
        assert tp["relationships"] == 4 and tp["channels"] == 4 and tp["longestChars"] > 0
        detail = client.get(f"/api/characters/{cid}").json()
        assert detail["modelPath"]["training"]["state"] == "plan"
        # 웹 실행은 학습 계획 뒤 '학습 시작/학습 없이 진행'을 고를 때까지 평가(G8)를 열지 않는다.
        assert client.post("/api/jobs", json={"characterId": cid, "until": "sx"}).status_code == 202
        detail = _wait_idle(client, cid)
    state = _state(root, cid)
    assert state["stages"].get("s10", {}).get("status", "PENDING") == "PENDING"
    assert state["gates"].get("G8", {}).get("status") != "AWAITING_HUMAN"
    assert "s10" in detail["lastJob"]["blocked"]


def test_train_needs_cost_confirmation_then_finishes(planned) -> None:
    root, cid = planned
    with TestClient(create_app(root)) as client:
        res = client.post("/api/jobs", json={"characterId": cid, "action": "train"})
        assert res.status_code == 400
        res = client.post(
            "/api/jobs", json={"characterId": cid, "action": "train", "confirm": ["s10t"]}
        )
        assert res.status_code == 202, res.text
        _wait_idle(client, cid)
        training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
    assert training["state"] == "done" and training["adopted"]
    assert training["rev"] == "tr1"  # 계획을 그대로 쓰고 새로 세우지 않았다
    assert {p["status"] for p in training["phases"]} <= {"ok", "skip"}
    assert _state(root, cid)["stages"]["s10t"]["status"] == "APPROVED"


def test_skip_training_opens_prompt_only_review(planned) -> None:
    root, cid = planned
    with TestClient(create_app(root)) as client:
        res = client.post(
            "/api/jobs", json={"characterId": cid, "action": "skip-training", "until": "sx"}
        )
        assert res.status_code == 202, res.text
        _wait_idle(client, cid)
        mp = client.get(f"/api/characters/{cid}/model-path").json()
        # 다시 고를 수 없다(이미 학습 없이 진행)
        again = client.post("/api/jobs", json={"characterId": cid, "action": "skip-training"})
    assert again.status_code == 409
    assert mp["training"]["state"] == "skip"
    assert mp["eval"]["promptOnly"] and mp["eval"]["gate"]["status"] == "AWAITING_HUMAN"


def test_stop_cancels_running_training(planned) -> None:
    root, cid = planned
    _fake_training(root, run_polls=400)
    with TestClient(create_app(root)) as client:
        assert client.post(f"/api/characters/{cid}/training/stop").status_code == 409
        client.post("/api/jobs", json={"characterId": cid, "action": "train", "confirm": ["s10t"]})
        end = time.monotonic() + 10
        training = {}
        while time.monotonic() < end:
            training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
            if training["state"] == "run" and (training["phases"][3]["meter"] or 0) > 0:
                break
            time.sleep(0.05)
        assert training["phases"][3]["status"] == "run", training
        assert client.post(f"/api/characters/{cid}/training/stop").status_code == 202
        detail = _wait_idle(client, cid)
        training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
    assert detail["lastJob"]["stoppedAt"] == "stopped"
    assert training["state"] == "stopped"
    assert training["phases"][3]["status"] == "fail"
    assert _state(root, cid)["stages"]["s10t"]["status"] == "REJECTED"


def test_collect_failure_holds_then_retry_finishes(planned) -> None:
    root, cid = planned
    _fake_training(root, run_polls=2, collect_failures=1)
    with TestClient(create_app(root)) as client:
        body = {"characterId": cid, "action": "train", "confirm": ["s10t"]}
        client.post("/api/jobs", json=body)
        detail = _wait_idle(client, cid)
        assert detail["lastJob"]["status"] == "failed"
        training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
        assert training["state"] == "hold" and training["phases"][5]["status"] == "fail"
        client.post("/api/jobs", json=body)  # 다시 받아 오기
        _wait_idle(client, cid)
        training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
    assert training["state"] == "done" and training["rev"] == "tr1"


def test_release_discards_held_result(planned) -> None:
    root, cid = planned
    _fake_training(root, run_polls=2, collect_failures=5)
    with TestClient(create_app(root)) as client:
        assert client.post(f"/api/characters/{cid}/training/release").status_code == 409
        client.post("/api/jobs", json={"characterId": cid, "action": "train", "confirm": ["s10t"]})
        _wait_idle(client, cid)
        res = client.post(f"/api/characters/{cid}/training/release")
        assert res.status_code == 200, res.text
        training = client.get(f"/api/characters/{cid}/model-path").json()["training"]
    assert training["state"] == "stopped" and not training["adopted"]


def test_gpu_eval_needs_confirmation_only_for_real_adapters(tmp_path: Path) -> None:
    from character_factory_poc.pipeline.orchestrator import gpu_eval_held
    from character_factory_poc.providers.training.inference import ADAPTER_FILES
    from character_factory_poc.stages.s3_plan.common import new_character
    from tests.support.flow import make_ctx

    ctx, _agents = make_ctx(tmp_path, flow.factory_toml(tmp_path))
    cid = new_character(ctx, "gpu")
    folder = ctx.character_dir(cid) / "s10-train" / "tr1" / "gemma_qlora"
    adapter = folder / "artifacts" / "checkpoint-2"
    adapter.mkdir(parents=True)
    run = {
        "schemaVersion": "training-run-v2",
        "characterId": cid,
        "datasetRev": "ds1",
        "datasetDigest": "x",
        "provider": "gemma_qlora",
        "baseModel": "gemma",
        "requestedConfig": {},
        "dryRun": False,
        "estimate": {"usd": 1.0},
        "budgetUsd": 6.0,
        "status": "SUCCEEDED",
        "modelBinding": {"provider": "gemma_qlora", "ref": str(adapter), "checkpointId": "c2"},
    }
    (folder / "training-run.json").write_text(json.dumps(run), "utf-8")
    assert not gpu_eval_held(ctx, cid, "s10")  # 어댑터 파일이 아직 없다
    for name in ADAPTER_FILES:
        (adapter / name).write_text("x", "utf-8")
    assert gpu_eval_held(ctx, cid, "s10")
    assert not gpu_eval_held(ctx, cid, "s9")


def test_renting_gpu_shows_as_running_not_cost_confirmation(planned) -> None:
    """제출 중(GPU 빌림·올림)에는 실행 기록이 PLANNED여도 '학습 중'이다. 돈이 나가는 중이다."""
    from character_factory_poc.web.model_path import training_view

    root, cid = planned
    char_dir = root / "runs" / "characters" / cid
    folder = next((char_dir / "s10-train").glob("tr*/fake"))
    lease = {
        "status": "READY",
        "gpu": "L40S",
        "dphTotal": 0.71,
        "createdAt": "2026-11-08T04:00:00+00:00",
    }
    (folder / "lease.json").write_text(json.dumps(lease), "utf-8")
    training = training_view(char_dir, _state(root, cid))
    assert training["state"] == "run"
    assert training["providers"][0]["gpuAlive"] and training["spentUsd"] > 0
