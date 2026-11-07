"""공장 전역 예외 (LLD §10)."""


class FactoryError(Exception):
    """사용자에게 보여 줄 수 있는 오류의 기반."""


class ImmutableWriteError(FactoryError):
    pass


class ValidationFailed(FactoryError):
    def __init__(self, contract: str, problems: list[str]):
        self.contract = contract
        self.problems = problems
        super().__init__(f"{contract}: " + "; ".join(problems))


class GateNotApprovedError(FactoryError):
    pass


class StateTransitionError(FactoryError):
    pass


class AgentFormatError(FactoryError):
    pass


class CheckFailed(FactoryError):
    def __init__(self, stage: str, problems: list[str]):
        self.stage = stage
        self.problems = problems
        super().__init__(f"{stage} check failed: " + "; ".join(problems))


class BudgetExceeded(FactoryError):
    pass


class TaintedOutputError(FactoryError):
    pass


class NameLeakError(FactoryError):
    """순위 목록의 이름이 다음 단계 산출물·이미지 프롬프트에 들어갔다 (FR-35)."""


class NeedsInputError(FactoryError):
    """사람의 입력(예: 기획 씨앗)이 있어야 진행할 수 있다. 오케스트레이터는 이 갈래만 멈춘다."""


class ImageGenerationError(FactoryError):
    """이미지 공급자가 이미지를 돌려주지 않았다."""


class VideoGenerationError(FactoryError):
    """영상 공급자가 영상을 돌려주지 않았다."""


class VideoTimeoutError(VideoGenerationError):
    """원격 작업이 시간 안에 끝나지 않았다. job_id로 다음 실행에서 이어 받는다."""

    def __init__(self, job_id: str, message: str):
        self.job_id = job_id
        super().__init__(message)


class ProviderRequestError(FactoryError, RuntimeError):
    """공급자가 요청을 거절했다(429·5xx를 뺀 비정상 응답, 명세 §24.3). 재시도하지 않는다.

    provider_message는 공급자 오류 문구의 앞 500자다. 키 값 가림은 호출한 어댑터가 먼저 한다.
    RuntimeError도 상속하므로 기존 공급자 실패를 RuntimeError로 잡던 곳은 그대로 동작한다.
    """

    def __init__(self, status: int, provider_message: str):
        self.status = status
        self.provider_message = (provider_message or "")[:500]
        super().__init__(f"공급자 요청 오류 {status}: {self.provider_message}")


class ProviderTransportError(FactoryError, RuntimeError):
    """응답을 끝까지 받지 못했다: 연결 끊김·시간 초과·429·5xx·깨진 스트림(D-0084).

    공급자가 이미 생성·청구했을 수 있으므로 예산 예약을 풀지 않는다. kind는
    disconnect·timeout·rate_limit·server_error·malformed_stream 가운데 하나다.
    """

    def __init__(self, kind: str, detail: str, status: int | None = None):
        self.kind = kind
        self.status = status
        super().__init__(f"공급자 호출 실패({kind}): {(detail or '')[:300]}")
