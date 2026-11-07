"""원격 학습·선별·서빙 스크립트 시험 (GPU·네트워크 없이).

세 스크립트는 무거운 패키지(unsloth·torch 등)를 main 안에서만 불러오므로 모듈째 import해 순수
함수를 직접 시험한다. import 순서와 필수 검사는 ast로 확인하고, 공장이 만드는 실행 명령의 인자는
각 스크립트의 실제 argparse로 풀어 본다.
"""

from __future__ import annotations

import ast
import json
import shlex
import sys
from pathlib import Path

import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.providers.training.inference import ADAPTER_FILES, GpuInferenceSession
from character_factory_poc.providers.training.port import resolve_dataset_files
from character_factory_poc.providers.training.remote import screen_qlora, serve_qlora, train_qlora
from tests.test_s10_train import FakeRemoteHost, gemma, make_dataset, request_for

SCRIPTS = {
    "train_qlora.py": train_qlora,
    "screen_qlora.py": screen_qlora,
    "serve_qlora.py": serve_qlora,
}
HEAVY = {"torch", "transformers", "trl", "datasets", "peft", "safetensors"}
IGNORE = -100


def _tree(name: str) -> ast.Module:
    return ast.parse(Path(SCRIPTS[name].__file__).read_text("utf-8"), filename=name)


def _imports(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name.split(".")[0]) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.lineno, node.module.split(".")[0]))
    return sorted(out)


def _called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    return names


def _strings(tree: ast.AST) -> set[str]:
    return {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


# ---- import 순서·모듈 import ------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_unsloth_is_imported_first_right_after_version_check(name: str) -> None:
    tree = _tree(name)
    imports = _imports(tree)
    first_unsloth = min(line for line, root in imports if root == "unsloth")
    heavy = [(line, root) for line, root in imports if root in HEAVY]
    assert any(root == "torch" for _, root in heavy), name
    assert all(first_unsloth < line for line, _ in heavy), (name, first_unsloth, heavy)
    version_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "version"
    ]
    assert version_lines and max(version_lines) < first_unsloth, name


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_heavy_packages_stay_inside_main(name: str) -> None:
    tree = _tree(name)
    top = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    roots = {root for node in top for _, root in _imports(node)}
    assert not roots & (HEAVY | {"unsloth"}), (name, roots)
    assert hasattr(SCRIPTS[name], "main")


# ---- 학습 스크립트 -----------------------------------------------------------------------------


def test_train_script_keeps_n3b_data_guards() -> None:
    tree = _tree("train_qlora.py")
    strings = _strings(tree)
    assert {"data-check.json", "collator-label-parity-confirmed.json"} <= strings
    assert train_qlora.SELECT_FIELD == "supervisedAssistantIndexes"
    assert train_qlora.PARTIAL_ID == "budget-partial"
    called = _called(tree)
    for needed in (
        "select_labels",
        "selected_assistants",
        "token_problems",
        "padded_labels",
        "data_collator",
        "partial_checkpoint",
        "training_finished",
        "deadline_reached",
        "map",
    ):
        assert needed in called, needed


USER, MODEL, END, NL, BOS = [10, 11], [20, 21], 99, 5, 2


def _conversation() -> tuple[list[int], list[int]]:
    """system 뒤 user→assistant 두 번. 라벨은 train_on_responses_only처럼 model 머리 뒤만 남긴다."""
    ids, labels = [BOS, 30, 31], [IGNORE] * 3
    for user_tokens, answer in (([40, 41], [50, 51]), ([42], [52])):
        part = [*USER, *user_tokens, END, NL]
        ids += part
        labels += [IGNORE] * len(part)
        ids += MODEL
        labels += [IGNORE] * len(MODEL)
        reply = [*answer, END, NL]
        ids += reply
        labels += reply
    return ids, labels


def _select(ids, labels, selected, count=2):
    return train_qlora.select_labels(ids, labels, selected, USER, MODEL, END, count)


def test_select_labels_keeps_only_selected_assistant_turns() -> None:
    ids, labels = _conversation()
    assert _select(ids, labels, [0, 1]) == labels
    first = _select(ids, labels, [0])
    second = _select(ids, labels, [1])
    assert [ids[i] for i, v in enumerate(first) if v != IGNORE] == [50, 51, END, NL]
    assert [ids[i] for i, v in enumerate(second) if v != IGNORE] == [52, END, NL]
    assert len(first) == len(ids)  # 입력 토큰은 그대로, 라벨만 지운다


