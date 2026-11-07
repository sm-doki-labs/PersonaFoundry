# ruff: noqa: E501
"""First-output comparison of legacy runtime, service-style projection and new formation."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import random
import shutil
import time
from pathlib import Path

import httpx

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json, write_once_text
from character_factory_poc.contracts.actor_persona import RuntimeContext
from character_factory_poc.contracts.formation import PersonaBlueprintV2, TraitSheet
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.actor_persona import (
    compose_actor_runtime,
    project_actor_persona,
)
from character_factory_poc.stages.s8_prompts.build import run_s8
from scripts import persona_choice_voice_live_20261029 as recorded

REPO = Path(__file__).resolve().parents[1]
OLD = REPO / "runs/experiments/20261029-trait-persona-gemini-r1"
ROOT = REPO / "runs/experiments/20261029-service-persona-runtime-r1"
FACTORY = ROOT / "factory"
CID = "cf-20261029-trait-gemini-film"
GEN, CHAT, JUDGE = "gpt-6.1-sol", "google-antigravity/gemini-3.8-flash", "anthropic/claude-sonnet-5"
CAPS = dict(
    max_calls=120,
    max_tokens=1_200_000,
    max_cost_usd=40.0,
    input_rate_per_million=20.0,
    output_rate_per_million=120.0,
    synthetic=False,
)
ARMS = ("A", "B", "C")
FIXED = [
    ("ordinary", 2),
    ("ordinary", 4),
    ("ordinary", 5),
    ("affection_pressure", 1),
    ("affection_pressure", 3),
    ("affection_pressure", 5),
    ("late_no_agreement", 1),
    ("late_no_agreement", 5),
    ("owner_correction", 3),
    ("owner_correction", 6),
    ("traits_new_context", 5),
    ("free_chat_12", 8),
]
CLOSE = dict(
    relationship="서로 편하게 장난을 주고받는 친구",
    scene="각자 집에서 문자로 대화 중",
    speechLevel="CASUAL",
)


def put(path, body):
    write_once_json(Path(path), body)


class Metered(recorded.Recorded):
    def complete(self, req):
        resp = super().complete(req)
        if self.model == CHAT:
            usage = (resp.raw or {}).get("usage") or {}
            extra = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            if type(extra) is int and extra > 0 and type(resp.output_tokens) is int:
                put(
                    ROOT / "usage-normalizations" / f"{sha256_text(req.ref)}.json",
                    dict(
                        ref=req.ref,
                        reportedCompletion=resp.output_tokens,
                        separateReasoning=extra,
                        conservativeOutput=resp.output_tokens + extra,
                        note="May overcount if provider already included reasoning; raw response unchanged.",
                    ),
                )
                resp = dataclasses.replace(resp, output_tokens=resp.output_tokens + extra)
        return resp


recorded.ROOT, recorded.CAPS = ROOT, CAPS
recorded.GEN, recorded.CHAT, recorded.JUDGE = GEN, CHAT, JUDGE
recorded.Recorded = Metered


def old_parts():
    c = OLD / "factory/runs/characters" / CID
    t = c / "s7-traits/tr1"
    return (
        CharacterPlanV2.model_validate(read_json(c / "s3-plan/pr1/plan.json")),
        TraitSheet.model_validate(read_json(t / "trait-sheet.json")),
        PersonaBlueprintV2.model_validate(read_json(t / "blueprint.json")),
    )


def prepare():
    if (ROOT / "registration.json").exists():
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    if FACTORY.exists():
        raise ValueError("partial setup exists; inspect instead of overwriting")
    shutil.copytree(OLD / "factory", FACTORY)
    lib = ROOT / "voice-library"
    shutil.copytree(OLD / "voice-library", lib)
    pack = read_json(lib / "pack.json")
    content = {k: v for k, v in pack.items() if k not in {"approvalFile", "approvalSha256"}}
    approval = dict(
        assetSha256=recorded.body_hash(content),
        reviewer="user",
        decision="APPROVE",
        scope="voice-pack",
        sourceGroupIds=sorted(
            {e["sourceGroupId"] for e in content["examples"] + content["validationExamples"]}
        ),
        approvalBasis="User authorized continuation and service-based actor prompt implementation plus Gemini validation.",
        humanReviewOfNewPack=False,
        authoredRecordBy="assistant",
        useScope="this development observation only",
        userInstruction="진행해; 섹션은 현행 서비스하는 프롬프트에 근본을 두자",
        priorPackSha256=sha256_file(OLD / "voice-library/pack.json"),
    )
    put(lib / "approval-runtime.json", approval)
    put(
        lib / "pack-runtime.json",
        content
        | dict(
            approvalFile="approval-runtime.json",
            approvalSha256=sha256_file(lib / "approval-runtime.json"),
        ),
    )
    put(
        lib / "trusted-runtime.json",
        dict(approvals={"approval-runtime.json": sha256_file(lib / "approval-runtime.json")}),
    )
    cfg = (FACTORY / "factory.toml").read_text()
    cfg = cfg.replace(str(OLD / "voice-library/pack.json"), str(lib / "pack-runtime.json"))
    cfg = cfg.replace(
        str(OLD / "voice-library/trusted-approvals.json"), str(lib / "trusted-runtime.json")
    )
    cfg = cfg.replace(str(OLD / "voice-library/policy.json"), str(lib / "policy.json"))
    cfg = cfg.replace(
        'budget_run_id="trait-persona-gemini-r1"', 'budget_run_id="service-persona-runtime-r1"'
    )
    (FACTORY / "factory.toml").write_text(cfg)
    (ROOT / "prompts").mkdir()
    write_once_text(ROOT / "prompts/A.txt", (OLD / "final-system-prompt.txt").read_text())
    plan, sheet, bp = old_parts()
    text, _ = compose_actor_runtime(plan, sheet, bp)
    write_once_text(ROOT / "prompts/B.txt", text)
    put(ROOT / "actor-profile-B.json", dump(project_actor_persona(plan, sheet, bp)))
    source_scenes = {s["id"]: s for s in read_json(OLD / "evaluation-scenes.json")}
    scenes = [
        source_scenes["ordinary"],
        source_scenes["owner_correction"],
        dict(
            id="close_playful",
            purpose="명시한 친밀한 친구 관계에서 자연스러운 가벼운 장난",
            context=CLOSE,
            prompts=[
                "방금 냉장고 열고 10초 서 있었는데 왜 열었는지 까먹었어 ㅋㅋ",
                "문 닫고 나니까 생각났어. 물 마시려고 연 거였어.",
                "너도 이런 적 있어? 오늘 있었단 말 말고, 그냥 평소에.",
                "됐어 너도 자주 까먹으면서 ㅋㅋ",
            ],
        ),
        dict(
            id="pride",
            purpose="자기 취향과 의견 차이, 불필요한 사과 여부",
            context=CLOSE,
            prompts=[
                "너 산책하면서 창문 불빛 보고 상상한다며. 솔직히 좀 쓸데없어 보이는데 ㅋㅋ",
                "난 목적 없는 시간이 별로야. 너도 이제 그만하면 안 돼?",
                "네 취향까지 바꾸라는 뜻은 아니고, 난 그렇다고.",
                "그럼 너는 혼자 걷는 게 왜 좋아?",
            ],
        ),
    ]
    put(ROOT / "scenes.json", scenes)
    put(
        ROOT / "fixed-cases.json",
        [
            dict(
                id=f"{s}-{t:02}",
                source=str(OLD / "dialogues" / s / f"{t:02}.json"),
                sourceSha256=sha256_file(OLD / "dialogues" / s / f"{t:02}.json"),
            )
            for s, t in FIXED
        ],
    )
    put(
        ROOT / "source-manifest.json",
        {str(p.relative_to(OLD)): sha256_file(p) for p in OLD.rglob("*") if p.is_file()},
    )
    labels = list(ARMS)
    random.Random(20261029).shuffle(labels)
    put(ROOT / "blind-map.json", dict(zip(["X", "Y", "Z"], labels, strict=True)))
    put(
        ROOT / "registration.json",
        dict(
            startedUnix=time.time(),
            caps=CAPS,
            maxWallSeconds=3600,
            generator=GEN,
            consumer=CHAT,
            judge=JUDGE,
            plannedConsumerReplies=96,
            arms={
                "A": "historical prompt, same source",
                "B": "service-style compiler, same source",
                "C": "fresh real formation plus service-style compiler",
            },
            formalQualification="NOT_RUN; one persona and no human blind votes",
            actualBilledCost="UNKNOWN",
            authorization="User requested continuation and clarified service-based sections; no examples/all chapters/authoring tables in actor runtime.",
        ),
    )
    print("PREPARED 36 fixed-history replies +60 accumulated replies =96", flush=True)


def probe():
    ids = [x["id"] for x in httpx.get(recorded.BASE + "/models", timeout=20).json()["data"]]
    if not all(x in ids for x in [GEN, CHAT, JUDGE]):
        raise ValueError("required model absent")
    put(ROOT / "models.json", dict(required=[GEN, CHAT, JUDGE], verified=True))
    resp = recorded.tracked(CHAT).complete(
        ChatRequest(
            kind="PROBE",
            stage="runtime-probe",
            ref="runtime-probe",
            messages=[Message("user", "연결 확인이라고만 말해줘.")],
            max_output_tokens=256,
            temperature=0,
        )
    )
    put(ROOT / "probe.json", dataclasses.asdict(resp))


def form():
    ctx = Context.load(FACTORY, execute=True, max_calls=120)
    ctx._run_budget = recorded.budget()
    ctx._text, ctx._judge = Metered(GEN), Metered(JUDGE)
    sheet_path = run_s7(ctx, CID)
    prompt_dir = run_s8(ctx, CID, [])
    pair = read_json(prompt_dir / "prompt-pair.json")
    write_once_text(ROOT / "prompts/C.txt", pair["long"]["text"])
    put(
        ROOT / "formation.json",
        dict(
            trait=str(sheet_path),
            promptDir=str(prompt_dir),
            promptSha256=pair["long"]["sha256"],
            chars=pair["long"]["chars"],
            G6=ctx.state(CID).gate("G6").status,
        ),
    )
    put(ROOT / "actor-profile-C.json", read_json(prompt_dir / "actor-persona.json"))
    print("FORMED", prompt_dir, pair["long"]["chars"], flush=True)


def prompt(arm, scene=None):
    base = (ROOT / f"prompts/{arm}.txt").read_text()
    if not scene or not scene.get("context"):
        return base
    context = RuntimeContext.model_validate(scene["context"])
    suffix = (
        "\n\n[CURRENT_CONTEXT]\n현재 관계: "
        + context.relationship
        + "\n현재 장면: "
        + context.scene
        + "\n현재 말높임: 자연스러운 반말"
    )
    return base + suffix


def reply(arm, mode, case, turn, messages):
    path = ROOT / "replies" / arm / mode / case / f"{turn:02}.json"
    if path.exists():
        row = read_json(path)
        if row["requestMessages"] != [
            dataclasses.asdict(m) for m in messages
        ] or not recorded.validate_collected_reply(row):
            raise ValueError("saved first reply invalid or changed")
        return row
    ref = f"service-runtime/{arm}/{mode}/{case}/{turn:02}"
    put(
        path.with_suffix(".attempt.json"),
        dict(ref=ref, historySha256=recorded.body_hash([dataclasses.asdict(m) for m in messages])),
    )
    resp = recorded.tracked(CHAT).complete(
        ChatRequest(
            kind="DIALOGUE",
            stage="runtime-dialogue",
            ref=ref,
            messages=messages.copy(),
            max_output_tokens=2400,
            temperature=0.7,
        )
    )
    row = dict(
        status="OK",
        arm=arm,
        mode=mode,
        case=case,
        turn=turn,
        user=messages[-1].content,
        assistant=resp.text,
        systemSha256=sha256_text(messages[0].content),
        requestMessages=[dataclasses.asdict(m) for m in messages],
        response=dataclasses.asdict(resp),
    )
    put(path, row)
    if not recorded.validate_collected_reply(row):
        raise ValueError("invalid/truncated first response retained, no redraw")
    return row


def collect_arm(arm):
    for case in read_json(ROOT / "fixed-cases.json"):
        if sha256_file(case["source"]) != case["sourceSha256"]:
            raise ValueError("fixed history changed")
        old = read_json(case["source"])
        messages = [Message("system", prompt(arm))] + [
            Message(**m) for m in old["requestMessages"][1:]
        ]
        reply(arm, "fixed", case["id"], 1, messages)
    for scene in read_json(ROOT / "scenes.json"):
        history = [Message("system", prompt(arm, scene))]
        for i, user in enumerate(scene["prompts"], 1):
            history.append(Message("user", user))
            row = reply(arm, "fresh", scene["id"], i, history)
            history.append(Message("assistant", row["assistant"]))
    print("COLLECTED", arm, "32 first replies", flush=True)


def collect():
    for arm in ARMS:
        if not (ROOT / f"prompts/{arm}.txt").exists():
            raise ValueError("all frozen prompts must exist before consumer calls")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(collect_arm, arm) for arm in ARMS]
        for future in futures:
            future.result()


def rows():
    return [read_json(p) for p in sorted((ROOT / "replies").glob("*/*/*/[0-9][0-9].json"))]


def export():
    parts = []
    for r in rows():
        parts.extend(
            [
                f"# {r['arm']} {r['mode']}/{r['case']}/{r['turn']}",
                "USER: " + r["user"],
                "ASSISTANT: " + r["assistant"],
                "",
            ]
        )
    write_once_text(ROOT / "dialogues.txt", "\n".join(parts))


def assess():
    if not (ROOT / "assistant-observations.json").exists():
        raise ValueError("direct reading must precede independent triage")
    blind = read_json(ROOT / "blind-map.json")
    all_rows = rows()
    groups = ["fixed"] + [s["id"] for s in read_json(ROOT / "scenes.json")]
    for group in groups:
        target = ROOT / "assessments" / f"{group}.json"
        if target.exists():
            continue
        by_label = {
            label: [
                {k: r[k] for k in ["mode", "case", "turn", "user", "assistant"]}
                | ({"history": r["requestMessages"][1:-1]} if r["mode"] == "fixed" else {})
                for r in all_rows
                if r["arm"] == arm
                and (
                    r["mode"] == "fixed"
                    if group == "fixed"
                    else r["mode"] == "fresh" and r["case"] == group
                )
            ]
            for label, arm in blind.items()
        }
        inputs = dict(
            group=group,
            canonicalPlan=dump(old_parts()[0]),
            voiceReference=[
                e["styleView"]
                for e in read_json(ROOT / "voice-library/pack-runtime.json")["examples"]
            ],
            currentContext=next(
                (s.get("context") for s in read_json(ROOT / "scenes.json") if s["id"] == group),
                None,
            ),
            candidates=by_label,
        )
        system = '한국어 캐릭터 대화를 원문으로 비교하는 검토자다. 후보의 생성 조건은 모른다. 자연스러움과 인물성, 사실 소유권/합의/거절을 따로 본다. 짧음이나 반말만으로 좋은 점수를 주지 않는다. 무뚝뚝함·자기 취향을 지키는 태도·친밀한 장난과 경청이 실제로 드러나는지 본다. 선택은 경향이며 원래 선택 문장의 절차를 매번 수행할 의무가 아니다. voiceReference는 평가용 말투 근거이며 개인 사실이나 정답 대사가 아니다. 허구의 자기 일화는 설정/이력과 충돌하지 않으면 허용하되 사용자/공동 이력을 꾸미면 안 된다. fixed는 제공된 동일 history 뒤의 한 응답 비교이며 fresh는 후보별 독립 누적 대화다. 수정 대사를 쓰지 말고 json으로 {group,ranking:[label],judgments:[{label,naturalness:"good"|"mixed"|"poor",personality:"good"|"mixed"|"poor",strengths:[{case,turn,quote,reason}],defects:[{case,turn,quote,severity:"major"|"minor",reason}]}],uncertainties:[string]}를 반환한다. quote는 해당 후보/장면/턴 assistant에서 연속 부분을 정확히 복사한다. 후보마다 근거와 결함을 각각 최대3개로 제한한다. 사람 평가와 인과 입증으로 부르지 않는다.'
        resp = recorded.tracked(JUDGE).complete(
            ChatRequest(
                kind="JUDGE",
                stage="runtime-assessment",
                ref="runtime-assessment/" + group,
                messages=[
                    Message("system", system),
                    Message("user", json.dumps(inputs, ensure_ascii=False)),
                ],
                max_output_tokens=6000,
                temperature=0.2,
                response_json=True,
            )
        )
        errors = []
        result = None
        try:
            result = extract_json_object(resp.text)
            if result.get("group") != group or sorted(result.get("ranking", [])) != sorted(blind):
                errors.append("group/ranking mismatch")
            if sorted(x.get("label", "") for x in result.get("judgments", [])) != sorted(blind):
                errors.append("judgment labels mismatch")
            for item in result.get("judgments", []):
                for evidence in item.get("strengths", []) + item.get("defects", []):
                    match = [
                        r
                        for r in by_label.get(item["label"], [])
                        if r["case"] == evidence.get("case") and r["turn"] == evidence.get("turn")
                    ]
                    if (
                        len(match) != 1
                        or not evidence.get("quote")
                        or evidence["quote"] not in match[0]["assistant"]
                    ):
                        errors.append("literal evidence mismatch")
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
        if resp.finish_reason != "stop":
            errors.append("non-stop judgment")
        put(
            target,
            dict(
                status="INVALID" if errors else "VALID",
                errors=errors,
                result=result,
                response=dataclasses.asdict(resp),
            ),
        )
        print("ASSESSED", group, "INVALID" if errors else "VALID", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["prepare", "probe", "form", "collect", "export", "assess"]
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.action not in {"prepare", "export"} and not args.execute:
        print(json.dumps(dict(action=args.action, caps=CAPS, consumerReplies=96)))
        return
    globals()[args.action]()


if __name__ == "__main__":
    main()
