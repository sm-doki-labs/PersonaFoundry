"""공개 사실 검색·인용·사람의 제외 선택을 합성 자료로 확인한다."""

import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s0_source import facts
from character_factory_poc.stages.s0_source.run import run_s0
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.actor_persona import (
    compose_from_ledger,
    load_actor_rules,
)
from character_factory_poc.stages.s8_prompts.build import run_s8
from character_factory_poc.stages.s8_prompts.twin import approved_facts
from tests.support.flow import v2_plan
from tests.support.web_gates import trait_sheet_for
from tests.test_source_s0 import _twin, _write_pack
from tests.test_text_model_deck import configured
from tests.test_trait_ledger import _ledger
from tests.test_motif_choices import demo_ledger
from tests.test_twin_s3 import CANARY, _ctx, _input, _ready


def fact(fid="first", **kw):
    return (
        dict(
            factId=fid,
            text="푸른 대회에 출전했다.",
            eventDate="2026-04-02",
            category="RESULT",
            importance=2,
            sources=[dict(url="https://example.org/report", title="공식 발표")],
        )
        | kw
    )


def test_rank_keeps_dated_public_sourced_items_within_both_caps():
    rows = [
        fact(),
        fact("old", eventDate="2020-03-03", text="첫 공연을 열었다."),
        fact("high", importance=3, text="현역 활동을 이어 간다."),
        fact(eventDate="2026-02-30"),
        fact(sources=[]),
        fact(text="열애 소문이 났다."),
        fact(sources=[{"url": "자료 없음", "title": "미상"}]),
        fact("dup"),
    ]
    assert [f.factId for f in facts.rank(rows, 10, 700)[0]] == ["high", "first", "old"]
    assert len(facts.rank(rows, 1, 700)[0]) == 1
    assert not facts.rank(rows, 10, 6)[0]


def test_quote_must_match_approved_subject_and_fallback_is_separate():
    rows = [
        dict(msgId=k, speaker=s, text=t)
        for k, s, t in [
            ("a", "SUBJECT", "마지막 무대가 좋았어요"),
            ("b", "USER", "누구와 갔어요"),
            ("c", "SUBJECT", "비교 전용"),
            ("d", "SUBJECT", "그건 비밀이죠"),
        ]
    ]
    base = dict(factId="first", paraphrase="본인은 마지막 무대가 좋았다고 한다.")
    bad = [
        dict(msgId=k, quote=q)
        for k, q in [
            ("z", "없음"),
            ("b", "누구와"),
            ("c", "비교 전용"),
            ("a", "전혀 다른 말"),
            ("a", ""),
        ]
    ]
    good = dict(msgId="a", quote="무대가 좋았어요")

    class Provider(facts.FakeFactsProvider):
        def propose(self, items, corpus):
            assert "비교 전용" not in str(corpus)
            return self.proposals

    provider = Provider(
        proposals=dict(
            views=[base | q for q in bad],
            deflections=bad + [dict(msgId="d", quote="그건 비밀이죠")],
        )
    )
    doc = facts.collect(provider, [fact()], rows, {"c"})
    assert doc.items[0].selfView is None
    assert doc.phrases() == ["그건 비밀이죠", "그런 얘기는 따로 안 하고 있어요"]
    provider.proposals["views"].append(base | good)
    assert facts.collect(provider, [fact()], rows, {"c"}).items[0].selfView.msgId == "a"


def test_gemini_uses_only_same_line_citations_and_never_searches_corpus(monkeypatch):
    a = "RESULT\t2026-04-02\t3\t푸른 대회 우승"
    b = "CAREER\t2020-04-02\t1\t첫 무대"
    log = []

    def post(url, *, headers, json, timeout):
        assert url.endswith("/models/fixture:generateContent")
        if "tools" in json:
            assert json["tools"] == [{"google_search": {}}]
            assert "합성 발화" not in str(json)
            candidate = dict(
                content={"parts": [{"text": a + "\n" + b}]},
                groundingMetadata=dict(
                    groundingChunks=[{"web": {"uri": "https://example.org/real", "title": "발표"}}],
                    groundingSupports=[
                        dict(
                            segment=dict(startIndex=0, endIndex=len(a.encode())),
                            groundingChunkIndices=[0],
                        )
                    ],
                ),
            )
        else:
            assert "합성 발화" in str(json)
            candidate = dict(content={"parts": [{"text": '{"views":[],"deflections":[]}'}]})
        return httpx.Response(200, json={"candidates": [candidate]})

    monkeypatch.setenv("GEMINI_API_KEY", "합성키")
    monkeypatch.setattr(httpx, "post", post)
    api = facts.GeminiFactsProvider(
        "fixture",
        SimpleNamespace(record_call=lambda **kw: log.append(kw)),
        SimpleNamespace(consume=lambda: None),
        "검사",
    )
    doc = facts.collect(
        api, api.search("합성 인물"), [dict(msgId="m", speaker="SUBJECT", text="합성 발화")], set()
    )
    assert [f.text for f in doc.items] == ["푸른 대회 우승"]
    assert str(doc.items[0].sources[0].url) == "https://example.org/real"
    assert len(log) == 2 and all(entry["ok"] for entry in log)


