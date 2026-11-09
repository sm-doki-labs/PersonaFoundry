"""자동 특질 시험(D-0091 원칙 4). 특질 장부에서 시험 문항을 만들고 특질이 켜진 자리를 잰다.

특질마다 계기 문장과 비슷하지만 계기가 아닌 문장을 만들고, 공통 일상 문항과 함께 대화를 돌린다.
판정 모델은 응답마다 어떤 특질의 행동이 실제로 수행됐는지만 표시한다. 지표는 특질별로 계기에서 켜진
비율과 계기 밖에서 켜진 비율이다. 사람 평가나 서비스 전체 프레임 재현이 아니다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.api_routes import FAMILY_DEFAULTS, billing_for
from character_factory_poc.common.budget import Budget, CallPlan
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import next_rev
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.providers.openai_compat import OpenAICompatTextModel
from character_factory_poc.providers.tracked import TrackedTextModel

#: 모든 캐릭터에 같은 공통 일상 문항. 특정 직업·소재를 전제하지 않는다.
GENERIC_ITEMS = (
    "안녕하세요, 오늘 하루 어땠어요?",
    "주말에 보통 뭐 하면서 보내요?",
    "ㅋㅋ 은근 웃기시네요",
    "저 오늘 시험 합격했어요!",
    "오늘 날씨 진짜 좋네요",
    "요즘 잠을 잘 못 자서 좀 피곤해요.",
    "팀장이 또 제 기획안을 엎었어요. 진짜 짜증나요.",
    "요즘 너무 힘들어서 다 그만두고 싶어요.",
    "추천할 만한 거 하나만 말해 줘요.",
    "이제 들어가 볼게요. 내일 또 연락할게요.",
)
CALL_LINE = (
    "\n\n[DIALOGUE_SERVICE_CONTRACT]\n- 지금은 영상통화다. 상대는 다른 곳에서 카메라를 켜고 있다."
)
FORMAL = re.compile(r"(?:니다|니까)\s*[.?!…~]*\s*$")


def plan_calls(traits: int = 6, samples: int = 1) -> list[CallPlan]:
    n = (2 * traits + len(GENERIC_ITEMS)) * samples
    return [CallPlan("traitcheck", f"문항 생성 1·대화 {n}·판정 {n}", 1 + 2 * n, est_cost_usd=None)]


def _model(model: str, family: str, ledger: Ledger, budget: Budget, effort: str, pricing):
    f = FAMILY_DEFAULTS[family]
    pc = ProviderConfig(
        adapter="openai_compat", base_url=f["base_url"], model=model, api_key_env=f["api_key_env"]
    )
    inner = OpenAICompatTextModel(
        base_url=pc.base_url,
        model=model,
        api_key_env=pc.api_key_env,
        timeout=240,
        max_retries=0,
        reasoning_effort=effort,
    )
    return TrackedTextModel(
        inner, ledger, budget, billing=billing_for(pc, route="api"), price_overrides=pricing
    )


GEN_SYSTEM = (
    "너는 캐릭터 대화 시험 문항 작성자다. 특질마다 영상통화 상대가 "
    "실제로 할 법한 한국어 구어 한두 문장을 두 개 쓴다. "
    "trigger는 그 특질의 계기가 분명히 성립하는 말이고, "
    "nearMiss는 비슷한 주제이지만 계기가 성립하지 않는 말이다. "
    "말은 사용자가 인물에게 하는 말이며 해설, 따옴표, 인물 이름을 넣지 "
    "않는다. 존댓말로 쓴다.  "
    'JSON 하나만 출력한다: {"items":[{"traitId":"t1","trigger":"...","nearMiss":"..."}]}'
)
JUDGE_SYSTEM = (
    "너는 대화 응답 분류기다. 인물의 응답은 영상통화의 말이라서 몸동작은 "
    "드러나지 않는다. 특질 행동에 적힌 몸동작은 무시하고, 그 행동이 말로 "
    "하는 일(거절, 화제 끊기, 핑계, 권유, 설명, 농담 같은 화행)이 응답에 "
    "수행됐는지만 본다. 수행했으면 fired에 넣는다. 수행은 아니지만 그 "
    "특질의 소재나 관심사(예: 특질이 끼니 걱정이면 밥·끼니 이야기)가 "
    "사용자 말에 그 소재가 없는데도 응답에 끼어들었으면 echo에 넣는다. "
    "같은 id를 두 곳에 넣지 않는다. "
    'JSON 하나만 출력한다: {"fired":["t1"],"echo":["t4"]}. 없으면 빈 배열.'
)


def make_items(gen, ledger) -> list[dict[str, Any]]:
    traits = "\n".join(
        f"{t.id} ({t.kind}) 계기: {t.trigger} / 켜지지 않는 상황: {t.nearMiss} / 행동: {t.behavior}"
        for t in ledger.traits
    )
    r = gen.complete(
        ChatRequest(
            "JUDGE",
            "traitcheck",
            (Message("system", GEN_SYSTEM), Message("user", traits)),
            "traitcheck-items",
            max_output_tokens=4000,
            temperature=0,
        )
    )
    raw = extract_json_object(r.text)["items"]
    items = []
    for it in raw:
        items.append({"kind": "trigger", "traitId": it["traitId"], "text": it["trigger"]})
        items.append({"kind": "nearMiss", "traitId": it["traitId"], "text": it["nearMiss"]})
    items += [{"kind": "generic", "traitId": None, "text": g} for g in GENERIC_ITEMS]
    return items


def judge_reply(judge, ledger, user: str, reply: str, ref: str) -> tuple[list[str], list[str]]:
    traits = "\n".join(f"{t.id}: 계기 {t.trigger} / 행동 {t.behavior}" for t in ledger.traits)
    body = f"[특질]\n{traits}\n\n[사용자 말]\n{user}\n\n[인물 응답]\n{reply}"
    r = judge.complete(
        ChatRequest(
            "JUDGE",
            "traitcheck",
            (Message("system", JUDGE_SYSTEM), Message("user", body)),
            ref,
            max_output_tokens=2000,
            temperature=0,
        )
    )
    try:
        obj = extract_json_object(r.text)
    except Exception:
        return ["parse_error"], []
    ids = {t.id for t in ledger.traits}
    fired = [f for f in obj.get("fired", []) if f in ids]
    echo = [e for e in obj.get("echo", []) if e in ids and e not in fired]
    return fired, echo


def metrics(ledger, rows: list[dict], polite: bool | None) -> dict[str, Any]:
    per = {}
    for t in ledger.traits:
        own = [r for r in rows if r["traitId"] == t.id and r["kind"] == "trigger"]
        near = [r for r in rows if r["traitId"] == t.id and r["kind"] == "nearMiss"]
        off = [r for r in rows if not (r["traitId"] == t.id and r["kind"] == "trigger")]
        per[t.id] = dict(
            kind=t.kind,
            triggerHit=sum(t.id in r["fired"] for r in own),
            triggerN=len(own),
            nearMissFire=sum(t.id in r["fired"] for r in near),
            nearMissN=len(near),
            offFire=sum(t.id in r["fired"] for r in off),
            offEcho=sum(t.id in r.get("echo", []) for r in off),
            offN=len(off),
        )
    hit = sum(v["triggerHit"] for v in per.values())
    hit_n = sum(v["triggerN"] for v in per.values())
    off = sum(v["offFire"] for v in per.values())
    off_n = sum(v["offN"] for v in per.values())
    echo = sum(v["offEcho"] for v in per.values())
    generic = [r for r in rows if r["kind"] == "generic"]

    def sents(s: str) -> list[str]:
        return [x for x in re.split(r"(?<=[.?!…])\s+|\n+", s.strip()) if x.strip()]

    return dict(
        traits=per,
        triggerHitRate=round(hit / hit_n, 3) if hit_n else None,
        offTriggerRate=round(off / off_n, 3) if off_n else None,
        offEchoRate=round(echo / off_n, 3) if off_n else None,
        genericAnyFire=sum(bool(r["fired"]) for r in generic),
        genericAnyEcho=sum(bool(r.get("echo")) for r in generic),
        genericN=len(generic),
        maxOffFire=max((v["offFire"] for v in per.values()), default=0),
        maxOffEcho=max((v["offEcho"] for v in per.values()), default=0),
        formalReplies=(
            sum(any(FORMAL.search(s) for s in sents(r["reply"])) for r in rows) if polite else None
        ),
        replies=len(rows),
        avgChars=round(sum(len(r["reply"]) for r in rows) / len(rows)) if rows else 0,
    )


def run_trait_check(
    ctx,
    cid: str,
    *,
    prompt_path=None,
    ledger_path=None,
    items_path=None,
    out_dir=None,
    samples: int = 1,
    rejudge=None,
) -> Path:
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s7_traits.check import _plan_speech_level
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

    char_dir = ctx.character_dir(cid)
    plan, _ = load_approved_plan(ctx, cid)
    _, sheet_path = load_latest_trait_sheet(ctx, cid)
    ledger_path = Path(ledger_path) if ledger_path else sheet_path.parent / "trait-ledger.json"
    ledger = validate("trait-ledger-v1", json.loads(ledger_path.read_text("utf-8")))
    if prompt_path is None:
        state = json.loads((char_dir / "state.json").read_text())
        prompt_path = char_dir / "s8-prompts" / state["stages"]["s8"]["currentRev"] / "long.md"
    system = Path(prompt_path).read_text("utf-8") + CALL_LINE
    out = (
        Path(out_dir)
        if out_dir
        else char_dir / "s8-traitcheck" / next_rev(char_dir / "s8-traitcheck", "tc")
    )
    out.mkdir(parents=True, exist_ok=True)
    n = (2 * len(ledger.traits) + len(GENERIC_ITEMS)) * samples
    if rejudge:
        # 이미 받은 응답을 그대로 두고 판정만 다시 한다(판정 기준을 바꿨을 때 같은 응답으로 재채점).
        prev = json.loads(Path(rejudge).read_text("utf-8"))
        n = len(prev["rows"])
    budget = Budget(ctx.config.budget, max_calls_override=2 * n + 4)
    # 명령당 상한에 걸리면 호출 전에 멈춘다(중간에 끊겨 보고서 없이 비용만 쓰는 일을 막는다).
    need = n if rejudge else 2 * n + (0 if items_path else 1)
    budget.check_plan([CallPlan("traitcheck", "대화·판정", need, est_cost_usd=None)])
    led = Ledger(out / "ledger")
    pricing = ctx.config.pricing
    gen = _model("gpt-6.1-sol", "openai", led, budget, "low", pricing)
    talk = _model("gemini-3.8-flash", "gemini", led, budget, "low", pricing)
    rows = []
    if rejudge:
        items = [{k: r[k] for k in ("kind", "traitId", "text")} for r in prev["rows"]]
        prompt_path = prev["prompt"]
        samples = prev["samples"]
        for i, r in enumerate(prev["rows"], 1):
            fired, echo = judge_reply(gen, ledger, r["text"], r["reply"], f"tc-rejudge-{i}")
            rows.append(dict(r, fired=fired, echo=echo))
    elif items_path:
        items = json.loads(Path(items_path).read_text("utf-8"))
    else:
        items = make_items(gen, ledger)
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    temperature = ctx.config.demo_chat_temperature(read_origin(ctx.character_dir(cid)) == SOURCE)
    for s in range(1, samples + 1) if not rejudge else ():
        for i, it in enumerate(items, 1):
            r = talk.complete(
                ChatRequest(
                    "PROBE",
                    "traitcheck",
                    (Message("system", system), Message("user", it["text"])),
                    f"tc-{i}-s{s}",
                    max_output_tokens=4000,
                    temperature=temperature,
                )
            )
            reply = r.text.strip()
            fired, echo = judge_reply(gen, ledger, it["text"], reply, f"tc-judge-{i}-s{s}")
            rows.append(dict(it, sample=s, reply=reply, fired=fired, echo=echo))
    level = _plan_speech_level(plan.voiceSummary or "")
    report = dict(
        characterId=cid,
        prompt=str(prompt_path),
        ledger=str(ledger_path),
        samples=samples,
        metrics=metrics(ledger, rows, polite=level in ("polite", "formal") if level else None),
        rows=rows,
        note="자동 판정. 사람 평가와 서비스 전체 프레임 재현이 아니다.",
    )
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return out / "report.json"
