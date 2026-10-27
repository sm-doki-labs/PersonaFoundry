"""관문 승인 일반화 (G1, G3, G4a, G4b, G4, G5, G5b, G6). G2는 결번이다(D-0042)."""

from __future__ import annotations

from pathlib import Path

from acf.common.errors import FactoryError
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record
from acf.pipeline.graph import RETIRED_GATES


def approve_gate(ctx: Context, cid: str, gate: str, answer: dict) -> Path:
    if gate == "G1":
        from acf.stages.s1_reference.approve import approve_g1

        return approve_g1(ctx, cid, answer)
    if gate == "G2":
        raise FactoryError(
            RETIRED_GATES["G2"]
            + ". G1에서 얼굴을 고른 뒤 acf hero run(S2)이 자동으로 외모 명세를 고정한다. "
            '기준 이미지 생성이 필요하면 factory.toml [stages.s2] base_photo = "picked"를 쓴다'
        )
    if gate == "G4a":
        from acf.stages.s4a_backgrounds.approve import approve_g4a

        return approve_g4a(ctx, cid, answer)
    if gate == "G4b":
        from acf.stages.s4b_poses.approve import approve_g4b

        return approve_g4b(ctx, cid, answer)
    if gate == "G4":
        from acf.stages.s4_frames.approve import approve_g4

        return approve_g4(ctx, cid, answer)
    if gate == "G5":
        from acf.stages.s5_intro.approve import approve_g5

        return approve_g5(ctx, cid, answer)
    if gate == "G5b":
        from acf.stages.s6_actions.approve import approve_g5b

        return approve_g5b(ctx, cid, answer)
    if gate == "G6":
        from acf.stages.s8_prompts.approve import approve_g6

        return approve_g6(ctx, cid, answer)
    if gate == "G3":
        char_dir = ctx.character_dir(cid)
        state = ctx.state(cid)
        g = state.gate("G3")
        if g.rev and (char_dir / "s3-plan" / g.rev / "variants.json").exists():
            # D-0033: 변형 후보 중 하나를 고르는(고친 칸 포함) 새 흐름
            from acf.stages.s3_plan.approve import approve_g3_variants

            return approve_g3_variants(ctx, cid, answer)
        if g.status != "AWAITING_HUMAN" or not g.rev:
            raise ValueError(f"{cid}: G3가 대기 상태가 아니다({g.status})")
        rev_dir = char_dir / "s3-plan" / g.rev
        rec = write_gate_record(
            char_dir,
            state,
            gate="G3",
            rev=g.rev,
            stage_id="s3",
            shown=[rev_dir / "plan.json"],
            decision=answer["decision"],
            reviewer=answer["reviewer"],
            reasons=answer.get("reasons", ""),
            minutes=float(answer.get("minutes", 0)),
            requested_changes=answer.get("requestedChanges"),
        )
        ctx.ledger(cid).record_human(gate="G3", minutes=rec.minutes, ref=f"{cid}/{g.rev}")
        return rev_dir
    raise ValueError(f"{gate} 관문 승인은 아직 구현되지 않았다")
