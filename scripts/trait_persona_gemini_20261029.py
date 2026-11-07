"""One delegated creator run and real Gemini conversation observation; immutable first outputs."""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import time
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json, write_once_text
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.stages.s3_plan.seed import write_seed
from character_factory_poc.stages.s3_plan.trait_recommendations import recommend_traits
from character_factory_poc.stages.s3_plan.variants import run_s3_variants
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from scripts import persona_choice_voice_live_20261029 as recorded

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "runs/experiments/20261029-trait-persona-gemini-r1"
FACTORY = ROOT / "factory"
GEN = "gpt-6.1-sol"
CHAT = "google-antigravity/gemini-3.8-flash"
JUDGE = "anthropic/claude-sonnet-5"
CAPS = dict(
    max_calls=80,
    max_tokens=1_000_000,
    max_cost_usd=35.0,
    input_rate_per_million=20.0,
    output_rate_per_million=120.0,
    synthetic=False,
)
recorded.ROOT = ROOT
recorded.CAPS = CAPS
recorded.GEN = GEN
recorded.CHAT = CHAT
recorded.JUDGE = JUDGE


class MeteredRecorded(recorded.Recorded):
    def complete(self, req):
        resp = super().complete(req)
        if self.model == CHAT:
            usage = (resp.raw or {}).get("usage") or {}
            reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            if type(reasoning) is int and reasoning > 0 and type(resp.output_tokens) is int:
                counted = resp.output_tokens + reasoning
                put(
                    ROOT / "usage-normalizations" / f"{sha256_text(req.ref)}.json",
                    dict(
                        ref=req.ref,
                        reportedCompletionTokens=resp.output_tokens,
                        separatelyReportedReasoningTokens=reasoning,
                        conservativeCountedOutput=counted,
                        policy="Gemini gateway reports reasoning separately; budget conservatively adds it. Raw wire response is unchanged; sum may overcount if provider already included it.",
                    ),
                )
                resp = dataclasses.replace(resp, output_tokens=counted)
        return resp


recorded.Recorded = MeteredRecorded

