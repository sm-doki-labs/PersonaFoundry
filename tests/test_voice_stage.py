"""D-0205: 만들 때 적은 Fish Audio 음성 ID가 그대로 캐릭터 패키지까지 간다."""

import json

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.pipeline.graph import CREATED, SOURCE, stages_for
from character_factory_poc.stages.export.doki_app.api_svc import build_seed
from character_factory_poc.stages.export.settings import API_SVC_HEAD
from character_factory_poc.stages.s11_release.package import (
    build_package,
    load_package,
    verify_package_files,
)
from character_factory_poc.stages.sv_voice.run import (
    SETTINGS,
    approved_voice,
    normalize_reference_id,
    read_voice,
    run_sv,
    write_voice,
)
from character_factory_poc.web.app import create_app
from tests.test_twin_export import _approved
from tests.test_web_runtime import client_for, make_root

VOICE = "802e3bc2b27e49c2995d23ef70e6ac89"


def test_reference_id_is_trimmed_lowercased_or_rejected():
    assert normalize_reference_id("  " + VOICE.upper() + " ") == VOICE
    assert normalize_reference_id("") is None
    assert normalize_reference_id(None) is None
    for bad in ("802e3bc2", VOICE + "0", "x" * 32, 123):
        with pytest.raises(ValueError):
            normalize_reference_id(bad)


def test_every_graph_has_the_voice_stage_before_release():
    modes = ("TRAIN", "BIND_EXISTING", "PROMPT_ONLY")
    for graph in [stages_for(CREATED)] + [stages_for(SOURCE, m) for m in modes]:
        assert graph["sv"].gate is None
        assert "sv" in graph["s11"].after


def test_runtime_create_keeps_the_voice_id(tmp_path):
    root = make_root(tmp_path)
    client, _ = client_for(root)
    res = client.post(
        "/api/runtime/characters",
        json={
            "slug": "voiced",
            "brief": "목소리가 낮은 정비사.",
            "voiceReferenceId": VOICE.upper(),
        },
    )
    assert res.status_code == 201, res.text
    folder = root / "runs/characters" / res.json()["characterId"]
    assert read_voice(folder) == {"provider": "fish_audio", "referenceId": VOICE}
    bad = client.post(
        "/api/runtime/characters",
        json={"slug": "bad-voice", "brief": "정비사.", "voiceReferenceId": "nope"},
    )
    assert bad.status_code == 400
    assert "32자" in bad.json()["detail"]
    assert not list((root / "runs/characters").glob("*bad-voice*"))


def test_source_draft_keeps_the_voice_id(tmp_path):
    client = TestClient(create_app(tmp_path))
    body = {"displayName": "선수", "subjectKind": "PUBLIC_FIGURE", "voiceReferenceId": VOICE}
    res = client.post("/api/sources/drafts", json=body)
    assert res.status_code == 200, res.text
    cid = res.json()["characterId"]
    assert client.get("/api/sources/" + cid).json()["voiceReferenceId"] == VOICE
    folder = tmp_path / "runs/characters" / cid
    assert json.loads((folder / SETTINGS).read_text("utf-8"))["referenceId"] == VOICE
    res = client.post("/api/sources/drafts", json=body | {"voiceReferenceId": "short"})
    assert res.status_code == 422


@pytest.mark.parametrize("voice", [VOICE, None])
def test_voice_stage_records_and_approves_without_a_gate(tmp_path, voice):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    folder = ctx.character_dir(cid)
    write_voice(folder, voice)
    run_sv(ctx, cid)
    state = ctx.state(cid)
    assert state.stage("sv").status == "APPROVED"
    record = json.loads((folder / "voice/vo1/voice.json").read_text("utf-8"))
    assert record["referenceId"] == voice
    assert (approved_voice(folder, state) is None) == (voice is None)


def test_package_ships_the_voice_id_as_given(tmp_path):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    write_voice(ctx.character_dir(cid), VOICE)
    run_sv(ctx, cid)
    build_package(ctx, cid)
    package, folder = load_package(ctx, cid)
    assert package.voice is not None
    assert package.voice.referenceId == VOICE
    assert package.voice.provider == "fish_audio"
    assert json.loads((folder / "voice/voice.json").read_text("utf-8")) == {
        "provider": "fish_audio",
        "referenceId": VOICE,
    }
    assert "voice/voice.json" in {item.path for item in package.files}
    assert verify_package_files(package, folder) == []
    seed = build_seed(
        package, folder, exported_at="2026-11-13T00:00:00Z", alembic_revision=API_SVC_HEAD
    )
    assert any(VOICE in item for item in seed.unmapped)


def test_package_without_voice_has_no_voice_field(tmp_path):
    ctx, cid, _, _ = _approved(tmp_path, "PROMPT_ONLY")
    run_sv(ctx, cid)
    build_package(ctx, cid)
    package, folder = load_package(ctx, cid)
    assert package.voice is None
    assert "voice" not in json.loads((folder / "package.json").read_text("utf-8"))
    assert not (folder / "voice").exists()
