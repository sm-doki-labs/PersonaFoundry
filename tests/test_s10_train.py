"""S10t 학습 공급자·단계 테스트. 합성 dataset-rev-v2와 가짜 원격 호스트만 쓴다."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import httpx
import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.dataset import ClusterCount, DatasetRev, SplitFile
from character_factory_poc.contracts.training import TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training import make_training_provider
from character_factory_poc.providers.training.errors import (
    TrainingIntegrityError,
    TrainingLimitError,
)
from character_factory_poc.providers.training.gemma_qlora import GemmaQLoraProvider
from character_factory_poc.providers.training.port import TrainRequest
from character_factory_poc.providers.training.vertex_gemini import VertexGeminiProvider
from character_factory_poc.stages.s10_train.collect import collect_s10t
from character_factory_poc.stages.s10_train.io import latest_rev, read_run, run_path
from character_factory_poc.stages.s10_train.plan import plan_s10t
from character_factory_poc.stages.s10_train.submit import submit_s10t

CID = "cf-1"


def _line(system: str, user: str, reply: str) -> str:
    return json.dumps(
        {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": reply},
            ]
        },
        ensure_ascii=False,
    )


def make_dataset(root: Path, *, train: int = 10) -> tuple[DatasetRev, Path]:
    char_dir = root / "runs" / "characters" / CID
    ds_dir = char_dir / "s9-data" / "ds1"
    ds_dir.mkdir(parents=True)
    splits = {
        "train.jsonl": ("train", train),
        "validation-base.jsonl": ("validation_base", 2),
        "validation-augmented.jsonl": ("validation_augmented", 1),
    }
    files: list[SplitFile] = []
    for name, (split, count) in splits.items():
        lines = [_line("짧은 system", f"사용자 {i}", f"답변 {i}입니다") for i in range(count)]
        path = ds_dir / name
        path.write_text("\n".join(lines) + "\n", "utf-8")
        files.append(
            SplitFile(split=split, path=name, sha256=sha256_file(path), conversations=count)
        )
    dataset = DatasetRev(
        characterId=CID,
        datasetRev="ds1",
        personaVersion="pv1",
        planSha256="1" * 64,
        sampleQaRefs=["gates/G7a.json"],
        clusterCounts={"base": ClusterCount(conversations=train, replies=train)},
        files=files,
        blockingFailures=0,
        digest="2" * 64,
    )
    (ds_dir / "dataset.json").write_text(
        json.dumps(dump(dataset), ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return dataset, ds_dir


def make_ctx(root: Path, toml: str, *, execute: bool = False) -> Context:
    (root / "factory.toml").write_text(toml, "utf-8")
    ctx = Context.load(root, execute=execute)
    ctx.state(CID).set_gate("G7", "APPROVED", "ds1", "gates/G7.json")
    return ctx


def request_for(
    root: Path, dataset: DatasetRev, ds_dir: Path, *, budget: float = 10.0, run_ref: str = "tr1"
) -> TrainRequest:
    return TrainRequest(
        dataset=dataset,
        dataset_dir=ds_dir,
        budget_usd=budget,
        plan_dir=root / "plan",
        artifact_dir=root / "artifacts",
        run_ref=run_ref,
    )


class FakeRemoteHost:
    """ssh/scp 대신 dict에 파일을 둔다. 조각 건너뛰기와 삭제를 관찰한다."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.puts: list[str] = []
        self.commands: list[list[str]] = []
        self.deleted: list[str] = []
        self.fetched: list[tuple[str, str]] = []

    def sha256(self, path: str) -> str | None:
        data = self.files.get(path)
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def put_chunk(self, path: str, data: bytes) -> None:
        self.files[path] = data
        self.puts.append(path)

    def concat(self, parts: list[str], dest: str) -> None:
        data = b"".join(self.files[p] for p in parts)
        self.files[dest] = data
        for part in parts:
            self.files.pop(part, None)

    def write_text(self, path: str, text: str) -> None:
        self.files[path] = text.encode("utf-8")

    def read_text(self, path: str) -> str | None:
        data = self.files.get(path)
        return data.decode("utf-8") if data is not None else None

    def run(self, argv: list[str]) -> str:
        self.commands.append(argv)
        return "4242"

    def fetch(self, remote: str, local: Path) -> None:
        data = self.files[remote]
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(data)
        self.fetched.append((remote, str(local)))

    def delete(self, path: str) -> None:
        self.deleted.append(path)
        for key in [k for k in self.files if k == path or k.startswith(path + "/")]:
            self.files.pop(key, None)


