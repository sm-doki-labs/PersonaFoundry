"""원격 GPU에서 도는 QLoRA 학습 스크립트 (텍스트로만 둔다, 공장은 실행하지 않는다).

GemmaQLoraProvider.submit이 이 파일을 원격 작업 폴더로 보내 실행한다. 학습 설정과 데이터 검사는
결과를 낸 머스크 N3b 학습 워커(2026-10-30, Gemma 4 31B, L40S 236 step; 원본 worker.py·
masking.py)에서 옮겼다(D-0077). 원본 코드를 그대로 쓰지 않고 공장 데이터 형식에 맞춰 바꾼 곳이 있다.

원본에서 옮긴 것
- 버전 검사 직후 unsloth를 torch·transformers·trl·datasets·peft보다 먼저 import한다(패치 순서).
- FastModel + gemma-4-thinking 템플릿, 언어 층만 LoRA(r16/α32, dropout 0)
- 응답 턴만 손실: Gemma 4 표시 "<|turn>user\n" / "<|turn>model\n", 그 위에 선택 턴 지도
  (select_labels)
- 학습 전 검사: 모든 행의 input_ids가 로컬 토큰화와 같은지, BOS가 첫 토큰 한 번뿐인지, 최대 길이
  이하인지, data_collator가 모든 샘플의 라벨을 바꾸지 않는지(패딩 방향 고려) 확인하고
  data-check.json·collator-label-parity-confirmed.json을 쓴다. 하나라도 어긋나면 학습하지 않는다.
- constant_with_warmup(5%), adamw_8bit, weight decay 0.001, bf16, packing 없음
- 0.5 epoch 단위 체크포인트를 step 목표로 저장한다. 마감(--deadline-epoch)에 닿아 멈추면
  checkpoints/budget-partial을 저장하고 complete.json에 ok:true, finished:false로 남긴다.
- 실행 환경 버전이 고정값과 다르면 학습 전에 멈춘다.

원본과 다른 것
- 검증 세트: --validation으로 받은 공장 파일 전부(validation_base·validation_augmented)의 Trainer
  eval_loss 한 값을 기록만 한다. 원본은 eval_loss를 r2 validation-original(23개)로 재고, 묶음별 토큰
  가중 손실과 탐침 생성을 체크포인트마다 따로 했다. 여기에는 둘 다 없다(선별은 screen_qlora.py).
- 선택 턴 지도는 행에 "supervisedAssistantIndexes"가 있을 때만 쓴다. 없거나 null이면 모든 assistant
  턴을 지도한다. 원본은 모든 행의 선택을 별도 supervision.json으로 받았다. 검증 행에도 같은 규칙을
  적용해 eval_loss가 학습과 같은 턴을 잰다(원본 Trainer eval_loss에는 선택이 없었다).
- 토큰 대조: 원본은 미리 계산한 expected-token-hashes.json과도 맞췄다. 공장은 기대 해시를 보내지
  않으므로 여기서는 원격 토크나이저의 로컬 토큰화와만 맞춘다.
- 체크포인트는 목표 step의 on_step_end에서 저장한다(원본은 on_evaluate에서 저장하고 측정까지 했다).

완료는 이 스크립트가 마지막에 쓰는 complete.json으로만 알린다. 무거운 패키지는 main 안에서만
불러오므로 이 모듈은 GPU 없이 import해 순수 함수를 시험할 수 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

USER_PART = "<|turn>user\n"
MODEL_PART = "<|turn>model\n"
TURN_END = "<turn|>"
SELECT_FIELD = "supervisedAssistantIndexes"
IGNORE_INDEX = -100
DEADLINE_RESERVE_SECONDS = 300.0
PARTIAL_ID = "budget-partial"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="append", required=True)
    parser.add_argument("--validation", action="append", default=[])
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--checkpoint-epochs", default="0.5,1,1.5,2")
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.0)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--lr-scheduler", default="constant_with_warmup")
    parser.add_argument("--warmup-ratio", type=float, default=0.05)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--optim", default="adamw_8bit")
    parser.add_argument("--weight-decay", type=float, default=0.001)
    parser.add_argument("--chat-template", default="gemma-4-thinking")
    parser.add_argument("--expected-versions", default="{}")
    parser.add_argument("--allow-version-drift", action="store_true")
    parser.add_argument("--deadline-epoch", type=float, default=0.0)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def append_json(path: Path, payload: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def files_under(root: Path, base: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out.append(
                {
                    "path": path.relative_to(base).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return out


def read_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in paths:
        for line in Path(name).read_text("utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def clean_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in row["messages"]]


def version_drift(expected: dict[str, str], actual: dict[str, str]) -> dict[str, list[str]]:
    return {k: [v, actual.get(k, "")] for k, v in expected.items() if actual.get(k) != v}


# ---- 선택 턴 지도 (원본 masking.py) -----------------------------------------------------------


def assistant_count(messages: list[dict[str, Any]]) -> int:
    return sum(1 for m in messages if m.get("role") == "assistant")


def selected_assistants(row: dict[str, Any]) -> list[int]:
    """행이 지도할 assistant 턴 순번(0부터, assistant 메시지끼리 센다).

    supervisedAssistantIndexes가 없거나 null이면 모든 assistant 턴이다. 빈 목록(지도 0)·중복·음수·
    정수가 아닌 값·범위 밖 순번은 오류로 막는다.
    """
    count = assistant_count(row.get("messages") or [])
    if count == 0:
        raise ValueError("assistant 메시지가 없어 지도할 턴이 없다")
    raw = row.get(SELECT_FIELD)
    if raw is None:
        return list(range(count))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{SELECT_FIELD}가 비었다: 지도할 턴이 0개인 행은 학습하지 않는다")
    if any(type(i) is not int or i < 0 for i in raw) or len(set(raw)) != len(raw):
        raise ValueError(f"{SELECT_FIELD}는 겹치지 않는 0 이상 정수 목록이어야 한다: {raw}")
    if max(raw) >= count:
        raise ValueError(f"{SELECT_FIELD} {max(raw)}가 assistant 턴 수 {count}를 넘는다")
    return list(raw)


def select_labels(
    input_ids: Sequence[int],
    labels: Sequence[int],
    selected: Sequence[int],
    user_head: Sequence[int],
    model_head: Sequence[int],
    turn_end_id: int,
    expected_count: int,
) -> list[int]:
    """입력 토큰은 그대로 두고 선택하지 않은 응답 턴의 라벨만 -100으로 바꾼다(원본 masking.py).

    train_on_responses_only가 만든 라벨을 model 머리 뒤 구간마다 assistant 턴으로 나눈다. 턴 수가
    expected_count와 같고, 턴마다 지도 토큰이 있고 지도된 턴 끝(<turn|>)이 정확히 하나인지 확인한다.
    """
    ids, labels = list(input_ids), list(labels)
    user_head, model_head = list(user_head), list(model_head)
    selected = list(selected)
    if len(ids) != len(labels) or not ids:
        raise ValueError("input_ids와 labels 길이가 다르거나 비었다")
    if not user_head or not model_head or user_head == model_head:
        raise ValueError("user·model 머리 토큰은 비지 않고 서로 달라야 한다")
    if not selected or any(type(i) is not int or i < 0 for i in selected):
        raise ValueError("지도할 assistant 순번은 0 이상 정수 하나 이상이어야 한다")
    if len(set(selected)) != len(selected):
        raise ValueError("지도할 assistant 순번이 겹친다")
    if type(expected_count) is not int or expected_count < 1:
        raise ValueError("assistant 턴 수가 필요하다")
    if any(
        label != IGNORE_INDEX and label != token for token, label in zip(ids, labels, strict=True)
    ):
        raise ValueError("라벨은 입력 토큰과 같거나 -100이어야 한다")
    spans: list[list[int]] = []
    current: int | None = None
    i = 0
    while i < len(ids):
        head = None
        if ids[i : i + len(user_head)] == user_head:
            head = user_head
        elif ids[i : i + len(model_head)] == model_head:
            head = model_head
        if head is not None:
            if any(v != IGNORE_INDEX for v in labels[i : i + len(head)]):
                raise ValueError("역할 머리 토큰이 지도되었다")
            if head is model_head:
                spans.append([])
                current = len(spans) - 1
            else:
                current = None
            i += len(head)
            continue
        if labels[i] != IGNORE_INDEX:
            if current is None:
                raise ValueError("assistant 턴 밖의 토큰이 지도되었다")
            spans[current].append(i)
        i += 1
    if len(spans) != expected_count or any(not span for span in spans):
        raise ValueError(
            f"assistant 구간 수 {len(spans)}가 메시지 수 {expected_count}와 다르거나 빈 구간이 있다"
        )
    if any(n >= len(spans) for n in selected):
        raise ValueError("지도할 assistant 순번이 범위를 벗어났다")
    if any(sum(1 for j in span if ids[j] == turn_end_id) != 1 for span in spans):
        raise ValueError("assistant 구간마다 지도된 턴 끝 토큰이 정확히 하나여야 한다")
    out = [IGNORE_INDEX] * len(labels)
    for n in selected:
        for j in spans[n]:
            out[j] = labels[j]
    return out


# ---- 학습 전 데이터 검사 (원본 worker.py 46~61줄) -----------------------------------------------


def token_problems(
    ids: Sequence[int], local_ids: Sequence[int], bos_id: int | None, max_len: int
) -> list[str]:
    """학습 행 하나의 토큰 문제. 빈 목록이면 통과다."""
    ids, local_ids = list(ids), list(local_ids)
    problems: list[str] = []
    if ids != local_ids:
        problems.append("input_ids가 로컬 토큰화(add_special_tokens=False)와 다르다")
    if bos_id is None or not ids or ids[0] != bos_id or ids.count(bos_id) != 1:
        problems.append("BOS가 첫 토큰 한 번이 아니다")
    if len(ids) > max_len:
        problems.append(f"길이 {len(ids)}토큰이 최대 {max_len}토큰을 넘는다")
    return problems


def padded_labels(labels: Sequence[int], length: int, padding_side: str) -> list[int]:
    """collator가 길이 length로 패딩했을 때 나와야 하는 라벨. 잘렸으면 오류다."""
    pad = length - len(labels)
    if pad < 0:
        raise ValueError("collator 출력이 원래 라벨보다 짧다(잘림)")
    if padding_side == "left":
        return [IGNORE_INDEX] * pad + list(labels)
    return list(labels) + [IGNORE_INDEX] * pad


# ---- 체크포인트·마감 -------------------------------------------------------------------------


def checkpoint_targets(max_steps: int, epochs: float, wanted: list[float]) -> dict[int, float]:
    """0.5 epoch 같은 목표를 step 번호로 바꾼다. 같은 step으로 겹치면 뒤의 목표를 남긴다."""
    targets: dict[int, float] = {}
    for epoch in wanted:
        step = max(1, round(epoch * max_steps / epochs))
        targets[min(step, max_steps)] = epoch
    return targets


def tag(epoch: float) -> str:
    return "epoch-" + format(epoch, "g")


def deadline_reached(
    deadline_epoch: float, now: float, reserve: float = DEADLINE_RESERVE_SECONDS
) -> bool:
    """마감 여유(reserve초)를 남기고 멈출 때인지. 마감이 0이면 마감이 없다."""
    return deadline_epoch > 0 and now > deadline_epoch - reserve


def training_finished(global_step: int, max_steps: int, epoch: float | None, epochs: float) -> bool:
    return max_steps > 0 and global_step >= max_steps and float(epoch or 0.0) >= epochs - 1e-3


def partial_checkpoint(
    global_step: int, epoch: float | None, checkpoints: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """마감으로 멈춘 학습의 마지막 상태를 체크포인트로 남길 기록. epoch는 실제 state.epoch다.

    한 step도 못 했으면 남길 것이 없고, 방금 목표 체크포인트를 저장한 step이면 같은 가중치이므로
    다시 저장하지 않는다.
    """
    if global_step <= 0:
        return None
    if checkpoints and checkpoints[-1]["step"] == global_step:
        return None
    return {
        "checkpointId": PARTIAL_ID,
        "epoch": float(epoch or 0.0),
        "step": int(global_step),
        "ref": f"checkpoints/{PARTIAL_ID}",
        "budgetStopped": True,
    }


def main() -> None:
    args = parse_args()
    work = Path.cwd()
    complete = work / "complete.json"
    wanted = sorted({float(v) for v in args.checkpoint_epochs.split(",") if v.strip()})
    expected_versions = json.loads(args.expected_versions or "{}")
    started = time.time()

    def state(phase: str, **extra: Any) -> None:
        write_json(work / "state.json", {"phase": phase, "time": time.time(), **extra})
        print("STATE", phase, extra, flush=True)

    try:
        # 무거운 패키지를 불러오기 전에 지도 선택부터 확인한다(값싼 오류를 먼저 낸다).
        raws = {"train": read_rows(args.train), "validation": read_rows(args.validation)}
        if not raws["train"]:
            raise RuntimeError("학습 행이 없다")
        selections: dict[str, list[list[int]]] = {}
        bad: list[dict[str, Any]] = []
        for split, rows in raws.items():
            selections[split] = []
            for index, row in enumerate(rows):
                try:
                    selections[split].append(selected_assistants(row))
                except ValueError as exc:
                    selections[split].append([])
                    bad.append({"split": split, "index": index, "error": str(exc)})
        if bad:
            write_json(
                work / "data-check.json",
                {"ok": False, "selectionErrors": len(bad), "problems": bad[:20]},
            )
            raise RuntimeError(f"지도 턴 선택이 잘못된 행이 {len(bad)}개다(첫 행: {bad[0]})")

        import importlib.metadata

        versions = {k: importlib.metadata.version(k) for k in expected_versions}
        drift = version_drift(expected_versions, versions)
        write_json(work / "runtime-train.json", {"versions": versions, "drift": drift})
        if drift and not args.allow_version_drift:
            raise RuntimeError(f"실행 환경 버전이 고정값과 다르다: {drift}")

        # Unsloth는 torch·transformers·trl·datasets·peft보다 먼저 불러와야 패치가 적용된다
        # (원본 worker.py 4줄). 아래 state() 호출이 두 import 묶음을 갈라 정렬기가 섞지 않게 한다.
        from unsloth import FastModel
        from unsloth.chat_templates import get_chat_template, train_on_responses_only

        state("loading_model")
        import torch
        from datasets import Dataset
        from transformers import TrainerCallback, set_seed
        from trl import SFTConfig, SFTTrainer

        set_seed(args.seed)
        model, processor = FastModel.from_pretrained(
            model_name=args.base_model,
            revision=args.revision or None,
            max_seq_length=args.max_seq_length,
            load_in_4bit=True,
            full_finetuning=False,
        )
        processor = get_chat_template(processor, chat_template=args.chat_template)
        tok = getattr(processor, "tokenizer", processor)
        model = FastModel.get_peft_model(
            model,
            finetune_vision_layers=False,
            finetune_language_layers=True,
            finetune_attention_modules=True,
            finetune_mlp_modules=True,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            random_state=args.seed,
            use_gradient_checkpointing="unsloth",
        )
        trainable = [n for n, p in model.named_parameters() if p.requires_grad]
        if not trainable or not all("lora_" in n for n in trainable):
            raise RuntimeError("LoRA 밖의 파라미터가 학습 대상이다")

        def render(messages: list[dict[str, str]]) -> str:
            return processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False, enable_thinking=False
            )

        texts = {split: [render(clean_messages(r)) for r in rows] for split, rows in raws.items()}
        local = {
            split: [tok(t, add_special_tokens=False)["input_ids"] for t in items]
            for split, items in texts.items()
        }
        too_long = [i for i, ids in enumerate(local["train"]) if len(ids) > args.max_seq_length]
        if too_long:
            raise RuntimeError(
                f"학습 대화 {len(too_long)}개가 최대 길이 {args.max_seq_length}토큰을 넘는다"
                f"(앞 5개 index {too_long[:5]}). 잘라서 학습하지 않는다"
            )
        datasets = {s: Dataset.from_dict({"text": t}) for s, t in texts.items() if t}
        has_validation = "validation" in datasets
        config = SFTConfig(
            output_dir=str(work / "trainer-state"),
            dataset_text_field="text",
            dataset_num_proc=1,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.learning_rate,
            warmup_ratio=args.warmup_ratio,
            logging_steps=5,
            optim=args.optim,
            weight_decay=args.weight_decay,
            lr_scheduler_type=args.lr_scheduler,
            seed=args.seed,
            data_seed=args.seed,
            report_to="none",
            save_strategy="no",
            eval_strategy="steps" if has_validation else "no",
            eval_steps=10**6,
            prediction_loss_only=True,
            bf16=True,
            max_length=args.max_seq_length,
            packing=False,
        )
        state("preparing_dataset")
        trainer = SFTTrainer(
            model=model,
            tokenizer=processor,
            train_dataset=datasets["train"],
            eval_dataset=datasets.get("validation"),
            args=config,
        )
        trainer = train_on_responses_only(
            trainer, instruction_part=USER_PART, response_part=MODEL_PART
        )

        # 선택 턴 지도: 행 순서대로 라벨을 고친다. 순서가 어긋나면 지도가 다른 행에 붙으므로
        # 행 수부터 맞춰 본다.
        user_head = tok(USER_PART, add_special_tokens=False)["input_ids"]
        model_head = tok(MODEL_PART, add_special_tokens=False)["input_ids"]
        turn_end_id = tok.convert_tokens_to_ids(TURN_END)

        def splits() -> list[tuple[str, Any]]:
            out = [("train", trainer.train_dataset)]
            if has_validation:
                out.append(("validation", trainer.eval_dataset))
            return out

        def masker(split: str):
            def mask(row: dict[str, Any], index: int) -> dict[str, list[int]]:
                source = raws[split][index]
                try:
                    labels = select_labels(
                        row["input_ids"],
                        row["labels"],
                        selections[split][index],
                        user_head,
                        model_head,
                        turn_end_id,
                        assistant_count(source["messages"]),
                    )
                except ValueError as exc:
                    raise ValueError(f"{split} {index}행 지도 선택 실패: {exc}") from exc
                return {"labels": labels}

            return mask

        for split, ds in splits():
            if len(ds) != len(raws[split]):
                raise RuntimeError(
                    f"{split} 데이터셋 행 수 {len(ds)}가 입력 {len(raws[split])}행과 다르다"
                )
        trainer.train_dataset = trainer.train_dataset.map(
            masker("train"), with_indices=True, load_from_cache_file=False
        )
        if has_validation:
            trainer.eval_dataset = trainer.eval_dataset.map(
                masker("validation"), with_indices=True, load_from_cache_file=False
            )

        # 토큰 대조: 실제 학습 행이 로컬 토큰화와 같고 BOS 한 번·최대 길이 이하·지도 토큰 있음.
        bos_id = tok.bos_token_id
        checks: dict[str, Any] = {}
        problems: list[dict[str, Any]] = []
        for split, ds in splits():
            supervised, longest = 0, 0
            for index, row in enumerate(ds):
                ids = list(row["input_ids"])
                labels = list(row["labels"])
                for problem in token_problems(
                    ids, local[split][index], bos_id, args.max_seq_length
                ):
                    problems.append({"split": split, "index": index, "problem": problem})
                count = sum(1 for v in labels if v != IGNORE_INDEX)
                if count == 0:
                    problems.append(
                        {"split": split, "index": index, "problem": "지도 토큰이 0개다"}
                    )
                supervised += count
                longest = max(longest, len(ids))
            checks[split] = {
                "records": len(raws[split]),
                "supervisedTokens": supervised,
                "maxTokens": longest,
                "selectedRows": sum(1 for r in raws[split] if r.get(SELECT_FIELD) is not None),
            }
        write_json(
            work / "data-check.json",
            {
                "ok": not problems,
                "allRecordsMatchLocalTokenization": not problems,
                "bosTokenId": bos_id,
                "maxSeqLength": args.max_seq_length,
                "supervisionField": SELECT_FIELD,
                **checks,
                "problemCount": len(problems),
                "problems": problems[:20],
            },
        )
        if problems:
            raise RuntimeError(f"학습 행 검사 실패 {len(problems)}건(첫 건: {problems[0]})")

        # collator가 모든 샘플의 선택 라벨을 그대로 두는지(패딩 방향 고려) 실제 collator로 확인한다.
        padding_side = str(getattr(tok, "padding_side", "right") or "right")
        parity: dict[str, int] = {}
        for split, ds in splits():
            parity[split] = 0
            for index, sample in enumerate(ds):
                packed = trainer.data_collator([dict(sample)])
                actual = packed["labels"][0].tolist()
                try:
                    expected_labels = padded_labels(
                        list(sample["labels"]), len(actual), padding_side
                    )
                except ValueError as exc:
                    raise RuntimeError(f"collator가 {split} {index}행을 잘랐다") from exc
                if actual != expected_labels:
                    raise RuntimeError(f"collator가 {split} {index}행의 선택 라벨을 바꿨다")
                parity[split] += 1
        write_json(
            work / "collator-label-parity-confirmed.json",
            {
                "records": parity,
                "paddingSide": padding_side,
                "selectedLabelsPreservedInTrainingCollator": True,
                "time": time.time(),
            },
        )

        targets: dict[int, float] = {}
        checkpoints: list[dict[str, Any]] = []
        losses: dict[str, float] = {}
        stop = {"deadline": False}

        class Monitor(TrainerCallback):
            def on_train_begin(self, train_args, state_, control, **kwargs):
                targets.clear()
                targets.update(checkpoint_targets(state_.max_steps, args.epochs, wanted))
                write_json(
                    work / "checkpoint-plan.json",
                    {
                        "maxSteps": state_.max_steps,
                        "targets": {str(k): v for k, v in targets.items()},
                    },
                )

            def on_log(self, train_args, state_, control, logs=None, **kwargs):
                append_json(
                    work / "metrics.jsonl",
                    {
                        "time": time.time(),
                        "step": state_.global_step,
                        "epoch": state_.epoch,
                        **(logs or {}),
                    },
                )
                if logs and "eval_loss" in logs:
                    losses[str(state_.global_step)] = float(logs["eval_loss"])
                state("training", step=state_.global_step, epoch=state_.epoch)

            def on_step_end(self, train_args, state_, control, **kwargs):
                if state_.global_step in targets:
                    if has_validation:
                        control.should_evaluate = True
                    planned = targets[state_.global_step]
                    folder = work / "checkpoints" / tag(planned)
                    model.save_pretrained(str(folder))
                    processor.save_pretrained(str(folder))
                    checkpoints.append(
                        {
                            "checkpointId": tag(planned),
                            "epoch": planned,
                            "actualEpoch": state_.epoch,
                            "step": int(state_.global_step),
                            "ref": f"checkpoints/{tag(planned)}",
                        }
                    )
                if deadline_reached(args.deadline_epoch, time.time()):
                    stop["deadline"] = True
                    control.should_training_stop = True

        trainer.add_callback(Monitor())
        if deadline_reached(args.deadline_epoch, time.time()):
            raise TimeoutError("학습을 시작하기 전에 마감 여유가 없다")
        if has_validation:
            state("baseline_validation")
            base_metrics = trainer.evaluate()
            losses["0"] = float(base_metrics.get("eval_loss", float("nan")))
        state("training")
        result = trainer.train()
        epoch_now = float(trainer.state.epoch or 0.0)
        finished = training_finished(
            trainer.state.global_step, trainer.state.max_steps, epoch_now, args.epochs
        )
        if not finished:
            # 마감에 닿아 멈췄다: 마지막 상태를 budget-partial로 남긴다(원본 worker.py 104줄).
            partial = partial_checkpoint(trainer.state.global_step, epoch_now, checkpoints)
            if partial is not None:
                folder = work / partial["ref"]
                model.save_pretrained(str(folder))
                processor.save_pretrained(str(folder))
                checkpoints.append(partial)
        for item in checkpoints:
            loss = losses.get(str(item["step"]))
            if loss is not None:
                item["validationLoss"] = loss
        stop_reason = None if finished else ("deadline" if stop["deadline"] else "incomplete")
        write_json(
            work / "training.json",
            {
                "globalStep": trainer.state.global_step,
                "maxSteps": trainer.state.max_steps,
                "epoch": epoch_now,
                "finished": finished,
                "stopReason": stop_reason,
                "trainingLoss": result.training_loss,
                "validationLosses": losses,
                "runtimeSeconds": time.time() - started,
                "gpu": torch.cuda.get_device_name(0),
            },
        )
        if not checkpoints:
            raise RuntimeError("저장된 체크포인트가 없다")
        logs = [
            work / n
            for n in (
                "training.json",
                "data-check.json",
                "collator-label-parity-confirmed.json",
                "runtime-train.json",
                "checkpoint-plan.json",
                "metrics.jsonl",
            )
        ]
        payload = {
            "ok": True,
            "finished": finished,
            "stopReason": stop_reason,
            "modelBindingRef": checkpoints[-1]["ref"],
            "checkpoints": checkpoints,
            "files": [
                *files_under(work / "checkpoints", work),
                *[
                    {"path": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                    for p in logs
                    if p.exists()
                ],
            ],
            "appliedConfig": {
                "baseModel": args.base_model,
                "revision": args.revision,
                "epochs": args.epochs,
                "checkpointEpochs": wanted,
                "loraR": args.lora_r,
                "loraAlpha": args.lora_alpha,
                "learningRate": args.learning_rate,
                "lrScheduler": args.lr_scheduler,
                "optim": args.optim,
                "maxSeqLength": args.max_seq_length,
                "seed": args.seed,
                "chatTemplate": args.chat_template,
                "runtimeVersions": versions,
                "supervisionField": SELECT_FIELD,
                "selectedRows": checks["train"]["selectedRows"],
                "supervisedTokens": checks["train"]["supervisedTokens"],
                "globalStep": trainer.state.global_step,
                "epochReached": epoch_now,
                # 공장은 appliedConfig만 옮겨 담으므로 마감 중단 여부를 여기에도 남긴다.
                "finished": finished,
                "stopReason": stop_reason,
            },
            "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        write_json(complete, payload)
        state(
            "complete" if finished else "partial", step=trainer.state.global_step, epoch=epoch_now
        )
        print("DONE", flush=True)
    except BaseException as exc:  # noqa: BLE001 - 원격 실패 사유를 complete.json에 남긴다
        write_json(
            complete,
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        raise


if __name__ == "__main__":
    main()
