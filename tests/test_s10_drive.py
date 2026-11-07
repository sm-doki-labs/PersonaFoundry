"""S10t 실행 몰기 종단 시험: 계획 → 제출 → 원격 학습·선별(모의) → 회수 → 체크포인트 선택 → binding.

실제 GPU 대신 원격 작업을 흉내 내는 호스트를 쓴다. job.sh 실행 요청을 받으면 학습 스크립트와 선별
스크립트가 남기는 파일(체크포인트, complete.json, screen/responses.jsonl, screen-complete.json,
job-exit.json)을 같은 형식으로 만든다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.dataset import ClusterCount, DatasetRev, SplitFile
from character_factory_poc.contracts.training import ModelBinding
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training.errors import RemoteHostError, TrainingLimitError
from character_factory_poc.providers.training.gemma_qlora import (
    REMOTE_PROCESS_PATTERN,
    GemmaQLoraProvider,
    kill_command,
)
from character_factory_poc.providers.training.screening import read_tasks
from character_factory_poc.stages.s10_train import drive as drive_mod
from character_factory_poc.stages.s10_train import guard as guard_mod
from character_factory_poc.stages.s10_train import io as io_mod
from character_factory_poc.stages.s10_train.drive import (
    CollectPendingError,
    DriveSignal,
    cleanup_s10t,
    drive_s10t,
)
from character_factory_poc.stages.s10_train.io import latest_rev, read_run, run_path
from character_factory_poc.stages.s10_train.plan import plan_s10t
from character_factory_poc.stages.s10_train.run import _in_flight, run_s10t
from character_factory_poc.stages.s10_train.submit import submit_s10t
from tests.test_vast_lease import FakeVast, lease_extra

CID = "cf-drive"


def _conv(system: str, turns: int, tag: str) -> str:
    messages = [{"role": "system", "content": system}]
    for n in range(turns):
        messages.append({"role": "user", "content": f"{tag} 질문 {n}"})
        messages.append({"role": "assistant", "content": f"{tag} 대답 {n}이야"})
    return json.dumps({"messages": messages}, ensure_ascii=False)


def make_dataset(root: Path) -> None:
    ds_dir = root / "runs" / "characters" / CID / "s9-data" / "ds1"
    ds_dir.mkdir(parents=True)
    spec = {
        "train.jsonl": ("train", [_conv("짧은 system", 2, f"t{i}") for i in range(8)]),
        "validation-base.jsonl": (
            "validation_base",
            [_conv("짧은 system", 4, f"v{i}") for i in range(5)],
        ),
        "validation-augmented.jsonl": (
            "validation_augmented",
            [_conv("짧은 system", 1, f"a{i}") for i in range(3)],
        ),
    }
    files = []
    for name, (split, lines) in spec.items():
        path = ds_dir / name
        path.write_text("\n".join(lines) + "\n", "utf-8")
        files.append(
            SplitFile(split=split, path=name, sha256=sha256_file(path), conversations=len(lines))
        )
    dataset = DatasetRev(
        characterId=CID,
        datasetRev="ds1",
        personaVersion="pv1",
        planSha256="1" * 64,
        sampleQaRefs=["gates/G7a.json"],
        clusterCounts={"base": ClusterCount(conversations=8, replies=16)},
        files=files,
        blockingFailures=0,
        digest="2" * 64,
    )
    (ds_dir / "dataset.json").write_text(json.dumps(dump(dataset), ensure_ascii=False), "utf-8")


class SimHost:
    """원격 작업 폴더를 dict로 흉내 낸다. job.sh 실행 때 원격 스크립트 산출물을 만든다."""

    def __init__(self, *, finish: bool = True) -> None:
        self.files: dict[str, bytes] = {}
        self.finish = finish
        self.deleted: list[str] = []
        self.commands: list[str] = []
        self.fail_puts = 0
        self.fail_fetches = 0

    def sha256(self, path):
        data = self.files.get(path)
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def put_chunk(self, path, data):
        if self.fail_puts:
            self.fail_puts -= 1
            raise RemoteHostError("원격 조각 전송 실패(rc=255): connection reset")
        self.files[path] = data

    def concat(self, parts, dest):
        self.files[dest] = b"".join(self.files.pop(p) for p in parts)

    def write_text(self, path, text):
        self.files[path] = text.encode("utf-8")

    def read_text(self, path):
        data = self.files.get(path)
        return data.decode("utf-8") if data is not None else None

    def fetch(self, remote, local):
        if self.fail_fetches:
            self.fail_fetches -= 1
            raise RemoteHostError("파일 회수 실패(4회 시도, 마지막: 시간 초과(180초))")
        Path(local).write_bytes(self.files[remote])

    def delete(self, path):
        self.deleted.append(path)
        for key in [k for k in self.files if k.startswith(path)]:
            del self.files[key]

    def _entry(self, job: str, rel: str, data: bytes) -> dict:
        self.files[f"{job}/{rel}"] = data
        return {"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def run(self, argv):
        command = argv[-1]
        self.commands.append(command)
        if "job.sh" not in command:
            return ""
        job = command.split("cd ", 1)[1].split(" && ", 1)[0].strip("'")
        self.files[f"{job}/train.log"] = b"STATE training\n"
        if not self.finish:
            return "4242"
        checkpoints, files = [], []
        for epoch, step in ((0.5, 2), (1, 4), (1.5, 6), (2, 8)):
            tag = f"epoch-{epoch:g}"
            for name in ("adapter_config.json", "adapter_model.safetensors"):
                files.append(
                    self._entry(job, f"checkpoints/{tag}/{name}", f"{tag}:{name}".encode())
                )
            checkpoints.append(
                {
                    "checkpointId": tag,
                    "epoch": epoch,
                    "step": step,
                    "ref": f"checkpoints/{tag}",
                    "validationLoss": 2.3 - step * 0.01,
                }
            )
        complete = {
            "ok": True,
            "finished": True,
            "modelBindingRef": "checkpoints/epoch-2",
            "checkpoints": checkpoints,
            "files": files,
            "appliedConfig": {"runtimeVersions": {"unsloth": "2026.10.3"}},
        }
        self.files[f"{job}/complete.json"] = json.dumps(complete).encode()
        tasks = [json.loads(x) for x in self.read_text(f"{job}/screen/requests.jsonl").splitlines()]
        rows = []
        for arm in ["base", *(c["checkpointId"] for c in checkpoints)]:
            for task in tasks:
                users = task.get("userTurns") or [None]
                turns = [
                    {
                        "turn": n,
                        "user": u or "",
                        "text": f"{arm} {task['taskId']} 대답 {n}",
                        "finish": "stop",
                        "inputTokens": 10,
                        "outputTokens": 5,
                    }
                    for n, u in enumerate(users, start=1)
                ]
                rows.append(
                    json.dumps(
                        {
                            "arm": arm,
                            "taskId": task["taskId"],
                            "kind": task["kind"],
                            "turns": turns,
                        },
                        ensure_ascii=False,
                    )
                )
        entry = self._entry(job, "screen/responses.jsonl", ("\n".join(rows) + "\n").encode())
        self.files[f"{job}/screen-complete.json"] = json.dumps(
            {"ok": True, "files": [entry]}
        ).encode()
        self.files[f"{job}/job-exit.json"] = b'{"train":0,"screen":"0"}'
        return "4242"


TOML = """
[budget]
max_calls_per_command = 500
max_cost_usd_per_command = 20

