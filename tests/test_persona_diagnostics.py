import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import read_json
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
    DevelopmentCohortV2,
    validate_development,
)
from character_factory_poc.stages.persona_quality.producers import prepare_development_pair
from character_factory_poc.stages.persona_quality.report import report_qualification
from character_factory_poc.stages.persona_quality.run import run_qualification
from tests.test_choice_voice_development import development_case


def selection_case(tmp_path):
    ctx, cohort = development_case(tmp_path)
    d = next(s for s in cohort.slots if s.arm == "D")
    sources = read_json(d.producer.verify())["assets"]
    from pathlib import Path

    assets = {name: Path(ref["path"]) for name, ref in sources.items()}
    trait_root = assets["trait"].parent
    assets.update(
        profile=trait_root / "profile.json", coveragePolicy=trait_root / "coverage-policy.json"
    )
    slots = []
    for arm in ("CURRENT", "COVERED"):
        pair, producer = prepare_development_pair(arm, assets, tmp_path / arm)
        slots.append(
            dict(
                d.model_dump(),
                id=f"selection-{arm}",
                arm=arm,
                pair=pair.model_dump(),
                producer=producer.model_dump(),
            )
        )
    return ctx, DevelopmentCohortV2(
        **dict(cohort.model_dump(), comparison="selection", slots=slots)
    )


def test_s8_selection_compare_freezes_all_twelve_dialogues_and_counts_first_replies(tmp_path):
    ctx, cohort = selection_case(tmp_path)
    validate_development(cohort)
    model = FakeTextModel("fake-dialogue", {"*": "응, 조건을 확인할게"})
    run = run_qualification(
        ctx, cohort, tmp_path / "selection-eval", dialogue_model=model, token_counter=lambda _: 10
    )
    result = report_qualification(run)
    assert result["status"] == "METRICS_ONLY" and result["plannedReplies"] == 24
    assert result["completedReplies"] == 24
    assert len(model.requests) == 24


def test_s8_comparison_refuses_changed_producer_input(tmp_path):
    _, cohort = selection_case(tmp_path)
    changed = read_json(cohort.slots[0].producer.verify())
    path = changed["assets"]["dialogues"]["path"]
    from pathlib import Path

    Path(path).write_text("{}")
    assert sha256_file(Path(path)) != changed["assets"]["dialogues"]["sha256"]
    with pytest.raises(ValueError, match="hash"):
        validate_development(cohort)


def test_s3_diagnostic_tracks_all_positions_and_keeps_failed_arm(tmp_path):
    from character_factory_poc.stages.persona_quality.s3_diagnostics import (
        export_s3_diagnostic,
        report_s3_diagnostic,
    )

    manifest = s3_case(tmp_path)
    out = export_s3_diagnostic(manifest, tmp_path / "s3-review")
    result = report_s3_diagnostic(out)
    assert result["plannedCandidates"] == 9 and result["completedCandidates"] == 6
    assert len(result["failedArms"]) == 1 and not result["qualityQualified"]
    packet = read_json(out / "review-packet.json")
    assert len(packet) == 6 and all("arm" not in row for row in packet)


def test_s3_diagnostic_rejects_changes_outside_example_order(tmp_path):
    from pathlib import Path

    from character_factory_poc.stages.persona_quality.s3_diagnostics import export_s3_diagnostic

    manifest = s3_case(tmp_path)
    path = Path(manifest["arms"][1]["renderedInput"]["path"])
    path.write_text(path.read_text() + "추가 성격 지시")
    manifest["arms"][1]["renderedInput"]["sha256"] = sha256_file(path)
    with pytest.raises(ValueError, match="input|prompt"):
        export_s3_diagnostic(manifest, tmp_path / "bad-review")


