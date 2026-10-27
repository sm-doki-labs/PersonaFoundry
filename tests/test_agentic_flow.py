"""에이전틱 전체 흐름 (D-0049, LLD §11 M9, 계획서 §8).

사람은 워크숍 API로 작업을 한 번 시작하고 그 뒤로는 관문 결정만 보낸다. 결정마다 실행기가
이어서 돌고(자동 재개), 의존이 풀린 갈래는 동시에 돈다(물결 실행). 중간에 G4a·G4 수정 요청을
한 번씩 넣는다. 공급자는 모두 가짜이고 네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.config import load_config
from character_factory_poc.pipeline.graph import GATES
from character_factory_poc.pipeline.orchestrator import RunLog, run_until
from character_factory_poc.web import create_app
from tests import test_offline_pipeline as flow

ORCH = '\n[orchestrator]\nmax_parallel = 3\nauto_resume = true\nresume_until = "sx"\n'
NOTES = {"G4a": "ch2 배경을 비 오는 골목으로", "G4": "ch2 표정을 조금 더 밝게"}


def _idle(client: TestClient, cid: str, timeout: float = 60.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        data = client.get(f"/api/characters/{cid}").json()
        if data["job"] is None:
            return data
        time.sleep(0.05)
    raise AssertionError("작업이 끝나지 않았다")


def _app(root: Path, ctx, extra: dict):
    holder: dict = {}

    def runner(job, stream) -> RunLog:
        jobs = holder["app"].state.jobs
        log = run_until(ctx, job.character_id, jobs.run_options(job, stream, **extra))
        holder.setdefault("waves", []).extend(log.waves)
        holder.setdefault("triggers", []).append(job.trigger)
        return log

    app = create_app(root, runner=runner)
    holder["app"] = app
    return app, holder


def _request_changes(client: TestClient, cid: str, gate: str) -> None:
    res = client.post(
        f"/api/characters/{cid}/gates/{gate}/decision",
        json={
            "decision": "REQUEST_CHANGES",
            "requestedChanges": [{"field": "ch2", "note": NOTES[gate]}],
            "reviewer": "tester",
            "minutes": 1,
        },
    )
    assert res.status_code == 200, (gate, res.text)


@pytest.mark.parametrize("gender", sorted(flow.CHARACTERS))
def test_workshop_decisions_only_reach_export(tmp_path: Path, gender: str) -> None:
    root = tmp_path / gender
    ctx, cid = flow.setup(root, gender)
    with open(root / "factory.toml", "a", encoding="utf-8") as f:
        f.write(ORCH)
    ctx.config = load_config(root)
    extra = {
        "ranking": flow.ranking_for(gender),
        "seed": flow.SEED,
        "voice_probes": list(flow.PROBES),
        "submit_training": True,
        "verify_export": flow.VERIFY_DB,
    }
    app, holder = _app(root, ctx, extra)
    asked: set[str] = set()
    seen: dict = {}
    with TestClient(app) as client:
        res = client.post("/api/jobs", json={"characterId": cid, "action": "run", "until": "sx"})
        assert res.status_code == 202, res.text  # 사람이 작업을 시작한 것은 이 한 번뿐이다
        for _ in range(60):
            detail = _idle(client, cid)
            if ctx.state(cid).stage("sx").status == "APPROVED":
                break
            pending = detail["pendingGates"]
            assert pending, (detail["lastJob"], ctx.state(cid).stage("sx").status)
            gate = pending[0] if isinstance(pending[0], str) else pending[0]["id"]
            if gate in NOTES and gate not in asked:
                asked.add(gate)
                _request_changes(client, cid, gate)
                continue
            flow.decide(client, cid, gate, seen)
        else:
            pytest.fail("관문 결정만으로 끝나지 않았다")
        jobs = client.get(f"/api/jobs?characterId={cid}&limit=200").json()["jobs"]
    state = ctx.state(cid)
    assert state.stage("sx").status == "APPROVED"
    for gate in GATES:
        assert state.gate(gate).status == "APPROVED", gate
    assert [j["trigger"] for j in jobs].count("manual") == 1
    # 관문을 하나씩 결정하므로 어느 갈래가 겹치는지는 결정 순서에 달렸다. 한 결정(G1)이 두 갈래를
    # 함께 푸는 s3‖s5와, G3 하나가 함께 푸는 s4a‖s7은 늘 같은 물결이다.
    together = [set(w) for w in holder["waves"]]
    for pair in ({"s3", "s5"}, {"s4a", "s7"}):
        assert any(pair <= w for w in together), (pair, holder["waves"])
    char_dir = ctx.character_dir(cid)
    for gate in NOTES:
        records = sorted((char_dir / "gates").glob(f"{gate}-*.json"))
        decisions = [json.loads(p.read_text("utf-8"))["decision"] for p in records]
        assert decisions[0] == "REQUEST_CHANGES" and decisions[-1] != "REQUEST_CHANGES", decisions
    result = json.loads(
        (char_dir / "sx-export" / state.stage("sx").currentRev / "export-result.json").read_text()
    )
    assert result["verification"]["status"] == ("PASSED" if flow.VERIFY_DB else "NOT_RUN")
