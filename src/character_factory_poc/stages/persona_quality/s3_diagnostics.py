"""Audit captured S3 example interventions; no model calls or qualification."""

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.formation import FormationContract, Nonempty
from character_factory_poc.contracts.planning import PlanVariantsOutput
from character_factory_poc.stages.persona_quality.choice_voice_protocol import FileAsset
from character_factory_poc.stages.s3_plan.choice_design import body_hash


class S3DiagnosticArm(FormationContract):
    id: Nonempty
    arm: Literal["original", "removed", "reordered"]
    seed: FileAsset
    template: FileAsset
    examples: dict[str, FileAsset]
    exampleOrder: list[str]
    renderedInput: FileAsset
    firstAttempt: FileAsset
    modelBinding: dict
    firstOutput: FileAsset | None = None
    failure: FileAsset | None = None


class S3Diagnostic(FormationContract):
    schemaVersion: Literal["s3-diagnostic-v1"] = "s3-diagnostic-v1"
    id: Nonempty
    expectedCandidates: int = Field(ge=1, le=5)
    arms: list[S3DiagnosticArm] = Field(min_length=3, max_length=3)


def validate_s3_diagnostic(manifest):
    groups = {a.arm: a for a in manifest.arms}
    if set(groups) != {"original", "removed", "reordered"}:
        raise ValueError("S3 diagnostic needs all three first attempts")
    first = groups["original"]
    if len({a.id for a in manifest.arms}) != 3 or len(first.exampleOrder) < 2:
        raise ValueError("S3 diagnostic IDs/examples are incomplete")
    if (
        len(set(first.exampleOrder)) != len(first.exampleOrder)
        or set(first.exampleOrder) != first.examples.keys()
    ):
        raise ValueError("S3 diagnostic example inventory mismatch")
    if (
        groups["removed"].exampleOrder
        or groups["reordered"].exampleOrder == first.exampleOrder
        or sorted(groups["reordered"].exampleOrder) != sorted(first.exampleOrder)
    ):
        raise ValueError("S3 diagnostic must remove or reorder only the same examples")
    outputs = {}
    for arm in manifest.arms:
        if (arm.seed, arm.template, arm.examples, arm.modelBinding) != (
            first.seed,
            first.template,
            first.examples,
            first.modelBinding,
        ):
            raise ValueError("S3 diagnostic changes inputs outside example intervention")
        template = arm.template.verify().read_text("utf-8")
        if template.count("{{SEED_JSON}}") != 1 or template.count("{{BEHAVIOR_EXAMPLES}}") != 1:
            raise ValueError("S3 diagnostic prompt needs explicit single intervention placeholders")
        seed = json.dumps(read_json(arm.seed.verify()), ensure_ascii=False, sort_keys=True)
        examples = {key: asset.verify().read_text("utf-8") for key, asset in arm.examples.items()}
        rendered = template.replace("{{SEED_JSON}}", seed).replace(
            "{{BEHAVIOR_EXAMPLES}}", "\n".join(examples[e] for e in arm.exampleOrder)
        )
        if arm.renderedInput.verify().read_text("utf-8") != rendered:
            raise ValueError("S3 diagnostic actual prompt differs from controlled inputs")
        if bool(arm.firstOutput) == bool(arm.failure):
            raise ValueError("S3 diagnostic needs exactly one first output or failure")
        result = arm.firstOutput or arm.failure
        result.verify()
        attempt = read_json(arm.firstAttempt.verify())
        if attempt != dict(
            attemptOrdinal=1,
            inputSha256=arm.renderedInput.sha256,
            modelBinding=arm.modelBinding,
            resultSha256=result.sha256,
        ):
            raise ValueError("S3 diagnostic first attempt is disconnected from actual input/output")
        if arm.firstOutput:
            parsed = PlanVariantsOutput.model_validate(read_json(result.verify()))
            if (
                len(parsed.variants) != manifest.expectedCandidates
                or len({v.variantId for v in parsed.variants}) != manifest.expectedCandidates
            ):
                raise ValueError("S3 diagnostic first output candidate inventory mismatch")
            outputs[arm.id] = parsed
    return outputs