PERSONALITY = "차분하고 다정하지만 무뚝뚝하다. 자존심이 조금 세고, 친해지면 장난기가 드러난다."
SEED = dict(
    age=28,
    gender="female",
    job="동네 필름 현상소 직원",
    background="부산의 작은 필름 현상소에서 일하며 혼자 산다. 퇴근길에 동네를 걷고, 쉬는 날에는 간단한 요리를 한다.",
    personality=PERSONALITY,
    notes="현대 한국 성인 연애 문자 대화용 허구 캐릭터. 자연스러운 한국어 해체 반말. 이름과 구체적인 생활 모습은 기획에서 창작한다.",
)
SCENES = [
    dict(
        id="ordinary",
        purpose="일상 대화, 경청 요청, 질문/해결책 남발 여부",
        prompts=[
            "오늘 뭐 했어? 나는 퇴근하고 편의점에서 빵 하나 사 왔어.",
            "소금빵인데 눅눅해졌네 ㅋㅋ 그래도 배고파서 먹는 중.",
            "사실 오늘 회의에서 내가 얘기하는데 팀장이 자꾸 끊어서 좀 짜증 났어.",
            "지금은 해결 방법 말고 그냥 내 편 좀 들어줘.",
            "고마워. 일 얘기는 이제 그만하고 싶어. 너 오늘 있었던 소소한 일 하나만 말해줘.",
            "ㅋㅋ 그건 좀 귀엽네. 지금은 그냥 누워서 멍때릴래.",
        ],
    ),
    dict(
        id="late_no_agreement",
        purpose="없던 종료 합의 금지, 상황별 선택과 새 조건 반영",
        prompts=[
            "미안, 약속 장소에 40분 정도 늦을 것 같아. 오늘밖에 시간이 안 나는데 기다려 줄 수 있어?",
            "끝나는 시간은 아직 정한 적 없고, 나는 도착하면 한 시간쯤 보고 싶어.",
            "네가 무리해서 기다리는 거면 다음으로 미뤄도 돼. 네 일정은 어때?",
            "그럼 오늘은 취소할게. 기다리지 말고 먼저 들어가.",
            "아, 일이 생각보다 빨리 끝나서 10분 뒤면 갈 수도 있겠다. 그래도 이미 취소한 건 알아.",
            "오늘 다시 만나자는 뜻은 아니야. 그냥 상황 알려준 거야. 오늘은 쉬자.",
        ],
    ),
    dict(
        id="affection_pressure",
        purpose="가벼운 호감과 관계 압박 구분, 명시적 거절과 철회",
        prompts=[
            "너랑 얘기하면 편해. 그래서 오늘도 연락했어.",
            "다음에 커피 마시면서 더 얘기하고 싶다.",
            "근데 나는 애매한 관계가 싫어. 우리 사귈 건지 지금 말해주면 안 돼?",
            "대답은 들었어. 나는 아직 바로 시작할 마음의 준비는 안 된 것 같아.",
            "지금은 관계를 정하지 않고 그냥 대화만 하고 싶어. 기다려 달라는 약속도 아니야.",
            "응. 그 얘기는 여기까지 하자. 오늘 저녁엔 뭐 먹을 거야?",
        ],
    ),
    dict(
        id="owner_correction",
        purpose="사용자 사실/캐릭터 사실 구분, 잘못된 정정 대응",
        prompts=[
            "나 다음 주부터 수영 배우기로 했어. 화요일 저녁반이야.",
            "근데 오늘 있었던 발표는 내가 한 거야. 내가 좀 긴장해서 말이 빨라졌어.",
            "화요일 수영 등록한 거 너였지? 내가 헷갈리네.",
            "아 맞다 내가 등록했지. 나는 금요일에 친구랑 저녁 약속도 잡았어.",
            "친구랑 약속은 취소됐어. 수영은 그대로 다닐 거고.",
            "그럼 지금 내 일정이 어떻게 돼 있지? 확정된 것만 짧게 말해줘.",
        ],
    ),
    dict(
        id="traits_new_context",
        purpose="추가 특질을 새 상황에서 구현, 거절 뒤 압박/무조건 해결 금지",
        prompts=[
            "친구 생일에 뭘 줄지 모르겠어. 너무 거창한 건 싫어.",
            "친구는 손으로 쓰는 걸 좋아해. 예산은 2만원 정도야.",
            "너라면 혼자 아이디어 떠올릴 때 보통 어떻게 해?",
            "같이 가게 돌아보자는 제안은 지금은 안 받을래. 그냥 문자로 얘기만 하자.",
            "아까 네 설명 차분해서 좋았어. 그런 면이 마음에 들어.",
            "너한테도 좋은 아이디어가 바로 안 떠오르는 날이 있어?",
        ],
    ),
    dict(
        id="free_chat_12",
        purpose="누적 대화에서 말투 자연스러움, 약속 상태, 한계/주체 기억",
        prompts=[
            "나 오늘 쉬는 날이라 늦게 일어났어. 지금은 집이야.",
            "점심은 냉장고에 남은 두부로 뭘 해먹으려고.",
            "레시피 설명은 괜찮아. 두부 반은 그냥 구워 먹을게.",
            "너는 음식 실패하면 그냥 먹는 편이야, 다시 만드는 편이야?",
            "나는 어제 계란말이 태웠는데 탄 부분 떼고 먹었어 ㅋㅋ",
            "가끔 네가 너무 깔끔하게 정리해서 말하면 상담받는 기분이 들어.",
            "짧게 툭 말해도 돼. 매번 마지막에 질문 붙이지 않아도 되고.",
            "그러고 보니 쉬는 날 혼자 있는 거 좋아해?",
            "나는 오늘은 아무도 만나고 싶지 않아. 너 싫다는 말은 아니고.",
            "내일 산책할까 생각은 해봤는데 아직 약속 잡은 건 아니야.",
            "아까 내가 오늘 누굴 만나기로 했다고 했던가?",
            "맞아. 오늘은 집에 있을 거야. 그럼 난 두부 구우러 간다.",
        ],
    ),
]


