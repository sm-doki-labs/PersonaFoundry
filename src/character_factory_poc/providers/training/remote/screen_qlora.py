"""원격 GPU에서 체크포인트별 첫 답변을 만드는 선별 스크립트 (공장은 실행하지 않는다).

학습이 끝난 뒤 같은 작업 폴더에서 돈다. 머스크 N3b 선별 워커(원본 screen_worker.py)처럼 기반 모델을
한 번 올리고 체크포인트 어댑터를 차례로 붙여, 검증 대화에서 뽑은 요청의 첫 출력만 남긴다(다시 뽑기
없음). 선택은 공장이 회수한 뒤 결함 지표와 짝 판정으로 한다(D-0077). 손실로 고르지 않는다.

원본에서 옮긴 것
- 버전 검사(--expected-versions) 직후 unsloth를 torch·peft보다 먼저 import한다.
- 첫 출력 원칙: screen/generation-started.json이나 screen/responses.jsonl이 이미 있으면
  --allow-resume 없이 다시 돌지 않는다(screen-complete.json ok:false, 이미 있으면 건드리지 않음).
- 어댑터를 붙인 뒤 adapter_model.safetensors와 올라간 state dict의 텐서가 모두 같은지 확인한다.
- 기반 모델(base) 조건은 어떤 어댑터보다 먼저 만든다.
- 응답 턴마다 요청 wire 문자열과 input_ids의 sha256을 남긴다.

원본과 다른 것
- 요청을 하나씩 순서대로 만든다(원본은 왼쪽 패딩 묶음 생성과 패딩 자체 검사, 실패 때 순차 대체).
- 원본은 요청 파일에 든 기대 wire·input_ids 해시와 맞춰 봤다. 공장 요청에는 기대 해시가 없어
  해시를 기록만 한다.
- 끝 이유는 마지막 토큰이 EOS면 stop, 아니고 출력 상한에 닿았으면 length다(서빙과 같은 규칙).
  연속 대화는 이전 턴의 자기 첫 답을 다음 턴 이력에 넣고, 빈 답·stop 아닌 끝에서 그 대화를 멈춘다.
- 어댑터가 도착하기를 기다리지 않는다. 학습의 complete.json에 적힌 체크포인트만 쓴다.

무거운 패키지는 main 안에서만 불러오므로 이 모듈은 GPU 없이 import해 순수 함수를 시험할 수 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FIRST_OUTPUT_REFUSAL = "첫 출력 원칙: 자동 재시작 금지"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", default="screen/requests.jsonl")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--chat-template", default="gemma-4-thinking")
    parser.add_argument("--max-seq-length", type=int, default=8192)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--include-base", action="store_true")
    parser.add_argument("--deadline-epoch", type=float, default=0.0)
    parser.add_argument("--expected-versions", default="{}")
    parser.add_argument(
        "--allow-resume",
        action="store_true",
        help="이미 만든 첫 출력을 두고 남은 요청만 이어 만든다(사람이 명시할 때만)",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def version_drift(expected: dict[str, str], actual: dict[str, str]) -> dict[str, list[str]]:
    return {k: [v, actual.get(k, "")] for k, v in expected.items() if actual.get(k) != v}


def resume_refusal(started_exists: bool, responses_exist: bool, allow_resume: bool) -> str | None:
    """이미 생성을 시작했던 폴더에서 다시 돌려는지. 거절할 때 이유를 돌려준다."""
    if allow_resume or not (started_exists or responses_exist):
        return None
    found = "screen/responses.jsonl" if responses_exist else "screen/generation-started.json"
    return f"{FIRST_OUTPUT_REFUSAL} ({found}이 이미 있다. 이어 만들려면 --allow-resume)"


def eos_ids(config_eos: Any, tokenizer_eos: Any) -> set[int]:
    """generation_config.eos_token_id(정수·목록·None)와 토크나이저 EOS를 합친다."""
    out: set[int] = set()
    for raw in (config_eos, tokenizer_eos):
        values = raw if isinstance(raw, list | tuple | set) else [raw]
        out.update(int(v) for v in values if isinstance(v, int) and not isinstance(v, bool))
    return out


def finish_reason(new_ids: Sequence[int], stop_ids: Iterable[int], max_new_tokens: int) -> str:
    """마지막 토큰이 EOS면 stop, 아니고 출력 상한에 닿았으면 length, 그 밖은 stop."""
    stops = set(stop_ids)
    if new_ids and new_ids[-1] in stops:
        return "stop"
    if len(new_ids) >= max_new_tokens:
        return "length"
    return "stop"


def adapter_mismatch(
    expected: dict[str, Any], actual: dict[str, Any], equal: Callable[[Any, Any], bool]
) -> list[str]:
    """파일의 어댑터 텐서와 모델에 올라간 텐서를 비교한 문제 목록. 비면 같다."""
    problems = [f"모델에 없는 텐서: {k}" for k in sorted(set(expected) - set(actual))]
    problems += [f"파일에 없는 텐서: {k}" for k in sorted(set(actual) - set(expected))]
    problems += [
        f"값이 다른 텐서: {k}"
        for k in sorted(set(expected) & set(actual))
        if not equal(expected[k], actual[k])
    ]
    return problems


def response_files(responses: Path) -> list[dict[str, Any]]:
    if not responses.exists():
        return []
    return [
        {
            "path": "screen/responses.jsonl",
            "bytes": responses.stat().st_size,
            "sha256": sha256_file(responses),
        }
    ]


def main() -> None:
    args = parse_args()
    work = Path.cwd()
    out_dir = work / "screen"
    done_path = work / "screen-complete.json"
    responses = out_dir / "responses.jsonl"
    started_marker = out_dir / "generation-started.json"

    refusal = resume_refusal(started_marker.exists(), responses.exists(), args.allow_resume)
    if refusal:
        # 이미 끝난 선별 기록은 덮지 않는다. 기록이 없을 때만 실패로 남긴다.
        if not done_path.exists():
            write_json(
                done_path,
                {
                    "ok": False,
                    "error": refusal,
                    "files": response_files(responses),
                    "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
                },
            )
        print("SCREEN_REFUSED", refusal, flush=True)
        raise SystemExit(3)

    try:
        train = json.loads((work / "complete.json").read_text("utf-8"))
        if not train.get("ok"):
            raise RuntimeError("학습이 성공하지 않아 선별을 하지 않는다")
        tasks = [
            json.loads(line)
            for line in (work / args.requests).read_text("utf-8").splitlines()
            if line.strip()
        ]
        done: set[tuple[str, str]] = set()
        if responses.exists():
            for line in responses.read_text("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    done.add((row["arm"], row["taskId"]))

        import importlib.metadata

        expected_versions = json.loads(args.expected_versions or "{}")
        versions = {k: importlib.metadata.version(k) for k in expected_versions}
        drift = version_drift(expected_versions, versions)
        write_json(work / "runtime-screen.json", {"versions": versions, "drift": drift})
        if drift:
            raise RuntimeError(f"실행 환경 버전이 고정값과 다르다: {drift}")

        # Unsloth는 torch·peft보다 먼저 불러와야 패치가 적용된다(원본 screen_worker.py 6줄).
        from unsloth import FastModel
        from unsloth.chat_templates import get_chat_template

        print("STATE loading_model", flush=True)
        import torch
        from peft import PeftModel, get_peft_model_state_dict
        from safetensors.torch import load_file

        model, processor = FastModel.from_pretrained(
            model_name=args.base_model,
            revision=args.revision or None,
            max_seq_length=args.max_seq_length,
            load_in_4bit=True,
            full_finetuning=False,
        )
        processor = get_chat_template(processor, chat_template=args.chat_template)
        tok = getattr(processor, "tokenizer", processor)
        model.eval()
        stop_ids = eos_ids(
            getattr(getattr(model, "generation_config", None), "eos_token_id", None),
            getattr(tok, "eos_token_id", None),
        )
        if not stop_ids:
            raise RuntimeError("EOS 토큰을 알 수 없어 끝 이유를 판정할 수 없다")

        def generate(messages: list[dict[str, str]], seed: int) -> dict[str, Any]:
            wire = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            id_list = tok(wire, add_special_tokens=False)["input_ids"]
            hashes = {
                "wireSha256": sha256_text(wire),
                "inputIdsSha256": sha256_text(json.dumps(id_list)),
            }
            if len(id_list) + args.max_new_tokens > args.max_seq_length:
                return {
                    "text": "",
                    "finish": "context",
                    "inputTokens": len(id_list),
                    "outputTokens": 0,
                    **hashes,
                }
            ids = torch.tensor([id_list], dtype=torch.long, device="cuda")
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            with torch.inference_mode():
                out = model.generate(
                    input_ids=ids,
                    attention_mask=torch.ones_like(ids),
                    max_new_tokens=args.max_new_tokens,
                    do_sample=True,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    top_k=args.top_k,
                    use_cache=True,
                )
            new = out[0, ids.shape[1] :].tolist()
            return {
                "text": tok.decode(new, skip_special_tokens=True).strip(),
                "finish": finish_reason(new, stop_ids, args.max_new_tokens),
                "inputTokens": len(id_list),
                "outputTokens": len(new),
                **hashes,
            }

        arms: list[tuple[str, str | None]] = []
        if args.include_base:
            arms.append(("base", None))
        arms += [(c["checkpointId"], c["ref"]) for c in train["checkpoints"]]
        peft_loaded = False
        loads: list[dict[str, Any]] = []
        count = 0
        out_dir.mkdir(parents=True, exist_ok=True)
        marker = {"time": time.time(), "planned": len(tasks) * len(arms), "noRedraw": True}
        if started_marker.exists():
            with (out_dir / "resumes.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**marker, "alreadyDone": len(done)}) + "\n")
        else:
            write_json(started_marker, marker)
        for name, ref in arms:
            if ref is None:
                if peft_loaded:
                    raise RuntimeError("기반 모델 조건은 어댑터를 붙이기 전에 만들어야 한다")
            else:
                path = (work / ref).resolve()
                weights = path / "adapter_model.safetensors"
                adapter_name = name.replace("-", "_").replace(".", "p")
                if not peft_loaded:
                    model = PeftModel.from_pretrained(
                        model, str(path), adapter_name=adapter_name, is_trainable=False
                    )
                    peft_loaded = True
                else:
                    model.load_adapter(str(path), adapter_name=adapter_name, is_trainable=False)
                model.set_adapter(adapter_name)
                for param in model.parameters():
                    param.requires_grad_(False)
                model.eval()
                # 원본 screen_worker.py 72~74줄: 파일과 올라간 어댑터 텐서가 모두 같아야 한다.
                expected = load_file(str(weights))
                actual = get_peft_model_state_dict(model, adapter_name=adapter_name)
                problems = adapter_mismatch(
                    expected,
                    actual,
                    lambda a, b: torch.equal(a.to(b.device, dtype=b.dtype), b),
                )
                if problems:
                    raise RuntimeError(
                        f"어댑터 {name}의 텐서가 파일과 다르다 {len(problems)}건: {problems[:3]}"
                    )
                loads.append(
                    {
                        "arm": name,
                        "sha256": sha256_file(weights),
                        "tensors": len(actual),
                        "allEqual": True,
                        "active": list(getattr(model, "active_adapters", []) or []),
                    }
                )
                del expected, actual
            for task in tasks:
                if (name, task["taskId"]) in done:
                    continue
                if args.deadline_epoch and time.time() > args.deadline_epoch - 300:
                    raise TimeoutError("선별 시간 상한에 닿았다")
                messages = [dict(m) for m in task["messages"]]
                turns: list[dict[str, Any]] = []
                users = task.get("userTurns") or [None]
                for n, user in enumerate(users, start=1):
                    if user is not None:
                        messages.append({"role": "user", "content": user})
                    result = generate(messages, int(task["seed"]) * 100 + n)
                    turns.append({"turn": n, "user": user or messages[-1]["content"], **result})
                    count += 1
                    if not result["text"] or result["finish"] != "stop":
                        break
                    messages.append({"role": "assistant", "content": result["text"]})
                request_sha = sha256_text(json.dumps(task, ensure_ascii=False, sort_keys=True))
                with responses.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "arm": name,
                                "taskId": task["taskId"],
                                "kind": task["kind"],
                                "requestSha256": request_sha,
                                "turns": turns,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                write_json(
                    work / "screen-state.json",
                    {
                        "arm": name,
                        "task": task["taskId"],
                        "generations": count,
                        "time": time.time(),
                    },
                )
        write_json(
            done_path,
            {
                "ok": True,
                "arms": [a for a, _ in arms],
                "adapterLoads": loads,
                "generations": count,
                "resumed": bool(done),
                "runtimeVersions": versions,
                "files": response_files(responses),
                "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        print("SCREEN_DONE", flush=True)
    except BaseException as exc:  # noqa: BLE001
        write_json(
            done_path,
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "files": response_files(responses),
                "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        raise


if __name__ == "__main__":
    main()
