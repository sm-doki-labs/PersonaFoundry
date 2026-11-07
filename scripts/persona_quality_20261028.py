# ruff: noqa: E501
# Preserve full Korean instructions and inline HTML strings.
"""Authorized one-character live experiment. Default: dry run, --execute required."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
ROOT = REPO / "runs/experiments/20261028-persona-quality"
RAW = ROOT / "evidence"
RAW.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:10100/v1"
GEN = "gpt-6.1-sol"
CHAT = "google-antigravity/gemini-3.8-flash"
JUDGE = "anthropic/claude-sonnet-5"


def put(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        f.write(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=2))


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


class Recorded:
    name = "openai_compat"

    def __init__(self, model):
        self.model = model

    def complete(self, request):
        from character_factory_poc.providers.base import ChatResponse

        k = f"{request.stage}-{time.time_ns()}"
        body = dict(
            model=self.model,
            messages=[dataclasses.asdict(m) for m in request.messages],
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
        )
        if request.response_json:
            body["response_format"] = {"type": "json_object"}
        if self.model.startswith(("gpt-", "google-", "anthropic/")):
            body["reasoning_effort"] = "low"
        wire = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        put(RAW / f"{k}.request.json", wire)
        t = time.monotonic()
        with httpx.Client(timeout=240) as c:
            r = c.post(
                BASE + "/chat/completions",
                content=wire.encode(),
                headers={"Content-Type": "application/json"},
            )
        put(RAW / f"{k}.response.json", r.text)
        elapsed = int((time.monotonic() - t) * 1000)
        meta = dict(
            key=k,
            ref=request.ref,
            stage=request.stage,
            kind=request.kind,
            requestedModel=self.model,
            requestSha256=sha(wire),
            responseSha256=sha(r.text),
            status=r.status_code,
            elapsedMs=elapsed,
        )
        try:
            d = r.json()
            meta.update(usage=d.get("usage"), returnedModel=d.get("model"))
        except ValueError:
            d = {}
        put(RAW / f"{k}.meta.json", meta)
        r.raise_for_status()
        text = d["choices"][0]["message"]["content"] or ""
        if not text:
            raise RuntimeError(f"empty response: {k}")
        u = d.get("usage") or {}
        print(f"CALL {request.stage} {request.ref} {self.model} {elapsed}ms", flush=True)
        return ChatResponse(
            text,
            u.get("prompt_tokens"),
            u.get("completion_tokens"),
            elapsed,
            d.get("model", self.model),
            self.name,
        )


def ctx():
    from character_factory_poc.pipeline.context import Context

    c = Context.load(ROOT, execute=True)
    c.use_models(Recorded(GEN), Recorded(JUDGE))
    return c


def bootstrap():
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.s1_reference.run import run_s1
    from character_factory_poc.stages.s2_hero.run import run_s2
    from character_factory_poc.stages.s3_plan.draft import new_character
    from character_factory_poc.stages.s3_plan.seed import write_seed
    from tests.support.synthetic import RANKING, scout_features

    c = ctx()
    cid = new_character(c, "persona-quality")
    put(ROOT / "character-id.txt", cid)
    # Appearance is explicitly synthetic and excluded from quality claims.
    fake = FakeTextModel()
    fake.add("AGENT", lambda req: scout_features(RANKING))
    c.use_models(fake)
    run_s1(c, cid, RANKING)
    approve_gate(
        c,
        cid,
        "G1",
        dict(
            decision="SELECT",
            selections=["c2"],
            referencePreviews=["c2-1"],
            reviewer="agent",
            reasons=["외모는 합성 입력이며 품질 판정에서 제외한다."],
        ),
    )
    run_s2(c, cid)
    write_seed(
        c,
        cid,
        dict(
            personality="상대가 망설이면 작은 실행안을 먼저 내지만, 명시적인 거절과 자기 일의 마감은 지킨다. 관심은 말보다 구체적인 행동으로 보인다.",
            job="동네 독립 책방 직원",
            age=26,
            gender="female",
            background="서울의 작은 독립 책방에서 일하며 혼자 산다. 퇴근길 산책과 손으로 쓰는 독서 메모를 좋아한다.",
            notes="평범한 한국 연애 대화 앱의 허구 인물. 자연스러운 해체 반말과 짧은 호흡을 쓴다.",
        ),
    )
    print(cid)


def generation(stage):
    cid = (ROOT / "character-id.txt").read_text().strip()
    c = ctx()
    if stage == "s3":
        from character_factory_poc.stages.s3_plan.variants import run_s3_variants

        print(run_s3_variants(c, cid))
    if stage == "s7":
        from character_factory_poc.stages.s7_traits.sheet import run_s7

        print(run_s7(c, cid))
    if stage == "s8":
        from character_factory_poc.stages.s8_prompts.build import run_s8

        print(run_s8(c, cid, []))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["bootstrap", "s3", "s7", "s8"])
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    if not a.execute:
        calls = dict(bootstrap=0, s3=6, s7=5, s8=5)[a.stage]
        plan = dict(
            stage=a.stage,
            dryRun=True,
            maxCalls=calls,
            billing="unknown: relay does not expose authoritative rates",
            sensitivityRatesUSDPerMillion=dict(input=[1, 10], output=[5, 50]),
            note="Scenario rates, not vendor prices. Generation envelope per call: 20000 input + 12000 output tokens; high scenario max $0.80/call. No media or training calls.",
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    elif a.stage == "bootstrap":
        bootstrap()
    else:
        generation(a.stage)
