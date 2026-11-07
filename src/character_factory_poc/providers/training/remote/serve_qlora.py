"""원격 GPU에서 학습 어댑터로 답을 만드는 작은 HTTP 서버 (공장은 실행하지 않는다).

S10 평가가 SHORT_GEMMA_SFT 조건의 답을 받을 때 쓴다(D-0077). 로딩과 생성 규칙은 머스크 N3b 서빙
(원본 musk_grounded_chat/generation/gemma.py)에서 옮겼다: 버전 검사 직후 unsloth를 torch·peft보다
먼저 import, FastModel 4bit 기반 + PeftModel 어댑터, gemma-4-thinking 템플릿, thinking 끔, 끝 이유는
마지막 토큰이 EOS면 stop·아니고 출력 상한에 닿았으면 length. 127.0.0.1에만 열고 공장은 SSH 포트
전달로 붙는다. 요청은 한 번에 하나씩 처리한다(GPU 하나).

원본과 다른 것: 생성 마감 시각(StoppingCriteria)과 'error' 끝 이유가 없고, 원본 서빙 매니페스트
대신 --adapter 이름=경로로 어댑터를 여럿 올려 요청마다 고른다. 응답에 wire 문자열 sha256을 담는다.

POST /v1/generate {adapter, messages, seed, max_new_tokens, temperature, top_p, top_k}
GET  /health

무거운 패키지는 main 안에서만 불러오므로 이 모듈은 GPU 없이 import해 순수 함수를 시험할 수 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Iterable, Sequence
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", action="append", default=[], help="이름=경로")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--chat-template", default="gemma-4-thinking")
    parser.add_argument("--max-seq-length", type=int, default=12288)
    parser.add_argument("--port", type=int, default=18123)
    parser.add_argument("--expected-versions", default="{}")
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, path)


def eos_ids(config_eos: Any, tokenizer_eos: Any) -> set[int]:
    """generation_config.eos_token_id(정수·목록·None)와 토크나이저 EOS를 합친다."""
    out: set[int] = set()
    for raw in (config_eos, tokenizer_eos):
        values = raw if isinstance(raw, list | tuple | set) else [raw]
        out.update(int(v) for v in values if isinstance(v, int) and not isinstance(v, bool))
    return out


def finish_reason(new_ids: Sequence[int], stop_ids: Iterable[int], max_new_tokens: int) -> str:
    """원본 gemma.py 123줄: 마지막 토큰이 EOS면 stop, 아니고 출력 상한에 닿았으면 length."""
    stops = set(stop_ids)
    if new_ids and new_ids[-1] in stops:
        return "stop"
    if len(new_ids) >= max_new_tokens:
        return "length"
    return "stop"


def main() -> None:
    args = parse_args()
    work = Path.cwd()
    state_path = work / "serve-state.json"
    write_json(state_path, {"phase": "loading", "time": time.time()})
    try:
        import importlib.metadata

        expected = json.loads(args.expected_versions or "{}")
        versions = {k: importlib.metadata.version(k) for k in expected}
        drift = {k: [expected[k], v] for k, v in versions.items() if v != expected[k]}
        if drift:
            raise RuntimeError(f"실행 환경 버전이 고정값과 다르다: {drift}")
        # Unsloth는 torch·peft보다 먼저 불러와야 패치가 적용된다(원본 worker.py 4줄과 같은 순서).
        from unsloth import FastModel
        from unsloth.chat_templates import get_chat_template

        write_json(state_path, {"phase": "loading_model", "time": time.time()})
        import torch
        from peft import PeftModel

        model, processor = FastModel.from_pretrained(
            model_name=args.base_model,
            revision=args.revision or None,
            max_seq_length=args.max_seq_length,
            load_in_4bit=True,
            full_finetuning=False,
        )
        processor = get_chat_template(processor, chat_template=args.chat_template)
        tok = getattr(processor, "tokenizer", processor)
        stop_ids = eos_ids(
            getattr(getattr(model, "generation_config", None), "eos_token_id", None),
            getattr(tok, "eos_token_id", None),
        )
        if not stop_ids:
            raise RuntimeError("EOS 토큰을 알 수 없어 끝 이유를 판정할 수 없다")
        adapters: dict[str, str] = {}
        loaded = False
        for spec in args.adapter:
            name, _, path = spec.partition("=")
            folder = (work / path).resolve()
            if not loaded:
                model = PeftModel.from_pretrained(
                    model, str(folder), adapter_name=name, is_trainable=False
                )
                loaded = True
            else:
                model.load_adapter(str(folder), adapter_name=name, is_trainable=False)
            adapters[name] = sha256_file(folder / "adapter_model.safetensors")
        FastModel.for_inference(model)
        model.eval()
    except BaseException as exc:  # noqa: BLE001
        write_json(
            state_path,
            {"phase": "failed", "error": f"{type(exc).__name__}: {exc}", "time": time.time()},
        )
        raise

    info = {
        "phase": "ready",
        "adapters": adapters,
        "versions": versions,
        "gpu": torch.cuda.get_device_name(0),
        "time": time.time(),
    }
    write_json(state_path, info)

    def generate(body: dict[str, Any]) -> dict[str, Any]:
        adapter = str(body.get("adapter") or "")
        messages = [{"role": m["role"], "content": m["content"]} for m in body["messages"]]
        wire = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        ids = tok(wire, add_special_tokens=False, return_tensors="pt")["input_ids"].to("cuda")
        max_new = int(body.get("max_new_tokens", 512))
        if ids.shape[1] + max_new > args.max_seq_length:
            raise ValueError(f"입력 {ids.shape[1]}토큰 + 출력 {max_new}토큰이 최대 길이를 넘는다")
        seed = int(body.get("seed", 3407))
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        kwargs = dict(
            input_ids=ids,
            attention_mask=torch.ones_like(ids),
            max_new_tokens=max_new,
            do_sample=True,
            temperature=float(body.get("temperature", 0.7)),
            top_p=float(body.get("top_p", 0.9)),
            top_k=int(body.get("top_k", 50)),
            use_cache=True,
        )
        started = time.time()
        with torch.inference_mode():
            if adapter == "base":
                with model.disable_adapter():
                    out = model.generate(**kwargs)
            else:
                if adapter not in adapters:
                    raise ValueError(f"올리지 않은 어댑터: {adapter}")
                model.set_adapter(adapter)
                out = model.generate(**kwargs)
        new = out[0, ids.shape[1] :].tolist()
        return {
            "text": tok.decode(new, skip_special_tokens=True).strip(),
            "finish": finish_reason(new, stop_ids, max_new),
            "inputTokens": int(ids.shape[1]),
            "outputTokens": len(new),
            "seconds": round(time.time() - started, 3),
            "adapter": adapter,
            "adapterSha256": adapters.get(adapter, ""),
            "wireSha256": hashlib.sha256(wire.encode("utf-8")).hexdigest(),
        }

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, info)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/v1/generate":
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                result = generate(body)
                with (work / "serve-requests.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "time": time.time(),
                                "ref": body.get("ref", ""),
                                "adapter": result["adapter"],
                                "outputTokens": result["outputTokens"],
                            }
                        )
                        + "\n"
                    )
                self._send(200, result)
            except Exception as exc:  # noqa: BLE001
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

        def log_message(self, format, *a):  # noqa: A002
            return

    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
