"""Synthetic evidence only: continuity, bounded sampling, and source provenance."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from character_factory_poc.stages.s8_prompts.evidence_source import (
    MAX_RECORD_CHARS,
    MAX_TURN_CHARS,
    prepare_records,
    validate_card,
)


def message(index, speaker, text, *, unit="a", at="2026-01-01T00:00:00"):
    return dict(
        msgId=f"{unit}-{index}", textId="synthetic", convId=unit, speaker=speaker, text=text, at=at
    )


def dialogue(texts, *, unit="a"):
    return [
        message(i, "USER" if i % 2 == 0 else "SUBJECT", text, unit=unit)
        for i, text in enumerate(texts)
    ]


def records(rows, **kwargs):
    return prepare_records(rows, [], set(), **kwargs)["records"]


def test_complete_merged_turns_and_five_turn_history_without_input_mutation():
    rows = dialogue([f"Synthetic turn {n}" for n in range(8)])
    rows += [
        message(8, "SUBJECT", "second part\nwith its own ending"),
        message(9, "USER", "next question"),
        message(10, "SUBJECT", "observed followup"),
        message(11, "SUBJECT", "full ending retained"),
    ]
    before = deepcopy(rows)
    result = {r["id"]: r for r in records(rows)}["a-7"]
    assert result == {
        "id": "a-7",
        "unit": ["synthetic", "a"],
        "context": "Synthetic turn 6",
        "target": "Synthetic turn 7 second part\nwith its own ending",
        "next": "next question",
        "followup": "observed followup full ending retained",
        "history": [
            {"speaker": "USER" if n % 2 == 0 else "SUBJECT", "text": f"Synthetic turn {n}"}
            for n in range(2, 7)
        ],
    }
    assert rows == before
    result["history"][0]["text"] = "changed output"
    assert rows == before


@pytest.mark.parametrize(
    "barrier",
    [
        "",
        "사진",
        "사진 3장",
        "(이모티콘)",
        "동영상",
        "음성메시지",
        "삭제된 메시지입니다.",
        "https://example.invalid/x",
        "www.example.invalid",
        "test@example.invalid",
        "010-0000-0000",
        "010 0000 0000",
        "01000000000",
        "12-3456-789012",
        "송금 요청",
        "100원을 보냈어요",
        "샵검색: 합성",
        "[전화번호]",
        "연락처 [이메일]",
        "[번호]",
        "[REDACTED]",
        "[MASKED]",
        "참여자1에게 물어봐",
        "[PII]",
        "<PHONE>",
    ],
)
def test_unsafe_message_splits_all_four_fields_and_history(barrier):
    rows = dialogue(
        [
            "earlier question",
            "earlier response",
            barrier,
            "orphan response",
            "fresh question",
            "fresh response",
        ]
    )
    result = {r["id"]: r for r in records(rows)}
    assert set(result) == {"a-1", "a-5"}
    assert result["a-1"]["next"] is None
    assert result["a-1"]["followup"] is None
    assert result["a-5"]["history"] == [
        {"speaker": "SUBJECT", "text": "orphan response"},
        {"speaker": "USER", "text": "fresh question"},
    ]


@pytest.mark.parametrize(
    "patch,flags", [({"speaker": "OTHER"}, set()), ({}, {"a-2"}), ({"text": None}, set())]
)
def test_other_speaker_and_flagged_or_invalid_text_are_boundaries(patch, flags):
    rows = dialogue(["before", "answer", "gap", "orphan", "after", "reply"])
    rows[2].update(patch)
    result = prepare_records(rows, [], flags)["records"]
    assert {r["id"] for r in result} == {"a-1", "a-5"}
    assert next(r for r in result if r["id"] == "a-1")["followup"] is None


@pytest.mark.parametrize("seconds,expected", [(1800, 1), (1801, 0), (-1, 0), (0, 1)])
def test_timestamp_boundary_is_inclusive_and_never_reorders(seconds, expected):
    start = datetime(2026, 1, 1)
    rows = [
        message(0, "USER", "question", at=start.isoformat()),
        message(1, "SUBJECT", "answer", at=(start + timedelta(seconds=seconds)).isoformat()),
    ]
    assert len(records(rows)) == expected


def test_custom_gap_and_boundary_before_followup():
    rows = dialogue(["question", "answer", "next", "followup"])
    rows[-1]["at"] = "2026-01-01T00:01:01"
    first = next(r for r in records(rows, max_gap_seconds=60) if r["id"] == "a-1")
    assert first["next"] == "next"
    assert first["followup"] is None


@pytest.mark.parametrize("stamp", ["invalid", 123, None, "2026-01-01T00:00:01+00:00"])
def test_unknown_or_incomparable_time_does_not_bridge_dated_messages(stamp):
    rows = dialogue(["before", "answer", "missing time", "orphan"])
    rows[2]["at"] = stamp
    first = next(r for r in records(rows) if r["id"] == "a-1")
    assert first["next"] is None
    assert first["followup"] is None
    assert not any(r["id"] == "a-3" for r in records(rows))


def test_undated_transcript_and_timezone_offsets_are_supported():
    rows = dialogue(["question", "answer", "next", "followup"])
    for row in rows:
        row.pop("at")
    assert next(r for r in records(rows) if r["id"] == "a-1")["followup"] == "followup"
    rows = dialogue(["question", "answer"])
    rows[0]["at"] = "2026-01-01T09:00:00+09:00"
    rows[1]["at"] = "2026-01-01T00:00:01Z"
    assert len(records(rows)) == 1


def test_time_gap_between_subject_fragments_prevents_false_merge_or_followup():
    rows = dialogue(["question", "answer", "next", "followup"])
    rows += [
        message(4, "SUBJECT", "later unrelated response", at="2026-01-01T01:00:00"),
        message(5, "USER", "new question", at="2026-01-01T01:00:01"),
        message(6, "SUBJECT", "new answer", at="2026-01-01T01:00:02"),
    ]
    result = {r["id"]: r for r in records(rows)}
    assert result["a-1"]["followup"] == "followup"
    assert result["a-3"]["target"] == "followup"
    assert result["a-3"]["next"] is None
    assert result["a-6"]["history"] == [
        {"speaker": "SUBJECT", "text": "later unrelated response"},
        {"speaker": "USER", "text": "new question"},
    ]


def test_user_fragments_merge_and_textid_is_part_of_unit_identity():
    rows = [
        message(0, "USER", "first question"),
        message(1, "USER", "continued"),
        message(2, "SUBJECT", "response"),
        message(3, "USER", "next"),
        message(4, "USER", "continued again"),
        message(5, "SUBJECT", "followup"),
    ]
    held = [message(6, "SUBJECT", "held text") | {"textId": "other-source"}]
    first = next(r for r in prepare_records(rows, held, set())["records"] if r["id"] == "a-2")
    assert first["context"] == "first question continued"
    assert first["next"] == "next continued again"
    assert first["followup"] == "followup"


def test_exclude_whole_holdout_units_and_return_only_sorted_holdout_ids():
    train = dialogue(["shared question", "shared response"], unit="shared")
    train += dialogue(["safe question", "safe response"], unit="safe")
    held = [
        message("z", "SUBJECT", "held content", unit="shared"),
        message("a", "USER", "other held content", unit="shared"),
    ]
    result = prepare_records(train, held, set())
    assert [r["id"] for r in result["records"]] == ["safe-1"]
    assert result["holdoutIds"] == ["shared-a", "shared-z"]
    assert result["stats"]["discarded_shared_units"] == 1
    assert "held content" not in str(result)


@pytest.mark.parametrize("where", ["train", "holdout", "cross"])
def test_duplicate_ids_rejected_even_inside_excluded_units(where):
    row = message(1, "SUBJECT", "synthetic", unit="shared")
    other = row | {"text": "different synthetic text"}
    train, held = {
        "train": ([row, other], [row | {"msgId": "h"}]),
        "holdout": ([], [row, other]),
        "cross": ([row], [other]),
    }[where]
    with pytest.raises(ValueError, match="duplicate|cross-split"):
        prepare_records(train, held, set())


@pytest.mark.parametrize(
    "field,value", [("msgId", ""), ("msgId", None), ("textId", []), ("convId", " ")]
)
def test_invalid_identity_rejected(field, value):
    row = message(1, "SUBJECT", "synthetic") | {field: value}
    with pytest.raises(ValueError):
        prepare_records([row], [], set())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_records": -1},
        {"max_records": True},
        {"max_records": 1.5},
        {"max_gap_seconds": -1},
        {"max_gap_seconds": False},
    ],
)
def test_invalid_limits_rejected(kwargs):
    with pytest.raises(ValueError):
        records([], **kwargs)


def test_empty_and_zero_budget_are_empty_but_still_validate_ids():
    assert records([]) == []
    rows = dialogue(["question", "answer"])
    assert records(rows, max_records=0) == []
    with pytest.raises(ValueError):
        records(rows + rows, max_records=0)


def test_deterministic_sample_balances_units_and_question_cues_and_caps_ids():
    groups = []
    for unit in ("a", "b", "c", "d"):
        texts = []
        for i in range(30):
            question = ("plain statement", "왜 그런지", "가능한가", "question?", "ㅋㅋ")
            texts += [question[i % len(question)], f"synthetic answer {i}"]
        groups.append(dialogue(texts, unit=unit))
    train = [row for group in groups for row in group]
    result = prepare_records(train, [], set(), max_records=20)
    assert result == prepare_records(
        [r for g in reversed(groups) for r in g], [], set(), max_records=20
    )
    sample = result["records"]
    assert len(sample) == len({r["id"] for r in sample}) == 20
    assert Counter(r["unit"][1] for r in sample) == dict.fromkeys("abcd", 5)
    assert len({r["context"] for r in sample}) == 5
    assert len(records(train)) == 80
    assert result["stats"]["heuristic_labels_semantically_validated"] is False
    assert not any(row["text"] in str(result["stats"]) for row in train)


def test_sparse_units_get_a_share_and_exhaustion_does_not_underfill():
    train = dialogue(["question", "answer"] * 40, unit="large")
    train += dialogue(["rare question", "rare answer"], unit="small")
    sample = records(train, max_records=10)
    assert len(sample) == 10
    assert Counter(r["unit"][1] for r in sample) == {"large": 9, "small": 1}
    assert "small" in {r["unit"][1] for r in records(train, max_records=2)}


def test_eligible_but_unsampled_id_cannot_be_cited():
    train = sum((dialogue(["question", "answer"], unit=u) for u in "abc"), [])
    sample = records(train, max_records=2)
    excluded = ({"a-1", "b-1", "c-1"} - {r["id"] for r in sample}).pop()
    _, card = sample_and_card()
    with pytest.raises(ValueError, match="unsampled"):
        validate_card(card | {"evidence": [sample[0]["id"], excluded]}, sample)


@pytest.mark.parametrize("position", range(4))
def test_huge_turn_discards_dependent_window_without_truncation(position):
    texts = ["question", "answer", "next", "followup"]
    texts[position] = "x" * (MAX_TURN_CHARS + 1)
    assert not any(r["id"] == "a-1" for r in records(dialogue(texts)))


def test_turn_at_limit_is_retained_completely():
    reply = "x" * (MAX_TURN_CHARS - 4) + "END!"
    sample = records(dialogue(["question", reply]))
    assert len(sample) == 1
    assert sample[0]["target"] == reply


def test_oversized_merged_turn_discards_prefix_and_cannot_bridge():
    rows = [
        message(0, "USER", "question"),
        message(1, "SUBJECT", "x" * MAX_TURN_CHARS),
        message(2, "SUBJECT", "overflow"),
        message(3, "SUBJECT", "tail"),
        message(4, "USER", "new question"),
        message(5, "SUBJECT", "new response"),
    ]
    result = records(rows)
    assert not any(r["id"] in {"a-1", "a-2", "a-3"} for r in result)
    assert all("tail" not in str(r["history"]) for r in result)


def test_total_record_budget_discards_rather_than_shortens_history():
    rows = dialogue([str(i) * MAX_TURN_CHARS for i in range(8)])
    result = records(rows)
    assert not any(r["id"] == "a-7" for r in result)
    for record in result:
        size = sum(len(record[k] or "") for k in ("context", "target", "next", "followup"))
        size += sum(len(turn["text"]) for turn in record["history"])
        assert size <= MAX_RECORD_CHARS


def sample_and_card():
    sample = records(
        dialogue(["question one", "answer one"], unit="a")
        + dialogue(["question two", "answer two"], unit="b")
    )
    card = dict(
        evidence=["a-1", "b-1"],
        trigger="On disagreement",
        first="Acknowledge",
        shift="On clarification",
        stop="After resolution",
        limit="Only if observed",
        rule="Keep the response conditional.",
    )
    return sample, card


def test_valid_provenance_returns_none_and_does_not_mutate():
    sample, card = sample_and_card()
    before = deepcopy((sample, card))
    assert validate_card(card, sample) is None
    assert (sample, card) == before


@pytest.mark.parametrize(
    "refs", [["a-1"], ["a-1", "a-1"], ["a-1", "missing"], [], "a-1", [None, "b-1"]]
)
def test_bad_or_unsampled_references_fail(refs):
    sample, card = sample_and_card()
    with pytest.raises(ValueError):
        validate_card(card | {"evidence": refs}, sample)


def test_two_distinct_ids_in_one_unit_do_not_establish_replication():
    sample, card = sample_and_card()
    sample[1]["unit"] = sample[0]["unit"].copy()
    with pytest.raises(ValueError, match="unit"):
        validate_card(card, sample)


@pytest.mark.parametrize("field", ["trigger", "first", "shift", "stop", "limit", "rule"])
@pytest.mark.parametrize("source", ["context", "target", "next", "followup", "history"])
def test_all_card_fields_checked_against_uncited_sample_raw_text(field, source):
    sample, card = sample_and_card()
    uncited = deepcopy(sample[0]) | {"id": "uncited", "unit": ["synthetic", "c"]}
    speech = "가 나 다 라 마 바 사 아 자 차 카 타"
    if source == "history":
        uncited["history"] = [{"speaker": "USER", "text": speech}]
    else:
        uncited[source] = speech
    sample.append(uncited)
    with pytest.raises(ValueError, match="copied"):
        validate_card(card | {field: "prefix\n가나다라마바\t사아자차카타 suffix"}, sample)


def test_exact_twelve_character_threshold_and_no_cross_field_false_match():
    sample, card = sample_and_card()
    sample[0]["target"] = "abcdefghijkl"
    assert validate_card(card | {"rule": "abcdefghijk"}, sample) is None
    with pytest.raises(ValueError, match="copied"):
        validate_card(card | {"rule": "a b c d e f\ng h i j k l"}, sample)
    sample[0].update(target="abcdef", context="ghijkl")
    assert validate_card(card | {"rule": "abcdefghijkl"}, sample) is None


def test_ambiguous_sample_ids_rejected_and_errors_do_not_echo_speech():
    sample, card = sample_and_card()
    with pytest.raises(ValueError):
        validate_card(card, sample + [deepcopy(sample[0])])
    sample[0]["target"] = "synthetic private utterance marker"
    with pytest.raises(ValueError) as caught:
        validate_card(card | {"rule": sample[0]["target"]}, sample)
    assert "synthetic private" not in str(caught.value)
