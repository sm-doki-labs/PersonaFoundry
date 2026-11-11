"""Retired workshop pages cannot reopen the obsolete interface."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.web.app import create_app

REPO = Path(__file__).resolve().parents[1]
PAGES = [
    "src/character_factory_poc/web/static/index.html",
    "src/character_factory_poc/web/static/c-glass.html",
    "src/character_factory_poc/web/static/d-ops.html",
    "studio/index.html",
    "studio/a-studio.html",
    "studio/b-editorial.html",
    "studio/c-glass.html",
]


def test_retired_pages_only_forward_to_current_factory():
    for name in PAGES:
        text = (REPO / name).read_text()
        assert "/shared/current-factory.js" in text, name
        assert "/studio/factory.html" in text, name
        for legacy in ["shared/live.js", "shared/engine.js", "shared/ops.js", "previews/"]:
            assert legacy not in text, name


def test_default_server_serves_current_factory_without_extra_config(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        root = client.get("/")
        assert "/shared/current-factory.js" in root.text
        assert client.get("/studio/factory.html").status_code == 200
        assert client.get("/gate.html").status_code == 200
        assert client.get("/shared/gate.js").status_code == 200


def test_old_links_keep_character_and_gate_context():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required")
    script = REPO / "src/character_factory_poc/web/static/shared/current-factory.js"
    cases = [
        ["", "", "/studio/factory.html#all"],
        ["?character=synthetic", "", "/studio/factory.html#c/synthetic"],
        ["?character=synthetic&gate=G6", "", "/gate.html?character=synthetic&gate=G6"],
        ["", "#char/synthetic", "/studio/factory.html#c/synthetic"],
        ["", "#c/synthetic", "/studio/factory.html#c/synthetic"],
    ]
    code = """const fs=require('node:fs'),vm=require('node:vm');
    const assert=require('node:assert/strict');
    const src=fs.readFileSync(process.argv[1],'utf8');
    for(const [search,hash,want] of JSON.parse(process.argv[2])) {
      let target; vm.runInNewContext(src,{URLSearchParams,encodeURIComponent,decodeURIComponent,
        location:{search,hash,replace(x){target=x;}}}); assert.equal(target,want);
    }"""
    result = subprocess.run(
        [node, "-e", code, str(script), json.dumps(cases)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_installed_server_finds_packaged_factory(tmp_path, monkeypatch):
    import sys

    from character_factory_poc.web import settings

    installed = tmp_path / "env/share/character-factory-poc/studio"
    installed.mkdir(parents=True)
    (installed / "factory.html").write_text("<main>installed factory</main>")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
    monkeypatch.setattr(settings, "__file__", str(tmp_path / "env/lib/pkg/web/settings.py"))
    assert settings.WebSettings(root=tmp_path).studio_path == installed
