"""Gemma 4 31B QLoRA 임대 GPU 학습 (LLD §8.9, D-0044·D-0077).

기본 설정은 실제로 결과를 낸 머스크 N3b 학습(2026-10-30)과 같다:
unsloth/gemma-4-31B-it-unsloth-bnb-4bit revision 8e256fc6d630…, gemma-4-thinking 템플릿,
QLoRA r16/α32, dropout 0, LR 5e-5
constant_with_warmup(5%), adamw_8bit, 배치 1×누적 4, 최대 4,096토큰, seed 3407, 2 epoch,
0.5 epoch마다 체크포인트, assistant 답변만 손실. 학습 뒤 같은 GPU에서 체크포인트별 첫 답변을 만들고
(선별), 공장이 회수해 생성 결과로 체크포인트를 고른다. 검증 손실은 기록만 한다.

GPU는 두 방식이다. ssh_host(또는 테스트의 remote_host)가 있으면 그 호스트를 쓰고, 없으면 Vast에서
한 대를 빌려(lease.json) 회수 뒤 삭제한다. 완료는 원격 complete.json·screen-complete.json으로만
판정하고, 회수한 파일의 해시를 확인한 뒤에만 원격 폴더와 GPU를 지운다.
"""

from __future__ import annotations

import hashlib
import json
import math
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.contracts.training import (
    Checkpoint,
    CostEstimate,
    ModelBinding,
    TrainingRun,
    Transfer,
)
from character_factory_poc.providers.training.errors import (
    RemoteHostError,
    TrainingIntegrityError,
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.providers.training.hosts import RemoteHost, VastRemoteHost
from character_factory_poc.providers.training.port import TrainRequest, resolve_dataset_files
from character_factory_poc.providers.training.screening import (
    build_screen_tasks,
    generations,
    tasks_text,
)
from character_factory_poc.providers.training.settings import as_float, as_int, as_str
from character_factory_poc.providers.training.vast import VastLease, VastSettings

N3B_VERSIONS = {
    "unsloth": "2026.10.3",
    "unsloth_zoo": "2026.10.3",
    "torch": "2.10.0+cu128",
    "transformers": "5.5.0",
    "trl": "0.23.1",
    "peft": "0.18.1",
    "datasets": "4.3.0",
    "bitsandbytes": "0.50.2",
}
REMOTE_SCRIPTS = ("train_qlora.py", "screen_qlora.py", "serve_qlora.py")
# guard 마감에 더하는 회수 여유(초). 학습 벽시계 상한 + GPU 준비 대기 상한 + 이 값.
GUARD_COLLECT_MARGIN_S = 7200.0
# 원격 학습·선별 프로세스. 대괄호 패턴은 이 패턴을 담은 셸 자신과는 맞지 않는다.
REMOTE_PROCESS_PATTERN = "[t]rain_qlora[.]py|[s]creen_qlora[.]py"


def kill_command(job: str, *, dedicated: bool) -> str:
    """원격 학습을 끄는 셸 명령.

    pid.txt는 nohup timeout의 PID다. GNU timeout은 자기 프로세스 그룹을 만들므로 그 그룹(job.sh와
    python)을 끈다. 임대 GPU(dedicated)는 다른 작업이 없으니 스크립트 이름으로도 한 번 더 끈다.
    작업 폴더 경로로 pkill -f를 하면 명령을 실행한 셸 자신이 먼저 맞아 죽으므로 쓰지 않는다.
    """
    pid_file = shlex.quote(f"{job}/pid.txt")
    pattern = shlex.quote(REMOTE_PROCESS_PATTERN)
    steps = [
        f"pid=$(tr -dc 0-9 2>/dev/null < {pid_file})",
        'if [ -n "$pid" ]; then pkill -TERM -g "$pid"; kill -TERM "$pid" 2>/dev/null; fi',
    ]
    if dedicated:
        steps.append(f"pkill -TERM -f {pattern}")
    steps += ["sleep 5", 'if [ -n "$pid" ]; then pkill -KILL -g "$pid"; fi']
    if dedicated:
        steps.append(f"pkill -KILL -f {pattern}")
    steps.append("true")
    return "; ".join(steps)


def _seconds_since(raw: Any) -> float:
    if not isinstance(raw, str):
        return 0.0
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - at).total_seconds())


def _floats(
    extra: dict[str, Any], keys: tuple[str, ...], default: list[float]
) -> tuple[float, ...]:
    for key in keys:
        raw = extra.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = [v for v in raw.split(",") if v.strip()]
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{key}는 숫자 목록이어야 한다")
        return tuple(sorted({float(v) for v in raw}))
    return tuple(default)


