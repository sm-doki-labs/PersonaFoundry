"""특질 시트 자동 검사 (LLD §8.6, FR-19·FR-20)."""

from __future__ import annotations

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


def check_trait_sheet(sheet: TraitSheet) -> list[str]:
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
    if sheet.typeMappingAssumed:
        p.append("typeMappingAssumed: 14유형과 프리셋의 대응을 가정할 수 없다(Q-0005)")
    for r in sheet.references:
        if not r.version:
            p.append(f"references[{r.id}]: version이 비어 있다")
    return p


def check_matches_plan(plan_name: str, plan_core: list[str]):
    def _check(sheet: TraitSheet) -> list[str]:
        p = []
        core_text = " ".join(sheet.card.expressedTraits.core) + " " + sheet.choice.primaryResponse
        missing = [t for t in plan_core if t not in core_text and t not in sheet.card.stance]
        if len(missing) == len(plan_core):
            p.append("card.expressedTraits.core: 기획서의 핵심 성격이 하나도 언급되지 않았다")
        return p

    return _check
