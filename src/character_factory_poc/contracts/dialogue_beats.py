"""Dialogue content without rendered wording; example facts never become memory."""

from typing import Literal

from pydantic import Field, JsonValue

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256, SourceRef


class BeatFact(FormationContract):
    id: Nonempty
    text: Nonempty
    owner: Literal["character", "user", "shared", "external"]
    scope: Literal["canon", "example-local"]
    sourceRef: SourceRef | None = None


class DialogueBeat(FormationContract):
    turnId: Nonempty
    role: Literal["user", "assistant"]
    act: Nonempty
    facts: list[BeatFact]
    tone: Nonempty
    decisionRuleIds: list[Nonempty]
    stateBefore: dict[str, JsonValue]
    stateAfter: dict[str, JsonValue]


class BeatDialogue(FormationContract):
    dialogueId: Nonempty
    category: Literal["ordinary", "boundary", "change"]
    coverageTags: list[Literal["ordinary", "emotion", "decision", "change"]]
    relationship: Nonempty
    scene: Nonempty
    turns: list[DialogueBeat] = Field(min_length=2, max_length=12)


@register("formation-beats-draft-v1")
class FormationBeatsDraft(FormationContract):
    dialogues: list[BeatDialogue] = Field(min_length=1)


@register("formation-beats-v1")
class FormationBeats(FormationBeatsDraft):
    schemaVersion: Literal["formation-beats-v1"] = "formation-beats-v1"
    characterId: Nonempty
    traitRevision: Nonempty
    planSha256: Sha256
    blueprintSha256: Sha256
    choiceSha256: Sha256
