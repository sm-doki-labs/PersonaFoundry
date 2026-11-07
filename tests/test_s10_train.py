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
from character_factory_poc.providers.training.gemma_qlora import GemmaQLoraProvider, GemmaSettings
from character_factory_poc.providers.training.port import TrainRequest
from character_factory_poc.providers.training.vertex_gemini import VertexGeminiProvider
from character_factory_poc.stages.s10_train.collect import collect_s10t
from character_factory_poc.stages.s10_train.io import latest_rev, read_run, run_path
from character_factory_poc.stages.s10_train.plan import plan_s10t
from character_factory_poc.stages.s10_train.submit import submit_s10t
from tests.test_vast_lease import FakeVast, lease_extra

CID = "cf-1"
N3B_REVISION = "8e256fc6d63003fc0ca8c91b976e6dcc38433385"


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


def leased_gemma(tmp_path: Path, host: FakeRemoteHost, vast: FakeVast) -> GemmaQLoraProvider:
    """remote_host 없이 Vast 임대 모드로 돈다. 준비된 GPU의 SSH는 가짜 호스트로 바꾼다."""
    cfg = ProviderConfig(
        adapter="gemma_qlora",
        model="unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        extra={
            **lease_extra(tmp_path, vast, host=host),
            "chunk_bytes": 8,
            "prep_overhead_seconds": 0.0,
            "max_cost_usd": 20.0,
            "max_gpu_hours": 8.0,
        },
    )
    return GemmaQLoraProvider(cfg)


def finish_remote(
    host: FakeRemoteHost,
    job: str,
    files: dict[str, bytes],
    checkpoints: list[dict],
    *,
    screen: bytes | None = b'{"arm":"base"}\n',
    bad: str = "",
    **extra: object,
) -> None:
    """원격 학습·선별이 끝난 모습: 파일, complete.json, screen-complete.json."""

    def entry(path: str, data: bytes) -> dict:
        digest = "0" * 64 if path == bad else hashlib.sha256(data).hexdigest()
        return {"path": path, "bytes": len(data), "sha256": digest}

    for path, data in files.items():
        host.files[f"{job}/{path}"] = data
    host.write_text(
        f"{job}/complete.json",
        json.dumps(
            {
                "ok": True,
                "files": [entry(p, d) for p, d in files.items()],
                "checkpoints": checkpoints,
                **extra,
            }
        ),
    )
    if screen is not None:
        host.files[f"{job}/screen/responses.jsonl"] = screen
        host.write_text(
            f"{job}/screen-complete.json",
            json.dumps({"ok": True, "files": [entry("screen/responses.jsonl", screen)]}),
        )


def test_gemma_defaults_follow_musk_n3b() -> None:
    s = GemmaSettings.from_extra({})
    assert s.revision == N3B_REVISION
    assert s.chat_template == "gemma-4-thinking"
    assert (s.lora_r, s.lora_alpha, s.lora_dropout) == (16, 32, 0.0)
    assert (s.learning_rate, s.lr_scheduler) == (5e-5, "constant_with_warmup")
    assert s.epochs == 2.0
    assert s.checkpoint_epochs == (0.5, 1.0, 1.5, 2.0)
    # N3b 실측 236스텝 2,060초 ≈ 8.7초/스텝, 준비 900초, Vast L40S 시간당 상한 $0.90.
    assert s.step_seconds == 8.7
    assert s.prep_overhead_seconds == 900.0
    assert s.hourly_rate_usd == 0.90
    # 품질 운영 규격 개발 비교: 단발 24 + 6턴 장면 2, 기반 모델도 함께 생성.
    assert (s.screen_single, s.screen_multi, s.screen_turns) == (24, 2, 6)
    assert s.screen_include_base is True
    assert s.remote_python == "/venv/main/bin/python"  # 임대 템플릿의 venv
    assert GemmaSettings.from_extra({"ssh_host": "h"}).remote_python == "python"
    assert GemmaSettings.from_extra({"checkpoint_epochs": "2,1"}).checkpoint_epochs == (1.0, 2.0)