@pytest.mark.parametrize(
    "case",
    [
        "head_supervised",
        "user_supervised",
        "count_mismatch",
        "out_of_range",
        "no_turn_end",
        "label_differs",
        "empty_selection",
        "length_mismatch",
    ],
)
def test_select_labels_rejects_broken_supervision(case: str) -> None:
    ids, labels = _conversation()
    selected, count = [0], 2
    model_at = ids.index(MODEL[0])
    if case == "head_supervised":
        labels[model_at] = ids[model_at]
    elif case == "user_supervised":
        labels[ids.index(40)] = 40
    elif case == "count_mismatch":
        count = 3
    elif case == "out_of_range":
        selected = [2]
    elif case == "no_turn_end":
        last_end = len(ids) - 2
        ids[last_end] = labels[last_end] = 53
    elif case == "label_differs":
        labels[ids.index(50)] = 777
    elif case == "empty_selection":
        selected = []
    elif case == "length_mismatch":
        labels = labels[:-1]
    with pytest.raises(ValueError):
        _select(ids, labels, selected, count)


def _row(**extra) -> dict:
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1", "weight": 1},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2", "weight": 1},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3", "weight": 1},
    ]
    return {"messages": messages, **extra}


def test_selected_assistants_defaults_to_all_and_reads_factory_field() -> None:
    assert train_qlora.selected_assistants(_row()) == [0, 1, 2]
    assert train_qlora.selected_assistants(_row(supervisedAssistantIndexes=None)) == [0, 1, 2]
    assert train_qlora.selected_assistants(_row(supervisedAssistantIndexes=[2, 0])) == [2, 0]


@pytest.mark.parametrize("value", [[], [0, 0], [-1], [True], [3], ["1"], 1])
def test_selected_assistants_blocks_zero_or_bad_selection(value) -> None:
    with pytest.raises(ValueError):
        train_qlora.selected_assistants(_row(supervisedAssistantIndexes=value))


def test_selected_assistants_blocks_rows_without_assistant() -> None:
    with pytest.raises(ValueError):
        train_qlora.selected_assistants({"messages": [{"role": "user", "content": "u"}]})


def test_token_problems_checks_parity_single_bos_and_length() -> None:
    ids = [BOS, 7, 8]
    assert train_qlora.token_problems(ids, list(ids), BOS, 3) == []
    assert train_qlora.token_problems(ids, [BOS, 7, 9], BOS, 3)
    assert train_qlora.token_problems([BOS, BOS, 7], [BOS, BOS, 7], BOS, 3)
    assert train_qlora.token_problems([7, BOS, 8], [7, BOS, 8], BOS, 3)
    assert train_qlora.token_problems(ids, ids, None, 3)
    assert train_qlora.token_problems(ids, ids, BOS, 2)


def test_padded_labels_follows_padding_side() -> None:
    assert train_qlora.padded_labels([1, 2], 4, "right") == [1, 2, IGNORE, IGNORE]
    assert train_qlora.padded_labels([1, 2], 4, "left") == [IGNORE, IGNORE, 1, 2]
    assert train_qlora.padded_labels([1, 2], 2, "left") == [1, 2]
    with pytest.raises(ValueError):
        train_qlora.padded_labels([1, 2, 3], 2, "right")


def test_checkpoint_targets_match_n3b_plan() -> None:
    # N3b 실제 checkpoint-plan.json: 236 step, 2 epoch, 0.5 epoch마다.
    plan = train_qlora.checkpoint_targets(236, 2.0, [0.5, 1.0, 1.5, 2.0])
    assert plan == {59: 0.5, 118: 1.0, 177: 1.5, 236: 2.0}
    assert train_qlora.checkpoint_targets(3, 2.0, [0.5, 1.0, 1.5, 2.0]) == {
        1: 0.5,
        2: 1.5,
        3: 2.0,
    }


