import json

import pytest

from character_factory_poc.stages.s3_plan import trait_recommendations as traits


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / "traits.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "creator-trait-catalog-v1",
                "catalogId": "synthetic-v1",
                "source": {"sha256": "a" * 64, "kind": "authored"},
                "items": [
                    {
                        "traitId": f"P0{i}-T1",
                        "behavior": behavior,
                        "presetId": f"P0{i}",
                        "sourceField": f"presets[{i - 1}].expression_focus[0].behavior",
                        "role": role,
                        "domain": "합성",
                    }
                    for i, (behavior, role) in enumerate(
                        [
                            ("힘든 상대의 기분을 살피고 도움을 건넨다.", "core"),
                            ("혼자 쉬며 자기 시간을 지킨다.", "contrast"),
                            ("새로운 취미를 먼저 시도한다.", "core"),
                            ("시험 조건을 바꾸고 다음 실험 조건을 정한다.", "core"),
                        ],
                        1,
                    )
                ],
            },
            ensure_ascii=False,
        )
    )
    return traits.load_catalog(path)


def test_recommendations_retrieve_real_behaviors_without_applying_them(catalog):
    result = traits.recommend_traits("다정하고 배려한다", catalog=catalog)
    assert result["items"][0]["traitId"] == "P01-T1"
    assert result["items"][0]["behavior"] == catalog["items"][0]["behavior"]
    assert result["items"][0]["category"] == "reinforce"
    assert result["method"] == "lexical-v1"
    assert result["matchStatus"] == "matched"
    assert result["catalogSha256"] == catalog["catalogSha256"]


def test_unmatched_input_still_allows_optional_exploration(catalog):
    result = traits.recommend_traits("외계의 보랏빛 존재", catalog=catalog)
    assert result["matchStatus"] == "limited"
    assert result["items"]
    assert all(x["category"] == "explore" for x in result["items"])


def test_pride_does_not_recommend_experimental_conditions_from_generic_word_overlap(catalog):
    result = traits.recommend_traits("자존심이 세다", catalog=catalog)
    assert result["items"][0]["traitId"] == "P02-T1"


def test_search_and_selection_exclusions_are_independent(catalog):
    result = traits.recommend_traits(
        "다정", selected_ids=["P01-T1"], search="혼자", catalog=catalog
    )
    assert [x["traitId"] for x in result["items"]] == ["P02-T1"]
    empty = traits.recommend_traits("다정", search="없는검색어", catalog=catalog)
    assert empty["items"] == []


def test_selected_traits_keep_literal_behavior_and_source_snapshot(catalog):
    selected = traits.resolve_traits(["P02-T1"], catalog=catalog)
    assert selected[0].behavior == "혼자 쉬며 자기 시간을 지킨다."
    assert selected[0].catalogSha256 == catalog["catalogSha256"]
    assert selected[0].sourceCatalogSha256 == "a" * 64
    assert selected[0].sourceField == "presets[1].expression_focus[0].behavior"
    assert traits.resolve_traits([], catalog=catalog) == []


@pytest.mark.parametrize("ids", [["missing"], ["P01-T1", "P01-T1"]])
def test_unknown_or_duplicate_selection_is_rejected(ids, catalog):
    with pytest.raises(ValueError):
        traits.resolve_traits(ids, catalog=catalog)


def test_changed_catalog_and_forged_snapshots_are_rejected(catalog):
    with pytest.raises(ValueError, match="카탈로그"):
        traits.resolve_traits(["P01-T1"], catalog_sha="b" * 64, catalog=catalog)
    item = traits.resolve_traits(["P01-T1"], catalog=catalog)[0]
    forged = item.model_copy(update={"behavior": "다른 원문"})
    with pytest.raises(ValueError):
        traits.verify_selected_traits([forged], catalog=catalog)


def test_limit_bounds_and_dismissed_choices(catalog):
    with pytest.raises(ValueError):
        traits.recommend_traits("다정", limit=0, catalog=catalog)
    result = traits.recommend_traits("다정", dismissed_ids=["P01-T1"], catalog=catalog)
    assert "P01-T1" not in [x["traitId"] for x in result["items"]]


def test_nearby_behavior_family_does_not_fill_the_entire_recommendation_list(catalog):
    duplicate = dict(
        catalog["items"][0],
        traitId="P05-T1",
        presetId="P05",
        behavior="상대의 기분과 필요한 도움을 먼저 살핀다.",
    )
    catalog["items"].append(duplicate)
    result = traits.recommend_traits("다정하고 배려한다", catalog=catalog)
    assert len([x for x in result["items"] if x["category"] == "reinforce"]) == 1


def test_skipped_duplicate_family_does_not_hide_a_different_trait_of_that_preset(catalog):
    original = catalog["items"][0]
    catalog["items"] += [
        dict(
            original,
            traitId="P05-T1",
            presetId="P05",
            behavior="상대의 기분과 필요한 도움을 먼저 살핀다.",
        ),
        dict(
            original,
            traitId="P05-T2",
            presetId="P05",
            domain="다른 계열",
            behavior="낯선 취향을 천천히 발견한다.",
            role="contrast",
        ),
    ]
    result = traits.recommend_traits("다정하고 배려한다", catalog=catalog)
    assert "P05-T2" in [x["traitId"] for x in result["items"]]
