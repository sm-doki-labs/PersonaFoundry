"""내보내기 설정 (`[export]` 절, LLD §8.11).

`cfp/common/config.py`는 `[stages]`·`[providers]` 등 정해진 절만 읽는다. `[export]`는 이
모듈이 `factory.toml`에서 직접 읽는다(설정 로더 확장은 통합 담당 몫으로 남긴다).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from character_factory_poc.pipeline.context import Context

# 대상 저장소의 적재 스키마. 실제 head와 다르면 적재 전에 멈춘다(LLD §8.11).
# 모티브 표시 칸(disclosure_label·call_start_label)은 api-svc 194부터, 캐릭터별 대화 모델은
# chat-svc codex/per-character-dialogue-model 브랜치(0030 위)부터 받는다(D-0142).
API_SVC_HEAD = "194_twin_demo_labels"
CHAT_SVC_HEAD = "0030_projection_gap_backoff"

DEFAULT_ADMIN_URL_ENV = "CFP_PG_ADMIN_URL"


@dataclass(frozen=True)
class ExportSettings:
    api_svc_repo: Path
    chat_svc_repo: Path
    admin_url_env: str = DEFAULT_ADMIN_URL_ENV
    sql_python: str = ""
    timeout_s: float = 900.0
    default_voice_id: str | None = None


def _table(payload: dict, name: str) -> dict:
    value = payload.get(name)
    return value if isinstance(value, dict) else {}


def _path(value: object, default: Path) -> Path:
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return default


def load_export_settings(ctx: Context) -> ExportSettings:
    """factory.toml의 `[export.doki_app]`·`[export.verify]`와 환경변수를 합친다."""
    data: dict = {}
    source = ctx.config.source_path
    if source is not None and Path(source).is_file():
        data = tomllib.loads(Path(source).read_text(encoding="utf-8"))
    export = _table(data, "export")
    doki = _table(export, "doki_app")
    verify = _table(export, "verify")
    api_default = Path(os.environ.get("CFP_API_SVC_REPO", "~/projects/api-svc"))
    chat_default = Path(os.environ.get("CFP_CHAT_SVC_REPO", "~/projects/relationship-quest-chat"))
    return ExportSettings(
        api_svc_repo=_path(doki.get("api_svc_repo"), api_default.expanduser()),
        chat_svc_repo=_path(doki.get("chat_svc_repo"), chat_default.expanduser()),
        admin_url_env=str(verify.get("admin_url_env") or DEFAULT_ADMIN_URL_ENV),
        sql_python=str(verify.get("sql_python") or ""),
        default_voice_id=doki.get("default_voice_id") or os.environ.get("CFP_DEFAULT_VOICE_ID"),
        timeout_s=float(verify.get("timeout_s", 900.0)),
    )


__all__ = [
    "API_SVC_HEAD",
    "CHAT_SVC_HEAD",
    "DEFAULT_ADMIN_URL_ENV",
    "ExportSettings",
    "load_export_settings",
]
