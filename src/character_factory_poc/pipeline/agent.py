"""에이전트 러너 (명세 §4, LLD §7).

두 백엔드가 있다.
- API: 역할 프롬프트+입력을 한 번에 보내고 JSON을 받는다. 검사 실패는 사유를 붙여 재호출한다.
- codex_exec: 작업 공간(AGENTS.md, inputs/, contract-example.json, check.sh)을 만들고 Codex가 그 안에서
  파일을 읽고 output.json을 쓰고 ./check.sh로 스스로 검사한다. 러너가 다시 검사해 실패하면 사유를 붙여 재실행한다.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from character_factory_poc.checks.registry import run_checks
from character_factory_poc.common.errors import AgentFormatError, ValidationFailed
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.providers.base import (
    ChatRequest,
    Message,
    TextModel,
    extract_json_object,
)

Check = Callable[[Any], list[str]]


@dataclass(frozen=True)
class AgentSpec:
    role: str
    output_contract: str
    stage: str
    max_format_retries: int = 2
    max_check_retries: int = 3
    temperature: float = 0.7


@dataclass
class AgentResult:
    ok: bool
    output: Any
    raw: dict[str, Any] | None
    problems: list[str]
    attempts: int


def load_role_prompt(role: str) -> str:
    return (
        resources.files("character_factory_poc.prompts")
        .joinpath(f"{role}.md")
        .read_text(encoding="utf-8")
    )


def _write_inputs(workspace: Path, inputs: dict[str, Any]) -> list[str]:
    (workspace / "inputs").mkdir(parents=True, exist_ok=True)
    names = []
    for name, value in inputs.items():
        fname = name if "." in name else f"{name}.json"
        p = workspace / "inputs" / fname
        if isinstance(value, str):
            p.write_text(value, encoding="utf-8")
        else:
            p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        names.append(fname)
    return names


def _render_inputs(inputs: dict[str, Any]) -> str:
    parts = []
    for name, value in inputs.items():
        body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        parts.append(f'<input name="{name}">\n{body}\n</input>')
    return "\n\n".join(parts)


# ---------------------------------------------------------------- API 백엔드


def run_agent(
    spec: AgentSpec,
    workspace: Path,
    inputs: dict[str, Any],
    checks: list[Check],
    model: TextModel,
    ref: str,
    contract_example: dict[str, Any] | None = None,
    backend=None,
) -> AgentResult:
    if backend is not None:
        return run_agent_codex(spec, workspace, inputs, backend, ref, contract_example)
    workspace = Path(workspace)
    _write_inputs(workspace, inputs)
    role_text = load_role_prompt(spec.role)
    (workspace / "role.md").write_text(role_text, encoding="utf-8")

    user = _render_inputs(inputs)
    user += f"\n\n출력은 '{spec.output_contract}' 계약을 따르는 JSON 객체 하나만 낸다. 설명을 붙이지 않는다."
    if contract_example is not None:
        user += (
            "\n\n<contract_example>\n"
            + json.dumps(contract_example, ensure_ascii=False, indent=2)
            + "\n</contract_example>"
        )

    history: list[Message] = [Message("system", role_text), Message("user", user)]
    format_failures = check_failures = attempts = 0
    last_raw: dict[str, Any] | None = None
    last_problems: list[str] = []
    while True:
        attempts += 1
        req = ChatRequest(
            kind="AGENT",
            stage=spec.stage,
            messages=tuple(history),
            ref=f"{ref}#{attempts}",
            max_output_tokens=12000,
            temperature=spec.temperature,
            response_json=True,
        )
        resp = model.complete(req)
        (workspace / f"attempt-{attempts}.txt").write_text(resp.text, encoding="utf-8")
        try:
            raw = extract_json_object(resp.text)
            validated = validate(spec.output_contract, raw)
        except (ValueError, ValidationFailed) as e:
            format_failures += 1
            problems = e.problems if isinstance(e, ValidationFailed) else [str(e)]
            if format_failures > spec.max_format_retries:
                raise AgentFormatError(
                    f"{spec.role}: 형식 실패 {format_failures}회: " + "; ".join(problems)
                ) from None
            history += [
                Message("assistant", resp.text),
                Message(
                    "user",
                    "출력 형식이 계약과 다르다. 다음 문제를 고쳐 JSON만 다시 낸다:\n- "
                    + "\n- ".join(problems),
                ),
            ]
            continue
        last_raw = raw
        problems = [p for c in checks for p in c(validated)]
        if not problems:
            (workspace / "output.json").write_text(
                json.dumps(dump(validated), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return AgentResult(True, validated, raw, [], attempts)
        last_problems = problems
        check_failures += 1
        if check_failures > spec.max_check_retries:
            (workspace / "last-failed.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return AgentResult(False, None, last_raw, last_problems, attempts)
        history += [
            Message("assistant", resp.text),
            Message(
                "user",
                "자동 검사에 실패했다. 다음 문제를 고쳐 전체 JSON을 다시 낸다:\n- "
                + "\n- ".join(problems),
            ),
        ]


# ---------------------------------------------------------------- codex_exec 백엔드


def build_codex_workspace(
    spec: AgentSpec, workspace: Path, inputs: dict[str, Any], contract_example: dict | None
) -> None:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    names = _write_inputs(workspace, inputs)
    role_text = load_role_prompt(spec.role)
    common = (
        resources.files("character_factory_poc.prompts")
        .joinpath("common-procedure.md")
        .read_text("utf-8")
    )
    agents_md = (
        f"# 역할: {spec.role}\n\n{role_text}\n\n{common}\n\n## 입력 파일\n\n"
        + "\n".join(f"- inputs/{n}" for n in names)
        + f"\n\n## 출력 계약\n\n- 계약 이름: {spec.output_contract}\n- 예시: contract-example.json\n"
    )
    (workspace / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    if contract_example is not None:
        (workspace / "contract-example.json").write_text(
            json.dumps(contract_example, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    check = workspace / "check.sh"
    check.write_text(
        "#!/usr/bin/env bash\n"
        'cd "$(dirname "$0")"\n'
        f'exec "{sys.executable}" -m character_factory_poc.checks.cli {spec.stage} .\n',
        encoding="utf-8",
    )
    check.chmod(check.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # 출력이 남아 있으면(재실행) 지우지 않는다. 에이전트가 고쳐 쓴다.


def run_agent_codex(
    spec: AgentSpec,
    workspace: Path,
    inputs: dict[str, Any],
    backend,
    ref: str,
    contract_example: dict[str, Any] | None = None,
) -> AgentResult:
    workspace = Path(workspace).resolve()
    build_codex_workspace(spec, workspace, inputs, contract_example)
    prompt = "AGENTS.md를 읽고 그 역할과 절차대로 작업하라. 끝나면 DONE이라고만 답한다."
    attempts = 0
    last_problems: list[str] = []
    env_ok = os.environ.get("PYTHONPATH")
    _ = env_ok
    while True:
        attempts += 1
        run = backend.run(workspace, prompt, ref=f"{ref}#{attempts}")
        (workspace / f"attempt-{attempts}.final.txt").write_text(run.final_text, encoding="utf-8")
        problems = run_checks(spec.stage, workspace)
        if not problems:
            raw = json.loads((workspace / "output.json").read_text("utf-8"))
            validated = validate(spec.output_contract, raw)
            return AgentResult(True, validated, raw, [], attempts)
        last_problems = problems
        if attempts > spec.max_check_retries:
            if (workspace / "output.json").exists():
                (workspace / "last-failed.json").write_text(
                    (workspace / "output.json").read_text("utf-8"), encoding="utf-8"
                )
            return AgentResult(False, None, None, last_problems, attempts)
        prompt = (
            "이전 실행의 output.json이 검사에 실패했다. AGENTS.md의 절차대로 다음 문제를 고치고 "
            "./check.sh가 PASS를 낼 때까지 반복한 뒤 DONE이라고 답한다:\n- " + "\n- ".join(problems)
        )
