"""Same configured transport for generated samples and interactive chat."""

import pytest

from character_factory_poc.common import demo_chat as demo
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from tests.test_demo_chat import put, ready


def test_samples_use_configured_text_transport_without_separate_gemini_key(tmp_path, monkeypatch):
    (tmp_path / "factory.toml").write_text(
        '[providers.text]\nadapter="vertex_openai"\nmodel="google/gemini-3.8-flash"\nproject="synthetic-project"\nmax_retries=0\n'
    )
    ctx = Context.load(tmp_path, execute=True)
    folder = ctx.character_dir("cf-provider")
    put(folder / "origin.json", {"schemaVersion": "character-origin-v1", "origin": "SOURCE"})
    put(folder / "s3-plan/pr1/plan.json", {"name": "가람"})
    ready(folder)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake = FakeTextModel(model="synthetic", responses={"*": "잘 들었어."})
    transports = []

    def make(cfg):
        transports.append(cfg)
        return fake

    monkeypatch.setattr(demo, "make_text_model", make)
    path = demo.run_samples(ctx, "cf-provider")
    assert path.is_file()
    assert transports[0].adapter == "vertex_openai"
    assert transports[0].extra["project"] == "synthetic-project"
    assert demo.provider(ctx, "studio") == transports[0]


def test_explicit_demo_transport_wins_over_text(tmp_path):
    ctx = Context.load(tmp_path, execute=False)
    ctx.config.providers["text"] = ProviderConfig(adapter="vertex_openai", model="pipeline")
    ctx.config.providers["demo_chat"] = ProviderConfig(adapter="fake", model="configured-chat")
    assert demo.provider(ctx, "studio").model == "configured-chat"


def test_configured_vertex_cannot_bypass_server_mode(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, execute=False)
    ctx.config.providers["demo_chat"] = ProviderConfig(
        adapter="vertex_openai", model="google/demo", extra={"project": "synthetic-project"}
    )
    monkeypatch.setenv("CFP_SERVER_MODE", "1")
    with pytest.raises(PermissionError):
        demo.provider(ctx, "studio")


@pytest.mark.parametrize(
    "template,first_question",
    [
        ("FRIEND_CHAT", "오늘 뭐 했어?"),
        ("INTERVIEW", "오늘 인터뷰에 응해 주셔서 감사합니다. 요즘 가장 집중하는 일은 무엇인가요?"),
    ],
)
def test_samples_follow_selected_conversation_scene(
    tmp_path, monkeypatch, template, first_question
):
    (tmp_path / "factory.toml").write_text(
        '[providers.demo_chat]\nadapter="fake"\nmodel="synthetic"\n'
    )
    ctx = Context.load(tmp_path, execute=True)
    folder = ctx.character_dir("cf-scene-samples")
    put(folder / "origin.json", {"schemaVersion": "character-origin-v1", "origin": "SOURCE"})
    put(folder / "source-pack.json", {"chapterTemplate": template})
    put(folder / "s3-plan/pr1/plan.json", {"name": "가람"})
    ready(folder)
    fake = FakeTextModel(model="synthetic", responses={"*": "생각을 정리하고 있었어."})
    monkeypatch.setattr(demo, "make_text_model", lambda cfg: fake)
    path = demo.run_samples(ctx, "cf-scene-samples")
    import json

    saved = json.loads(path.read_text())
    assert saved["samples"][0]["turns"][0]["user"] == first_question
    assert demo.scenarios(folder)[0]["turns"][0] == first_question
