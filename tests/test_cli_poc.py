"""H 갈래 명령 연결: 새 하위 명령이 등록되고, 유료·사람 판정 경로는 기본으로 막힌다."""

from __future__ import annotations

import pytest

from character_factory_poc.cli import build_parser, main


@pytest.mark.parametrize(
    "argv",
    [
        ["data", "plan", "cf-x"],
        ["data", "samples", "cf-x"],
        ["data", "build", "cf-x"],
        ["train", "plan", "cf-x"],
        ["train", "submit", "cf-x"],
        ["train", "collect", "cf-x"],
        ["eval", "prereg", "cf-x"],
        ["eval", "run", "cf-x"],
        ["eval", "judge", "cf-x"],
        ["eval", "report", "cf-x"],
        ["release", "build", "cf-x"],
        ["export", "doki-app", "cf-x", "--verify"],
        ["web", "--port", "8800"],
    ],
)
def test_new_commands_parse(argv) -> None:
    args = build_parser().parse_args(argv)
    assert callable(args.fn)


def test_train_submit_without_execute_is_dry_run(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "train", "submit", "cf-x"])
    assert rc == 0
    assert "--execute" in capsys.readouterr().out


@pytest.mark.parametrize("gate", ["G7a", "G8"])
def test_run_refuses_auto_approve_for_human_gates(tmp_path, capsys, gate) -> None:
    rc = main(["--root", str(tmp_path), "run", "cf-x", "--until", "sx", "--auto-approve", gate])
    assert rc == 1
    assert gate in capsys.readouterr().err