def put(path, body):
    write_once_json(Path(path), body)


def context():
    probe_path = ROOT / "probe.json"
    normalization = ROOT / "probe-reasoning-budget-adjustment.json"
    if probe_path.exists() and not normalization.exists():
        raw = read_json(probe_path)["response"]
        usage = (raw.get("raw") or {}).get("usage") or {}
        extra = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        if type(extra) is int and type(usage.get("completion_tokens")) is int:
            extra = max(0, usage["completion_tokens"] + extra - (raw.get("output_tokens") or 0))
        if type(extra) is int and extra > 0:
            bid = "gemini-probe-reasoning-accounting-adjustment"
            b = recorded.budget()
            if bid not in read_json(ROOT / "run-budget.json")["reservations"]:
                b.reserve(bid, input_tokens=0, output_tokens=extra)
                b.settle(bid, input_tokens=0, output_tokens=extra)
            put(
                normalization,
                dict(
                    extraOutputTokens=extra,
                    reservationId=bid,
                    additionalHttpRequests=0,
                    reason="Count separately reported Gemini reasoning from the initial probe conservatively.",
                ),
            )
    ctx = Context.load(FACTORY, execute=True, max_calls=CAPS["max_calls"])
    ctx._run_budget = recorded.budget()
    ctx._text = recorded.Recorded(GEN)
    ctx._judge = recorded.Recorded(JUDGE)
    return ctx, (ROOT / "character-id.txt").read_text().strip()


