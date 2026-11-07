"""승인된 기획 정본을 모델의 재서술 없이 프롬프트까지 전달한다."""

from __future__ import annotations

from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.persona import TraitSheet

SOURCE_FIELDS = (
    "selectedTraits",
    "schemaVersion",
    "characterId",
    "planRev",
    "name",
    "age",
    "gender",
    "job",
    "background",
    "coreTraits",
    "contrastTrait",
    "choices",
    "lifeAndTastes",
    "wantsAndFears",
    "misreadings",
    "voiceSummary",
    "voiceExamples",
    "boundaries",
    "chapterArc",
    "chapters",
    "profileCard",
)
CANONICAL_SECTIONS = ("ACTOR_IDENTITY", "PERSONA / FACTS", "PERSONA / VOICE", "CHAPTERS")


def with_creator_traits(disposition: str, plan) -> str:
    traits = dump(plan).get("selectedTraits", [])
    if not traits:
        return disposition
    return (
        disposition + "\n제작자가 추가한 성향: 기본 성격과 함께 상황에 맞을 때만 드러낸다. "
        "매 턴 모두 적용하거나 없던 약속·관계·사용자 사실을 만들지 않는다.\n"
        + "\n".join(f"- {t['behavior']}" for t in traits)
    )


def project_plan(plan, source_sha256: str) -> dict:
    raw = dump(plan)
    return {
        "schemaVersion": "persona-source-v1",
        "sourceSha256": source_sha256,
        "plan": {k: raw[k] for k in SOURCE_FIELDS if k in raw},
    }


def canonical_sections(source: dict, sheet: TraitSheet) -> dict[str, str]:
    p = source["plan"]
    gender = {"female": "여성", "male": "남성", "other": ""}.get(p.get("gender"), "")
    identity = f"너는 {p['name']}, {p['age']}세 {gender} {p['job']}이다."
    facts = [p["background"]] if p.get("background") else []
    facts.extend(p.get("lifeAndTastes", []))
    if not facts:
        facts = ["고정 배경은 위 신원과 아래 허구 경험의 범위다."]
        facts.extend(e.event for e in sheet.card.experiences)
    voice = (
        [p["voiceSummary"]]
        if p.get("voiceSummary")
        else list(dump(sheet.card.dialogueHabits).values())
    )
    voice.extend(f"말투 예시: {v}" for v in p.get("voiceExamples", []))
    voice.append("예시는 호흡의 참고다. 해당 상황이 아니면 대사나 말끝을 복사하지 않는다.")
    chapters = []
    for c in p.get("chapterArc", p.get("chapters", [])):
        if "arc" in c:
            chapters.append(f"{c['chapterId']} {c['entryStage']}→{c['targetStage']}: {c['arc']}")
        else:
            chapters.append(f"{c['chapterId']} {c['relationStage']}: {c['scene']}")
    chapters.append(
        "챕터는 관계 흐름이다. 현재 관계·장소는 실제 이력에 따르고, "
        "목표를 이미 겪은 공동 과거로 만들지 않는다."
    )
    return {
        "ACTOR_IDENTITY": identity,
        "PERSONA / FACTS": "\n".join(facts),
        "PERSONA / VOICE": "\n".join(voice),
        "CHAPTERS": "\n".join(chapters),
    }
