import json

import pytest

import acf.contracts  # noqa: F401
from acf.common.budget import Budget, CallPlan
from acf.common.config import BudgetConfig
from acf.common.errors import BudgetExceeded, ImmutableWriteError, ValidationFailed
from acf.common.ids import character_id, is_valid
from acf.common.schema import validate
from acf.common.store import next_rev, verify_manifest, write_manifest, write_once_json
from acf.common.textstats import looks_like_bare_adjectives, section_names
from acf.providers.base import extract_json_object


def test_write_once(tmp_path):
    p = tmp_path / "a.json"
    assert write_once_json(p, {"x": 1}) is True
    assert write_once_json(p, {"x": 1}) is False
    with pytest.raises(ImmutableWriteError):
        write_once_json(p, {"x": 2})


def test_manifest_roundtrip(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    write_manifest(tmp_path)
    assert verify_manifest(tmp_path) == []
    (tmp_path / "f.txt").write_text("changed")
    assert verify_manifest(tmp_path)


def test_next_rev(tmp_path):
    assert next_rev(tmp_path, "pv") == "pv1"
    (tmp_path / "pv1").mkdir()
    (tmp_path / "pv3").mkdir()
    assert next_rev(tmp_path, "pv") == "pv4"


def test_ids():
    cid = character_id("haneul")
    assert is_valid("character_id", cid)
    with pytest.raises(ValueError):
        character_id("Bad Slug")


def test_budget():
    b = Budget(BudgetConfig(max_calls_per_command=3), max_calls_override=10)
    b.check_plan([CallPlan("s7", "x", 3)])
    with pytest.raises(BudgetExceeded):
        b.check_plan([CallPlan("s7", "x", 4)])
    b.consume(3)
    with pytest.raises(BudgetExceeded):
        b.consume(1)


def test_section_names_and_adjectives():
    assert section_names("[A]\nx\n\n[PERSONA / VOICE]\ny\n") == ["A", "PERSONA / VOICE"]
    assert looks_like_bare_adjectives("밝음, 솔직함, 자신감")
    assert not looks_like_bare_adjectives("칭찬을 받으면 짧게 받고 화제를 돌린다.")


def test_extract_json_object():
    fenced = "\x60\x60\x60json\n" + '{"a": {"b": "}"}}' + "\n\x60\x60\x60"
    assert extract_json_object(fenced) == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        extract_json_object("no json here")


def test_contract_rejects_unknown_fields():
    with pytest.raises(ValidationFailed) as e:
        validate("gate-record-v1", {"schemaVersion": "gate-record-v1", "bogus": 1})
    assert any("bogus" in p for p in e.value.problems)


def test_plan_rejects_appearance_evidence_for_personality():
    from tests.support.synthetic import PLAN

    obj = dict(
        PLAN,
        characterId="cf-20260101-x",
        planRev="pr1",
        evidence={"coreTraits": [{"kind": "APPEARANCE", "ref": "ar1", "quote": ""}]},
    )
    with pytest.raises(ValidationFailed) as e:
        validate("character-plan-v1", obj)
    assert any("D-0005" in p for p in e.value.problems)
    ok = dict(
        PLAN,
        characterId="cf-20260101-x",
        planRev="pr1",
        evidence={"coreTraits": [{"kind": "BRIEF", "ref": "s3", "quote": "..."}]},
    )
    validate("character-plan-v1", ok)
    json.dumps(ok)
