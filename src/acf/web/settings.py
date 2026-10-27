"""워크숍 웹앱 설정 (PoC 계획서 §6, P-18·P-22).

경로·저장 위치·포트를 코드에 박지 않는다. factory.toml에 [web] 절을 두거나 별도 설정 파일을
--config로 넘긴다. 상대 경로는 공장 루트 기준이다. 이 파일에는 비밀값을 두지 않는다.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_JOBS_DIR = "work/web-jobs"
DEFAULT_HEARTBEAT_S = 15.0
DEFAULT_UNTIL = "G6"


@dataclass(frozen=True)
class WebSettings:
    """화면·작업 큐의 배포 설정. 값은 factory.toml의 [web] 또는 --config 파일에서 온다."""

    root: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    static_dir: Path = DEFAULT_STATIC_DIR
    jobs_dir: Path = Path(DEFAULT_JOBS_DIR)
    sse_heartbeat_s: float = DEFAULT_HEARTBEAT_S
    default_until: str = DEFAULT_UNTIL
    config_path: Path | None = None

    @property
    def static_path(self) -> Path:
        """화면 파일 폴더. 상대 경로면 공장 루트 기준으로 푼다."""
        return _absolute(self.root, self.static_dir)

    @property
    def jobs_path(self) -> Path:
        """작업 기록 저장 위치. 상대 경로면 공장 루트 기준으로 푼다."""
        return _absolute(self.root, self.jobs_dir)

    def as_dict(self) -> dict[str, Any]:
        """GET /api/health에 싣는 설정 요약. 비밀값은 담지 않는다."""
        return {
            "root": str(self.root),
            "host": self.host,
            "port": self.port,
            "staticDir": str(self.static_path),
            "jobsDir": str(self.jobs_path),
            "sseHeartbeatS": self.sse_heartbeat_s,
            "defaultUntil": self.default_until,
            "configPath": str(self.config_path) if self.config_path else None,
        }


def _absolute(root: Path, path: Path | str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else (root / p)


def _web_table(root: Path, config_path: Path | None) -> dict[str, Any]:
    path = Path(config_path).expanduser() if config_path else (root / "factory.toml")
    if not path.exists():
        if config_path:
            raise ValueError(f"설정 파일이 없다: {path}")
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = data.get("web", {})
    if not isinstance(table, dict):
        raise ValueError(f"[web] 절은 표여야 한다: {path}")
    return dict(table)


def _port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"[web] port는 정수여야 한다: {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"[web] port는 1~65535 사이여야 한다: {port}")
    return port


def load_settings(root: Path, config_path: Path | None = None) -> WebSettings:
    """공장 루트와 설정 파일에서 화면·작업 큐 설정을 읽는다."""
    root = Path(root).expanduser().resolve()
    table = _web_table(root, config_path)
    static_raw = table.get("static_dir") or DEFAULT_STATIC_DIR
    jobs_raw = table.get("jobs_dir") or DEFAULT_JOBS_DIR
    heartbeat = float(table.get("sse_heartbeat_s") or DEFAULT_HEARTBEAT_S)
    if heartbeat <= 0:
        raise ValueError(f"[web] sse_heartbeat_s는 0보다 커야 한다: {heartbeat}")
    return WebSettings(
        root=root,
        host=str(table.get("host") or DEFAULT_HOST),
        port=_port(table.get("port") or DEFAULT_PORT),
        static_dir=_absolute(root, static_raw),
        jobs_dir=_absolute(root, jobs_raw),
        sse_heartbeat_s=heartbeat,
        default_until=str(table.get("default_until") or DEFAULT_UNTIL),
        config_path=Path(config_path).expanduser().resolve() if config_path else None,
    )
