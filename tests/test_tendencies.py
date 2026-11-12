"""D-0148: 모티브 원문 경향. 원문 전체의 상황·반응을 세어 되풀이된 경향만 특질로 쓴다."""

import json

import pytest

from character_factory_poc.common.errors import CheckFailed, ValidationFailed
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s3_plan import tendencies as T
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.ledger import check_ledger
from tests.test_trait_ledger import _ledger
from tests.test_twin_s3 import _answer, _ready


def _pairs(spec):
    """spec: (msgId, 자리) 목록."""
    return [
        {"msgId": m, "occasion": occ, "year": "2020", "question": "", "answer": f"답 {m}"}
        for m, occ in spec
    ]


def test_tendency_needs_three_occasions_not_three_answers():
    pairs = _pairs(
        [
            ("a1", "v1@d"),
            ("a2", "v1@d"),
            ("a3", "v1@d"),
            ("b1", "v1@d"),
            ("b2", "v2@d"),
            ("b3", "v3@d"),
            ("c1", "v4@d"),
        ]
    )
    tags = (
        [
            {"id": m, "situation": "PRAISE", "moves": ["CREDIT_OTHERS"], "evidence": ""}
            for m in ("a1", "a2", "a3")
        ]
        + [
            {"id": m, "situation": "PRAISE", "moves": ["SELF_DEPRECATE"], "evidence": f"답 {m}"}
            for m in ("b1", "b2", "b3")
        ]
        + [{"id": "c1", "situation": "OTHER", "moves": ["OTHER"], "evidence": ""}]
    )
    agg = T.aggregate(pairs, tags)
    rows = {r["cell"]: r for r in agg["rows"]}
    # 한 영상에서 세 번 한 말은 일화이고, 세 자리에서 한 번씩 한 말이 경향이다.
    assert rows["PRAISE/CREDIT_OTHERS"]["kind"] == "ANECDOTE"
    assert rows["PRAISE/SELF_DEPRECATE"]["kind"] == "TENDENCY"
    assert rows["PRAISE/SELF_DEPRECATE"]["share"] == 0.5
    assert agg["situations"] == {"PRAISE": 6} and agg["tagged"] == 7
    assert "PRAISE" in agg["thinSituations"] and not agg["enforced"]
    assert T.tendency_cells(agg) == {m: ["PRAISE/SELF_DEPRECATE"] for m in ("b1", "b2", "b3")}
    view = T.agent_view(agg)
    assert [t["cell"] for t in view["tendencies"]] == ["PRAISE/SELF_DEPRECATE"]
    assert "msgIds" not in json.dumps(view)


def test_rare_tendency_is_not_a_main_tendency(monkeypatch):
    # 자리가 많아도 그 상황 답에서 드물게 나온 반응은 특질로 올리지 않는다.
    pairs = _pairs([(f"a{i}", f"v{i}@d") for i in range(10)])
    tags = [
        {"id": f"a{i}", "situation": "TEAMMATE", "moves": ["OWN_EXPERIENCE"], "evidence": ""}
        for i in range(10)
    ]
    for t in tags[:3]:
        t["moves"].append("HOLD_LINE")
    monkeypatch.setattr(T, "MAIN_SHARE", 0.35)
    rows = {r["cell"]: r for r in T.aggregate(pairs, tags)["rows"]}
    assert rows["TEAMMATE/HOLD_LINE"]["kind"] == "TENDENCY"
    assert not rows["TEAMMATE/HOLD_LINE"]["main"] and rows["TEAMMATE/OWN_EXPERIENCE"]["main"]


def test_parse_tags_drops_unknown_ids_and_labels():
    raw = {
        "items": [
            {"id": "x", "situation": "NOPE", "moves": ["ADMIT", "BAD", "ADMIT"]},
            {"id": "y", "situation": "FANS", "moves": []},
            {"id": "x"},
            "junk",
        ]
    }
    assert T.parse_tags(raw, {"x"}) == [
        {"id": "x", "situation": "OTHER", "moves": ["ADMIT"], "evidence": ""}
    ]


def test_s3_binds_traits_to_tendencies_and_reuses_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "MIN_OCCASIONS", 2)
    monkeypatch.setattr(T, "MIN_TENDENCY_CELLS", 1)
    ctx, model, cid = _ready(tmp_path)

    def tags(req):
        items = json.loads(req.messages[-1].content)
        last = items[-1]["id"]
        return {
            "items": [
                {
                    "id": it["id"],
                    "situation": "FAMILY" if it["id"] == last else "TASTE",
                    "moves": ["ADMIT" if it["id"] == last else "OWN_EXPERIENCE"],
                    "evidence": it["answer"][:8],
                }
                for it in items
            ]
        }

    model.add(f"s3:{cid}/pr1/tendencies/0", tags)
    ctx.config.stages["s3t"] = {"analysis_mode": "exhaustive", "max_check_retries": 0}
    # 기본 응답은 세 번째 선택의 근거로 한 번만 나온 답을 쓴다.
    with pytest.raises(CheckFailed, match="주요 경향"):
        run_s3_twin(ctx, cid)
    first = ctx.character_dir(cid) / "s3-plan/pr1"
    agg = read_json(first / "tendencies.json")
    assert agg["enforced"] and agg["schemaVersion"] == T.SCHEMA

    def grounded(req):
        out = _answer(req)
        out["evidence"]["choices"][2] = out["evidence"]["choices"][0]
        return out

    model.add("AGENT", grounded)
    judged = sum(r.kind == "JUDGE" for r in model.requests)
    folder = run_s3_twin(ctx, cid)
    # 같은 승인 원문과 같은 표시 지시면 앞 revision의 표시를 다시 쓴다.
    assert sum(r.kind == "JUDGE" for r in model.requests) == judged
    assert read_json(folder / "tendencies.json") == agg
    page = (folder / "gate-G3.html").read_text("utf-8")
    assert "원문 경향" in page and "자기 경험을 구체적으로 들어 설명한다" in page
    assert "원문 근거가 적은 상황" in page


def _motif(**over):
    traits = [t | {"basis": "TASTE/OWN_EXPERIENCE"} for t in _ledger().model_dump()["traits"]]
    traits[0] |= {"kind": "choice"}
    return _ledger(traits=traits, **over)


def test_motif_ledger_needs_tendency_basis_not_an_invented_insult_reaction():
    ledger = _motif()
    assert "insult_reaction" not in [t.kind for t in ledger.traits]
    view = {"tendencies": [{"cell": "TASTE/OWN_EXPERIENCE"}]}
    problems = check_ledger("인물", view)(ledger)
    assert not [p for p in problems if "basis" in p]
    # 같은 상황의 경향은 trait 하나로 합친다.
    assert sum("같은 상황(TASTE)" in p for p in problems) == 2
    other = check_ledger("인물", {"tendencies": [{"cell": "PRAISE/ADMIT"}]})(ledger)
    assert sum("basis" in p for p in other) == 3
    assert any("basis" in p for p in check_ledger("인물")(ledger))
    traits = _ledger().model_dump()["traits"]
    traits[0]["basis"] = "TASTE/OWN_EXPERIENCE"
    with pytest.raises(ValidationFailed, match="basis"):
        _ledger(traits=traits)
    # 오리지널 장부의 시비 반응·결점 규칙은 그대로다.
    assert "basis" not in json.dumps(_ledger().model_dump(mode="json", exclude_none=True))
