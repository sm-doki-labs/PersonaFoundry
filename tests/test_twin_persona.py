"""모티브 G3 → 공통 S7/S8: 합성 원문과 가짜 모델만 쓴다."""

from pathlib import Path

import pytest

from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.synthetic import assembly_answer
from tests.support.web_gates import trait_sheet_for
from tests.test_motif_choices import demo_ledger
from tests.test_text_model_deck import configured
from tests.test_twin_s3 import CANARY, LINES, _answer, _input, _ready


@pytest.mark.parametrize(
    "template,deck,title", [("FAMILY_CALL", False, "안부"), ("FAN_CALL", True, "첫 통화")]
)
def test_approved_subject_voice_reaches_both_prompts(tmp_path, monkeypatch, template, deck, title):
    ctx, model, cid = _ready(tmp_path, template=template)
    root = ctx.character_dir(cid)
    held = root / "s0-source/sp1/holdout.jsonl"
    assert CANARY in held.read_text("utf-8")
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != held, "S3/S7/S8에서 비교 세트를 열었다"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    # 한 문장의 앞 절만 G3에서 인용한다. 전체 발화는 G0 대표 메시지로만 들어온다.
    excerpt = LINES[1][1].split(". ")[0] + "."

    def plan_answer(req):
        plan = _answer(req)
        for refs in plan["evidence"].values():
            for ref in refs:
                if ref["quote"] == LINES[1][1]:
                    ref["quote"] = excerpt
        plan["voiceSummary"] = "한 문장으로 먼저 제안한다."
        return plan

    model.add("AGENT", plan_answer)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "u"})
    if deck:
        ctx = Context(configured(tmp_path), execute=True)
        ctx.use_models(model)
        monkeypatch.setattr(
            ctx, "role_model", lambda cid, budget, role: ctx.text_model(cid, budget)
        )
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
    sheet = run_s7(ctx, cid)
    assert (sheet.parent / "trait-ledger.json").is_file() == deck
    model.add("AGENT", assembly_answer)
    ctx.config.stages.setdefault("s8", {})["motif_compiler"] = "v3"
    ctx.config.stages.setdefault("s8", {})["example_turns"] = 2 if deck else 0
    folder = run_s8(ctx, cid, [])
    source = read_json(folder / "source-plan.json")
    assert source["plan"]["chapterArc"][0]["title"] == title
    assert source["plan"]["job"] == "제본사"
    assert source["sourceVoice"]["speechEndings"]["politeEnding"] == 3
    pair = read_json(folder / "prompt-pair.json")
    inputs = read_json(folder / "assembler-input.json")
    assembly = read_json(folder / "assembly.json")
    assert pair["systemRulesRef"] == "builtin:motif-assembler-v3"
    assert "한 문장으로 먼저 제안한다." in inputs["analysis"]["voice"]
    assert "실제 본인은 아니다" in pair["long"]["text"]
    assert pair["short"] == pair["long"]
    assert pair["long"]["text"].endswith(inputs["examples"][assembly["ids"][0]])
    assert pair["long"]["text"].startswith(assembly["frame"])
    example_file = folder / "example-turns.json"
    assert example_file.is_file() == deck
    if deck:
        examples = read_json(example_file)
        corpus = (root / "s0-source/sp1/corpus.jsonl").read_text("utf-8")
        assert (
            examples["system"].startswith(assembly["frame"]) and examples["sameMedium"]
        )  # 합성 원문은 카톡이라 장면과 매체가 같다
        assert examples["turns"] and all(t["msgId"] in corpus for t in examples["turns"])
    if deck:
        assert "INFERRED" in (folder / "gate-G6.html").read_text("utf-8")
        assert "INFERRED" not in str(inputs["analysis"]["observedTraits"])
    assert excerpt in [e["quote"] for e in source["sourceVoice"]["examples"]]
    assert source["sourceVoice"]["speechProfile"]["schemaVersion"] == "speech-profile-v1"
    for directory in (sheet.parent, folder):
        assert verify_manifest(directory) == []
        assert all(
            CANARY.encode() not in p.read_bytes() for p in directory.rglob("*") if p.is_file()
        )
    assert CANARY not in str(
        [m.content for req in model.requests if req.stage in {"s7", "s8"} for m in req.messages]
    )
    approve_gate(ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "u"})
    assert ctx.state(cid).stage("s7").status == ctx.state(cid).stage("s8").status == "APPROVED"


@pytest.mark.parametrize("bad", ["user", "quote"])
def test_g3_voice_still_has_to_match_approved_subject(tmp_path, bad):
    from character_factory_poc.stages.s0_source.run import load_approved_source
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts.twin import approved_voice

    ctx, _, cid = _ready(tmp_path)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "u"})
    plan, _ = load_approved_plan(ctx, cid)
    # G3 편집본이라도 근거 ID만 남기고 대사를 지어내거나 USER 발화를 쓸 수 없다.
    ref = plan.evidence["voiceExamples"][0]
    if bad == "user":
        _, _, rows = load_approved_source(ctx, cid)
        row = next(r for r in rows if r["speaker"] == "USER")
        ref.ref, ref.quote = row["msgId"], row["text"]
    else:
        ref.quote = "원문에 없는 합성 대사"
    plan.voiceExamples[0] = ref.quote
    with pytest.raises(ValueError, match="본인 발화"):
        approved_voice(ctx, cid, plan)


@pytest.mark.parametrize("ids", [[], ["missing"], ["a", "a"], ["a", "b", "c", "d"]])
def test_assembler_rejects_unavailable_or_duplicate_quotes(ids):
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.s8_prompts.motif_v3 import assemble

    model = FakeTextModel(responses={"AGENT": {"frame": "대답한다.", "ids": ids}})
    with pytest.raises(ValueError, match="원문 예시 키"):
        assemble(model, {"facts": "", "examples": {"a": "응."}}, "test")
