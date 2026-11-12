"""evidence-v7: one-line transport, conversation-bordered repacking, per-conversation citation.

Synthetic data only; no paid calls and no real chat text.
"""

import json
import math
from copy import deepcopy

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
from character_factory_poc.stages.s8_prompts import evidence_tendencies as m
from character_factory_poc.stages.s8_prompts.evidence_atomic import partition, partition_compact
from character_factory_poc.stages.s8_prompts.evidence_full_source import (
    TRANSPORT,
    lines_size,
    prepare_full_source,
)


def rows(convs=40, turns=12, words=6):
    out = []
    for c in range(convs):
        for i in range(turns):
            n = c * turns + i
            out.append(
                dict(
                    msgId=f"m{n:05d}",
                    textId="t",
                    convId=f"c{c:03d}",
                    speaker="USER" if i % 2 == 0 else "SUBJECT",
                    text=f"합성 발화 {n} " + "가나다 " * words,
                    at=None,
                )
            )
    return out


def test_lines_transport_keeps_records_coverage_and_bounds():
    data = rows()
    old = prepare_full_source(data, [], set(), max_chunk_chars=6000)
    new = prepare_full_source(data, [], set(), max_chunk_chars=6000, transport=TRANSPORT)
    assert new["records"] == old["records"] and new["coverage"] == old["coverage"]
    assert "transport" not in old and new["transport"] == dict(format=TRANSPORT, maxChunkChars=6000)
    assert all(lines_size(c["segments"]) <= 6000 for c in new["chunks"])
    assert len(new["chunks"]) < len(old["chunks"])
    # Every conversation fits, so none is cut across chunks.
    homes = {}
    for c in new["chunks"]:
        for s in c["segments"]:
            homes.setdefault(tuple(s["unit"]), set()).add(c["id"])
    assert all(len(v) == 1 for v in homes.values())
    with pytest.raises(ValueError):
        prepare_full_source(data, [], set(), transport="yaml")


def test_each_half_is_repacked_minimally_on_conversation_borders():
    data = rows(convs=48)
    v4 = prepare_full_source(data, [], set(), max_chunk_chars=6000)
    with pytest.raises(ValueError, match="한 줄 원문"):
        partition_compact(v4)
    source = prepare_full_source(data, [], set(), max_chunk_chars=6000, transport=TRANSPORT)
    old_dev, old_check, old_split = partition(source)
    dev, check, split = partition_compact(source)
    assert split["developmentUnits"] == old_split["developmentUnits"]
    assert split["confirmationUnits"] == old_split["confirmationUnits"]
    assert split["schemaVersion"] == "evidence-partition-v2"
    assert [c["id"] for c in split["developmentChunks"]] == [c["id"] for c in dev]
    per_chunk = None
    for chunks, units in [(dev, split["developmentUnits"]), (check, split["confirmationUnits"])]:
        assert chunks and all(c["segments"] and c["recordIds"] for c in chunks)
        assert all(lines_size(c["segments"]) <= 6000 for c in chunks)
        seen = [tuple(s["unit"]) for c in chunks for s in c["segments"]]
        assert sorted(seen) == sorted(tuple(u) for u in units)  # each unit once, whole
        ids = [t["id"] for c in chunks for s in c["segments"] for t in s["turns"]]
        assert len(ids) == len(set(ids))
        # Equal-size conversations: the count is the lower bound for whole-unit packing.
        per_chunk = per_chunk or max(len(c["segments"]) for c in chunks)
        assert len(chunks) == math.ceil(len(units) / per_chunk)
    assert len(dev) + len(check) < len(old_dev) + len(old_check)


def chunk2():
    def turns(u, n):
        return [
            t
            for i in range(n)
            for t in (
                dict(id=f"{u}u{i}", speaker="USER", text=f"{u} 질문 {i}"),
                dict(id=f"{u}s{i}", speaker="SUBJECT", text=f"{u} 대답 {i}\n둘째 줄"),
            )
        ]

    segs = [dict(unit=["t", "A"], turns=turns("A", 4)), dict(unit=["t", "B"], turns=turns("B", 2))]
    return dict(
        id="dev-0001",
        segments=segs,
        recordIds=[t["id"] for s in segs for t in s["turns"] if t["speaker"] == "SUBJECT"],
    )


def claim(n=1):
    return dict(
        id=f"tendency-{n:02d}",
        section="VOICE",
        function="질문에 대한 답",
        dimension="response",
        trigger="상대가 질문했을 때",
        realization="짧은 서술로 답한다.",
        linguisticLevel="syntax",
        exclusion="질문이 없으면 확대하지 않는다.",
        observability="prior_context",
        evidence=["As0"],
    )


