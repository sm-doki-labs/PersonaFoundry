"""외모 명세 읽기와 고정 (LLD §5.8, D-0042). appearance_rev = S2 rev(ar<k>).

S2는 사람 관문 없이 자동으로 고정되므로 G2 기록이 없다. 여기서는 `s2` 단계가 `APPROVED`인지와
그 `currentRev`를 본다. 옛 상태 파일(ar2를 G2로 승인한 캐릭터)은 `s2`도 이미 `APPROVED`라
그대로 읽히고, 혹시 `s2` 표시가 빠진 옛 파일은 G2 승인을 읽기 전용으로 되짚는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from acf.common.errors import GateNotApprovedError
from acf.common.schema import validate
from acf.contracts.hero import AppearanceSpec, HeroCandidate, HeroInputs
from acf.contracts.reference import MULTI_FIELDS, SINGLE_FIELDS
from acf.pipeline.context import Context

FORBIDDEN = [
    "문자·워터마크·로고",
    "실존 인물의 이름이나 사진을 생성 지시로 쓰지 않는다(D-0017)",
]


def load_candidates(rev_dir: Path) -> list[HeroCandidate]:
    """옛 `generate` rev의 기준 사진 시도 기록(읽기 전용)."""
    objs = json.loads((rev_dir / "candidates.json").read_text("utf-8"))
    return [validate("hero-candidate-v1", o) for o in objs]  # type: ignore[misc]


def load_inputs(rev_dir: Path) -> HeroInputs:
    """S2 실행 입력 고정본. 옛 기록에는 `basePhoto`가 없으므로 generate로 읽힌다."""
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


def appearance_rev(ctx: Context, cid: str) -> str:
    """외모 명세를 고정한 S2 rev. `s2` 승인이 기준이고 옛 G2 기록은 읽기만 한다."""
    state = ctx.state(cid)
    st = state.stage("s2")
    if st.status == "APPROVED" and st.currentRev:
        return st.currentRev
    g2 = state.gate("G2")
    if g2.status == "APPROVED" and g2.rev:
        return g2.rev
    raise GateNotApprovedError(
        f"{cid}: 외모 명세가 없다. G1 승인 뒤 S2를 돌린다(현재 s2 {st.status}). acf hero run {cid}"
    )


def load_appearance_spec(ctx: Context, cid: str) -> tuple[AppearanceSpec, Path]:
    """S2가 고정한 외모 명세와 기준 이미지 경로(S4·S5·S6 입력, D-0042)."""
    rev = appearance_rev(ctx, cid)
    rev_dir = ctx.character_dir(cid) / "s2-hero" / rev
    p = rev_dir / "appearance-spec.json"
    if not p.exists():
        raise GateNotApprovedError(f"{cid}: {rev}에 외모 명세 파일이 없다(appearance-spec.json)")
    spec = validate("appearance-spec-v1", json.loads(p.read_text("utf-8")))
    reference = spec.referenceImage  # type: ignore[union-attr]
    if reference is None:
        raise GateNotApprovedError(f"{cid}: {rev} 외모 명세에 기준 이미지가 없다")
    return spec, rev_dir / reference.path  # type: ignore[union-attr]
