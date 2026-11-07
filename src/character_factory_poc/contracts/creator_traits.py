"""Creator-selected authored behaviors; source evidence is not a measured personality score."""

from pydantic import Field

from character_factory_poc.contracts.common import Strict


class CreatorTrait(Strict):
    traitId: str = Field(min_length=1, max_length=80)
    behavior: str = Field(min_length=1, max_length=500)
    presetId: str = Field(min_length=1, max_length=80)
    sourceField: str = Field(min_length=1, max_length=200)
    catalogSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sourceCatalogSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
