"""공식 API 호출 경로의 모델 계열·공식 모델 ID·과금 구분(명세 §24.2, LLD §22.2).

이 모듈은 환경변수 이름만 다룬다. 키 값은 읽지 않으며, 키가 비었는지는 호출 직전
`Context.task_model`이 확인한다.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

FAMILY_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
    },
}
RELAY_PREFIX = "google-antigravity/"
API_HOSTS = frozenset({"api.openai.com", "generativelanguage.googleapis.com", "api.anthropic.com"})
RELAY_HOSTS = frozenset({"127.0.0.1", "localhost"})
ENV_NAME_RE = re.compile(r"[A-Z_][A-Z0-9_]*")
ENV_NAME_MAX = 64
SECRET_PREFIXES = ("sk-", "AIza")


def validate_env_name(name: str) -> None:
    """인증 환경변수 이름만 받는다. 키 값처럼 보이면 거절하고, 오류 문구에 값을 넣지 않는다."""
    if (
        not isinstance(name, str)
        or name.startswith(SECRET_PREFIXES)
        or len(name) > ENV_NAME_MAX
        or not ENV_NAME_RE.fullmatch(name)
    ):
        raise ValueError(
            "api_key_env에는 인증 값 대신 환경변수 이름(대문자·숫자·밑줄, 64자 이하)을 쓴다"
        )


def family_of(model: str) -> str | None:
    """덱 모델 ID로 계열을 정한다. 정할 수 없으면 None이다."""
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith(("gemini-", RELAY_PREFIX + "gemini-")):
        return "gemini"
    return None


def official_model_id(model: str) -> str:
    """중계 전용 접두사를 빼서 공식 API가 받는 모델 ID로 바꾼다."""
    return model.removeprefix(RELAY_PREFIX)


def billing_for(cfg, route: str | None = None) -> dict:
    """경로와 주소 호스트로 과금 구분을 정한다. 키 값은 읽지 않는다.

    test 경로는 주소와 무관하게 미확인, opencodex 경로는 중계 환산이다(명세 §24.2).
    api 경로와 덱 밖 공급자는 호스트 규칙을 따른다.
    """
    fake = cfg.adapter == "fake"
    if fake:
        kind = "none"
    elif route == "test":
        kind = "unverified"
    elif route == "opencodex":
        kind = "relay_equivalent"
    else:
        host = (urlsplit(cfg.base_url).hostname or "").lower()
        if host in API_HOSTS or host.endswith("aiplatform.googleapis.com"):
            kind = "api_billed"
        elif host in RELAY_HOSTS:
            kind = "relay_equivalent"
        else:
            kind = "unverified"
    return {
        "route": route or ("fake" if fake else "direct"),
        "family": family_of(cfg.model or ""),
        "class": kind,
    }
