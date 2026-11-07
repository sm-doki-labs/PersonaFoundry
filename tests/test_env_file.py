"""Root .env loading: fills missing names only and never overrides the shell."""

import os

from character_factory_poc.common.config import load_config, load_env_file


def test_env_file_fills_missing_names_without_overriding(tmp_path, monkeypatch):
    for name in ("CFP_T_A", "CFP_T_B", "CFP_T_EMPTY", "CFP_T_Q"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CFP_T_B", "from-shell")
    (tmp_path / ".env").write_text(
        "# comment\n\nCFP_T_A=alpha\nexport CFP_T_B=from-file\nCFP_T_EMPTY=\n"
        'CFP_T_Q="quoted value"\nnot a line\n1BAD=x\n',
        encoding="utf-8",
    )
    loaded = load_env_file(tmp_path / ".env")
    assert loaded == ["CFP_T_A", "CFP_T_Q"]
    assert os.environ["CFP_T_A"] == "alpha"
    assert os.environ["CFP_T_B"] == "from-shell"
    assert "CFP_T_EMPTY" not in os.environ
    assert os.environ["CFP_T_Q"] == "quoted value"


def test_load_config_reads_root_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CFP_T_ROOT", raising=False)
    (tmp_path / ".env").write_text("CFP_T_ROOT=yes\n", encoding="utf-8")
    load_config(tmp_path)
    assert os.environ["CFP_T_ROOT"] == "yes"
    monkeypatch.delenv("CFP_T_ROOT")


def test_env_file_strips_trailing_comments_outside_quotes(tmp_path, monkeypatch):
    names = ("CFP_T_C1", "CFP_T_C2", "CFP_T_C3", "CFP_T_C4", "CFP_T_C5", "CFP_T_C6")
    for name in names:
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "CFP_T_C1=plain # 메모\n"
        "CFP_T_C2=abc#def\n"
        'CFP_T_C3="keep # inside" # 메모\n'
        "CFP_T_C4='single # inside'\n"
        "CFP_T_C5=   # 값 없이 메모만\n"
        "CFP_T_C6=tab\t# 탭 뒤 메모\n",
        encoding="utf-8",
    )
    loaded = load_env_file(tmp_path / ".env")
    assert loaded == ["CFP_T_C1", "CFP_T_C2", "CFP_T_C3", "CFP_T_C4", "CFP_T_C6"]
    assert os.environ["CFP_T_C1"] == "plain"
    assert os.environ["CFP_T_C2"] == "abc#def"
    assert os.environ["CFP_T_C3"] == "keep # inside"
    assert os.environ["CFP_T_C4"] == "single # inside"
    assert "CFP_T_C5" not in os.environ
    assert os.environ["CFP_T_C6"] == "tab"


def test_env_file_fills_names_that_are_empty_in_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("CFP_T_BLANK", "")
    monkeypatch.setenv("CFP_T_SET", "from-shell")
    (tmp_path / ".env").write_text("CFP_T_BLANK=from-file\nCFP_T_SET=from-file\n", encoding="utf-8")
    assert load_env_file(tmp_path / ".env") == ["CFP_T_BLANK"]
    assert os.environ["CFP_T_BLANK"] == "from-file"
    assert os.environ["CFP_T_SET"] == "from-shell"
