"""특질 시트 자동 검사 (LLD §8.6, FR-19·FR-20)."""

from __future__ import annotations

import re

from character_factory_poc.common.call_context import appearance_reading_problems
from character_factory_poc.common.textstats import looks_like_bare_adjectives
from character_factory_poc.contracts.persona import TraitSheet

MIN_CHARS = 6
UNRESOLVED = "미정"


def _field_problems(path: str, text: str, unresolved: set[str]) -> list[str]:
    if text.strip() == UNRESOLVED:
        if path not in unresolved:
            return [f"{path}: '미정'이면 unresolved에 적어야 한다"]
        return []
    if len(text.strip()) < MIN_CHARS:
        return [f"{path}: 너무 짧다({len(text.strip())}자). 조건과 행동을 서술한다"]
    if looks_like_bare_adjectives(text):
        return [f"{path}: 낱말 나열로 보인다. '~하면 ~한다'처럼 서술한다"]
    return []


def check_trait_sheet(sheet: TraitSheet, *, canonical_core: list[str] | None = None) -> list[str]:
    p: list[str] = []
    un = set(sheet.unresolved)
    c = sheet.choice
    for name in ("attention", "interpretationPriority", "primaryResponse", "expressionIntensity"):
        p += _field_problems(f"choice.{name}", getattr(c, name), un)
    if len(c.switchConditions) < 2:
        p.append("choice.switchConditions: 최소 2개가 필요하다")
    for i, s in enumerate(c.switchConditions):
        p += _field_problems(f"choice.switchConditions[{i}]", s, un)

    card = sheet.card
    p += _field_problems("card.stance", card.stance, un)
    if not card.expressedTraits.core:
        p.append("card.expressedTraits.core: 비어 있다")
    for i, t in enumerate(card.expressedTraits.core):
        if t in (canonical_core or []) and not looks_like_bare_adjectives(t):
            continue
        p += _field_problems(f"card.expressedTraits.core[{i}]", t, un)
    p += _field_problems("card.expressedTraits.contrast", card.expressedTraits.contrast, un)
    if len(card.judgmentPriorities) < 2:
        p.append("card.judgmentPriorities: 최소 2개가 필요하다")
    for i, j in enumerate(card.judgmentPriorities):
        for f in ("dilemma", "choice", "reason", "switch"):
            p += _field_problems(f"card.judgmentPriorities[{i}].{f}", getattr(j, f), un)
    for f in ("order", "directness", "questions", "evidence", "lexicon"):
        p += _field_problems(f"card.dialogueHabits.{f}", getattr(card.dialogueHabits, f), un)
    if len(card.situational) < 3:
        p.append("card.situational: 최소 3개가 필요하다")
    for i, s in enumerate(card.situational):
        for f in ("condition", "reaction", "returnOrSwitch"):
            p += _field_problems(f"card.situational[{i}].{f}", getattr(s, f), un)
    if len(card.experiences) < 1:
        p.append("card.experiences: 최소 1개가 필요하다")
    for i, e in enumerate(card.experiences):
        for f in ("event", "interpretation", "habitLink"):
            p += _field_problems(f"card.experiences[{i}].{f}", getattr(e, f), un)
    # D-0082: 상대를 읽는 칸에 외모·신체 상태 읽기를 쓰지 않는다(영상통화 카메라 관찰 규칙).
    reading = {
        "choice.attention": c.attention,
        "choice.interpretationPriority": c.interpretationPriority,
        "choice.primaryResponse": c.primaryResponse,
        "choice.switchConditions": " ".join(c.switchConditions),
        "card.stance": card.stance,
        "card.dialogueHabits": " ".join(
            getattr(card.dialogueHabits, f)
            for f in ("order", "directness", "questions", "evidence", "lexicon")
        ),
        "card.judgmentPriorities": " ".join(
            j.choice + " " + j.switch for j in card.judgmentPriorities
        ),
        "card.situational": " ".join(s.condition + " " + s.reaction for s in card.situational),
    }
    for field, value in reading.items():
        p += appearance_reading_problems(field, value)
    if sheet.typeMappingAssumed:
        p.append("typeMappingAssumed: 14유형과 프리셋의 대응을 가정할 수 없다(Q-0005)")
    for r in sheet.references:
        if not r.version:
            p.append(f"references[{r.id}]: version이 비어 있다")
    return p


