"""원격 GPU에서 도는 QLoRA 학습 스크립트 (텍스트로만 둔다, 공장은 실행하지 않는다).

GemmaQLoraProvider.submit이 이 파일을 원격 작업 폴더로 보내고 train.log로 실행한다. 완료는
이 스크립트가 마지막에 쓰는 complete.json으로만 알린다. 학습 설정 기본값은 학습 가이드 §11과
LLD §8.9를 따르며, 공급자가 명령 인자로 넘긴 값을 그대로 쓴다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="append", required=True)
    parser.add_argument("--validation", action="append", default=[])
    parser.add_argument("--output", default="adapter")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.0)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--lr-scheduler", default="linear")
    parser.add_argument("--warmup-ratio", type=float, default=0.05)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--save-epochs", default="1,2,3")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_complete(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def files_under(root: Path, base: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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


def main() -> None:
    args = parse_args()
    work = Path.cwd()
    output = work / args.output
    output.mkdir(parents=True, exist_ok=True)
    complete = work / "complete.json"
    save_epochs = {int(v) for v in args.save_epochs.split(",") if v.strip()}
    try:
        # 학습용 GPU가 있을 때만 불러온다. 공장의 테스트는 이 파일을 import하지 않는다.
        from datasets import load_dataset
        from transformers import TrainerCallback
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastLanguageModel
        from unsloth.chat_templates import train_on_responses_only

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.base_model,
            revision=args.revision or None,
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            use_gradient_checkpointing="unsloth",
            random_state=args.seed,
        )

        def formatting(example: dict[str, Any]) -> dict[str, str]:
            return {
                "text": tokenizer.apply_chat_template(
                    example["messages"], tokenize=False, add_generation_prompt=False
                )
            }

        train = load_dataset("json", data_files=args.train, split="train").map(formatting)
        validation = None
        if args.validation:
            validation = load_dataset("json", data_files=args.validation, split="train").map(
                formatting
            )
        config = SFTConfig(
            output_dir=str(work / "trainer"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.learning_rate,
            lr_scheduler_type=args.lr_scheduler,
            warmup_ratio=args.warmup_ratio,
            max_seq_length=args.max_seq_length,
            seed=args.seed,
            save_strategy="no",
            logging_steps=10,
            report_to="none",
            dataset_text_field="text",
        )
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=train,
            eval_dataset=validation,
            args=config,
        )
        # assistant 답변에만 손실을 준다(가이드 §11).
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<start_of_turn>user\n",
            response_part="<start_of_turn>model\n",
        )
        checkpoints: list[dict[str, Any]] = []

        class SaveEpochs(TrainerCallback):
            """1·2·3 epoch 어댑터를 저장한다. epoch 값은 trainer가 보고한 원값만 쓴다."""

            def on_epoch_end(self, train_args, state, control, **kwargs):
                epoch = int(round(float(state.epoch or 0)))
                if epoch not in save_epochs:
                    return control
                target = work / "checkpoints" / f"epoch-{epoch}"
                model.save_pretrained(str(target))
                tokenizer.save_pretrained(str(target))
                checkpoints.append(
                    {
                        "checkpointId": f"epoch-{epoch}",
                        "epoch": epoch,
                        "step": int(state.global_step),
                        "ref": f"checkpoints/epoch-{epoch}",
                    }
                )
                return control

        trainer.add_callback(SaveEpochs())
        trainer.train()
        trainer.save_model(str(output))
        tokenizer.save_pretrained(str(output))
        payload = {
            "ok": True,
            "adapterDir": args.output,
            "modelBindingRef": args.output,
            "files": [
                *files_under(output, work),
                *files_under(work / "checkpoints", work),
            ],
            "checkpoints": checkpoints,
            "appliedConfig": {
                "baseModel": args.base_model,
                "revision": args.revision,
                "epochs": args.epochs,
                "loraR": args.lora_r,
                "loraAlpha": args.lora_alpha,
                "maxSeqLength": args.max_seq_length,
                "seed": args.seed,
                "saveEpochs": sorted(save_epochs),
            },
            "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        write_complete(complete, payload)
        print("DONE", flush=True)
    except Exception as exc:  # noqa: BLE001 - 원격 실패 사유를 complete.json에 남긴다
        write_complete(
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
