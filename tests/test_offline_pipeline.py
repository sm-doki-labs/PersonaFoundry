"""PoC 전체 흐름(D-0044, 계획서 §8).

여성·남성 합성 브리프가 S1 → G9 → 패키지 → 우리 앱 적재까지 간다.

- 단계 진행은 오케스트레이터(`run_until`)가 그래프를 따라 한다. 테스트는 단계를 직접 부르지 않는다.
- 관문 결정은 모두 워크숍 웹 API(`POST /api/characters/{id}/gates/{gate}/decision`)로 보낸다.
  답은 화면이 보여 주는 항목(`GET .../gates/{gate}`)에서 만든다.
  사람이 화면에서 하는 일과 같은 경로다.
- 공급자는 모두 가짜다(이미지·영상·LLM·학습). 네트워크를 쓰지 않는다.
- `CFP_PG_ADMIN_URL`이 있으면 마지막 내보내기(sx)가 일회용 PostgreSQL 두 개(api-svc·chat-svc)에
  실제로 넣어 확인한다(`scripts/verify_db.sh up`). 없으면 적재 확인은 NOT_RUN으로 남는다.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.pipeline.graph import GATES
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s3_plan.draft import new_character
from character_factory_poc.web import create_app
from tests.support.data_fakes import FakeWriterModel, s9_toml, write_sns
from tests.support.flow import make_ctx
from tests.support.synthetic import RANKING, prompter_output
from tests.support.web_gates import PROBES, SEED, answer_for, trait_sheet_for
from tests.test_plan_variants import output as plan_variants
from tests.test_s10_eval import JudgeResponder
from tests.test_scene_flow import backgrounds, poses, scenes

VERIFY_DB = bool(os.environ.get("CFP_PG_ADMIN_URL"))
CHARACTERS = {
    "female": {"name": "윤하린", "category": "여자 배우"},
    "male": {"name": "강도윤", "category": "남자 배우"},
}
MAX_ROUNDS = 30


def ranking_for(gender: str) -> dict:
    """합성 순위 목록의 성별 범위만 바꾼다. 인물 이름은 모두 가상이다."""
    ranking = copy.deepcopy(RANKING)
    ranking["scope"]["characterGender"] = gender
    ranking["lists"][0]["category"] = CHARACTERS[gender]["category"]
    return ranking


def factory_toml(root: Path) -> str:
    return (
        "[providers.text]\n"
        'adapter = "fake"\n'
        'model = "base-model"\n'
        "[providers.judge]\n"
        'adapter = "fake"\n'
        'model = "anthropic/claude-opus-5-5"\n'
        "[budget]\n"
        "max_calls_per_command = 20000\n"
        "[stages.s10t]\n"
        'providers = ["fake"]\n' + s9_toml(root)
    )


class Judge(JudgeResponder):
    """평가 판정은 S10 시험의 가짜 판정자를 쓰고, S8 말투 표본 판정에는 고정 답을 준다."""

    def __call__(self, req):
        if req.stage == "s8":
            return {"pick": "A", "reasons": "선택이 더 맞는다"}
        return super().__call__(req)


def eval_replies():
    """평가 응답. 매번 다른 문장이라 반복률 지표가 0에 가깝게 나온다."""
    counter = itertools.count(1)
    return lambda req: f"응, 그 얘기 기억해. 오늘 {next(counter)}번째로 들어도 좋아."


def gendered_variants(cid: str, gender: str) -> dict:
    out = plan_variants(cid)
    for plan in out["variants"] if "variants" in out else out["plans"]:
        plan["gender"] = gender
        plan["name"] = CHARACTERS[gender]["name"]
    return out


def setup(root: Path, gender: str):
    root.mkdir(parents=True)
    write_sns(root / "sns.jsonl")
    ctx, agents = make_ctx(root, factory_toml(root))
    cid = new_character(ctx, f"poc-{gender}")
    agents.set("s3-variants", lambda req: gendered_variants(cid, gender))
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    agents.set("s7", lambda req: trait_sheet_for(ctx, cid))
    agents.set("s8", lambda req: prompter_output())
    writer = FakeWriterModel()
    agents.set("s9s", writer.respond)
    agents.set("s9", writer.respond)
    text = ctx._text
    text.add("PROBE", lambda req: "그럼 이렇게 하자. 내일 아침에 같이 보자.")
    text.add("EVAL", eval_replies())
    judge = FakeTextModel(model="anthropic/claude-opus-5-5")
    judge.add("JUDGE", Judge())
    ctx.use_models(text, judge)
    return ctx, cid


def view(client: TestClient, cid: str, gate: str) -> dict:
    res = client.get(f"/api/characters/{cid}/gates/{gate}")
    assert res.status_code == 200, res.text
    return res.json()


def post(client: TestClient, cid: str, gate: str, answer: dict) -> None:
    res = client.post(f"/api/characters/{cid}/gates/{gate}/decision", json=answer)
    assert res.status_code == 200, (gate, res.text)


def decide(client: TestClient, cid: str, gate: str, seen: dict) -> None:
    """화면 항목을 읽고 사람이 고를 답을 만들어 보낸다."""
    v = view(client, cid, gate)
    items = v["items"]
    seen[gate] = items.get("source")
    if gate in {"G1", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6"}:
        post(client, cid, gate, answer_for(gate, items))
        return
    if gate == "G7a":
        for cluster in items["clusters"]:
            if cluster["reviewed"]:
                continue
            verdicts = {s["conversationId"]: "ADOPT" for s in cluster["samples"]}
            assert verdicts, cluster["clusterId"]
            post(
                client,
                cid,
                gate,
                {
                    "decision": "SELECT",
                    "cluster": cluster["clusterId"],
                    "verdicts": verdicts,
                    "notes": {},
                    "reviewer": "tester",
                    "minutes": 1,
                },
            )
        return
    if gate == "G7":
        assert items["dataset"]["blockingFailures"] == 0
        assert items["samples"]
        post(client, cid, gate, {"decision": "APPROVE", "verdicts": {}, "reviewer": "tester"})
        return
    if gate == "G8":
        pairs = items["pairs"]
        assert len(pairs) == 20
        blind = json.dumps(pairs, ensure_ascii=False)
        assert "LONG_BASE" not in blind and "SFT" not in blind
        answer = {
            "decision": "SELECT",
            "adopted": items["adoptOptions"][0],
            "humanPicks": [{"pairId": p["pairId"], "pick": "A"} for p in pairs],
            "reviewer": "tester",
            "minutes": 15,
        }
        post(client, cid, gate, answer)
        return
    if gate == "G9":
        assert items["counts"]["missing"] == []
        post(client, cid, gate, {"decision": "APPROVE", "reviewer": "tester", "reasons": "확인"})
        return
    raise AssertionError(f"모르는 관문: {gate}")


@pytest.mark.parametrize("gender", sorted(CHARACTERS))
def test_full_pipeline_from_ranking_to_app_db(tmp_path: Path, gender: str) -> None:
    root = tmp_path / gender
    ctx, cid = setup(root, gender)
    opt = RunOptions(
        until="sx",
        ranking=ranking_for(gender),
        seed=SEED,
        voice_probes=list(PROBES),
        verify_export=VERIFY_DB,
    )
    seen: dict[str, str | None] = {}
    rounds = 0
    with TestClient(create_app(root)) as client:
        for _ in range(MAX_ROUNDS):
            rounds += 1
            log = run_until(ctx, cid, opt)
            if ctx.state(cid).stage("sx").status == "APPROVED":
                break
            assert log.waiting, ("진행이 멈췄다", log.blocked, log.steps[-8:])
            for gate in log.waiting:
                decide(client, cid, gate, seen)
        else:
            pytest.fail(f"{MAX_ROUNDS}번 돌아도 끝나지 않았다")

    state = ctx.state(cid)
    # 모든 현행 관문이 사람(웹 API) 결정으로 승인됐다. G2는 결번이다.
    assert set(seen) == set(GATES)
    for gate in GATES:
        assert state.gate(gate).status == "APPROVED", gate
    # G7a~G9 화면은 합성 예시가 아니라 실제 산출물을 보여 줬다.
    assert all(seen[g] == "artifacts" for g in ("G7a", "G7", "G8", "G9"))
    for sid in ("s2", "s9s", "s9", "s10t", "s10", "s11", "sx"):
        assert state.stage(sid).status == "APPROVED", sid

    char_dir = ctx.character_dir(cid)
    package_rev = state.stage("s11").currentRev
    package = json.loads((char_dir / "s11-release" / package_rev / "package.json").read_text())
    assert package["characterId"] == cid
    assert package["profile"]["gender"] == gender
    assert package["profile"]["name"] == CHARACTERS[gender]["name"]
    assert len(package["chapters"]) == 3
    kinds = [v["kind"] for v in package["videos"]]
    assert kinds.count("INTRO") == 1 and kinds.count("ACTION") == 18
    assert all(v["synthetic"] for v in package["videos"])
    assert package["persona"]["longPrompt"] and package["persona"]["shortPrompt"]
    assert package["sft"]["datasetRev"] and package["sft"]["evalReport"]
    assert {g["gate"] for g in package["gates"]} >= set(GATES) - {"G9"}

    export_rev = state.stage("sx").currentRev
    result = json.loads((char_dir / "sx-export" / export_rev / "export-result.json").read_text())
    assert {o["system"] for o in result["outputs"]} == {"api-svc", "chat-svc"}
    verification = result["verification"]
    assert verification["disposableDb"] is True
    if VERIFY_DB:
        assert verification["status"] == "PASSED", verification["steps"]
        names = [s["name"] for s in verification["steps"]]
        assert sum(1 for n in names if n.startswith("drop")) == 2
    else:
        assert verification["status"] == "NOT_RUN"
    print(f"{gender}: {rounds}회 실행으로 sx까지, 적재 확인 {verification['status']}")
