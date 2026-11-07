#!/usr/bin/env python3
"""Offline regression reproductions for qualification-review findings 1, 3, 4.

Run from the repository root:
    .venv/bin/python -B work/persona-quality-floor/qualification-review-repro.py

The reviewed implementation returns QUALIFIED in all three invalid cases, so
the assertions are RED there. Correct rejection makes each test GREEN. A valid
control must qualify first, preventing unrelated blanket rejection from passing.
All fixture files are virtual. Only prompt loading/hash I/O is stubbed; the
production cohort/review validation and report verdict remain real. This is
synthetic aggregation evidence, not a real-provider qualification run.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.contracts.formation import QualityProfile
from character_factory_poc.stages.persona_quality import report
from character_factory_poc.stages.persona_quality.protocol import Cohort, canonical_hash


def make_cohort(*, natural_min: int = 6, uneven_runs: bool = False) -> dict:
    """Minimal 8-character/16-slot holdout, with seven scenes and five choices."""
    profile = QualityProfile.model_validate(
        dict(
            profileId="review-repro",
            scope={},
            thresholds=dict(naturalScenesPerArtifactMin=natural_min),
            thresholdsFrozen=True,
            rubricVersion="v1",
            rubricSha256="b" * 64,
            recipeHash="a" * 64,
            splitManifestSha256="c" * 64,
            protocolSha256="d" * 64,
            modelBinding=dict(
                provider="synthetic-provider",
                providerPath="https://unused.invalid/v1",
                model="bound-model",
                revision="frozen-revision",
                reasoningSettings={},
                temperature=0.7,
                maxOutputTokens=1000,
                systemAssemblyVersion="v1",
                contextLimit=24000,
            ),
        )
    ).model_dump(mode="json")
    scenes = [
        dict(
            id=f"s{i}",
            turns=[dict(user="hello") for _ in range(6)],
            expectedChoices={1: "expected choice"} if i < 5 else {},
        )
        for i in range(6)
    ] + [dict(id="long", turns=[dict(user="hello") for _ in range(24)])]
    character_ids = (
        ["c0"] * 9 + [f"c{i}" for i in range(1, 8)]
        if uneven_runs
        else [f"c{i // 2}" for i in range(16)]
    )
    return dict(
        id="review-repro",
        split="holdout",
        profile=profile,
        recipeHash="a" * 64,
        rubricHash="b" * 64,
        independent=True,
        overlapAudit="synthetic independent-review fixture",
        expectedBeforeFormation=True,
        formation=True,
        slots=[
            dict(
                id=f"r{i}",
                characterId=character_id,
                recipe="new",
                root=f"/virtual/input/{i}",
                scenes=copy.deepcopy(scenes),
            )
            for i, character_id in enumerate(character_ids)
        ],
    )


def evaluate(
    *,
    missing_second_reviewers=False,
    stricter_threshold=False,
    uneven_runs=False,
    second_collapse=False,
):
    raw = make_cohort(natural_min=7 if stricter_threshold else 6, uneven_runs=uneven_runs)
    try:
        cohort = Cohort.model_validate(raw)
    except ValidationError as exc:
        # Rejecting the invalid 9+1+1+1+1+1+1+1 layout during preflight is valid.
        # Other construction errors must surface as fixture errors.
        if not uneven_runs:
            raise
        return dict(status="NOT_QUALIFIED", reasons=[str(exc)])

    digest = canonical_hash(cohort)
    pair = SimpleNamespace(long=SimpleNamespace(text="system", sha256=sha256_text("system")))
    files = {
        "/virtual/run/cohort.json": json.dumps(cohort.model_dump(mode="json")),
        "/virtual/run/registration.json": json.dumps(
            dict(
                synthetic=False,
                cohortHash=digest,
                observedRecipeHash=cohort.recipeHash,
                slotIds=[s.id for s in cohort.slots],
            )
        ),
    }
    reviews = dict(cohortHash=digest, scenes={}, blueprintFaithful={})
    for slot in cohort.slots:
        files[f"/virtual/run/artifacts/{slot.id}.json"] = json.dumps(
            dict(path="/virtual/pair.json", sha256="e" * 64)
        )
        reviews["blueprintFaithful"][slot.id] = True
        for scene in slot.scenes:
            body = dict(
                reviewer="human-one",
                sawLLMCandidatesFirst=False,
                naturalness=1,
                collapse=False,
                turns=[
                    dict(turn=n, voiceOK=True, majorTypes=[], evidence="", choiceOK=True)
                    for n in range(1, len(scene.turns) + 1)
                ],
            )
            second = None
            if scene.id in ("s0", "long"):
                second = copy.deepcopy(body)
                second["reviewer"] = "human-two"
                if second_collapse:
                    second["collapse"] = True
                if missing_second_reviewers:
                    second = {"naturalness": 1}
            review = dict(body, second=second, adjudication=None)
            if stricter_threshold and slot.id == "r0" and scene.id == "s1":
                review["naturalness"] = 0  # Six usable scenes; frozen minimum is seven.
            reviews["scenes"][f"{slot.id}/{scene.id}"] = review

            history = [dict(role="system", content=pair.long.text)]
            for n in range(1, len(scene.turns) + 1):
                history.append(dict(role="user", content="hello"))
                files[f"/virtual/run/dialogues/{slot.id}/{scene.id}/{n:02}.json"] = json.dumps(
                    dict(
                        status="OK",
                        user="hello",
                        assistant="ok",
                        cohortHash=digest,
                        systemSha256=pair.long.sha256,
                        requestSha256=canonical_hash(history),
                        responseSha256=sha256_text("ok"),
                        turn=n,
                    )
                )
                history.append(dict(role="assistant", content="ok"))
    files["/virtual/reviews.json"] = json.dumps(reviews)
    with (
        patch.object(report, "load_prompt_pair", lambda path: pair),
        patch.object(report, "sha256_file", lambda path: "e" * 64),
        patch.object(Path, "exists", lambda path: str(path) in files),
        patch.object(Path, "read_text", lambda path, *args, **kwargs: files[str(path)]),
    ):
        return report.report_qualification(Path("/virtual/run"), Path("/virtual/reviews.json"))


class QualificationReviewRepro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = evaluate()
        if result["status"] != "QUALIFIED":
            raise AssertionError(f"Valid control must qualify; fixture is not isolated: {result}")

    def test_finding_1_missing_second_reviewer_identity_must_reject(self):
        result = evaluate(missing_second_reviewers=True)
        self.assertEqual(result["status"], "NOT_QUALIFIED", result)

    def test_finding_3_frozen_seven_scene_minimum_must_reject_six(self):
        result = evaluate(stricter_threshold=True)
        self.assertEqual(result["status"], "NOT_QUALIFIED", result)

    def test_second_review_collapse_disagreement_requires_resolution(self):
        result = evaluate(second_collapse=True)
        self.assertEqual(result["status"], "NOT_QUALIFIED", result)

    def test_finding_4_nine_runs_and_seven_singletons_must_reject(self):
        result = evaluate(uneven_runs=True)
        self.assertEqual(result["status"], "NOT_QUALIFIED", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
