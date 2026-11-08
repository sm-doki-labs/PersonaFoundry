"""가짜 학습 공급자: 네트워크 없이 plan → submit → collect를 끝까지 돈다(D-0044).

기본은 제출하자마자 끝난다. 화면 확인용으로 두 값을 설정할 수 있다(D-0130).

- run_polls: 상태 확인을 이만큼 받을 때까지 '학습 중'으로 남는다. 확인마다 진행 스텝이 늘어난다.
- collect_failures: 결과 받기를 이만큼 실패한다(결과 받기 실패·다시 받아 오기 흐름).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.providers.training.port import TrainRequest, resolve_dataset_files
from character_factory_poc.providers.training.settings import as_int

FAKE_STEPS_PER_EPOCH = 100
COLLECT_COUNTER = "fake-collect-failures.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class FakeTrainingProvider:
    name = "fake"

    def __init__(self, cfg: ProviderConfig | None = None):
        self.cfg = cfg or ProviderConfig(adapter="fake")

    def _epochs(self) -> int:
        return as_int(self.cfg.extra, ("epochs", "epoch_count"), 3, minimum=1)

    def _polls(self) -> int:
        return as_int(self.cfg.extra, ("run_polls",), 0, minimum=0)

    def plan(self, request: TrainRequest) -> TrainingRun:
        files = resolve_dataset_files(request)
        return TrainingRun(
            characterId=request.dataset.characterId,
            datasetRev=request.dataset.datasetRev,
            datasetDigest=request.dataset.digest,
            provider="fake",
            baseModel=self.cfg.model or "fake-base",
            requestedConfig={"epochs": self._epochs(), "offline": True},
            dryRun=True,
            estimate=CostEstimate(usd=0.0, gpuHours=0.0, basis="가짜 공급자(오프라인, 비용 0)"),
            budgetUsd=request.budget_usd,
            status="PLANNED",
            transfers=[Transfer(path=f.relative, bytes=f.bytes, sha256=f.sha256) for f in files],
        )

    def _collect_failures(self) -> int:
        return as_int(self.cfg.extra, ("collect_failures",), 0, minimum=0)

    def _finished(self, run: TrainingRun, bind: bool = True) -> TrainingRun:
        job_id = run.jobId or f"fake-{run.characterId}-{run.datasetRev}"
        checkpoints = [
            Checkpoint(
                checkpointId=f"fake-epoch-{e}",
                epoch=e,
                step=e * FAKE_STEPS_PER_EPOCH,
                ref=f"fake://{job_id}/{e}",
            )
            for e in range(1, self._epochs() + 1)
        ]
        binding = ModelBinding(
            provider="fake",
            ref=f"fake://{job_id}/adapter",
            checkpointId=checkpoints[-1].checkpointId,
        )
        applied = {k: v for k, v in run.appliedConfig.items() if k != "fakePollsLeft"}
        applied.setdefault("completedAt", _now())
        total = self._epochs() * FAKE_STEPS_PER_EPOCH
        applied["progress"] = {"phase": "done", "step": total, "maxSteps": total}
        return run.model_copy(
            update={
                "dryRun": False,
                "status": "SUCCEEDED",
                "jobId": job_id,
                "appliedConfig": applied,
                "checkpoints": checkpoints,
                # 결과 받기 실패를 흉내 낼 때는 collect 전까지 binding을 비운다(실제와 같다).
                "modelBinding": binding if bind else None,
            }
        )

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if run.estimate.usd is not None and run.estimate.usd > run.budgetUsd:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {run.budgetUsd:.4f} USD를 넘는다"
            )
        job_id = f"fake-{run.characterId}-{run.datasetRev}"
        applied = {**run.requestedConfig, "submittedAt": _now()}
        polls = self._polls()
        submitted = run.model_copy(update={"dryRun": False, "jobId": job_id})
        if polls <= 0:
            return self._finished(submitted.model_copy(update={"appliedConfig": applied}))
        total = self._epochs() * FAKE_STEPS_PER_EPOCH
        applied["fakePollsLeft"] = polls
        applied["progress"] = {"phase": "training", "step": 0, "maxSteps": total}
        return submitted.model_copy(update={"status": "SUBMITTED", "appliedConfig": applied})

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if not run.jobId:
            raise TrainingNotReadyError("가짜 학습 작업이 아직 제출되지 않았다")
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        left = int(run.appliedConfig.get("fakePollsLeft", 0) or 0)
        if left <= 0:
            return self._finished(run, bind=not self._collect_failures())
        polls = max(self._polls(), left)
        total = self._epochs() * FAKE_STEPS_PER_EPOCH
        step = round(total * (polls - left + 1) / (polls + 1))
        applied = {
            **run.appliedConfig,
            "fakePollsLeft": left - 1,
            "progress": {"phase": "training", "step": step, "maxSteps": total},
        }
        return run.model_copy(update={"status": "RUNNING", "appliedConfig": applied})

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        current = self.status(run, request)
        if current.status != "SUCCEEDED":
            raise TrainingNotReadyError(f"가짜 학습 작업이 끝나지 않았다: {current.status}")
        wanted = self._collect_failures()
        if wanted:
            counter = request.plan_dir / COLLECT_COUNTER
            done = json.loads(counter.read_text("utf-8")) if counter.is_file() else 0
            if done < wanted:
                counter.parent.mkdir(parents=True, exist_ok=True)
                counter.write_text(json.dumps(done + 1), "utf-8")
                raise RemoteHostError("가짜 공급자: 결과를 받아 오다 연결이 끊겼다(시험용)")
        return current if current.modelBinding is not None else self._finished(current)

    def abort(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        """중단: 빌린 것이 없으니 기록만 취소로 바꾼다(drive가 저장한다)."""
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        return run.model_copy(update={"status": "CANCELLED"})
