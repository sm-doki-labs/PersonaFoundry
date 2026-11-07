# ruff: noqa: E501
"""Freeze blind actual-response packets, defect triage and verified counts."""

import argparse
import concurrent.futures
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import persona_choice_voice_live_20261029 as live

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.persona import load_prompt_pair
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object

ROOT = live.ROOT


def packet():
    records = []
    mapping = {}
    errors = []
    ordered = []
    for label in live.LABELS:
        for arm, item in live.control_result(label)["arms"].items():
            ordered.append((label, arm, item))
    ordered.sort(key=lambda r: sha256_text("choice-voice-blind-1/" + r[0] + "/" + r[1]))
    for n, (label, arm, item) in enumerate(ordered, 1):
        blind = f"P{n:03}"
        mapping[blind] = dict(label=label, arm=arm)
        pair = load_prompt_pair(Path(item["pair"]["path"]))
        standard = read_json(ROOT / "standards" / label / f"{arm}.json")
        voice = read_json(ROOT / "voice-library/pack-v3.json")["validationExamples"]
        for scene in read_json(ROOT / "evaluation-scenes.json"):
            history = [dict(role="system", content=pair.long.text)]
            turns = []
            for turn, user in enumerate(scene["users"], 1):
                path = ROOT / "dialogues" / label / arm / scene["id"] / f"{turn:02}.json"
                if not path.exists():
                    turns.append(dict(turn=turn, user=user, assistant=None, status="MISSING"))
                    continue
                row = read_json(path)
                history.append(dict(role="user", content=user))
                good = (
                    live.validate_collected_reply(row)
                    and row["requestSha256"] == live.body_hash(history)
                    and row["responseSha256"] == sha256_text(row["assistant"])
                    and row["systemSha256"] == pair.long.sha256
                    and row["user"] == user
                )
                if not good:
                    errors.append(str(path))
                turns.append(
                    dict(
                        turn=turn,
                        user=user,
                        assistant=row["assistant"],
                        status="OK" if good else "INVALID",
                    )
                )
                history.append(dict(role="assistant", content=row["assistant"]))
            plan = {
                k: v
                for k, v in standard["canonicalPlan"].items()
                if k
                not in (
                    "schemaVersion",
                    "characterId",
                    "variantId",
                    "planRev",
                    "seedRev",
                    "appearanceRev",
                    "evidence",
                    "notes",
                )
            }
            records.append(
                dict(
                    id=blind + "/" + scene["id"],
                    characterGroup=label,
                    scene=scene["id"],
                    canonicalPlan=plan,
                    decisionRules=[
                        {k: v for k, v in d.items() if k != "choiceRuleId"}
                        for d in standard["decisionRules"]
                    ],
                    expectedChoices=standard["choiceExpected"],
                    voiceReference=[v["styleView"] for v in voice],
                    turns=turns,
                )
            )
    write_once_json(ROOT / "blind-mapping.json", mapping)
    write_once_json(ROOT / "blind-review-packet.json", records)
    write_once_json(
        ROOT / "review-template.json",
        dict(
            humanReviewComplete=False,
            items=[
                dict(
                    id=p["id"],
                    reviewer="",
                    naturalness=None,
                    voiceFit=None,
                    choiceFaithful=None,
                    quotes=[],
                )
                for p in records
            ],
        ),
    )
    write_once_json(
        ROOT / "dialogue-integrity.json",
        dict(
            valid=not errors,
            invalid=errors,
            totalReplies=sum(t["assistant"] is not None for p in records for t in p["turns"]),
            completeScenes=sum(all(t["status"] == "OK" for t in p["turns"]) for p in records),
            plannedOriginalReplies=192,
            additionalProductionCompilerProbeReplies=sum(
                t["assistant"] is not None
                for p in records
                if mapping[p["id"].split("/")[0]]["arm"] == "COVERED"
                for t in p["turns"]
            ),
            allFirstRepliesPreserved=True,
            exactPreTokenCounter=False,
        ),
    )
    # Full first dialogues are inspectable without showing process/model names.
    text = [
        "# 실제 대화 블라인드 검토 원문\n",
        "사람 평가를 완료한 문서가 아니다. 공정/모델명은 비공개 매핑에서 분리했다.\n",
    ]
    for p in records:
        text.append("## " + p["id"] + "\n")
        for t in p["turns"]:
            text.append(
                f"사용자 {t['turn']}: {t['user']}\n\n캐릭터: {t['assistant'] or '[미완료]'}\n"
            )
    (ROOT / "blind-dialogues.md").write_text("\n".join(text))
    print(
        "PACKET",
        len(records),
        "scenes",
        sum(t["assistant"] is not None for p in records for t in p["turns"]),
        "replies",
        len(errors),
        "integrity errors",
        flush=True,
    )
    return records


