"""학습 공급자 오류 (LLD §8.9, §10)."""

from __future__ import annotations

from acf.common.errors import FactoryError


class TrainingError(FactoryError):
    """학습 공급자 설정·호출·응답이 계약과 맞지 않는다."""


class TrainingLimitError(TrainingError):
    """시간·비용 상한을 넘어 제출·회수를 거절한다."""


class TrainingNotReadyError(TrainingError):
    """원격 작업이 아직 끝나지 않아 결과를 회수할 수 없다."""


class TrainingIntegrityError(TrainingError):
    """로컬·원격 파일의 바이트나 sha256이 기록과 다르다."""


class RemoteHostError(TrainingError):
    """임대 GPU 원격 호스트 명령이 실패했다."""