@pytest.mark.parametrize("mode", ["replace", "merge"])
def test_manual_pack_path_and_gate_exclusions(tmp_path, monkeypatch, mode):
    ctx, _ = _ctx(tmp_path)
    cid = _twin(ctx)
    path = _write_pack(tmp_path, kind="PUBLIC_FIGURE")
    raw = read_json(path) | {"factsPath": "manual.json"}
    path.write_text(json.dumps(raw))
    path.with_name("manual.json").write_text(json.dumps({"items": [fact()]}))
    ctx.config.stages["s0"] = {"facts": {"manual_mode": mode}}
    calls = []

    def search(self, subject):
        calls.append(subject)
        return [fact("extra", text="은빛 상을 받았다.")]

    monkeypatch.setattr(facts.FakeFactsProvider, "search", search)
    rev = run_s0(ctx, cid, path)
    assert bool(calls) == (mode == "merge")
    page = (rev / "gate-G0.html").read_text()
    assert "first" in page and "https://example.org/report" in page and "excludedFactIds" in page
    answer = dict(decision="APPROVE", reviewer="검토자")
    with pytest.raises(FactoryError, match="사실 ID"):
        approve_gate(ctx, cid, "G0", answer | {"excludedFactIds": ["unknown"]})
    approve_gate(ctx, cid, "G0", answer | {"excludedFactIds": ["first"]})
    doc = approved_facts(ctx, cid)
    assert [f.factId for f in doc.items] == (["extra"] if mode == "merge" else [])
    assert verify_manifest(rev) == []
    (rev / "facts.json").write_text("{}")
    with pytest.raises(ValueError, match="다르다"):
        approved_facts(ctx, cid)


def test_manual_path_checks_server_boundary_and_format(tmp_path, monkeypatch):
    file = tmp_path / "other.json"
    file.write_text("{}")
    monkeypatch.setenv("CFP_SERVER_MODE", "1")
    with pytest.raises(FactoryError, match="폴더 안"):
        facts.manual_path(file.name, tmp_path, tmp_path / "character")
    with pytest.raises(FactoryError, match="공개 사실 JSON"):
        facts.manual_path("없음", tmp_path, tmp_path)


def test_created_prompt_matches_prechange_bytes():
    p = dict(v2_plan("cf-20260101-x"), voiceSummary="정갈한 해요체로 짧게 말한다.")
    text, _ = compose_from_ledger(p, _ledger(), rules_text=load_actor_rules(origin="CREATED")[0])
    assert hashlib.sha256(text.encode()).hexdigest() == (
        "7c2644fd6daf784b33e96e7b322e3cca82655e14ad5274bac04fc83b45903fee"
    )


def test_public_facts_and_adjacent_self_view_reach_deck(tmp_path, monkeypatch):
    class Provider(facts.FakeFactsProvider):
        def search(self, subject):
            return [
                fact(category="CURRENT_STATUS", text="활동을 이어 간다고 밝혔다."),
                fact("hidden", text="제외된 행사에 갔다.", excluded=True),
            ]

        def propose(self, items, corpus):
            assert CANARY not in str(corpus)
            row = next(r for r in corpus if r["speaker"] == "SUBJECT")
            return {
                "views": [
                    dict(
                        factId="first",
                        msgId=row["msgId"],
                        quote=row["text"],
                        paraphrase="본인은 일상에 대해 짧게 말한다.",
                    )
                ]
            }

    monkeypatch.setattr(facts, "FakeFactsProvider", Provider)
    ctx, model, cid = _ready(tmp_path, "PUBLIC_FIGURE")
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v1"], reviewer="검토자"))
    ctx = Context(configured(tmp_path), execute=True)
    ctx.use_models(model)
    monkeypatch.setattr(ctx, "role_model", lambda cid, budget, role: ctx.text_model(cid, budget))
    model.add(
        "AGENT",
        lambda req: (
            demo_ledger(
                cid, _input(req, "character-plan")["evidence"]["choices"][0]["ref"]
            ).model_dump()
            if "/ledger" in req.ref
            else trait_sheet_for(ctx, cid)
        ),
    )
    ctx.config.stages["s7"] = {"formation_profile": "ko-text-choice-voice-long-v2"}
    run_s7(ctx, cid)
    pair = read_json(run_s8(ctx, cid, []) / "prompt-pair.json")
    assert pair["systemRulesRef"] == "builtin:actor-system-rules-v4-motif"
    for mode in ("long", "short"):
        text = pair[mode]["text"]
        assert len(text) <= 8000 and "제외된 행사" not in text
        assert "활동을 이어 간다고 밝혔다.\n본인은 일상에 대해 짧게 말한다." in text
        limits = text.split("[PERSONA / KNOWS_AND_LIMITS]")[1]
        assert all(word in limits for word in ("지난 경기", "활동을 이어", "그런 얘기는"))