[stages.s10t]
providers = ["gemma_qlora"]
budget_usd = 10
poll_s = 0
selection_judge = false

[stages.s10t.gemma_qlora]
ssh_host = "sim.invalid"
screen_single = 4
screen_multi = 1
screen_turns = 3
"""


@pytest.fixture
def setup(tmp_path, monkeypatch):
    make_dataset(tmp_path)
    (tmp_path / "factory.toml").write_text(TOML, "utf-8")
    host = SimHost()
    monkeypatch.setattr(GemmaQLoraProvider, "_host", lambda self, request=None: host)
    ctx = Context.load(tmp_path, execute=True)
    ctx.state(CID).set_gate("G7", "APPROVED", "ds1", "gates/G7.json")
    return ctx, host


def test_drive_runs_plan_to_selected_binding(setup):
    ctx, host = setup
    plan_s10t(ctx, CID)
    rev_dir = drive_s10t(ctx, CID, sleep=lambda s: None, log=lambda m: None)
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    assert run.status == "SUCCEEDED"
    assert [c.epoch for c in run.checkpoints] == [0.5, 1, 1.5, 2]
    assert run.checkpoints[0].validationLoss == pytest.approx(2.28)
    selection = json.loads((rev_dir / "gemma_qlora" / "checkpoint-selection.json").read_text())
    # 판정 없이(selection_judge=false) 결함이 없으면 마지막 적격을 고르고 INCONCLUSIVE로 남긴다.
    assert selection["decision"] == "INCONCLUSIVE"
    assert run.appliedConfig["selection"]["checkpointId"] == "epoch-2"
    adapter = Path(run.modelBinding.ref)
    assert adapter.name == "epoch-2" and (adapter / "adapter_model.safetensors").is_file()
    assert adapter.is_relative_to(rev_dir / "gemma_qlora" / "artifacts")
    tasks = read_tasks(rev_dir / "gemma_qlora" / "screen-requests.jsonl")
    assert {t["kind"] for t in tasks} == {"single", "multi"}
    assert host.deleted, "회수 뒤 원격 작업 폴더를 지워야 한다"
    assert ctx.state(CID).stage("s10t").status == "APPROVED"


def test_drive_interrupt_cancels_and_aborts(setup, monkeypatch):
    ctx, host = setup
    host.finish = False
    aborted = []
    monkeypatch.setattr(
        GemmaQLoraProvider, "abort", lambda self, run, request: aborted.append(run.jobId) or run
    )
    plan_s10t(ctx, CID)

    def stop(_seconds):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        drive_s10t(ctx, CID, sleep=stop, log=lambda m: None)
    run = read_run(run_path(latest_rev(ctx, CID), "gemma_qlora"))
    assert run.status == "CANCELLED"
    assert aborted and "실행 중단" in run.appliedConfig["error"]


# ---- 비용 안전(R2) -------------------------------------------------------------------------------


def no_sleep(_seconds: float) -> None:
    return None


def quiet(_message: str) -> None:
    return None


def test_kill_command_never_matches_its_own_shell() -> None:
    job = "/workspace/cfp/cf-drive/ds1/tr1"
    dedicated = kill_command(job, dedicated=True)
    # 원격에서 이 명령을 실행하는 bash -lc의 명령줄이 곧 이 문자열이다. pkill -f 패턴이 자기 셸과
    # 맞으면 학습보다 먼저 자기를 죽인다.
    assert re.search(REMOTE_PROCESS_PATTERN, dedicated) is None
    assert re.search(REMOTE_PROCESS_PATTERN, "python train_qlora.py --train train.jsonl")
    assert re.search(REMOTE_PROCESS_PATTERN, "python screen_qlora.py --include-base")
    assert 'pkill -TERM -g "$pid"' in dedicated and "pid.txt" in dedicated
    shared = kill_command(job, dedicated=False)
    assert "pkill -TERM -f" not in shared  # ssh_host 모드는 작업 프로세스 그룹만 끈다
    assert f"pkill -f {job}" not in shared


def test_ssh_host_abort_stops_remote_training(setup):
    ctx, host = setup
    host.finish = False
    plan_s10t(ctx, CID)

    def stop(_seconds):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        drive_s10t(ctx, CID, sleep=stop, log=quiet)
    kills = [c for c in host.commands if "pkill" in c]
    assert kills and "pid.txt" in kills[-1]


def test_sigterm_becomes_abort_and_handler_is_restored(setup, monkeypatch):
    ctx, host = setup
    host.finish = False
    aborted = []
    monkeypatch.setattr(
        GemmaQLoraProvider, "abort", lambda self, run, request: aborted.append(run.jobId) or run
    )
    before_term = signal.getsignal(signal.SIGTERM)
    before_hup = signal.getsignal(signal.SIGHUP)
    plan_s10t(ctx, CID)

    def terminate(_seconds):
        os.kill(os.getpid(), signal.SIGTERM)

    with pytest.raises(DriveSignal):
        drive_s10t(ctx, CID, sleep=terminate, log=quiet)

    run = read_run(run_path(latest_rev(ctx, CID), "gemma_qlora"))
    assert run.status == "CANCELLED"
    assert aborted and "SIGTERM" in run.appliedConfig["error"]
    assert signal.getsignal(signal.SIGTERM) is before_term
    assert signal.getsignal(signal.SIGHUP) is before_hup


def test_selection_retry_skips_remote_status_and_never_aborts(setup, monkeypatch):
    ctx, _host = setup
    rev_dir = plan_s10t(ctx, CID)
    path = run_path(rev_dir, "gemma_qlora")
    run = read_run(path)
    write = io_mod.write_run
    write(
        path,
        run.model_copy(
            update={
                "status": "SUCCEEDED",
                "dryRun": False,
                "jobId": "/workspace/cfp/job",
                "appliedConfig": {"remoteDeleted": True, "selection": {"decision": "PENDING"}},
            }
        ),
    )

    def no_status(self, run, request):
        raise AssertionError("GPU가 지워진 뒤에는 원격 상태를 묻지 않는다")

    aborted = []
    monkeypatch.setattr(GemmaQLoraProvider, "status", no_status)
    monkeypatch.setattr(
        GemmaQLoraProvider, "abort", lambda self, run, request: aborted.append(1) or run
    )
    calls = []

    def flaky_collect(ctx_, cid, providers=None):
        calls.append(providers)
        if len(calls) == 1:
            raise RuntimeError("판정 모델 응답 없음")
        current = read_run(path)
        applied = {**current.appliedConfig, "selection": {"decision": "INCONCLUSIVE"}}
        binding = ModelBinding(provider="gemma_qlora", ref=str(rev_dir), checkpointId="epoch-2")
        write(path, current.model_copy(update={"appliedConfig": applied, "modelBinding": binding}))
        return rev_dir

    monkeypatch.setattr(drive_mod, "collect_s10t", flaky_collect)
    assert _in_flight(ctx, CID, None)

    with pytest.raises(RuntimeError, match="판정 모델"):
        drive_s10t(ctx, CID, sleep=no_sleep, log=quiet)
    assert read_run(path).status == "SUCCEEDED"  # 취소로 덮지 않는다
    assert aborted == []

    drive_s10t(ctx, CID, sleep=no_sleep, log=quiet)
    assert calls == [["gemma_qlora"], ["gemma_qlora"]]
    assert read_run(path).modelBinding is not None
    assert not _in_flight(ctx, CID, None)


# ---- Vast 임대 모드: 가짜 vastai + 모의 원격 호스트 ----------------------------------------

LEASE_TOML = TOML.replace('ssh_host = "sim.invalid"\n', "")


@pytest.fixture
def leased(tmp_path, monkeypatch):
    make_dataset(tmp_path)
    (tmp_path / "factory.toml").write_text(LEASE_TOML, "utf-8")
    host = SimHost()
    vast = FakeVast()
    extra = lease_extra(tmp_path, vast, host=host)
    original = io_mod._config_for

    def config_for(ctx, adapter):
        cfg = original(ctx, adapter)
        return replace(cfg, extra={**cfg.extra, **extra})

    monkeypatch.setattr(io_mod, "_config_for", config_for)
    guards: list[tuple[Path, int]] = []

    def fake_start(root, cid, adapter, plan_dir, **_kw):
        # 실제로는 새 세션의 프로세스를 띄우고 준비 기록을 기다린다(test_s10_guard).
        guards.append((plan_dir, len(vast.args("create", "instance"))))
        return 1

    monkeypatch.setattr(guard_mod, "start_guard", fake_start)
    ctx = Context.load(tmp_path, execute=True)
    ctx.state(CID).set_gate("G7", "APPROVED", "ds1", "gates/G7.json")
    return ctx, host, vast, guards


def lease_of(ctx) -> dict:
    return json.loads((latest_rev(ctx, CID) / "gemma_qlora" / "lease.json").read_text("utf-8"))


def test_lease_drive_starts_guard_before_renting_and_destroys_after_collect(leased):
    ctx, _host, vast, guards = leased

    rev_dir = run_s10t(ctx, CID)

    assert guards and guards[0][1] == 0, "guard는 GPU 생성 전에 떠야 한다"
    assert guard_mod.read_plan(rev_dir / "gemma_qlora")["deadlineEpoch"] > 0
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    assert run.status == "SUCCEEDED" and run.modelBinding is not None
    assert len(vast.args("create", "instance")) == 1
    assert len(vast.args("destroy", "instance")) == 1
    assert lease_of(ctx)["status"] == "DESTROYED"


def test_guard_start_failure_blocks_renting(leased, monkeypatch):
    ctx, _host, vast, _guards = leased

    def broken(*_a, **_k):
        raise drive_mod.TrainingError("guard 시작을 확인하지 못했다. GPU를 빌리지 않는다")

    monkeypatch.setattr(guard_mod, "start_guard", broken)
    with pytest.raises(drive_mod.TrainingError, match="guard"):
        run_s10t(ctx, CID)
    assert vast.args("create", "instance") == []
    assert vast.args("show", "user") == []


def test_upload_failure_in_drive_aborts_and_destroys_gpu(leased):
    ctx, host, vast, _guards = leased
    host.fail_puts = 1

    with pytest.raises(RemoteHostError, match="조각 전송"):
        run_s10t(ctx, CID)

    run = read_run(run_path(latest_rev(ctx, CID), "gemma_qlora"))
    assert run.status == "CANCELLED"
    assert len(vast.args("create", "instance")) == 1
    assert len(vast.args("destroy", "instance")) == 1
    assert lease_of(ctx)["status"] == "DESTROYED"


def test_rerun_after_upload_failure_reuses_the_same_gpu(leased):
    ctx, host, vast, _guards = leased
    plan_s10t(ctx, CID)
    host.fail_puts = 1
    # drive 밖에서 제출이 실패하고 프로세스가 죽은 상황: 기록은 PLANNED, GPU는 READY로 남는다.
    with pytest.raises(RemoteHostError):
        submit_s10t(ctx, CID)
    first = latest_rev(ctx, CID)
    assert read_run(run_path(first, "gemma_qlora")).status == "PLANNED"
    assert lease_of(ctx)["status"] == "READY"
    assert _in_flight(ctx, CID, None)

    rev_dir = run_s10t(ctx, CID)

    assert rev_dir == first, "새 학습 계획(=새 GPU)을 만들지 않는다"
    assert len(vast.args("create", "instance")) == 1
    assert len(vast.args("destroy", "instance")) == 1
    assert read_run(run_path(rev_dir, "gemma_qlora")).modelBinding is not None


def test_collect_timeout_keeps_gpu_and_records_collect_error(leased):
    ctx, host, vast, _guards = leased
    host.fail_fetches = 1

    with pytest.raises(CollectPendingError) as info:
        run_s10t(ctx, CID)

    message = str(info.value)
    assert "cfp train collect" in message and "cfp train cleanup" in message
    assert "guard" in message
    path = run_path(latest_rev(ctx, CID), "gemma_qlora")
    run = read_run(path)
    assert run.status == "SUCCEEDED"
    assert "시간 초과" in run.appliedConfig["collectError"]
    assert vast.args("destroy", "instance") == []
    assert lease_of(ctx)["status"] == "READY"
    assert _in_flight(ctx, CID, None)

    # 다시 몰면 같은 GPU에서 회수만 다시 하고 지운다.
    run_s10t(ctx, CID)
    run = read_run(path)
    assert run.modelBinding is not None
    assert "collectPending" not in run.appliedConfig
    assert len(vast.args("create", "instance")) == 1
    assert len(vast.args("destroy", "instance")) == 1


@pytest.mark.parametrize(("hours_ago", "ok"), [(7.5, True), (7.99, False)])
def test_gpu_ready_wait_shrinks_remote_wall_limit(leased, hours_ago, ok):
    ctx, host, vast, _guards = leased
    rev_dir = plan_s10t(ctx, CID)
    vast.instances.append({"id": 7001, "label": "cfp-old"})
    created = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    (rev_dir / "gemma_qlora" / "lease.json").write_text(
        json.dumps(
            {
                "status": "READY",
                "instanceId": 7001,
                "label": "cfp-old",
                "createdAt": created,
                "sshHost": "203.0.113.7",
                "sshPort": 41022,
            }
        ),
        "utf-8",
    )
    if not ok:
        with pytest.raises(TrainingLimitError, match="GPU 준비"):
            submit_s10t(ctx, CID)
        return
    submit_s10t(ctx, CID)
    run = read_run(run_path(rev_dir, "gemma_qlora"))
    started = json.loads(host.read_text(f"{run.jobId}/started.json"))
    assert started["maxWallHours"] == pytest.approx(0.5, abs=0.01)  # 상한 8시간 - 준비 7.5시간
    assert started["readyWaitSeconds"] == pytest.approx(7.5 * 3600, abs=60)
    launch = next(c for c in host.commands if "bash job.sh" in c)
    seconds = int(re.search(r"nohup timeout (\d+)s bash job.sh", launch).group(1))
    assert 1700 < seconds <= 1800


def test_cleanup_sweeps_old_revisions_eval_sessions_and_label_only_records(leased):
    ctx, _host, vast, _guards = leased
    char = ctx.character_dir(CID)

    def put(rel: str, data: dict) -> None:
        path = char / rel / "lease.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), "utf-8")

    vast.instances += [
        {"id": 7001, "label": "cfp-old"},
        {"id": 7005, "label": "cfp-lost"},
        {"id": 7003, "label": "cfp-eval"},
    ]
    put("s10-train/tr1/gemma_qlora", {"status": "READY", "instanceId": 7001, "label": "cfp-old"})
    put(
        "s10-train/tr2/gemma_qlora",
        {"status": "UNRESOLVED", "label": "cfp-lost", "preexisting": [900]},
    )
    put("s10-train/tr3/gemma_qlora", {"status": "DESTROYED", "instanceId": 7009})
    put("s10-eval/ev1/inference", {"status": "CREATED", "instanceId": 7003, "label": "cfp-eval"})

    removed = cleanup_s10t(ctx, CID)

    assert removed == ["7001", "7005", "7003"]
    destroyed = sorted(c[3] for c in vast.args("destroy", "instance"))
    assert destroyed == ["7001", "7003", "7005"]
    for rel in ("s10-train/tr1/gemma_qlora", "s10-train/tr2/gemma_qlora", "s10-eval/ev1/inference"):
        assert json.loads((char / rel / "lease.json").read_text("utf-8"))["status"] == "DESTROYED"
    assert cleanup_s10t(ctx, CID) == []
