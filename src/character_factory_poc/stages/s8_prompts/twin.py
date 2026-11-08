"""G3의 인용과 G0의 대표 메시지를 승인된 본인 발화에만 연결한다."""

from __future__ import annotations

import json

from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.source import SourceDigest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source
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
    return {
        "sourceRev": index.sourceRev,
        "speechEndings": _speech_endings(corpus),
        "examples": examples,
    }


def voice_lines(summary: str, voice: dict) -> list[str]:
    counts = voice["speechEndings"]
    polite, casual = counts["politeEnding"], counts["casualEnding"]
    lines = []
    # 원문이 한 등급으로만 관측됐을 때 쓴다. 섞이거나 미분류면 G3 요약을 따른다.
    if _plan_speech_level(summary) is None:
        if polite and not casual:
            lines.append("기본 말높임: 존댓말.")
        elif casual and not polite:
            lines.append("기본 말높임: 반말.")
    lines.extend(
        [
            summary,
            "아래는 본인의 실제 발화다. 본인이 밝힌 사실과 말투를 따르고, "
            "원문에 없는 경험이나 사용자와의 공동 기억을 지어내지 않는다.",
        ]
    )
    lines.extend(
        "말투 예시: " + json.dumps(q, ensure_ascii=False)
        for q in dict.fromkeys(e["quote"] for e in voice["examples"])
    )
    return lines