def export_s3_diagnostic(manifest, out):
    """Prepare blind position labels from preserved first outputs, including failures."""
    manifest = S3Diagnostic.model_validate(manifest)
    outputs = validate_s3_diagnostic(manifest)
    out = Path(out)
    write_once_json(out / "manifest.json", manifest.model_dump(mode="json"))
    packet = []
    mapping = {}
    for i, arm in enumerate(
        sorted(manifest.arms, key=lambda a: sha256_text(manifest.id + a.id)), 1
    ):
        for position, variant in enumerate(
            outputs[arm.id].variants if arm.id in outputs else [], 1
        ):
            key = f"S{i:03}/{position}"
            mapping[key] = dict(armId=arm.id, arm=arm.arm, candidatePosition=position)
            plan = variant.model_dump(mode="json")
            for field in (
                "schemaVersion",
                "characterId",
                "planRev",
                "seedRev",
                "variantId",
                "appearanceRev",
                "evidence",
                "notes",
            ):
                plan.pop(field, None)
            packet.append(
                dict(
                    id=key, candidatePosition=position, seed=read_json(arm.seed.verify()), plan=plan
                )
            )
    write_once_json(out / "blind-mapping.json", mapping)
    write_once_json(out / "review-packet.json", packet)
    write_once_json(
        out / "human-reviews-template.json",
        dict(
            manifestHash=body_hash(manifest.model_dump(mode="json")),
            candidates=[
                dict(id=p["id"], reviewer="", seedFaithful=None, choiceCategory="", evidence=[])
                for p in packet
            ],
        ),
    )
    return out


class CandidateReview(FormationContract):
    id: Nonempty
    reviewer: Nonempty
    seedFaithful: bool
    choiceCategory: Nonempty
    evidence: list[Nonempty] = Field(min_length=1)


class S3DiagnosticReviews(FormationContract):
    manifestHash: Nonempty
    candidates: list[CandidateReview]


def report_s3_diagnostic(out, human_reviews=None):
    out = Path(out)
    manifest = S3Diagnostic.model_validate(read_json(out / "manifest.json"))
    outputs = validate_s3_diagnostic(manifest)
    # Re-export also checks that review packets/mapping still match the frozen sources.
    export_s3_diagnostic(manifest.model_dump(mode="json"), out)
    packet = {p["id"]: p for p in read_json(out / "review-packet.json")}
    result = dict(
        status="METRICS_ONLY",
        qualityQualified=False,
        plannedCandidates=len(manifest.arms) * manifest.expectedCandidates,
        completedCandidates=sum(len(p.variants) for p in outputs.values()),
        failedArms=[a.id for a in manifest.arms if a.failure],
        humanReviewComplete=False,
        positionChoiceDistribution=[],
        seedFaithfulCandidates=None,
    )
    if human_reviews is not None:
        reviews = S3DiagnosticReviews.model_validate(read_json(Path(human_reviews)))
        if (
            reviews.manifestHash != body_hash(manifest.model_dump(mode="json"))
            or len(reviews.candidates) != len(packet)
            or {r.id for r in reviews.candidates} != packet.keys()
        ):
            raise ValueError("S3 diagnostic human review coverage/hash mismatch")
        mapping = read_json(out / "blind-mapping.json")
        counts = Counter()
        for review in reviews.candidates:
            text = json.dumps(packet[review.id]["plan"], ensure_ascii=False)
            if any(q not in text for q in review.evidence):
                raise ValueError("S3 diagnostic human review quote mismatch")
            record = mapping[review.id]
            counts[(record["arm"], record["candidatePosition"], review.choiceCategory)] += 1
        result.update(
            humanReviewComplete=True,
            seedFaithfulCandidates=sum(r.seedFaithful for r in reviews.candidates),
            positionChoiceDistribution=[
                dict(arm=a, candidatePosition=p, choiceCategory=c, count=n)
                for (a, p, c), n in sorted(counts.items())
            ],
        )
    return result
