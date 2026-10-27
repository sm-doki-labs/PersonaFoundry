"""G2 결정과 외모 명세 고정 (명세 §7, LLD §8.2, FR-12). appearance_rev = S2 rev(ar<k>)."""

from __future__ import annotations

import json
from pathlib import Path

from acf.common.canonical import sha256_file
from acf.common.errors import FactoryError, GateNotApprovedError
from acf.common.schema import dump, validate
from acf.common.store import write_manifest, write_once_json
from acf.contracts.hero import AppearanceSpec, HeroCandidate, HeroInputs
from acf.contracts.reference import MULTI_FIELDS, SINGLE_FIELDS
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record
from acf.stages.s1_reference.features import load_vocab
from acf.stages.s1_reference.page import summary

FORBIDDEN = [
    "문자·워터마크·로고",
    "실존 인물의 이름이나 사진을 생성 지시로 쓰지 않는다(D-0017)",
]


def load_candidates(rev_dir: Path) -> list[HeroCandidate]:
    objs = json.loads((rev_dir / "candidates.json").read_text("utf-8"))
    return [validate("hero-candidate-v1", o) for o in objs]  # type: ignore[misc]


def load_inputs(rev_dir: Path) -> HeroInputs:
    obj = json.loads((rev_dir / "inputs.json").read_text("utf-8"))
    return validate("hero-inputs-v1", obj)  # type: ignore[return-value]


def description_en(tags: dict, vocab: dict) -> str:
    out = []
    for f in (*SINGLE_FIELDS, *MULTI_FIELDS):
        if f in tags:
            group = vocab["single"] if f in SINGLE_FIELDS else vocab["multi"]
            vals = tags[f] if isinstance(tags[f], list) else [tags[f]]
            out += [group[f]["values"][v]["en"] for v in vals]
    return ", ".join(out)


def approve_g2(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    g = state.gate("G2")
    if g.status != "AWAITING_HUMAN" or not g.rev:
        raise FactoryError(f"{cid}: G2가 대기 상태가 아니다({g.status})")
    rev_dir = char_dir / "s2-hero" / g.rev
    candidates = load_candidates(rev_dir)
    ids = [c.candidateId for c in candidates]
    decision = answer["decision"]
    selections = list(answer.get("selections") or [])
    reasons = answer.get("reasons", "")
    if decision == "APPROVE":  # --auto-approve G2 (D-0015)
        selections = selections or [ids[0]]
        reasons = (reasons + " " if reasons else "") + f"첫 후보 {selections[0]}을 골랐다."
        decision = "SELECT"
    if decision == "SELECT":
        if len(selections) != 1 or selections[0] not in ids:
            raise FactoryError(
                f"G2 SELECT는 후보 하나를 selections에 담아야 한다({', '.join(ids)})"
            )
    elif decision in {"REJECT", "REQUEST_CHANGES"}:
        selections = []
    else:
        raise FactoryError(f"G2 결정은 SELECT·REQUEST_CHANGES·REJECT 중 하나다: {decision}")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G2",
        rev=g.rev,
        stage_id="s2",
        shown=[rev_dir / "candidates.json", rev_dir / "gate-G2.html"],
        decision=decision,
        reviewer=answer["reviewer"],
        reasons=reasons,
        selections=selections,
        minutes=float(answer.get("minutes", 0)),
        requested_changes=answer.get("requestedChanges"),
    )
    ctx.ledger(cid).record_human(gate="G2", minutes=rec.minutes, ref=f"{cid}/{g.rev}")
    if decision == "SELECT":
        chosen = next(c for c in candidates if c.candidateId == selections[0])
        inputs = load_inputs(rev_dir)
        vocab = load_vocab()
        spec = validate(
            "appearance-spec-v1",
            {
                "characterId": cid,
                "appearanceRev": g.rev,
                "sourceReferenceRev": inputs.sourceReferenceRev,
                "clusterId": inputs.clusterId,
                "scope": dump(inputs.scope),
                "tags": inputs.commonTags,
                "descriptionKo": summary(inputs.commonTags, vocab),
                "descriptionEn": description_en(inputs.commonTags, vocab),
                "referenceImage": {
                    "id": chosen.candidateId,
                    "path": chosen.filePath,
                    "sha256": sha256_file(rev_dir / chosen.filePath),
                },
                "referencePreviews": [dump(r) for r in inputs.referencePreviews],
                "heroPrompt": chosen.prompt,
                "forbidden": FORBIDDEN,
                "notes": reasons,
            },
        )
        write_once_json(rev_dir / "appearance-spec.json", dump(spec))
        write_manifest(rev_dir)
    return rev_dir


def load_appearance_spec(ctx: Context, cid: str) -> tuple[AppearanceSpec, Path]:
    """G2에서 고정한 외모 명세와 기준 이미지 경로(S4·S5·S6 입력)."""
    g = ctx.state(cid).gate("G2")
    if g.status != "APPROVED" or not g.rev:
        raise GateNotApprovedError(f"{cid}: G2 승인이 필요하다(현재 {g.status})")
    rev_dir = ctx.character_dir(cid) / "s2-hero" / g.rev
    p = rev_dir / "appearance-spec.json"
    if not p.exists():
        raise GateNotApprovedError(f"{cid}: G2가 후보를 고르지 않았다(외모 명세 없음)")
    spec = validate("appearance-spec-v1", json.loads(p.read_text("utf-8")))
    return spec, rev_dir / spec.referenceImage.path  # type: ignore[union-attr]