def test_gemma_plan_has_dataset_hashes_steps_and_cost(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    run = provider.plan(request_for(tmp_path, dataset, ds_dir))

    assert run.schemaVersion == "training-run-v2"
    assert run.dryRun is True
    assert run.status == "PLANNED"
    assert run.jobId is None
    assert run.baseModelRevision == N3B_REVISION
    assert len(run.transfers) == 3
    assert {t.path for t in run.transfers} == {
        "train.jsonl",
        "validation-base.jsonl",
        "validation-augmented.jsonl",
    }
    assert all(t.sha256 == sha256_file(ds_dir / t.path) for t in run.transfers)
    # 학습: ceil(10대화 × 2 epoch / (배치 1 × 누적 4)) = 5스텝 × 8.7초 = 43.5초.
    # 준비는 테스트 설정으로 0초.
    # 선별: 검증 대화 3개는 모두 한 턴이라 단발 3개·6턴 장면 0개. 체크포인트 4개 + base = 5조건
    # × 3 = 15생성 × 12초 + 모델 적재 420초 = 600초. 합 643.5초, 시간당 $0.90.
    seconds = 5 * 8.7 + 15 * 12 + 420
    assert run.estimate.gpuHours == pytest.approx(seconds / 3600, abs=1e-4)
    assert run.estimate.usd == pytest.approx(round(seconds / 3600 * 0.9, 4))
    assert "L40S" in run.estimate.basis
    assert "스텝 5" in run.estimate.basis
    assert run.requestedConfig["loraR"] == 16
    assert run.requestedConfig["loraAlpha"] == 32
    assert run.requestedConfig["maxSeqLength"] == 4096
    assert run.requestedConfig["lossOn"] == "assistant"
    assert run.requestedConfig["epochs"] == 2.0
    assert run.requestedConfig["checkpointEpochs"] == [0.5, 1.0, 1.5, 2.0]
    assert run.requestedConfig["lrScheduler"] == "constant_with_warmup"
    assert run.requestedConfig["selection"] == "generation"
    assert run.requestedConfig["screenGenerations"] == 15
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
    # 선별이 기본으로 켜져 있어 원격에 screen/requests.jsonl이 있다.
    # 학습 완료(complete.json)만으로는 끝나지 않는다.
    assert host.sha256(f"{job}/screen/requests.jsonl") is not None
    assert provider.status(run, request).status == "RUNNING"
    host.write_text(f"{job}/screen-complete.json", json.dumps({"ok": True, "files": []}))
    done = provider.status(run, request)
    assert done.status == "SUCCEEDED"
    assert done.appliedConfig["screen"] == "done"


def test_gemma_status_without_screening_needs_only_complete_json(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host, screen_single=0, screen_multi=0)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    assert host.sha256(f"{job}/screen/requests.jsonl") is None
    assert "screen_qlora.py" not in host.commands[0][-1]

    host.write_text(
        f"{job}/complete.json", json.dumps({"ok": True, "files": [], "checkpoints": []})
    )
    done = provider.status(run, request)
    assert done.status == "SUCCEEDED"
    assert done.appliedConfig["screen"] == "none"


def test_gemma_collect_verifies_then_deletes_remote(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    adapter = b"adapter-bytes"
    half = b"half-epoch-adapter"
    screen = b'{"arm":"epoch-2","taskId":"s-1"}\n'
    finish_remote(
        host,
        job,
        {
            "checkpoints/epoch-0.5/adapter_model.safetensors": half,
            "checkpoints/epoch-2/adapter_model.safetensors": adapter,
        },
        [
            {"checkpointId": "epoch-0.5", "epoch": 0.5, "step": 2, "ref": "checkpoints/epoch-0.5"},
            {
                "checkpointId": "epoch-2",
                "epoch": 2.0,
                "step": 5,
                "ref": "checkpoints/epoch-2",
                "validationLoss": 1.25,
            },
        ],
        screen=screen,
        modelBindingRef="checkpoints/epoch-2",
    )

    done = provider.collect(run, request)

    assert done.status == "SUCCEEDED"
    assert done.modelBinding is not None
    assert done.modelBinding.provider == "gemma_qlora"
    assert done.modelBinding.checkpointId == "epoch-2"
    assert done.modelBinding.ref.endswith("checkpoints/epoch-2")
    assert done.checkpoints[0].epoch == 0.5
    assert done.checkpoints[1].epoch == 2
    assert done.checkpoints[1].step == 5
    assert done.checkpoints[1].validationLoss == 1.25
    local = request.artifact_dir / "checkpoints" / "epoch-2" / "adapter_model.safetensors"
    assert local.read_bytes() == adapter
    assert (request.artifact_dir / "screen" / "responses.jsonl").read_bytes() == screen
    assert (request.artifact_dir / "remote" / "screen-complete.json").is_file()
    assert (request.artifact_dir / "remote" / "complete.json").is_file()
    assert done.appliedConfig["remoteDeleted"] is True
    assert "leaseDestroyed" not in done.appliedConfig
    assert job in host.deleted


@pytest.mark.parametrize(
    "bad", ["checkpoints/epoch-2/adapter_model.safetensors", "screen/responses.jsonl"]
)
def test_gemma_collect_hash_mismatch_keeps_remote(tmp_path: Path, bad: str) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    finish_remote(
        host,
        job,
        {"checkpoints/epoch-2/adapter_model.safetensors": b"x"},
        [{"checkpointId": "epoch-2", "epoch": 2, "ref": "checkpoints/epoch-2"}],
        bad=bad,
    )

    with pytest.raises(TrainingIntegrityError):
        provider.collect(run, request)
    assert host.deleted == []


def test_gemma_collect_without_binding_ref_keeps_remote(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    finish_remote(host, job, {"training.json": b"{}"}, [])

    with pytest.raises(TrainingIntegrityError):
        provider.collect(run, request)
    assert host.deleted == []


def test_gemma_lease_submit_records_lease_and_job_script(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    vast = FakeVast()
    provider = leased_gemma(tmp_path, host, vast)
    assert provider.uses_lease
    request = request_for(tmp_path, dataset, ds_dir)

    run = provider.submit(provider.plan(request), request)

    lease = json.loads((request.plan_dir / "lease.json").read_text("utf-8"))
    assert lease["status"] == "READY"
    assert lease["instanceId"] == 7001
    assert len(vast.args("create", "instance")) == 1
    assert run.status == "SUBMITTED"
    assert run.appliedConfig["lease"] == "vast"
    assert run.appliedConfig["instanceId"] == "7001"
    assert run.appliedConfig["gpu"] == "L40S"
    assert run.appliedConfig["screenTasks"] == 3
    assert (request.plan_dir / "screen-requests.jsonl").is_file()
    probe, command = host.commands  # 준비 확인(SSH로 true 실행) 뒤 학습 시작
    assert probe == ["true"]
    assert command[:2] == ["bash", "-lc"]
    script = command[2]
    order = [
        script.index("/venv/main/bin/python train_qlora.py"),
        script.index("if [ $rc -eq 0 ]; then /venv/main/bin/python screen_qlora.py"),
        script.index("job-exit.json"),
        script.index("> job.sh"),
        script.index("nohup timeout"),
    ]
    assert order == sorted(order)
    assert "--include-base" in script
    # 다시 제출해도 GPU를 새로 만들지 않는다.
    assert provider.submit(run, request) == run
    assert len(vast.args("create", "instance")) == 1


def test_gemma_lease_collect_fetches_then_destroys_gpu(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    vast = FakeVast()
    provider = leased_gemma(tmp_path, host, vast)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    finish_remote(
        host,
        job,
        {"checkpoints/epoch-2/adapter_model.safetensors": b"adapter"},
        [{"checkpointId": "epoch-2", "epoch": 2, "ref": "checkpoints/epoch-2"}],
    )

    done = provider.collect(run, request)

    assert (request.artifact_dir / "screen" / "responses.jsonl").is_file()
    assert job in host.deleted
    assert vast.args("destroy", "instance") == [
        ["vastai", "destroy", "instance", "7001", "--yes", "--raw"]
    ]
    assert json.loads((request.plan_dir / "lease.json").read_text("utf-8"))["status"] == "DESTROYED"
    assert done.appliedConfig["leaseDestroyed"] is True
    assert done.appliedConfig["remoteDeleted"] is True


def test_gemma_lease_collect_mismatch_keeps_gpu(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    vast = FakeVast()
    provider = leased_gemma(tmp_path, host, vast)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    assert run.jobId
    finish_remote(
        host,
        run.jobId,
        {"checkpoints/epoch-2/adapter_model.safetensors": b"adapter"},
        [{"checkpointId": "epoch-2", "epoch": 2, "ref": "checkpoints/epoch-2"}],
        bad="checkpoints/epoch-2/adapter_model.safetensors",
    )

    with pytest.raises(TrainingIntegrityError):
        provider.collect(run, request)
    assert host.deleted == []
    assert vast.args("destroy", "instance") == []


def test_gemma_lease_abort_saves_logs_then_destroys_gpu(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    vast = FakeVast()
    provider = leased_gemma(tmp_path, host, vast)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    job = run.jobId
    assert job
    host.write_text(f"{job}/train.log", "x" * 250_000 + "OOM at step 3\n")
    host.write_text(f"{job}/state.json", '{"phase":"training"}')
    host.write_text(f"{job}/job-exit.json", '{"train":1,"screen":"skip"}\n')

    provider.abort(run, request)

    saved = request.artifact_dir / "remote"
    log = (saved / "train.log").read_text("utf-8")
    assert log.endswith("OOM at step 3\n")
    assert len(log) == 200_000
    assert (saved / "state.json").is_file()
    assert (saved / "job-exit.json").is_file()
    assert len(vast.args("destroy", "instance")) == 1
    assert json.loads((request.plan_dir / "lease.json").read_text("utf-8"))["status"] == "DESTROYED"


def test_gemma_lease_abort_destroys_gpu_that_never_became_ready(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    vast = FakeVast(rows=[{"actual_status": "loading"}])
    provider = leased_gemma(tmp_path, host, vast)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.plan(request)

    with pytest.raises(Exception, match="준비되지 않았다"):
        provider.submit(run, request)
    provider.abort(run, request)

    assert host.commands == []
    assert len(vast.args("destroy", "instance")) == 1
    assert json.loads((request.plan_dir / "lease.json").read_text("utf-8"))["status"] == "DESTROYED"


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
