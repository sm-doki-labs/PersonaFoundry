"""트윈 모델 연결·비교 세트·비학습 G8. 실제 자료나 네트워크를 사용하지 않는다."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import BIND_EXISTING, PROMPT_ONLY, SOURCE
from character_factory_poc.pipeline.orchestrator import _training_ready
from character_factory_poc.pipeline.origin import write_model_mode, write_origin
from character_factory_poc.stages.model_prep.bind import import_binding
from character_factory_poc.stages.s0_source.run import read_jsonl
from character_factory_poc.stages.s9h_holdout import run as holdout
from character_factory_poc.stages.s10_eval.twin import run_s10_twin
from character_factory_poc.stages.s11_release.package import collect_sft
from tests.test_s10_eval import _prompt_pair
from tests.test_twin_s3 import CANARY, _ready

SHA = "1a" * 20
BASE = "synthetic/base"
SECRET = "hf_synthetic_never_persist"


class Hub:
    owner = "lab"
    sha = SHA
    base = BASE
    files = {"adapter_config.json", "adapter_model.safetensors"}
    denied = False

    def whoami(self):
        return {"name": "reader", "orgs": [{"name": self.owner}], "auth": {"token": SECRET}}

    def revision_info(self, ref, revision):
        assert revision == SHA and ref == "lab/adapter"
        if self.denied:
            raise PermissionError(SECRET)
        return ref, self.sha, self.files

    def adapter_config(self, ref, revision):
        assert (ref, revision) == ("lab/adapter", SHA)
        return {"base_model_name_or_path": self.base}


def _path(tmp, **fields):
    obj = {
        "schemaVersion": "model-binding-import-v1",
        "provider": "HF_ADAPTER",
        "ref": "lab/adapter",
        "revision": SHA,
        "baseModel": BASE,
        "baseModelRevision": "v1",
        "servingRoute": "test-route",
        "provenance": {
            "trainedBy": "테스트",
            "trainedAt": "2026-11-01",
            "dataNote": "합성 대화",
            "usageBasis": "테스트용",
        },
        **fields,
    }
    path = tmp / "input.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


@pytest.fixture
def target(tmp_path):
    ctx = Context.load(tmp_path, execute=False)
    char = ctx.character_dir("t")
    write_origin(char, SOURCE)
    write_model_mode(char, BIND_EXISTING)
    return ctx, char


@pytest.mark.parametrize("revision", ["main", "v1.1", "1ab23cd", "z" * 40])
def test_rejects_unpinned_before_network(target, tmp_path, revision):
    ctx, char = target
    with pytest.raises(FactoryError, match="커밋"):
        import_binding(ctx, "t", _path(tmp_path, revision=revision), client=object())
    assert not (char / "model-prep").exists()


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("owner", "other", "소유"),
        ("denied", True, "404.*없음.*권한 없음"),
        ("sha", "a" * 40, "커밋"),
        ("files", {"adapter_config.json"}, "가중치"),
        ("files", {"adapter_model.bin"}, "adapter_config.json"),
        ("base", "another/model", "기반 모델"),
    ],
)
def test_failed_preflight_publishes_nothing(target, tmp_path, field, value, reason):
    ctx, char = target
    client = Hub()
    setattr(client, field, value)
    with pytest.raises(FactoryError, match=reason) as exc:
        import_binding(ctx, "t", _path(tmp_path), client=client)
    assert SECRET not in str(exc.value)
    assert not (char / "model-prep").exists() and not _training_ready(ctx, "t")


def test_mode_and_origin_checked_before_read(target, tmp_path):
    ctx, char = target
    write_model_mode(char, PROMPT_ONLY)
    for cid in ("t", "original"):
        with pytest.raises(FactoryError, match="트윈.*BIND_EXISTING"):
            import_binding(ctx, cid, tmp_path / "missing")


def test_no_credentials_persist(target, tmp_path, monkeypatch):
    ctx, char = target
    monkeypatch.setenv("HF_TOKEN", SECRET)
    with pytest.raises(FactoryError, match="토큰 값"):
        import_binding(ctx, "t", _path(tmp_path, servingRoute=SECRET), client=Hub())
    folder = import_binding(ctx, "t", _path(tmp_path), client=Hub())
    check = read_json(folder / "preflight.json")
    assert check["tokenEnv"] == "HF_TOKEN" and check["account"] == "reader"
    assert check["owner"] == "lab" and check["commit"] == SHA
    assert _training_ready(ctx, "t") and verify_manifest(folder) == []
    for path in char.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path


def test_default_client_uses_same_token_and_commit_for_metadata_and_config(
    target, tmp_path, monkeypatch
):
    ctx, _ = target
    requests = []
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"base_model_name_or_path": BASE}))

    class Api:
        def __init__(self, token):
            assert token == SECRET
            self.token = token

        def whoami(self):
            requests.append("identity")
            return {"name": "lab", "orgs": []}

        def model_info(self, ref, *, revision):
            assert (ref, revision) == ("lab/adapter", SHA)
            requests.append("revision")
            return SimpleNamespace(
                id=ref,
                sha=SHA,
                siblings=[SimpleNamespace(rfilename=f) for f in Hub.files],
            )

    def download(ref, filename, *, revision, token):
        assert (ref, revision, token) == ("lab/adapter", SHA, SECRET)
        requests.append(filename)
        return str(config)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(HfApi=Api, hf_hub_download=download)
    )
    monkeypatch.setenv("HF_TOKEN", SECRET)
    folder = import_binding(ctx, "t", _path(tmp_path))
    assert requests == ["identity", "revision", "adapter_config.json"]
    assert read_json(folder / "preflight.json")["status"] == "PASSED"


@pytest.mark.parametrize("limit", [0, 2, 6])
def test_context_is_bounded_and_adjacent(tmp_path, monkeypatch, limit):
    ctx, _, cid = _ready(tmp_path)
    rows = []
    for conv, speakers in [
        ("a", ["OTHER"] * 8 + ["USER", "SUBJECT", "USER"]),
        ("b", ["SUBJECT", "USER", "OTHER", "SUBJECT", "USER", "SUBJECT"]),
    ]:
        for i, speaker in enumerate(speakers):
            rows.append(
                dict(convId=conv, msgId=f"{conv}{i}", speaker=speaker, text=f"합성 {conv}{i}")
            )
    monkeypatch.setattr(holdout, "load_holdout", lambda *_: rows)
    ctx.config.stages["s9h"] = {"context_messages": limit}
    folder = holdout.run_s9h(ctx, cid)
    scenes = read_jsonl(folder / "scenes.jsonl")
    assert [s["actualReply"]["msgId"] for s in scenes] == ["a9", "b5"]
    for scene, ids in zip(
        scenes, [[f"a{i}" for i in range(8)], ["b0", "b1", "b2", "b3"]], strict=True
    ):
        assert [m["msgId"] for m in scene["context"]] == ids[max(0, len(ids) - limit) :]
    assert ctx.state(cid).stage("s9h").status == "APPROVED" and verify_manifest(folder) == []


def test_no_scene_fails_without_gate(tmp_path, monkeypatch):
    ctx, _, cid = _ready(tmp_path)
    monkeypatch.setattr(holdout, "load_holdout", lambda *_: [])
    with pytest.raises(CheckFailed, match="장면이 없다"):
        holdout.run_s9h(ctx, cid)
    assert ctx.state(cid).stage("s9h").status == "CHECK_FAILED"


@pytest.mark.parametrize("mode", [BIND_EXISTING, PROMPT_ONLY])
def test_holdout_and_g8_through_package_selection(tmp_path, monkeypatch, mode):
    ctx, model, cid = _ready(tmp_path)
    char = ctx.character_dir(cid)
    write_model_mode(char, mode)
    _prompt_pair(ctx, cid)
    before = len(model.requests)
    folder = holdout.run_s9h(ctx, cid)
    scenes = read_jsonl(folder / "scenes.jsonl")
    assert len(scenes) == 1 and scenes[0]["actualReply"]["text"] == CANARY
    assert not scenes[0]["context"]
    if mode == BIND_EXISTING:
        with pytest.raises(FactoryError, match="먼저 모델을 연결"):
            run_s10_twin(ctx, cid)
        # 선택적 SDK가 없는 설치에서는 실제 토큰/네트워크를 쓰지 않는다.
        monkeypatch.setitem(sys.modules, "huggingface_hub", None)
        mb = import_binding(ctx, cid, _path(tmp_path))
        assert read_json(mb / "preflight.json")["status"] == "SKIPPED"
        adopted = "model-prep/mb1/binding.json"
    else:
        adopted = "LONG_BASE"
    ev = run_s10_twin(ctx, cid)
    assert run_s10_twin(ctx, cid) == ev
    page = (ev / "gate-G8.html").read_text()
    assert all(word in page for word in [mode, "1장면", "비교 보고는 순서 8", adopted])
    if mode == BIND_EXISTING:
        assert "건너뜀(확인 안 됨)" in page and "test-route" in page
    assert not (ev / "report.json").exists()
    with pytest.raises(FactoryError, match="채택 조건"):
        approve_gate(ctx, cid, "G8", {"decision": "SELECT", "adopted": "unknown"})
    approve_gate(ctx, cid, "G8", {"decision": "SELECT", "adopted": adopted})
    assert ctx.state(cid).stage("s10").status == ctx.state(cid).gate("G8").status == "APPROVED"
    assert verify_manifest(ev) == [] and len(model.requests) == before
    sft, _, problems = collect_sft(ctx, cid)
    assert not problems and sft.adoptedBinding == adopted and not sft.evalReport
    for path in char.rglob("*"):
        if path.is_file() and path not in (
            char / "s0-source/sp1/holdout.jsonl",
            folder / "scenes.jsonl",
        ):
            assert CANARY.encode() not in path.read_bytes(), path


def test_rebinding_cannot_change_an_open_decision(tmp_path):
    ctx, _, cid = _ready(tmp_path)
    char = ctx.character_dir(cid)
    write_model_mode(char, BIND_EXISTING)
    _prompt_pair(ctx, cid)
    holdout.run_s9h(ctx, cid)
    one = import_binding(ctx, cid, _path(tmp_path, provider="VERTEX_TUNED"))
    first = run_s10_twin(ctx, cid)
    two = import_binding(ctx, cid, _path(tmp_path, provider="ENDPOINT"))
    with pytest.raises(FactoryError, match="입력이 바뀌었다"):
        approve_gate(
            ctx, cid, "G8", {"decision": "SELECT", "adopted": "model-prep/mb1/binding.json"}
        )
    approve_gate(ctx, cid, "G8", {"decision": "REJECT"})
    assert first != run_s10_twin(ctx, cid) and one != two
    adopted = (two / "binding.json").relative_to(char).as_posix()
    approve_gate(ctx, cid, "G8", {"decision": "SELECT", "adopted": adopted})
    sft, files, problems = collect_sft(ctx, cid)
    assert not problems and sft.adoptedBinding == adopted and len(files) == 2
