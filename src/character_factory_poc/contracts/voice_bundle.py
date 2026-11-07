"""Pinned source bundle and deterministic example-coverage policy."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.formation import (
    FormationContract,
    Nonempty,
    PersonaBundle,
    Sha256,
)


class ExampleCoverage(FormationContract):
    tags: list[Literal["ordinary", "emotion", "decision", "change"]]
    ruleIds: list[Nonempty]


@register("coverage-policy-v1")
class CoveragePolicy(FormationContract):
    schemaVersion: Literal["coverage-policy-v1"] = "coverage-policy-v1"
    requiredRuleIds: list[Nonempty]
    requiredTags: list[str] = Field(
        default_factory=lambda: ["ordinary", "emotion", "decision", "change"]
    )
    coverage: dict[str, ExampleCoverage]
    examples: Literal[4] = 4


class BundleAsset(FormationContract):
    path: Nonempty
    sha256: Sha256


@register("persona-bundle-v2")
class PersonaBundleV2(PersonaBundle):
    schemaVersion: Literal["persona-bundle-v2"] = "persona-bundle-v2"
    sourceAssets: dict[str, BundleAsset]
    recipeSha256: Sha256
    coveragePolicySha256: Sha256
    examplesUsage: Literal["injected", "review-only"] = "injected"
