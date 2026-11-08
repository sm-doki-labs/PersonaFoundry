"""모티브 데이터: 합성 카톡 원문 → 실제 관문 → 가짜 공급자의 학습 계획."""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json, verify_manifest, write_once_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.stages.s0_source.run import load_holdout, read_jsonl, run_s0
from character_factory_poc.stages.s9_data.twin import run_s9_twin, run_s9s_twin
from character_factory_poc.stages.s10_train.plan import plan_s10t
from tests.test_source_s0 import _good_digest, _twin, _write_pack
from tests.test_twin_s3 import _ctx

SYSTEM = "승인한 짧은 합성 프롬프트"
HELD = "비교에서만 써야 할 유리 연필"


def _ready(tmp, *, system=SYSTEM):
    ctx, model = _ctx(tmp)
    cid = _twin(ctx)
    path = _write_pack(tmp)
    days = [
        [
            ("엄마", "대화 시작 전 독백"),
            ("나", "표지 골랐어?"),
            ("나", "색은?"),
            ("엄마", "초록색."),
            ("엄마", "두꺼운 종이야."),
            ("이모", "제삼자 전용 문구"),
            ("엄마", "제삼자한테 하는 답"),
            ("나", "끈은?"),
            ("엄마", "흰 끈."),
            ("나", "답 없는 끝"),
        ],
        [("나", "통째로 빼야 할 질문"), ("엄마", "같이 빠져야 할 답"), ("이모", "표시 대상")],
        [("나", "질문만 있고 답이 없다")],
        [("나", "비교 중복을 가진 대화"), ("엄마", f"겹침: {HELD}")],
        *[[("나", f"합성 질문 {i}번"), ("엄마", f"합성 대답 {i}번")] for i in range(4)],
        [("나", "마지막 날 비교 질문"), ("엄마", HELD)],
    ]
    lines = []
    for day, items in enumerate(days, 1):
        lines.append(f"--------------- 2026년 10월 {day}일 토요일 ---------------")
        lines.extend(f"[{speaker}] [오전 9:{i:02}] {msg}" for i, (speaker, msg) in enumerate(items))
    path.with_name("mom.txt").write_text("\n".join(lines), "utf-8")
    pack = read_json(path)
    pack["holdout"] = {"fraction": 0.1}
    path.write_text(json.dumps(pack, ensure_ascii=False), "utf-8")

    def digest(req):
        out = _good_digest(req)
        out["piiFlags"] = [{"msgId": "k1-00013", "reason": "합성 자료의 표시 대상"}]
        return out

    model.add("AGENT", digest)
    run_s0(ctx, cid, path)
    approve_gate(ctx, cid, "G0", {"decision": "APPROVE", "reviewer": "u"})
    prompt = dict(text=system, sha256=sha256_text(system), chars=len(system))
    write_once_json(
        ctx.character_dir(cid) / "s8-prompts/pv1/prompt-pair.json",
        {
            "schemaVersion": "prompt-pair-v1",
            "characterId": cid,
            "personaVersion": "pv1",
            "traitSheetSha256": "0" * 64,
            "sections": [],
            "systemRulesRef": "",
            "systemRulesSha256": "1" * 64,
            "short": prompt,
            "long": prompt | {"text": "사용하지 않는 긴 프롬프트"},
        },
    )
    ctx.state(cid).set_gate("G6", "APPROVED", "pv1", None)
    return ctx, cid, model


@pytest.mark.parametrize("mode", ["original", "BIND_EXISTING", "PROMPT_ONLY"])
def test_only_train_twins(tmp_path, mode):
    ctx, model = _ctx(tmp_path)
    cid = "original" if mode == "original" else _twin(ctx)
    if mode != "original":
        write_model_mode(ctx.character_dir(cid), mode)
    for run in (run_s9s_twin, run_s9_twin):
        with pytest.raises(FactoryError, match="TRAIN 방식의 모티브"):
            run(ctx, cid)
    assert not model.requests
    assert not (ctx.character_dir(cid) / "s9-data").exists()