@dataclass(frozen=True)
class GemmaSettings:
    base_model: str = "unsloth/gemma-4-31B-it-unsloth-bnb-4bit"
    revision: str = "8e256fc6d63003fc0ca8c91b976e6dcc38433385"
    chat_template: str = "gemma-4-thinking"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    learning_rate: float = 5e-5
    lr_scheduler: str = "constant_with_warmup"
    warmup_ratio: float = 0.05
    optim: str = "adamw_8bit"
    weight_decay: float = 0.001
    batch_size: int = 1
    grad_accum: int = 4
    max_seq_length: int = 4096
    seed: int = 3407
    epochs: float = 2.0
    checkpoint_epochs: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0)
    expected_versions: dict[str, str] = field(default_factory=lambda: dict(N3B_VERSIONS))
    allow_version_drift: bool = False
    # QLoRA 품질 운영 규격(2026-11-02) §5 개발 비교: 단발 24 + 6턴 장면 2 = 조건당 36출력.
    # 같은 짧은 프롬프트의 기반 모델(base)을 함께 생성해 학습 없이도 되는지 본다.
    screen_single: int = 24
    screen_multi: int = 2
    screen_turns: int = 6
    screen_max_new_tokens: int = 512
    screen_include_base: bool = True
    screen_seconds: float = 12.0
    step_seconds: float = 8.7
    hourly_rate_usd: float = 0.90
    prep_overhead_seconds: float = 900.0
    max_gpu_hours: float = 8.0
    max_cost_usd: float = 20.0
    chunk_bytes: int = 8 * 1024 * 1024
    remote_root: str = "/workspace/cfp"
    remote_python: str = "python"

    @classmethod
    def from_extra(cls, extra: dict[str, Any], model: str = "") -> GemmaSettings:
        lease = "remote_host" not in extra and not extra.get("ssh_host")
        versions = extra.get("expected_versions")
        return cls(
            base_model=model or as_str(extra, ("base_model", "baseModel"), cls.base_model),
            revision=as_str(extra, ("revision",), cls.revision),
            chat_template=as_str(extra, ("chat_template",), cls.chat_template),
            lora_r=as_int(extra, ("lora_r", "loraR"), 16, minimum=1),
            lora_alpha=as_int(extra, ("lora_alpha", "loraAlpha"), 32, minimum=1),
            lora_dropout=as_float(extra, ("lora_dropout", "loraDropout"), 0.0, minimum=0.0),
            learning_rate=as_float(extra, ("learning_rate", "lr"), 5e-5, minimum=0.0),
            lr_scheduler=as_str(extra, ("lr_scheduler",), cls.lr_scheduler),
            warmup_ratio=as_float(extra, ("warmup_ratio",), 0.05, minimum=0.0),
            optim=as_str(extra, ("optim",), cls.optim),
            weight_decay=as_float(extra, ("weight_decay",), 0.001, minimum=0.0),
            batch_size=as_int(extra, ("batch_size",), 1, minimum=1),
            grad_accum=as_int(extra, ("grad_accum",), 4, minimum=1),
            max_seq_length=as_int(extra, ("max_seq_length",), 4096, minimum=1),
            seed=as_int(extra, ("seed",), 3407),
            epochs=as_float(extra, ("epochs", "epoch_count"), 2.0, minimum=0.1),
            checkpoint_epochs=_floats(
                extra, ("checkpoint_epochs", "save_epochs", "saveEpochs"), [0.5, 1.0, 1.5, 2.0]
            ),
            expected_versions=dict(versions) if isinstance(versions, dict) else dict(N3B_VERSIONS),
            allow_version_drift=bool(extra.get("allow_version_drift", False)),
            screen_single=as_int(extra, ("screen_single",), 24, minimum=0),
            screen_multi=as_int(extra, ("screen_multi",), 2, minimum=0),
            screen_turns=as_int(extra, ("screen_turns",), 6, minimum=1),
            screen_max_new_tokens=as_int(extra, ("screen_max_new_tokens",), 512, minimum=16),
            screen_include_base=bool(extra.get("screen_include_base", True)),
            screen_seconds=as_float(extra, ("screen_seconds",), 12.0, minimum=0.0),
            step_seconds=as_float(extra, ("step_seconds",), 8.7, minimum=0.0),
            hourly_rate_usd=as_float(extra, ("hourly_rate_usd",), 0.90, minimum=0.0),
            prep_overhead_seconds=as_float(extra, ("prep_overhead_seconds",), 900.0, minimum=0.0),
            max_gpu_hours=as_float(extra, ("max_gpu_hours",), 8.0, minimum=0.0),
            max_cost_usd=as_float(extra, ("max_cost_usd",), 20.0, minimum=0.0),
            chunk_bytes=as_int(extra, ("chunk_bytes",), 8 * 1024 * 1024, minimum=1),
            remote_root=as_str(extra, ("remote_root",), "/workspace/cfp"),
            remote_python=as_str(
                extra, ("remote_python",), "/venv/main/bin/python" if lease else "python"
            ),
        )

    @property
    def effective_batch(self) -> int:
        return self.batch_size * self.grad_accum

    def requested_config(self) -> dict[str, Any]:
        return {
            "baseModel": self.base_model,
            "baseModelRevision": self.revision,
            "chatTemplate": self.chat_template,
            "loraR": self.lora_r,
            "loraAlpha": self.lora_alpha,
            "loraDropout": self.lora_dropout,
            "learningRate": self.learning_rate,
            "lrScheduler": self.lr_scheduler,
            "warmupRatio": self.warmup_ratio,
            "optim": self.optim,
            "weightDecay": self.weight_decay,
            "batchSize": self.batch_size,
            "gradAccum": self.grad_accum,
            "maxSeqLength": self.max_seq_length,
            "seed": self.seed,
            "epochs": self.epochs,
            "checkpointEpochs": list(self.checkpoint_epochs),
            "expectedVersions": dict(self.expected_versions),
            "lossOn": "assistant",
            "selection": "generation",
        }