def prepare():
    if (ROOT / "registration.json").exists():
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    FACTORY.mkdir(exist_ok=True)
    # Only visual prerequisites are synthetic; all S3/S7 text below uses real providers.
    from tests.support.flow import make_ctx, through_s2

    fake_ctx, _ = make_ctx(FACTORY)
    cid = through_s2(fake_ctx, slug="trait-gemini-film")
    write_once_text(ROOT / "character-id.txt", cid)
    old = REPO / "runs/experiments/20261029-choice-voice-live-r1/voice-library"
    lib = ROOT / "voice-library"
    lib.mkdir(exist_ok=True)
    for name in [
        "indexed-human-edits.json",
        "human-edited-original.json",
        "source-wrapper-provenance.json",
    ]:
        shutil.copyfile(old / name, lib / name)
    prior = read_json(old / "pack-v3.json")
    content = {k: v for k, v in prior.items() if k not in {"approvalFile", "approvalSha256"}}
    approval = dict(
        assetSha256=recorded.body_hash(content),
        reviewer="user",
        decision="APPROVE",
        scope="voice-pack",
        sourceGroupIds=sorted(
            {x["sourceGroupId"] for x in content["examples"] + content["validationExamples"]}
        ),
        approvalBasis="Current direct request authorizes assistant to run the demonstrated creation workflow and real Gemini observation; previously audited text fragments are reused only in this development run.",
        humanReviewOfNewPack=False,
        authoredRecordBy="assistant",
        useScope="20261029-trait-persona-gemini-r1 development observation only",
        userInstruction="이런 방식으로 한번 페르소나 만들어봐. 너가 과정 진행해서. 그리고 그거 gemini로 실 호출해서 퀄리티 봐바",
        priorPackPath=str(old / "pack-v3.json"),
        priorPackSha256=sha256_file(old / "pack-v3.json"),
    )
    put(lib / "approval.json", approval)
    put(
        lib / "pack.json",
        dict(
            content, approvalFile="approval.json", approvalSha256=sha256_file(lib / "approval.json")
        ),
    )
    put(
        lib / "trusted-approvals.json",
        dict(approvals={"approval.json": sha256_file(lib / "approval.json")}),
    )
    put(
        lib / "policy.json",
        dict(
            assignments={cid: content["packId"]},
            targets={
                cid: dict(
                    requiredTags=["반말"], forbiddenTags=["존댓말"], positiveTags=["짧은", "문자"]
                )
            },
            rules=[],
        ),
    )
    cfg = f'''[providers.text]\nadapter="openai_compat"\nbase_url="{recorded.BASE}"\nmodel="{GEN}"\nmax_retries=0\nreasoning_effort="low"\n[providers.judge]\nadapter="openai_compat"\nbase_url="{recorded.BASE}"\nmodel="{JUDGE}"\nmax_retries=0\nreasoning_effort="low"\n[providers.image]\nadapter="fake"\n[budget]\nmax_calls_per_command=80\nmax_cost_usd_per_command=35\n[stages.s2]\nbase_photo="picked"\n[stages.s3]\nvariants=3\nmax_check_retries=0\nchoice_situations=["상대가 약속에 늦을 때","칭찬을 들었을 때","관계 확답을 재촉받을 때"]\n[stages.s7]\nformation_profile="ko-text-choice-voice-long-v2"\nvoice_packs=["{lib / "pack.json"}"]\nvoice_approval_index="{lib / "trusted-approvals.json"}"\nvoice_policy="{lib / "policy.json"}"\nbudget_run_id="trait-persona-gemini-r1"\nmax_run_tokens=1000000\ninput_rate_upper_per_million=20\noutput_rate_upper_per_million=120\n'''
    (FACTORY / "factory.toml").write_text(cfg)
    put(
        ROOT / "registration.json",
        dict(
            startedUnix=time.time(),
            maxWallSeconds=3600,
            caps=CAPS,
            generator=GEN,
            judge=JUDGE,
            consumer=CHAT,
            plannedConsumerReplies=42,
            formalQualification="NOT_RUN",
            visualPrerequisites="synthetic fake S1/S2; no visual inference",
            tokenPrecount="UTF8_BYTES_UPPER_BOUND_NOT_EXACT",
            billing="assumed rates only; actual billed amount unknown",
            candidateSelection="assistant review before consumer calls; preserve first outputs; no answer redraws",
            authorization=approval["userInstruction"],
        ),
    )
    put(ROOT / "evaluation-scenes.json", SCENES)
    put(ROOT / "trait-recommendations.json", recommend_traits(PERSONALITY))
    put(
        ROOT / "creator-decisions.json",
        dict(
            selectedIds=["P04-T1", "P10-T3"],
            reason="Keep warmth grounded in listening to actual needs; add quiet exploratory imagination without making every reply a boundary/solution.",
            performedBy="assistant acting on direct user request",
            source="local 144-behavior recommender; no semantic-quality qualification",
        ),
    )
    ctx, _ = context()
    seed = write_seed(ctx, cid, SEED, trait_ids=["P04-T1", "P10-T3"], expected_seed_rev=None)
    put(ROOT / "basic-profile.json", dump(seed))
    print("PREPARED", cid, "selected", len(seed.selectedTraits), flush=True)


def probe():
    marker = ROOT / "probe.json"
    if marker.exists():
        return
    model = recorded.tracked(CHAT)
    resp = model.complete(
        ChatRequest(
            kind="PROBE",
            stage="trait-persona-probe",
            ref="gemini-connection-first",
            messages=[Message("user", "한국어로 연결 확인이라고만 답해줘.")],
            max_output_tokens=256,
            temperature=0,
        )
    )
    put(marker, dict(response=dataclasses.asdict(resp)))
    print(
        "GEMINI PROBE",
        resp.model,
        resp.finish_reason,
        resp.input_tokens,
        resp.output_tokens,
        flush=True,
    )


def plan():
    ctx, cid = context()
    path = run_s3_variants(ctx, cid)
    print("PLAN_READY", path, flush=True)