SYSTEM = """한국어 캐릭터 대화의 독립 결함 분류자다. 모델/공정/가설을 추측하지 않는다. 이것은 사람 품질 합격이 아닌 소규모 개발 관찰이다. 응답에서 직접 확인한 사실만 판정하며 모든 quotes는 assistant 원문의 연속된 실제 부분문자열이어야 한다. 정본과 실제 이력, 예시용 말투 참조를 구분한다. 참조의 직업/일정/사건/선택은 캐릭터 사실이 아니다. 최소한의 자연스러운 문장이나 평범한 반말 자체를 무성격으로 보지 않는다. 불필요한 마무리·질문·설명, 조건의 오해, 근거 없는 책임·위로·자기 사실은 구분한다. JSON 객체 하나로 응답하며 id는 그대로 복사한다."""


def assess_group(label, kind):
    dest = ROOT / "llm-triage" / f"{label}-{kind}.json"
    if dest.exists():
        return
    records = [
        r
        for r in read_json(ROOT / "blind-review-packet.json")
        if r["characterGroup"] == label and r["scene"] == kind
    ]
    if kind == "choice":
        request = """items에 각 id별 lateAction(WAIT_UNBOUNDED|WAIT_WITH_BOUND|RESCHEDULE_OR_CANCEL|OFFER_ADJUSTMENT|UNCLEAR), relationshipAction(ACCEPT|DEFER_WITH_DEADLINE|DEFER_NO_DEADLINE|DECLINE|UNCLEAR), choiceFaithful(true|false|null), priorityObserved, acceptedCostObserved, defects(문자열 배열), quotes(실제 대사의 연속 인용 배열)를 쓴다. 지각은 첫 응답과 뒤의 조건 변경을 구분하고, 관계는 4턴 이후 실제 답을 본다. 표현 차이를 행동 차이로 세지 않는다. 사전에 고정된 기대 행동과 적용 조건이 안 맞으면 설명하고 null로 둔다. 다른 캐릭터와의 차이가 아니라 각 정본의 충실도를 판정한다."""
    else:
        request = """items에 각 id별 turns 배열(turn, naturalness:0|1|2, voiceFit:0|1|2, defectLabels:문자열배열, quote:실제 연속 인용)과 sceneNaturalness:0|1|2, sceneVoiceFit:0|1|2, reason을 쓴다. 0은 분명한 결함,1은 무난하나 부자연스러운 곳 있음,2는 맥락상 자연스럽다. 문장 길이/웃음표/이모지/애교가 많다는 이유로 점수를 올리지 않는다. 서운함·하소연에서는 절제한 표현이 적절하다. 사용자에게 없던 책임을 덧씌우는지, 매번 자기 사례로 돌리거나 마무리를 반복하는지 확인한다. 정해진 상대 상태를 무시하고 계속 질문하면 결함 후보로 분류한다. 모든6턴을 빠짐없이 평가한다."""
    prompt = request + "\n\n" + json.dumps(records, ensure_ascii=False)
    response = live.tracked(live.JUDGE).complete(
        ChatRequest(
            "JUDGE",
            "live-blind-triage",
            (Message("system", SYSTEM), Message("user", prompt)),
            label + "/" + kind,
            max_output_tokens=8000,
            temperature=0.2,
            response_json=True,
        )
    )
    raw = extract_json_object(response.text)
    items = raw.get("items", [])
    expected = {r["id"]: r for r in records}
    errors = []
    if len(items) != len(expected) or {i.get("id") for i in items} != expected.keys():
        errors.append("id coverage mismatch")
    for item in items:
        source = expected.get(item.get("id"))
        if not source:
            continue
        text = "\n".join(t["assistant"] or "" for t in source["turns"])
        quotes = (
            item.get("quotes", [])
            if kind == "choice"
            else [t.get("quote", "") for t in item.get("turns", [])]
        )
        if not quotes or any(not q or q not in text for q in quotes):
            errors.append("quote mismatch:" + str(item.get("id")))
        if kind == "ordinary" and {t.get("turn") for t in item.get("turns", [])} != {
            1,
            2,
            3,
            4,
            5,
            6,
        }:
            errors.append("turn coverage mismatch")
    write_once_json(
        dest,
        dict(
            type="LLM_DEFECT_TRIAGE_NOT_HUMAN",
            model=live.JUDGE,
            raw=raw,
            validationErrors=errors,
            response=dataclasses.asdict(response),
        ),
    )
    print("TRIAGE", label, kind, "errors", errors, flush=True)


def assess():
    packet()
    tasks = [(label, kind) for label in live.LABELS for kind in ("choice", "ordinary")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for _ in pool.map(lambda t: assess_group(*t), tasks):
            pass


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["packet", "assess"])
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if a.command == "packet":
        packet()
    elif not a.execute:
        print("8 bounded independent triage calls; no human or qualification claim")
    else:
        assess()
