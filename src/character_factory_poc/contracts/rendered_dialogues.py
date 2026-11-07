"""Rendered text and independent per-turn meaning-preservation evidence."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.choice_design import Verdict
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256


class RenderedTurn(FormationContract):
    turnId: Nonempty
    role: Literal["user", "assistant"]
    content: Nonempty


class RenderedDialogue(FormationContract):
    dialogueId: Nonempty
    turns: list[RenderedTurn] = Field(min_length=2)


@register("rendered-dialogues-draft-v1")
class RenderedDraft(FormationContract):
    dialogues: list[RenderedDialogue] = Field(min_length=1)


@register("rendered-dialogues-v1")
class RenderedDialogues(RenderedDraft):
    schemaVersion: Literal["rendered-dialogues-v1"] = "rendered-dialogues-v1"
    characterId: Nonempty
    traitRevision: Nonempty
    beatsSha256: Sha256
    voiceBindingSha256: Sha256


class PreservationItem(FormationContract):
    turnId: Nonempty
    quote: Nonempty
    actPreserved: Verdict
    factsPreserved: Verdict
    ownerPreserved: Verdict
    statePreserved: Verdict
    toneAppropriate: Verdict
    noUnplannedClaims: Verdict
    coverageFaithful: Verdict
    reason: Nonempty


@register("preservation-report-v1")
class PreservationReport(FormationContract):
    schemaVersion: Literal["preservation-report-v1"] = "preservation-report-v1"
    inputSha256: Sha256 | None = None
    status: Verdict
    items: list[PreservationItem] = Field(min_length=1)
