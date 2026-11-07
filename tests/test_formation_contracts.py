"""Bounded formation contracts: synthetic data, no providers or quality claims."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from pydantic import ValidationError

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import contract
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts import persona

H = "a" * 64


def prompt(text="Synthetic long prompt"):
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)}


def source(kind="plan", **updates):
    return {
        "kind": kind,
        "ref": f"{kind}.json",
        "version": "v1",
        "sha256": H,
        "fieldPath": "background",
        "quote": "Synthetic source quote",
        **updates,
    }


def blueprint():
    return {
        "characterId": "synthetic",
        "planRev": "pr1",
        "planSha256": H,
        "traitSheetSha256": H,
        "decisionRules": [
            {
                key: "Synthetic rule"
                for key in (
                    "situation",
                    "activateWhen",
                    "doNotActivateWhen",
                    "firstMove",
                    "priority",
                    "switchWhen",
                    "wrongTransformation",
                )
            }
        ],
        "voiceProfile": {
            **{
                key: "Synthetic voice"
                for key in (
                    "speechLevel",
                    "rhythm",
                    "directness",
                    "emotionalVariation",
                    "relationshipDistance",
                )
            },
            "lexicon": ["everyday words"],
            "avoidRepetition": ["repeated closing questions"],
        },
        "ordinaryModes": {
            key: "Choose when relevant"
            for key in (
                "reacting",
                "selfStory",
                "playful",
                "listening",
                "affection",
            )
        },
        "factPolicy": {
            key: "Confirmed history precedes initial state and examples"
            for key in (
                "selfFiction",
                "userFacts",
                "sharedHistory",
                "proposalAgreementCancellation",
                "externalCurrentFacts",
                "mutableState",
            )
        },
        "sourceRefs": [source(), source("trait")],
        "unresolved": ["optional childhood detail"],
    }


def dialogues():
    rows = []
    for i in range(12):
        category = "ordinary" if i < 8 else "boundary" if i < 10 else "change"
        slot = (
            "ordinary-self"
            if i < 4
            else "playful-affection"
            if i < 8
            else "listening-conflict"
            if i < 10
            else "condition-owner-change"
        )
        rows.append(
            {
                "dialogueId": f"d{i + 1:02}",
                "category": category,
                "selectionSlot": slot,
                "pairs": [{"user": "Synthetic user", "assistant": "Synthetic reply"}]
                * (6 if i < 2 else 2),
                "factRefs": [],
            }
        )
    return {
        "characterId": "synthetic",
        "traitRevision": "tr1",
        "planSha256": H,
        "traitSheetSha256": H,
        "blueprintSha256": H,
        "sourceRefs": [source(), source("trait"), source("blueprint")],
        "dialogues": rows,
    }


def bundle():
    return {
        "characterId": "synthetic",
        "personaVersion": "pv1",
        "planRev": "pr1",
        "traitRevision": "tr1",
        "planSha256": H,
        "traitSheetSha256": H,
        "blueprintSha256": H,
        "dialoguesSha256": H,
        "profileId": "ko-text-prompt-long-v1",
        "profileSha256": H,
        "compilerVersion": "compiler-v1",
        "compilerSha256": H,
        "systemRulesRef": "rules.md",
        "systemRulesSha256": H,
        "selectedDialogueIds": ["d01", "d05", "d09", "d11"],
        "long": prompt(),
    }


def pair(version="prompt-pair-v2"):
    data = {
        "schemaVersion": version,
        "characterId": "synthetic",
        "traitSheetSha256": H,
        "sections": ["ACTOR_IDENTITY"],
        "long": prompt(),
        "systemRulesRef": "rules.md",
        "systemRulesSha256": H,
    }
    if version.endswith("v1"):
        data["short"] = prompt("Short")
    else:
        data["shortStatus"] = "UNAVAILABLE"
    return data


def bound_profile():
    from character_factory_poc.contracts.formation import load_quality_profile

    data = load_quality_profile().model_dump(mode="json")
    data.update(
        {
            "thresholdsFrozen": True,
            "rubricSha256": H,
            "recipeHash": H,
            "splitManifestSha256": H,
            "protocolSha256": H,
            "modelBinding": {
                "provider": "synthetic",
                "providerPath": "local/fake",
                "model": "synthetic-model",
                "revision": "r1",
                "reasoningSettings": {},
                "temperature": 0.7,
                "maxOutputTokens": 1024,
                "systemAssemblyVersion": "system-v1",
                "contextLimit": 32768,
            },
        }
    )
    return data


def result(**updates):
    return {
        "status": "QUALIFIED",
        "profileId": "ko-text-prompt-long-v1",
        "profileSha256": hashlib.sha256(
            (
                json.dumps(bound_profile(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode()
        ).hexdigest(),
        "plannedArtifacts": 16,
        "completedArtifacts": 16,
        "reasons": [],
        "metrics": {"allArtifactCriteriaPassed": True},
        **updates,
    }


def test_versioned_loader_preserves_legacy_and_long_only(tmp_path):
    assert hasattr(persona, "load_prompt_pair"), "version-aware loader is missing"
    for version in ("prompt-pair-v1", "prompt-pair-v2"):
        data = pair(version)
        path = tmp_path / f"{version}.json"
        write_once_json(path, data)
        loaded = persona.load_prompt_pair(path)
        assert loaded.schemaVersion == version
        assert persona.require_long(loaded).text == "Synthetic long prompt"
        assert loaded.shortAdopted is False
    with pytest.raises(ValueError, match="short|SHORT"):
        persona.require_short(loaded)
    assert persona.require_short(persona.load_prompt_pair(pair("prompt-pair-v1"))).text == "Short"


@pytest.mark.parametrize(
    "status,has_short,valid",
    [
        ("UNAVAILABLE", False, True),
        ("UNAVAILABLE", True, False),
        ("UNQUALIFIED", False, False),
        ("UNQUALIFIED", True, True),
        ("READY", False, False),
        ("READY", True, True),
    ],
)
def test_short_state_requires_consistent_data(status, has_short, valid):
    data = {**pair(), "shortStatus": status}
    if has_short:
        data["short"] = prompt("Short")
    if not valid:
        with pytest.raises(ValidationError):
            persona.PromptPairV2.model_validate(data)
        return
    loaded = persona.PromptPairV2.model_validate(data)
    if status == "READY":
        assert persona.require_short(loaded).text == "Short"
    else:
        with pytest.raises(ValueError):
            persona.require_short(loaded)


@pytest.mark.parametrize(
    "change",
    [
        {"long": None},
        {"longStatus": "UNAVAILABLE"},
        {"shortAdopted": True},
        {"shortAdopted": 0},
        {"shortStatus": "ready"},
        {"unknown": True},
        {"long": {**prompt(), "sha256": "b" * 64}},
        {"long": {**prompt(), "chars": "21"}},
        {"long": {**prompt(), "chars": 0}},
        {"long": prompt("")},
        {"traitSheetSha256": "invalid"},
    ],
)
def test_v2_rejects_invalid_long_adoption_and_unrecognized_fields(change):
    with pytest.raises(ValidationError):
        persona.PromptPairV2.model_validate({**pair(), **change})


def test_loader_requires_explicit_supported_version():
    for version in (None, "prompt-pair-v3", "trait-sheet-v1"):
        with pytest.raises(ValueError):
            persona.load_prompt_pair({**pair(), "schemaVersion": version})


def test_profile_is_loadable_proposal_without_invented_binding():
    from character_factory_poc.contracts.formation import load_quality_profile

    profile = load_quality_profile()
    assert profile.profileId == "ko-text-prompt-long-v1"
    assert profile.modelBinding is None
    assert profile.thresholdsFrozen is False
    assert profile.thresholds.assistantTurnsPerArtifact == 60
    assert profile.thresholds.scenesPerArtifact == 7
    assert profile.thresholds.longMaxChars == 8000


def test_final_validation_preserves_explicit_qualified_with_complete_gates():
    from character_factory_poc.contracts.formation import validate_qualification_result

    validated = validate_qualification_result(
        result(),
        bound_profile(),
        scope_supported=True,
        human_review_complete=True,
        independence_verified=True,
    )
    assert validated.status == "QUALIFIED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("modelBinding", None),
        ("thresholdsFrozen", False),
        ("rubricSha256", None),
        ("recipeHash", None),
        ("splitManifestSha256", None),
        ("protocolSha256", None),
    ],
)
def test_final_validation_fails_closed_for_unbound_or_unfrozen_profile(field, value):
    from character_factory_poc.contracts.formation import validate_qualification_result

    data = bound_profile()
    data[field] = value
    validated = validate_qualification_result(
        result(),
        data,
        scope_supported=True,
        human_review_complete=True,
        independence_verified=True,
    )
    assert validated.status == "NOT_QUALIFIED"
    assert validated.reasons


@pytest.mark.parametrize(
    "gate", ["scope_supported", "human_review_complete", "independence_verified"]
)
def test_final_validation_requires_external_evidence(gate):
    from character_factory_poc.contracts.formation import validate_qualification_result

    gates = dict(scope_supported=True, human_review_complete=True, independence_verified=True)
    gates[gate] = False
    validated = validate_qualification_result(result(), bound_profile(), **gates)
    assert validated.status != "QUALIFIED"
    assert validated.reasons


def test_nonqualified_status_never_upgraded_by_valid_schema():
    from character_factory_poc.contracts.formation import validate_qualification_result

    for state in ("NOT_RUN", "METRICS_ONLY", "NOT_QUALIFIED"):
        validated = validate_qualification_result(
            result(status=state),
            bound_profile(),
            scope_supported=True,
            human_review_complete=True,
            independence_verified=True,
        )
        assert validated.status == state


@pytest.mark.parametrize(
    "change",
    [
        {"plannedArtifacts": 0, "completedArtifacts": 0},
        {"completedArtifacts": 15},
        {"completedArtifacts": 17},
        {"reasons": ["first-pass failure"]},
        {"metrics": None},
    ],
)
def test_qualified_envelope_rejects_incomplete_denominators_or_failure(change):
    from character_factory_poc.contracts.formation import QualificationResult

    with pytest.raises(ValidationError):
        QualificationResult.model_validate(result(**change))


@pytest.mark.parametrize(
    "factory,name",
    [
        (blueprint, "persona-blueprint-v1"),
        (dialogues, "formation-dialogues-v1"),
        (bundle, "persona-bundle-v1"),
        (bound_profile, "persona-quality-profile-v1"),
    ],
)
def test_new_contracts_registered_roundtrip_and_forbid_unknown_fields(factory, name):
    model = contract(name)
    data = factory()
    loaded = model.model_validate(data)
    assert model.model_validate_json(loaded.model_dump_json()) == loaded
    with pytest.raises(ValidationError):
        model.model_validate({**data, "extra": True})


@pytest.mark.parametrize("field", ["doNotActivateWhen", "switchWhen", "wrongTransformation"])
def test_blueprint_requires_activation_and_transformation_boundaries(field):
    from character_factory_poc.contracts.formation import PersonaBlueprint

    data = blueprint()
    del data["decisionRules"][0][field]
    with pytest.raises(ValidationError):
        PersonaBlueprint.model_validate(data)


@pytest.mark.parametrize(
    "change", ["count", "pairs-low", "pairs-high", "six", "mix", "duplicate", "slot"]
)
def test_dialogue_contract_enforces_counts_mix_unique_ids_and_slots(change):
    from character_factory_poc.contracts.formation import FormationDialogues

    data = dialogues()
    rows = data["dialogues"]
    if change == "count":
        rows.pop()
    elif change == "pairs-low":
        rows[0]["pairs"] = rows[0]["pairs"][:1]
    elif change == "pairs-high":
        rows[0]["pairs"] += [{"user": "One more", "assistant": "Over limit"}]
    elif change == "six":
        rows[1]["pairs"] = rows[1]["pairs"][:2]
    elif change == "mix":
        rows[7].update(category="boundary", selectionSlot="listening-conflict")
    elif change == "duplicate":
        rows[1]["dialogueId"] = rows[0]["dialogueId"]
    else:
        rows[0]["selectionSlot"] = "condition-owner-change"
    with pytest.raises(ValidationError):
        FormationDialogues.model_validate(data)


def test_fact_provenance_is_local_and_has_exact_quote_path_hash():
    from character_factory_poc.contracts.formation import FactRef, FormationDialogues

    fact = {
        "scope": "example-local",
        "owner": "user",
        "text": "Synthetic user plan",
        "dialogueId": "d01",
        "source": source("dialogue", fieldPath="pairs[0].user"),
    }
    data = dialogues()
    data["dialogues"][0]["factRefs"] = [fact]
    FormationDialogues.model_validate(data)
    for field in ("quote", "fieldPath", "sha256"):
        bad = copy.deepcopy(fact)
        del bad["source"][field]
        with pytest.raises(ValidationError):
            FactRef.model_validate(bad)
    for updates in ({"dialogueId": "d02"}, {"scope": "canon"}):
        data["dialogues"][0]["factRefs"] = [{**fact, **updates}]
        with pytest.raises(ValidationError):
            FormationDialogues.model_validate(data)


def test_combined_design_preserves_legacy_and_checks_identity_not_reencoded_hash(tmp_path):
    from character_factory_poc.contracts.formation import FormationDesign
    from tests.support.synthetic import trait_sheet

    sheet = trait_sheet("synthetic", "pr1")
    path = tmp_path / "trait-sheet.json"
    write_once_json(path, sheet)
    bp = blueprint()
    bp["traitSheetSha256"] = sha256_file(path)
    bp["sourceRefs"][1]["sha256"] = sha256_file(path)
    data = {"traitSheet": sheet, "blueprint": bp}
    design = FormationDesign.model_validate(data)
    assert design.traitSheet.schemaVersion == "trait-sheet-v1"
    assert design.blueprint.traitSheetSha256 == sha256_file(path)
    bp["characterId"] = "different"
    with pytest.raises(ValidationError):
        FormationDesign.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "traitRevision",
        "planSha256",
        "traitSheetSha256",
        "blueprintSha256",
        "dialoguesSha256",
        "profileSha256",
        "compilerSha256",
        "systemRulesSha256",
    ],
)
def test_bundle_requires_pinned_source_metadata(field):
    from character_factory_poc.contracts.formation import PersonaBundle

    data = bundle()
    del data[field]
    with pytest.raises(ValidationError):
        PersonaBundle.model_validate(data)


def test_bundle_selected_examples_are_four_distinct_ids():
    from character_factory_poc.contracts.formation import PersonaBundle

    for ids in (["d01"], ["d01"] * 4):
        with pytest.raises(ValidationError):
            PersonaBundle.model_validate({**bundle(), "selectedDialogueIds": ids})


def test_profile_loader_rejects_malformed_hashes_and_nested_extras(tmp_path):
    from character_factory_poc.contracts.formation import load_quality_profile

    for field, value in (("rubricSha256", "invalid"), ("scope", {"invented": True})):
        data = bound_profile()
        data[field] = value
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(data))
        with pytest.raises(ValidationError):
            load_quality_profile(path)


def test_qualification_cannot_be_reused_after_profile_changes():
    from character_factory_poc.contracts.formation import validate_qualification_result

    old = bound_profile()
    claim = result()
    changed = copy.deepcopy(old)
    changed["modelBinding"]["model"] = "different-model"
    checked = validate_qualification_result(
        claim, changed, scope_supported=True, human_review_complete=True, independence_verified=True
    )
    assert checked.status != "QUALIFIED"


def test_nested_canon_reference_must_match_pinned_source():
    from character_factory_poc.contracts.formation import FormationDialogues

    data = dialogues()
    data["dialogues"][0]["factRefs"] = [
        dict(scope="canon", owner="character", text="fact", source=source("plan", sha256="b" * 64))
    ]
    with pytest.raises(ValidationError, match="canon"):
        FormationDialogues.model_validate(data)
