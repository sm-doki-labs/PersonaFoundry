"""이미지 자동 검사 루프 (D-0036·D-0037, LLD §8.4a).

생성 → 비전 판정(기준표 항목마다 PASS·FAIL·UNSURE) → FAIL이면 판정의 수정 지시를 붙여
직전 이미지를 편집(또는 다시 생성) → 다시 판정. 상한(max_fix_rounds)까지 통과하지 못하면
FAIL이 가장 적은 시도를 고르고 FAIL 상태로 사람에게 넘긴다. 검사는 사람 관문을 대신하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any

from acf.common.aspect import crop_to_ratio
from acf.common.canonical import sha256_file
from acf.common.errors import CheckFailed, ValidationFailed
from acf.common.schema import validate
from acf.common.store import write_once_bytes
from acf.contracts.qa import ImageQaReport, QaRound, QaSummary, VisionVerdict
from acf.providers.base import ImageRequest, VisionRequest, extract_json_object


@dataclass(frozen=True)
class RubricItem:
    id: str
    label: str  # 검토 페이지용 한국어
    criterion: str  # 판정 모델용 영어


@dataclass(frozen=True)
class Rubric:
    id: str
    items: tuple[RubricItem, ...]

    @property
    def ids(self) -> list[str]:
        return [i.id for i in self.items]

    def label(self, item_id: str) -> str:
        return next((i.label for i in self.items if i.id == item_id), item_id)


def _rubric(rid: str, *items: tuple[str, str, str]) -> Rubric:
    return Rubric(rid, tuple(RubricItem(*x) for x in items))


RUBRICS: dict[str, Rubric] = {
    # S4a·S4b 배경 사진: 인물 없는 9:16 장소 사진
    "plate-v1": _rubric(
        "plate-v1",
        (
            "no_people",
            "사람 없음",
            "No person, silhouette, reflection of a person or body part is visible anywhere.",
        ),
        (
            "no_text",
            "글자·로고 없음",
            "No readable text, logo, brand name, sign lettering or watermark.",
        ),
        (
            "matches_brief",
            "묘사와 일치",
            "The place, time of day, light and mood match the scene description.",
        ),
        (
            "usable_background",
            "배경으로 쓸 수 있음",
            "A vertical frame with a clear area where one person could later stand or sit; "
            "nothing large blocks the center.",
        ),
    ),
    # S4 챕터 완성 이미지: 기준 얼굴 + 배경 사진 + 자세
    "composite-v1": _rubric(
        "composite-v1",
        (
            "same_identity",
            "같은 얼굴",
            "The person is clearly the same individual as the identity reference "
            "(face shape, eyes, nose, lips, hair).",
        ),
        (
            "same_place",
            "같은 장소",
            "The background is the same place as the background plate: same layout, light "
            "and colors.",
        ),
        (
            "pose_match",
            "자세 일치",
            "Body orientation, gaze and expression follow the pose description.",
        ),
        (
            "hands_ok",
            "손",
            "Hands do not touch the face, chin or cheek, and fingers look natural in number "
            "and shape.",
        ),
        ("outfit_match", "의상 일치", "The outfit matches the outfit description."),
        (
            "single_person_no_text",
            "인물 한 명·글자 없음",
            "Exactly one person in focus; no readable text, logo or watermark.",
        ),
    ),
}


@dataclass(frozen=True)
class QaSettings:
    enabled: bool = True
    max_fix_rounds: int = 2
    fix_mode: str = "edit"  # edit: 직전 이미지를 참조로 붙여 고친다. regenerate: 처음부터 다시

    @property
    def max_attempts(self) -> int:
        return 1 + (self.max_fix_rounds if self.enabled else 0)


def qa_settings(ctx) -> QaSettings:
    """[stages.image_qa] enabled, max_fix_rounds, fix_mode (D-0037 제안값)."""
    raw = ctx.config.stage("image_qa")
    s = QaSettings(
        enabled=bool(raw.get("enabled", True)),
        max_fix_rounds=int(raw.get("max_fix_rounds", 2)),
        fix_mode=str(raw.get("fix_mode", "edit")),
    )
    if s.fix_mode not in {"edit", "regenerate"} or s.max_fix_rounds < 0:
        raise CheckFailed("image_qa", ["fix_mode는 edit|regenerate, max_fix_rounds는 0 이상이다"])
    return s


# 판정 형식이 틀리면 같은 시도를 한 번 더 묻는다(generate_checked). 비전 최대치에 넣는다.
JUDGE_TRIES = 2


def worst_case_calls(settings: QaSettings, images: int) -> tuple[int, int]:
    """(이미지 호출, 비전 호출) 최대치. 판정 형식 재질의까지 넣는다.

    호출 계획과 예산 확인에 쓴다."""
    if not settings.enabled:
        return images, 0
    return images * settings.max_attempts, images * settings.max_attempts * JUDGE_TRIES


def ensure_judge(ctx, settings: QaSettings) -> str:
    """실제 이미지인데 비전 판정이 가짜면 막는다. 계열 경고 문장을 돌려준다(D-0010)."""
    if not settings.enabled:
        return ""
    image = ctx.config.provider("image").adapter
    vision = ctx.config.provider("vision").adapter
    if image != "fake" and vision == "fake" and ctx._vision is None:
        raise CheckFailed(
            "image_qa",
            [
                "비전 판정 공급자가 설정되지 않았다. [providers.vision]을 설정하거나 "
                "[stages.image_qa] enabled = false로 검사를 끈다"
            ],
        )
    warning = ctx.vision_family_warning()
    if warning and not bool(ctx.config.stage("image_qa").get("allow_same_family", False)):
        raise CheckFailed("image_qa", [warning + ". allow_same_family = true로 명시해야 한다"])
    return warning


def judge_system() -> str:
    return resources.files("acf.prompts").joinpath("image_judge.md").read_text("utf-8")


def judge_prompt(rubric: Rubric, context: str, labels: list[str]) -> str:
    lines = "\n".join(f"- {i.id}: {i.criterion}" for i in rubric.items)
    imgs = "\n".join(f"{n}. {lab}" for n, lab in enumerate(labels, 1))
    return (
        f"Attached images, in order:\n{imgs}\n\n"
        f"Judge ONLY the first image (the candidate). Other images are references.\n\n"
        f"<rubric>\n{lines}\n</rubric>\n\n<context>\n{context}\n</context>\n\n"
        'Return one JSON object: {"schemaVersion": "vision-verdict-v1", "items": '
        '[{"id": <rubric id>, "verdict": "PASS"|"FAIL"|"UNSURE", "reason": <짧은 한국어>}], '
        '"fixHint": <English instruction that changes only the failed points, or "">}. '
        "Judge every rubric id exactly once."
    )


def parse_verdict(text: str, rubric: Rubric) -> VisionVerdict:
    try:
        v: VisionVerdict = validate("vision-verdict-v1", extract_json_object(text))  # type: ignore[assignment]
    except (ValueError, ValidationFailed) as e:
        raise ValueError(f"판정 형식 오류: {e}") from e
    ids = [i.id for i in v.items]
    if sorted(ids) != sorted(rubric.ids):
        raise ValueError(f"판정 항목이 기준표와 다르다: {ids} != {rubric.ids}")
    return v


@dataclass
class QaOutcome:
    data: bytes
    report: ImageQaReport | None
    final_path: Path | None


def generate_checked(
    *,
    image_model: Any,
    vision: Any,
    request: ImageRequest,
    ratio: tuple[int, int],
    rubric: Rubric,
    context: str,
    judge_refs: list[tuple[str, str]],
    out_dir: Path,
    image_id: str,
    settings: QaSettings,
    warning: str = "",
) -> QaOutcome:
    """이미지 하나를 만들고 검사한다. 시도마다 out_dir/attempts/<id>-a<k>.png를 남긴다."""
    if not settings.enabled:
        res = image_model.generate(request)
        try:
            png, _, _ = crop_to_ratio(res.data, ratio)
        except ValueError as e:
            raise CheckFailed(request.stage, [f"{image_id}: {e}"]) from e
        return QaOutcome(png, None, None)
    rounds: list[QaRound] = []
    paths: list[Path] = []
    fix, prev = "", ""
    gen_provider = gen_model = ""
    for k in range(1, settings.max_attempts + 1):
        if k == 1:
            req, mode = request, "generate"
        elif settings.fix_mode == "edit":
            req = replace(
                request,
                prompt=(
                    f"Edit the last attached image. Fix: {fix} Keep everything else the same. "
                    + request.prompt
                ),
                reference_images=(*request.reference_images, prev),
                ref=f"{request.ref}#a{k}",
            )
            mode = "edit"
        else:
            req = replace(request, prompt=f"{request.prompt} Fix: {fix}", ref=f"{request.ref}#a{k}")
            mode = "regenerate"
        res = image_model.generate(req)
        gen_provider, gen_model = res.provider, res.model
        try:
            png, _, _ = crop_to_ratio(res.data, ratio)
        except ValueError as e:
            raise CheckFailed(request.stage, [f"{image_id} 시도 {k}: {e}"]) from e
        path = out_dir / "attempts" / f"{image_id}-a{k}.png"
        write_once_bytes(path, png)
        paths.append(path)
        labels = ["candidate image", *(lab for lab, _ in judge_refs)]
        vreq = VisionRequest(
            stage=request.stage,
            ref=f"{request.ref}#qa{k}",
            prompt=judge_prompt(rubric, context, labels),
            images=(("candidate image", str(path)), *judge_refs),
            system=judge_system(),
        )
        verdict = None
        problem = ""
        for _ in range(JUDGE_TRIES):  # 형식 오류는 한 번 더 묻는다
            try:
                verdict = parse_verdict(vision.judge(vreq).text, rubric)
                break
            except ValueError as e:
                problem = str(e)
        if verdict is None:
            raise CheckFailed(request.stage, [f"{image_id} 판정 실패: {problem}"])
        failed = [i.id for i in verdict.items if i.verdict == "FAIL"]
        unsure = [i.id for i in verdict.items if i.verdict == "UNSURE"]
        rounds.append(
            QaRound(
                attempt=k,
                filePath=path.relative_to(out_dir).as_posix(),
                sha256=sha256_file(path),
                mode=mode,  # type: ignore[arg-type]
                fixApplied=fix if k > 1 else "",
                items=verdict.items,
                failed=failed,
                unsure=unsure,
                fixHint=verdict.fixHint,
            )
        )
        if not failed:
            break
        reasons = "; ".join(f"{i.id}: {i.reason}" for i in verdict.items if i.verdict == "FAIL")
        fix, prev = (verdict.fixHint or reasons), str(path)
    passed = [r for r in rounds if not r.failed]
    final = passed[0] if passed else min(reversed(rounds), key=lambda r: len(r.failed))
    report = ImageQaReport(
        imageId=image_id,
        stage=request.stage,
        rubric=rubric.id,
        generatorProvider=gen_provider,
        generatorModel=gen_model,
        judgeProvider=vision.name,
        judgeModel=vision.model,
        sameFamilyWarning=warning,
        rounds=rounds,
        finalAttempt=final.attempt,
        status="PASS" if passed else "FAIL",
    )
    final_path = paths[final.attempt - 1]
    return QaOutcome(final_path.read_bytes(), report, final_path)


def summarize(report: ImageQaReport, rubric: Rubric, report_rel: str) -> QaSummary:
    final = report.rounds[report.finalAttempt - 1]
    reasons = [
        f"{rubric.label(i.id)}: {i.reason}" for i in final.items if i.verdict in {"FAIL", "UNSURE"}
    ]
    return QaSummary(
        status=report.status,
        attempts=len(report.rounds),
        failed=final.failed,
        unsure=final.unsure,
        reasons=reasons,
        report=report_rel,
    )