def item(rid, form="present"):
    u, i = rid[0], rid[2:]
    return dict(
        responseTurnId=rid,
        conditionTurnId=f"{u}u{i}",
        conditionQuote=f"{u} 질문 {i}",
        responseQuote=f"{u} 대답 {i}",
        applicability="yes",
        functionMatch="present",
        formMatch=form,
        reason="합성",
    )


def payload(claims=None):
    c = chunk2()
    return dict(
        role="r", scene="s", facts="f", chunk=c, targets=m.targets(c), claims=claims or [claim()]
    )


def test_compact_body_sends_lines_without_local_id_lists():
    p = payload()
    body = m.compact_payload("tendency-audit", p)
    assert set(body) == {"role", "scene", "facts", "chunk", "claims", "citationLimits"}
    assert body["chunk"]["format"] == TRANSPORT and set(body["chunk"]) == {"id", "format", "lines"}
    lines = body["chunk"]["lines"].split("\n")
    assert lines[0] == "## t A" and lines[1] == "Au0 U A 질문 0"
    assert lines[2] == "As0 S A 대답 0 ⏎ 둘째 줄"
    sent = json.dumps(body, ensure_ascii=False)
    assert "precedingUserIds" not in sent and "messageIds" not in sent
    assert len(sent) < len(json.dumps(p, ensure_ascii=False)) / 2
    disc = m.compact_payload("tendency-discover", dict(p, allowedIds=p["chunk"]["recordIds"]))
    assert "allowedIds" not in disc and "targets" not in disc and "citationLimits" not in disc


def test_one_citation_per_conversation_and_kind_is_counted():
    p = payload()
    bad = dict(item("Bs1"), responseQuote="지어낸 인용")
    items = [
        item("As0"),
        item("As1"),  # second support from conversation A
        item("As2", form="absent"),  # variation in A: a different kind, kept
        item("As3", form="absent"),  # second variation in A
        item("Bs0"),
        bad,
    ]
    out = {"findings": [dict(claimId="tendency-01", items=items, note="합성")]}
    m.validate_compact("tendency-audit", out, p)
    f = out["findings"][0]
    assert [i["responseTurnId"] for i in f["items"]] == ["As0", "As2", "Bs0"]
    assert [x["item"]["responseTurnId"] for x in f["overflowItems"]] == ["As1", "As3"]
    assert [x["item"]["responseTurnId"] for x in f["invalidItems"]] == ["Bs1"]
    saved = deepcopy(out)
    m.validate_compact("tendency-audit", out, p)  # cached output re-validates unchanged
    assert out == saved
    records = [dict(id=t, unit=["t", t[0]]) for t in p["chunk"]["recordIds"]]
    stats = m.aggregate_compact([out], p["claims"], records)["tendency-01"]
    assert stats["support"] == ["As0", "Bs0"] and stats["supportUnits"] == 2
    assert stats["variation"] == ["As2"] and stats["overflowCount"] == 2
    assert stats["invalidCount"] == 1  # a bad quote is still an error, overflow is not


def test_overflow_alone_does_not_mark_a_claim_mixed():
    p = payload()
    out = {
        "findings": [
            dict(claimId="tendency-01", items=[item("As0"), item("As1"), item("Bs0")], note="합성")
        ]
    }
    m.validate_compact("tendency-audit", out, p)
    records = [dict(id=t, unit=["t", t[0]]) for t in p["chunk"]["recordIds"]]
    stats = m.aggregate_compact([out], p["claims"], records)["tendency-01"]
    assert stats["overflowCount"] == 1 and stats["invalidCount"] == 0
    assert m.state_for(stats, stats) == "evidence_present"


def test_per_claim_cap_follows_the_response_size_line():
    claims = [claim(n) for n in range(1, 13)]
    limits = m.citation_limits(claims)
    assert limits["perCall"] == m.AUDIT_ITEM_LIMIT
    assert limits["perClaim"] * len(claims) <= m.AUDIT_ITEM_LIMIT
    assert m.citation_limits([claim()])["perClaim"] == m.AUDIT_ITEM_LIMIT
    # Ten conversations, one support each, under a cap of eight per claim.
    convs = "ABCDEFGHIJ"
    segs = [
        dict(
            unit=["t", u],
            turns=[
                dict(id=f"{u}u0", speaker="USER", text=f"{u} 질문 0"),
                dict(id=f"{u}s0", speaker="SUBJECT", text=f"{u} 대답 0"),
            ],
        )
        for u in convs
    ]
    c = dict(id="dev-0001", segments=segs, recordIds=[f"{u}s0" for u in convs])
    p = dict(chunk=c, targets=m.targets(c), claims=claims)
    out = {
        "findings": [
            dict(
                claimId=x["id"],
                items=[item(f"{u}s0") for u in convs] if x is claims[0] else [],
                note="합성",
            )
            for x in claims
        ]
    }
    m.validate_compact("tendency-audit", out, p)
    first = out["findings"][0]
    assert len(first["items"]) == limits["perClaim"] == 8 and len(first["overflowItems"]) == 2


