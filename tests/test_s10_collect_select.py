"""회수 뒤 체크포인트 선택과 binding 규칙 (D-0077 검토 반영).

- 선택이 체크포인트를 고른 경우(DEVELOPMENT_RECOMMENDED·INCONCLUSIVE)에만 binding을 남긴다.
- 같은 짧은 프롬프트의 기반 모델이 이기면(KEEP_INCUMBENT) 어댑터를 채택하지 않는다.
- 선택이 실패하면 binding 없이 PENDING으로 남고, 다시 돌리면 선택만 다시 한다(원격 재접속 없음).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.dataset import ClusterCount, DatasetRev, SplitFile
from character_factory_poc.contracts.training import Checkpoint, ModelBinding
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training.gemma_qlora import GemmaQLoraProvider
from character_factory_poc.stages.s10_train import collect as collect_mod
from character_factory_poc.stages.s10_train import select as select_mod
from character_factory_poc.stages.s10_train.io import read_run, run_path, write_run
from character_factory_poc.stages.s10_train.plan import plan_s10t

CID = "cf-select"
TOML = """
[stages.s10t]
providers = ["gemma_qlora"]
budget_usd = 10
selection_judge = false

[stages.s10t.gemma_qlora]
ssh_host = "sim.invalid"
"""


def _setup(root: Path) -> tuple[Context, Path]:
    ds = root / "runs" / "characters" / CID / "s9-data" / "ds1"
    ds.mkdir(parents=True)
    line = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u"},
                {"role": "assistant", "content": "a"},
            ]
        },
        ensure_ascii=False,
    )
    files = []
    for name, split in (("train.jsonl", "train"), ("validation-base.jsonl", "validation_base")):
        (ds / name).write_text(line + "\n", "utf-8")
        files.append(
            SplitFile(split=split, path=name, sha256=sha256_file(ds / name), conversations=1)
        )
    dataset = DatasetRev(
        characterId=CID,
        datasetRev="ds1",
        personaVersion="pv1",
        planSha256="1" * 64,
        sampleQaRefs=[],
        clusterCounts={"base": ClusterCount(conversations=1, replies=1)},
        files=files,
        blockingFailures=0,
        digest="2" * 64,
    )
    (ds / "dataset.json").write_text(json.dumps(dump(dataset)), "utf-8")
    (root / "factory.toml").write_text(TOML, "utf-8")
    ctx = Context.load(root, execute=True)
    ctx.state(CID).set_gate("G7", "APPROVED", "ds1", "gates/G7.json")
    rev_dir = plan_s10t(ctx, CID)
    folder = rev_dir / "gemma_qlora"
    (folder / "screen-requests.jsonl").write_text(
        '{"taskId":"s-1","kind":"single","messages":[]}\n'
    )
    path = run_path(rev_dir, "gemma_qlora")
    write_run(
        path,
        read_run(path).model_copy(update={"status": "RUNNING", "jobId": "/job", "dryRun": False}),
    )
    return ctx, rev_dir


def _collected(run, request):
    checkpoints = [
        Checkpoint(checkpointId=f"epoch-{e}", epoch=e, ref=f"checkpoints/epoch-{e}") for e in (1, 2)
    ]
    return run.model_copy(
        update={
            "status": "SUCCEEDED",
            "checkpoints": checkpoints,
            "appliedConfig": {**run.appliedConfig, "remoteDeleted": True},
            "modelBinding": ModelBinding(
                provider="gemma_qlora",
                ref=str(request.artifact_dir / "checkpoints/epoch-2"),
                checkpointId="epoch-2",
            ),
        }
    )


def _result(decision: str, checkpoint: str | None, out: Path):
    out.write_text("{}")
    ref = f"checkpoints/{checkpoint}" if checkpoint else None
    return select_mod.SelectionResult(
        decision=decision, checkpoint_id=checkpoint, checkpoint_ref=ref, record_path=out
    )


@pytest.mark.parametrize(
    ("decision", "checkpoint", "bound"),
    [
        ("DEVELOPMENT_RECOMMENDED", "epoch-1", "epoch-1"),
        ("INCONCLUSIVE", "epoch-2", "epoch-2"),
        ("KEEP_INCUMBENT", None, None),
        ("BLOCKED_QUALITY", None, None),
    ],
)
def test_binding_follows_selection_decision(tmp_path, monkeypatch, decision, checkpoint, bound):
    ctx, rev_dir = _setup(tmp_path)
    monkeypatch.setattr(
        GemmaQLoraProvider, "collect", lambda self, run, request: _collected(run, request)
    )
    monkeypatch.setattr(
        select_mod, "select_checkpoint", lambda **kw: _result(decision, checkpoint, kw["out_path"])
    )
    collect_mod.collect_s10t(ctx, CID)
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    assert run.appliedConfig["selection"]["decision"] == decision
    assert (run.modelBinding.checkpointId if run.modelBinding else None) == bound
    approved = ctx.state(CID).stage("s10t").status == "APPROVED"
    assert approved is (bound is not None)
    assert collect_mod.collection_done(run)


def test_selection_failure_keeps_pending_and_retries_selection_only(tmp_path, monkeypatch):
    ctx, rev_dir = _setup(tmp_path)
    calls = {"collect": 0}

    def fake_collect(self, run, request):
        calls["collect"] += 1
        return _collected(run, request)

    monkeypatch.setattr(GemmaQLoraProvider, "collect", fake_collect)

    def boom(**kw):
        raise RuntimeError("판정 모델 오류")

    monkeypatch.setattr(select_mod, "select_checkpoint", boom)
    with pytest.raises(RuntimeError):
        collect_mod.collect_s10t(ctx, CID)
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    assert run.modelBinding is None and run.appliedConfig["selection"]["decision"] == "PENDING"
    assert not collect_mod.collection_done(run)
    assert ctx.state(CID).stage("s10t").status != "APPROVED"

    monkeypatch.setattr(
        select_mod,
        "select_checkpoint",
        lambda **kw: _result("INCONCLUSIVE", "epoch-2", kw["out_path"]),
    )
    collect_mod.collect_s10t(ctx, CID)
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    assert calls["collect"] == 1, "선택만 다시 해야 한다(원격 회수 재시도 없음)"
    assert run.modelBinding.checkpointId == "epoch-2"
    assert ctx.state(CID).stage("s10t").status == "APPROVED"