def test_deadline_and_finish_rules() -> None:
    assert not train_qlora.deadline_reached(0.0, 10**10)
    assert not train_qlora.deadline_reached(1000.0, 699.0)
    assert train_qlora.deadline_reached(1000.0, 701.0)
    assert train_qlora.training_finished(236, 236, 2.0, 2.0)
    assert not train_qlora.training_finished(150, 236, 1.27, 2.0)
    assert not train_qlora.training_finished(0, 0, 0.0, 2.0)


def test_partial_checkpoint_records_actual_epoch() -> None:
    saved = [
        {"checkpointId": "epoch-0.5", "epoch": 0.5, "step": 59, "ref": "checkpoints/epoch-0.5"}
    ]
    partial = train_qlora.partial_checkpoint(100, 0.847457, saved)
    assert partial == {
        "checkpointId": "budget-partial",
        "epoch": 0.847457,
        "step": 100,
        "ref": "checkpoints/budget-partial",
        "budgetStopped": True,
    }
    assert train_qlora.partial_checkpoint(59, 0.5, saved) is None  # 방금 저장한 가중치와 같다
    assert train_qlora.partial_checkpoint(0, 0.0, []) is None  # 한 step도 못 했으면 실패


def test_train_main_stops_before_model_on_zero_supervision(tmp_path, monkeypatch) -> None:
    rows = [_row(), _row(supervisedAssistantIndexes=[])]
    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["train_qlora.py", "--train", "train.jsonl", "--base-model", "m"]
    )
    with pytest.raises(RuntimeError, match="지도 턴 선택"):
        train_qlora.main()
    complete = json.loads((tmp_path / "complete.json").read_text("utf-8"))
    check = json.loads((tmp_path / "data-check.json").read_text("utf-8"))
    assert complete["ok"] is False
    assert check["ok"] is False and check["problems"][0]["index"] == 1
    assert not (tmp_path / "runtime-train.json").exists()  # 버전 검사·모델 로딩 전에 멈췄다


# ---- 선별 스크립트 -----------------------------------------------------------------------------


def test_screen_script_checks_versions_adapters_and_hashes() -> None:
    tree = _tree("screen_qlora.py")
    called = _called(tree)
    for needed in (
        "resume_refusal",
        "get_peft_model_state_dict",
        "load_file",
        "adapter_mismatch",
        "finish_reason",
        "version_drift",
    ):
        assert needed in called, needed
    assert {"wireSha256", "inputIdsSha256", "requestSha256"} <= _strings(tree)
    args = screen_qlora.parse_args(["--base-model", "m"])
    assert args.expected_versions == "{}" and args.allow_resume is False


def test_resume_refusal_follows_first_output_rule() -> None:
    assert screen_qlora.resume_refusal(False, False, False) is None
    assert screen_qlora.resume_refusal(True, True, True) is None
    for started, responses in ((True, False), (False, True)):
        reason = screen_qlora.resume_refusal(started, responses, False)
        assert reason and reason.startswith("첫 출력 원칙: 자동 재시작 금지")


def _screen_dir(tmp_path: Path) -> Path:
    (tmp_path / "screen").mkdir()
    (tmp_path / "screen" / "responses.jsonl").write_text('{"arm":"base","taskId":"s-1"}\n')
    (tmp_path / "complete.json").write_text(json.dumps({"ok": True, "checkpoints": []}))
    return tmp_path


def test_screen_main_refuses_restart_without_touching_outputs(tmp_path, monkeypatch) -> None:
    work = _screen_dir(tmp_path)
    before = (work / "screen" / "responses.jsonl").read_bytes()
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["screen_qlora.py", "--base-model", "m"])
    with pytest.raises(SystemExit) as exc:
        screen_qlora.main()
    assert exc.value.code == 3
    done = json.loads((work / "screen-complete.json").read_text("utf-8"))
    assert done["ok"] is False and "첫 출력 원칙: 자동 재시작 금지" in done["error"]
    assert done["files"][0]["path"] == "screen/responses.jsonl"
    assert (work / "screen" / "responses.jsonl").read_bytes() == before


def test_screen_refusal_keeps_existing_completion(tmp_path, monkeypatch) -> None:
    work = _screen_dir(tmp_path)
    finished = json.dumps({"ok": True, "files": []})
    (work / "screen-complete.json").write_text(finished)
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["screen_qlora.py", "--base-model", "m"])
    with pytest.raises(SystemExit):
        screen_qlora.main()
    assert (work / "screen-complete.json").read_text() == finished


