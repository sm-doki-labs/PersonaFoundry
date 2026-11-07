"""Offline S7 formation fixtures and first-output/resume regressions."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from character_factory_poc.common.errors import AgentFormatError, CheckFailed
from character_factory_poc.common.store import read_json, verify_manifest, write_once_json
from character_factory_poc.contracts.formation import FormationDialogues, PersonaBlueprint
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.state import StateFile
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s7_traits.sheet import run_s7
from tests.support.legacy import import_plan
from tests.support.synthetic import PLAN, trait_sheet
from tests.test_formation_contracts import blueprint, dialogues

PROFILE = "ko-text-prompt-long-v1"


def formation_outputs(cid: str, plan_rev: str = "pr1") -> tuple[dict, dict]:
    """Reusable model drafts: metadata/hashes are deliberately absent."""
    bp = blueprint()
    for key in ("characterId", "planRev", "planSha256", "traitSheetSha256", "sourceRefs"):
        bp.pop(key)
    bp["decisionRules"][0].update(
        doNotActivateWhen="가벼운 호감에는 확답을 요구하지 않는다.",
        switchWhen="새 일정 제안이면 새 조건을 받고 틀린 회상과 구분한다.",
    )
    bp["unresolved"] = ["optional childhood detail"]
    rows = dialogues()["dialogues"]
    rows[0]["pairs"][0]["user"] = "오늘 나는 합성 공방에서 일했어."
    rows[0]["factRefs"] = [
        {
            "scope": "example-local",
            "owner": "user",
            "text": "오늘 나는 합성 공방에서 일했어.",
            "dialogueId": "d01",
            "source": {
                "kind": "dialogue",
                "fieldPath": "pairs[0].user",
                "quote": "오늘 나는 합성 공방에서 일했어.",
            },
        }
    ]
    return {"traitSheet": trait_sheet(cid, plan_rev), "blueprint": bp}, {"dialogues": rows}


@dataclass
class FormationCase:
    ctx: Context
    cid: str
    design: dict
    examples: dict
    model: FakeTextModel

    @property
    def revision(self) -> Path:
        return self.ctx.character_dir(self.cid) / "s7-traits" / "tr1"


@pytest.fixture
def formation_case(tmp_path: Path) -> FormationCase:
    """Reusable approved v1 plan + opt-in Context + two independent fake drafts."""
    (tmp_path / "factory.toml").write_text(
        f'[stages.s7]\nformation_profile = "{PROFILE}"\n', encoding="utf-8"
    )
    ctx = Context.load(tmp_path, execute=True)
    source = tmp_path / "plan.json"
    write_once_json(source, PLAN)
    plan = import_plan(ctx, "formation", source)
    design, examples = formation_outputs(plan.characterId)
    model = FakeTextModel()
    model.add(
        "AGENT",
        lambda req: (
            design
            if req.metadata.get("formationStep") == "design"
            else (
                examples
                if req.metadata.get("formationStep") == "dialogues"
                else design["traitSheet"]
            )
        ),
    )
    ctx.use_models(model)
    return FormationCase(ctx, plan.characterId, design, examples, model)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_opt_in_forms_both_artifacts_once_with_stored_byte_hashes(formation_case):
    c = formation_case
    path = run_s7(c.ctx, c.cid)
    assert path == c.revision / "trait-sheet.json"
    assert len(c.model.requests) == 2
    bp = PersonaBlueprint.model_validate(read_json(c.revision / "blueprint.json"))
    ds = FormationDialogues.model_validate(read_json(c.revision / "formation-dialogues.json"))
    plan_path = c.ctx.character_dir(c.cid) / "s3-plan/pr1/plan.json"
    assert bp.planSha256 == ds.planSha256 == digest(plan_path)
    assert bp.traitSheetSha256 == ds.traitSheetSha256 == digest(path)
    assert ds.blueprintSha256 == digest(c.revision / "blueprint.json")
    assert len(ds.dialogues) == 12
    assert [d.category for d in ds.dialogues].count("ordinary") == 8
    assert sum(len(d.pairs) == 6 for d in ds.dialogues) >= 2
    assert read_json(path)["card"]["bigFiveNotes"] == "미정"
    assert "card.bigFiveNotes" in read_json(path)["unresolved"]
    assert bp.decisionRules[0].doNotActivateWhen == "가벼운 호감에는 확답을 요구하지 않는다."
    assert c.ctx.state(c.cid).stage("s7").status == "AWAITING_HUMAN"
    assert verify_manifest(c.revision) == []
    for sub in ("design", "dialogues"):
        assert (c.revision / sub / "workspace/attempt-1.txt").exists()
    profile = read_json(c.revision / "profile.json")
    assert profile["profileId"] == PROFILE
    assert profile["modelBinding"] is None and not profile["thresholdsFrozen"]
    for ref in [*bp.sourceRefs, *ds.sourceRefs]:
        actual = c.ctx.character_dir(c.cid) / ref.ref
        assert actual.exists() and ref.sha256 == digest(actual)
    assert {r.kind for r in bp.sourceRefs} >= {"plan", "trait"}
    assert {r.kind for r in ds.sourceRefs} >= {"plan", "trait", "blueprint"}


def test_writer_receives_projected_canon_sheet_and_blueprint_bodies(formation_case):
    c = formation_case
    run_s7(c.ctx, c.cid)
    inputs = read_json(c.revision / "dialogues/workspace/inputs.json")
    assert inputs["canonical_plan"]["plan"]["name"] == PLAN["name"]
    assert [v["scene"] for v in inputs["canonical_plan"]["plan"]["chapters"]] == [
        v["scene"] for v in PLAN["chapters"]
    ]
    assert "evidence" not in inputs["canonical_plan"]["plan"]
    assert "notes" not in inputs["canonical_plan"]["plan"]
    assert inputs["traitSheet"]["choice"] == c.design["traitSheet"]["choice"]
    assert inputs["blueprint"]["ordinaryModes"] == c.design["blueprint"]["ordinaryModes"]
    assert "rubric" not in inputs and "heldout" not in inputs


def test_local_fact_cites_its_own_separate_source_without_hash_cycle(formation_case):
    c = formation_case
    run_s7(c.ctx, c.cid)
    ds = read_json(c.revision / "formation-dialogues.json")
    fact = ds["dialogues"][0]["factRefs"][0]
    source = c.ctx.character_dir(c.cid) / fact["source"]["ref"]
    assert source != c.revision / "formation-dialogues.json"
    assert fact["source"]["sha256"] == digest(source)
    assert read_json(source)["pairs"][0]["user"] == fact["source"]["quote"]
    assert "factRefs" not in read_json(source)
    assert len(list((c.revision / "dialogues/sources").glob("*.json"))) == 12


@pytest.mark.parametrize("step", ["design", "dialogues"])
def test_format_retries_preserve_all_raw_outputs_then_pass(formation_case, step):
    c = formation_case
    attempts = {"design": 0, "dialogues": 0}

    def answer(req):
        current = req.metadata["formationStep"]
        attempts[current] += 1
        if current == step and attempts[current] <= 2:
            return "malformed first output" if attempts[current] == 1 else {}
        return c.design if current == "design" else c.examples

    c.model.add("AGENT", answer)
    run_s7(c.ctx, c.cid)
    assert attempts[step] == 3
    workspace = c.revision / step / "workspace"
    assert (workspace / "attempt-1.txt").read_text() == "malformed first output"
    assert json.loads((workspace / "attempt-2.txt").read_text()) == {}
    assert (workspace / "attempt-3.txt").exists()


@pytest.mark.parametrize("step", ["design", "dialogues"])
def test_format_retry_cap_is_two_even_if_config_requests_more(formation_case, step):
    c = formation_case
    c.ctx.config.stages["s7"]["max_format_retries"] = 99
    c.model.add(
        "AGENT",
        lambda req: (
            c.design
            if (step == "dialogues" and req.metadata["formationStep"] == "design")
            else "not JSON"
        ),
    )
    with pytest.raises(AgentFormatError):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == (3 if step == "design" else 4)
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"
    with pytest.raises((AgentFormatError, CheckFailed)):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == (3 if step == "design" else 4)


@pytest.mark.parametrize("problem", ["trait-check", "canon", "plan-id", "quote", "path"])
def test_design_semantic_failure_stops_without_redraw_including_resume(formation_case, problem):
    c = formation_case
    if problem == "trait-check":
        c.design["traitSheet"]["choice"]["attention"] = "밝음, 솔직함"
    elif problem == "canon":
        c.design["traitSheet"]["card"]["expressedTraits"]["core"] = ["혼자 오래 기다린다."]
        c.design["traitSheet"]["choice"]["primaryResponse"] = "충분히 기다린 뒤 조용히 듣는다."
        c.design["traitSheet"]["card"]["stance"] = "상대의 흐름을 기다리는 쪽이다."
    elif problem == "plan-id":
        c.design["traitSheet"]["planRev"] = "pr99"
    else:
        c.design["blueprint"]["sourceRefs"] = [
            {
                "kind": "plan",
                "fieldPath": "name",
                "quote": PLAN["name"],
            }
        ]
        c.design["blueprint"]["sourceRefs"][0].update(
            {"quote": "invented source quote"} if problem == "quote" else {"ref": "../other.json"}
        )
    c.ctx.config.stages["s7"]["max_check_retries"] = 99
    with pytest.raises(CheckFailed):
        run_s7(c.ctx, c.cid)
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"
    assert len(c.model.requests) == 1
    with pytest.raises(CheckFailed):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 1


@pytest.mark.parametrize(
    "problem", ["promote-user", "wrong-dialogue", "quote", "path", "unknown-ref"]
)
def test_example_semantic_failure_keeps_first_output_without_redraw(formation_case, problem):
    c = formation_case
    fact = c.examples["dialogues"][0]["factRefs"][0]
    if problem == "promote-user":
        fact.update(scope="canon", dialogueId=None)
        fact["source"] = {"kind": "plan", "fieldPath": "job", "quote": PLAN["job"]}
    elif problem == "wrong-dialogue":
        fact["dialogueId"] = "d02"
    elif problem == "quote":
        fact["source"]["quote"] = "invented quote"
    elif problem == "path":
        fact["source"]["fieldPath"] = "pairs[99].user"
    else:
        c.examples["sourceRefs"] = [
            {
                "kind": "reference",
                "ref": "unprovided-sns.json",
                "fieldPath": "body",
                "quote": "unprovided dialogue",
            }
        ]
    with pytest.raises(CheckFailed):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 2
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"
    assert (c.revision / "dialogues/workspace/attempt-1.txt").exists()
    with pytest.raises(CheckFailed):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 2


@pytest.mark.parametrize("problem", ["eleven", "seven-pairs", "one-long", "counts", "duplicate"])
def test_malformed_composition_fails_after_bounded_format_attempts(formation_case, problem):
    c = formation_case
    rows = c.examples["dialogues"]
    if problem == "eleven":
        rows.pop()
    elif problem == "seven-pairs":
        rows[0]["pairs"].append(copy.deepcopy(rows[0]["pairs"][0]))
    elif problem == "one-long":
        rows[1]["pairs"] = rows[1]["pairs"][:2]
    elif problem == "counts":
        rows[7].update(category="boundary", selectionSlot="listening-conflict")
    else:
        rows[1]["dialogueId"] = rows[0]["dialogueId"]
    with pytest.raises(AgentFormatError):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 4
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"


def test_transport_resume_reuses_design_and_then_completed_examples(formation_case):
    c = formation_case

    def interrupted(req):
        if req.metadata["formationStep"] == "dialogues":
            raise OSError("synthetic transport interruption")
        return c.design

    c.model.add("AGENT", interrupted)
    with pytest.raises(OSError):
        run_s7(c.ctx, c.cid)
    before = {
        name: (c.revision / name).read_bytes()
        for name in ("trait-sheet.json", "blueprint.json", "profile.json")
    }
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"
    c.model.add(
        "AGENT",
        lambda req: (
            c.examples
            if req.metadata["formationStep"] == "dialogues"
            else pytest.fail("completed design was recalled")
        ),
    )
    out = run_s7(c.ctx, c.cid)
    assert out == c.revision / "trait-sheet.json"
    assert len(c.model.requests) == 3
    assert all((c.revision / name).read_bytes() == body for name, body in before.items())
    assert run_s7(c.ctx, c.cid) == out
    assert len(c.model.requests) == 3
    assert verify_manifest(c.revision) == []


def test_resume_after_artifacts_written_before_final_transition_makes_no_calls(
    formation_case, monkeypatch
):
    c = formation_case
    original = StateFile.transition

    def interrupt(state, sid, new, **kw):
        if sid == "s7" and new == "AWAITING_HUMAN":
            raise OSError("interrupted final transition")
        return original(state, sid, new, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(StateFile, "transition", interrupt)
        with pytest.raises(OSError):
            run_s7(c.ctx, c.cid)
    run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 2
    assert c.ctx.state(c.cid).stage("s7").status == "AWAITING_HUMAN"


@pytest.mark.parametrize("profile", ["unknown-profile", "", None])
def test_unknown_profile_fails_closed_without_calls_or_revision(formation_case, profile):
    c = formation_case
    c.ctx.config.stages["s7"]["formation_profile"] = profile
    with pytest.raises(ValueError, match="profile"):
        run_s7(c.ctx, c.cid)
    assert c.model.requests == []
    assert not c.revision.exists()


def test_execute_guard_blocks_new_profile_without_side_effects(formation_case):
    c = formation_case
    c.ctx.execute = False
    with pytest.raises(ValueError, match="execute"):
        run_s7(c.ctx, c.cid)
    assert c.model.requests == []
    assert not c.revision.exists()


def test_profile_path_is_loaded_and_pinned_without_automatic_binding(formation_case):
    from tests.test_formation_contracts import bound_profile

    c = formation_case
    profile = bound_profile()
    path = c.ctx.config.root / "bound-profile.json"
    write_once_json(path, profile)
    c.ctx.config.stages["s7"]["profile_path"] = "bound-profile.json"
    run_s7(c.ctx, c.cid)
    assert read_json(c.revision / "profile.json") == profile


def test_existing_legacy_sheet_is_not_promoted_to_new_profile(formation_case):
    c = formation_case
    c.ctx.config.stages["s7"].pop("formation_profile")
    c.model.add("AGENT", c.design["traitSheet"])
    old = run_s7(c.ctx, c.cid)
    c.ctx.config.stages["s7"]["formation_profile"] = PROFILE
    c.model.add(
        "AGENT", lambda req: c.design if req.metadata["formationStep"] == "design" else c.examples
    )
    # A legacy pending G6 is deliberately superseded only by this explicit opt-in run.
    state = c.ctx.state(c.cid)
    state.transition("s7", "APPROVED", rev="tr1")
    new = run_s7(c.ctx, c.cid)
    assert old.parent.name == "tr1" and new.parent.name == "tr2"
    assert not (old.parent / "blueprint.json").exists()
    assert len(c.model.requests) == 3


@pytest.mark.parametrize("field", ["activateWhen", "doNotActivateWhen"])
def test_missing_rule_conditions_are_format_failures_and_keep_raw_attempts(formation_case, field):
    c = formation_case
    del c.design["blueprint"]["decisionRules"][0][field]
    with pytest.raises(AgentFormatError):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 3
    assert c.ctx.state(c.cid).stage("s7").status == "CHECK_FAILED"
    assert len(list((c.revision / "design/workspace").glob("attempt-*.txt"))) == 3


@pytest.mark.parametrize(
    "kind,field",
    [
        ("plan", "job"),
        ("trait", "choice.attention"),
        ("blueprint", "ordinaryModes.selfStory"),
    ],
)
def test_nested_canon_fact_binds_actual_source_fields_and_hashes(formation_case, kind, field):
    c = formation_case
    quote = {
        "plan": PLAN["job"],
        "trait": c.design["traitSheet"]["choice"]["attention"],
        "blueprint": c.design["blueprint"]["ordinaryModes"]["selfStory"],
    }[kind]
    c.examples["dialogues"][1]["factRefs"] = [
        {
            "scope": "canon",
            "owner": "character",
            "text": quote,
            "source": {"kind": kind, "fieldPath": field, "quote": quote},
        }
    ]
    run_s7(c.ctx, c.cid)
    ds = FormationDialogues.model_validate(read_json(c.revision / "formation-dialogues.json"))
    ref = ds.dialogues[1].factRefs[0].source
    assert ref.sha256 == digest(c.ctx.character_dir(c.cid) / ref.ref)
    assert (
        ref.sha256
        == {"plan": ds.planSha256, "trait": ds.traitSheetSha256, "blueprint": ds.blueprintSha256}[
            kind
        ]
    )


def test_claimed_hash_mismatch_is_semantic_failure_without_redraw(formation_case):
    c = formation_case
    c.examples["dialogues"][0]["factRefs"][0]["source"]["sha256"] = "a" * 64
    with pytest.raises(CheckFailed, match="hash mismatch"):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 2


def test_legacy_canonical_projection_does_not_invent_optional_fields(formation_case):
    c = formation_case
    run_s7(c.ctx, c.cid)
    for step in ("design", "dialogues"):
        p = read_json(c.revision / step / "workspace/inputs.json")["canonical_plan"]["plan"]
        assert "gender" not in p and "background" not in p and "voiceExamples" not in p


def test_existing_v2_plan_body_reaches_both_steps_without_private_evidence(tmp_path):
    from tests.support.flow import approve_plan_v2, sample_plan_v2

    (tmp_path / "factory.toml").write_text(
        f'[stages.s7]\nformation_profile = "{PROFILE}"\n', encoding="utf-8"
    )
    ctx = Context.load(tmp_path, execute=True)
    cid = "synthetic-formation-v2"
    plan = sample_plan_v2(cid)
    approve_plan_v2(ctx, cid, plan)
    design, examples = formation_outputs(cid)
    design["traitSheet"]["card"]["expressedTraits"]["core"] = [
        f"{t} 상황에 맞게 그 행동을 먼저 한다." for t in plan["coreTraits"]
    ]
    model = FakeTextModel()
    model.add(
        "AGENT", lambda req: design if req.metadata["formationStep"] == "design" else examples
    )
    ctx.use_models(model)
    root = run_s7(ctx, cid).parent
    for step in ("design", "dialogues"):
        p = read_json(root / step / "workspace/inputs.json")["canonical_plan"]["plan"]
        for field in ("name", "background", "lifeAndTastes", "voiceExamples", "chapterArc"):
            assert p[field] == plan[field]
        assert "evidence" not in p and "appearanceRev" not in p and "seedRev" not in p


def test_invented_trait_reference_stops_design_without_redraw(formation_case):
    c = formation_case
    c.design["traitSheet"]["references"] = [
        {"kind": "STANFORD", "id": "not-provided", "version": "v1"}
    ]
    with pytest.raises(CheckFailed, match="reference"):
        run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 1


def test_explicit_standard_reference_is_snapshotted_and_its_quote_verified(formation_case):
    c = formation_case
    standard = {"guidance": "A wholly synthetic standard for ordinary conversation."}
    c.design["traitSheet"]["references"] = [
        {"kind": "OTHER", "id": "synthetic-standard", "version": "r1"}
    ]
    c.design["blueprint"]["sourceRefs"] = [
        {
            "kind": "reference",
            "fieldPath": "body.guidance",
            "quote": standard["guidance"],
        }
    ]
    path = run_s7(
        c.ctx,
        c.cid,
        references=c.design["traitSheet"]["references"],
        reference_docs={"synthetic-standard": standard},
    )
    bp = read_json(path.parent / "blueprint.json")
    ref = next(r for r in bp["sourceRefs"] if r["kind"] == "reference")
    assert ref["sha256"] == digest(c.ctx.character_dir(c.cid) / ref["ref"])
    assert ref["version"] == "r1" and ref["quote"] == standard["guidance"]
    inputs = read_json(c.revision / "design/workspace/inputs.json")
    assert inputs["reference_sources"][0]["body"] == {"body": standard}
    assert verify_manifest(c.revision) == []


@pytest.mark.parametrize("kind", ["SNS14", "OTHER"])
def test_missing_reference_body_or_raw_corpus_input_fails_before_generation(formation_case, kind):
    c = formation_case
    with pytest.raises(ValueError, match="reference"):
        run_s7(c.ctx, c.cid, references=[{"kind": kind, "id": "missing", "version": "v1"}])
    assert len(c.model.requests) == 0


def test_resume_budget_counts_only_remaining_writer_attempts(formation_case):
    c = formation_case

    def interrupt(req):
        if req.metadata["formationStep"] == "dialogues":
            raise OSError("synthetic transport interruption")
        return c.design

    c.model.add("AGENT", interrupt)
    with pytest.raises(OSError):
        run_s7(c.ctx, c.cid)
    c.ctx.max_calls = 2
    c.model.add("AGENT", c.examples)
    run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 3
    assert c.ctx.state(c.cid).stage("s7").status == "AWAITING_HUMAN"


def test_saved_valid_draft_is_assembled_without_recalling_or_rebudgeting_design(
    formation_case, monkeypatch
):
    import character_factory_poc.stages.s7_traits.formation as formation

    c = formation_case
    original = formation.write_once_json

    def interrupt(path, obj):
        if path.name == "blueprint.json":
            raise OSError("interrupted blueprint write")
        return original(path, obj)

    with monkeypatch.context() as patch:
        patch.setattr(formation, "write_once_json", interrupt)
        with pytest.raises(OSError):
            run_s7(c.ctx, c.cid)
    assert (c.revision / "design/workspace/output.json").exists()
    assert not (c.revision / "blueprint.json").exists()
    c.ctx.max_calls = 3
    run_s7(c.ctx, c.cid)
    assert len(c.model.requests) == 2
    assert c.ctx.state(c.cid).stage("s7").status == "AWAITING_HUMAN"


def test_design_json_request_is_explicit_for_raw_compatible_provider(formation_case):
    c = formation_case
    run_s7(c.ctx, c.cid)
    assert all("json" in " ".join(m.content for m in req.messages) for req in c.model.requests)


def test_output_schema_exposes_blueprint_body_types():
    from character_factory_poc.stages.s7_traits.formation import FormationDraft

    schema = FormationDraft.model_json_schema()
    assert "$ref" in schema["properties"]["blueprint"]
    voice = schema["$defs"]["VoiceProfile"]["properties"]
    assert voice["lexicon"]["type"] == "array"
