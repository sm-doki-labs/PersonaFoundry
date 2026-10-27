"""cfp ref collect 연결(B 갈래 통합): 기본 실행은 네트워크 없이 호출 계획만 낸다."""

from __future__ import annotations

import httpx
import pytest

from character_factory_poc.cli import main


def test_ref_collect_dry_run_prints_plan_without_network(tmp_path, capsys, monkeypatch) -> None:
    def no_network(*args, **kwargs):
        raise AssertionError("dry run이 네트워크를 불렀다")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    rc = main(["--root", str(tmp_path), "ref", "collect", "--character-gender", "female"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry run" in out
    assert not (tmp_path / "runs").exists()


def test_ref_collect_rejects_unknown_gender(tmp_path) -> None:
    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "ref", "collect", "--character-gender", "robot"])
