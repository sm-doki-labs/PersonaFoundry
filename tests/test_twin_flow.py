"""트윈 앞단 통합 흐름 (D-0128~D-0130): 오케스트레이터만으로 s0 → G0 → s2·s3 동시 → G1s·G3 대기."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_vision import FakeVisionModel
from tests.test_source_s0 import _good_digest, _twin, _write_pack
from tests.test_twin_s3 import CANARY, LINES, _answer

APPROVE = {"decision": "APPROVE", "reviewer": "u"}


def _pack(tmp: Path) -> Path:
    path = _write_pack(tmp)
    pack = read_json(path)
    pack["knownFacts"] = {"age": "41", "gender": "female", "job": "제본사", "relation": "가족"}
    ok, encoded = cv2.imencode(".png", np.full((24, 16, 3), 90, np.uint8))
    assert ok
    path.with_name("mom.png").write_bytes(encoded.tobytes())
    pack["photos"] = [{"path": "mom.png", "origin": "가족 사진"}]
    path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    lines = []
    for i, (q, a) in enumerate((*LINES, ("내일 봐요.", CANARY)), 1):
        lines += [
            f"--------------- 2026년 10월 {i}일 토요일 ---------------",
            f"[나] [오전 9:00] {q}",
            f"[엄마] [오전 9:05] {a}",
        ]
    path.with_name("mom.txt").write_text("\n".join(lines), encoding="utf-8")
    return path


def test_orchestrator_runs_twin_front_and_waits_human_gates(tmp_path: Path) -> None:
    ctx = Context.load(tmp_path, execute=True)
    model = FakeTextModel()
    model.add("AGENT", _good_digest)
    ctx.use_models(model)
    ctx.use_vision(FakeVisionModel(responder=lambda req: {"faceShape": "oval"}))
    cid = _twin(ctx)

    log = run_until(ctx, cid, RunOptions(until="G3", source_pack=_pack(tmp_path), max_parallel=2))
    assert "G0" in log.waiting
    assert ctx.state(cid).stage("s2").status == "PENDING"

    approve_gate(ctx, cid, "G0", APPROVE)
    model.add("AGENT", _answer)
    log = run_until(ctx, cid, RunOptions(until="G3", max_parallel=2))
    assert {"G1s", "G3"} <= set(log.waiting)
    assert any({"s2", "s3"} <= set(wave) for wave in log.waves), log.waves
    state = ctx.state(cid)
    assert state.gate("G1s").status == "AWAITING_HUMAN"
    assert state.gate("G3").status == "AWAITING_HUMAN"
    # 비교 세트(s9h)는 G0만 기다리고 관문 없이 끝난다. 다른 산출물과 섞이지 않는다.
    log = run_until(ctx, cid, RunOptions(until="s9h", max_parallel=2))
    assert ctx.state(cid).stage("s9h").status == "APPROVED"

    approve_gate(ctx, cid, "G1s", APPROVE)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "u"})
    state = ctx.state(cid)
    assert state.stage("s2").status == "APPROVED" and state.stage("s3").status == "APPROVED"
    state.require_deps("s7")  # 뒤쪽 단계는 오리지널과 같은 의존으로 풀린다
    state.require_deps("s4a")