def s3_case(tmp_path):
    import json
    from pathlib import Path

    from character_factory_poc.common.store import write_once_json
    from tests.test_choice_voice_development import development_case

    _, cohort = development_case(tmp_path)
    d = next(s for s in cohort.slots if s.arm == "D")
    template = tmp_path / "template.txt"
    template.write_text("씨앗: {{SEED_JSON}}\n행동 예시:\n{{BEHAVIOR_EXAMPLES}}")
    examples = {}
    for i in range(2):
        p = tmp_path / f"example-{i}.txt"
        p.write_text(f"합성 행동 예시 {i}")
        examples[str(i)] = dict(path=str(p), sha256=sha256_file(p))

    def ref(p):
        return dict(path=str(p), sha256=sha256_file(p))

    arms = []
    seed = json.dumps(read_json(d.seed.verify()), ensure_ascii=False, sort_keys=True)
    for i, (arm, order) in enumerate(
        (("original", ["0", "1"]), ("removed", []), ("reordered", ["1", "0"]))
    ):
        text = (
            template.read_text()
            .replace("{{SEED_JSON}}", seed)
            .replace(
                "{{BEHAVIOR_EXAMPLES}}",
                "\n".join(Path(examples[e]["path"]).read_text() for e in order),
            )
        )
        input_path = tmp_path / f"input-{arm}.txt"
        input_path.write_text(text)
        output = tmp_path / f"output-{arm}.json"
        if i == 2:
            write_once_json(output, dict(error="synthetic first failure"))
        else:
            plan = read_json(d.plan.verify())
            write_once_json(
                output, dict(variants=[dict(plan, variantId=f"v{j}") for j in range(1, 4)])
            )
        attempt = tmp_path / f"attempt-{arm}.json"
        binding = dict(provider="fake", model="fake", settings={"maxOutputTokens": 12000})
        write_once_json(
            attempt,
            dict(
                attemptOrdinal=1,
                inputSha256=sha256_file(input_path),
                modelBinding=binding,
                resultSha256=sha256_file(output),
            ),
        )
        arms.append(
            dict(
                id=arm,
                arm=arm,
                seed=d.seed.model_dump(),
                template=ref(template),
                examples=examples,
                exampleOrder=order,
                renderedInput=ref(input_path),
                firstAttempt=ref(attempt),
                modelBinding=binding,
                firstOutput=ref(output) if i < 2 else None,
                failure=ref(output) if i == 2 else None,
            )
        )
    return dict(schemaVersion="s3-diagnostic-v1", id="synthetic", expectedCandidates=3, arms=arms)


def test_s3_human_categories_keep_failed_candidates_in_denominator(tmp_path):
    from character_factory_poc.common.store import write_once_json
    from character_factory_poc.stages.persona_quality.s3_diagnostics import (
        export_s3_diagnostic,
        report_s3_diagnostic,
    )

    out = export_s3_diagnostic(s3_case(tmp_path), tmp_path / "s3-review")
    template = read_json(out / "human-reviews-template.json")
    packet = {p["id"]: p for p in read_json(out / "review-packet.json")}
    for row in template["candidates"]:
        row.update(
            reviewer="synthetic-reviewer",
            seedFaithful=True,
            choiceCategory="조건 확인",
            evidence=[packet[row["id"]]["plan"]["choices"][0]["firstMove"]],
        )
    reviews = tmp_path / "reviews.json"
    write_once_json(reviews, template)
    result = report_s3_diagnostic(out, reviews)
    assert result["humanReviewComplete"] and result["seedFaithfulCandidates"] == 6
    assert result["plannedCandidates"] == 9 and len(result["failedArms"]) == 1
    assert {r["candidatePosition"] for r in result["positionChoiceDistribution"]} == {1, 2, 3}
    assert not result["qualityQualified"]


def test_s3_diagnostic_accepts_unmodified_original_s3_output_envelope(tmp_path):
    import json
    from pathlib import Path

    from character_factory_poc.contracts.planning import PlanVariantsOutput
    from character_factory_poc.stages.persona_quality.s3_diagnostics import (
        export_s3_diagnostic,
        report_s3_diagnostic,
    )

    manifest = s3_case(tmp_path)
    for arm in manifest["arms"]:
        if arm["firstOutput"]:
            path = Path(arm["firstOutput"]["path"])
            actual = PlanVariantsOutput.model_validate(read_json(path)).model_dump(mode="json")
            actual["axisNote"] = "실제 원본의 후보 차이 설명"
            path.write_text(json.dumps(actual, ensure_ascii=False))
            arm["firstOutput"]["sha256"] = sha256_file(path)
            attempt_path = Path(arm["firstAttempt"]["path"])
            attempt = read_json(attempt_path)
            attempt["resultSha256"] = sha256_file(path)
            attempt_path.write_text(json.dumps(attempt, ensure_ascii=False))
            arm["firstAttempt"]["sha256"] = sha256_file(attempt_path)
    out = export_s3_diagnostic(manifest, tmp_path / "original-envelope")
    assert report_s3_diagnostic(out)["completedCandidates"] == 6
