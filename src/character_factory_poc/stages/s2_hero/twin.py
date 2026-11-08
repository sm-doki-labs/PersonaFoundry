"""받은 사진으로 트윈 기준 얼굴을 정한다. G1s 전에는 외모 명세를 고정하지 않는다."""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.errors import CheckFailed, FactoryError, NeedsInputError
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    verify_manifest,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.common import GateDecision, RequestedChange
from character_factory_poc.contracts.hero import AppearanceSpec, HeroInputs, IdentityCheck, ImageRef
from character_factory_poc.contracts.reference import RankingScope
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import render_gate_page, write_gate_record
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.providers.base import VisionRequest
from character_factory_poc.stages.s0_source.run import load_approved_source
from character_factory_poc.stages.s1_reference.features import load_vocab
from character_factory_poc.stages.s1_reference.page import summary
from character_factory_poc.stages.s2_hero.approve import description_en

STAGE_DIR = "s2-hero"
OPTIONS = "photo-options.json"


def _photo(folder: Path, src: Path, photo_id: str, expected: str) -> ImageRef:
    if src.resolve().name == "holdout.jsonl":
        raise CheckFailed("s2", ["비교 세트는 사진으로 쓸 수 없다"])
    data = src.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise CheckFailed("s2", [f"{photo_id}: G0 승인 때와 사진 해시가 다르다"])
    # 원본과 그 해시는 보존한다. S4/S5가 내용을 그대로 .png에 복사하므로
    # 실제 참조에는 방향을 반영하고 메타데이터를 뺀 PNG 픽셀을 쓴다.
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if image is None:
        raise CheckFailed("s2", [f"{photo_id}: 사진을 열 수 없다"])
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise CheckFailed("s2", [f"{photo_id}: PNG 변환 실패"])
    write_once_bytes(folder / "originals" / photo_id, data)
    rel = f"references/{photo_id}.png"
    pixels = png.tobytes()
    write_once_bytes(folder / rel, pixels)
    return ImageRef(id=photo_id, path=rel, sha256=hashlib.sha256(pixels).hexdigest())


def _describe(vision, folder, ref, vocab, ledger_ref) -> dict[str, str]:
    allowed = {k: list(v["values"]) for k, v in vocab["single"].items()}
    request = VisionRequest(
        stage="s2",
        ref=ledger_ref,
        images=(("기준 사진 후보", str(folder / ref.path)),),
        prompt=(
            "사진 속 한 사람에게 보이는 외형만 아래 어휘에서 골라 JSON 객체로 답한다. "
            "키마다 값 하나만 쓴다. 보이지 않거나 확실하지 않은 특징은 생략한다. "
            "한 사람을 묘사할 수 없으면 {}를 반환한다. 신원·이름·성격은 추정하지 않는다.\n"
            + json.dumps(allowed)
        ),
    )
    raw = vision.judge(request).text
    try:
        tags = json.loads(raw)
    except ValueError:
        tags = None
    if (
        not isinstance(tags, dict)
        or not tags
        or any(k not in allowed or v not in allowed[k] for k, v in tags.items())
    ):
        raise CheckFailed("s2", [f"{ref.id}: 사진 설명은 허용된 외형 태그로만 작성해야 한다"])
    return tags


def _page(cid: str, rev: str, specs: list[AppearanceSpec]) -> str:
    page = render_gate_page(
        title="G1s 기준 사진 확인",
        subject_id=cid,
        gate="G1s",
        rev=rev,
        sections=[
            ("기준 사진 선택", "본인과 닮았는지 확인하고, 외형 설명이 맞는 사진을 고르세요.")
        ],
    )
    choices = []
    for i, spec in enumerate(specs):
        ref = spec.referenceImage
        choices.append(
            f'<label><input type="radio" name="photo" value="{ref.id}"'
            f"{' checked' if i == 0 else ''}> 사진 {i + 1}{' (기본)' if i == 0 else ''} · {ref.id}"
            f'<br><img src="{ref.path}" alt="후보 사진 {i + 1}" '
            f'style="max-width:min(100%,22rem);max-height:24rem">'
            f"<br>{escape(spec.descriptionKo)}<br>{escape(spec.descriptionEn)}</label>"
        )
    # 공통 관문 폼의 승인 동작에 선택한 사진 ID를 실어 보낸다.
    return page.replace("<h2>결정</h2>", "".join(choices) + "<h2>결정</h2>").replace(
        "const t=JSON.stringify(o,null,2);",
        """if(o.decision==='APPROVE'){
        const p=document.querySelector('input[name="photo"]:checked');
        if(!p.defaultChecked){o.decision='SELECT';o.selections=[p.value];}}
        const t=JSON.stringify(o,null,2);""",
    )


