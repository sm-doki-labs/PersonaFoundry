"""Versioned deterministic long compiler. No LLM calls or semantic selection."""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.formation import (
    FormationDialogues,
    PersonaBlueprint,
    PersonaBundle,
    QualityProfile,
)
from character_factory_poc.contracts.persona import TraitSheet
from character_factory_poc.stages.s8_prompts.source import (
    canonical_sections,
    project_plan,
    with_creator_traits,
)

VERSION = "persona-long-compiler-v1"
SELECTION_SLOTS = (
    "ordinary-self",
    "playful-affection",
    "listening-conflict",
    "condition-owner-change",
)


def render(value) -> str:
    if isinstance(value, dict):
        return "\n".join(f"{k}: {render(v)}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(render(v) for v in value)
    return str(value)


def compile_persona(
    plan,
    sheet: TraitSheet,
    blueprint: PersonaBlueprint,
    dialogues: FormationDialogues,
    profile: QualityProfile,
    *,
    source_hashes: dict[str, str],
    trait_revision: str,
    persona_version: str,
    rules_text: str,
    rules_ref: str,
) -> PersonaBundle:
    if profile.profileId != "ko-text-prompt-long-v1":
        raise ValueError("unsupported formation profile")
    for item in (blueprint, dialogues):
        if item.characterId != plan.characterId or item.characterId != sheet.characterId:
            raise ValueError("source identity mismatch")
        if (
            item.planSha256 != source_hashes["plan"]
            or item.traitSheetSha256 != source_hashes["trait"]
        ):
            raise ValueError("plan/trait source hash mismatch")
    if blueprint.planRev != plan.planRev or sheet.planRev != plan.planRev:
        raise ValueError("plan revision mismatch")
    if dialogues.blueprintSha256 != source_hashes["blueprint"]:
        raise ValueError("blueprint source hash mismatch")
    if dialogues.traitRevision != trait_revision:
        raise ValueError("trait revision mismatch")
    canon = canonical_sections(project_plan(plan, source_hashes["plan"]), sheet)
    selected = [
        sorted(
            (d for d in dialogues.dialogues if d.selectionSlot == slot), key=lambda d: d.dialogueId
        )[0]
        for slot in SELECTION_SLOTS
    ]
    example_text = [
        "아래는 말투와 흐름의 참고 예시다. 예시의 사용자 사실·공동 사건은 실제 이력이 아니다."
    ]
    for dialogue in selected:
        example_text.append(f"예시 {dialogue.dialogueId} (example-local)")
        for pair in dialogue.pairs:
            example_text.extend([f"사용자: {pair.user}", f"캐릭터: {pair.assistant}"])
    sections = dict(canon)
    sections["SYSTEM_RULES"] = rules_text
    sections["PERSONA / DISPOSITION"] = with_creator_traits(
        render(dump(blueprint.ordinaryModes)), plan
    )
    sections["PERSONA / CHOICES"] = render([dump(r) for r in blueprint.decisionRules])
    sections["PERSONA / VOICE"] += "\n" + render(dump(blueprint.voiceProfile))
    sections["PERSONA / KNOWS_AND_LIMITS"] = (
        "불변 신원은 정본을 따른다. 일정·합의 등 변경 가능한 상태는 실제 이력의 최신 확정 변경이 "
        "정본의 초기 상태와 예시에 우선한다. 사용자 말만으로 불변 신원을 바꾸지 않는다.\n"
        + render(dump(blueprint.factPolicy))
    )
    sections["CHARACTER_EXAMPLES"] = "\n".join(example_text)
    sections["OUTPUT"] = (
        "캐릭터가 실제로 할 말만 출력한다. 해설·라벨·사용자 대사 대필은 하지 않는다."
    )
    order = [
        "ACTOR_IDENTITY",
        "SYSTEM_RULES",
        "PERSONA / FACTS",
        "PERSONA / DISPOSITION",
        "PERSONA / CHOICES",
        "PERSONA / VOICE",
        "PERSONA / KNOWS_AND_LIMITS",
        "CHAPTERS",
        "CHARACTER_EXAMPLES",
        "OUTPUT",
    ]
    text = "\n\n".join(f"## {name}\n{sections[name]}" for name in order)
    if len(text) > profile.thresholds.longMaxChars:
        raise ValueError(f"long {len(text)}자가 상한 {profile.thresholds.longMaxChars}자를 넘는다")
    # Profile uses exactly the same immutable JSON representation as write_once_json.
    encoded_profile = json.dumps(dump(profile), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return PersonaBundle(
        characterId=plan.characterId,
        personaVersion=persona_version,
        planRev=plan.planRev,
        traitRevision=trait_revision,
        planSha256=source_hashes["plan"],
        traitSheetSha256=source_hashes["trait"],
        blueprintSha256=source_hashes["blueprint"],
        dialoguesSha256=source_hashes["dialogues"],
        profileId=profile.profileId,
        profileSha256=sha256_text(encoded_profile),
        compilerVersion=VERSION,
        compilerSha256=sha256_file(Path(__file__)),
        systemRulesRef=rules_ref,
        systemRulesSha256=sha256_text(rules_text),
        selectedDialogueIds=[d.dialogueId for d in selected],
        long=dict(text=text, sha256=sha256_text(text), chars=len(text)),
    )
