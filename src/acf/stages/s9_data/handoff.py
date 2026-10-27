"""클러스터별 인계안 작성 (LLD §8.8 2단계, 가이드 §4·§7).

특질 시트의 선택 기준 5항목과 상황별 변화를 `behaviorTable`(상황 → 먼저 보는 것 → 고르는
행동 → 말투)로 좁힌 인계안을 작성 모델로 만든다. 사람은 G7a에서 샘플과 함께 이 문서를 본다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from acf.common.budget import CallPlan
from acf.common.schema import dump, register
from acf.common.store import write_once_json
from acf.common.textstats import looks_like_bare_adjectives
from acf.contracts.common import Strict
from acf.contracts.dataset import BehaviorRow, DataHandoff, DataPlan
from acf.contracts.persona import PromptPair, TraitSheet
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context


@register("data-handoff-output-v1")
class HandoffOutput(Strict):
    behaviorTable: list[BehaviorRow] = Field(min_length=3, max_length=8)
    voiceExamples: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    notes: str = ""


def check_handoff(out: HandoffOutput) -> list[str]:
    problems: list[str] = []
    if len(out.behaviorTable) < 3:
        problems.append("behaviorTable은 3행 이상이다")
    for i, row in enumerate(out.behaviorTable, start=1):
        if not all(s.strip() for s in (row.situation, row.attention, row.choice, row.voice)):
            problems.append(f"{i}행: situation·attention·choice·voice를 모두 채운다")
        elif looks_like_bare_adjectives(row.choice):
            problems.append(f"{i}행: choice가 형용사 나열이다. 동사로 끝나는 행동으로 쓴다")
    if len(out.voiceExamples) < 2:
        problems.append("voiceExamples는 2개 이상이다")
    if not out.forbidden:
        problems.append("forbidden은 1개 이상이다. 이 클러스터에서 하면 안 되는 패턴을 적는다")
    return problems


def cluster_input(plan: DataPlan, cluster_id: str) -> dict[str, Any]:
    for c in plan.clusters:
        if c.clusterId == cluster_id:
            return {
                "clusterId": c.clusterId,
                "label": c.label,
                "share": c.share,
                "targetConversations": c.targetConversations,
                "materials": list(c.materials),
                "sampleSize": c.sampleSize,
            }
    raise ValueError(f"계획에 없는 클러스터다: {cluster_id}")


def build_handoff(
    ctx: Context,
    cid: str,
    *,
    plan: DataPlan,
    plan_sha: str,
    cluster_id: str,
    pair: PromptPair,
    sheet: TraitSheet,
    workspace: Path,
    stage: str,
    retries: int,
    memo: str = "",
) -> DataHandoff:
    budget = ctx.budget()
    model = ctx.text_model(cid, budget)
    inputs = {
        "trait-sheet": dump(sheet),
        "cluster": cluster_input(plan, cluster_id),
        "prompt-short": pair.short.text,
        "memo": memo,
    }
    spec = AgentSpec(
        role="data_handoff",
        output_contract="data-handoff-output-v1",
        stage=stage,
        max_check_retries=retries,
    )
    result = run_agent(
        spec,
        workspace,
        inputs,
        [check_handoff],
        model,
        ref=f"{cid}/{workspace.parent.name}/{cluster_id}-handoff",
        contract_example={
            "behaviorTable": [
                {"situation": "...", "attention": "...", "choice": "...", "voice": "..."}
            ],
            "voiceExamples": ["..."],
            "forbidden": ["..."],
            "notes": "...",
        },
        backend=ctx.agent_backend(cid, budget, stage),
    )
    if not result.ok:
        from acf.common.errors import CheckFailed

        raise CheckFailed(stage, [f"{cluster_id} 인계안: {p}" for p in result.problems])
    out: HandoffOutput = result.output
    notes = out.notes.strip()
    if memo:
        notes = (notes + "\n\n검토자 메모: " + memo).strip()
    return DataHandoff(
        characterId=cid,
        planSha256=plan_sha,
        clusterId=cluster_id,  # type: ignore[arg-type]
        behaviorTable=out.behaviorTable,
        voiceExamples=out.voiceExamples,
        forbidden=out.forbidden,
        notes=notes,
    )


def write_handoff(path: Path, handoff: DataHandoff) -> None:
    write_once_json(path, dump(handoff))


def plan_calls(cluster_count: int, retries: int) -> list[CallPlan]:
    return [
        CallPlan(
            "s9s",
            f"클러스터 {cluster_count}개 인계안 작성 (재시도 포함 최대 {1 + retries}회)",
            cluster_count * (1 + retries),
        )
    ]