def run_s2_twin(ctx: Context, cid: str) -> Path:
    char_dir = ctx.character_dir(cid)
    if read_origin(char_dir) != SOURCE:
        raise FactoryError(f"{cid}: 트윈 캐릭터에만 G1s가 있다")
    state = ctx.state(cid)
    state.require_deps("s2")
    pack, index, _ = load_approved_source(ctx, cid)
    if not pack.photos:
        raise NeedsInputError("기준 사진이 없다. 사진이 있는 출처 묶음으로 G0 승인을 받는다")
    if not ctx.execute:
        raise FactoryError("트윈 기준 사진 설명에는 --execute가 필요하다")
    if [p.path for p in pack.photos] != [p.get("path") for p in index.photos]:
        raise CheckFailed("s2", ["출처 묶음과 G0 사진 목록이 다르다"])
    budget = ctx.budget()
    budget.check_plan([CallPlan("s2", "기준 사진별 외형 설명", len(pack.photos), None)])
    vision = ctx.vision_model(cid, budget)
    vocab = load_vocab()
    rev = next_rev(char_dir / STAGE_DIR, "ar")
    folder = char_dir / STAGE_DIR / rev
    state.transition("s2", "RUNNING", rev=rev)
    try:
        folder.mkdir(parents=True, exist_ok=False)
        refs = [
            _photo(folder, Path(p.path), f"photo{i:03}", approved["sha256"])
            for i, (p, approved) in enumerate(zip(pack.photos, index.photos, strict=True), 1)
        ]
        specs = []
        for ref in refs:
            tags = _describe(vision, folder, ref, vocab, f"{cid}/{rev}/{ref.id}")
            specs.append(
                AppearanceSpec(
                    characterId=cid,
                    appearanceRev=rev,
                    # 기존 계약은 rf<숫자>만 받는다. 실제 출처 sp 판도 별도로 기록한다.
                    sourceReferenceRev="rf" + index.sourceRev.removeprefix("sp"),
                    clusterId="source-photos",
                    scope=RankingScope(
                        characterGender="any",
                        ageRange="unspecified",
                        artStyle="photographic",
                        appearanceOrigin="unspecified",
                    ),
                    tags=tags,
                    descriptionKo=summary(tags, vocab),
                    descriptionEn=description_en(tags, vocab),
                    referenceImage=ref,
                    referencePreviews=[ref],
                    heroPrompt="Use the selected reference photograph as the facial reference.",
                    forbidden=["문자·워터마크·로고"],
                    basePhoto="picked",
                    identityCheck=IdentityCheck(status="SKIPPED"),
                    notes=f"G0 {index.sourceRev}에서 받은 사진. 닮음은 G1s에서 사람이 확인한다.",
                )
            )
        write_once_json(
            folder / OPTIONS,
            {
                "sourceRev": index.sourceRev,
                "originalSha256": {
                    r.id: p["sha256"] for r, p in zip(refs, index.photos, strict=True)
                },
                "options": [dump(s) for s in specs],
            },
        )
        write_once_text(folder / "gate-G1s.html", _page(cid, rev, specs))
        write_manifest(folder)
    except Exception as exc:
        state.transition("s2", "CHECK_FAILED", rev=rev, error=str(exc))
        raise
    state.transition("s2", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G1s", "AWAITING_HUMAN", rev, None)
    return folder


class _Answer(BaseModel):
    decision: GateDecision
    reviewer: str = "user"
    minutes: float = 0
    reasons: str = ""
    requestedChanges: list[RequestedChange] = Field(default_factory=list)
    selections: list[str] = Field(default_factory=list)


def approve_g1s(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    gate = state.gate("G1s")
    st = state.stage("s2")
    if (
        read_origin(char_dir) != SOURCE
        or not gate.rev
        or gate.rev != st.currentRev
        or gate.status != "AWAITING_HUMAN"
        or st.status != "AWAITING_HUMAN"
    ):
        raise FactoryError(f"{cid}: G1s가 대기 상태가 아니다")
    try:
        a = _Answer.model_validate(answer)
    except ValidationError:
        raise FactoryError("G1s 답의 결정·사진 선택·검토 기록을 확인한다") from None
    folder = char_dir / STAGE_DIR / gate.rev
    shown = [folder / "gate-G1s.html", folder / OPTIONS]
    if a.decision != "SELECT" and a.selections:
        raise FactoryError("사진을 바꾸려면 SELECT와 사진 ID 하나를 보낸다")
    chosen = []
    if a.decision in {"APPROVE", "SELECT"}:
        state.require_deps("s2")
        problems = verify_manifest(folder)
        if problems:
            raise CheckFailed("s2", problems)
        data = read_json(folder / OPTIONS)
        if state.gate("G0").rev != data["sourceRev"]:
            raise FactoryError("검토 중 G0 출처 판이 바뀌었다. 수정 요청 뒤 다시 실행한다")
        options = [AppearanceSpec.model_validate(o) for o in data["options"]]
        by_id = {o.referenceImage.id: o for o in options}
        if a.decision == "SELECT" and (len(a.selections) != 1 or a.selections[0] not in by_id):
            raise FactoryError("G1s SELECT에는 후보 사진 ID 하나가 필요하다")
        spec = by_id[a.selections[0]] if a.decision == "SELECT" else options[0]
        chosen = [spec.referenceImage.id]
        inputs = HeroInputs(
            sourceReferenceRev=spec.sourceReferenceRev,
            clusterId=spec.clusterId,
            commonTags=spec.tags,
            scope=spec.scope,
            referencePreviews=spec.referencePreviews,
            basePhoto="picked",
        )
        write_once_json(folder / "inputs.json", dump(inputs))
        write_once_json(folder / "appearance-spec.json", dump(spec))
        write_manifest(folder)
        shown.extend(folder / o.referenceImage.path for o in options)
    rec = write_gate_record(
        char_dir,
        state,
        gate="G1s",
        rev=gate.rev,
        stage_id="s2",
        shown=shown,
        decision=a.decision,
        selections=chosen,
        reviewer=a.reviewer,
        reasons=a.reasons,
        minutes=a.minutes,
        requested_changes=[dump(c) for c in a.requestedChanges],
    )
    ctx.ledger(cid).record_human(gate="G1s", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    return folder
