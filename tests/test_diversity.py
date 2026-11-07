"""D-0100 기획 다양성 단서."""

import json

from character_factory_poc.stages.s3_plan.diversity import (
    avoid_list,
    draw_anchors,
    load_anchors,
    recent_anchor_values,
)


def test_draw_is_deterministic_and_distinct_within_run():
    a = draw_anchors("cf-x", "pr1", 3)
    assert a == draw_anchors("cf-x", "pr1", 3)
    for cat in load_anchors():
        assert len({row[cat] for row in a}) == 3


def test_exclude_recent_values_when_pool_allows():
    first = draw_anchors("cf-x", "pr1", 3)
    used = {v for row in first for k, v in row.items() if k != "variantId"}
    second = draw_anchors("cf-x", "pr1", 3, exclude=used)
    assert not used & {v for row in second for k, v in row.items() if k != "variantId"}


def test_recent_values_and_avoid_list_skip_current_character(tmp_path):
    for cid, name in (("cf-a", "가나"), ("cf-b", "다라")):
        inp = tmp_path / cid / "s3-plan" / "pr1" / "workspace" / "inputs"
        inp.mkdir(parents=True)
        (inp / "diversity-anchors.json").write_text(
            json.dumps([{"variantId": "v1", "자란 곳": cid}])
        )
        (tmp_path / cid / "s3-plan" / "pr1" / "variants.json").write_text(
            json.dumps({"candidates": [{"name": name, "profileCard": {"hobby": "낚시"}}]})
        )
    assert recent_anchor_values(tmp_path, "cf-a") == {"cf-b"}
    assert avoid_list(tmp_path, "cf-a") == {"names": ["다라"], "hobbies": ["낚시"], "foods": []}
