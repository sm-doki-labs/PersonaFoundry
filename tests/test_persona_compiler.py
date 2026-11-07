"""고정 컴파일은 평가 점수·모델 호출 없이 정본과 예시를 묶는다."""

from __future__ import annotations

import importlib.util

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.formation import (
    FormationDialogues,
    PersonaBlueprint,
    load_quality_profile,
)
from tests.support.synthetic import PLAN, trait_sheet
from tests.test_formation_contracts import blueprint, dialogues


def sources(tmp_path):
    plan = validate("character-plan-v1", PLAN | {"characterId": "synthetic", "planRev": "pr1"})
    cid = plan.characterId
    sheet = validate("trait-sheet-v1", trait_sheet(cid, plan.planRev))
    pp, sp = tmp_path / "plan.json", tmp_path / "trait-sheet.json"
    write_once_json(pp, dump(plan))
    write_once_json(sp, dump(sheet))
    bp = blueprint() | dict(
        characterId=cid,
        planRev=plan.planRev,
        planSha256=sha256_file(pp),
        traitSheetSha256=sha256_file(sp),
    )
    for ref in bp["sourceRefs"]:
        ref["sha256"] = sha256_file(pp if ref["kind"] == "plan" else sp)
    bp = PersonaBlueprint.model_validate(bp)
    bp_path = tmp_path / "blueprint.json"
    write_once_json(bp_path, dump(bp))
    ds = dialogues() | dict(
        characterId=cid,
        planSha256=sha256_file(pp),
        traitSheetSha256=sha256_file(sp),
        blueprintSha256=sha256_file(bp_path),
    )
    for ref in ds["sourceRefs"]:
        ref["sha256"] = ds[
            {"plan": "planSha256", "trait": "traitSheetSha256", "blueprint": "blueprintSha256"}[
                ref["kind"]
            ]
        ]
    ds = FormationDialogues.model_validate(ds)
    dp = tmp_path / "dialogues.json"
    write_once_json(dp, dump(ds))
    return (
        plan,
        sheet,
        bp,
        ds,
        {
            "plan": sha256_file(pp),
            "trait": sha256_file(sp),
            "blueprint": sha256_file(bp_path),
            "dialogues": sha256_file(dp),
        },
    )


def test_compile_keeps_canon_and_chooses_four_stable_examples(tmp_path):
    assert importlib.util.find_spec("character_factory_poc.stages.s8_prompts.compiler")
    from character_factory_poc.stages.s8_prompts.compiler import compile_persona

    plan, sheet, bp, ds, hashes = sources(tmp_path)
    result = compile_persona(
        plan,
        sheet,
        bp,
        ds,
        load_quality_profile(),
        source_hashes=hashes,
        trait_revision="tr1",
        persona_version="pv1",
        rules_text="기본 규칙",
        rules_ref="builtin:test",
    )
    assert result.selectedDialogueIds == ["d01", "d05", "d09", "d11"]
    assert "CHARACTER_EXAMPLES" in result.long.text
    assert plan.name in result.long.text and plan.job in result.long.text
    assert "실제 이력" in result.long.text
    assert result == compile_persona(
        plan,
        sheet,
        bp,
        ds,
        load_quality_profile(),
        source_hashes=hashes,
        trait_revision="tr1",
        persona_version="pv1",
        rules_text="기본 규칙",
        rules_ref="builtin:test",
    )


def test_compile_rejects_mismatched_source_and_never_truncates(tmp_path):
    assert importlib.util.find_spec("character_factory_poc.stages.s8_prompts.compiler")
    from character_factory_poc.stages.s8_prompts.compiler import compile_persona

    plan, sheet, bp, ds, hashes = sources(tmp_path)
    kwargs = dict(
        source_hashes=hashes,
        trait_revision="tr1",
        persona_version="pv1",
        rules_text="규칙" * 5000,
        rules_ref="builtin:test",
    )
    with pytest.raises(ValueError, match="상한"):
        compile_persona(plan, sheet, bp, ds, load_quality_profile(), **kwargs)
    kwargs["source_hashes"] = hashes | {"plan": "b" * 64}
    with pytest.raises(ValueError, match="hash"):
        compile_persona(plan, sheet, bp, ds, load_quality_profile(), **kwargs)
