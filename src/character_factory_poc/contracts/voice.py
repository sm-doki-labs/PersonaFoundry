"""Voice source evidence is distinct from generated dialogue provenance."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256


class VoiceExample(FormationContract):
    id: Nonempty
    situation: Nonempty
    relationship: Nonempty
    emotion: Nonempty
    channel: Literal["text"] = "text"
    styleView: Nonempty
    sourceFile: Nonempty
    sourceSha256: Sha256
    fieldPath: Nonempty
    sourceQuote: Nonempty
    sourceGroupId: Nonempty
    originalConversationId: Nonempty
    material: Literal["human-edited", "approved-data", "model-draft"]


class VoiceValidationExample(FormationContract):
    id: Nonempty
    styleView: Nonempty
    sourceGroupId: Nonempty
    originalConversationId: Nonempty
    sourceFile: Nonempty
    sourceSha256: Sha256
    fieldPath: Nonempty
    sourceQuote: Nonempty
    material: Literal["human-edited", "approved-data", "model-draft"]


@register("voice-pack-v1")
class VoicePack(FormationContract):
    schemaVersion: Literal["voice-pack-v1"] = "voice-pack-v1"
    packId: Nonempty
    version: Nonempty
    rules: list[Nonempty] = Field(min_length=1)
    doNotUseWhen: list[Nonempty]
    tags: list[Nonempty] = Field(min_length=1)
    examples: list[VoiceExample] = Field(min_length=20)
    validationExamples: list[VoiceValidationExample] = Field(min_length=1)
    preprocessingVersion: Nonempty
    approvalFile: Nonempty
    approvalSha256: Sha256

    def check_split(self):
        groups = {e.sourceGroupId for e in self.examples}
        if groups & {e.sourceGroupId for e in self.validationExamples}:
            raise ValueError("voice source group overlaps injection and validation")
        if len({e.id for e in self.examples}) != len(self.examples):
            raise ValueError("duplicate voice example id")


class BoundVoiceExample(FormationContract):
    id: Nonempty
    situation: Nonempty
    relationship: Nonempty
    emotion: Nonempty
    styleView: Nonempty
    sourceGroupId: Nonempty


@register("voice-binding-v1")
class VoiceBinding(FormationContract):
    schemaVersion: Literal["voice-binding-v1"] = "voice-binding-v1"
    status: Literal["READY", "DRAFT", "VOICE_SOURCE_MISSING"]
    characterId: Nonempty
    planSha256: Sha256
    policySha256: Sha256
    packId: str | None = None
    packPath: str | None = None
    packSha256: Sha256 | None = None
    approvalIndexPath: str | None = None
    approvalIndexSha256: Sha256 | None = None
    rules: list[str] = Field(default_factory=list)
    doNotUseWhen: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    examples: list[BoundVoiceExample] = Field(default_factory=list)
    reason: Nonempty
