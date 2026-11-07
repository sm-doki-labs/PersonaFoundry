"""D-0080: cfp plan import·draft가 신형(character-plan-v2)으로만 기획을 고정한다."""

import json

import pytest

from character_factory_poc.cli import main
from character_factory_poc.common.errors import NeedsInputError
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.importer import import_plan, load_approved_plan
from tests.support.flow import make_ctx, sample_plan_v2, v2_plan
from tests.support.synthetic import PLAN


def test_v2_plan_import_is_fixed_with_seed_and_approved(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    source = tmp_path / "plan.json"
    raw = v2_plan("cf-ignored")
    for key in ("characterId", "planRev", "seedRev", "variantId", "evidence"):
        raw.pop(key)
    source.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
    out = import_plan(ctx, "import-v2", source)
    assert out["mode"] == "approved" and agents.calls == []
    plan, path = load_approved_plan(ctx, out["characterId"])
    assert isinstance(plan, CharacterPlanV2)
    assert plan.seedRev == "sd1" and plan.variantId == "u1" and plan.appearanceRev is None
    assert (path.parent.parent / "seeds" / "sd1.json").exists()
    assert ctx.state(out["characterId"]).gate("G3").status == "APPROVED"


def test_v1_plan_needs_execute_then_becomes_v2_candidate(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    source = tmp_path / "old.json"
    source.write_text(json.dumps(PLAN, ensure_ascii=False), "utf-8")
    dry = Context(ctx.config, execute=False)
    with pytest.raises(NeedsInputError, match="--execute"):
        import_plan(dry, "import-v1", source)
    assert not (tmp_path / "runs" / "characters").exists()

    def normalize(req):
        text = "\n".join(m.content for m in req.messages)
        assert "구형 기획서" in text and PLAN["coreTraits"][0] in text
        cid = json.loads(text.split('"characterId": ')[1].split(",")[0])
        return sample_plan_v2(
            cid,
            variant="u1",
            appearanceRev=None,
            coreTraits=list(PLAN["coreTraits"]),
            evidence={
                "coreTraits": [{"kind": "USER", "ref": "user-text.md", "quote": "먼저 제안한다"}]
            },
        )

    agents.set("s3-own", normalize)
    out = import_plan(ctx, "import-v1", source)
    assert out["mode"] == "upgraded"
    variants = json.loads((out["path"] / "variants.json").read_text("utf-8"))
    assert variants["mode"] == "own" and variants["candidates"][0]["schemaVersion"] == (
        "character-plan-v2"
    )
    assert ctx.state(out["characterId"]).gate("G3").status == "AWAITING_HUMAN"


def test_cli_plan_draft_and_v1_import_dry_runs_make_no_character(tmp_path, capsys):
    make_ctx(tmp_path)
    brief = tmp_path / "brief.md"
    brief.write_text("말수가 적고 도구를 고쳐 쓰는 성인 정비사.", "utf-8")
    assert main(["--root", str(tmp_path), "plan", "draft", "cli", "--brief", str(brief)]) == 0
    old = tmp_path / "old.json"
    old.write_text(json.dumps(PLAN, ensure_ascii=False), "utf-8")
    assert main(["--root", str(tmp_path), "plan", "import", "old", "--from", str(old)]) == 0
    out = capsys.readouterr().out
    assert "호출 계획" in out and "--execute" in out
    assert not (tmp_path / "runs" / "characters").exists()
