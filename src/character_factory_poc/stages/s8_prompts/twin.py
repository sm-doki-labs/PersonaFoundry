"""G3 인용과 G0 대표 메시지를 승인된 본인 발화에 연결한다. 말투 칸은 원문 통계로 만든다(D-0145)."""

from __future__ import annotations

from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.source import SourceDigest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source
from character_factory_poc.stages.s3_plan.speech_profile import (
    MIN_SENTENCES,
    build_speech_profile,
    render_voice_definition,
)
from character_factory_poc.stages.s3_plan.twin import _speech_endings
from character_factory_poc.stages.s7_traits.check import _plan_speech_level


def approved_voice(ctx: Context, cid: str, plan: CharacterPlanV2) -> dict:
    _, index, corpus = load_approved_source(ctx, cid)
    if index.characterId != cid or index.sourceRev != "sp" + plan.seedRev.removeprefix("sd"):
        raise ValueError("G3 기획과 G0 승인 원문의 revision이 다르다")
    messages = {r["msgId"]: r["text"] for r in corpus if r["speaker"] == "SUBJECT"}
    folder = ctx.character_dir(cid) / STAGE_DIR / index.sourceRev
    digest = SourceDigest.model_validate(read_json(folder / "digest.json"))
    examples = []
    refs = plan.evidence.get("voiceExamples", [])
    if any(e.kind != "SOURCE" for e in refs) or [e.quote for e in refs] != plan.voiceExamples:
        raise ValueError("G3 말투 예시마다 일치하는 SOURCE 인용이 필요하다")

    def add(ref: str, quote: str) -> None:
        if not quote or ref not in messages or quote not in messages[ref]:
            raise ValueError(f"승인된 본인 발화와 일치하지 않는 말투 인용: {ref}")
        item = {"msgId": ref, "quote": quote}
        if item not in examples:
            examples.append(item)

    for evidence in (refs, *plan.evidence.values()):
        for e in evidence:
            if e.kind == "SOURCE":
                add(e.ref, e.quote)
    for rep in digest.representative:
        add(rep.msgId, messages.get(rep.msgId, ""))
    kinds = {t.textId: t.kind for t in index.texts}
    return {
        "sourceRev": index.sourceRev,
        "speechEndings": _speech_endings(corpus),
        "speechProfile": build_speech_profile(corpus, kinds),
        # 예시는 G3 근거와 비교 겹침 검사(s10)에만 쓰고 대화 프롬프트에는 넣지 않는다(D-0145).
        "examples": examples,
    }


def voice_lines(summary: str, voice: dict) -> list[str]:
    """D-0145: 말투 칸은 원문 통계로 만든 말버릇 정의다. 말투 예시 문장은 넣지 않는다.

    원문 문장이 적어 통계를 낼 수 없으면 원문에서 한 등급만 관측된 말높임과 G3 말투 요약을 쓴다.
    """
    profile = voice["speechProfile"]
    if profile["sentences"] >= MIN_SENTENCES:
        return render_voice_definition(profile, summary)
    counts = voice["speechEndings"]
    polite, casual = counts["politeEnding"], counts["casualEnding"]
    lines = []
    if _plan_speech_level(summary) is None:
        if polite and not casual:
            lines.append("기본 말높임: 존댓말.")
        elif casual and not polite:
            lines.append("기본 말높임: 반말.")
    return [*lines, summary, render_voice_definition(profile)[-1]]