def test_v7_is_opt_in_and_v4_stays_default():
    from types import SimpleNamespace

    def ctx(value=None):
        cfg = {} if value is None else {"motif_compiler": value}
        return SimpleNamespace(config=SimpleNamespace(stage=lambda _: cfg))

    assert pipeline.version_for(ctx()) == "evidence-pipeline-v4"
    assert pipeline.selected(ctx("evidence-v7"))
    assert pipeline.version_for(ctx("evidence-v7")) == "evidence-pipeline-v7"
    assert "v7" in pipeline.instructions("evidence-pipeline-v7").splitlines()[0]
    assert pipeline.instructions("evidence-pipeline-v4") != pipeline.instructions(
        "evidence-pipeline-v7"
    )


def compact_fake(req):
    from tests.test_evidence_pipeline import candidate

    data = json.loads(req.messages[1].content)
    phase = data.get("phase", "")
    if not phase.startswith("tendency-"):
        return candidate(req)
    assert "targets" not in data and "allowedIds" not in data
    if phase == "tendency-consolidate":
        return {"claims": data["observations"][0]["claims"]}
    sections = []
    for line in data["chunk"]["lines"].split("\n"):
        if line.startswith("## "):
            sections.append([])
        else:
            tid, role, text = line.split(" ", 2)
            sections[-1].append((tid, role, text))
    if phase == "tendency-discover":
        c = {k: v for k, v in claim().items() if k != "id"}
        c["evidence"] = [t for s in sections for t, r, _ in s if r == "S"]
        return {"claims": [c]}
    items = []
    for s in sections:
        for i, (tid, role, text) in enumerate(s):
            if role == "S" and i:
                uid, _, utext = next(x for x in reversed(s[:i]) if x[1] == "U")
                items.append(
                    dict(
                        responseTurnId=tid,
                        conditionTurnId=uid,
                        conditionQuote=utext,
                        responseQuote=text,
                        applicability="yes",
                        functionMatch="present",
                        formMatch="present",
                        reason="합성 검증",
                    )
                )
    return {"findings": [dict(claimId=c["id"], items=items, note="합성") for c in data["claims"]]}


def test_native_v7_build_runs_planned_calls_and_reverifies(tmp_path):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v7"
    model.add("AGENT", compact_fake)
    planned = pipeline.full_plan(ctx, cid)[0].calls - ATOMIC_RETRIES
    before = len(model.requests)
    folder = run_s8(ctx, cid, [])
    sent = [r for r in model.requests[before:] if "/tendency-" in (r.ref or "")]
    phases = [r.ref.split("/")[2] for r in sent]
    # Three small conversations: one development chunk, one confirmation chunk.
    assert sorted(phases) == sorted(
        ["tendency-discover", "tendency-consolidate", "tendency-audit", "tendency-confirm"]
    )
    # The plan is an upper bound: audit calls scale with ceil(claims / COMPACT_AUDIT_BATCH).
    assert 0 < len(sent) <= planned
    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v7" and review["cards"]
    binding = read_json(folder / "evidence-binding.json")
    assert binding["compiler"] == "evidence-pipeline-v7" and binding["sourceTransport"] == TRANSPORT
    split = read_json(folder / "evidence-partition.json")
    keys = {r.ref.split("/")[3] for r in sent}
    assert keys == {"all"} | {c["id"] for c in split["developmentChunks"]} | {
        c["id"] for c in split["confirmationChunks"]
    }
    for r in sent:
        body = json.loads(r.messages[1].content)
        if "chunk" in body:
            assert body["chunk"]["format"] == TRANSPORT
    assert (
        read_json(folder / "prompt-pair.json")["systemRulesRef"] == "builtin:evidence-pipeline-v7"
    )
    decision = read_json(folder / "evidence-tendency-decisions.json")[0]
    assert decision["retained"] and decision["support"]["conversations"] == 3
    (folder / "evidence-partition.json").write_text("{}")
    with pytest.raises(ValueError):
        pipeline.verify_review(ctx, cid, folder)
