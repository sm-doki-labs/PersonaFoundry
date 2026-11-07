"""Executable source lineage, neutral dialogue inputs and frozen development arms."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256
from character_factory_poc.stages.persona_quality.protocol import Scene
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.formation import field_text


class FileAsset(FormationContract):
    path: Nonempty
    sha256: Sha256

    def verify(self):
        p = Path(self.path)
        if not p.is_file() or sha256_file(p) != self.sha256:
            raise ValueError("frozen file asset hash mismatch")
        return p


class SplitRow(FileAsset):
    id: Nonempty
    sourceGroupId: Nonempty
    originalConversationId: Nonempty
    parentSourceIds: list[Nonempty]
    derivedFrom: list[Nonempty]
    sceneFamilyId: Nonempty
    split: Literal["injection", "voice-validation", "development", "holdout"]
    fieldPath: str = ""


class SplitManifest(FormationContract):
    auditStatus: Literal["PASS", "FAIL", "UNRESOLVED"]
    rows: list[SplitRow]


def validate_source_split(manifest: SplitManifest):
    if manifest.auditStatus != "PASS":
        raise ValueError("source split audit is unresolved or failed")
    by_id = {r.id: r for r in manifest.rows}
    if len(by_id) != len(manifest.rows):
        raise ValueError("duplicate split row id")
    parents = {}

    def find(k):
        parents.setdefault(k, k)
        if parents[k] != k:
            parents[k] = find(parents[k])
        return parents[k]

    def union(a, b):
        parents[find(a)] = find(b)

    content = {}
    for row in manifest.rows:
        p = row.verify()
        raw = read_json(p) if p.suffix == ".json" else p.read_text("utf-8")
        excerpt = field_text(raw, row.fieldPath) if row.fieldPath else raw
        content[row.id] = body_hash(excerpt)
        for marker in (
            ("group", row.sourceGroupId),
            ("conversation", row.originalConversationId),
            ("scene", row.sceneFamilyId),
            ("content", content[row.id]),
        ):
            union(("row", row.id), marker)
        for parent in [*row.parentSourceIds, *row.derivedFrom]:
            if parent not in by_id:
                raise ValueError("unresolved source lineage parent")
            union(("row", row.id), ("row", parent))
    components = defaultdict(set)
    for row in manifest.rows:
        components[find(("row", row.id))].add(row.split)
    for splits in components.values():
        if ("injection" in splits and ("voice-validation" in splits or "holdout" in splits)) or (
            "development" in splits and "holdout" in splits
        ):
            raise ValueError("source lineage overlap across frozen splits")


def next_neutral_user(turn, last_assistant=""):
    raw = turn.model_dump() if hasattr(turn, "model_dump") else turn
    if raw.get("branches"):
        raise ValueError(
            "substring branches are unsupported in the choice-voice profile; use neutral follow-ups"
        )
    return raw["user"]


def check_controlled_hashes(arms):
    for key in ("choice", "blueprint"):
        if (
            not all(arms.get(a, {}).get(key) for a in ("B", "C", "D"))
            or len({arms[a][key] for a in ("B", "C", "D")}) != 1
        ):
            raise ValueError(f"controlled {key} inputs differ")
    if not arms["C"].get("beats") or arms["C"]["beats"] != arms["D"].get("beats"):
        raise ValueError("controlled beats inputs differ")


class DevelopmentSlot(FormationContract):
    id: Nonempty
    characterId: Nonempty
    arm: Literal["A", "B", "C", "D", "CURRENT", "COVERED"]
    seed: FileAsset
    pair: FileAsset
    plan: FileAsset
    blueprint: FileAsset
    choice: FileAsset | None = None
    beats: FileAsset | None = None
    voiceBinding: FileAsset | None = None
    voicePolicy: FileAsset | None = None
    scenes: list[Scene]
    producer: FileAsset | None = None


class DevelopmentCohortV2(FormationContract):
    schemaVersion: Literal["persona-development-cohort-v2"] = "persona-development-cohort-v2"
    id: Nonempty
    profile: dict
    recipeHash: Sha256
    splitManifest: SplitManifest
    comparison: Literal["choice-voice", "selection"] = "choice-voice"
    slots: list[DevelopmentSlot] = Field(min_length=2)


def validate_development(cohort):
    from character_factory_poc.contracts.voice import VoiceBinding
    from character_factory_poc.stages.s7_traits.voice import verify_voice_binding

    validate_source_split(cohort.splitManifest)
    groups = defaultdict(dict)
    if len({s.id for s in cohort.slots}) != len(cohort.slots):
        raise ValueError("duplicate development slot id")
    for slot in cohort.slots:
        from character_factory_poc.stages.persona_quality.producers import (
            verify_development_producer,
        )

        verify_development_producer(slot)
        if slot.arm in groups[slot.characterId]:
            raise ValueError("duplicate development arm")
        groups[slot.characterId][slot.arm] = slot
        if len(slot.scenes) != 2 or any(len(s.turns) != 6 for s in slot.scenes):
            raise ValueError("development requires two scenes of six replies")
        for scene in slot.scenes:
            for turn in scene.turns:
                next_neutral_user(turn)
        for key in (
            "seed",
            "pair",
            "plan",
            "blueprint",
            "choice",
            "beats",
            "voiceBinding",
            "voicePolicy",
        ):
            asset = getattr(slot, key)
            if asset:
                asset.verify()
        if slot.arm in {"C", "D", "CURRENT", "COVERED"}:
            if not slot.voiceBinding or not slot.beats:
                raise ValueError("voice control needs a frozen binding and beats")
            binding = VoiceBinding.model_validate(read_json(slot.voiceBinding.verify()))
            if slot.arm == "C" and (binding.status != "DRAFT" or binding.packPath is not None):
                raise ValueError("C must use a generated draft voice control")
            if slot.arm in {"D", "CURRENT", "COVERED"}:
                if not slot.voicePolicy:
                    raise ValueError("D needs an approved voice policy")
                pack = verify_voice_binding(
                    binding, read_json(slot.plan.verify()), read_json(slot.voicePolicy.verify())
                )
                verify_voice_split(pack, cohort.splitManifest)
    for arms in groups.values():
        if cohort.comparison == "selection":
            if set(arms) != {"CURRENT", "COVERED"}:
                raise ValueError("selection comparison requires CURRENT/COVERED")
            from character_factory_poc.stages.persona_quality.producers import DevelopmentProducer

            receipts = [
                DevelopmentProducer.model_validate(read_json(s.producer.verify()))
                for s in arms.values()
            ]
            if receipts[0].assets != receipts[1].assets:
                raise ValueError(
                    "selection comparison must share all twelve source dialogues and other inputs"
                )
            if len({body_hash([d.model_dump() for d in s.scenes]) for s in arms.values()}) != 1:
                raise ValueError("controlled user inputs differ")
            continue
        if set(arms) != {"A", "B", "C", "D"}:
            raise ValueError("each development character requires A/B/C/D")
        from character_factory_poc.stages.persona_quality.producers import DevelopmentProducer

        producers = {
            a: DevelopmentProducer.model_validate(read_json(s.producer.verify()))
            for a, s in arms.items()
        }
        if (
            len({p.assets["systemRules"].sha256 for p in producers.values()}) != 1
            or len(
                {
                    p.assets["profile" if a == "A" else "compilerProfile"].sha256
                    for a, p in producers.items()
                }
            )
            != 1
        ):
            raise ValueError("controlled system rules/compiler profile differs")
        if (
            producers["B"].assets["voiceBinding"].sha256
            != producers["C"].assets["voiceBinding"].sha256
        ):
            raise ValueError("controlled generated voice differs between B and C")
        if len({s.seed.sha256 for s in arms.values()}) != 1:
            raise ValueError("controlled seed differs")
        check_controlled_hashes(
            {
                a: dict(
                    choice=s.choice.sha256 if s.choice else None,
                    blueprint=s.blueprint.sha256,
                    beats=s.beats.sha256 if s.beats else None,
                )
                for a, s in arms.items()
            }
        )
        inputs = [body_hash([d.model_dump() for d in s.scenes]) for s in arms.values()]
        if len(set(inputs)) != 1:
            raise ValueError("controlled user inputs differ")


def verify_voice_split(pack, manifest):
    from character_factory_poc.stages.s7_traits.voice import resolved_voice_sources

    actual = {e.sourceGroupId for e in pack.examples}
    validation = {e.sourceGroupId for e in pack.validationExamples}
    provided = {r.sourceGroupId for r in manifest.rows if r.split == "injection"}
    held = {r.sourceGroupId for r in manifest.rows if r.split == "voice-validation"}
    if not actual <= provided or not validation <= held:
        raise ValueError("split manifest does not cover actual injected/validation voice inputs")
    for example, path, split in resolved_voice_sources(pack):
        matching = [
            row
            for row in manifest.rows
            if row.split == split
            and row.sourceGroupId == example.sourceGroupId
            and Path(row.path).resolve() == path.resolve()
            and row.sha256 == example.sourceSha256
            and row.fieldPath == example.fieldPath
            and row.originalConversationId == example.originalConversationId
        ]
        if not matching:
            raise ValueError("voice source audit is disconnected from actual source files/quotes")
        for row in matching:
            raw = read_json(row.verify()) if path.suffix == ".json" else path.read_text("utf-8")
            if field_text(raw, row.fieldPath) != example.sourceQuote:
                raise ValueError("voice source audit quote mismatch")


def validate_frozen_split(cohort):
    path = Path(cohort.overlapAudit)
    if not path.is_file() or sha256_file(path) != cohort.profile.get("splitManifestSha256"):
        raise ValueError("frozen source split manifest is missing or differs from profile")
    manifest = SplitManifest.model_validate(read_json(path))
    validate_source_split(manifest)
    split = "holdout" if cohort.split == "holdout" else "development"
    snapshots = []
    for row in manifest.rows:
        if row.split == split:
            raw = read_json(row.verify())
            snapshots.append(field_text(raw, row.fieldPath) if row.fieldPath else raw)
    for slot in cohort.slots:
        for scene in slot.scenes:
            if dump_scene(scene) not in snapshots:
                raise ValueError("actual evaluation scene is absent from the source split audit")
            for turn in scene.turns:
                next_neutral_user(turn)
    return manifest


def dump_scene(scene):
    return json.loads(scene.model_dump_json())
