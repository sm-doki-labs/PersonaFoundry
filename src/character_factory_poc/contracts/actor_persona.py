"""Actor-facing personality sentences, separate from authoring and evaluation."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.formation import FormationContract, Nonempty


class RuntimeContext(FormationContract):
    relationship: Nonempty | None = None
    scene: Nonempty | None = None
    speechLevel: Literal["CASUAL", "POLITE"] | None = None


@register("actor-persona-v1")
class RuntimePersona(FormationContract):
    schemaVersion: Literal["actor-persona-v1"] = "actor-persona-v1"
    facts: list[Nonempty]
    lifeAndTastes: list[Nonempty]
    disposition: list[Nonempty] = Field(min_length=1)
    wantsAndFears: list[Nonempty]
    readingAndTension: list[Nonempty]
    choices: list[Nonempty]
    voice: list[Nonempty] = Field(min_length=1)
    boundaries: list[Nonempty]