def _mentions(trait: str, text: str, ratio: float = 0.7) -> bool:
    """기획의 핵심 성격이 시트에 실질적으로 남았는가. 원문 그대로이거나, 어미·문장 이음만 바뀌어
    어절의 ratio 이상이 그대로 들어 있으면 언급한 것으로 본다.

    2026-11-04 실제 실행에서 '책임을 다한다.'가 '책임을 다하고,'로 이어 쓰여 오판된 사례가 있었다.
    """
    if trait in text:
        return True
    words = [w.strip(".,!?·") for w in trait.split()]
    words = [w for w in words if len(w) >= 2]
    if not words:
        return False
    return sum(w in text for w in words) / len(words) >= ratio


def check_matches_plan(plan_name: str, plan_core: list[str]):
    def _check(sheet: TraitSheet) -> list[str]:
        p = []
        core_text = " ".join(sheet.card.expressedTraits.core) + " " + sheet.choice.primaryResponse
        text = core_text + " " + sheet.card.stance
        missing = [t for t in plan_core if not _mentions(t, text)]
        if len(missing) == len(plan_core):
            p.append("card.expressedTraits.core: 기획서의 핵심 성격이 하나도 언급되지 않았다")
        return p

    return _check


# K-0073: 해요체 기획에 S7이 "'~합니다'를 주로 쓴다"를 정해 응답이 하십시오체로 흐른
# 사례(2026-11-04).
_QUOTE_END = r"\s*[?!.]?\s*['\"’”」』]"
_WORD_END = r"(?=$|[\s,.!?·'\"’”」』)])"
# 따옴표 없이 낱말로 적은 어미('괜찮습니다' 등)도 잡는다(2026-11-05 tr1 재생성에서 놓친 사례).
_FORMAL = re.compile(
    r"(?:니다|니까)"
    + _QUOTE_END
    + r"|~\s*\S*니다|[가-힣]+(?:니다|니까)"
    + _WORD_END
    + r"|하십시오체|합쇼체|합니다체"
)
_POLITE = re.compile(
    r"요"
    + _QUOTE_END
    + r"|~\s*\S*[해세]요|[가-힣]+(?:어요|아요|해요|세요|예요|에요)"
    + _WORD_END
    + r"|해요체|존댓말"
)


def _plan_speech_level(voice_summary: str) -> str | None:
    if re.search(r"하십시오체|합쇼체|합니다체", voice_summary):
        return "formal"
    if re.search(r"해요체|존댓말|존대", voice_summary):
        return "polite"
    if re.search(r"반말|해체", voice_summary):
        return "casual"
    return None


def check_speech_level(voice_summary: str):
    """말버릇 칸이 기획 voiceSummary의 말높임과 다른 종결어미를 정하면 문제로 돌려준다.

    S7은 말높임을 정하지 않는다. 기획이 정한 말높임과 부딪히는 어미·예시만 잡는다.
    """
    level = _plan_speech_level(voice_summary or "")
    label = {"formal": "하십시오체", "polite": "해요체", "casual": "반말"}.get(level or "")
    banned = {"polite": [_FORMAL], "casual": [_FORMAL, _POLITE]}.get(level or "", [])

    def _check(sheet: TraitSheet) -> list[str]:
        fields = {
            f"card.dialogueHabits.{f}": getattr(sheet.card.dialogueHabits, f)
            for f in ("order", "directness", "questions", "evidence", "lexicon")
        }
        fields["choice.expressionIntensity"] = sheet.choice.expressionIntensity
        problems = []
        for path, value in fields.items():
            found = sorted({m.group(0).strip() for rx in banned for m in rx.finditer(value or "")})
            if found:
                problems.append(
                    f"{path}: 기획 voiceSummary의 말높임({label})과 다른 "
                    f"어미·예시({', '.join(found)})를 정했다. 말높임과 종결어미는 정하지 않고, "
                    "예시 말은 voiceSummary의 말높임을 따른다"
                )
        return problems

    return _check
