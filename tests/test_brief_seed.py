"""D-0080: 브리프 → 씨앗 변환과 S8 빈 섹션 거절."""

import pytest

from character_factory_poc.stages.s3_plan.seed import seed_fields_from_brief
from character_factory_poc.stages.s8_prompts.actor_persona import compose_approved_sheet
from tests.support.synthetic import PLAN

BRIEF = """# 캐릭터 기획 브리프

## 1. 타깃과 범위
- 서비스와 타깃 사용자: 관계형 대화 앱, 20대 후반~30대 초반 여성 사용자
- 캐릭터 성별·연령대: 남성, 29세
- 피해야 할 것: 상담사 같은 말투

## 4. 페르소나 방향
- 핵심 성격 2개와 대비 특징 1개: 꼼꼼하고 책임감이 강하다 / 대비: 친해지면 엉뚱한 농담을 던진다
- 말투 확인 문장: "괜찮다는 말, 표정이랑 안 맞는데요."
"""


def test_brief_becomes_seed_with_full_text_preserved():
    seed = seed_fields_from_brief(BRIEF)
    assert seed["personality"].startswith("꼼꼼하고 책임감이 강하다")
    # 타깃 사용자 줄의 "여성"이 아니라 캐릭터 성별 줄을 읽는다.
    assert seed["gender"] == "male"
    assert seed["age"] == 29
    assert seed["notes"] == BRIEF.strip()
    assert "상담사 같은 말투" in seed["notes"]


def test_unlabelled_brief_falls_back_to_first_line_and_rejects_empty():
    seed = seed_fields_from_brief("말수가 적고 도구를 고쳐 쓰는 성인 정비사.")
    assert seed["personality"] == "말수가 적고 도구를 고쳐 쓰는 성인 정비사."
    assert "gender" not in seed and "age" not in seed
    with pytest.raises(ValueError):
        seed_fields_from_brief("   ")


def test_s8_refuses_plan_without_section_sources():
    plan = dict(PLAN, schemaVersion="character-plan-v1", characterId="cf-x", planRev="pr1")
    with pytest.raises(ValueError, match="lifeAndTastes"):
        compose_approved_sheet(plan, None, rules_text="")


def test_topic_particle_follows_final_consonant():
    from character_factory_poc.stages.s8_prompts.actor_persona import _topic

    assert _topic("하진우") == "는"
    assert _topic("윤도현") == "은"
    assert _topic("Alex") == "은(는)"


def test_voice_summary_must_pick_one_speech_level():
    from character_factory_poc.stages.s3_plan.model_deck import mixed_speech_levels

    class P:
        def __init__(self, vid, s):
            self.variantId, self.voiceSummary = vid, s

    class Out:
        variants = [
            P("v1", "정갈한 해요체와 담백한 하십시오체."),
            P("v2", "짧은 반말."),
            P("v3", "해요체."),
        ]

    problems = mixed_speech_levels(Out())
    assert len(problems) == 1 and problems[0].startswith("v1.voiceSummary")
