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
    seen.setdefault("kinds", {})[gate] = v["kind"]
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
    if gate == "G8" and v["kind"] == "promptOnly":
        # 학습 결과 없이 연 G8(K-0038): 화면은 블라인드 비교 대신 '긴 프롬프트로 진행'을 묻는다.
        assert "pairs" not in items and items["adoptOptions"] == ["LONG_BASE"]
        choice = seen.get("g8_choice", "SELECT")
        answer = {"decision": choice, "reviewer": "tester", "minutes": 1}
        if choice == "SELECT":
            answer["adopted"] = "LONG_BASE"
        post(client, cid, gate, answer)
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


def drive(root: Path, gender: str, *, submit_training: bool, seen: dict) -> tuple:
    """sx가 끝나거나 더 진행할 관문이 없을 때까지 돌리고 대기 관문을 웹 API로 결정한다."""
    ctx, cid = setup(root, gender)
    opt = RunOptions(
        until="sx",
        ranking=ranking_for(gender),
        seed=SEED,
        voice_probes=list(PROBES),
        verify_export=VERIFY_DB,
        submit_training=submit_training,
    )
    rounds = 0
    log = None
    with TestClient(create_app(root)) as client:
        for _ in range(MAX_ROUNDS):
            rounds += 1
            log = run_until(ctx, cid, opt)
            if ctx.state(cid).stage("sx").status == "APPROVED" or not log.waiting:
                break
            for gate in log.waiting:
                decide(client, cid, gate, seen)
        else:
            pytest.fail(f"{MAX_ROUNDS}번 돌아도 끝나지 않았다")
    return ctx, cid, rounds, log


@pytest.mark.parametrize("gender", sorted(CHARACTERS))
def test_full_pipeline_from_ranking_to_app_db(tmp_path: Path, gender: str) -> None:
    """SFT 경로: 학습(가짜)을 제출·회수하고 평가·블라인드 판정을 거쳐 패키지·적재까지."""
    seen: dict = {}
    ctx, cid, rounds, log = drive(tmp_path / gender, gender, submit_training=True, seen=seen)
    assert ctx.state(cid).stage("sx").status == "APPROVED", log.steps[-8:]
    assert seen["kinds"]["G8"] == "eval"
    seen.pop("kinds")

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


def test_prompt_only_path_packages_without_training(tmp_path: Path) -> None:
    """K-0038: 학습은 계획(dry run)만, G8에서 긴 프롬프트를 골라 패키지·적재까지 간다."""
    seen: dict = {}
    ctx, cid, rounds, log = drive(tmp_path / "f", "female", submit_training=False, seen=seen)
    state = ctx.state(cid)
    assert state.stage("sx").status == "APPROVED", log.steps[-8:]
    assert seen["kinds"]["G8"] == "promptOnly"
    assert state.stage("s10t").status == "AWAITING_HUMAN"  # 계획만 있고 제출하지 않았다
    char_dir = ctx.character_dir(cid)
    plan_run = next((char_dir / "s10-train").glob("tr*/*/training-run.json"))
    assert json.loads(plan_run.read_text())["dryRun"] is True
    package_rev = state.stage("s11").currentRev
    package = json.loads((char_dir / "s11-release" / package_rev / "package.json").read_text())
    sft = package["sft"]
    assert sft["adoptedBinding"] == "LONG_BASE"
    assert sft["evalReport"] is None
    assert sft["datasetRev"] and sft["trainingRuns"]
    assert package["persona"]["longPrompt"]
    export_rev = state.stage("sx").currentRev
    result = json.loads((char_dir / "sx-export" / export_rev / "export-result.json").read_text())
    assert result["verification"]["status"] == ("PASSED" if VERIFY_DB else "NOT_RUN")


def test_prompt_only_wait_choice_keeps_s10_waiting(tmp_path: Path) -> None:
    """G8에서 '학습을 기다린다'를 고르면 평가가 멈추고, 다시 돌려도 같은 질문을 또 열지 않는다."""
    seen: dict = {"g8_choice": "REJECT"}
    ctx, cid, rounds, log = drive(tmp_path / "f", "female", submit_training=False, seen=seen)
    state = ctx.state(cid)
    assert state.gate("G8").status == "REJECTED"
    assert state.stage("s10").status == "REJECTED"
    assert state.stage("s11").status == "PENDING"
    assert "s10" in log.blocked and any("학습 결과" in s for s in log.steps)
    evals = sorted(p.name for p in (ctx.character_dir(cid) / "s10-eval").iterdir())
    assert evals == ["ev1"]
