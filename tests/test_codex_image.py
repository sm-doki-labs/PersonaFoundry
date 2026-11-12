"""ChatGPT 구독 이미지 어댑터(codex_image) 테스트. 실제 codex는 부르지 않는다 (D-0019, NFR-08)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.providers.codex_image import CodexImageModel
from character_factory_poc.providers.factory import make_image_model
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import solid_png
from character_factory_poc.stages.s1_reference.run import run_s1
from character_factory_poc.stages.s3_plan.common import new_character
from tests.support.synthetic import RANKING, scout_features


class FakeCodex:
    """codex exec를 흉내 낸다: 이벤트를 내고 generated_images/<thread>/에 PNG를 쓴다."""

    def __init__(self, home: Path, write_image: bool = True, exit_code: int = 0):
        self.home = home
        self.write_image = write_image
        self.exit_code = exit_code
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        tid = f"thread-{len(self.calls)}"
        if self.write_image:
            folder = self.home / "generated_images" / tid
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "exec-1.png").write_bytes(solid_png(4, 4, (0, 0, 255)))
        events = [
            {"type": "thread.started", "thread_id": tid},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "DONE"}},
            {"type": "turn.completed", "usage": {"input_tokens": 19000, "output_tokens": 40}},
        ]
        stdout = "\n".join(json.dumps(e) for e in events)
        return subprocess.CompletedProcess(
            cmd, self.exit_code, stdout, "boom" if self.exit_code else ""
        )


def _req(prompt: str = "a calm portrait") -> ImageRequest:
    return ImageRequest(stage="s1", prompt=prompt, ref="x", negative_prompt="text, watermark")


def test_generate_reads_saved_png_and_keeps_original(tmp_path):
    fake = FakeCodex(tmp_path)
    model = CodexImageModel(codex_home=tmp_path, runner=fake)
    res = model.generate(_req("Character reference portrait of a fictional woman"))
    assert res.data.startswith(b"\x89PNG") and res.provider == "codex_image"
    assert (res.input_tokens, res.output_tokens, res.est_cost_usd) == (19000, 40, 0.0)
    assert Path(res.source_path).exists()  # 원본은 지우지 않는다
    cmd = fake.calls[0]
    assert cmd[:2] == ["codex", "exec"] and "--json" in cmd
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert "mcp_servers={}" in cmd and cmd.count("--disable") == 3
    assert "-i" not in cmd and cmd[-2] == "--"
    assert "Character reference portrait of a fictional woman" in cmd[-1]
    assert "Avoid: text, watermark" in cmd[-1]


def test_reference_images_are_attached_before_prompt(tmp_path):
    fake = FakeCodex(tmp_path)
    ref = tmp_path / "ref.png"
    ref.write_bytes(solid_png(2, 2, (1, 2, 3)))
    model = CodexImageModel(codex_home=tmp_path, runner=fake)
    req = ImageRequest(stage="s2", prompt="same person", ref="x", reference_images=(str(ref),))
    model.generate(req)
    cmd = fake.calls[0]
    i = cmd.index("-i")
    assert cmd[i + 1] == str(ref.resolve()) and cmd[-2] == "--"
    assert "identity references" in cmd[-1]
    with pytest.raises(ImageGenerationError, match="참조 이미지가 없다"):
        model.generate(ImageRequest(stage="s2", prompt="p", ref="x", reference_images=("/no.png",)))


def test_no_image_or_failed_run_raises(tmp_path):
    with pytest.raises(ImageGenerationError, match="만들어지지 않았다"):
        CodexImageModel(codex_home=tmp_path, runner=FakeCodex(tmp_path, False)).generate(_req())
    with pytest.raises(ImageGenerationError, match="exit 1"):
        CodexImageModel(codex_home=tmp_path, runner=FakeCodex(tmp_path, True, 1)).generate(_req())


def test_factory_builds_codex_image_from_config():
    cfg = ProviderConfig(
        adapter="codex_image",
        model="gpt-6.1-sol",
        extra={"timeout_s": 120, "disable_features": ["apps"], "reasoning_effort": "medium"},
    )
    m = make_image_model(cfg)
    assert isinstance(m, CodexImageModel)
    assert (m.timeout_s, m.disable_features, m.reasoning_effort) == (120, ("apps",), "medium")
    with pytest.raises(ValueError, match="codex_image"):
        make_image_model(ProviderConfig(adapter="unknown_image_adapter"))


def test_s1_previews_through_codex_image(tmp_path):
    (tmp_path / "factory.toml").write_text(
        '[providers.image]\nadapter = "codex_image"\nmodel = "gpt-6.1-sol"\n', encoding="utf-8"
    )
    ctx = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", lambda req: scout_features(RANKING))
    ctx.use_models(text)
    home = tmp_path / "codex-home"
    fake = FakeCodex(home)
    ctx.use_image(CodexImageModel(codex_home=home, runner=fake))
    cid = new_character(ctx, "sub")
    out = run_s1(ctx, cid, RANKING)
    previews = json.loads((out / "previews.json").read_text("utf-8"))
    assert len(previews) == 9 and {p["provider"] for p in previews} == {"codex_image"}
    assert len(fake.calls) == 9
    images = [c for c in ctx.ledger(cid).calls() if c["kind"] == "IMAGE"]
    assert len(images) == 9 and images[0]["inputTokens"] == 19000