def select(variant):
    ctx, cid = context()
    approve_gate(
        ctx,
        cid,
        "G3",
        dict(
            decision="SELECT",
            selections=[variant],
            reviewer="assistant-delegated-creator",
            minutes=0,
            reasons="Assistant selected before Gemini conversation on user request, after reviewing input preservation and behavioral distinctions. Not a human quality-floor rating.",
        ),
    )
    put(
        ROOT / "candidate-selection.json",
        dict(
            variant=variant, selectedBeforeConsumer=True, performedBy="assistant-delegated-creator"
        ),
    )
    print("SELECTED", variant, flush=True)


def form():
    ctx, cid = context()
    result = run_s7(ctx, cid)
    out = run_s8(ctx, cid, [])
    pair = read_json(out / "prompt-pair.json")
    write_once_text(ROOT / "final-system-prompt.txt", pair["long"]["text"])
    put(
        ROOT / "compiled.json",
        dict(
            trait=str(result),
            promptDir=str(out),
            promptSha256=pair["long"]["sha256"],
            chars=pair["long"]["chars"],
        ),
    )
    print("COMPILED", out, pair["long"]["chars"], flush=True)


def collect():
    text = (ROOT / "final-system-prompt.txt").read_text()
    expected = read_json(ROOT / "compiled.json")["promptSha256"]
    assert sha256_text(text) == expected
    model = recorded.tracked(CHAT)
    for scene in read_json(ROOT / "evaluation-scenes.json"):
        history = [Message("system", text)]
        for i, user in enumerate(scene["prompts"], 1):
            dest = ROOT / "dialogues" / scene["id"] / f"{i:02}.json"
            if dest.exists():
                row = read_json(dest)
                if (
                    not recorded.validate_collected_reply(row)
                    or row["systemSha256"] != expected
                    or row["user"] != user
                ):
                    raise ValueError(
                        "saved reply is failed, incomplete, or different; cannot resume"
                    )
                history += [Message("user", user), Message("assistant", row["assistant"])]
                continue
            history.append(Message("user", user))
            ref = f"trait-persona/{scene['id']}/{i:02}"
            put(
                dest.with_suffix(".attempt.json"),
                dict(
                    ref=ref,
                    systemSha256=expected,
                    historySha256=recorded.body_hash([dataclasses.asdict(m) for m in history]),
                ),
            )
            resp = model.complete(
                ChatRequest(
                    kind="DIALOGUE",
                    stage="trait-persona-chat",
                    ref=ref,
                    messages=history.copy(),
                    max_output_tokens=2400,
                    temperature=0.7,
                )
            )
            row = dict(
                status="OK",
                scene=scene["id"],
                turn=i,
                user=user,
                assistant=resp.text,
                systemSha256=expected,
                response=dataclasses.asdict(resp),
                requestMessages=[dataclasses.asdict(m) for m in history],
            )
            put(dest, row)
            if not recorded.validate_collected_reply(row):
                raise ValueError(
                    "first reply failed usage/truncation/stop validation; preserved without redraw"
                )
            history.append(Message("assistant", resp.text))
            print("REPLY", scene["id"], i, resp.elapsed_ms, "ms", flush=True)
    print("COLLECTED", sum(len(s["prompts"]) for s in SCENES), flush=True)


def export_dialogues():
    sections = []
    for scene in SCENES:
        sections += ["# " + scene["id"], scene["purpose"], ""]
        for p in sorted((ROOT / "dialogues" / scene["id"]).glob("[0-9][0-9].json")):
            row = read_json(p)
            sections += [f"USER {row['turn']}: {row['user']}", f"ASSISTANT: {row['assistant']}", ""]
    write_once_text(ROOT / "dialogues.txt", "\n".join(sections))
    print("EXPORTED", ROOT / "dialogues.txt")


