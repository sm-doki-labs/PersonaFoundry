from pathlib import Path

from character_factory_poc.common.config import load_config


def test_server_uses_official_apis(tmp_path):
    path = Path(__file__).resolve().parents[1] / "deploy/factory.server.toml"
    raw = path.read_text()
    assert "localhost" not in raw and "127.0.0.1" not in raw
    cfg = load_config(tmp_path, path)
    assert cfg.text_pipeline["enabled"] and cfg.text_pipeline["route"] == "api"
    for task, host, key in (
        ("brief", "https://api.openai.com/v1", "OPENAI_API_KEY"),
        ("voice", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    ):
        binding = cfg.task_provider(task)
        assert (binding.base_url, binding.api_key_env) == (host, key)
    dialogue = cfg.provider("dialogue")
    assert (dialogue.model, dialogue.base_url, dialogue.api_key_env) == (
        "gemini-3.8-flash",
        cfg.task_provider("voice").base_url,
        "GEMINI_API_KEY",
    )
    assert cfg.provider("image").adapter == cfg.provider("video").adapter == "fake"
