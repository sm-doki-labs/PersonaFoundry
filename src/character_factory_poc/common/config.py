"""factory.toml 로딩 (LLD §3). 키 값은 보관하지 않고 환경변수 이름만 둔다."""

from __future__ import annotations

import os
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

    def provider(self, name: str) -> ProviderConfig:
        return self.providers.get(name, ProviderConfig())

    def stage(self, name: str) -> dict[str, Any]:
        return dict(self.stages.get(name, {}))

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"


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
    root = Path(root)
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
    return FactoryConfig(
        root=root,
        providers=providers,
        budget=budget,
        stages=data.get("stages", {}),
        source_path=cfg_path if cfg_path.exists() else None,
        agent=dict(data.get("agent", {})),
        resources=dict(data.get("resources", {})),
    )
