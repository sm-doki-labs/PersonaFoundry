import pytest

from character_factory_poc.contracts.voice_bundle import CoveragePolicy
from character_factory_poc.stages.s8_prompts.choice_voice import select_covered_examples
from tests.test_persona_beats import beats_fixture
from tests.test_persona_voice_render import rendered_fixture


def test_core_choice_is_in_selected_examples():
    beats = beats_fixture()
    dialogues = rendered_fixture(beats)
    policy = CoveragePolicy(
        requiredRuleIds=["c1"],
        coverage={d.dialogueId: dict(tags=d.coverageTags, ruleIds=["c1"]) for d in beats.dialogues},
    )
    assert select_covered_examples(dialogues, policy) == ["d00", "d01", "d02", "d03"]


def test_coverage_gap_fails_without_truncation():
    beats = beats_fixture()
    dialogues = rendered_fixture(beats)
    policy = CoveragePolicy(
        requiredRuleIds=["missing"],
        coverage={d.dialogueId: dict(tags=d.coverageTags, ruleIds=["c1"]) for d in beats.dialogues},
    )
    with pytest.raises(ValueError, match="COVERAGE_GAP"):
        select_covered_examples(dialogues, policy)
