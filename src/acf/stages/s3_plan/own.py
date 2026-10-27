"""사람이 직접 쓴 상세 기획을 u1 후보로 정리하고 G3 선택을 기다린다."""

from __future__ import annotations

from pathlib import Path

from acf.common.budget import CallPlan
from acf.common.errors import AgentFormatError, CheckFailed, NeedsInputError
from acf.common.store import next_rev, write_once_text
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context
from acf.stages.s3_plan.check_v2 import check_own
from acf.stages.s3_plan.check_v2 import codex_checks as codex_checks
from acf.stages.s3_plan.variants import _config, _example, _fix_plan, _inputs, _preflight, _publish


def plan_calls(ctx: Context) -> list[CallPlan]:
    count = 3 + _config(ctx)["max_check_retries"]
    return [CallPlan("s3-own", "직접 쓴 기획 정리(형식·검사 재시도 포함)", count)]


def run_s3_own(ctx: Context, cid: str, user_text: str) -> Path:
    seed, appearance, guard = _preflight(ctx, cid)
    if not user_text.strip():
        raise NeedsInputError("직접 쓴 상세 기획이 비어 있다. 정리할 내용을 입력한다")
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx))
    rev = next_rev(ctx.character_dir(cid) / "s3-plan", "pr")
    rev_dir = ctx.character_dir(cid) / "s3-plan" / rev
    ctx.state(cid).transition("s3", "RUNNING", rev=rev)
    try:
        write_once_text(rev_dir / "user-text.md", user_text)
        inputs = _inputs(seed, appearance, guard, rev)
        inputs["user-text.md"] = user_text
        example = _example(seed, appearance, rev)
        example["variantId"] = "u1"
        example["evidence"] = {
            "coreTraits": [
                {"kind": "USER", "ref": "user-text.md", "quote": "<사용자 원문의 정확한 인용>"}
            ]
        }
        result = run_agent(
            AgentSpec(
                role="plan_normalizer",
                output_contract="character-plan-v2",
                stage="s3-own",
                max_check_retries=_config(ctx)["max_check_retries"],
            ),
            rev_dir / "workspace",
            inputs,
            [check_own(seed, guard, user_text)],
            ctx.text_model(cid, budget),
            ref=f"{cid}/{rev}",
            contract_example=example,
            backend=ctx.agent_backend(cid, budget, "s3-own"),
        )
        if not result.ok:
            raise CheckFailed("s3", result.problems)
        plan = _fix_plan(result.output, seed, appearance, rev, "u1", own=True)
        return _publish(ctx, cid, rev_dir, seed, [plan], "own")
    except (CheckFailed, AgentFormatError) as exc:
        ctx.state(cid).transition("s3", "CHECK_FAILED", rev=rev, error=str(exc))
        if isinstance(exc, AgentFormatError):
            raise CheckFailed("s3", [str(exc)]) from exc
        raise
