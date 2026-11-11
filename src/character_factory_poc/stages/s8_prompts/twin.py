"""G3 인용과 G0 대표 메시지를 승인된 본인 발화에 연결한다. 말투 칸은 원문 통계로 만든다(D-0145)."""

from __future__ import annotations

import re

from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.source import SourceDigest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source
from character_factory_poc.stages.s3_plan.speech_profile import (
    MIN_SENTENCES,
    build_speech_profile,
    render_voice_definition,
    source_registers,
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
        "speechProfile": build_speech_profile(
            corpus,
            kinds,
            source_registers(index.texts),
            ctx.config.stage("s8").get("model_habit_words"),
        ),
        # G3 인용 근거는 말의 결 견본과 따로 보관한다.
        "examples": examples,
    }


def voice_lines(summary: str, voice: dict) -> list[str]:
    """모티브 말투 칸. 표본이 작으면 기존 G3 요약과 말높임을 쓴다."""
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


def approved_facts(ctx, cid):
    """G0에서 검토한 같은 판만 읽고 제외한 사실은 뒤 단계에 넘기지 않는다."""
    from character_factory_poc.common.canonical import sha256_file
    from character_factory_poc.contracts.facts import MotifFacts

    gate = ctx.state(cid).gate("G0")
    if gate.status != "APPROVED" or not gate.rev or not gate.recordRef:
        raise ValueError("공개 사실을 쓰려면 G0 승인이 필요하다")
    root = ctx.character_dir(cid)
    record = read_json(root / gate.recordRef)
    path = root / STAGE_DIR / gate.rev / "facts.json"
    ref = path.relative_to(root).as_posix()
    artifact = next((a for a in record["shownArtifacts"] if a["ref"] == ref), None)
    if artifact is None and not path.exists():
        return None
    if not artifact or not path.is_file() or sha256_file(path) != artifact["sha256"]:
        raise ValueError("G0에서 검토한 공개 사실과 현재 파일이 다르다")
    facts = MotifFacts.model_validate(read_json(path))
    facts.items = [
        f for f in facts.items if not f.excluded and f.factId not in record["selections"]
    ]
    return facts


def motif_facts(facts):
    lines = []
    if facts:
        for f in facts.items:
            lines.append(f.line())
            if f.selfView:
                lines.append(f.selfView.paraphrase)
    return lines


_STATUS_WORDS = re.compile(r"은퇴|거취|복귀|재계약|계약 연장|이적설")


def status_lines(facts) -> list[str]:
    """은퇴·거취 질문의 답. 현재 상태와 1년 안에 본인이 밝힌 거취를 함께 준다."""
    items = [f for f in facts.items if not f.excluded]
    if not items:
        return []
    newest = max(f.eventDate for f in items)
    picked = [
        f
        for f in items
        if f.category == "CURRENT_STATUS"
        or (_STATUS_WORDS.search(f.text) and (newest - f.eventDate).days <= 365)
    ]
    if not picked:
        return []
    return [
        "은퇴나 거취 등 현재 상태를 물으면 아래 사실을 그대로 말한다: "
        + " / ".join(f.line() for f in picked)
    ]


def motif_limits(facts=None) -> list[str]:
    """D-0147: 실존 인물은 확인할 수 있는 지난 일을 지어내지 않는다.

    공통 대화 규칙은 생활·지난 일·취향을 대화 중에 새로 말해도 된다고 허용한다. 창작 인물에는 맞지만
    실존 인물에는 사실 확인이 가능한 내용이 생긴다. 이 한계는 인물이 소유하는 칸
    (KNOWS_AND_LIMITS)에 둔다.
    """
    lines = [
        "실존 인물이다. 확인할 수 있는 지난 일(있었던 일과 그 결과, 함께한 사람과 그 사람의 취향, "
        "먹은 음식, 쓰는 물건의 상표, 날짜와 숫자)은 위 사실과 말투 칸에 적힌 것만 사실로 말한다",
        "확인되지 않은 세부를 물으면 지어내지 않고 정확히 기억나지 않는다고 짧게 말한 뒤 "
        "아는 범위의 이야기로 넘어간다",
        "지금 통화 중의 상태와 오늘 일과는 장면 설정을 따른다",
    ]
    if facts is not None:
        phrases = " 또는 ".join(f"“{phrase}”" for phrase in facts.phrases())
        lines.extend(
            [
                "지난 경기와 대회 등 끝난 일은 위 사실에 적힌 결과와 본인이 밝힌 느낌대로 말한다",
                *status_lines(facts),
                f"연애와 결혼은 있다 없다도 말하지 않고 {phrases}처럼 웃으며 가볍게 넘긴다. "
                "누구와 주고받은 사적인 대화 내용과 가족의 사생활도 위 사실에 적힌 것만 말한다",
            ]
        )
    return lines
