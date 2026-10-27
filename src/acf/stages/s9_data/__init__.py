"""S9 데이터셋 단계 (LLD §5.14·§8.8, D-0044·D-0045).

두 그래프 단계로 나뉜다: `s9s`(인계안·샘플, 관문 G7a)와 `s9`(대량 작성·검사·분할, 관문 G7).
`stages/`는 `pipeline/`에 의존하지 않는다(LLD §2). 다만 기존 단계와 같은 방식으로
`Context`를 받아 상태·원장·예산을 쓴다.
"""

from __future__ import annotations

from acf.common.budget import CallPlan


def plan_calls(ctx, cid: str, stage: str = "s9s") -> list[CallPlan]:
    """명령 dry run용 호출 계획. 통합 담당이 `acf data plan|samples|build`에 연결한다."""
    from acf.stages.s9_data import build, plan, samples

    if stage == "s9s":
        return samples.plan_calls(ctx, cid)
    if stage == "s9":
        return build.plan_calls(ctx, cid)
    return plan.plan_calls()


__all__ = ["plan_calls"]
