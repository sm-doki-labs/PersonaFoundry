"""Choice provenance contracts; semantic judgments run outside shape retries."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ChoiceArtifactRef
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256
from character_factory_poc.contracts.planning import CharacterPlanV2

PROFILE_ID = "ko-text-choice-voice-long-v2"
Verdict = Literal["PASS", "FAIL", "UNRESOLVED"]


class SeedRequirement(FormationContract):
    requirementId: Nonempty
    field: Literal[
        "personality", "background", "notes", "job", "age", "gender", "userEdits", "selectedTraits"
    ]
    quote: Nonempty
    kind: Literal["fixed", "free", "open"]


@register("seed-requirements-draft-v1")
class SeedRequirementsDraft(FormationContract):
    requirements: list[SeedRequirement] = Field(min_length=1)


@register("seed-requirements-v1")
class SeedRequirements(SeedRequirementsDraft):
    schemaVersion: Literal["seed-requirements-v1"] = "seed-requirements-v1"
    characterId: Nonempty
    seedRev: Nonempty
    seedSha256: Sha256
    supersededRequirementIds: list[Nonempty] = Field(default_factory=list)
    previousRequirements: ChoiceArtifactRef | None = None


class DesignedChoice(FormationContract):
    choiceRuleId: Nonempty
    traitId: Nonempty
    requirementIds: list[Nonempty] = Field(min_length=1)
    situation: Nonempty
    firstMove: Nonempty
    attention: Nonempty
    priority: Nonempty
    acceptedCost: Nonempty
    activateWhen: Nonempty
    doNotActivateWhen: Nonempty
    switchWhen: Nonempty
    alternative: Nonempty
    wrongTransformation: Nonempty
    classification: Literal["shared", "contrast", "not_applicable"]
    classificationReason: Nonempty


class ChoiceDesignDraft(FormationContract):
    variantId: Nonempty
    coverage: dict[str, Literal["implemented", "discretion", "unresolved"]]
    rules: list[DesignedChoice] = Field(min_length=1)


@register("choice-design-v1")
class ChoiceDesign(ChoiceDesignDraft):
    schemaVersion: Literal["choice-design-v1"] = "choice-design-v1"
    characterId: Nonempty
    planRev: Nonempty
    seedSha256: Sha256
    requirementsSha256: Sha256
    planSha256: Sha256


@register("plan-variants-output-v2")
class PlanVariantsOutputV2(FormationContract):
    variants: list[CharacterPlanV2] = Field(min_length=1, max_length=5)
    designs: list[ChoiceDesignDraft] = Field(min_length=1, max_length=5)
    axisNote: str = ""


class ChoiceReviewItem(FormationContract):
    variantId: Nonempty
    requirementId: Nonempty
    status: Verdict
    quote: Nonempty
    reason: Nonempty


@register("choice-review-v1")
class ChoiceReview(FormationContract):
    schemaVersion: Literal["choice-review-v1"] = "choice-review-v1"
    inputSha256: Sha256 | None = None
    status: Verdict
    inventoryComplete: bool
    items: list[ChoiceReviewItem]
    contrastStatus: Verdict
    sharedStatus: Verdict
    evidence: list[Nonempty] = Field(min_length=1)


@register("plan-variants-v2")
class PlanVariantsV2(FormationContract):
    schemaVersion: Literal["plan-variants-v2"] = "plan-variants-v2"
    characterId: Nonempty
    planRev: Nonempty
    seedRev: Nonempty
    seedSha256: Sha256
    mode: Literal["variants", "own"] = "variants"
    axisNote: str = ""
    candidates: list[CharacterPlanV2] = Field(min_length=1)
    requirements: ChoiceArtifactRef
    designs: dict[str, ChoiceArtifactRef]
    review: ChoiceArtifactRef


@register("plan-selection-v2")
class PlanSelectionV2(FormationContract):
    schemaVersion: Literal["plan-selection-v2"] = "plan-selection-v2"
    characterId: Nonempty
    planRev: Nonempty
    selected: Nonempty
    seed: ChoiceArtifactRef
    requirements: ChoiceArtifactRef
    plan: ChoiceArtifactRef
    choice: ChoiceArtifactRef
    review: ChoiceArtifactRef
    editedFields: list[str] = Field(default_factory=list)
