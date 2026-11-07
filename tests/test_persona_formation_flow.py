"""새 bundle의 G6 승인과 구형 소비 호환을 합성 자료로 확인한다."""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.approve import approve_g6
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.test_persona_pipeline import _fake_models, _import
from tests.test_persona_pipeline import ctx as ctx


def test_g6_rejects_v2_missing_bundle_before_recording_approval(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)
    run_s7(ctx, cid)
    folder = run_s8(ctx, cid, [])
    path = folder / "prompt-pair.json"
    data = json.loads(path.read_text())
    data.update(
        schemaVersion="prompt-pair-v2", short=None, shortStatus="UNAVAILABLE", longStatus="READY"
    )
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError, FactoryError)):
        approve_g6(ctx, cid, dict(decision="APPROVE", reviewer="test"))
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"


def test_unknown_generation_cost_is_not_rendered_as_free():
    from character_factory_poc.common.budget import CallPlan, format_plan

    shown = format_plan([CallPlan("s7a", "형성", 3, est_cost_usd=None)])
    assert "미확인" in shown
    assert "0.00 USD" not in shown


def test_new_profile_dry_run_does_not_plan_s8_model_call(tmp_path, capsys):
    from character_factory_poc.cli import main

    (tmp_path / "factory.toml").write_text(
        '[stages.s7]\nformation_profile="ko-text-prompt-long-v1"\n'
    )
    assert main(["--root", str(tmp_path), "persona", "prompts", "uncreated"]) == 0
    shown = capsys.readouterr().out
    assert "모델 호출0회" in shown
    assert "s8" not in shown.splitlines()[0].lower()


from tests.test_persona_formation import formation_case as formation_case  # noqa: E402


def test_new_bundle_flow_is_two_calls_and_pins_approved_trait(formation_case):
    from character_factory_poc.common.store import read_json, write_once_json
    from character_factory_poc.stages.s9_data.plan import load_prompt_pair
    from character_factory_poc.stages.s11_release.package import load_persona

    c = formation_case
    run_s7(c.ctx, c.cid)
    out = run_s8(c.ctx, c.cid, [])
    assert len(c.model.requests) == 2
    pair = read_json(out / "prompt-pair.json")
    assert pair["schemaVersion"] == "prompt-pair-v2" and pair["short"] is None
    bundle = read_json(out / "persona-bundle.json")
    assert bundle["traitRevision"] == "tr1"
    approve_g6(c.ctx, c.cid, dict(decision="APPROVE", reviewer="test"))
    approved = read_json(c.ctx.character_dir(c.cid) / "gates/G6-pv1.json")
    assert any(a["ref"].endswith("formation-dialogues.json") for a in approved["shownArtifacts"])
    with pytest.raises(ValueError, match="short"):
        load_prompt_pair(c.ctx, c.cid)
    state = c.ctx.state(c.cid)
    state.transition("s7", "RUNNING", rev="tr2")
    write_once_json(
        c.ctx.character_dir(c.cid) / "s7-traits/tr2/trait-sheet.json", {"invalid": "newer"}
    )
    persona, sources, pair, sheet, problems = load_persona(c.ctx, c.cid)
    assert not problems
    assert persona.shortPrompt is None
    assert sheet.characterId == c.cid
    assert any(s.rel.endswith("persona-bundle.json") for s in sources)


def test_g6_rejects_mismatched_pair_identity_before_approval(formation_case):
    from character_factory_poc.common.store import read_json

    c = formation_case
    run_s7(c.ctx, c.cid)
    out = run_s8(c.ctx, c.cid, [])
    path = out / "prompt-pair.json"
    obj = read_json(path)
    obj["characterId"] = "different"
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="identity|metadata"):
        approve_g6(c.ctx, c.cid, dict(decision="APPROVE", reviewer="test"))
    assert c.ctx.state(c.cid).gate("G6").status == "AWAITING_HUMAN"


def test_s11_rejects_changed_persona_version_after_approval(formation_case):
    from character_factory_poc.common.canonical import sha256_text
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s11_release.package import load_persona

    c = formation_case
    run_s7(c.ctx, c.cid)
    out = run_s8(c.ctx, c.cid, [])
    approve_g6(c.ctx, c.cid, dict(decision="APPROVE", reviewer="test"))
    path = out / "persona-version.json"
    obj = read_json(path)
    obj["long"].update(text="unapproved change", sha256=sha256_text("unapproved change"), chars=17)
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="approved|version"):
        load_persona(c.ctx, c.cid)


@pytest.mark.parametrize("missing", ["long.md", "prompt-probe.json", "gate-G6.html"])
def test_s8_resume_finishes_saved_bundle_and_pending_gate(formation_case, missing):
    c = formation_case
    run_s7(c.ctx, c.cid)
    out = run_s8(c.ctx, c.cid, [])
    (out / missing).unlink()
    state = c.ctx.state(c.cid)
    state.set_gate("G6", "PENDING", None, None)
    assert run_s8(c.ctx, c.cid, []) == out
    assert (out / missing).exists()
    assert len(c.model.requests) == 2
    assert c.ctx.state(c.cid).gate("G6").status == "AWAITING_HUMAN"
