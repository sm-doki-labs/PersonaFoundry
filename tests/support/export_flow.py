"""S11·doki-app 내보내기 시험용 합성 승인 흐름. 네트워크·유료 호출 없음.

`tests/support/flow.py`의 S1→S2→G3→S4경로 위에 G5·G5b·G6을 이어 붙이고, 필요하면
S9·S10 산출물(데이터셋·학습·평가)과 G7·G8 기록을 손으로 고정한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.stages.s4_frames.run import run_s4
from character_factory_poc.stages.s5_intro.run import run_s5
from character_factory_poc.stages.s6_actions.run import run_s6
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.flow import approve_plan_v2, make_ctx, sample_plan_v2, through_s2
from tests.support.synthetic import prompter_output, trait_sheet
from tests.test_scene_flow import backgrounds, poses, scenes, through_pose


def full_flow(root: Path) -> tuple[Context, str]:
    """S1 → G1 → S2 → G3 → G4b → G4 → G5 → G5b → G6까지 승인한 캐릭터."""
    ctx, agents = make_ctx(root)
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    cid = through_s2(ctx)
    agents.set("s7", lambda req: _trait_sheet(cid))
    agents.set("s8", lambda req: prompter_output())
    text = ctx._text
    text.add("PROBE", lambda req: "그럼 이렇게 하자. 내일 아침에 같이 보자.")
    text.add("JUDGE", {"pick": "A", "reasons": "선택이 더 맞는다"})

    approve_plan_v2(ctx, cid)
    through_pose(ctx, cid)
    run_s4(ctx, cid)
    approve_gate(ctx, cid, "G4", {"decision": "APPROVE", "reviewer": "test"})
    run_s5(ctx, cid)
    approve_gate(ctx, cid, "G5", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    run_s6(ctx, cid)
    approve_gate(ctx, cid, "G5b", {"decision": "APPROVE", "reviewer": "test"})
    run_s7(ctx, cid)
    run_s8(ctx, cid, ["시험 망쳤어.", "너 발표 잘하더라."])
    approve_gate(ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test"})
    return ctx, cid


def _trait_sheet(cid: str) -> dict[str, Any]:
    """합성 기획서(v2)의 핵심 성격을 그대로 언급하는 특질 시트."""
    plan = sample_plan_v2(cid)
    sheet = trait_sheet(cid, "pr1")
    sheet["card"]["expressedTraits"]["core"] = list(plan["coreTraits"])
    sheet["card"]["expressedTraits"]["contrast"] = plan["contrastTrait"]
    return sheet


def fix_sft(ctx: Context, cid: str, *, adopted: str = "gemma-binding") -> dict[str, str]:
    """S9·S10 산출물과 G7·G8 기록을 합성 자료로 고정한다(패키지 sft 칸 시험)."""
    char_dir = ctx.character_dir(cid)
    dataset_rev = "ds1"
    rev_dir = char_dir / "s9-data" / dataset_rev
    split = rev_dir / "train.jsonl"
    split.parent.mkdir(parents=True, exist_ok=True)
    split.write_text('{"messages": []}\n', encoding="utf-8")
    dataset = validate(
        "dataset-rev-v2",
        {
            "characterId": cid,
            "datasetRev": dataset_rev,
            "personaVersion": "pv1",
            "planSha256": "a" * 64,
            "sampleQaRefs": ["s9-data/ds1/samples/base.json"],
            "clusterCounts": {"base": {"conversations": 1, "replies": 1}},
            "files": [
                {"split": "train", "path": "train.jsonl", "sha256": "b" * 64, "conversations": 1}
            ],
            "blockingFailures": 0,
            "warnings": 0,
            "digest": "c" * 64,
        },
    )
    write_once_json(rev_dir / "dataset.json", dump(dataset))
    write_manifest(rev_dir)

    train = char_dir / "s10-train" / "tr1" / "gemma_qlora"
    run = validate(
        "training-run-v2",
        {
            "characterId": cid,
            "datasetRev": dataset_rev,
            "datasetDigest": "c" * 64,
            "provider": "gemma_qlora",
            "baseModel": "gemma-4-31b-it",
            "requestedConfig": {"epochs": 2},
            "dryRun": True,
            "estimate": {"usd": 3.0, "gpuHours": 1.0, "basis": "합성"},
            "budgetUsd": 20.0,
            "status": "PLANNED",
            "modelBinding": {"provider": "gemma_qlora", "ref": adopted, "checkpointId": "ck1"},
        },
    )
    write_once_json(train / "training-run.json", dump(run))

    ev = char_dir / "s10-eval" / "ev1"
    report = validate(
        "eval-report-v2",
        {
            "characterId": cid,
            "preregSha256": "d" * 64,
            "runRefs": [{"ref": "s10-eval/ev1/runs/LONG_BASE-OE.json", "sha256": "e" * 64}],
            "metrics": [{"armId": "LONG_BASE", "metric": "memory_recall_200", "value": 0.9}],
            "criteriaResults": [
                {"id": "memory_recall_200", "armId": "LONG_BASE", "value": 0.9, "passed": True}
            ],
            "llmPairs": [],
            "recommendation": "두 경로 모두 기준을 넘었다",
        },
    )
    write_once_json(ev / "report.json", dump(report))

    state = ctx.state(cid)
    for stage, gate, rev in (("s9", "G7", dataset_rev), ("s10", "G8", "ev1")):
        state.transition(stage, "RUNNING", rev=rev)
        state.transition(stage, "AWAITING_HUMAN", rev=rev)
        write_gate_record(
            char_dir,
            state,
            gate=gate,
            rev=rev,
            stage_id=stage,
            shown=[],
            decision="APPROVE",
            reviewer="test",
            reasons="합성 승인",
            selections=[adopted] if gate == "G8" else [],
        )
    return {"datasetRev": dataset_rev, "binding": adopted}


def approve_package(ctx: Context, cid: str) -> str:
    from character_factory_poc.stages.s11_release.approve import approve_g9

    rev = ctx.state(cid).gate("G9").rev or ""
    approve_g9(ctx, cid, {"decision": "APPROVE", "reasons": "시험 승인", "reviewer": "test"})
    return rev


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


__all__ = ["approve_package", "fix_sft", "full_flow", "next_rev", "write_json"]