def _safe_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned or "run"


def _safe_rel(value: str) -> str:
    rel = PurePosixPath(value)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise TrainingIntegrityError(f"원격 완료 기록의 경로가 안전하지 않다: {value}")
    return rel.as_posix()


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _epoch(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return int(value) if float(value).is_integer() else float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sync_file(
    host: RemoteHost,
    local: Path,
    remote: str,
    chunk_bytes: int,
    transfer: Transfer,
) -> Transfer:
    """맞는 조각은 건너뛰고, 모든 조각과 합친 파일의 원격 해시를 확인한다."""
    digest = sha256_file(local)
    if digest != transfer.sha256:
        raise TrainingIntegrityError(
            f"전송할 파일의 sha256이 데이터셋 기록과 다르다: {transfer.path}"
        )
    if host.sha256(remote) == digest:
        return transfer.model_copy(update={"remoteSha256": digest})
    parts: list[str] = []
    with local.open("rb") as handle:
        index = 0
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            part = f"{remote}.part{index:06d}"
            want = hashlib.sha256(chunk).hexdigest()
            if host.sha256(part) != want:
                host.put_chunk(part, chunk)
            if host.sha256(part) != want:
                raise TrainingIntegrityError(f"조각의 원격 sha256이 다르다: {part}")
            parts.append(part)
            index += 1
    if not parts:
        host.put_chunk(remote, b"")
    else:
        host.concat(parts, remote)
    if host.sha256(remote) != digest:
        raise TrainingIntegrityError(f"합친 파일의 원격 sha256이 다르다: {remote}")
    return transfer.model_copy(update={"remoteSha256": digest})


def remote_script(name: str) -> str:
    return (Path(__file__).parent / "remote" / name).read_text("utf-8")


def ensure_scripts(host: RemoteHost, job_dir: str, names: tuple[str, ...] = REMOTE_SCRIPTS) -> None:
    for name in names:
        text = remote_script(name)
        remote = f"{job_dir}/{name}"
        if host.sha256(remote) != sha256_text(text):
            host.write_text(remote, text)
        if host.sha256(remote) != sha256_text(text):
            raise TrainingIntegrityError(f"원격 스크립트 {name}의 sha256이 다르다")


class GemmaQLoraProvider:
    name = "gemma_qlora"

    def __init__(self, cfg: ProviderConfig | None = None):
        self.cfg = cfg or ProviderConfig(adapter="gemma_qlora")
        self.settings = GemmaSettings.from_extra(self.cfg.extra, self.cfg.model)

    # ---- GPU 선택 -------------------------------------------------------------------------

    @property
    def uses_lease(self) -> bool:
        return "remote_host" not in self.cfg.extra and not self.cfg.extra.get("ssh_host")

    def lease(self, request: TrainRequest) -> VastLease:
        return VastLease.from_extra(request.plan_dir / "lease.json", self.cfg.extra)

    def _host(self, request: TrainRequest | None = None) -> RemoteHost:
        host = self.cfg.extra.get("remote_host")
        if host is not None:
            return host
        if self.cfg.extra.get("ssh_host"):
            return VastRemoteHost.from_config(self.cfg.extra)
        if request is None:
            raise RemoteHostError("임대 GPU 기록을 찾을 요청 정보가 없다")
        return self.lease(request).host()

    def _job_dir(self, request: TrainRequest) -> str:
        root = self.settings.remote_root.rstrip("/")
        run = request.run_ref or "run"
        parts = [request.dataset.characterId, request.dataset.datasetRev, run]
        return "/".join([root, *(_safe_segment(p) for p in parts)])

    # ---- 계획 -------------------------------------------------------------------------------

    def _check_budget(self, run: TrainingRun) -> None:
        if run.estimate.usd is None:
            raise TrainingLimitError("예상 비용이 없어 제출할 수 없다")
        limit = min(run.budgetUsd, self.settings.max_cost_usd)
        if run.estimate.usd > limit + 1e-9:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {limit:.4f} USD를 넘는다"
            )
        hours = run.estimate.gpuHours or 0.0
        if hours > self.settings.max_gpu_hours + 1e-9:
            raise TrainingLimitError(
                f"예상 GPU {hours:.2f}시간이 상한 {self.settings.max_gpu_hours:.2f}시간을 넘는다"
            )

    def _wall_hours(self, run: TrainingRun) -> float:
        """GPU 시간 상한과 비용 상한 가운데 더 빨리 닿는 쪽을 벽시계 상한으로 쓴다.

        임대 GPU는 만든 순간부터 비용이 들므로, 실제 원격 작업 시간 제한은 이 값에서 GPU 준비에
        쓴 시간을 뺀다(submit). guard 마감은 이 값 + 준비 대기 상한 + 회수 여유다(guard_limits).
        """
        cap = self.settings.max_gpu_hours
        rate = self.settings.hourly_rate_usd
        if rate > 0:
            cap = min(cap, min(run.budgetUsd, self.settings.max_cost_usd) / rate)
        return max(cap, 1.0 / 3600.0)

    def guard_limits(self, run: TrainingRun) -> dict[str, float]:
        """분리 감시(guard)가 쓸 마감·예산 값. 임대 모드에서만 쓴다."""
        vast = VastSettings.from_extra(self.cfg.extra)
        return {
            "wallSeconds": self._wall_hours(run) * 3600.0,
            "readyTimeoutS": vast.ready_timeout_s,
            "collectMarginS": as_float(
                self.cfg.extra, ("guard_collect_margin_s",), GUARD_COLLECT_MARGIN_S, minimum=0.0
            ),
            "budgetUsd": min(run.budgetUsd, self.settings.max_cost_usd),
            "reserveUsd": vast.credit_reserve_usd,
            "pollS": as_float(self.cfg.extra, ("guard_poll_s",), 60.0, minimum=0.0),
        }

    def screen_tasks(self, request: TrainRequest) -> list[dict[str, Any]]:
        s = self.settings
        if s.screen_single + s.screen_multi == 0:
            return []
        return build_screen_tasks(
            resolve_dataset_files(request),
            single=s.screen_single,
            multi=s.screen_multi,
            max_turns=s.screen_turns,
            seed=s.seed,
        )

    def plan(self, request: TrainRequest) -> TrainingRun:
        s = self.settings
        files = resolve_dataset_files(request)
        train_conversations = sum(f.conversations for f in files if f.split == "train")
        steps = math.ceil(train_conversations * s.epochs / s.effective_batch)
        tasks = self.screen_tasks(request)
        arms = len(s.checkpoint_epochs) + (1 if s.screen_include_base else 0)
        screen_gens = generations(tasks) * arms if tasks else 0
        screen_seconds = (screen_gens * s.screen_seconds + 420.0) if tasks else 0.0
        seconds = steps * s.step_seconds + s.prep_overhead_seconds + screen_seconds
        gpu_hours = seconds / 3600.0
        usd = round(gpu_hours * s.hourly_rate_usd, 4)
        basis = (
            f"Vast L40S 시간당 상한 ${s.hourly_rate_usd:.2f}, 스텝당 {s.step_seconds:g}초"
            f"(머스크 N3b 실측 236스텝 2,060초), 준비 {s.prep_overhead_seconds:g}초; "
            f"스텝 {steps} = ceil(대화 {train_conversations} × epoch {s.epochs:g} / "
            f"유효 배치 {s.effective_batch}); 선별 {screen_gens}회 × {s.screen_seconds:g}초 "
            f"(체크포인트 {arms}개 × 요청 {len(tasks)}개); 2026-11-02 확인"
        )
        return TrainingRun(
            characterId=request.dataset.characterId,
            datasetRev=request.dataset.datasetRev,
            datasetDigest=request.dataset.digest,
            provider="gemma_qlora",
            baseModel=s.base_model,
            baseModelRevision=s.revision,
            requestedConfig={**s.requested_config(), "screenGenerations": screen_gens},
            dryRun=True,
            estimate=CostEstimate(usd=usd, gpuHours=round(gpu_hours, 4), basis=basis),
            budgetUsd=request.budget_usd,
            status="PLANNED",
            transfers=[Transfer(path=f.relative, bytes=f.bytes, sha256=f.sha256) for f in files],
        )

    # ---- 제출 -------------------------------------------------------------------------------

    def _job_script(self, files, wall_seconds: int, screening: bool) -> str:
        """원격 job.sh 본문: 학습 → rc 0이면 선별 → job-exit.json.

        두 스크립트에 같은 마감 시각(--deadline-epoch)을 넘겨, 바깥 timeout이 죽이기 전에
        스스로 멈추고 complete.json·screen-complete.json을 남기게 한다.
        """
        s = self.settings
        py = s.remote_python
        train = [py, "train_qlora.py"]
        for item in files:
            train += ["--train" if item.split == "train" else "--validation", item.relative]
        train += [
            "--base-model",
            s.base_model,
            "--revision",
            s.revision,
            "--chat-template",
            s.chat_template,
            "--epochs",
            f"{s.epochs:g}",
            "--checkpoint-epochs",
            ",".join(f"{e:g}" for e in s.checkpoint_epochs),
            "--max-seq-length",
            str(s.max_seq_length),
            "--seed",
            str(s.seed),
            "--lora-r",
            str(s.lora_r),
            "--lora-alpha",
            str(s.lora_alpha),
            "--lora-dropout",
            str(s.lora_dropout),
            "--learning-rate",
            str(s.learning_rate),
            "--lr-scheduler",
            s.lr_scheduler,
            "--warmup-ratio",
            str(s.warmup_ratio),
            "--batch-size",
            str(s.batch_size),
            "--grad-accum",
            str(s.grad_accum),
            "--optim",
            s.optim,
            "--weight-decay",
            str(s.weight_decay),
            "--expected-versions",
            json.dumps(s.expected_versions, sort_keys=True),
        ]
        if s.allow_version_drift:
            train.append("--allow-version-drift")
        deadline = ' --deadline-epoch "$deadline"'
        script = [
            "export HF_HOME=/workspace/hf-cache HF_HUB_DISABLE_TELEMETRY=1 "
            "TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1 WANDB_DISABLED=true",
            f"deadline=$(( $(date +%s) + {int(wall_seconds)} ))",
            shlex.join(train) + deadline,
            "rc=$?",
            "src=skip",
        ]
        if screening:
            screen = [
                py,
                "screen_qlora.py",
                "--base-model",
                s.base_model,
                "--revision",
                s.revision,
                "--chat-template",
                s.chat_template,
                "--max-new-tokens",
                str(s.screen_max_new_tokens),
                "--expected-versions",
                json.dumps(s.expected_versions, sort_keys=True),
            ]
            if s.screen_include_base:
                screen.append("--include-base")
            script += ["if [ $rc -eq 0 ]; then " + shlex.join(screen) + deadline + "; src=$?; fi"]
        script.append('printf \'{"train":%s,"screen":"%s"}\\n\' "$rc" "$src" > job-exit.json')
        return "\n".join(script) + "\n"

    def _command(self, files, job_dir: str, wall_seconds: int, screening: bool) -> str:
        """job.sh를 쓰고 백그라운드로 띄운 뒤 PID만 출력한다.

        백그라운드로 보내는 것은 nohup 명령 하나뿐이다. 앞의 cd·printf까지 함께 보내면 그
        서브셸이 ssh 출력 파이프를 쥔 채 학습이 끝날 때까지 남아 ssh가 돌아오지 않는다.
        """
        body = self._job_script(files, wall_seconds, screening)
        return (
            f"cd {shlex.quote(job_dir)} && printf %s {shlex.quote(body)} > job.sh && "
            f"{{ nohup timeout {wall_seconds}s bash job.sh > train.log 2>&1 < /dev/null & "
            "echo $!; }"
        )

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        self._check_budget(run)
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        if run.status in {"SUBMITTED", "RUNNING"} and run.jobId:
            return run
        lease_info: dict[str, Any] = {}
        ready_spent = 0.0
        if self.uses_lease:
            lease = self.lease(request)
            lease.acquire(run.estimate.usd or 0.0)
            host = lease.wait_ready()
            ready_spent = _seconds_since(lease.data.get("createdAt"))
            lease_info = {
                "lease": "vast",
                "instanceId": lease.instance_id,
                "gpu": lease.data.get("gpu"),
                "dphTotal": lease.data.get("dphTotal"),
            }
        else:
            host = self._host(request)
        # GPU를 만든 뒤 준비에 쓴 시간만큼 원격 작업 시간을 줄여 전체 임대 시간을 상한 안에 둔다.
        wall_seconds = int(self._wall_hours(run) * 3600 - ready_spent)
        need = max(
            60.0, (run.estimate.gpuHours or 0.0) * 3600 - self.settings.prep_overhead_seconds
        )
        if wall_seconds < need:
            raise TrainingLimitError(
                f"GPU 준비에 {ready_spent / 60:.0f}분을 써서 남은 시간 {max(wall_seconds, 0)}초가 "
                f"예상 학습 시간 {need:.0f}초보다 짧다"
            )
        job_dir = run.jobId or self._job_dir(request)
        files = resolve_dataset_files(request)
        old = {t.path: t for t in run.transfers}
        transfers: list[Transfer] = []
        for item in files:
            transfer = old.get(item.relative)
            if transfer is None:
                transfer = Transfer(path=item.relative, bytes=item.bytes, sha256=item.sha256)
            transfers.append(
                _sync_file(
                    host,
                    item.path,
                    f"{job_dir}/{item.relative}",
                    self.settings.chunk_bytes,
                    transfer,
                )
            )
        ensure_scripts(host, job_dir)
        tasks = self.screen_tasks(request)
        if tasks:
            text = tasks_text(tasks)
            request.plan_dir.mkdir(parents=True, exist_ok=True)
            (request.plan_dir / "screen-requests.jsonl").write_text(text, "utf-8")
            host.write_text(f"{job_dir}/screen/requests.jsonl", text)
            if host.sha256(f"{job_dir}/screen/requests.jsonl") != sha256_text(text):
                raise TrainingIntegrityError("선별 요청 파일의 원격 sha256이 다르다")
        for transfer in transfers:
            if host.sha256(f"{job_dir}/{transfer.path}") != transfer.sha256:
                raise TrainingIntegrityError(f"원격 파일의 sha256이 다르다: {transfer.path}")
        started = {
            "startedAt": _now(),
            "maxWallHours": wall_seconds / 3600.0,
            "readyWaitSeconds": round(ready_spent, 1),
            "maxCostUsd": min(run.budgetUsd, self.settings.max_cost_usd),
            "hourlyRateUsd": self.settings.hourly_rate_usd,
            "datasetRev": run.datasetRev,
            "datasetDigest": run.datasetDigest,
            "screenTasks": len(tasks),
        }
        host.write_text(f"{job_dir}/started.json", json.dumps(started, ensure_ascii=False))
        pid = host.run(["bash", "-lc", self._command(files, job_dir, wall_seconds, bool(tasks))])
        host.write_text(f"{job_dir}/pid.txt", pid.strip() + "\n")
        return run.model_copy(
            update={
                "dryRun": False,
                "status": "SUBMITTED",
                "jobId": job_dir,
                "transfers": transfers,
                "appliedConfig": {
                    **run.requestedConfig,
                    **lease_info,
                    "screenTasks": len(tasks),
                    "submittedAt": started["startedAt"],
                    "maxWallSeconds": wall_seconds,
                    "readyWaitSeconds": started["readyWaitSeconds"],
                },
            }
        )

    # ---- 상태·회수 ---------------------------------------------------------------------------

    def _checkpoints(self, data: dict[str, Any]) -> list[Checkpoint]:
        out: list[Checkpoint] = []
        for raw in data.get("checkpoints") or []:
            checkpoint_id = str(raw.get("checkpointId") or raw.get("id") or "")
            if not checkpoint_id:
                raise TrainingIntegrityError("원격 complete.json의 체크포인트에 ID가 없다")
            ref = str(raw.get("ref") or checkpoint_id)
            loss = raw.get("validationLoss")
            out.append(
                Checkpoint(
                    checkpointId=checkpoint_id,
                    epoch=_epoch(raw.get("epoch")),
                    step=_int_or_none(raw.get("step")),
                    ref=ref,
                    validationLoss=float(loss) if isinstance(loss, int | float) else None,
                )
            )
        return out

    def _limit_reason(self, started: dict[str, Any]) -> str | None:
        raw = started.get("startedAt")
        if not isinstance(raw, str):
            return None
        try:
            at = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        hours = (datetime.now(UTC) - at).total_seconds() / 3600.0
        max_wall = float(started.get("maxWallHours", self.settings.max_gpu_hours))
        if hours > max_wall:
            return f"시간 상한 {max_wall:.2f}시간을 넘었다(경과 {hours:.2f}시간)"
        rate = float(started.get("hourlyRateUsd", self.settings.hourly_rate_usd))
        max_cost = float(started.get("maxCostUsd", self.settings.max_cost_usd))
        if hours * rate > max_cost:
            return f"비용 상한 {max_cost:.2f} USD를 넘었다(추정 {hours * rate:.2f} USD)"
        return None

    def _screen_state(self, host: RemoteHost, job: str) -> tuple[str, dict[str, Any] | None]:
        """선별 결과 상태: none(요청 없음)·pending·done·failed.

        선별 중 시간·비용 상한을 넘으면 바깥 timeout이 프로세스를 죽여 기록이 남지 않으므로
        상한 초과를 선별 실패로 본다. 학습 결과는 그대로 쓸 수 있다.
        """
        if host.sha256(f"{job}/screen/requests.jsonl") is None:
            return "none", None
        raw = host.read_text(f"{job}/screen-complete.json")
        if raw is not None:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TrainingIntegrityError("원격 screen-complete.json을 읽을 수 없다") from exc
            return ("done" if data.get("ok") else "failed"), data
        if host.read_text(f"{job}/job-exit.json") is not None:
            return "failed", {"ok": False, "error": "선별이 결과 없이 끝났다", "files": []}
        reason = self._limit_reason(self._started(host, job))
        if reason:
            self._kill(host, job)
            return "failed", {"ok": False, "error": f"선별 중 {reason}", "files": []}
        return "pending", None

    def _started(self, host: RemoteHost, job: str) -> dict[str, Any]:
        raw = host.read_text(f"{job}/started.json")
        if raw is None:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _kill(self, host: RemoteHost, job: str) -> None:
        try:
            host.run(["bash", "-lc", kill_command(job, dedicated=self.uses_lease)])
        except RemoteHostError:
            pass

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if not run.jobId:
            raise TrainingNotReadyError("학습 작업이 아직 제출되지 않았다")
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        host = self._host(request)
        job = run.jobId
        complete = host.read_text(f"{job}/complete.json")
        if complete is not None:
            try:
                data = json.loads(complete)
            except json.JSONDecodeError as exc:
                raise TrainingIntegrityError("원격 complete.json을 읽을 수 없다") from exc
            if data.get("ok") is False:
                reason = str(data.get("error") or "원격 학습이 실패했다")
                return run.model_copy(
                    update={
                        "status": "FAILED",
                        "appliedConfig": {**run.appliedConfig, "error": reason},
                    }
                )
            screen, screen_data = self._screen_state(host, job)
            if screen == "pending":
                return run.model_copy(update={"status": "RUNNING"})
            checkpoints = self._checkpoints(data)
            applied = dict(run.appliedConfig)
            if isinstance(data.get("appliedConfig"), dict):
                applied.update(data["appliedConfig"])
            applied["completedAt"] = data.get("finishedAt", "")
            applied["screen"] = screen
            if screen == "failed" and screen_data:
                applied["screenError"] = str(screen_data.get("error") or "")[:500]
            return run.model_copy(
                update={"status": "SUCCEEDED", "checkpoints": checkpoints, "appliedConfig": applied}
            )
        reason = self._limit_reason(self._started(host, job))
        if reason:
            self._kill(host, job)
            return run.model_copy(
                update={
                    "status": "FAILED",
                    "appliedConfig": {**run.appliedConfig, "error": reason},
                }
            )
        if host.read_text(f"{job}/job-exit.json") is not None:
            return run.model_copy(
                update={
                    "status": "FAILED",
                    "appliedConfig": {**run.appliedConfig, "error": "학습이 완료 기록 없이 끝났다"},
                }
            )
        log = host.read_text(f"{job}/train.log")
        return run.model_copy(update={"status": "RUNNING" if log is not None else "SUBMITTED"})

    def _fetch(self, host: RemoteHost, job: str, artifact_dir: Path, items: list[dict]) -> None:
        for item in items:
            rel = _safe_rel(str(item.get("path") or ""))
            dest = (artifact_dir / rel).resolve()
            if not dest.is_relative_to(artifact_dir):
                raise TrainingIntegrityError(f"회수 경로가 폴더 밖을 가리킨다: {rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            host.fetch(f"{job}/{rel}", dest)
            if sha256_file(dest) != str(item.get("sha256") or ""):
                raise TrainingIntegrityError(f"회수한 파일의 sha256이 다르다: {rel}")
            expected_bytes = item.get("bytes")
            if isinstance(expected_bytes, int) and dest.stat().st_size != expected_bytes:
                raise TrainingIntegrityError(f"회수한 파일의 바이트 수가 다르다: {rel}")

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        current = self.status(run, request)
        if current.status != "SUCCEEDED":
            raise TrainingNotReadyError(f"학습 작업이 아직 끝나지 않았다: {current.status}")
        host = self._host(request)
        job = current.jobId
        if not job:
            raise TrainingNotReadyError("학습 작업 ID가 없다")
        raw = host.read_text(f"{job}/complete.json")
        if raw is None:
            raise TrainingNotReadyError("원격 complete.json이 없다")
        data = json.loads(raw)
        files = list(data.get("files") or [])
        if not files:
            raise TrainingIntegrityError("원격 complete.json에 회수할 파일이 없다")
        checkpoints = self._checkpoints(data)
        raw_ref = data.get("modelBindingRef") or (checkpoints[-1].ref if checkpoints else "")
        if not raw_ref:
            raise TrainingIntegrityError("원격 complete.json에 체크포인트도 modelBindingRef도 없다")
        binding_ref = _safe_rel(str(raw_ref))
        screen_raw = host.read_text(f"{job}/screen-complete.json")
        if screen_raw is not None:
            files += list(json.loads(screen_raw).get("files") or [])
        artifact_dir = request.artifact_dir.resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._fetch(host, job, artifact_dir, files)
        for name in ("complete.json", "screen-complete.json", "train.log", "job-exit.json"):
            text = host.read_text(f"{job}/{name}")
            if text is not None:
                (artifact_dir / "remote").mkdir(exist_ok=True)
                (artifact_dir / "remote" / name).write_text(text, "utf-8")
        host.delete(job)
        checkpoint_id = checkpoints[-1].checkpointId if checkpoints else "final"
        applied = dict(current.appliedConfig)
        if isinstance(data.get("appliedConfig"), dict):
            applied.update(data["appliedConfig"])
        applied["remoteDeleted"] = True
        if self.uses_lease:
            self.release(request)
            applied["leaseDestroyed"] = True
        return current.model_copy(
            update={
                "checkpoints": checkpoints,
                "appliedConfig": applied,
                "modelBinding": ModelBinding(
                    provider="gemma_qlora",
                    ref=str((artifact_dir / binding_ref).resolve()),
                    checkpointId=checkpoint_id,
                ),
            }
        )

    def abort(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        """실패·중단 때 원격 학습을 끄고 로그를 가능한 만큼 남긴 뒤 임대 GPU를 지운다.

        ssh_host 모드는 GPU를 지우지 않으므로 원격 학습을 끄지 않으면 계속 돈다.
        """
        try:
            host = self._host(request)
            if run.jobId:
                self._kill(host, run.jobId)
                folder = request.artifact_dir / "remote"
                folder.mkdir(parents=True, exist_ok=True)
                for name in (
                    "complete.json",
                    "screen-complete.json",
                    "job-exit.json",
                    "train.log",
                    "state.json",
                    "screen-state.json",
                ):
                    text = host.read_text(f"{run.jobId}/{name}")
                    if text is not None:
                        (folder / name).write_text(text[-200_000:], "utf-8")
        except RemoteHostError:
            pass
        if self.uses_lease:
            self.release(request)
        return run

    def release(self, request: TrainRequest) -> None:
        lease = self.lease(request)
        if lease.instance_id:
            lease.destroy()
        elif lease.status in {"CREATING", "UNRESOLVED", "AMBIGUOUS", "DESTROY_UNVERIFIED"}:
            lease.destroy_by_label()
