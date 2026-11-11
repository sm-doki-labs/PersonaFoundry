"""G6 승인 → persona_version 발급 (FR-23)."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.persona import PromptPairV2, load_prompt_pair
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record


def approve_g6(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    rev = state.gate("G6").rev
    if not rev or state.gate("G6").status != "AWAITING_HUMAN":
        raise ValueError(f"{cid}: G6가 대기 상태가 아니다({state.gate('G6').status})")
    rev_dir = char_dir / "s8-prompts" / rev
    shown = [rev_dir / "prompt-pair.json", rev_dir / "prompt-probe.json"]
    pair = load_prompt_pair(rev_dir / "prompt-pair.json")
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import is_evidence, verify_review

    if is_evidence(rev_dir):
        if answer["decision"] in {"APPROVE", "SELECT"}:
            if answer.get("evidenceReviewed") is not True:
                raise ValueError("원문 근거와 적용 조건을 직접 검토한 확인이 필요하다")
            verify_review(ctx, cid, rev_dir)
        shown += [
            rev_dir / name
            for name in (
                "evidence-binding.json",
                "evidence-packet.json",
                "evidence-review.json",
                "assembly.json",
            )
        ]
    tr = state.stage("s7").currentRev
    if isinstance(pair, PromptPairV2) or (rev_dir / "persona-bundle.json").exists():
        from character_factory_poc.stages.s8_prompts.formation import verify_bundle

        bundle, _, trait_path = verify_bundle(ctx, cid, rev_dir)
        tr = bundle.traitRevision
        shown += [
            rev_dir / "persona-bundle.json",
            trait_path.parent / "blueprint.json",
            trait_path.parent / "formation-dialogues.json",
            trait_path.parent / "profile.json",
        ]
    if tr:
        shown.append(char_dir / "s7-traits" / tr / "trait-sheet.json")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G6",
        rev=rev,
        stage_id="s8",
        shown=shown,
        decision=answer["decision"],
        reviewer=answer["reviewer"],
        reasons=answer.get("reasons", ""),
        minutes=float(answer.get("minutes", 0)),
        requested_changes=answer.get("requestedChanges"),
    )
    ctx.ledger(cid).record_human(gate="G6", minutes=rec.minutes, ref=f"{cid}/{rev}")
    if rec.decision == "APPROVE":
        pair = pair.model_copy(update={"personaVersion": rev})
        write_once_json(rev_dir / "persona-version.json", dump(pair))
        if (
            tr
            and state.stage("s7").currentRev == tr
            and state.stage("s7").status == "AWAITING_HUMAN"
        ):
            state.transition("s7", "APPROVED", rev=tr)
        write_manifest(rev_dir)
    return rev_dir
