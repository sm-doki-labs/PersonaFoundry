"""Deck-specific brief extraction and voice finalization around Gemini drafts.

D-0086(2026-11-05): 설정 검토(GPT) → 수정 → 재검토 단계를 뺐다. 실제 실행에서 이 고리가 서로 다른
이유로 S3를 반복해서 멈췄고(K-0072), Argon 수정 뒤에도 재검토가 같은 지적을 남겼다. 초안 다음에
말투 두 칸만 확정하고, 후보 판단은 G3 사람 검토가 맡는다.
"""

import re

from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.choice_design import SeedRequirementsDraft
from character_factory_poc.contracts.planning import PlanVariantsOutput
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.formation_step import run_typed_step

#: voiceSummary에서 읽는 말높임 이름. 한 후보에 둘 이상 적으면 섞어 쓴다는 뜻이다.
SPEECH_LEVELS = {
    "하십시오체": re.compile(r"하십시오체|합쇼체|합니다체"),
    "해요체": re.compile(r"해요체"),
    "반말": re.compile(r"반말|(?<!해요)해체"),
}


def brief(ctx, cid, folder, seed, budget):
    return dump(
        run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=folder / "deck-brief",
            role="seed_requirements",
            contract=SeedRequirementsDraft,
            stage="s3",
            inputs={"seed": dump(seed)},
            budget=budget,
        )
    )


def mixed_speech_levels(out: PlanVariantsOutput) -> list[str]:
    """voiceSummary가 말높임 둘 이상을 섞으면 문제로 돌려준다.

    2026-11-05 말투 확정 단계에서 Flash·Argon 모두 '해요체와 하십시오체'를 적었다.
    """
    problems = []
    for p in out.variants:
        found = [name for name, rx in SPEECH_LEVELS.items() if rx.search(p.voiceSummary)]
        if len(found) > 1:
            problems.append(
                f"{p.variantId}.voiceSummary: 말높임을 하나로 정한다"
                f"({' + '.join(found)}를 섞었다). 브리프 말투 확인 문장의 말높임을 따르고 "
                "voiceExamples도 같은 말높임으로 쓴다"
            )
    return problems


#: D-0090: voiceSummary는 대화 프롬프트 말투 칸에 그대로 들어간다. 지시문 목표는 300~550자다.
VOICE_SUMMARY_MAX = 700


def voice_summary_length(out: PlanVariantsOutput) -> list[str]:
    return [
        f"{p.variantId}.voiceSummary: {len(p.voiceSummary)}자다. 범주마다 한 번만 써서 "
        f"{VOICE_SUMMARY_MAX}자 안으로 줄인다"
        for p in out.variants
        if len(p.voiceSummary) > VOICE_SUMMARY_MAX
    ]


def finish(ctx, cid, folder, seed, draft, budget, checks):
    original = {p.variantId: dump(p) for p in draft.variants}
    allowed = {(p.variantId, f) for p in draft.variants for f in ("voiceSummary", "voiceExamples")}
    axis_note = draft.axisNote

    def preserve_axis(out):
        return [] if out.axisNote == axis_note else ["axisNote: 허용된 수정 필드가 아니다"]

    result = run_agent(
        # 말높임 혼용만 자동 검사로 한 번 다시 쓰게 한다. 다른 모델의 의견을 받는 단계가 아니다.
        AgentSpec("deck_plan_voice", "plan-variants-output-v1", "s3", max_check_retries=1),
        folder / "deck-voice",
        {"draft": dump(draft), "seed": dump(seed)},
        checks
        + [
            preserve_axis,
            lambda out: _unchanged(original, out, allowed),
            mixed_speech_levels,
            voice_summary_length,
        ],
        ctx.task_model(cid, budget, "voice"),
        ref=f"{cid}/{folder.name}/deck_plan_voice",
        contract_example=dump(draft),
    )
    if not result.ok:
        raise CheckFailed("s3", result.problems)
    return result.output


def _unchanged(original: dict, out: PlanVariantsOutput, allowed: set) -> list[str]:
    if list(original) != [p.variantId for p in out.variants]:
        return ["수정 중 후보 ID나 순서를 바꿀 수 없다"]
    problems = []
    for p in out.variants:
        for field, value in dump(p).items():
            if (p.variantId, field) not in allowed and original[p.variantId][field] != value:
                problems.append(f"{p.variantId}.{field}: 허용된 수정 필드가 아니다")
    return problems
