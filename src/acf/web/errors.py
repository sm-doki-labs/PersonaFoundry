"""워크숍 API 오류 (PoC 계획서 §6). 상태 코드와 한국어 메시지를 함께 들고 다닌다."""

from __future__ import annotations


class WebError(Exception):
    """화면에 그대로 보여 줄 수 있는 API 오류."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:  # pragma: no cover - 로그용
        return f"{self.status} {self.detail}"