def test_source_to_review_to_training_plan(tmp_path):
    ctx, cid, model = _ready(tmp_path)
    calls = len(model.requests)
    folder = run_s9s_twin(ctx, cid)
    assert ctx.state(cid).gate("G7a").status == "AWAITING_HUMAN"
    with pytest.raises(FactoryError, match="G7a"):
        run_s9_twin(ctx, cid)
    assert "원문 대화" in (folder / "gate-G7a.html").read_text()
    assert "OTHER" in (folder / "gate-G7a-base.html").read_text()
    approve_gate(
        ctx,
        cid,
        "G7a",
        {
            "decision": "SELECT",
            "cluster": "base",
            "reviewer": "u",
            "verdicts": {"k1-c0005-1": "FIX"},
        },
    )
    assert run_s9_twin(ctx, cid) == folder
    dataset = read_json(folder / "dataset.json")
    splits = {}
    for f in dataset["files"]:
        split_rows = read_jsonl(folder / f["path"])
        assert f["sha256"] == sha256_file(folder / f["path"])
        assert f["conversations"] == len(split_rows)
        splits[f["split"]] = [row["messages"] for row in split_rows]
    assert all(splits[name] for name in ["train", "validation_base", "eval"])
    originals = {}
    for row in read_jsonl(folder / "index.jsonl"):
        conv = read_json(folder / row["path"])
        assert conv["provenance"]["sourceRef"].endswith("#" + conv["skeletonId"])
        assert conv["material"] == "SOURCE" and conv["provenance"]["editedBy"] == "none"
        assert [{"role": "system", "content": SYSTEM}, *conv["messages"]] in splits[row["split"]]
        assert conv["system"] == SYSTEM
        originals.setdefault(conv["skeletonId"], []).append((row["split"], conv["messages"]))
    assert set(originals) == {"k1-c0001", "k1-c0006", "k1-c0007", "k1-c0008"}
    chunks = originals["k1-c0001"]
    assert len({s for s, _ in chunks}) == 1
    assert [turns for _, turns in chunks] == [
        [
            {"role": "user", "content": "표지 골랐어?\n색은?"},
            {"role": "assistant", "content": "초록색.\n두꺼운 종이야."},
        ],
        [{"role": "user", "content": "끈은?"}, {"role": "assistant", "content": "흰 끈."}],
    ]
    artifacts = "\n".join(p.read_text() for p in folder.rglob("*") if p.is_file())
    for forbidden in [r["text"] for r in load_holdout(ctx, cid)] + [
        "통째로 빼야 할 질문",
        "같이 빠져야 할 답",
        "표시 대상",
        "질문만 있고 답이 없다",
        "제삼자 전용 문구",
        "제삼자한테 하는 답",
    ]:
        assert forbidden not in artifacts
    report = read_json(folder / "check-report.json")
    assert (
        report["metrics"]["piiConversations"] == report["metrics"]["holdoutTextConversations"] == 1
    )
    assert report["metrics"]["noExchangeConversations"] == 1
    assert dataset["warnings"] == len(report["warnings"]) > 0
    assert (
        "PROMPT_ONLY" in report["warnings"][0]
        and "PROMPT_ONLY" in (folder / "gate-G7.html").read_text()
    )
    approve_gate(ctx, cid, "G7", {"decision": "APPROVE", "reviewer": "u"})
    planned = plan_s10t(ctx, cid, ["fake"])
    run = read_json(planned / "fake/training-run.json")
    assert (
        run["dryRun"] and run["status"] == "PLANNED" and run["datasetDigest"] == dataset["digest"]
    )
    assert {item["path"]: item["sha256"] for item in run["transfers"]} == {
        f["path"]: f["sha256"] for f in dataset["files"] if f["split"] != "eval"
    }
    assert not verify_manifest(folder)
    assert len(model.requests) == calls


def test_system_leak_stops_before_samples(tmp_path):
    ctx, cid, _ = _ready(tmp_path, system=f"예시: {HELD}")
    with pytest.raises(FactoryError, match="짧은 system에 비교 세트"):
        run_s9s_twin(ctx, cid)
    assert ctx.state(cid).stage("s9s").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G7a").status == "PENDING"
    assert not list((ctx.character_dir(cid) / "s9-data").rglob("conversations"))


def test_changed_g6_cannot_reuse_sample_review(tmp_path):
    ctx, cid, _ = _ready(tmp_path)
    folder = run_s9s_twin(ctx, cid)
    approve_gate(ctx, cid, "G7a", {"cluster": "base", "decision": "SELECT"})
    root = ctx.character_dir(cid) / "s8-prompts"
    changed = read_json(root / "pv1/prompt-pair.json")
    changed["short"] = changed["long"]
    write_once_json(root / "pv2/prompt-pair.json", changed)
    ctx.state(cid).set_gate("G6", "APPROVED", "pv2", None)
    with pytest.raises(FactoryError, match="G7a 이후"):
        run_s9_twin(ctx, cid)
    assert ctx.state(cid).stage("s9").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G7").status == "PENDING"
    assert not (folder / "train.jsonl").exists()


@pytest.mark.parametrize("remaining", [0, 1])
def test_tiny_reviewed_set_reserves_train_or_stops(tmp_path, remaining):
    ctx, cid, _ = _ready(tmp_path)
    folder = run_s9s_twin(ctx, cid)
    refs = read_json(folder / "samples/base.json")["conversations"]
    verdicts = {read_json(folder / ref["ref"])["conversationId"]: "REJECT" for ref in refs}
    if remaining:
        verdicts.pop("k1-c0005-1")
    approve_gate(ctx, cid, "G7a", {"cluster": "base", "decision": "SELECT", "verdicts": verdicts})
    if not remaining:
        with pytest.raises(FactoryError, match="학습할 원문 대화가 남지"):
            run_s9_twin(ctx, cid)
        assert not (folder / "dataset.json").exists()
        assert ctx.state(cid).gate("G7").status == "PENDING"
    else:
        run_s9_twin(ctx, cid)
        assert len(read_jsonl(folder / "train.jsonl")) == 1


def test_rejected_source_is_omitted_on_later_revisions(tmp_path):
    ctx, cid, _ = _ready(tmp_path)
    first = run_s9s_twin(ctx, cid)
    approve_gate(
        ctx,
        cid,
        "G7a",
        {
            "cluster": "base",
            "decision": "REQUEST_CHANGES",
            "notes": {"k1-c0005-1": "사용하지 않는다"},
        },
    )
    second = run_s9s_twin(ctx, cid)
    assert second != first
    approve_gate(ctx, cid, "G7a", {"cluster": "base", "decision": "SELECT"})
    run_s9_twin(ctx, cid)
    previous = second
    excluded = {"k1-c0005-1"}
    for key in ["k1-c0006-1", "k1-c0007-1"]:
        approve_gate(ctx, cid, "G7", {"decision": "REQUEST_CHANGES", "verdicts": {key: "REJECT"}})
        before = (previous / "manifest.sha256").read_bytes()
        folder = run_s9_twin(ctx, cid)
        excluded.add(key)
        assert previous != folder and not verify_manifest(previous)
        assert (previous / "manifest.sha256").read_bytes() == before
        assert excluded.isdisjoint(r["conversationId"] for r in read_jsonl(folder / "index.jsonl"))
        previous = folder