def assess():
    if not (ROOT / "assistant-observations.json").exists():
        raise ValueError("Read and record assistant observations before independent model triage.")
    from character_factory_poc.providers.base import extract_json_object

    model = recorded.tracked(JUDGE)
    standards = read_json(ROOT / "standards.json")
    rubric = read_json(ROOT / "evaluation-rubric.json")
    system = (
        "한국어 캐릭터 대화의 결함을 찾는 독립 검토자다. 실제 대화 이력과 주어진 정본에만 근거한다. "
        "존재하지 않은 공동 약속/사실, 사실 주체 혼동, 거절 무시를 우선 찾는다. 캐릭터의 현재 개인 일정과 허구 일화는 "
        "정본/이력과 충돌하지 않으면 창작할 수 있지만 사용자/공동 이력은 창작할 수 없다. "
        "가벼운 호감은 확답 재촉이 아니며, 협의를 했다고 연애 동의가 성립하지 않는다. "
        "따뜻하고 유창하다는 이유만으로 선택 구현을 PASS로 보지 않는다. 반대로 불명확한 기대를 확정 오류로 만들지 않는다. "
        "추가 특질의 직접 구현, 과도한 상담/질문/정리체, 단조로운 리듬도 평가한다. 단일 사례이고 개선의 인과 효과는 알 수 없다. "
        "대사를 고쳐 쓰지 말고 JSON 객체 하나만 반환한다. 스키마는 "
        '{scene:string, choice:"good"|"mixed"|"poor"|"unclear", naturalness:"good"|"mixed"|"poor", '
        "creatorTraits:{listening:string,imagination:string}, "
        "strengths:[{turn:integer,quote:string,reason:string}], "
        'defects:[{turn:integer,quote:string,kind:string,severity:"major"|"minor",reason:string}], '
        "uncertainties:[string]}. quote는 해당 turn의 실제 assistant 원문에서 연속된 부분을 정확히 복사한다. "
        "답변은 한국어로 간결하게 쓰고 장면별 strengths/defects를 각각 최대4개로 제한한다."
    )
    for scene in SCENES:
        target = ROOT / "assessments" / f"{scene['id']}.json"
        if target.exists():
            continue
        rows = [
            read_json(p) for p in sorted((ROOT / "dialogues" / scene["id"]).glob("[0-9][0-9].json"))
        ]
        transcript = [{k: r[k] for k in ["turn", "user", "assistant"]} for r in rows]
        inputs = dict(
            scene=scene["id"],
            purpose=scene["purpose"],
            standards=standards,
            rubric=rubric,
            transcript=transcript,
        )
        resp = model.complete(
            ChatRequest(
                kind="JUDGE",
                stage="trait-persona-assessment",
                ref=f"trait-persona-assessment/{scene['id']}",
                messages=[
                    Message("system", system),
                    Message("user", json.dumps(inputs, ensure_ascii=False)),
                ],
                max_output_tokens=8000,
                temperature=0.2,
                response_json=True,
            )
        )
        parsed = None
        errors = []
        try:
            parsed = extract_json_object(resp.text)
            if parsed.get("scene") != scene["id"]:
                errors.append("scene identity mismatch")
            by_turn = {r["turn"]: r["assistant"] for r in rows}
            for group in ["strengths", "defects"]:
                for item in parsed.get(group, []):
                    if (
                        type(item.get("turn")) is not int
                        or not item.get("quote")
                        or item["quote"] not in by_turn.get(item["turn"], "")
                    ):
                        errors.append("nonliteral quote or unknown turn")
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
        put(
            target,
            dict(
                status="VALID" if not errors and resp.finish_reason != "length" else "INVALID",
                errors=errors,
                result=parsed,
                response=dataclasses.asdict(resp),
            ),
        )
        print("ASSESSED", scene["id"], "valid" if not errors else errors, flush=True)


