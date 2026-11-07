# ruff: noqa: E501
"""Somin 방법론의 공장 적용 실험. 실제 호출은 --execute로만 실행한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
from pathlib import Path

import persona_quality_20261028 as recording

from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "runs/experiments/20261028-persona-quality"
ROOT = REPO / "runs/experiments/20261029-somin-transfer"
recording.ROOT = ROOT
recording.RAW = ROOT / "evidence"
recording.RAW.mkdir(parents=True, exist_ok=True)
put, sha, Recorded = recording.put, recording.sha, recording.Recorded


def paths():
    cid = (BASELINE / "character-id.txt").read_text().strip()
    return cid, ROOT / "runs/characters" / cid


def context():
    ctx = Context.load(ROOT, execute=True)
    ctx.use_models(Recorded(recording.GEN), Recorded(recording.JUDGE))
    return ctx


def setup():
    from character_factory_poc.pipeline.approve import approve_gate

    cid, char = paths()
    shutil.copytree(BASELINE / "runs/characters" / cid, char)
    shutil.copyfile(BASELINE / "factory.toml", ROOT / "factory.toml")
    shutil.copyfile(BASELINE / "scenes.json", ROOT / "scenes.json")
    put(
        ROOT / "fork.json",
        {
            "source": str(BASELINE),
            "characterId": cid,
            "originalStateSha256": sha((char / "state.json").read_text()),
            "rule": "All old revisions copied byte-for-byte; original experiment remains unchanged",
        },
    )
    ctx = context()
    approve_gate(
        ctx,
        cid,
        "G6",
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "agent",
            "reasons": "사용자 요청에 따라 한소민 분석의 정본 보존·조건부 반응·말투 흐름을 새 revision에 반영한다.",
        },
    )
    ctx.state(cid).transition("s7", "REJECTED")


def generate(stage):
    cid, _ = paths()
    ctx = context()
    if stage == "s7":
        from character_factory_poc.stages.s7_traits.sheet import run_s7

        print(run_s7(ctx, cid))
    else:
        from character_factory_poc.stages.s8_prompts.build import run_s8

        print(run_s8(ctx, cid, []))


def collect(scene, condition):
    cid, char = paths()
    pair = json.loads((char / "s8-prompts/pv2/prompt-pair.json").read_text())
    system = pair["long"]["text"]
    dest = ROOT / "dialogues" / condition / scene["id"]
    dest.mkdir(parents=True, exist_ok=True)
    history = [Message("system", system)]
    for i, user in enumerate(scene["users"], 1):
        baseline = json.loads(
            (BASELINE / "dialogues/long" / scene["id"] / f"{i:02}.json").read_text()
        )
        history.append(Message("user", user))
        target = dest / f"{i:02}.json"
        if target.exists():
            saved = json.loads(target.read_text())
            assert saved["systemSha256"] == sha(system) and saved["user"] == user
            reply = saved["assistant"]
        else:
            reply = (
                Recorded(recording.CHAT)
                .complete(
                    ChatRequest(
                        "DIALOGUE",
                        f"{condition}-{scene['id']}",
                        tuple(history),
                        f"{condition}/{scene['id']}/{i}",
                        max_output_tokens=2400,
                    )
                )
                .text
            )
            put(
                target,
                {
                    "condition": condition,
                    "scene": scene["id"],
                    "turn": i,
                    "user": user,
                    "assistant": reply,
                    "baselineAssistant": baseline["assistant"],
                    "systemSha256": sha(system),
                    "responseSha256": sha(reply),
                    "historySha256": sha(
                        json.dumps(
                            [{"role": m.role, "content": m.content} for m in history],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            )
        # Shadow replies never enter the frozen baseline history.
        history.append(
            Message("assistant", baseline["assistant"] if condition == "fixed-history" else reply)
        )
    return condition + "/" + scene["id"]


def judge(scene):
    cid, char = paths()
    dest = ROOT / "judgments" / (scene["id"] + ".json")
    if dest.exists():
        return str(dest)
    rows = [
        json.loads(p.read_text())
        for p in sorted((ROOT / "dialogues/revised" / scene["id"]).glob("*.json"))
    ]
    assert len(rows) == len(scene["users"])
    plan = json.loads((char / "s3-plan/pr1/plan.json").read_text())
    rule = """캐릭터 대화의 결함을 분류한다. 점수나 선호 승자는 만들지 않는다. personality·voice·naturalness·context·factualBoundary를 매 턴 분류한다. 각 값은 {status:ok|minor|major|not_tested,evidence:assistant 원문의 정확한 부분문자열 또는 빈 문자열,reason:짧은 이유}다. json {turns:[{turn:1,personality:{...},voice:{...},naturalness:{...},context:{...},factualBoundary:{...}}]}만 출력한다. 모든 턴을 포함한다. 성격은 해당 상황의 첫 행동으로 본다. 한 답에 모든 특질이나 결론-이유-대안 틀을 요구하지 않는다. 명시된 곤란에 도움으로 전환하는 반응을 규칙 위반으로 세지 않는다. 이력에 있던 조건을 새 사실이라고 오판하지 않는다. 허구의 자기 일정·취향·현재 행동 생성은 정본/이력에 모순되지 않으면 허용한다. 사용자 사실·공동 과거·합의 날조나 조회 도구 없이 실제 현재 외부 정보를 확인/검색하겠다는 주장은 구분한다. 현재 조건이 바뀌었거나 사용자가 물어서 일정을 다시 말하는 것은 불필요한 반복으로 세지 않는다. 호감은 확답 압박과 다르다. 관계 목표를 이미 일어난 공동 과거로 보지 않는다. 근거 없이 사용자의 정정을 무조건 맞다고 하면 결함이다. 짧고 구체적으로 이유를 적어 출력 길이를 아낀다."""
    data = {
        "plan": plan,
        "scene": scene,
        "turns": [
            {"turn": t["turn"], "user": t["user"], "assistant": t["assistant"]} for t in rows
        ],
    }
    resp = Recorded(recording.JUDGE).complete(
        ChatRequest(
            "JUDGE",
            f"judge-{scene['id']}",
            (Message("system", rule), Message("user", json.dumps(data, ensure_ascii=False))),
            f"judge/{scene['id']}",
            max_output_tokens=16000,
            response_json=True,
            temperature=0.1,
        )
    )
    obj = extract_json_object(resp.text)
    assert [t["turn"] for t in obj["turns"]] == list(range(1, len(rows) + 1))
    for item, row in zip(obj["turns"], rows, strict=True):
        for dim in ["personality", "voice", "naturalness", "context", "factualBoundary"]:
            assert item[dim]["status"] in ["ok", "minor", "major", "not_tested"]
            item[dim]["evidenceValid"] = item[dim]["evidence"] in row["assistant"]
    put(dest, obj)
    return str(dest)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["setup", "s7", "s8", "dialogue", "judge"])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--kind", choices=["all", "design", "free"], default="all")
    ap.add_argument("--scene", action="append")
    args = ap.parse_args()
    scenes = json.loads((BASELINE / "scenes.json").read_text())
    scenes = [s for s in scenes if args.kind == "all" or s["kind"] == args.kind]
    scenes = [s for s in scenes if args.scene is None or s["id"] in args.scene]
    if args.stage == "judge":
        scenes = [s for s in scenes if not (ROOT / "judgments" / (s["id"] + ".json")).exists()]
        if args.execute:
            for scene in scenes:
                if len(list((ROOT / "dialogues/revised" / scene["id"]).glob("*.json"))) != len(
                    scene["users"]
                ):
                    raise SystemExit(f"대화 수집이 끝나지 않은 장면: {scene['id']}")
    calls = {
        "setup": 0,
        "s7": 5,
        "s8": 5,
        "dialogue": sum(len(s["users"]) * (2 if s["kind"] == "free" else 1) for s in scenes),
        "judge": len(scenes),
    }[args.stage]
    if not args.execute:
        print(
            json.dumps(
                {
                    "dryRun": True,
                    "stage": args.stage,
                    "nominalCalls": calls,
                    "billing": "unknown",
                    "scenarioUSD": "Whole experiment planning assumption $2-20, not an actual tariff or guaranteed charge cap",
                    "assumedUSDperMillion": {"input": [1, 10], "output": [5, 50]},
                    "mediaAndTraining": False,
                    "dialogueRetries": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.stage == "setup":
        setup()
    elif args.stage in ["s7", "s8"]:
        generate(args.stage)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            if args.stage == "dialogue":
                jobs = [(s, "revised") for s in scenes] + [
                    (s, "fixed-history") for s in scenes if s["kind"] == "free"
                ]
                futures = [pool.submit(collect, s, condition) for s, condition in jobs]
            else:
                futures = [pool.submit(judge, s) for s in scenes]
            for future in concurrent.futures.as_completed(futures):
                print("DONE", future.result(), flush=True)
