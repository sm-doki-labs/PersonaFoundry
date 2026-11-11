from copy import deepcopy

import pytest

from character_factory_poc.stages.s8_prompts.contrast_pairs import analyze_pairs, blind_shortlist
from character_factory_poc.stages.s8_prompts.response_traits import sample


def rows():
    return [
        dict(textId="t", convId=str(i), msgId=f"{i}-{j}", text=f"{token} {i}", speaker=role)
        for i in range(24)
        for j, (role, token) in enumerate((("USER", "질문"), ("SUBJECT", "비공개 정답")))
    ]


def trial(mode=None):
    def reader(step, prompt, data):
        if step == "discover":
            evidence = [dict(id=i, topic=0, at=[0, 0]) for i in range(3)]
            rule = dict(
                situation="두 선택",
                cueA="A인 단서",
                cueB="B인 단서",
                focusA="대상1",
                focusB="대상2",
                moveA="확인",
                moveB="응원",
                A=evidence[:2],
                B=evidence[2:],
            )
            if mode == "overlap":
                rule["B"] = evidence[:1]
            return {"patterns": [rule]}
        assert mode != "overlap"
        if step == "route":
            assert (
                "비공개 정답" not in str(data)
                and "focusA" not in str(data)
                and "moveA" not in str(data)
            )
            return {
                "routes": [
                    dict(
                        key="0",
                        A=[{"id": 0, "marker": "질문"}],
                        B=[
                            {
                                "id": 1 if mode != "ambiguous" else 0,
                                "marker": "유출" if mode == "fake marker" else "질문",
                            }
                        ],
                    )
                ]
            }
        assert set(data["0"]) == {"actions", "scenes"} and "비공개 정답" in str(data)
        items = [dict(id=i, actual="A" if i == 0 else "B", topic=5, at=[0, 0]) for i in range(2)]
        if mode == "wrong":
            items[1]["actual"] = "neither"
        if mode == "citation":
            items[1]["at"] = [0, 5]
        if mode == "missing":
            items.pop()
        if mode == "same topic":
            for item in items:
                item["topic"] = 0
        return {"reviews": [dict(key="0", items=items)]}

    return analyze_pairs(rows(), set(), reader)


def test_predicts_both_branches_before_reading_the_answer():
    result = trial()
    assert len(result["patterns"]) == 1
    assert [c["hit"] for c in result["patterns"][0]["checks"]] == [True, True]
    assert set(result["discoveryScenes"]).isdisjoint(result["routedScenes"])


@pytest.mark.parametrize(
    "mode", ["overlap", "ambiguous", "fake marker", "wrong", "citation", "same topic"]
)
def test_refuses_unverifiable_contrasts(mode):
    result = trial(mode)
    assert not result["patterns"] and result["rejected"]


def test_missing_review_is_not_a_pass():
    with pytest.raises(ValueError, match="누락"):
        trial("missing")


def test_shortlist_order_is_independent_of_hidden_answer_text_and_length():
    discovery, pool = sample(rows(), set(), pair=True, reservoir=True)
    ids = list(discovery)
    candidates = {"0": {"discovery": {"A": [{"id": ids[0]}], "B": [{"id": ids[1]}]}}}
    changed = deepcopy(pool)
    for s in changed.values():
        s["turns"][1] = ["다른 내용 " * 4000]
    assert list(blind_shortlist(candidates, discovery, pool)) == list(
        blind_shortlist(candidates, discovery, changed)
    )


def test_contrast_requires_explicit_opt_in_and_reserves_a_third_call():
    from character_factory_poc.stages.s8_prompts.build import motif_plan_calls

    def count(*args):
        return sum(plan.calls for plan in motif_plan_calls(0, *args, motif_compiler="v3"))

    assert count(False) == 1
    assert count(True) == count(True, "focus") == 3
    assert count(True, "contrast") == 4
    with pytest.raises(ValueError):
        count(True, "bad")