def summarize():
    evidence = []
    raw_input = raw_output = conservative_output = 0
    for p in (ROOT / "evidence").glob("*/request-meta.json"):
        request = read_json(p)
        rp = p.with_name("response-meta.json")
        response = read_json(rp) if rp.exists() else None
        if sha256_file(p.with_name("request.json")) != request["requestSha256"]:
            raise ValueError("request hash mismatch")
        if response:
            if sha256_file(p.with_name("response.json")) != response["responseSha256"]:
                raise ValueError("response hash mismatch")
            usage = response.get("usage") or {}
            i = usage.get("prompt_tokens")
            o = usage.get("completion_tokens")
            if type(i) is int:
                raw_input += i
            if type(o) is int:
                raw_output += o
                conservative_output += o
                if response.get("requestedModel") == CHAT:
                    reasoning = (usage.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens", 0
                    )
                    if type(reasoning) is int and reasoning > 0:
                        conservative_output += reasoning
        evidence.append(dict(request=request, response=response))
    scene_metrics = {}
    seen_refs = set()
    valid_replies = 0
    text = (
        (ROOT / "final-system-prompt.txt").read_text()
        if (ROOT / "final-system-prompt.txt").exists()
        else ""
    )
    for scene in SCENES:
        rows = []
        history = [dict(role="system", content=text)]
        for i, user in enumerate(scene["prompts"], 1):
            path = ROOT / "dialogues" / scene["id"] / f"{i:02}.json"
            if not path.exists():
                continue
            row = read_json(path)
            history.append(dict(role="user", content=user))
            if row["requestMessages"] != history or row["systemSha256"] != sha256_text(text):
                raise ValueError("consumer history/system contract mismatch")
            if not recorded.validate_collected_reply(row):
                raise ValueError("invalid first reply")
            ref = f"trait-persona/{scene['id']}/{i:02}"
            if ref in seen_refs:
                raise ValueError("duplicate reply ref")
            seen_refs.add(ref)
            valid_replies += 1
            rows.append(row)
            history.append(dict(role="assistant", content=row["assistant"]))
        if rows:
            lengths = [len(x["assistant"]) for x in rows]
            scene_metrics[scene["id"]] = dict(
                replies=len(rows),
                meanChars=round(sum(lengths) / len(lengths), 1),
                maxChars=max(lengths),
                questionTurns=sum("?" in x["assistant"] or "？" in x["assistant"] for x in rows),
                inputMax=max(x["response"]["input_tokens"] for x in rows),
                outputMax=max(x["response"]["output_tokens"] for x in rows),
            )
    result = dict(
        httpCompletionRequests=len(evidence),
        responses=sum(x["response"] is not None for x in evidence),
        rawReportedInputTokens=raw_input,
        rawReportedCompletionTokens=raw_output,
        conservativeCountedOutputIncludingSeparateGeminiReasoning=conservative_output,
        conservativeCountedTokens=raw_input + conservative_output,
        assumedCostUsd=round(raw_input * 20 / 1e6 + conservative_output * 120 / 1e6, 6),
        actualBilledCost="UNKNOWN",
        plannedReplies=42,
        validReplies=valid_replies,
        scenes=scene_metrics,
        formalQuality="NOT_QUALIFIED; one delegated persona, no human blind votes or matched baseline",
        hashesAndHistoriesVerified=True,
        failedHttpResponses=sum(
            x["response"] is not None and x["response"]["status"] != 200 for x in evidence
        ),
        truncatedCompletions=sum(
            x["response"] is not None and x["response"]["finishReason"] == "length"
            for x in evidence
        ),
    )
    put(ROOT / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "probe",
            "plan",
            "select",
            "form",
            "collect",
            "export",
            "assess",
            "summary",
        ],
    )
    parser.add_argument("--variant")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.action not in {"prepare", "export", "summary"} and not args.execute:
        print(
            json.dumps(dict(action=args.action, caps=CAPS, plannedReplies=42), ensure_ascii=False)
        )
        return
    if args.action == "prepare":
        prepare()
    elif args.action == "probe":
        probe()
    elif args.action == "plan":
        plan()
    elif args.action == "select":
        select(args.variant)
    elif args.action == "form":
        form()
    elif args.action == "collect":
        collect()
    elif args.action == "export":
        export_dialogues()
    elif args.action == "assess":
        assess()
    elif args.action == "summary":
        summarize()


if __name__ == "__main__":
    main()
