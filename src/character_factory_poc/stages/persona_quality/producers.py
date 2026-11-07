"""Replay consumer prompts from actual frozen producer assets, not arm labels."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.dialogue_beats import FormationBeats
from character_factory_poc.contracts.formation import (
    FormationContract,
    FormationDialogues,
    PersonaBlueprint,
    PersonaBlueprintV2,
    PersonaBundle,
    TraitSheet,
    load_quality_profile,
)
from character_factory_poc.contracts.persona import PromptPairV2, load_prompt_pair
from character_factory_poc.contracts.rendered_dialogues import RenderedDialogues
from character_factory_poc.contracts.voice import VoiceBinding
from character_factory_poc.stages.persona_quality.choice_voice_protocol import FileAsset
from character_factory_poc.stages.s7_traits.voice import verify_voice_binding
from character_factory_poc.stages.s7_traits.voice_render import check_render_structure
from character_factory_poc.stages.s8_prompts.compiler import compile_persona


class DevelopmentProducer(FormationContract):
    schemaVersion: Literal["development-producer-v1"] = "development-producer-v1"
    arm: Literal["A", "B", "C", "D", "CURRENT", "COVERED"]
    assets: dict[str, FileAsset]
    selectedDialogueIds: list[str] = Field(min_length=4, max_length=4)
    pairSha256: str


def _sources(assets):
    return {name: asset.verify() for name, asset in assets.items()}


def _replay(arm, paths):
    raw = read_json(paths["plan"])
    plan = validate(raw["schemaVersion"], raw)
    sheet = TraitSheet.model_validate(read_json(paths["trait"]))
    rules = paths["systemRules"].read_text("utf-8")
    if arm == "A":
        original = PersonaBundle.model_validate(read_json(paths["legacyBundle"]))
        bp = PersonaBlueprint.model_validate(read_json(paths["blueprint"]))
        ds = FormationDialogues.model_validate(read_json(paths["dialogues"]))
        replayed = compile_persona(
            plan,
            sheet,
            bp,
            ds,
            load_quality_profile(paths["profile"]),
            source_hashes={
                k: sha256_file(paths[k]) for k in ("plan", "trait", "blueprint", "dialogues")
            },
            trait_revision=original.traitRevision,
            persona_version=original.personaVersion,
            rules_text=rules,
            rules_ref=original.systemRulesRef,
        )
        if replayed != original:
            raise ValueError("legacy producer cannot be replayed from its frozen sources")
        return original.long.text, original.selectedDialogueIds, original.systemRulesRef
    bp = PersonaBlueprintV2.model_validate(read_json(paths["blueprint"]))
    if (
        bp.planSha256 != sha256_file(paths["plan"])
        or bp.traitSheetSha256 != sha256_file(paths["trait"])
        or bp.approvedChoiceRef.sha256 != sha256_file(paths["choice"])
    ):
        raise ValueError("producer blueprint/choice source relationship mismatch")
    voice = VoiceBinding.model_validate(read_json(paths["voiceBinding"]))
    if arm in {"B", "C"} and (voice.status != "DRAFT" or voice.packPath is not None):
        raise ValueError("generated producer control includes an approved voice")
    if arm in {"D", "CURRENT", "COVERED"}:
        verify_voice_binding(voice, raw, read_json(paths["voicePolicy"]))
    if arm == "B":
        direct = FormationDialogues.model_validate(read_json(paths["dialogues"]))
        if (
            direct.planSha256 != sha256_file(paths["plan"])
            or direct.blueprintSha256 != sha256_file(paths["blueprint"])
            or direct.traitSheetSha256 != sha256_file(paths["trait"])
        ):
            raise ValueError("direct producer source relationship mismatch")
    else:
        beats = FormationBeats.model_validate(read_json(paths["beats"]))
        rendered = RenderedDialogues.model_validate(read_json(paths["dialogues"]))
        if (
            rendered.beatsSha256 != sha256_file(paths["beats"])
            or rendered.voiceBindingSha256 != sha256_file(paths["voiceBinding"])
            or beats.blueprintSha256 != sha256_file(paths["blueprint"])
            or beats.choiceSha256 != sha256_file(paths["choice"])
        ):
            raise ValueError("rendered producer input relationship mismatch")
        check_render_structure(beats, rendered)
        rows = []
        ordinary = 0
        by_id = {d.dialogueId: d for d in rendered.dialogues}
        for scene in beats.dialogues:
            if scene.category == "ordinary":
                slot = "ordinary-self" if ordinary < 4 else "playful-affection"
                ordinary += 1
            else:
                slot = (
                    "listening-conflict"
                    if scene.category == "boundary"
                    else "condition-owner-change"
                )
            turns = by_id[scene.dialogueId].turns
            rows.append(
                dict(
                    dialogueId=scene.dialogueId,
                    category=scene.category,
                    selectionSlot=slot,
                    pairs=[
                        dict(user=turns[i].content, assistant=turns[i + 1].content)
                        for i in range(0, len(turns), 2)
                    ],
                    factRefs=[],
                )
            )
        refs = [dump(r) for r in bp.sourceRefs]
        refs.append(
            dict(
                kind="blueprint",
                ref=str(paths["blueprint"]),
                version=rendered.traitRevision,
                sha256=sha256_file(paths["blueprint"]),
                fieldPath="decisionRules[0].firstMove",
                quote=bp.decisionRules[0].firstMove,
            )
        )
        direct = FormationDialogues(
            characterId=raw["characterId"],
            traitRevision=rendered.traitRevision,
            planSha256=sha256_file(paths["plan"]),
            traitSheetSha256=sha256_file(paths["trait"]),
            blueprintSha256=sha256_file(paths["blueprint"]),
            dialogues=rows,
            sourceRefs=refs,
        )
    if arm in {"CURRENT", "COVERED"}:
        from character_factory_poc.contracts.voice_bundle import CoveragePolicy
        from character_factory_poc.stages.s8_prompts.choice_voice import (
            compose_choice_voice_text,
            select_covered_examples,
        )

        policy = CoveragePolicy.model_validate(read_json(paths["coveragePolicy"]))
        expected = CoveragePolicy(
            requiredRuleIds=[r.choiceRuleId for r in bp.decisionRules],
            coverage={
                d.dialogueId: dict(
                    tags=d.coverageTags,
                    ruleIds=sorted({r for t in d.turns for r in t.decisionRuleIds}),
                )
                for d in beats.dialogues
            },
        )
        if policy != expected:
            raise ValueError("selection policy does not cover actual frozen beats")
        selected = (
            select_covered_examples(rendered, policy)
            if arm == "COVERED"
            else [
                sorted(d.dialogueId for d in direct.dialogues if d.selectionSlot == slot)[0]
                for slot in (
                    "ordinary-self",
                    "playful-affection",
                    "listening-conflict",
                    "condition-owner-change",
                )
            ]
        )
        profile = load_quality_profile(paths["profile"])
        text, _ = compose_choice_voice_text(
            plan,
            sheet,
            bp,
            rendered,
            voice,
            selected,
            plan_sha=sha256_file(paths["plan"]),
            rules_text=rules,
            long_max=profile.thresholds.longMaxChars,
        )
        return text, selected, "development-fixed-compiler-selection-only"
    # B/C/D keep the pre-intervention compiler and four-slot policy identical.
    # Only source choice design, direct-vs-beat writing and injected voice differ.
    projected = dump(bp)
    projected["schemaVersion"] = "persona-blueprint-v1"
    projected.pop("approvedChoiceRef")
    for rule in projected["decisionRules"]:
        for key in ("choiceRuleId", "attention", "acceptedCost", "alternative"):
            rule.pop(key)
    legacy_bp = PersonaBlueprint.model_validate(projected)
    replayed = compile_persona(
        plan,
        sheet,
        legacy_bp,
        direct,
        load_quality_profile(paths["compilerProfile"]),
        source_hashes={k: sha256_file(paths[k]) for k in ("plan", "trait", "blueprint")}
        | dict(dialogues=sha256_file(paths["dialogues"])),
        trait_revision=direct.traitRevision,
        persona_version="development",
        rules_text=rules,
        rules_ref="development-frozen-v1",
    )
    return replayed.long.text, replayed.selectedDialogueIds, replayed.systemRulesRef


def prepare_development_pair(arm, assets, out):
    """Compile already captured first outputs. No model calls or output selection."""
    out = Path(out)
    refs = {
        k: FileAsset(path=str(Path(p).resolve()), sha256=sha256_file(Path(p)))
        for k, p in assets.items()
    }
    paths = _sources(refs)
    text, selected, rules_ref = _replay(arm, paths)
    plan = read_json(paths["plan"])
    rules = paths["systemRules"].read_text("utf-8")
    pair = PromptPairV2(
        characterId=plan["characterId"],
        traitSheetSha256=sha256_file(paths["trait"]),
        sections=[line[3:] for line in text.splitlines() if line.startswith("## ")],
        long=dict(text=text, sha256=sha256_text(text), chars=len(text)),
        shortStatus="UNAVAILABLE",
        systemRulesRef=rules_ref,
        systemRulesSha256=sha256_text(rules),
    )
    pair_path = out / "prompt-pair.json"
    write_once_json(pair_path, dump(pair))
    receipt = DevelopmentProducer(
        arm=arm, assets=refs, selectedDialogueIds=selected, pairSha256=sha256_file(pair_path)
    )
    producer_path = out / "producer.json"
    write_once_json(producer_path, dump(receipt))
    return FileAsset(path=str(pair_path.resolve()), sha256=sha256_file(pair_path)), FileAsset(
        path=str(producer_path.resolve()), sha256=sha256_file(producer_path)
    )


def verify_development_producer(slot):
    if slot.producer is None:
        raise ValueError("development prompt has no producer receipt")
    producer = DevelopmentProducer.model_validate(read_json(slot.producer.verify()))
    if producer.arm != slot.arm or producer.pairSha256 != slot.pair.sha256:
        raise ValueError("development producer/prompt identity mismatch")
    for name in ("seed", "plan", "blueprint", "choice", "beats", "voiceBinding", "voicePolicy"):
        declared = getattr(slot, name)
        if declared is not None and producer.assets.get(name) != declared:
            raise ValueError("development producer does not use declared control sources")
    text, selected, rules_ref = _replay(slot.arm, _sources(producer.assets))
    pair = load_prompt_pair(slot.pair.verify())
    if (
        pair.long.text != text
        or producer.selectedDialogueIds != selected
        or pair.systemRulesRef != rules_ref
    ):
        raise ValueError("development consumer prompt differs from its actual producer")
