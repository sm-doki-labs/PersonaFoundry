"""합성 출처에서 G8·G9를 거쳐 두 서비스 파일까지 검사한다. 외부 호출은 없다."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.providers.fake_vision import FakeVisionModel
from character_factory_poc.stages.export.doki_app.chat_svc import ASSESSOR_MODEL, DIALOGUE_MODEL
from character_factory_poc.stages.export.export import TargetHeads, export_doki_app
from character_factory_poc.stages.export.settings import API_SVC_HEAD, CHAT_SVC_HEAD
from character_factory_poc.stages.model_prep.bind import import_binding
from character_factory_poc.stages.s0_source.run import run_s0
from character_factory_poc.stages.s2_hero.twin import run_s2_twin
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s4_frames.run import run_s4
from character_factory_poc.stages.s5_intro.run import run_s5
from character_factory_poc.stages.s6_actions.run import run_s6
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from character_factory_poc.stages.s9h_holdout.run import run_s9h
from character_factory_poc.stages.s10_eval.twin import run_s10_twin
from character_factory_poc.stages.s11_release.package import build_package
from tests.support.export_flow import approve_package, write_json
from tests.support.flow import make_ctx
from tests.support.synthetic import assembly_answer
from tests.support.web_gates import trait_sheet_for
from tests.test_evidence_pipeline import candidate
from tests.test_model_prep import Hub, _path
from tests.test_s11_export import _settings
from tests.test_s11_serving import _gemma_run
from tests.test_scene_flow import backgrounds, poses, scenes, through_pose
from tests.test_source_s0 import _good_digest, _twin
from tests.test_twin_flow import _pack
from tests.test_twin_s3 import CANARY, LINES, _answer

VOICE = "b8196023-6358-4960-934c-46a372df8712"


def _approved(
    tmp,
    mode,
    one_scene=False,
    *,
    legacy_v3=False,
    full_evidence=False,
    atomic_evidence=False,
    tendency_evidence=False,
):
    """Keep shared callers on the default; historical V3 cases must opt in."""
    ctx, agents = make_ctx(tmp)
    ctx.config.stages.setdefault("s8", {})["motif_compiler"] = (
        "v3"
        if legacy_v3
        else (
            "evidence-v4"
            if tendency_evidence
            else "evidence-v3"
            if atomic_evidence
            else "evidence-v2"
            if full_evidence
            else "evidence-v1"
        )
    )
    ctx.use_vision(FakeVisionModel(responder=lambda req: {"faceShape": "oval"}))
    cid = _twin(ctx, "cf-20261108-test")
    write_model_mode(ctx.character_dir(cid), mode)
    pack = _pack(tmp)
    data = read_json(pack)
    data["usageBasis"]["notes"] = "공개하지 않을 동의 메모"
    if mode == "BIND_EXISTING":
        data.update(voiceId=VOICE, chapterTemplate="FAN_CALL")
    write_json(pack, data)
    for stage, fn in [
        ("s0", _good_digest),
        ("s3-twin", _answer),
        ("s4a", backgrounds),
        ("s4b-scene", scenes),
        ("s4b-pose", poses),
        ("s7", lambda req: trait_sheet_for(ctx, cid)),
        ("s8", assembly_answer if legacy_v3 else candidate),
    ]:
        agents.set(stage, fn)
    if one_scene:
        # D-0164·D-0165: 모티브 영상은 한 장면(ch1)에 등급 몸짓과 시그니처 포즈를 만든다.
        from character_factory_poc.pipeline.origin import write_signature, write_video_tier
        from tests.test_scene_flow import agent_input

        def scoped(fn):
            def respond(req):
                wanted = agent_input(req, "settings")["chapters"]
                return {"chapters": [c for c in fn(req)["chapters"] if c["chapterId"] in wanted]}

            return respond

        write_video_tier(ctx.character_dir(cid), "light")
        write_signature(
            ctx.character_dir(cid), {"title": "찰칵", "motion": "카메라 손", "useWhen": ""}
        )
        agents.set("s4a", scoped(backgrounds))
        agents.set("s4b-pose", scoped(poses))

    def approve(gate, decision="APPROVE", **fields):
        approve_gate(ctx, cid, gate, {"decision": decision, "reviewer": "u", **fields})

    run_s0(ctx, cid, pack)
    approve("G0")
    run_s2_twin(ctx, cid)
    approve("G1s")
    run_s3_twin(ctx, cid)
    approve("G3", "SELECT", selections=["v1"])
    ctx.use_vision(FakeVisionModel())
    if one_scene:
        from character_factory_poc.stages.s4a_backgrounds.run import run_s4a
        from character_factory_poc.stages.s4b_poses.run import run_s4b

        run_s4a(ctx, cid, chapters=("ch1",))
        approve("G4a")
        run_s4b(ctx, cid)
        approve("G4b")
    else:
        through_pose(ctx, cid)
    run_s4(ctx, cid)
    approve("G4")
    run_s5(ctx, cid)
    approve("G5", "SELECT", selections=["v1"])
    run_s6(ctx, cid)
    approve("G5b")
    run_s7(ctx, cid)
    run_s8(ctx, cid, [])
    approve("G6", **({} if legacy_v3 else {"evidenceReviewed": True}))
    run_s9h(ctx, cid)
    if mode == "TRAIN":
        folder, adopted = _gemma_run(ctx, cid)
        return ctx, cid, folder, adopted
    adopted = "LONG_BASE"
    if mode == "BIND_EXISTING":
        import_binding(ctx, cid, _path(tmp), client=Hub())
        ctx.config.providers["test-route"] = ProviderConfig(
            adapter="fake",
            model="synthetic-adapter",
            base_url="https://private.invalid/v1",
            api_key_env="SYNTHETIC_PROXY_KEY",
        )
        adopted = "model-prep/mb1/binding.json"
    ev = run_s10_twin(ctx, cid)
    approve("G8", "SELECT", adopted=adopted, reasons=CANARY)
    return ctx, cid, ev, adopted


def test_export_setup_keeps_default_evidence_pipeline(tmp_path):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    state = ctx.state(cid)
    folder = ctx.character_dir(cid) / "s8-prompts" / state.gate("G6").rev
    pair = read_json(folder / "prompt-pair.json")
    assert pair["systemRulesRef"] == "builtin:evidence-pipeline-v1"
    assert state.gate("G6").status == "APPROVED"
    assert read_json(folder / "persona-version.json")["long"] == pair["long"]
    assert (folder / "evidence-review.json").is_file()
    assert not (folder / "example-turns.json").exists()


@pytest.mark.parametrize("mode", ["PROMPT_ONLY", "BIND_EXISTING"])
def test_twin_export(tmp_path: Path, mode: str, monkeypatch):
    ctx, cid, ev, adopted = _approved(tmp_path, mode, legacy_v3=True)
    root = ctx.character_dir(cid)
    bind = mode == "BIND_EXISTING"
    assert (ev / "twin-comparison.json").is_file()
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path.name not in {"holdout.jsonl", "scenes.jsonl", "twin-comparison.json"}
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    pk = build_package(ctx, cid)
    published = (pk / "persona/long-prompt.txt").read_text()
    assert read_json(root / "s8-prompts/pv1/assembly.json")["frame"] in published
    assert "[자료에서 고른 발화 참고]" not in published
    approve_package(ctx, cid)
    settings = replace(_settings(tmp_path), default_voice_id="5d8d907a-826d-419c-8567-685618d0b650")
    result, ex = export_doki_app(
        ctx, cid, heads=TargetHeads(API_SVC_HEAD, CHAT_SVC_HEAD), settings=settings
    )
    pkg = read_json(pk / "package.json")
    meta = pkg["twin"]
    pack_path = root / "s0-source/sp1/source-pack.json"
    assert meta["sourcePackSha256"] == sha256_file(pack_path)
    assert (meta["origin"], meta["originLabel"], meta["subjectKind"]) == (
        "SOURCE",
        "모티브",
        "PRIVATE_PERSON",
    )
    assert meta["usageScope"] == read_json(pack_path)["usageBasis"]["scope"]
    assert meta["consentRecorded"] and meta["modelMode"] == mode
    assert meta["disclosure"] == "AI 생성 · 본인과 무관한 기술 시연"
    assert meta["comparisonReport"] == "s10-eval/ev1/twin-comparison.json"
    assert pkg["sft"]["adoptedBinding"] == adopted
    seed = read_json(ex / "doki-app/api-svc/seed.json")

    def rows(name):
        table = seed["tables"][name]
        return [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]

    titles = ["첫 통화", "친해지기", "단골 팬"] if bind else ["안부", "일상", "속마음"]
    assert [r["display_name"] for r in rows("character_stage")] == titles
    button = "통화 시작하기" if bind else "안부 전화하기"
    assert button == meta["startButtonLabel"] and not any(button in u for u in result.unmapped)
    character = rows("character")[0]
    assert character["call_start_label"] == button
    assert character["disclosure_label"] == "AI 생성 · 본인과 무관한 기술 시연"
    voice = rows("character")[0]["voice_id"]
    assert voice is not None and rows("character_voice")[0]["id"] == voice
    lang = rows("character_voice_language")[0]
    assert (lang["character_voice_id"], lang["language"], lang["voice_id"]) == (
        voice,
        "ko",
        VOICE if bind else settings.default_voice_id,
    )
    chat = ex / "doki-app/chat-svc"
    bundles = [read_json(p) for p in (chat / "split_prompt_bundles").glob("*.json")]
    assert len(bundles) == 3
    revisions = {b["dialogue"]["modelConfigRevision"] for b in bundles}
    assert {b["assessment"]["modelConfigRevision"] for b in bundles} == {ASSESSOR_MODEL}
    if bind:
        (revision,) = revisions
        config = read_json(chat / f"models/{revision}.json")
        assert config["configVersion"] == revision and config["model"] == "synthetic-adapter"
        assert config["baseUrl"] is None and config["apiKeyEnv"] == "SYNTHETIC_PROXY_KEY"
    else:
        assert revisions == {DIALOGUE_MODEL} and not (chat / "models").exists()
    private = [t for pair in LINES for t in pair] + [
        CANARY,
        "공개하지 않을 동의 메모",
        "private.invalid",
    ]
    for folder in (pk, ex):
        for path in folder.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                assert all(t.encode() not in content for t in private), path


def test_train_exports_only_g8_checkpoint(tmp_path):
    ctx, cid, folder, ref = _approved(tmp_path, "TRAIN", legacy_v3=True)
    raw = read_json(folder / "training-run.json")
    root = ctx.character_dir(cid)
    # 같은 공급자에서 더 최근에 만든 모델은 G8이 선택하지 않았다.
    other = dict(raw, modelBinding={**raw["modelBinding"], "ref": "other-checkpoint"})
    write_json(root / "s10-train/tr2/gemma_qlora/training-run.json", other)
    raw["appliedConfig"].update(servingRoute="trained-adapter", host="private.invalid")
    write_json(folder / "training-run.json", raw)
    pk = build_package(ctx, cid)
    pkg = read_json(pk / "package.json")
    assert pkg["sft"]["adoptedBinding"] == ref
    assert pkg["twin"]["trainingRecord"]["sha256"] == sha256_file(folder / "training-run.json")
    assert pkg["twin"]["comparisonReport"] is None
    serving = read_json(pk / pkg["sft"]["serving"])
    assert sha256_file(pk / serving["trainingRun"]["ref"]) == serving["trainingRun"]["sha256"]
    approve_package(ctx, cid)
    result, ex = export_doki_app(
        ctx, cid, heads=TargetHeads(API_SVC_HEAD, CHAT_SVC_HEAD), settings=_settings(tmp_path)
    )
    assert any("default_voice_id" in u for u in result.unmapped)
    (model_file,) = (ex / "doki-app/chat-svc/models").glob("*.json")
    assert read_json(model_file)["model"] == "trained-adapter"
    assert b"private.invalid" not in (pk / serving["trainingRun"]["ref"]).read_bytes()


def test_binding_changed_after_g8_blocks_package(tmp_path):
    ctx, cid, _, ref = _approved(tmp_path, "BIND_EXISTING", legacy_v3=True)
    root = ctx.character_dir(cid)
    path = root / ref
    binding = dict(read_json(path), servingRoute="other-adapter")
    run_path = root / "s10-train/tr1/IMPORTED-mb1/training-run.json"
    run = read_json(run_path)
    run["appliedConfig"]["binding"] = binding
    write_json(path, binding)
    write_json(run_path, run)
    with pytest.raises(CheckFailed, match="G8"):
        build_package(ctx, cid)
    assert not (root / "s11-release").exists()


@pytest.mark.skipif(
    not os.environ.get("CFP_PG_ADMIN_URL"),
    reason="CFP_PG_ADMIN_URL이 없어 실제 적재를 건너뛴다",
)
@pytest.mark.parametrize("mode", ["PROMPT_ONLY", "BIND_EXISTING", "TRAIN"])
def test_twin_real_load_into_disposable_postgres(tmp_path: Path, mode: str):
    """순서 10 완료 기준: 모티브 캐릭터가 일회용 PostgreSQL 두 개에 실제로 적재된다."""
    from character_factory_poc.stages.export.settings import load_export_settings

    ctx, cid, _, _ = _approved(tmp_path, mode)
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = replace(
        load_export_settings(ctx), default_voice_id="5d8d907a-826d-419c-8567-685618d0b650"
    )
    result, rev_dir = export_doki_app(ctx, cid, verify=True, settings=settings)
    assert result.verification.status == "PASSED", [
        (step.name, step.detail) for step in result.verification.steps
    ]
    steps = [step.name for step in result.verification.steps]
    assert any(name.startswith("api-svc") for name in steps)
    assert sum(1 for name in steps if name.startswith("drop")) == 2
    assert (rev_dir / "export-result.json").is_file()


def test_one_scene_motif_package(tmp_path: Path):
    """QA v5 F05: 한 장면 모티브도 패키지를 만든다(장면 세 개를 가정하지 않는다)."""
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY", one_scene=True)
    pk = build_package(ctx, cid)
    pkg = read_json(pk / "package.json")
    assert [c["chapterId"] for c in pkg["chapters"]] == ["ch1"]
    assert (pk / "chapters/ch1/facts.json").is_file() and not (pk / "chapters/ch2").exists()
    keys = {v.get("clipKey") for v in pkg["videos"]}
    assert "signature_good" in keys
