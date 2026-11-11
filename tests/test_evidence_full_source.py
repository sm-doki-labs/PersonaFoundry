import json

import pytest

from character_factory_poc.stages.s8_prompts.evidence_full_source import prepare_full_source


def rows(n=120):
    return [
        dict(
            msgId=f"m{i}",
            textId="t",
            convId=f"c{i // 12}",
            speaker="USER" if i % 2 == 0 else "SUBJECT",
            text=f"합성 발화 {i} " + ("가" * 40),
            at=None,
        )
        for i in range(n)
    ]


def test_all_messages_are_chunked_with_no_eighty_record_sampling():
    data = rows(400)
    s = prepare_full_source(data, [], set(), max_chunk_chars=2200)
    assert s["coverage"]["complete"]
    assert set(s["coverage"]["includedMessageIds"]) == {r["msgId"] for r in data}
    assert len(s["records"]) == 200
    for c in s["chunks"]:
        assert len(json.dumps(c, ensure_ascii=False)) <= 2200
        assert set(c["recordIds"]) == {
            t["id"] for x in c["segments"] for t in x["turns"] if t["speaker"] == "SUBJECT"
        }


def test_initial_subject_and_user_only_are_covered():
    data = rows(3)
    data[0]["speaker"] = "SUBJECT"
    data[1]["speaker"] = "USER"
    s = prepare_full_source(data, [], set())
    assert set(s["coverage"]["includedMessageIds"]) == {"m0", "m1", "m2"}
    assert s["records"][0]["context"] == ""


def test_excluded_private_message_is_a_barrier_with_a_reason():
    data = rows(6)
    data[2]["text"] = "private@example.test"
    s = prepare_full_source(data, [], set())
    assert "private@example.test" not in json.dumps(s)
    assert s["coverage"]["excluded"] == [dict(id="m2", reason="private_or_media")]
    r = next(r for r in s["records"] if r["id"] == "m3")
    assert r["history"] == [] and r["context"] == ""


def test_time_gap_does_not_synthesize_reply():
    data = rows(2)
    data[0]["at"] = "2026-01-01T00:00:00"
    data[1]["at"] = "2026-01-01T01:00:00"
    s = prepare_full_source(data, [], set())
    assert s["records"][0]["context"] == ""


def test_holdout_id_overlap_is_rejected():
    with pytest.raises(ValueError):
        prepare_full_source(rows(), [rows()[0]], set())


def test_oversized_turn_has_explicit_exclusion():
    data = rows(2)
    data[1]["text"] = "가" * 5000
    s = prepare_full_source(data, [], set())
    assert s["coverage"]["excluded"] == [dict(id="m1", reason="oversized_turn")]
