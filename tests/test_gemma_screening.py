"""Gemma 선별 요청·선별 상태 전이·원격 스크립트 테스트. GPU·네트워크 없이 돈다.

job.sh 테스트는 실제 bash로 제출 명령을 실행한다. 원격 python과 timeout만 가짜 스크립트로 바꾸고,
ssh가 하는 것처럼 명령을 한 번 더 shlex.join해 sh가 다시 해석하게 한다.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from character_factory_poc.providers.training.gemma_qlora import N3B_VERSIONS, REMOTE_SCRIPTS
from character_factory_poc.providers.training.port import DatasetFile, resolve_dataset_files
from character_factory_poc.providers.training.screening import (
    build_screen_tasks,
    generations,
    read_tasks,
    tasks_text,
)
from tests.test_s10_train import FakeRemoteHost, gemma, make_dataset, request_for

REMOTE = Path(__file__).resolve().parents[1] / (
    "src/character_factory_poc/providers/training/remote"
)


# ---- 선별 요청 ---------------------------------------------------------------------------


def _conversation(tag: str, users: int) -> dict:
    messages = [{"role": "system", "content": "짧은 system"}]
    for n in range(users):
        messages.append({"role": "user", "content": f"{tag} 질문 {n}"})
        messages.append({"role": "assistant", "content": f"{tag} 답 {n}", "weight": 1})
    return {"messages": messages}


def _file(root: Path, split: str, name: str, rows: list[dict]) -> DatasetFile:
    path = root / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    data = path.read_bytes()
    return DatasetFile(
        split=split,
        path=path,
        relative=name,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        conversations=len(rows),
    )


@pytest.fixture
def screen_files(tmp_path: Path) -> list[DatasetFile]:
    base = [_conversation(f"vb{i}", 1) for i in range(30)]
    base += [_conversation(f"long{i}", 7) for i in range(3)]
    base += [_conversation(f"short{i}", 5) for i in range(4)]
    augmented = [_conversation(f"va{i}", 2) for i in range(6)]
    train = [_conversation(f"TRAIN{i}", 7) for i in range(40)]
    return [
        _file(tmp_path, "train", "train.jsonl", train),
        _file(tmp_path, "validation_base", "validation-base.jsonl", base),
        _file(tmp_path, "validation_augmented", "validation-augmented.jsonl", augmented),
    ]


def test_screen_tasks_are_deterministic_and_use_validation_only(
    screen_files: list[DatasetFile],
) -> None:
    tasks = build_screen_tasks(screen_files, single=24, multi=2, max_turns=6, seed=3407)
    again = build_screen_tasks(screen_files[::-1], single=24, multi=2, max_turns=6, seed=3407)

    assert tasks_text(tasks) == tasks_text(again)
    assert "TRAIN" not in tasks_text(tasks)
    singles = [t for t in tasks if t["kind"] == "single"]
    multis = [t for t in tasks if t["kind"] == "multi"]
    assert len(singles) == 24
    assert len(multis) <= 2
    assert len({t["taskId"] for t in tasks}) == len(tasks)
    rows = [t["taskId"][2:] for t in tasks]
    assert len(set(rows)) == len(rows)  # 한 대화를 단발과 장면에 겹쳐 쓰지 않는다
    assert len({t["seed"] for t in tasks}) == len(tasks)
    assert generations(tasks) == len(singles) + 6 * len(multis)


def test_single_tasks_stop_right_before_last_reply(screen_files: list[DatasetFile]) -> None:
    tasks = build_screen_tasks(screen_files, single=40, multi=0, max_turns=6, seed=1)
    assert tasks
    for task in tasks:
        assert task["messages"][-1]["role"] == "user"
        assert task["reference"].startswith(task["messages"][-1]["content"].split(" ")[0])
        assert all(set(m) == {"role", "content"} for m in task["messages"])
        assert "userTurns" not in task


def test_multi_scenes_need_full_turn_count(screen_files: list[DatasetFile]) -> None:
    tasks = build_screen_tasks(screen_files, single=0, multi=2, max_turns=6, seed=3407)

    assert [t["kind"] for t in tasks] == ["multi", "multi"]
    for task in tasks:
        assert task["messages"] == [{"role": "system", "content": "짧은 system"}]
        assert len(task["userTurns"]) == 6
        assert task["userTurns"][0].startswith("long")  # 5턴 대화(short)는 6턴 장면이 못 된다
    assert generations(tasks) == 12

    shorter = build_screen_tasks(screen_files, single=0, multi=2, max_turns=5, seed=3407)
    assert all(len(t["userTurns"]) == 5 for t in shorter)


def test_multi_scene_count_shrinks_when_no_long_conversation(tmp_path: Path) -> None:
    files = [_file(tmp_path, "validation_base", "v.jsonl", [_conversation("s", 3)] * 4)]
    tasks = build_screen_tasks(files, single=0, multi=2, max_turns=6, seed=1)
    assert tasks == []


def test_submit_writes_same_requests_locally_and_remotely(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)

    local = request.plan_dir / "screen-requests.jsonl"
    assert host.files[f"{run.jobId}/screen/requests.jsonl"] == local.read_bytes()
    tasks = read_tasks(local)
    assert tasks == provider.screen_tasks(request)
    assert len(tasks) == 3
    assert run.appliedConfig["screenTasks"] == 3


# ---- 상태 전이 ---------------------------------------------------------------------------

OK = {"ok": True, "files": [], "checkpoints": []}


def submitted(tmp_path: Path):
    dataset, ds_dir = make_dataset(tmp_path)
    host = FakeRemoteHost()
    provider = gemma(host)
    request = request_for(tmp_path, dataset, ds_dir)
    run = provider.submit(provider.plan(request), request)
    assert run.jobId
    host.write_text(f"{run.jobId}/train.log", "STATE training\n")
    return host, provider, request, run


@pytest.mark.parametrize(
    ("remote", "status", "screen", "error"),
    [
        ({"complete.json": OK}, "RUNNING", None, None),
        (
            {"complete.json": OK, "screen-complete.json": {"ok": True, "files": []}},
            "SUCCEEDED",
            "done",
            None,
        ),
        (
            {
                "complete.json": OK,
                "screen-complete.json": {"ok": False, "error": "CUDA OOM", "files": []},
            },
            "SUCCEEDED",
            "failed",
            "CUDA OOM",
        ),
        (
            {"complete.json": OK, "job-exit.json": {"train": 0, "screen": "137"}},
            "SUCCEEDED",
            "failed",
            "결과 없이",
        ),
        ({"job-exit.json": {"train": 1, "screen": "skip"}}, "FAILED", None, "완료 기록 없이"),
        ({"complete.json": {"ok": False, "error": "RuntimeError: drift"}}, "FAILED", None, "drift"),
    ],
    ids=[
        "train-done-screen-pending",
        "screen-done",
        "screen-failed",
        "screen-vanished",
        "exit-without-complete",
        "train-failed",
    ],
)
def test_status_transitions(
    tmp_path: Path, remote: dict, status: str, screen: str | None, error: str | None
) -> None:
    host, provider, request, run = submitted(tmp_path)
    for name, payload in remote.items():
        host.write_text(f"{run.jobId}/{name}", json.dumps(payload))

    current = provider.status(run, request)

    assert current.status == status
    if screen is not None:
        assert current.appliedConfig["screen"] == screen
    if error is not None:
        key = "screenError" if status == "SUCCEEDED" else "error"
        assert error in current.appliedConfig[key]


def _expire(host: FakeRemoteHost, job: str) -> None:
    started = json.loads(host.read_text(f"{job}/started.json") or "{}")
    started["startedAt"] = (datetime.now(UTC) - timedelta(hours=9)).isoformat()
    host.write_text(f"{job}/started.json", json.dumps(started))


def test_screen_past_wall_limit_counts_as_screen_failure(tmp_path: Path) -> None:
    host, provider, request, run = submitted(tmp_path)
    assert run.jobId
    host.write_text(f"{run.jobId}/complete.json", json.dumps(OK))
    _expire(host, run.jobId)

    current = provider.status(run, request)

    assert current.status == "SUCCEEDED"
    assert current.appliedConfig["screen"] == "failed"
    assert "상한" in current.appliedConfig["screenError"]
    assert any("pkill" in c[-1] for c in host.commands)


def test_training_past_wall_limit_fails(tmp_path: Path) -> None:
    host, provider, request, run = submitted(tmp_path)
    assert run.jobId
    _expire(host, run.jobId)

    current = provider.status(run, request)

    assert current.status == "FAILED"
    assert "상한" in current.appliedConfig["error"]


# ---- job.sh를 실제 bash로 ----------------------------------------------------------------

FAKE_PYTHON = """#!/bin/bash
printf '%s\\n' "$@" > "args-$1.txt"
i=0
while [ ! -f go ] && [ "$i" -lt 200 ]; do sleep 0.05; i=$((i + 1)); done
if [ "$1" = train_qlora.py ]; then exit "${FAKE_TRAIN_RC:-0}"; fi
exit 0
"""

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash가 없다")


def _stub(path: Path, text: str) -> None:
    path.write_text(text, "utf-8")
    path.chmod(0o755)


@pytest.fixture
def job_env(tmp_path: Path):
    bin_dir = tmp_path / "bin dir"  # 공백이 든 경로도 따옴표가 맞아야 한다
    bin_dir.mkdir()
    _stub(bin_dir / "timeout", '#!/bin/bash\nshift\nexec "$@"\n')  # 원격의 GNU timeout 대신
    fake_python = bin_dir / "python"
    _stub(fake_python, FAKE_PYTHON)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    job_dir = tmp_path / "cfp job's dir"
    job_dir.mkdir()
    dataset, ds_dir = make_dataset(tmp_path)
    provider = gemma(FakeRemoteHost(), remote_python=str(fake_python))
    files = resolve_dataset_files(request_for(tmp_path, dataset, ds_dir))
    return provider, files, job_dir, env


def _launch(command: str, job_dir: Path, env: dict[str, str]) -> str:
    # VastRemoteHost.run은 ["bash", "-lc", 명령]을 shlex.join해 ssh에 넘기고, 원격 sh가 다시 푼다.
    outer = shlex.join(["bash", "-c", command])
    proc = subprocess.Popen(
        ["sh", "-c", outer], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True
    )
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        (job_dir / "go").touch()
        proc.kill()
        proc.communicate()
        pytest.fail("제출 명령이 백그라운드 작업을 기다리느라 돌아오지 않았다(ssh가 멈춘다)")
    assert proc.returncode == 0, err
    return out.strip()


def _wait_for(path: Path) -> dict:
    for _ in range(200):
        if path.exists() and path.read_text("utf-8").strip():
            return json.loads(path.read_text("utf-8"))
        time.sleep(0.05)
    pytest.fail(f"{path.name}이 생기지 않았다")


def _args(path: Path) -> list[str]:
    return path.read_text("utf-8").splitlines()


@needs_bash
@pytest.mark.parametrize("screening", [True, False])
def test_job_script_passes_bash_syntax_check(job_env, screening: bool) -> None:
    provider, files, job_dir, _ = job_env
    script = job_dir / "job.sh"
    script.write_text(provider._job_script(files, 3600, screening), "utf-8")
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_submit_command_runs_train_then_screen_then_writes_exit(job_env) -> None:
    provider, files, job_dir, env = job_env
    command = provider._command(files, str(job_dir), 3600, True)

    pid = _launch(command, job_dir, {**env, "FAKE_TRAIN_RC": "0"})

    assert pid.isdigit()  # ssh는 PID만 받고 바로 돌아온다
    script = job_dir / "job.sh"
    assert script.read_text("utf-8") == provider._job_script(files, 3600, True)
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    (job_dir / "go").touch()
    assert _wait_for(job_dir / "job-exit.json") == {"train": 0, "screen": "0"}

    train = _args(job_dir / "args-train_qlora.py.txt")
    assert json.loads(train[train.index("--expected-versions") + 1]) == N3B_VERSIONS
    assert train[train.index("--checkpoint-epochs") + 1] == "0.5,1,1.5,2"
    assert train[train.index("--lr-scheduler") + 1] == "constant_with_warmup"
    assert train[train.index("--train") + 1] == "train.jsonl"
    deadline = int(train[train.index("--deadline-epoch") + 1])
    assert time.time() < deadline <= time.time() + 3600
    screen = _args(job_dir / "args-screen_qlora.py.txt")
    assert "--include-base" in screen
    assert int(screen[screen.index("--deadline-epoch") + 1]) == deadline
    assert "train.log" in os.listdir(job_dir)


@needs_bash
def test_failed_training_skips_screen(job_env) -> None:
    provider, files, job_dir, env = job_env
    _launch(
        provider._command(files, str(job_dir), 3600, True), job_dir, {**env, "FAKE_TRAIN_RC": "3"}
    )
    (job_dir / "go").touch()

    assert _wait_for(job_dir / "job-exit.json") == {"train": 3, "screen": "skip"}
    assert not (job_dir / "args-screen_qlora.py.txt").exists()


# ---- 원격 스크립트 정적 검사 ---------------------------------------------------------------


def _tree(name: str) -> ast.Module:
    return ast.parse((REMOTE / name).read_text("utf-8"), filename=name)


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called == name:
                out.append(node)
    return out


def _options(tree: ast.AST) -> dict[str, ast.Call]:
    return {
        call.args[0].value: call
        for call in _calls(tree, "add_argument")
        if call.args and isinstance(call.args[0], ast.Constant)
    }


@pytest.mark.parametrize("name", REMOTE_SCRIPTS)
def test_remote_scripts_parse(name: str) -> None:
    tree = _tree(name)
    compile(tree, name, "exec")
    assert _calls(tree, "parse_args")


def test_train_script_follows_n3b_recipe() -> None:
    tree = _tree("train_qlora.py")
    strings = {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "<|turn>user\n" in strings
    assert "<|turn>model\n" in strings
    assert _calls(tree, "from_pretrained")
    assert _calls(tree, "get_peft_model")
    assert _calls(tree, "get_chat_template")
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert {"FastModel", "get_chat_template", "train_on_responses_only"} <= imported
    [responses] = _calls(tree, "train_on_responses_only")
    parts = {k.arg: getattr(k.value, "id", None) for k in responses.keywords}
    assert parts == {"instruction_part": "USER_PART", "response_part": "MODEL_PART"}
    [config] = _calls(tree, "SFTConfig")
    keywords = {k.arg for k in config.keywords}
    assert "max_length" in keywords
    assert "max_seq_length" not in keywords  # TRL 0.23은 max_seq_length를 받지 않는다
    scheduler = _options(tree)["--lr-scheduler"]
    default = next(k.value for k in scheduler.keywords if k.arg == "default")
    assert isinstance(default, ast.Constant) and default.value == "constant_with_warmup"


def test_job_script_flags_exist_in_remote_scripts(tmp_path: Path) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    provider = gemma(FakeRemoteHost(), allow_version_drift=True)
    files = resolve_dataset_files(request_for(tmp_path, dataset, ds_dir))
    lines = provider._job_script(files, 60, True).splitlines()
    for name in ("train_qlora.py", "screen_qlora.py"):
        [line] = [line for line in lines if f" {name} " in line]
        flags = {t for t in shlex.split(line) if t.startswith("--")}
        known = set(_options(_tree(name)))
        assert flags, name
        assert flags <= known, (name, flags - known)


def test_screen_and_serve_load_like_training() -> None:
    for name in ("screen_qlora.py", "serve_qlora.py"):
        tree = _tree(name)
        assert _calls(tree, "from_pretrained"), name
        assert _calls(tree, "get_chat_template"), name
        options = _options(tree)
        assert "--chat-template" in options, name
