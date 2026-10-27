"""TrainingProvider 포트와 요청 dataclass (LLD §5.15·§8.9, D-0044).

학습은 두 환경(Gemma 4 31B QLoRA 임대 GPU, Vertex Gemini 튜닝)이고 PoC는 plan(dry run)까지다.
`submit`은 원격 작업을 만들고, `status`는 공급자 상태를 읽고, `collect`는 결과를 회수한다.
모든 반환은 `training-run-v2`(src/acf/contracts/training.py)이며 상태 파일만 바꾼 사본을 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from acf.common.canonical import sha256_file
from acf.contracts.dataset import DatasetRev
from acf.contracts.training import TrainingProvider as ProviderName
from acf.contracts.training import TrainingRun
from acf.providers.training.errors import TrainingIntegrityError

TRAIN_SPLITS = ("train", "validation_base", "validation_augmented")
ALL_PROVIDERS: tuple[str, ...] = ("gemma_qlora", "vertex_gemini", "fake")


@dataclass(frozen=True)
class TrainRequest:
    """한 학습 실행에 필요한 로컬 경로와 상한. 공급자는 이 밖의 파일을 읽지 않는다."""

    dataset: DatasetRev
    dataset_dir: Path
    budget_usd: float
    plan_dir: Path
    artifact_dir: Path
    run_ref: str = ""


@dataclass(frozen=True)
class DatasetFile:
    split: str
    path: Path
    relative: str
    bytes: int
    sha256: str
    conversations: int


def resolve_dataset_files(
    request: TrainRequest, splits: tuple[str, ...] = TRAIN_SPLITS
) -> list[DatasetFile]:
    """dataset-rev-v2의 파일을 로컬에서 다시 재고, 기록과 다르면 시작하지 않는다."""
    root = request.dataset_dir.resolve()
    out: list[DatasetFile] = []
    for item in request.dataset.files:
        if item.split not in splits:
            continue
        local = (root / item.path).resolve()
        if not local.is_relative_to(root):
            raise TrainingIntegrityError(f"데이터셋 경로가 폴더 밖을 가리킨다: {item.path}")
        if not local.is_file():
            raise TrainingIntegrityError(f"데이터셋 파일이 없다: {item.path}")
        digest = sha256_file(local)
        if digest != item.sha256:
            raise TrainingIntegrityError(f"데이터셋 파일의 sha256이 다르다: {item.path}")
        out.append(
            DatasetFile(
                split=item.split,
                path=local,
                relative=item.path,
                bytes=local.stat().st_size,
                sha256=digest,
                conversations=item.conversations,
            )
        )
    if not out:
        raise TrainingIntegrityError("학습·검증 파일이 dataset-rev-v2에 없다")
    return out


def provider_name(value: str) -> ProviderName:
    if value not in ALL_PROVIDERS:
        raise ValueError(f"알 수 없는 학습 공급자: {value}")
    return value  # type: ignore[return-value]


@runtime_checkable
class TrainingProvider(Protocol):
    """학습 포트. `plan`만 dry run이고 나머지는 실제 원격 작업을 다룬다."""

    name: ProviderName

    def plan(self, request: TrainRequest) -> TrainingRun: ...

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun: ...

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun: ...

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun: ...
