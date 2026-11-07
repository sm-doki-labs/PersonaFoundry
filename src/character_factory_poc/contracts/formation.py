"""Bounded formation artifacts. Structural validity is not quality qualification.

Source hashes always identify stored file bytes (common.canonical.sha256_file),
including write_once_json's formatting and trailing newline. Models do not
re-encode sources to guess their hashes or verify quotes against absent files.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, JsonValue, StringConstraints, model_validator

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ChoiceArtifactRef, Strict
from character_factory_poc.contracts.persona import PromptTextV2, TraitSheet

Nonempty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Rate = Annotated[float, Field(ge=0, le=1)]
Positive = Annotated[int, Field(gt=0)]


class FormationContract(Strict):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SupportScope(FormationContract):
    language: Literal["ko"] = "ko"
    channel: Literal["text"] = "text"
    prompt: Literal["long"] = "long"
    setting: Literal["contemporary-korea"] = "contemporary-korea"
    adultsOnly: Literal[True] = True
    genre: Literal["romance"] = "romance"


class QualityModelBinding(FormationContract):
    provider: Nonempty
    providerPath: Nonempty
    model: Nonempty
    revision: Nonempty | None = None
    reasoningSettings: dict[str, JsonValue]
    temperature: float = Field(ge=0, le=2)
    maxOutputTokens: Positive
    systemAssemblyVersion: Nonempty
    contextLimit: Positive


class QualityThresholds(FormationContract):
    heldoutCharacters: Positive = 8
    runsPerCharacter: Positive = 2
    scenesPerArtifact: Positive = 7
    assistantTurnsPerArtifact: Positive = 60
    naturalScenesPerArtifactMin: Positive = 6
    naturalSceneRateMin: Rate = 0.9
    decisionItemsPerArtifact: Positive = 5
    decisionPassesPerArtifactMin: Positive = 4
    voiceTurnRateMin: Rate = 0.9
    majorErrorsPerArtifactMax: int = Field(default=1, ge=0)
    sameErrorTypePerArtifactMax: int = Field(default=1, ge=0)
    majorErrorTurnRateMax: Rate = 0.01
    collapseScenesMax: int = Field(default=0, ge=0)
    doubleReviewedScenes: Positive = 32
    binaryAgreementRateMin: Rate = 0.85
    longMaxChars: Positive = 8000
    shortMaxChars: Positive = 2400

    @model_validator(mode="after")
    def verify_counts(self) -> QualityThresholds:
        if self.naturalScenesPerArtifactMin > self.scenesPerArtifact:
            raise ValueError("natural scene minimum exceeds planned scenes")
        if self.decisionPassesPerArtifactMin > self.decisionItemsPerArtifact:
            raise ValueError("decision minimum exceeds planned items")
        scenes = self.heldoutCharacters * self.runsPerCharacter * self.scenesPerArtifact
        if self.doubleReviewedScenes > scenes:
            raise ValueError("double reviews exceed planned scenes")
        return self


@register("persona-quality-profile-v1")
class QualityProfile(FormationContract):
    schemaVersion: Literal["persona-quality-profile-v1"] = "persona-quality-profile-v1"
    profileId: Nonempty
    scope: SupportScope
    modelBinding: QualityModelBinding | None = None
    thresholds: QualityThresholds
    thresholdsFrozen: bool = False
    rubricVersion: Nonempty
    rubricSha256: Sha256 | None = None
    recipeHash: Sha256 | None = None
    splitManifestSha256: Sha256 | None = None
    protocolSha256: Sha256 | None = None


def load_quality_profile(path: str | Path | None = None) -> QualityProfile:
    resource = (
        Path(path)
        if path is not None
        else files("character_factory_poc").joinpath("resources/persona-quality-profile-v1.json")
    )
    return QualityProfile.model_validate_json(resource.read_text(encoding="utf-8"))


class SourceRef(FormationContract):
    kind: Literal["plan", "trait", "reference", "blueprint", "dialogue"]
    ref: Nonempty
    version: Nonempty
    sha256: Sha256
    fieldPath: Nonempty
    quote: Nonempty


@register("qualification-result-v1")
class QualificationResult(FormationContract):
    schemaVersion: Literal["qualification-result-v1"] = "qualification-result-v1"
    status: Literal["NOT_RUN", "METRICS_ONLY", "NOT_QUALIFIED", "QUALIFIED"] = "NOT_RUN"
    profileId: Nonempty
    profileSha256: Sha256 | None = None
    cohortHash: Sha256 | None = None
    failedSlots: list[Nonempty] = Field(default_factory=list)
    comparisonArtifacts: int = Field(default=0, ge=0)
    plannedArtifacts: int = Field(ge=0)
    completedArtifacts: int = Field(ge=0)
    reasons: list[Nonempty] = Field(default_factory=list)
    metrics: dict[str, JsonValue] | None = None
    failureRefs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_envelope(self) -> QualificationResult:
        if self.completedArtifacts > self.plannedArtifacts:
            raise ValueError("completedArtifacts exceeds plannedArtifacts")
        if self.status == "QUALIFIED" and (
            not self.plannedArtifacts
            or self.completedArtifacts != self.plannedArtifacts
            or self.reasons
            or self.failureRefs
            or not self.metrics
        ):
            raise ValueError("QUALIFIED requires complete artifacts, metrics and no failures")
        return self


def validate_qualification_result(
    data: Mapping[str, Any] | QualificationResult,
    profile: Mapping[str, Any] | QualityProfile,
    *,
    scope_supported: bool = False,
    human_review_complete: bool = False,
    independence_verified: bool = False,
) -> QualificationResult:
    """Final evidence gates, never a metric scorer or an automatic qualification.

    The evaluator owns per-artifact thresholds, denominators and raw evidence.
    Only an explicitly claimed QUALIFIED status is considered here; other states
    are preserved. Missing evidence fails closed rather than being inferred.
    """
    result = QualificationResult.model_validate(data)
    bound = QualityProfile.model_validate(profile)
    if result.status != "QUALIFIED":
        return result
    reasons = []
    serialized = (
        json.dumps(bound.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if result.profileSha256 != sha256_text(serialized):
        reasons.append("evaluated profile hash mismatch")
    if result.profileId != bound.profileId:
        reasons.append("profileId mismatch")
    if not scope_supported:
        reasons.append("unsupported or unverified scope")
    binding = bound.modelBinding
    if binding is None or binding.revision is None:
        reasons.append("modelBinding is not fully pinned")
    if not bound.thresholdsFrozen:
        reasons.append("thresholds are still a proposal")
    for field in ("rubricSha256", "recipeHash", "splitManifestSha256", "protocolSha256"):
        if getattr(bound, field) is None:
            reasons.append(f"missing {field}")
    planned = bound.thresholds.heldoutCharacters * bound.thresholds.runsPerCharacter
    if result.plannedArtifacts != planned:
        reasons.append("plannedArtifacts differs from frozen profile denominator")
    if not independence_verified:
        reasons.append("held-out independence unverified")
    if not human_review_complete:
        reasons.append("human review incomplete")
    if not reasons:
        return result
    return QualificationResult.model_validate(
        {
            **result.model_dump(mode="json"),
            "status": "METRICS_ONLY" if reasons == ["human review incomplete"] else "NOT_QUALIFIED",
            "reasons": reasons,
        }
    )


class DecisionRule(FormationContract):
    situation: Nonempty
    activateWhen: Nonempty
    doNotActivateWhen: Nonempty
    firstMove: Nonempty
    priority: Nonempty
    switchWhen: Nonempty
    wrongTransformation: Nonempty


class DecisionRuleV2(DecisionRule):
    choiceRuleId: Nonempty
    attention: Nonempty
    acceptedCost: Nonempty
    alternative: Nonempty


class VoiceProfile(FormationContract):
    speechLevel: Nonempty
    rhythm: Nonempty
    directness: Nonempty
    emotionalVariation: Nonempty
    relationshipDistance: Nonempty
    lexicon: list[Nonempty] = Field(min_length=1)
    avoidRepetition: list[Nonempty] = Field(min_length=1)


class OrdinaryModes(FormationContract):
    reacting: Nonempty
    selfStory: Nonempty
    playful: Nonempty
    listening: Nonempty
    affection: Nonempty


class FactPolicy(FormationContract):
    selfFiction: Nonempty
    userFacts: Nonempty
    sharedHistory: Nonempty
    proposalAgreementCancellation: Nonempty
    externalCurrentFacts: Nonempty
    mutableState: Nonempty


def _require_sources(refs: list[SourceRef], hashes: dict[str, str]) -> None:
    for kind, digest in hashes.items():
        matching = [ref for ref in refs if ref.kind == kind]
        if not matching or any(ref.sha256 != digest for ref in matching):
            raise ValueError(f"sourceRefs missing or mismatched {kind} hash")


@register("persona-blueprint-v1")
class PersonaBlueprint(FormationContract):
    schemaVersion: Literal["persona-blueprint-v1"] = "persona-blueprint-v1"
    characterId: Nonempty
    planRev: Nonempty
    planSha256: Sha256
    traitSheetSha256: Sha256
    decisionRules: list[DecisionRule] = Field(min_length=1)
    voiceProfile: VoiceProfile
    ordinaryModes: OrdinaryModes
    factPolicy: FactPolicy
    sourceRefs: list[SourceRef] = Field(min_length=1)
    unresolved: list[Nonempty] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_sources(self) -> PersonaBlueprint:
        _require_sources(self.sourceRefs, {"plan": self.planSha256, "trait": self.traitSheetSha256})
        return self


@register("persona-blueprint-v2")
class PersonaBlueprintV2(PersonaBlueprint):
    schemaVersion: Literal["persona-blueprint-v2"] = "persona-blueprint-v2"
    decisionRules: list[DecisionRuleV2] = Field(min_length=1)
    approvedChoiceRef: ChoiceArtifactRef


@register("formation-design-v2")
class FormationDesignV2(FormationContract):
    schemaVersion: Literal["formation-design-v2"] = "formation-design-v2"
    traitSheet: TraitSheet
    blueprint: PersonaBlueprintV2


@register("formation-draft-v2")
class FormationDraftV2(FormationContract):
    traitSheet: TraitSheet
    voiceProfile: VoiceProfile
    ordinaryModes: OrdinaryModes
    factPolicy: FactPolicy


@register("formation-design-v1")
class FormationDesign(FormationContract):
    schemaVersion: Literal["formation-design-v1"] = "formation-design-v1"
    traitSheet: TraitSheet
    blueprint: PersonaBlueprint

    @model_validator(mode="after")
    def verify_identity(self) -> FormationDesign:
        if (
            self.traitSheet.characterId != self.blueprint.characterId
            or self.traitSheet.planRev != self.blueprint.planRev
        ):
            raise ValueError("trait/blueprint characterId or planRev mismatch")
        return self


class FactRef(FormationContract):
    scope: Literal["canon", "example-local"]
    owner: Literal["character", "user", "shared", "external"]
    text: Nonempty
    source: SourceRef
    dialogueId: Nonempty | None = None

    @model_validator(mode="after")
    def verify_scope(self) -> FactRef:
        if self.scope == "example-local":
            if self.dialogueId is None or self.source.kind != "dialogue":
                raise ValueError("example-local facts require dialogueId and dialogue source")
        elif self.dialogueId is not None or self.source.kind == "dialogue":
            raise ValueError("canon facts cannot cite example dialogue sources")
        elif self.owner in ("user", "shared"):
            raise ValueError("user/shared example facts cannot become canon")
        return self


class DialoguePair(FormationContract):
    user: Nonempty
    assistant: Nonempty


class FormationDialogue(FormationContract):
    dialogueId: Nonempty
    category: Literal["ordinary", "boundary", "change"]
    selectionSlot: Literal[
        "ordinary-self", "playful-affection", "listening-conflict", "condition-owner-change"
    ]
    pairs: list[DialoguePair] = Field(min_length=2, max_length=6)
    factRefs: list[FactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_locality(self) -> FormationDialogue:
        category = {
            "ordinary-self": "ordinary",
            "playful-affection": "ordinary",
            "listening-conflict": "boundary",
            "condition-owner-change": "change",
        }[self.selectionSlot]
        if self.category != category:
            raise ValueError("category does not match selectionSlot")
        for fact in self.factRefs:
            if fact.scope == "example-local" and fact.dialogueId != self.dialogueId:
                raise ValueError("example-local fact belongs to another dialogue")
        return self


@register("formation-dialogues-v1")
class FormationDialogues(FormationContract):
    schemaVersion: Literal["formation-dialogues-v1"] = "formation-dialogues-v1"
    characterId: Nonempty
    traitRevision: Nonempty
    planSha256: Sha256
    traitSheetSha256: Sha256
    blueprintSha256: Sha256
    sourceRefs: list[SourceRef] = Field(min_length=1)
    dialogues: list[FormationDialogue] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def verify_composition(self) -> FormationDialogues:
        if len({d.dialogueId for d in self.dialogues}) != 12:
            raise ValueError("dialogue IDs must be unique")
        if Counter(d.category for d in self.dialogues) != {
            "ordinary": 8,
            "boundary": 2,
            "change": 2,
        }:
            raise ValueError("dialogues require 8 ordinary / 2 boundary / 2 change")
        if sum(len(d.pairs) == 6 for d in self.dialogues) < 2:
            raise ValueError("at least two dialogues must have six pairs")
        if len({d.selectionSlot for d in self.dialogues}) != 4:
            raise ValueError("all four selection slots are required")
        _require_sources(
            self.sourceRefs,
            {
                "plan": self.planSha256,
                "trait": self.traitSheetSha256,
                "blueprint": self.blueprintSha256,
            },
        )
        pinned = {
            "plan": self.planSha256,
            "trait": self.traitSheetSha256,
            "blueprint": self.blueprintSha256,
        }
        for dialogue in self.dialogues:
            for fact in dialogue.factRefs:
                if fact.scope == "canon" and (
                    fact.source.kind not in pinned or fact.source.sha256 != pinned[fact.source.kind]
                ):
                    raise ValueError("canon fact source differs from pinned source")
        return self


@register("persona-bundle-v1")
class PersonaBundle(FormationContract):
    schemaVersion: Literal["persona-bundle-v1"] = "persona-bundle-v1"
    characterId: Nonempty
    personaVersion: Nonempty
    planRev: Nonempty
    traitRevision: Nonempty
    planSha256: Sha256
    traitSheetSha256: Sha256
    blueprintSha256: Sha256
    dialoguesSha256: Sha256
    profileId: Nonempty
    profileSha256: Sha256
    compilerVersion: Nonempty
    compilerSha256: Sha256
    systemRulesRef: Nonempty
    systemRulesSha256: Sha256
    selectedDialogueIds: list[Nonempty] = Field(min_length=4, max_length=4)
    long: PromptTextV2

    @model_validator(mode="after")
    def verify_selection(self) -> PersonaBundle:
        if len(set(self.selectedDialogueIds)) != 4:
            raise ValueError("selectedDialogueIds must be four distinct IDs")
        return self
