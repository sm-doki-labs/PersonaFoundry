"""트윈의 비학습 G8. 채택 대상과 같은 장면의 비교 근거를 함께 제시한다."""

from __future__ import annotations

import html
import json
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError, NeedsInputError
from character_factory_poc.common.store import next_rev, read_json, write_manifest, write_once_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.pipeline.graph import BIND_EXISTING, PROMPT_ONLY, SOURCE
from character_factory_poc.pipeline.origin import read_model_mode, read_origin
from character_factory_poc.stages.s10_eval import blind
from character_factory_poc.stages.s10_eval.compare import build_comparison
from character_factory_poc.stages.s10_eval.prompt_only import ADOPTED, PROMPT_ONLY_FILE
from character_factory_poc.stages.s10_train.io import latest_rev, read_run

SCHEMA = "eval-twin-decision-v1"


def _inputs(ctx: Context, cid: str) -> dict:
    char_dir = ctx.character_dir(cid)
    mode = read_model_mode(char_dir)
    if read_origin(char_dir) != SOURCE or mode not in (PROMPT_ONLY, BIND_EXISTING):
        raise FactoryError("이 G8은 트윈의 PROMPT_ONLY·BIND_EXISTING 모드에서만 연다")
    state = ctx.state(cid)
    state.require_deps("s10")
    ho = state.stage("s9h")
    if ho.status != "APPROVED" or not ho.currentRev:
        raise FactoryError("승인된 s9h 비교 세트가 필요하다")
    summary_path = char_dir / "s9h-holdout" / ho.currentRev / "summary.json"
    summary = read_json(summary_path)
    source = state.gate("G0")
    if (
        source.status != "APPROVED"
        or summary["sourceRev"] != source.rev
        or not summary["sceneCount"]
    ):
        raise FactoryError("현재 G0 출처 묶음으로 s9h 비교 세트를 다시 만든다")
    prompt = char_dir / "s8-prompts" / (state.gate("G6").rev or "") / "long.md"
    if not prompt.is_file():
        raise FactoryError("G6이 승인한 긴 프롬프트(long.md)가 없다")
    adopted = ADOPTED
    binding = check = None
    shown = [prompt, summary_path, summary_path.with_name("scenes.jsonl")]
    shown.extend(
        p
        for p in (prompt.with_name("short.md"), prompt.with_name("source-plan.json"))
        if p.exists()
    )
    description = "연결 기록 없음. 사전 확인은 해당하지 않는다."
    if mode == BIND_EXISTING:
        tr = latest_rev(ctx, cid)
        paths = list(tr.glob("IMPORTED-mb*/training-run.json")) if tr else []
        if len(paths) != 1:
            raise NeedsInputError("BIND_EXISTING 연결 기록이 없다. 먼저 모델을 연결한다")
        run = read_run(paths[0])
        ref = run.modelBinding
        expected = Path("model-prep") / run.provider.removeprefix("IMPORTED-") / "binding.json"
        if (
            run.characterId != cid
            or run.status != "SUCCEEDED"
            or not ref
            or ref.ref != expected.as_posix()
        ):
            raise FactoryError("트윈 연결 기록이 올바른 채택 대상을 가리키지 않는다")
        adopted = ref.ref
        path = char_dir / expected
        check_path = path.with_name("preflight.json")
        binding, check = read_json(path), read_json(check_path)
        if binding != run.appliedConfig["binding"] or check != run.appliedConfig["preflight"]:
            raise FactoryError("가져온 연결 기록 또는 사전 확인 결과가 달라졌다")
        shown.extend([path, check_path, paths[0]])
        description = (
            f"연결 기록: {adopted} ({binding['ref']}@{binding['revision']}, "
            f"서빙: {binding['servingRoute']}). 사전 확인: {check['status']}. "
            + check.get("reason", "")
        )
    return {
        "schemaVersion": SCHEMA,
        "characterId": cid,
        "mode": mode,
        "sceneCount": summary["sceneCount"],
        "binding": binding,
        "preflight": check,
        "adoptOptions": [adopted],
        "reason": (
            f"{mode} · 비교 세트 {summary['sceneCount']}장면. {description} "
            "비교 보고는 순서 8의 평가 근거에 담겨 있다."
        ),
        "inputs": [
            {"ref": p.relative_to(char_dir).as_posix(), "sha256": sha256_file(p)} for p in shown
        ],
    }


