"""User-provided fact sheet: intake bounds, G0 display, verbatim S8 FACTS and facts-first role."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.source import SourcePack
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts import evidence_pipeline
from character_factory_poc.stages.s8_prompts.build import run_s8
from character_factory_poc.web.app import create_app
from tests import test_twin_s3
from tests.support.interview import interview_author, interview_judge
from tests.support.web_gates import trait_sheet_for
from tests.test_evidence_pipeline import candidate
from tests.test_source_intake import META, put

SHEET = [
    "2025-08-06 토트넘에서 LAFC로 이적했다.",
    "2024-25 시즌 프리미어리그 30경기 7골 10도움을 기록했다.",
    "형 손흥윤이 있다.",
]
BASE = dict(
    subject=dict(displayName="합성인물", kind="PUBLIC_FIGURE"),
    texts=[dict(textId="t1", kind="TRANSCRIPT", path="synthetic.txt")],
)


def test_contract_normalizes_lines_and_keeps_empty_packs_byte_identical():
    empty = SourcePack(**BASE)
    assert "factSheet" not in dump(empty)
    assert sha256_of(dump(empty)) == sha256_of(dump(SourcePack(**BASE, factSheet="\n  \n")))
    pack = SourcePack(**BASE, factSheet="  " + SHEET[0] + "  \n\n" + "\n".join(SHEET[1:]))
    assert pack.factSheet == SHEET
    assert dump(pack)["factSheet"] == SHEET
    assert SourcePack.model_validate(dump(pack)) == pack


@pytest.mark.parametrize(
    "line",
    [
        "연락처 010-1234-5678",
        "메일 son@example.com",
        "계좌 110-123-456789",
        "토트넘 → LAFC",
        "질문: 몇 골 넣었어요?",
        "[FACTS]",
        "제어\x07문자",
        "가" * 301,
    ],
)
def test_contract_rejects_contact_prompt_shaped_and_long_lines(line):
    with pytest.raises(ValidationError):
        SourcePack(**BASE, factSheet=[line])


def test_contract_bounds_line_count():
    SourcePack(**BASE, factSheet=[f"사실 {n}" for n in range(40)])
    with pytest.raises(ValidationError, match="40줄"):
        SourcePack(**BASE, factSheet=[f"사실 {n}" for n in range(41)])


def _draft(client, **extra):
    return client.post(
        "/api/sources/drafts",
        json=dict(displayName="선수", subjectKind="PUBLIC_FIGURE", autoReview=False, **extra),
    )


def test_web_intake_stores_fact_sheet_and_passes_it_to_the_source_pack(tmp_path):
    with TestClient(create_app(tmp_path, runner=lambda job, stream: None)) as client:
        response = _draft(client, factSheet=" " + SHEET[0] + "\n\n" + "\n".join(SHEET[1:]))
        assert response.status_code == 200, response.text
        cid = response.json()["characterId"]
        folder = tmp_path / "runs/characters" / cid
        assert read_json(folder / "s0-source/intake.json")["factSheet"] == SHEET
        url = "/api/sources/" + cid
        assert client.get(url).json()["factSheet"] == SHEET
        assert client.post(put(client, url) + "/complete", json=META).is_success
        assert client.post(url + "/finalize").is_success
        assert read_json(folder / "source-pack.json")["factSheet"] == SHEET

        plain = _draft(client).json()["characterId"]
        plain_folder = tmp_path / "runs/characters" / plain
        assert "factSheet" not in read_json(plain_folder / "s0-source/intake.json")
        url = "/api/sources/" + plain
        assert client.get(url).json()["factSheet"] == []
        assert client.post(put(client, url) + "/complete", json=META).is_success
        assert client.post(url + "/finalize").is_success
        assert "factSheet" not in read_json(plain_folder / "source-pack.json")


@pytest.mark.parametrize(
    "sheet,message",
    [
        (
            "연락처 010-1234-5678",
            "사실 1번째 줄에 연락처나 계좌처럼 보이는 번호가 있어요. 빼고 적어 주세요.",
        ),
        ("\n".join(f"사실 {n}" for n in range(41)), "사실은 40줄까지 적을 수 있어요."),
        ("괜찮은 줄\n" + "가" * 301, "사실 2번째 줄은 300자까지 적을 수 있어요."),
    ],
)
def test_web_intake_explains_rejected_fact_sheet(tmp_path, sheet, message):
    with TestClient(create_app(tmp_path, runner=lambda job, stream: None)) as client:
        response = _draft(client, factSheet=sheet)
        assert response.status_code == 422
        assert message in response.text


def _ready_with_sheet(tmp_path, monkeypatch, template):
    original = test_twin_s3._write_pack

    def write_pack(tmp, **kw):
        path = original(tmp, **kw)
        pack = read_json(path)
        pack["factSheet"] = SHEET
        path.write_text(json.dumps(pack), encoding="utf-8")
        return path

    monkeypatch.setattr(test_twin_s3, "_write_pack", write_pack)
    # Stand in for S0-collected public facts so the order can be checked.
    monkeypatch.setattr(evidence_pipeline, "approved_facts", lambda ctx, cid: None)
    monkeypatch.setattr(evidence_pipeline, "motif_facts", lambda facts: ["공개 사실 하나"])
    ctx, model, cid = test_twin_s3._ready(tmp_path, template=template)
    page = (ctx.character_dir(cid) / "s0-source/sp1/gate-G0.html").read_text("utf-8")
    assert "사용자가 준 사실" in page and all(line in page for line in SHEET)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", dict(decision="SELECT", selections=["v1"], reviewer="test"))
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    if template == "INTERVIEW":
        model.add("AGENT", interview_author)
        model.add("JUDGE", interview_judge)
    else:
        model.add("AGENT", candidate)
    return ctx, cid


@pytest.mark.parametrize("template", ["FAMILY_CALL", "INTERVIEW"])
def test_s8_injects_sheet_verbatim_with_facts_first_policy(tmp_path, monkeypatch, template):
    ctx, cid = _ready_with_sheet(tmp_path, monkeypatch, template)
    folder = run_s8(ctx, cid, [])
    packet = read_json(folder / "evidence-packet.json")
    binding = read_json(folder / "evidence-binding.json")
    lines = packet["facts"].split("\n")
    known = ["41", "female", "제본사", "가족"]
    assert lines[1:] == [*known, *SHEET, "공개 사실 하나"]
    assert binding["factPolicy"] == evidence_pipeline.FACT_POLICY
    assert packet["role"].endswith(evidence_pipeline.FACT_PRIORITY)
    text = read_json(folder / "prompt-pair.json")["long"]["text"]
    assert "[FACTS]\n" + packet["facts"] in text
    assert evidence_pipeline.FACT_PRIORITY.strip() in text
    approve_gate(ctx, cid, "G6", dict(decision="APPROVE", reviewer="test", evidenceReviewed=True))
    evidence_pipeline.verify_review(ctx, cid, folder, approved=True)

    # A different fact sheet is a different binding, so the reviewed packet no longer verifies.
    pack, index, corpus = evidence_pipeline.load_approved_source(ctx, cid)
    edited = pack.model_copy(update={"factSheet": SHEET[:2]})
    monkeypatch.setattr(
        evidence_pipeline, "load_approved_source", lambda *a: (edited, index, corpus)
    )
    with pytest.raises(ValueError, match="다시 생성"):
        evidence_pipeline.verify_review(ctx, cid, folder, approved=True)


@pytest.mark.parametrize("template", ["FAMILY_CALL", "INTERVIEW"])
def test_packets_built_without_policy_still_verify_unchanged(tmp_path, monkeypatch, template):
    ctx, cid = _ready_with_sheet(tmp_path, monkeypatch, template)
    with monkeypatch.context() as legacy:
        legacy.setattr(evidence_pipeline, "FACT_POLICY", None)
        folder = run_s8(ctx, cid, [])
    packet = read_json(folder / "evidence-packet.json")
    assert "factPolicy" not in read_json(folder / "evidence-binding.json")
    assert evidence_pipeline.FACT_PRIORITY not in packet["role"]
    approve_gate(ctx, cid, "G6", dict(decision="APPROVE", reviewer="test", evidenceReviewed=True))
    evidence_pipeline.verify_review(ctx, cid, folder, approved=True)
