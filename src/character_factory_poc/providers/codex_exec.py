"""codex exec 백엔드 (LLD §7). 작업 공간 안에서 도구를 쓰는 에이전트를 돌리고 이벤트를 해석한다."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from character_factory_poc.common.errors import TaintedOutputError

# 홈 경로는 ~ 다음이 / 이거나 경로가 끝나는 경우만 잡는다. 한국어 말투 표기('~요', '~죠')는
# 경로가 아니다(2026-10-22 실제 S3 변형 실행에서 오탐).
_ABS_PATH_RE = re.compile(r"(?<![\w/.-])(/[A-Za-z0-9_./-]+|~/[A-Za-z0-9_./-]*|~(?=$|[\s'\";|&)]))")
_PARENT_RE = re.compile(r"(^|[\s'\"=(])\.\.(/|$)")


@dataclass
class CodexRun:
    final_text: str
    commands: list[str]
    input_tokens: int | None
    output_tokens: int | None
    elapsed_ms: int
    exit_code: int
    tainted: list[str] = field(default_factory=list)
    thread_id: str | None = None
    stderr_tail: str = ""


def find_tainted_paths(commands: list[str], workspace: Path, allow: list[Path]) -> list[str]:
    """명령 문자열에서 작업 공간(과 허용 경로) 밖의 절대 경로·홈 경로·상위 이동을 찾는다."""
    ws = str(Path(workspace).resolve())
    allowed = [ws] + [str(Path(a).resolve()) for a in allow]
    bad: list[str] = []
    for cmd in commands:
        if _PARENT_RE.search(cmd):
            bad.append(cmd[:160])
            continue
        for m in _ABS_PATH_RE.finditer(cmd):
            p = m.group(1)
            if p.startswith("~"):
                bad.append(p)
                continue
            if p in ("/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/env") or p.startswith(
                ("/bin/", "/usr/bin/", "/dev/", "/tmp/")
            ):
                if p.startswith("/tmp/") and not any(p.startswith(a) for a in allowed):
                    bad.append(p)
                continue
            if not any(p == a or p.startswith(a + "/") for a in allowed):
                bad.append(p)
    return sorted(set(bad))


class CodexExecAgent:
    name = "codex_exec"

    def __init__(
        self,
        model: str,
        reasoning_effort: str = "medium",
        sandbox: str = "workspace-write",
        timeout_s: int = 1800,
        extra_config: list[str] | None = None,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.sandbox = sandbox
        self.timeout_s = timeout_s
        self.extra_config = list(extra_config or [])

    def run(self, workspace: Path, prompt: str, allow_paths: list[Path] | None = None) -> CodexRun:
        workspace = Path(workspace).resolve()
        cmd = [
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-m",
            self.model,
            "-s",
            self.sandbox,
            "-C",
            str(workspace),
            "-c",
            f"model_reasoning_effort={json.dumps(self.reasoning_effort)}",
        ]
        for c in self.extra_config:
            cmd += ["-c", c]
        cmd.append(prompt)
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            stdin=subprocess.DEVNULL,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        (workspace / "codex-events.jsonl").write_text(proc.stdout, encoding="utf-8")
        commands: list[str] = []
        final_text = ""
        in_tok = out_tok = None
        thread_id = None
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "thread.started":
                thread_id = ev.get("thread_id")
            elif t == "item.completed":
                item = ev.get("item", {})
                if item.get("type") == "command_execution":
                    commands.append(item.get("command", ""))
                elif item.get("type") == "agent_message":
                    final_text = item.get("text", "")
            elif t == "turn.completed":
                u = ev.get("usage", {})
                in_tok = u.get("input_tokens")
                out_tok = u.get("output_tokens")
        tainted = find_tainted_paths(commands, workspace, allow_paths or [])
        run = CodexRun(
            final_text=final_text,
            commands=commands,
            input_tokens=in_tok,
            output_tokens=out_tok,
            elapsed_ms=elapsed,
            exit_code=proc.returncode,
            tainted=tainted,
            thread_id=thread_id,
            stderr_tail=proc.stderr[-2000:],
        )
        if tainted:
            raise TaintedOutputError("작업 공간 밖 경로에 접근했다: " + ", ".join(tainted[:5]))
        return run