class LyingHost(FakeRemoteHost):
    def __init__(self, bad_path: str) -> None:
        super().__init__()
        self.bad_path = bad_path

    def sha256(self, path: str) -> str | None:
        if path == self.bad_path:
            return "0" * 64
        return super().sha256(path)


def gemma(
    host: FakeRemoteHost, *, chunk_bytes: int = 8, prep: float = 0.0, **extra: object
) -> GemmaQLoraProvider:
    cfg = ProviderConfig(
        adapter="gemma_qlora",
        model="unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        extra={
            "remote_host": host,
            "chunk_bytes": chunk_bytes,
            "prep_overhead_seconds": prep,
            "max_cost_usd": 20.0,
            "max_gpu_hours": 8.0,
            **extra,
        },
    )
    return GemmaQLoraProvider(cfg)


def test_gemma_plan_has_dataset_hashes_steps_and_cost(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    run = provider.plan(request_for(tmp_path, dataset, ds_dir))

    assert run.schemaVersion == "training-run-v2"
    assert run.dryRun is True
    assert run.status == "PLANNED"
    assert run.jobId is None
    assert run.baseModelRevision == "8e256fc6"
    assert len(run.transfers) == 3
    assert {t.path for t in run.transfers} == {
        "train.jsonl",
        "validation-base.jsonl",
        "validation-augmented.jsonl",
    }
    assert all(t.sha256 == sha256_file(ds_dir / t.path) for t in run.transfers)
    # 10대화 × 3 epoch / (배치 1 × 누적 4) = 8스텝, 8 × 6초 = 48초, L40S $0.80/h.
    assert run.estimate.gpuHours == pytest.approx(48 / 3600, abs=1e-4)
    assert run.estimate.usd == pytest.approx(round(48 / 3600 * 0.8, 4))
    assert "L40S" in run.estimate.basis
    assert run.requestedConfig["loraR"] == 16
    assert run.requestedConfig["loraAlpha"] == 32
    assert run.requestedConfig["maxSeqLength"] == 4096
    assert run.requestedConfig["lossOn"] == "assistant"
    assert host.commands == []


def test_vertex_plan_converts_format_and_estimates_tokens(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    cfg = ProviderConfig(
        adapter="vertex_gemini",
        model="gemini-3.1-flash-lite",
        extra={
            "epochs": 3,
            "chars_per_token": 1.0,
            "price_per_million_tokens_usd": 3.0,
        },
    )
    provider = VertexGeminiProvider(cfg)
    plan_dir = tmp_path / "plan"
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.plan(request)

    assert run.provider == "vertex_gemini"
    assert run.dryRun is True
    assert run.baseModel == "gemini-3.1-flash-lite"
    assert run.estimate.billableTokens is not None
    chars = 0
    for item in dataset.files:
        for line in (ds_dir / item.path).read_text("utf-8").splitlines():
            row = json.loads(line)
            chars += sum(len(m["content"]) for m in row["messages"])
    expected = math.ceil(chars / 1.0) * 3
    assert run.estimate.billableTokens == expected
    assert run.estimate.usd == pytest.approx(round(expected / 1_000_000 * 3.0, 4))
    assert "글자 기반 근사" in run.estimate.basis
    assert "2026-10-27" in run.estimate.basis
    assert "지원 목록" in run.estimate.basis
    assert {t.path for t in run.transfers} == {
        "vertex/train.jsonl",
        "vertex/validation-base.jsonl",
        "vertex/validation-augmented.jsonl",
    }
    first = json.loads((plan_dir / "vertex" / "train.jsonl").read_text("utf-8").splitlines()[0])
    assert first["systemInstruction"]["parts"][0]["text"] == "짧은 system"
    assert [c["role"] for c in first["contents"]] == ["user", "model"]


def test_stage_plan_writes_training_run_and_submit_rejects_over_budget(
    tmp_path: Path,
) -> None:
    make_dataset(tmp_path)
    toml = """
[providers.training_gemma]
adapter = "gemma_qlora"
model = "unsloth/gemma-4-31B-it-unsloth-bnb-4bit"
prep_overhead_seconds = 0

[stages.s10t]
providers = ["gemma_qlora"]
budget_usd = 0.001
"""
    ctx = make_ctx(tmp_path, toml, execute=True)
    rev = plan_s10t(ctx, CID, ["gemma_qlora"])
    run = read_run(run_path(rev, "gemma_qlora"))
    assert run.dryRun is True
    assert run.estimate.usd is not None and run.estimate.usd > 0.001
    assert ctx.state(CID).stage("s10t").status == "AWAITING_HUMAN"

    with pytest.raises(TrainingLimitError):
        submit_s10t(ctx, CID, ["gemma_qlora"])
    after = read_run(run_path(rev, "gemma_qlora"))
    assert after.jobId is None
    assert after.status == "PLANNED"


def test_stage_plan_writes_both_provider_runs(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    toml = """
[providers.training_gemma]
adapter = "gemma_qlora"
prep_overhead_seconds = 0

[stages.s10t]
providers = ["gemma_qlora", "vertex_gemini"]
budget_usd = 20.0
"""
    ctx = make_ctx(tmp_path, toml)
    rev = plan_s10t(ctx, CID)
    gemma_run = read_run(run_path(rev, "gemma_qlora"))
    vertex_run = read_run(run_path(rev, "vertex_gemini"))
    assert gemma_run.dryRun is True
    assert vertex_run.dryRun is True
    assert gemma_run.status == "PLANNED"
    assert vertex_run.status == "PLANNED"
    plan = json.loads((rev / "plan.json").read_text("utf-8"))
    assert {row["provider"] for row in plan["providers"]} == {"gemma_qlora", "vertex_gemini"}
    assert (rev / "vertex_gemini" / "vertex" / "train.jsonl").is_file()


def test_gemma_submit_resumes_matching_chunks(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.plan(request)
    job = "/workspace/cfp/cf-1/ds1/tr1"
    first = (ds_dir / "train.jsonl").read_bytes()[:8]
    host.files[f"{job}/train.jsonl.part000000"] = first

    submitted = provider.submit(run, request)

    assert f"{job}/train.jsonl.part000000" not in host.puts
    assert f"{job}/train.jsonl" in host.files
    assert host.sha256(f"{job}/train.jsonl") == sha256_file(ds_dir / "train.jsonl")
    assert submitted.status == "SUBMITTED"
    assert submitted.jobId == job
    assert submitted.dryRun is False
    assert len(submitted.transfers) == 3
    assert all(t.remoteSha256 == t.sha256 for t in submitted.transfers)
    assert host.commands and "train_qlora.py" in host.commands[0][-1]


def test_gemma_submit_stops_when_remote_hash_differs(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    job = "/workspace/cfp/cf-1/ds1/tr1"
    host = LyingHost(f"{job}/train.jsonl")
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.plan(request)

    with pytest.raises(TrainingIntegrityError):
        provider.submit(run, request)
    assert host.commands == []


def test_gemma_status_needs_complete_json(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job

    assert provider.status(run, request).status == "SUBMITTED"
    host.files[f"{job}/train.log"] = b"epoch 1\n"
    assert provider.status(run, request).status == "RUNNING"
    host.write_text(
        f"{job}/complete.json",
        json.dumps({"ok": True, "files": [], "checkpoints": []}),
    )
    assert provider.status(run, request).status == "SUCCEEDED"


def test_gemma_collect_verifies_then_deletes_remote(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    adapter = b"adapter-bytes"
    host.files[f"{job}/adapter/adapter_model.safetensors"] = adapter
    host.write_text(
        f"{job}/complete.json",
        json.dumps(
            {
                "ok": True,
                "modelBindingRef": "adapter",
                "files": [
                    {
                        "path": "adapter/adapter_model.safetensors",
                        "bytes": len(adapter),
                        "sha256": hashlib.sha256(adapter).hexdigest(),
                    }
                ],
                "checkpoints": [{"checkpointId": "epoch-3", "epoch": 3, "step": 120, "ref": "ep3"}],
            }
        ),
    )

    done = provider.collect(run, request)

    assert done.status == "SUCCEEDED"
    assert done.modelBinding is not None
    assert done.modelBinding.provider == "gemma_qlora"
    assert done.modelBinding.checkpointId == "epoch-3"
    assert done.checkpoints[0].epoch == 3
    assert done.checkpoints[0].step == 120
    local = request.artifact_dir / "adapter" / "adapter_model.safetensors"
    assert local.read_bytes() == adapter
    assert job in host.deleted


def test_gemma_collect_hash_mismatch_keeps_remote(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    host.files[f"{job}/adapter/adapter_model.safetensors"] = b"x"
    host.write_text(
        f"{job}/complete.json",
        json.dumps(
            {
                "ok": True,
                "files": [
                    {"path": "adapter/adapter_model.safetensors", "bytes": 1, "sha256": "0" * 64}
                ],
                "checkpoints": [],
            }
        ),
    )

    with pytest.raises(TrainingIntegrityError):
        provider.collect(run, request)
    assert host.deleted == []


def test_vertex_submit_status_and_checkpoints_with_mock_transport(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    seen: list[httpx.Request] = []
    job = {
        "name": "projects/p/locations/us-central1/tuningJobs/123",
        "state": "JOB_STATE_SUCCEEDED",
        "baseModel": "gemini-3.1-flash-lite",
        "tunedModel": {
            "model": "projects/p/locations/us-central1/models/tuned@1",
            "checkpoints": [
                {
                    "checkpointId": "ck-1",
                    "epoch": "1",
                    "step": "100",
                    "endpoint": "projects/p/locations/us-central1/endpoints/1",
                },
                {"checkpointId": "ck-2", "step": "200"},
            ],
        },
        "tuningDataStats": {"supervisedTuningDataStats": {"totalBillableTokenCount": "999"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert request.url.path.endswith("/tuningJobs")
            assert body["baseModel"] == "gemini-3.1-flash-lite"
            assert body["supervisedTuningSpec"]["trainingDatasetUri"] == "gs://b/train.jsonl"
            return httpx.Response(
                200,
                json={
                    "name": job["name"],
                    "state": "JOB_STATE_PENDING",
                    "baseModel": body["baseModel"],
                },
            )
        return httpx.Response(200, json=job)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = ProviderConfig(
        adapter="vertex_gemini",
        model="gemini-3.1-flash-lite",
        extra={
            "client": client,
            "token_provider": lambda: "test-token",
            "project": "p",
            "location": "us-central1",
            "training_dataset_uri": "gs://b/train.jsonl",
            "validation_dataset_uri": "gs://b/val.jsonl",
            "epochs": 3,
            "chars_per_token": 1.0,
            "price_per_million_tokens_usd": 3.0,
        },
    )
    provider = VertexGeminiProvider(cfg)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)

    assert run.status == "SUBMITTED"
    assert run.jobId == job["name"]
    assert seen[-1].headers["Authorization"] == "Bearer test-token"
    assert "test-token" not in json.dumps(dump(run))

    running = provider.status(run, request)
    assert running.status == "SUCCEEDED"
    assert running.checkpoints[0].epoch == 1
    assert running.checkpoints[0].step == 100
    assert running.checkpoints[1].epoch is None
    assert running.checkpoints[1].step == 200
    assert running.appliedConfig["tuningDataStats"]["totalBillableTokenCount"] == "999"

    done = provider.collect(running, request)
    assert done.modelBinding is not None
    assert done.modelBinding.provider == "vertex_gemini"
    assert done.modelBinding.ref == job["tunedModel"]["model"]
    assert done.modelBinding.checkpointId == "ck-2"


def test_fake_provider_runs_to_model_binding(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    toml = """
[stages.s10t]
providers = ["fake"]
budget_usd = 5.0
"""
    ctx = make_ctx(tmp_path, toml, execute=True)
    rev = plan_s10t(ctx, CID, ["fake"])
    planned = read_run(run_path(rev, "fake"))
    assert planned.dryRun is True
    assert planned.status == "PLANNED"
    assert ctx.state(CID).stage("s10t").status == "AWAITING_HUMAN"

    submit_s10t(ctx, CID, ["fake"])
    submitted = read_run(run_path(rev, "fake"))
    assert submitted.status == "SUCCEEDED"
    assert submitted.modelBinding is not None
    assert submitted.modelBinding.provider == "fake"
    assert ctx.state(CID).stage("s10t").status == "APPROVED"

    collect_s10t(ctx, CID, ["fake"])
    collected = read_run(run_path(rev, "fake"))
    assert collected.modelBinding == submitted.modelBinding


def test_plan_only_never_submits_without_execute(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    ctx = make_ctx(tmp_path, '[stages.s10t]\nproviders = ["fake"]\n', execute=False)
    rev = plan_s10t(ctx, CID, ["fake"])
    with pytest.raises(TrainingLimitError):
        submit_s10t(ctx, CID, ["fake"])
    run = read_run(run_path(rev, "fake"))
    assert run.status == "PLANNED"
    assert run.jobId is None


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        make_training_provider("nope", ProviderConfig(adapter="nope"))


def test_latest_rev_and_run_roundtrip(tmp_path: Path) -> None:
    make_dataset(tmp_path)
    ctx = make_ctx(tmp_path, '[stages.s10t]\nproviders = ["fake"]\n')
    first = plan_s10t(ctx, CID, ["fake"])
    second = plan_s10t(ctx, CID, ["fake"])
    assert first.name == "tr1"
    assert second.name == "tr2"
    assert latest_rev(ctx, CID) == second
    run: TrainingRun = read_run(run_path(second, "fake"))
    assert run.datasetRev == "ds1"
