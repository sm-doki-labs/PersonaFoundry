"""가짜 codex exec 백엔드. 작업 공간에 output.json을 쓰는 콜백으로 에이전트를 흉내 낸다."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from character_factory_poc.providers.codex_exec import CodexRun

Writer = Callable[[Path, str, int], object]  # (workspace, prompt, attempt) -> output obj | None


class FakeCodexAgent:
    name = "fake_codex"

    def __init__(self, model: str = "fake-codex", writer: Writer | None = None):
        self.model = model
        self.writer = writer
        self.calls: list[tuple[Path, str]] = []

    def run(self, workspace: Path, prompt: str, allow_paths=None) -> CodexRun:
        self.calls.append((Path(workspace), prompt))
        attempt = len([c for c in self.calls if c[0] == Path(workspace)])
        if self.writer is not None:
            obj = self.writer(Path(workspace), prompt, attempt)
            if obj is not None:
                (Path(workspace) / "output.json").write_text(
                    json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        return CodexRun(
            final_text="DONE",
            commands=["/bin/zsh -lc 'cat inputs/x.json'", "./check.sh"],
            input_tokens=100,
            output_tokens=50,
            elapsed_ms=1,
            exit_code=0,
        )