def test_adapter_mismatch_compares_every_tensor() -> None:
    same = {"a": [1, 2], "b": [3]}
    assert screen_qlora.adapter_mismatch(same, dict(same), lambda x, y: x == y) == []
    problems = screen_qlora.adapter_mismatch(
        {"a": [1], "b": [2], "c": [3]}, {"a": [1], "b": [9], "d": [4]}, lambda x, y: x == y
    )
    assert len(problems) == 3
    assert any("c" in p for p in problems) and any("d" in p for p in problems)
    assert any("b" in p for p in problems)


# ---- 끝 이유 (서빙·선별 공통) -------------------------------------------------------------------


@pytest.mark.parametrize("module", [serve_qlora, screen_qlora])
def test_finish_reason_uses_eos_token(module) -> None:
    stops = module.eos_ids([1, 106], None)
    assert stops == {1, 106}
    assert module.eos_ids(106, 1) == {1, 106}
    assert module.eos_ids(None, None) == set()
    assert module.eos_ids(True, None) == set()
    assert module.finish_reason([5, 6, 106], stops, 3) == "stop"  # 상한에서 EOS로 끝남
    assert module.finish_reason([5, 6, 7], stops, 3) == "length"
    assert module.finish_reason([5, 1], stops, 8) == "stop"
    assert module.finish_reason([5, 6], stops, 8) == "stop"


def test_serve_script_reports_eos_finish_and_wire_hash() -> None:
    tree = _tree("serve_qlora.py")
    assert {"finish_reason", "eos_ids"} <= _called(tree)
    assert "wireSha256" in _strings(tree)


# ---- 공장이 만드는 명령의 인자 ------------------------------------------------------------------


def _script_args(line: str, name: str) -> list[str]:
    tokens = shlex.split(line)
    argv = tokens[tokens.index(name) + 1 :]
    return ["1800000000" if t == "$deadline" else t for t in argv]


def _printf_body(command: str) -> str:
    tokens = shlex.split(command)
    return tokens[tokens.index("%s") + 1]


@pytest.mark.parametrize("drift", [False, True])
def test_gemma_command_flags_parse_in_remote_scripts(tmp_path: Path, drift: bool) -> None:
    dataset, ds_dir = make_dataset(tmp_path)
    provider = gemma(FakeRemoteHost(), allow_version_drift=drift)
    files = resolve_dataset_files(request_for(tmp_path, dataset, ds_dir))
    command = provider._command(files, "/workspace/cfp/job", 3600, True)
    body = _printf_body(command)
    assert body == provider._job_script(files, 3600, True)
    lines = body.splitlines()
    [train_line] = [line for line in lines if " train_qlora.py " in line]
    train = train_qlora.parse_args(_script_args(train_line, "train_qlora.py"))
    assert train.train == ["train.jsonl"] and train.validation
    assert train.deadline_epoch == 1800000000.0
    assert train.allow_version_drift is drift
    assert json.loads(train.expected_versions) == provider.settings.expected_versions
    [screen_line] = [line for line in lines if " screen_qlora.py " in line]
    inner = screen_line.split("then ", 1)[1].split("; src=", 1)[0]
    screen = screen_qlora.parse_args(_script_args(inner, "screen_qlora.py"))
    assert screen.include_base is True and screen.allow_resume is False


def test_serve_start_command_flags_parse(tmp_path: Path) -> None:
    folder = tmp_path / "adapter"
    folder.mkdir()
    for name in ADAPTER_FILES:
        (folder / name).write_bytes(b"x")
    cfg = ProviderConfig(
        adapter="gemma_qlora",
        model="unsloth/gemma-4-31B-it-unsloth-bnb-4bit",
        extra={"remote_host": FakeRemoteHost()},
    )
    session = GpuInferenceSession(cfg, tmp_path / "record", {"gemma_sft": folder})
    body = _printf_body(session._start_command())
    [line] = [line for line in body.splitlines() if line.startswith("exec ")]
    args = serve_qlora.parse_args(_script_args(line, "serve_qlora.py"))
    assert args.adapter == ["gemma_sft=adapters/gemma_sft"]
    assert json.loads(args.expected_versions) == session.settings.expected_versions
