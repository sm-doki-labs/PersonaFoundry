# ruff: noqa: E501
# Preserve full Korean instructions and inline HTML strings.
"""First-response dialogue collection and independent-family per-turn defect triage."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from persona_quality_20261028 import CHAT, JUDGE, ROOT, Recorded, put, sha

from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object


def load():
    cid = (ROOT / "character-id.txt").read_text().strip()
    char = ROOT / "runs/characters" / cid
    return cid, char, json.loads((char / "s3-plan/pr1/plan.json").read_text())


def scenes():
    return json.loads((ROOT / "scenes.json").read_text())


def dialogue(mode, scene):
    cid, char, plan = load()
    pair = json.loads((char / "s8-prompts/pv1/prompt-pair.json").read_text())
    system = pair[mode]["text"]
    dest = ROOT / "dialogues" / mode / scene["id"]
    dest.mkdir(parents=True, exist_ok=True)
    history = [Message("system", system)]
    model = Recorded(CHAT)
    for i, user in enumerate(scene["users"], 1):
        p = dest / f"{i:02}.json"
        if p.exists():
            old = json.loads(p.read_text())
            assert old["user"] == user and old["systemSha256"] == sha(system)
            history += [Message("user", user), Message("assistant", old["assistant"])]
            continue
        history.append(Message("user", user))
        req = ChatRequest(
            "DIALOGUE",
            f"dialogue-{mode}-{scene['id']}",
            tuple(history),
            f"{mode}/{scene['id']}/{i}",
            max_output_tokens=2400,
            temperature=0.7,
        )
        resp = model.complete(req)
        put(
            p,
            dict(
                turn=i,
                scene=scene["id"],
                mode=mode,
                user=user,
                assistant=resp.text,
                systemSha256=sha(system),
                historySha256=sha(
                    json.dumps(
                        [dict(role=m.role, content=m.content) for m in history],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
                responseSha256=sha(resp.text),
                returnedModel=resp.model,
                inputTokens=resp.input_tokens,
                outputTokens=resp.output_tokens,
                elapsedMs=resp.elapsed_ms,
            ),
        )
        history.append(Message("assistant", resp.text))
    return mode + "/" + scene["id"]


def judge(mode, scene):
    cid, char, plan = load()
    dest = ROOT / "judgments" / mode / (scene["id"] + ".json")
    if dest.exists():
        return str(dest)
    turns = [
        json.loads(p.read_text())
        for p in sorted((ROOT / "dialogues" / mode / scene["id"]).glob("*.json"))
    ]
    assert len(turns) == len(scene["users"])
    sheet = json.loads((char / "s7-traits/tr1/trait-sheet.json").read_text())
    instructions = """한국어 캐릭터 대화의 결함만 찾는 검토자다. 생성은 GPT, 응답은 Gemini이며 너는 Claude다. 점수나 총평 대신 매 턴 다섯 차원(personality, voice, naturalness, context, factualBoundary)의 결함을 각각 분류한다. 증거 없이 결함을 만들지 않는다. 성격은 라벨/상투어가 아니라 같은 조건에서 먼저 택한 행동과 가치로 비교한다. 말투는 기획서 voiceSummary/voiceExamples에 비춘다. 장면의 모든 이전 턴을 읽고 소유자/조건 정정이 실제 이전 발화와 맞는지 확인한다. 사용자의 잘못된 정정에 무조건 사과/동조하는 것도 결함이다. 현재 뉴스/영업/날씨/교통을 확인한 척하지 않는지 본다. 책방/산책 제안의 과잉 반복과 앞말 재요약도 자연스러움 결함이다. 모델 판정은 참고 자료이며 최종 품질 점수가 아니다. json 객체 {"turns":[{"turn":1,"personality":{"status":"ok|minor|major|not_tested","evidence":"정확한 응답 일부","reason":"근거"},"voice":{...},"naturalness":{...},"context":{...},"factualBoundary":{...}}]}만 반환한다. 반드시 모든 턴에 다섯 차원을 채워라. evidence는 assistant 원문의 정확한 부분문자열 또는 빈 문자열이어야 한다."""
    data = dict(
        plan=plan,
        traits=sheet,
        scene=scene,
        conversation=[
            dict(turn=t["turn"], user=t["user"], assistant=t["assistant"]) for t in turns
        ],
    )
    response = Recorded(JUDGE).complete(
        ChatRequest(
            "JUDGE",
            f"judge-{mode}-{scene['id']}",
            (
                Message("system", instructions),
                Message("user", json.dumps(data, ensure_ascii=False)),
            ),
            f"{mode}/{scene['id']}",
            max_output_tokens=16000,
            response_json=True,
            temperature=0.1,
        )
    )
    obj = extract_json_object(response.text)
    assert [t["turn"] for t in obj["turns"]] == list(range(1, len(turns) + 1))
    for t, raw in zip(obj["turns"], turns, strict=True):
        for dim in ["personality", "voice", "naturalness", "context", "factualBoundary"]:
            assert t[dim]["status"] in ["ok", "minor", "major", "not_tested"]
            t[dim]["evidenceValid"] = t[dim]["evidence"] in raw["assistant"]
    put(dest, obj)
    return str(dest)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["dialogue", "judge"])
    ap.add_argument("--mode", choices=["long", "short", "both"], default="both")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--kind", choices=["all", "design", "free"], default="all")
    ap.add_argument("--scene", default=None)
    a = ap.parse_args()
    jobs = [
        (m, s)
        for m in (["long", "short"] if a.mode == "both" else [a.mode])
        for s in scenes()
        if a.kind == "all" or s["kind"] == a.kind
    ]
    jobs = [(m, s) for m, s in jobs if a.scene is None or s["id"] == a.scene]
    calls = sum(len(s["users"]) for m, s in jobs) if a.stage == "dialogue" else len(jobs)
    plan = dict(
        stage=a.stage,
        modes=a.mode,
        calls=calls,
        maxTransportRetries=0,
        maxOutputTokensPerCall=2400 if a.stage == "dialogue" else 16000,
        estimatedCostUSD="unknown",
        sensitivityRatesPerMillion={"input": [1, 10], "output": [5, 50]},
        billingNote="Assumed scenario rates, not vendor prices; actual token usage saved",
        contract="No regenerated responses; full true history; unchanged G6 system",
    )
    if not a.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        fn = dialogue if a.stage == "dialogue" else judge
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            futures = [pool.submit(fn, m, s) for m, s in jobs]
            for f in concurrent.futures.as_completed(futures):
                print("DONE", f.result(), flush=True)
