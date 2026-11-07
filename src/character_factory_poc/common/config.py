"""factory.toml 로딩 (LLD §3). 키 값은 보관하지 않고 환경변수 이름만 둔다."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    adapter: str = "fake"
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    def family(self) -> str:
        """모델 계열 (D-0010 경고용). 'vendor/model'이면 vendor, 아니면 첫 토큰."""
        m = self.model
        if "/" in m:
            return m.split("/", 1)[0]
        return m.split("-", 1)[0] if m else self.adapter


@dataclass(frozen=True)
class BudgetConfig:
    max_calls_per_command: int = 200
    max_cost_usd_per_command: float = 20.0


@dataclass(frozen=True)
class FactoryConfig:
    root: Path
    providers: dict[str, ProviderConfig]
    budget: BudgetConfig
    stages: dict[str, dict[str, Any]]
    source_path: Path | None = None
    agent: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    # D-0049(LLD §3): 물결 실행·자동 재개, 관문 사전 검토, 수정 요청 재작업
    orchestrator: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    rework: dict[str, Any] = field(default_factory=dict)

    text_pipeline: dict[str, Any] = field(default_factory=dict)
    # D-0079(LLD §22.2): [pricing.models."<id>"] 단가 덮어쓰기. 값은 pricing.lookup의 overrides다.
    pricing: dict[str, Any] = field(default_factory=dict)

    def task_provider(self, task: str) -> ProviderConfig:
        from character_factory_poc.common.text_deck import JUDGE_TASKS

        if not self.text_pipeline.get("enabled", False):
            return self.provider("judge" if task in JUDGE_TASKS else "text")
        return ProviderConfig(**self.text_binding(task)["provider"])

    def text_binding(self, task: str) -> dict:
        from character_factory_poc.common.text_deck import resolve

        return resolve(self, task)

    def provider(self, name: str) -> ProviderConfig:
        return self.providers.get(name, ProviderConfig())

    def stage(self, name: str) -> dict[str, Any]:
        return dict(self.stages.get(name, {}))

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"


_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_ENV_QUOTED = re.compile(r"""^(["'])(.*?)\1\s*(?:#.*)?$""")
_ENV_COMMENT = re.compile(r"\s#")


def _env_value(raw: str) -> str:
    """줄의 값 부분.

    따옴표 값은 안쪽만 쓰고 안의 #은 유지한다. 따옴표 없는 값은 공백 뒤 #부터 떼어 낸다.
    """
    value = raw.strip()
    quoted = _ENV_QUOTED.match(value)
    if quoted:
        return quoted.group(2)
    return _ENV_COMMENT.split(raw, maxsplit=1)[0].strip()


def load_env_file(path: Path) -> list[str]:
    """KEY=VALUE 줄을 읽어 아직 없거나 값이 빈 환경변수만 설정하고, 설정한 이름 목록만 돌려준다.

    값은 반환·출력하지 않는다. 셸에 비어 있지 않은 값이 있는 이름은 덮어쓰지 않고, 파일의 빈 값은
    건너뛴다. 따옴표 없는 값에서 공백 뒤 `#`로 시작하는 줄 끝 메모는 떼어 낸다.
    """
    path = Path(path)
    if not path.is_file():
        return []
    loaded: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        name, value = match.group(1), _env_value(match.group(2))
        if not value or os.environ.get(name):
            continue
        os.environ[name] = value
        loaded.append(name)
    return loaded


def _provider(d: dict[str, Any]) -> ProviderConfig:
    known = {"adapter", "base_url", "model", "api_key_env"}
    return ProviderConfig(
        adapter=d.get("adapter", "fake"),
        base_url=d.get("base_url", ""),
        model=d.get("model", ""),
        api_key_env=d.get("api_key_env", ""),
        extra={k: v for k, v in d.items() if k not in known},
    )


def load_config(root: Path, path: Path | None = None) -> FactoryConfig:
    """factory.toml을 읽는다. 루트 .env의 비어 있지 않은 값은 셸에 없는 이름만 채운다."""
    root = Path(root)
    load_env_file(root / ".env")
    cfg_path = path or (root / "factory.toml")
    data: dict[str, Any] = {}
    if cfg_path.exists():
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    providers = {k: _provider(v) for k, v in data.get("providers", {}).items()}
    b = data.get("budget", {})
    budget = BudgetConfig(
        max_calls_per_command=int(b.get("max_calls_per_command", 200)),
        max_cost_usd_per_command=float(b.get("max_cost_usd_per_command", 20.0)),
    )
    text_pipeline = dict(data.get("text_pipeline", {}))
    selection = root / "work" / "text-pipeline-selection.json"
    if text_pipeline.get("enabled", False) and selection.exists():
        import json

        chosen = json.loads(selection.read_text(encoding="utf-8"))
        if set(chosen) != {"profile", "route"}:
            raise ValueError("잘못된 text-pipeline-selection.json")
        text_pipeline.update(chosen)
    return FactoryConfig(
        root=root,
        providers=providers,
        budget=budget,
        stages=data.get("stages", {}),
        source_path=cfg_path if cfg_path.exists() else None,
        agent=dict(data.get("agent", {})),
        resources=dict(data.get("resources", {})),
        orchestrator=dict(data.get("orchestrator", {})),
        review=dict(data.get("review", {})),
        rework=dict(data.get("rework", {})),
        text_pipeline=text_pipeline,
        pricing=_pricing(data.get("pricing", {})),
    )


def _pricing(section: Any) -> dict[str, Any]:
    """[pricing.models]를 읽는다. 숫자가 아니거나 음수인 단가, 모르는 칸은 ValueError다."""
    from character_factory_poc.common.pricing import OVERRIDE_KEYS, normalize_overrides

    if not isinstance(section, dict):
        raise ValueError("[pricing]은 표여야 한다")
    models = section.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("[pricing.models]는 표여야 한다")
    normalize_overrides(models)
    return {
        model: {key: float(rates[key]) for key in OVERRIDE_KEYS if key in rates}
        for model, rates in models.items()
    }