def _page(doc: dict) -> str:
    esc = html.escape
    adopted = doc["adoptOptions"][0]
    details = ""
    if doc["binding"]:
        for label, obj in [
            ("모델 연결 기록", doc["binding"]),
            ("사전 확인 결과", doc["preflight"]),
        ]:
            content = json.dumps(obj, ensure_ascii=False, indent=2)
            details += f"<h2>{label}</h2><pre>{esc(content)}</pre>"
    answer = json.dumps({"decision": "SELECT", "adopted": adopted, "reviewer": "user"})
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>G8 모델 채택</title>'
        f"<h1>G8 모델 채택</h1><p>{esc(doc['reason'])}</p>{details}"
        f"<h2>채택할 조건</h2><p>{esc(adopted)}</p><pre>{esc(answer)}</pre>"
        "<p>채택하지 않으려면 REJECT를 선택한다.</p></html>"
    )


def run_s10_twin(ctx: Context, cid: str, *, models=None) -> Path:
    doc = _inputs(ctx, cid)
    root = ctx.character_dir(cid) / "s10-eval"
    state = ctx.state(cid)
    gate = state.gate("G8")
    if gate.status == "AWAITING_HUMAN" and gate.rev:
        folder = root / gate.rev
        path = folder / PROMPT_ONLY_FILE
        if path.is_file() and read_json(path) == doc:
            build_comparison(ctx, cid, folder, models=models)
            blind.refresh_page(folder)
            return folder
        raise FactoryError("열린 G8과 입력이 다르다. 이전 결정을 반려한 뒤 새 판을 연다")
    rev = next_rev(root, "ev")
    folder = root / rev
    state.transition("s10", "RUNNING", rev=rev)
    try:
        build_comparison(ctx, cid, folder, models=models)
    except Exception:
        state.transition("s10", "CHECK_FAILED", rev=rev, error="트윈 비교 평가 실패")
        raise
    # 기존 G8 읽기 화면은 prompt-only.json의 reason과 adoptOptions를 사용한다.
    write_once_json(folder / PROMPT_ONLY_FILE, doc)
    (folder / "gate-G8.html").write_text(blind.decorate(_page(doc), folder), encoding="utf-8")
    write_manifest(folder)
    state.transition("s10", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G8", "AWAITING_HUMAN", rev, None)
    return folder


def approve_twin(ctx: Context, cid: str, folder: Path, doc: dict, answer: dict) -> Path:
    decision = answer.get("decision")
    selected = []
    if decision == "SELECT":
        blind.verify_evidence(folder)
        if _inputs(ctx, cid) != doc:
            raise FactoryError("G8을 연 뒤 입력이 바뀌었다. 반려한 뒤 새 판을 연다")
        adopted = answer.get("adopted")
        if adopted not in doc["adoptOptions"]:
            raise FactoryError("G8에 표시한 채택 조건을 선택해야 한다")
        selected = [adopted]
    elif decision != "REJECT":
        raise FactoryError("트윈 G8 결정은 SELECT 또는 REJECT다")
    rec = write_gate_record(
        ctx.character_dir(cid),
        ctx.state(cid),
        gate="G8",
        rev=folder.name,
        stage_id="s10",
        shown=[folder / PROMPT_ONLY_FILE, folder / "gate-G8.html", *blind.evidence(folder)],
        decision=decision,
        reviewer=str(answer.get("reviewer", "user")),
        reasons=str(answer.get("reasons", "")),
        selections=selected,
        minutes=float(answer.get("minutes", 0) or 0),
    )
    ctx.ledger(cid).record_human(gate="G8", minutes=rec.minutes, ref=f"{cid}/{folder.name}")
    return folder
