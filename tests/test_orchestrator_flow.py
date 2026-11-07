"""새 흐름의 오케스트레이터 전체 경로 (D-0033~D-0035). 네트워크 없음.

씨앗이 없으면 S3는 사람 입력을 기다리고 S5 소개 영상 갈래가 먼저 돈다. 씨앗을 넣고 다시 돌리면
변형 → G3 → (S3r 건너뜀) → 배경 → G4a → 장면·자세 → G4b → 완성 이미지 → G4까지 이어진다.
"""

from __future__ import annotations

import json

from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.stages.s4_frames.approve import load_approved_frames
from tests.support.flow import make_ctx
from tests.support.synthetic import RANKING
from tests.test_plan_variants import SEED, output
from tests.test_scene_flow import backgrounds, poses, scenes


def test_seed_wait_runs_intro_video_lane_then_full_scene_flow(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    from character_factory_poc.stages.s3_plan.common import new_character

    cid = new_character(ctx, "lanes")
    agents.set("s3-variants", lambda req: output(cid))
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)

    # 1차: 씨앗 없음. S3는 입력을 기다리고, 같은 실행에서 S5 소개 영상이 G5까지 간다.
    log = run_until(ctx, cid, RunOptions(until="G6", ranking=RANKING, auto_approve={"G1"}))
    st = ctx.state(cid)
    assert "s3" in log.blocked and any("사람 입력 대기" in s for s in log.steps)
    assert st.stage("s5").status == "AWAITING_HUMAN" and log.waiting == ["G5"]
    assert log.stopped_at == "G5" and st.stage("s3").status == "PENDING"
    assert st.stage("s4a").status == "PENDING" and st.stage("s7").status == "PENDING"

    # 2차: 씨앗을 넣고 기획·장면 관문을 자동 승인(실험 전용)해 G4까지 간다. G5는 계속 사람 대기다.
    log = run_until(
        ctx,
        cid,
        RunOptions(until="G4", seed=SEED, auto_approve={"G3", "G4a", "G4b", "G4"}),
    )
    st = ctx.state(cid)
    assert log.stopped_at == "G4" and st.gate("G4").status == "APPROVED"
    assert any("s5: G5 대기 중" in s for s in log.steps)
    assert st.stage("s3r").status == "SKIPPED"  # 색인 설정이 없으면 건너뛴다
    plan = json.loads(
        (ctx.character_dir(cid) / "s3-plan" / st.gate("G3").rev / "plan.json").read_text("utf-8")
    )
    assert plan["schemaVersion"] == "character-plan-v2" and plan["variantId"] == "v1"
    approved, rev_dir = load_approved_frames(ctx, cid)
    assert [f.chapterId for f in approved.frames] == ["ch1", "ch2", "ch3"]
    assert all((rev_dir / f.path).exists() for f in approved.frames)
    assert st.stage("s7").status == "PENDING"  # until=G4에서 멈췄다
