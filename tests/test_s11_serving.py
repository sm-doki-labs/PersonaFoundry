"""S11 패키지의 채택 어댑터 서빙 기록 sft/serving.json (D-0077).

합성 캐릭터 폴더에 성공한 gemma_qlora 학습 기록과 작은 가짜 어댑터 파일을 두고, G8 채택에 따라
serving.json이 생기거나(null) 해시 불일치로 막히는지 확인한다. 네트워크·GPU 호출 없음.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s11_release.package import build_package, verify_package_files
from tests.support.export_flow import fix_sft, full_flow, write_json

ADAPTER = {
    "adapter_model.safetensors": b"synthetic-lora-weights",
    "adapter_config.json": b'{"r": 16, "lora_alpha": 32}',
}


@pytest.fixture
def flow(tmp_path):
    return full_flow(tmp_path)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gemma_run(ctx, cid, *, selection: bool = True) -> tuple[Path, str]:
    """성공한 gemma_qlora 학습과 어댑터·회수 기록을 두고 G8이 그 binding을 채택하게 한다."""
    folder = ctx.character_dir(cid) / "s10-train" / "tr1" / "gemma_qlora"
    artifacts = folder / "artifacts"
    adapter_dir = (artifacts / "checkpoints" / "epoch-1.0").resolve()
    adapter_dir.mkdir(parents=True)
    for name, data in ADAPTER.items():
        (adapter_dir / name).write_bytes(data)
    write_json(
        artifacts / "remote" / "complete.json",
        {
            "files": [
                {
                    "path": f"checkpoints/epoch-1.0/{name}",
                    "bytes": len(data),
                    "sha256": _sha(data),
                }
                for name, data in ADAPTER.items()
            ]
        },
    )
    ref = str(adapter_dir)
    fix_sft(ctx, cid, adopted=ref)
    run_path = folder / "training-run.json"
    run = read_json(run_path)
    run.update(
        {
            "status": "SUCCEEDED",
            "dryRun": False,
            "jobId": "job-1",
            "baseModelRevision": "rev-abc",
            "requestedConfig": {
                "chatTemplate": "gemma-4-thinking",
                "expectedVersions": {"transformers": "4.99"},
            },
            "appliedConfig": {
                "chatTemplate": "gemma-4-thinking-applied",
                "runtimeVersions": {"transformers": "5.0.0", "peft": "0.18.0"},
            },
            "modelBinding": {"provider": "gemma_qlora", "ref": ref, "checkpointId": "epoch-1.0"},
        }
    )
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    write_json(
        ctx.character_dir(cid) / "s10-eval" / "ev1" / "adoption.json",
        {"armId": "SHORT_GEMMA_SFT", "adopted": ref},
    )
    if selection:
        write_json(folder / "checkpoint-selection.json", {"decision": "MODEL_ACCEPTED"})
    return folder, ref


def test_adopted_gemma_writes_serving(flow):
    ctx, cid = flow
    folder, ref = _gemma_run(ctx, cid)
    rev_dir = build_package(ctx, cid)
    package = read_json(rev_dir / "package.json")
    assert package["sft"]["serving"] == "sft/serving.json"

    serving = validate("sft-serving-v1", read_json(rev_dir / "sft" / "serving.json"))
    assert serving.provider == "gemma_qlora" and serving.armId == "SHORT_GEMMA_SFT"
    assert serving.adoptedBinding == ref and serving.adapterRef == ref
    assert serving.baseModel == "gemma-4-31b-it" and serving.baseModelRevision == "rev-abc"
    assert serving.chatTemplate == "gemma-4-thinking-applied"
    assert serving.thinkingEnabled is False and serving.checkpointId == "epoch-1.0"
    assert serving.runtimeVersions == {"transformers": "5.0.0", "peft": "0.18.0"}
    gen = serving.generation
    assert (gen.temperature, gen.top_p, gen.top_k, gen.max_new_tokens) == (0.7, 0.9, 50, 512)
    assert {(f.path, f.sha256, f.bytes) for f in serving.adapterFiles} == {
        (name, _sha(data), len(data)) for name, data in ADAPTER.items()
    }
    run_file = rev_dir / "sft" / "training-gemma_qlora.json"
    assert serving.trainingRun.ref == "sft/training-gemma_qlora.json"
    assert serving.trainingRun.sha256 == hashlib.sha256(run_file.read_bytes()).hexdigest()
    selection = folder / "checkpoint-selection.json"
    assert serving.checkpointSelection is not None
    assert serving.checkpointSelection.decision == "MODEL_ACCEPTED"
    assert serving.checkpointSelection.sha256 == _sha(selection.read_bytes())
    assert serving.checkpointSelection.path == "s10-train/tr1/gemma_qlora/checkpoint-selection.json"

    # 가중치는 복사하지 않고, serving.json은 패키지 해시 목록에 든다.
    assert not list(rev_dir.rglob("*.safetensors"))
    listed = {item["path"]: item for item in package["files"]}
    serving_bytes = (rev_dir / "sft" / "serving.json").read_bytes()
    assert listed["sft/serving.json"]["sha256"] == _sha(serving_bytes)
    assert verify_package_files(validate("character-package-v1", package), rev_dir) == []


def test_serving_without_selection_file(flow):
    ctx, cid = flow
    _gemma_run(ctx, cid, selection=False)
    rev_dir = build_package(ctx, cid)
    assert read_json(rev_dir / "sft" / "serving.json")["checkpointSelection"] is None


def test_adapter_hash_mismatch_blocks(flow):
    ctx, cid = flow
    _gemma_run(ctx, cid)
    adapter = Path(ctx.character_dir(cid) / "s10-train" / "tr1" / "gemma_qlora" / "artifacts")
    weights = adapter / "checkpoints" / "epoch-1.0" / "adapter_model.safetensors"
    weights.write_bytes(weights.read_bytes() + b"tamper")
    with pytest.raises(CheckFailed) as err:
        build_package(ctx, cid)
    assert any("adapter_model.safetensors sha256 불일치" in p for p in err.value.problems)
    assert ctx.state(cid).stage("s11").status == "CHECK_FAILED"
    assert not (ctx.character_dir(cid) / "s11-release" / "pk1" / "package.json").exists()


def test_missing_adapter_blocks(flow):
    ctx, cid = flow
    _gemma_run(ctx, cid)
    adapter = ctx.character_dir(cid) / "s10-train" / "tr1" / "gemma_qlora" / "artifacts"
    (adapter / "checkpoints" / "epoch-1.0" / "adapter_config.json").unlink()
    with pytest.raises(CheckFailed) as err:
        build_package(ctx, cid)
    assert any("어댑터 파일이 없다" in p for p in err.value.problems)


@pytest.mark.parametrize("adopted", ["LONG_BASE", "fake://fake-cf-ds1/adapter"])
def test_long_base_or_fake_adoption_has_no_serving(flow, adopted):
    ctx, cid = flow
    fix_sft(ctx, cid, adopted=adopted)
    rev_dir = build_package(ctx, cid)
    assert read_json(rev_dir / "package.json")["sft"]["serving"] is None
    assert not (rev_dir / "sft" / "serving.json").exists()


def test_serving_carries_the_training_prompt(flow):
    """서빙 기록은 학습한 데이터셋의 학습용 짧은 프롬프트와 조립 규칙을 담는다(D-0139)."""
    from types import SimpleNamespace

    from character_factory_poc.stages.s9_data import training_prompt as tp

    ctx, cid = flow
    _gemma_run(ctx, cid)
    run = read_json(ctx.character_dir(cid) / "s10-train/tr1/gemma_qlora/training-run.json")
    text = "[ACTOR_IDENTITY]\n캐릭터 이름: 윤하린\n\n[PERSONA / FACTS]\n윤하린은 꽃집 사장이다."
    built = tp.build(SimpleNamespace(long=SimpleNamespace(text=text), short=None))
    path = ctx.character_dir(cid) / "s9-data" / run["datasetRev"] / tp.FILE_NAME
    write_json(path, built.body())
    rev_dir = build_package(ctx, cid)
    package = read_json(rev_dir / "package.json")
    assert package["sft"]["trainingPrompt"] == "sft/training-prompt.json"
    serving = validate("sft-serving-v1", read_json(rev_dir / "sft" / "serving.json"))
    packaged = rev_dir / "sft" / "training-prompt.json"
    assert serving.systemPrompt is not None
    assert serving.systemPrompt.ref == "sft/training-prompt.json"
    assert serving.systemPrompt.sha256 == _sha(packaged.read_bytes())
    assert "[RELATIONSHIP]" in serving.systemAssembly and "[SCENE]" in serving.systemAssembly
    assert tp.load(packaged).core == built.core
