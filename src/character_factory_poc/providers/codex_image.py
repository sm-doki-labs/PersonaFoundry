"""ChatGPT 구독 이미지 생성 어댑터 (D-0019).

Codex CLI에 ChatGPT 계정으로 로그인한 상태에서 codex exec의 내장 image_gen 도구로 이미지 한 장을
만든다. API 키나 Images API 과금을 쓰지 않고 구독 사용량을 쓴다. Codex는 결과를
$CODEX_HOME/generated_images/<thread_id>/에 저장한다. 어댑터는 그 파일을 읽어 돌려주고
원본은 그대로 둔다.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.providers.base import ImageRequest, ImageResult

Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess]

# 이미지 생성에 필요 없는 플러그인·도구를 꺼서 호출마다 실리는 입력 토큰을 줄인다.
DEFAULT_DISABLE = ("apps", "browser_use", "computer_use")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

INSTRUCTION = """Use your built-in image generation tool exactly once to create one image
from the image prompt below.
Rules:
- Generate exactly one image. Do not run shell commands and do not read or write files.
- Keep the meaning of the image prompt. Do not add text, logos, watermarks, or extra people.
- Preferred size: {size}.
- Avoid: {negative}
{reference}
After the image is generated, reply with the single word DONE.

<image_prompt>
{prompt}
</image_prompt>
"""


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def _run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def parse_events(stdout: str) -> tuple[str | None, str, int | None, int | None]:
    """(thread_id, 마지막 agent_message, 입력 토큰, 출력 토큰)."""
    thread_id = None
    final = ""
    in_tok = out_tok = None
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "thread.started":
            thread_id = ev.get("thread_id")
        elif t == "item.completed" and ev.get("item", {}).get("type") == "agent_message":
            final = ev["item"].get("text", "")
        elif t == "turn.completed":
            u = ev.get("usage", {})
            in_tok, out_tok = u.get("input_tokens"), u.get("output_tokens")
    return thread_id, final, in_tok, out_tok


class CodexImageModel:
    name = "codex_image"

    def __init__(
        self,
        model: str = "gpt-6.1-sol",
        reasoning_effort: str = "low",
        timeout_s: int = 600,
        disable_features: Sequence[str] = DEFAULT_DISABLE,
        extra_config: Sequence[str] = (),
        codex_home: Path | None = None,
        runner: Runner | None = None,
    ):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_s = timeout_s
        self.disable_features = tuple(disable_features)
        self.extra_config = tuple(extra_config)
        self.codex_home = Path(codex_home) if codex_home else default_codex_home()
        self.runner = runner or _run

    def command(self, workspace: Path, text: str, references: Sequence[str] = ()) -> list[str]:
        cmd = [
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-m",
            self.model,
            "-s",
            "read-only",
            "-C",
            str(workspace),
            "-c",
            f"model_reasoning_effort={json.dumps(self.reasoning_effort)}",
            "-c",
            "mcp_servers={}",
        ]
        for f in self.disable_features:
            cmd += ["--disable", f]
        for c in self.extra_config:
            cmd += ["-c", c]
        for ref in references:
            cmd += ["-i", str(ref)]
        # -i는 여러 파일을 받으므로 프롬프트가 파일 이름으로 읽히지 않게 -- 뒤에 둔다.
        cmd += ["--", text]
        return cmd

    def generate(self, request: ImageRequest) -> ImageResult:
        refs = [str(Path(r).resolve()) for r in request.reference_images]
        for r in refs:
            if not Path(r).is_file():
                raise ImageGenerationError(f"참조 이미지가 없다: {r}")
        reference = (
            "- The attached image(s) are identity references described in the image prompt."
            if refs
            else ""
        )
        text = INSTRUCTION.format(
            size=request.size,
            negative=request.negative_prompt or "none",
            prompt=request.prompt,
            reference=reference,
        )
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="cfp-codex-image-") as tmp:
            proc = self.runner(self.command(Path(tmp), text, refs), Path(tmp), self.timeout_s)
        elapsed = int((time.monotonic() - t0) * 1000)
        thread_id, final, in_tok, out_tok = parse_events(proc.stdout or "")
        if proc.returncode != 0 or not thread_id:
            tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
            raise ImageGenerationError(
                f"codex exec 이미지 생성 실패(exit {proc.returncode}): {tail[0][:300]}"
            )
        folder = self.codex_home / "generated_images" / thread_id
        pngs = (
            sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
        )
        if not pngs:
            raise ImageGenerationError(
                f"이미지가 만들어지지 않았다(thread {thread_id}). 마지막 응답: {final[:200]!r}"
            )
        data = pngs[-1].read_bytes()
        if not data.startswith(PNG_MAGIC):
            raise ImageGenerationError(f"PNG가 아니다: {pngs[-1].name}")
        return ImageResult(
            data=data,
            mime="image/png",
            model=self.model,
            provider=self.name,
            elapsed_ms=elapsed,
            est_cost_usd=0.0,
            input_tokens=in_tok,
            output_tokens=out_tok,
            source_path=str(pngs[-1]),
        )
