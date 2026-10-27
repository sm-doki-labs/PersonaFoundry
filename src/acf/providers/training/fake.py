"""가짜 학습 공급자: 네트워크 없이 plan → submit → collect를 끝까지 돈다(D-0044)."""

from __future__ import annotations

from acf.common.config import ProviderConfig
from acf.contracts.training import Checkpoint, CostEstimate, ModelBinding, TrainingRun, Transfer
from acf.providers.training.errors import TrainingLimitError, TrainingNotReadyError
from acf.providers.training.port import TrainRequest, resolve_dataset_files
from acf.providers.training.settings import as_int


class FakeTrainingProvider:
    name = "fake"

    def __init__(self, cfg: ProviderConfig | None = None):
        self.cfg = cfg or ProviderConfig(adapter="fake")

    def _epochs(self) -> int:
        return as_int(self.cfg.extra, ("epochs", "epoch_count"), 3, minimum=1)

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

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if run.estimate.usd is not None and run.estimate.usd > run.budgetUsd:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {run.budgetUsd:.4f} USD를 넘는다"
            )
        job_id = f"fake-{run.characterId}-{run.datasetRev}"
        checkpoints = [
            Checkpoint(
                checkpointId=f"fake-epoch-{e}", epoch=e, step=e * 100, ref=f"fake://{job_id}/{e}"
            )
            for e in range(1, self._epochs() + 1)
        ]
        binding = ModelBinding(
            provider="fake",
            ref=f"fake://{job_id}/adapter",
            checkpointId=checkpoints[-1].checkpointId,
        )
        return run.model_copy(
            update={
                "dryRun": False,
                "status": "SUCCEEDED",
                "jobId": job_id,
                "appliedConfig": dict(run.requestedConfig),
                "checkpoints": checkpoints,
                "modelBinding": binding,
            }
        )

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if not run.jobId:
            raise TrainingNotReadyError("가짜 학습 작업이 아직 제출되지 않았다")
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        return self.submit(run, request)

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        current = self.status(run, request)
        if current.status != "SUCCEEDED" or current.modelBinding is None:
            raise TrainingNotReadyError(f"가짜 학습 작업이 끝나지 않았다: {current.status}")
        return current
