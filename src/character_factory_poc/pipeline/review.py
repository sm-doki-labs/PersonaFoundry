"""관문 사전 검토 (LLD §6.8, 명세 §7.2, D-0049).

관문이 `AWAITING_HUMAN`이 되면 판정 모델이 화면에 보이는 후보를 읽고 추천 순위·근거·걸리는 점을
`gate-review-v1`로 남긴다. 추천은 승인이 아니다. 상태·산출물은 바꾸지 않고, 관문 기록만
`reviewRef`·`followedReview`로 가리킨다(FR-45).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from character_factory_poc.common.budget import Budget, CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError, ValidationFailed
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.review import (
    GateReview,
    ReviewDefect,
    ReviewerRef,
    ReviewItem,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.providers.base import (
    ChatRequest,
    Message,
    VisionRequest,
    extract_json_object,
)

# 사람 판정 자체가 내용인 G7a, 블라인드 비교인 G8에는 추천을 붙이지 않는다(FR-45).
NO_REVIEW_GATES = frozenset({"G7a", "G8"})

# 추천 순위를 매기는 관문. 나머지 검토 관문(G4·G6·G7·G9)은 승인 검토다.
CHOOSING_GATES = frozenset({"G1", "G3", "G4a", "G4b", "G5", "G5b"})

# 관문 → 단계 id. 폴더 이름은 web.reads.STAGE_DIRS를 따른다.
GATE_STAGE: dict[str, str] = {s.gate: sid for sid, s in STAGES.items() if s.gate}

_VERDICTS = {"RECOMMEND", "OK", "CONCERN"}


class _FormatError(FactoryError):
    """검토 답이 정한 JSON 모양과 다르다. 한 번 더 부르고, 또 틀리면 기록하지 않는다."""


@dataclass(frozen=True)
class ReviewCandidate:
    candidate_id: str  # 화면 항목 ID(web/gate_items.py). G5b는 <actionId>:<candidateId>다.
    group: str  # 순위를 매기는 단위. 챕터·동작·관문 전체.
    chapter_id: str | None
    payload: dict[str, Any]
    images: tuple[tuple[str, Path], ...] = ()


@dataclass(frozen=True)
class ReviewUnit:
    """모델 호출 하나의 단위. 챕터가 있으면 챕터 하나가 한 번이다."""

    chapter_id: str | None
    title: str
    context: dict[str, Any]
    candidates: tuple[ReviewCandidate, ...]
    images: tuple[tuple[str, Path], ...] = ()


@dataclass(frozen=True)
class ReviewSpec:
    mode: Literal["llm", "vision", "deterministic"]
    build: Callable[[dict[str, Any], Path, Path], list[ReviewUnit]]
    prompt: str  # prompts/review/<gate>.md
    artifacts: tuple[str, ...] = ()


# ---------------------------------------------------------------- 입력 조립


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _asset(char_dir: Path, item: Any) -> Path | None:
    """gate_items가 만든 파일 항목(path는 캐릭터 폴더 기준)을 실제 파일 경로로 푼다."""
    if not isinstance(item, dict):
        return None
    rel = item.get("path")
    if not isinstance(rel, str) or not rel.strip():
        return None
    path = Path(char_dir) / rel.strip().lstrip("/")
    return path if path.is_file() else None


def _unit_images(*pairs: tuple[str, Any]) -> tuple[tuple[str, Path], ...]:
    out = []
    for label, item in pairs:
        path = item if isinstance(item, Path) else None
        if path is not None and path.is_file():
            out.append((label, path))
    return tuple(out)


def _build_faces(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    candidates: list[ReviewCandidate] = []
    for cluster in _dicts(items.get("clusters")):
        cluster_id = _text(cluster.get("clusterId"))
        for face in _dicts(cluster.get("faces")):
            preview_id = _text(face.get("previewId"))
            if not preview_id:
                continue
            image = _asset(char_dir, face.get("file"))
            candidates.append(
                ReviewCandidate(
                    candidate_id=preview_id,
                    group="G1",
                    chapter_id=None,
                    # 순위 목록의 인물 이름(members)은 넣지 않는다(FR-35).
                    payload={
                        "clusterId": cluster_id,
                        "commonTags": cluster.get("tags", []),
                        "clusterRationale": cluster.get("rationale", ""),
                        "limitations": cluster.get("limitations", []),
                    },
                    images=(_unit_images((f"{preview_id} 얼굴", image)) if image else ()),
                )
            )
    if not candidates:
        raise FactoryError("G1 검토할 얼굴 후보가 없다. S1·cfp ref faces를 먼저 돌린다")
    context = {
        "cautions": items.get("cautions", []),
        "normalization": items.get("normalization", ""),
    }
    return [ReviewUnit(None, "G1 얼굴 후보", context, tuple(candidates))]


def _build_plans(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    candidates = []
    for plan in _dicts(items.get("candidates")):
        variant_id = _text(plan.get("variantId"))
        if not variant_id:
            continue
        candidates.append(
            ReviewCandidate(
                candidate_id=variant_id,
                group="G3",
                chapter_id=None,
                payload=dict(plan),
            )
        )
    if not candidates:
        raise FactoryError("G3 검토할 기획안이 없다. cfp plan variants를 먼저 돌린다")
    context = {
        "mode": items.get("mode"),
        "seedRev": items.get("seedRev"),
        "axisNote": items.get("axisNote", ""),
        "editableFields": items.get("editableFields", []),
    }
    return [ReviewUnit(None, "G3 기획 변형", context, tuple(candidates))]


def _build_backgrounds(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    units = []
    for chapter in _dicts(items.get("chapters")):
        chapter_id = _text(chapter.get("chapterId"))
        candidates = []
        for candidate in _dicts(chapter.get("candidates")):
            candidate_id = _text(candidate.get("candidateId"))
            if not candidate_id:
                continue
            plate = _asset(char_dir, candidate.get("plate"))
            candidates.append(
                ReviewCandidate(
                    candidate_id=candidate_id,
                    group=chapter_id,
                    chapter_id=chapter_id,
                    payload={
                        "place": candidate.get("place", ""),
                        "timeOfDay": candidate.get("timeOfDay", ""),
                        "why": candidate.get("why", ""),
                        "props": candidate.get("props", []),
                        "mood": candidate.get("mood", ""),
                        "sceneFactsDraft": candidate.get("sceneFactsDraft", []),
                        "boundariesDraft": candidate.get("boundariesDraft", []),
                        "plateBrief": candidate.get("plateBrief", ""),
                    },
                    images=(_unit_images((f"{candidate_id} 배경", plate)) if plate else ()),
                )
            )
        if not candidates:
            continue
        context = {
            "chapterTitle": chapter.get("title", ""),
            "chapterArc": chapter.get("arc", ""),
            "aspectRatio": items.get("aspectRatio"),
        }
        units.append(
            ReviewUnit(
                chapter_id,
                f"{chapter_id} 배경 후보",
                context,
                tuple(candidates),
            )
        )
    if not units:
        raise FactoryError("G4a 검토할 배경 후보가 없다. cfp scene backgrounds를 먼저 돌린다")
    return units


def _build_poses(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    units = []
    for chapter in _dicts(items.get("chapters")):
        chapter_id = _text(chapter.get("chapterId"))
        candidates = []
        for pose in _dicts(chapter.get("candidates")):
            pose_id = _text(pose.get("poseId"))
            if not pose_id:
                continue
            payload = {k: v for k, v in pose.items() if k not in {"poseId", "animatable"}}
            candidates.append(
                ReviewCandidate(
                    candidate_id=pose_id,
                    group=chapter_id,
                    chapter_id=chapter_id,
                    payload=payload,
                )
            )
        if not candidates:
            continue
        plate = _asset(char_dir, chapter.get("plate"))
        context = {
            "place": chapter.get("place", ""),
            "timeOfDay": chapter.get("timeOfDay", ""),
            "mood": chapter.get("mood", ""),
            "sceneFacts": chapter.get("sceneFacts", []),
            "meetingContext": chapter.get("meetingContext", ""),
            "relationshipCanon": chapter.get("relationshipCanon", []),
            "sceneBoundaries": chapter.get("sceneBoundaries", []),
        }
        images = _unit_images((f"{chapter_id} 배경 사진", plate)) if plate else ()
        units.append(
            ReviewUnit(chapter_id, f"{chapter_id} 자세 후보", context, tuple(candidates), images)
        )
    if not units:
        raise FactoryError("G4b 검토할 자세 후보가 없다. cfp scene poses를 먼저 돌린다")
    return units


def _build_frames(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    shared = {
        "appearanceRev": items.get("appearanceRev"),
        "sceneRev": items.get("sceneRev"),
        "planRev": items.get("planRev"),
        "referenceCrop": items.get("referenceCrop"),
        "cropNote": items.get("cropNote", ""),
    }
    refs = _unit_images(
        ("기준 얼굴 참조", _asset(char_dir, items.get("referenceImage"))),
        ("동일인 참조", _asset(char_dir, items.get("identityReference"))),
    )
    units = []
    for frame in _dicts(items.get("frames")):
        chapter_id = _text(frame.get("chapterId"))
        frame_id = _text(frame.get("frameId"))
        if not frame_id:
            continue
        image = _asset(char_dir, frame.get("file"))
        candidate = ReviewCandidate(
            candidate_id=frame_id,
            group=chapter_id or frame_id,
            chapter_id=chapter_id or None,
            payload={
                "prompt": frame.get("prompt", ""),
                "provider": frame.get("provider", ""),
                "model": frame.get("model", ""),
                "qa": frame.get("qa"),
            },
            images=(_unit_images((f"{frame_id} 완성 이미지", image)) if image else ()),
        )
        units.append(
            ReviewUnit(chapter_id or None, f"{chapter_id} 완성 이미지", shared, (candidate,), refs)
        )
    if not units:
        raise FactoryError("G4 검토할 완성 이미지가 없다. cfp frames run을 먼저 돌린다")
    return units


def _build_intro(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    candidates = []
    for candidate in _dicts(items.get("candidates")):
        candidate_id = _text(candidate.get("candidateId"))
        if not candidate_id:
            continue
        candidates.append(
            ReviewCandidate(
                candidate_id=candidate_id,
                group="G5",
                chapter_id=None,
                payload={
                    "videoId": candidate.get("videoId"),
                    "provider": candidate.get("provider", ""),
                    "model": candidate.get("model", ""),
                    "probe": candidate.get("probe"),
                    "estCostUsd": candidate.get("estCostUsd"),
                },
            )
        )
    if not candidates:
        raise FactoryError("G5 검토할 영상 후보가 없다. cfp video intro를 먼저 돌린다")
    first_frame = _asset(char_dir, items.get("firstFrame"))
    context = {
        "provider": items.get("provider"),
        "model": items.get("model"),
        "settings": items.get("settings"),
        "motionPrompt": items.get("prompt", ""),
        "firstFrameSource": items.get("firstFrameSource"),
    }
    images = _unit_images(("공통 첫 프레임", first_frame)) if first_frame else ()
    return [ReviewUnit(None, "G5 소개 영상 후보", context, tuple(candidates), images)]


def _build_actions(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    units = []
    for chapter in _dicts(items.get("chapters")):
        chapter_id = _text(chapter.get("chapterId"))
        candidates = []
        for action in _dicts(chapter.get("actions")):
            action_id = _text(action.get("actionId"))
            for candidate in _dicts(action.get("candidates")):
                video_id = _text(candidate.get("candidateId"))
                if not action_id or not video_id:
                    continue
                candidates.append(
                    ReviewCandidate(
                        candidate_id=f"{action_id}:{video_id}",
                        group=action_id,
                        chapter_id=chapter_id,
                        payload={
                            "actionId": action_id,
                            "actionKey": action.get("actionKey"),
                            "title": action.get("title", ""),
                            "description": action.get("description", ""),
                            "useWhen": action.get("useWhen", ""),
                            "pickRole": action.get("pickRole"),
                            "actionCategory": action.get("actionCategory"),
                            "mood": action.get("mood"),
                            "duration": action.get("duration"),
                            "prompt": action.get("prompt", ""),
                            "reviewNote": action.get("reviewNote", ""),
                            "videoId": candidate.get("videoId"),
                            "reusedFrom": candidate.get("reusedFrom"),
                        },
                    )
                )
        if not candidates:
            continue
        context = {
            "chapterId": chapter_id,
            "stageNote": chapter.get("stageNote", ""),
            "preset": items.get("preset"),
            "resolution": items.get("resolution"),
            "aspectRatio": items.get("aspectRatio"),
        }
        images = _unit_images(
            ("미소 출발 첫 프레임", _asset(char_dir, chapter.get("goodFrame"))),
            ("무표정 출발 첫 프레임", _asset(char_dir, chapter.get("badFrame"))),
        )
        units.append(
            ReviewUnit(
                chapter_id, f"{chapter_id} 동작 영상 후보", context, tuple(candidates), images
            )
        )
    if not units:
        raise FactoryError("G5b 검토할 동작 영상 후보가 없다. cfp video actions를 먼저 돌린다")
    return units


def _build_prompts(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    candidates = []
    for key in ("long", "short"):
        doc = items.get(key)
        if not isinstance(doc, dict) or not doc.get("text"):
            continue
        candidates.append(
            ReviewCandidate(
                candidate_id=key,
                group="G6",
                chapter_id=None,
                payload={"chars": doc.get("chars"), "text": doc.get("text")},
            )
        )
    if not candidates:
        raise FactoryError("G6 검토할 프롬프트가 없다. cfp persona prompts를 먼저 돌린다")
    context = {
        "sections": items.get("sections", []),
        "shortAdopted": items.get("shortAdopted", False),
        "probes": items.get("probes", []),
        "traitSheet": items.get("traitSheet"),
    }
    return [ReviewUnit(None, "G6 프롬프트 쌍", context, tuple(candidates))]


def _build_dataset(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    candidates = []
    for sample in _dicts(items.get("samples")):
        conversation_id = _text(sample.get("conversationId"))
        if not conversation_id:
            continue
        candidates.append(
            ReviewCandidate(
                candidate_id=conversation_id,
                group="G7",
                chapter_id=None,
                payload={
                    "clusterId": sample.get("clusterId"),
                    "messages": sample.get("messages", []),
                },
            )
        )
    if not candidates:
        raise FactoryError("G7 검토할 표본 대화가 없다. cfp data build를 먼저 돌린다")
    dataset = items.get("dataset") or {}
    context = {
        "datasetRev": dataset.get("datasetRev"),
        "blockingFailures": dataset.get("blockingFailures"),
        "warnings": dataset.get("warnings"),
        "notes": items.get("notes", []),
    }
    return [ReviewUnit(None, "G7 데이터셋 표본", context, tuple(candidates))]


def _build_package(items: dict[str, Any], char_dir: Path, rev_dir: Path) -> list[ReviewUnit]:
    """G9는 모델을 부르지 않는다. 호출 단위가 없다."""
    return []


REVIEWERS: dict[str, ReviewSpec] = {
    "G1": ReviewSpec("vision", _build_faces, "G1.md", ("report.json", "previews.json")),
    "G3": ReviewSpec("llm", _build_plans, "G3.md", ("variants.json",)),
    "G4a": ReviewSpec("vision", _build_backgrounds, "G4a.md", ("background-candidates.json",)),
    "G4b": ReviewSpec(
        "vision", _build_poses, "G4b.md", ("pose-candidates.json", "scene-plan.json")
    ),
    "G4": ReviewSpec("vision", _build_frames, "G4.md", ("frames.json", "inputs.json")),
    "G5": ReviewSpec("vision", _build_intro, "G5.md", ("videos.json", "inputs.json")),
    "G5b": ReviewSpec("vision", _build_actions, "G5b.md", ("clips.json", "inputs.json")),
    "G6": ReviewSpec("llm", _build_prompts, "G6.md", ("prompt-pair.json", "prompt-probe.json")),
    "G7": ReviewSpec("llm", _build_dataset, "G7.md", ("dataset.json", "check-report.json")),
    "G9": ReviewSpec("deterministic", _build_package, "", ("package.json",)),
}


# ---------------------------------------------------------------- 경로·설정


def _stage_dir(gate: str) -> str:
    from character_factory_poc.web.reads import STAGE_DIRS

    sid = GATE_STAGE.get(gate)
    if sid is None:
        raise FactoryError(f"관문이 없다: {gate}")
    return STAGE_DIRS[sid]


def review_path(char_dir: Path, gate: str, rev: str) -> Path:
    """<캐릭터 폴더>/reviews/<gate>-<rev>.json (LLD §5.19).

    단계 revision 폴더 안에 두면 매니페스트·패키지 파일 목록에 없는 파일이 생겨 해시 검사가
    깨진다(통합 시험에서 G9 패키지 검사로 확인). 관문 기록(gates/)처럼 캐릭터 폴더에 둔다.
    """
    _stage_dir(gate)  # 모르는 관문이면 FactoryError
    return Path(char_dir) / "reviews" / f"{gate}-{rev}.json"


def load_review(char_dir: Path, gate: str, rev: str) -> GateReview | None:
    """그 관문 revision의 검토 기록. 없거나 깨졌으면 None(화면은 '검토 없음')."""
    if not rev:
        return None
    try:
        path = review_path(char_dir, gate, rev)
    except FactoryError:
        return None
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    from character_factory_poc.common.schema import validate

    try:
        return validate("gate-review-v1", data)  # type: ignore[return-value]
    except ValidationFailed:
        return None


def followed_review(gate: str, review: GateReview | None, selections: list[str]) -> bool | None:
    """고르기 관문에서 단위마다 1순위 추천이 모두 선택에 들어 있는지(LLD §6.8)."""
    if review is None or gate not in CHOOSING_GATES:
        return None
    top = [item.candidateId for item in review.items if item.rank == 1]
    if not top:
        return None
    chosen = {str(s) for s in selections}
    return all(candidate_id in chosen for candidate_id in top)


def review_fields(
    char_dir: Path, gate: str, rev: str, selections: list[str] | None
) -> dict[str, Any]:
    """관문 기록에 넣을 reviewRef·followedReview. 검토가 없으면 둘 다 None."""
    review = load_review(char_dir, gate, rev)
    if review is None:
        return {"reviewRef": None, "followedReview": None}
    return {
        "reviewRef": review_path(char_dir, gate, rev).relative_to(char_dir).as_posix(),
        "followedReview": followed_review(gate, review, list(selections or [])),
    }


def _review_config(ctx: Context) -> dict[str, Any]:
    return dict(ctx.config.review or {})


def _review_allowed(ctx: Context, gate: str, spec: ReviewSpec) -> bool:
    cfg = _review_config(ctx)
    if not bool(cfg.get("enabled", False)):
        return False
    gates = cfg.get("gates")
    if isinstance(gates, list) and gate not in gates:
        return False
    if spec.mode == "vision" and not bool(cfg.get("vision", False)):
        return False
    return True


# ---------------------------------------------------------------- 호출


def _prompt_text(spec: ReviewSpec) -> str:
    if not spec.prompt:
        return ""
    folder = resources.files("character_factory_poc.prompts")
    try:
        return folder.joinpath("review", spec.prompt).read_text("utf-8")
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise FactoryError(f"검토 프롬프트를 읽지 못했다: {spec.prompt}") from exc


def _format_rule(gate: str, unit: ReviewUnit, choosing: bool) -> str:
    groups = []
    for candidate in unit.candidates:
        if candidate.group not in groups:
            groups.append(candidate.group)
    if choosing:
        return (
            'JSON 객체 하나만 출력한다: {"items": [{"candidateId": "...", "rank": 1, '
            '"verdict": "RECOMMEND"|"OK"|"CONCERN", "reasons": ["한국어 한 문장", ...], '
            '"defects": [{"field": "...", "note": "한국어"}]}], "summary": "한두 문장"}. '
            "보여 준 후보를 하나도 빠뜨리지 않고 정확히 한 번씩 판정한다. 순위 group마다 "
            "rank 1이 정확히 하나이고, 같은 group 안의 rank는 1..n을 겹치지 않게 쓴다. "
            f"group: {', '.join(groups)}. 근거는 화면에서 확인할 수 있는 것만 쓴다. "
            "사람 이름·순위 목록의 이름은 쓰지 않는다."
        )
    return (
        'JSON 객체 하나만 출력한다: {"items": [{"candidateId": "...", '
        '"verdict": "RECOMMEND"|"OK"|"CONCERN", "reasons": ["한국어 한 문장", ...], '
        '"defects": [{"field": "...", "note": "한국어"}]}], "summary": "한두 문장"}. '
        "승인 검토이므로 rank를 쓰지 않는다. 보여 준 후보를 하나도 빠뜨리지 않고 정확히 "
        "한 번씩 판정한다. 근거는 화면에서 확인할 수 있는 것만 쓴다. 사람 이름·순위 목록의 "
        "이름은 쓰지 않는다."
    )


def _body(gate: str, unit: ReviewUnit, choosing: bool) -> str:
    payload = {
        "gate": gate,
        "unit": unit.chapter_id or "관문 전체",
        "title": unit.title,
        "context": unit.context,
        "candidates": [
            {
                "candidateId": c.candidate_id,
                "group": c.group,
                "chapterId": c.chapter_id,
                **c.payload,
            }
            for c in unit.candidates
        ],
    }
    return (
        f"<input>\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n</input>\n\n"
        f"<format>\n{_format_rule(gate, unit, choosing)}\n</format>"
    )


def _check_text_reviewer(ctx: Context) -> None:
    judge = ctx.config.provider("judge")
    text = ctx.config.provider("text")
    if ctx._judge is None and judge.adapter == "fake" and text.adapter != "fake":
        raise FactoryError(
            "판정 공급자가 설정되지 않았다. [providers.judge]를 설정해야 사전 검토를 돌린다"
        )


def _check_vision_reviewer(ctx: Context) -> None:
    warning = ctx.vision_family_warning()
    if warning:
        raise FactoryError(warning + ". 같은 계열이면 관문 사전 검토를 돌리지 않는다(D-0010)")
    vision = ctx.config.provider("vision")
    image = ctx.config.provider("image")
    if ctx._vision is None and vision.adapter == "fake" and image.adapter != "fake":
        raise FactoryError(
            "비전 판정 공급자가 설정되지 않았다. [providers.vision]을 설정해야 사전 검토를 돌린다"
        )


def _call_text(
    ctx: Context, cid: str, gate: str, rev: str, unit: ReviewUnit, system: str, budget: Budget
) -> tuple[str, ReviewerRef]:
    try:
        model = ctx.judge_model(cid, budget)
    except ValueError as exc:
        raise FactoryError(str(exc)) from exc
    ref = f"{gate}/{rev}/{unit.chapter_id or 'all'}"
    response = model.complete(
        ChatRequest(
            kind="REVIEW",
            stage=gate,
            messages=(Message("system", system), Message("user", _body(gate, unit, True))),
            ref=ref,
            max_output_tokens=3000,
            temperature=0.0,
            response_json=True,
        )
    )
    reviewer = ReviewerRef(
        provider=model.name,
        model=model.model,
        family=ctx.config.provider("judge").family(),
    )
    return response.text, reviewer


def _call_vision(
    ctx: Context, cid: str, gate: str, rev: str, unit: ReviewUnit, system: str, budget: Budget
) -> tuple[str, ReviewerRef]:
    model = ctx.vision_model(cid, budget)
    ref = f"{gate}/{rev}/{unit.chapter_id or 'all'}"
    images = list(unit.images)
    for candidate in unit.candidates:
        images.extend(candidate.images)
    prompt = f"{system.strip()}\n\n{_body(gate, unit, gate in CHOOSING_GATES)}".strip()
    request = VisionRequest(
        stage=gate,
        ref=ref,
        prompt=prompt,
        images=tuple((label, str(path)) for label, path in images),
        max_output_tokens=3000,
    )
    result = model.judge(request)
    reviewer = ReviewerRef(
        provider=result.provider,
        model=result.model,
        family=ctx.config.provider("vision").family(),
    )
    return result.text, reviewer


def _check_ranks(items: list[ReviewItem], unit: ReviewUnit) -> None:
    groups: dict[str, list[int | None]] = {}
    group_of = {c.candidate_id: c.group for c in unit.candidates}
    for item in items:
        groups.setdefault(group_of[item.candidateId], []).append(item.rank)
    for group, ranks in groups.items():
        if sorted(r for r in ranks if r is not None) != list(range(1, len(ranks) + 1)):
            raise _FormatError(f"{group}: rank가 1..{len(ranks)}가 아니다({ranks})")


def _parse_answer(text: str, unit: ReviewUnit, choosing: bool) -> tuple[list[ReviewItem], str]:
    try:
        obj = extract_json_object(text)
    except ValueError as exc:
        raise _FormatError(f"JSON을 읽지 못했다: {exc}") from exc
    if not isinstance(obj, dict):
        raise _FormatError("JSON이 객체가 아니다")
    raw_items = obj.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise _FormatError("items가 비었다")
    expected = {c.candidate_id: c for c in unit.candidates}
    items: list[ReviewItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise _FormatError("items 항목이 객체가 아니다")
        candidate_id = _text(raw.get("candidateId"))
        if candidate_id not in expected:
            raise _FormatError(f"보여 주지 않은 candidateId다: {candidate_id!r}")
        if candidate_id in seen:
            raise _FormatError(f"candidateId가 겹친다: {candidate_id}")
        seen.add(candidate_id)
        rank = raw.get("rank")
        if choosing:
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise _FormatError(f"{candidate_id}: rank는 1 이상의 정수여야 한다")
        elif rank is not None:
            raise _FormatError("승인 관문에는 rank를 쓰지 않는다")
        verdict = _text(raw.get("verdict")).upper()
        if verdict not in _VERDICTS:
            raise _FormatError(f"{candidate_id}: verdict는 RECOMMEND·OK·CONCERN 중 하나다")
        raw_reasons = raw.get("reasons") or []
        if isinstance(raw_reasons, str):
            raw_reasons = [raw_reasons]
        if not isinstance(raw_reasons, list):
            raise _FormatError(f"{candidate_id}: reasons는 문자열 목록이어야 한다")
        reasons = [str(r) for r in raw_reasons if str(r).strip()]
        defects = []
        raw_defects = raw.get("defects") or []
        if not isinstance(raw_defects, list):
            raise _FormatError(f"{candidate_id}: defects는 객체 목록이어야 한다")
        for defect in raw_defects:
            if not isinstance(defect, dict):
                raise _FormatError("defects 항목이 객체가 아니다")
            field = _text(defect.get("field")).strip()
            note = _text(defect.get("note")).strip()
            if not field or not note:
                raise _FormatError("defects에는 field와 note가 필요하다")
            defects.append(ReviewDefect(field=field, note=note))
        items.append(
            ReviewItem(
                candidateId=candidate_id,
                chapterId=expected[candidate_id].chapter_id,
                rank=rank,
                verdict=verdict,  # type: ignore[arg-type]
                reasons=reasons,
                defects=defects,
            )
        )
    if seen != set(expected):
        missing = sorted(set(expected) - seen)
        raise _FormatError(f"판정하지 않은 후보가 있다: {', '.join(missing)}")
    if choosing:
        _check_ranks(items, unit)
    summary = _text(obj.get("summary")).strip()
    return items, summary


def _ask_unit(
    ctx: Context,
    cid: str,
    gate: str,
    rev: str,
    spec: ReviewSpec,
    unit: ReviewUnit,
    system: str,
    budget: Budget,
) -> tuple[list[ReviewItem], str, ReviewerRef]:
    choosing = gate in CHOOSING_GATES
    failure = ""
    for _attempt in (1, 2):
        if failure:
            system_retry = (
                system
                + "\n\n앞선 답이 형식에 맞지 않았다. 사유: "
                + failure
                + "\n같은 후보로 JSON 객체 하나를 다시 쓴다."
            )
        else:
            system_retry = system
        if spec.mode == "vision":
            text, reviewer = _call_vision(ctx, cid, gate, rev, unit, system_retry, budget)
        else:
            text, reviewer = _call_text(ctx, cid, gate, rev, unit, system_retry, budget)
        try:
            items, summary = _parse_answer(text, unit, choosing)
            return items, summary, reviewer
        except _FormatError as exc:
            failure = str(exc)
    raise FactoryError(f"{gate} 검토 답 형식 오류: {failure}")


# ---------------------------------------------------------------- 검토 실행


def _gate_items(ctx: Context, cid: str, gate: str, rev: str) -> tuple[dict[str, Any], Path, Path]:
    from character_factory_poc.web.gate_items import build_gate_items
    from character_factory_poc.web.reads import GATE_META

    meta = GATE_META.get(gate)
    if meta is None:
        raise FactoryError(f"관문이 없다: {gate}")
    char_dir = ctx.character_dir(cid)
    stage_dir = _stage_dir(gate)
    rev_dir = char_dir / stage_dir / rev
    items = build_gate_items(
        gate=gate,
        kind=meta["kind"],
        connected=bool(meta["connected"]),
        char_dir=char_dir,
        character_id=cid,
        stage_dir=stage_dir,
        rev=rev,
    )
    return items, char_dir, rev_dir


def _prepare(
    ctx: Context, cid: str, gate: str
) -> tuple[ReviewSpec, list[ReviewUnit], dict[str, Any], Path, Path, str]:
    if gate in NO_REVIEW_GATES:
        raise FactoryError(
            f"{gate}는 사람 판정 자체가 관문의 내용이라 사전 검토를 붙이지 않는다(FR-45)"
        )
    spec = REVIEWERS.get(gate)
    if spec is None:
        raise FactoryError(f"{gate} 사전 검토 정의가 없다")
    state = ctx.state(cid)
    gate_state = state.gate(gate)
    if not gate_state.rev:
        raise FactoryError(f"{cid}: {gate} revision이 없다. 단계를 먼저 돌린다")
    rev = gate_state.rev
    items, char_dir, rev_dir = _gate_items(ctx, cid, gate, rev)
    units = spec.build(items, char_dir, rev_dir)
    if spec.mode != "deterministic" and not units:
        problems = [str(p) for p in items.get("problems", [])]
        detail = ": " + "; ".join(problems) if problems else ""
        raise FactoryError(f"{gate} 검토 입력이 비었다{detail}")
    return spec, units, items, char_dir, rev_dir, rev


def plan_review_calls(ctx: Context, cid: str, gate: str) -> list[CallPlan]:
    """검토 호출 계획. 모델은 부르지 않는다(dry run)."""
    spec, units, _items, _char_dir, _rev_dir, rev = _prepare(ctx, cid, gate)
    if spec.mode == "deterministic":
        return [
            CallPlan(
                stage=gate,
                description=f"{rev} 패키지 검사 요약(모델 호출 없음)",
                calls=0,
            )
        ]
    mode = "비전" if spec.mode == "vision" else "텍스트"
    names = ", ".join(unit.chapter_id or "전체" for unit in units)
    return [
        CallPlan(
            stage=gate,
            description=f"{rev} {mode} 검토 {len(units)}회({names})",
            calls=len(units),
        )
    ]


def _shown_artifacts(
    char_dir: Path, rev_dir: Path, spec: ReviewSpec, units: list[ReviewUnit], items: dict[str, Any]
) -> list[ArtifactRef]:
    paths: list[Path] = []
    for name in spec.artifacts:
        path = rev_dir / name
        if path.is_file():
            paths.append(path)
    for unit in units:
        for _label, path in unit.images:
            paths.append(path)
        for candidate in unit.candidates:
            for _label, path in candidate.images:
                paths.append(path)
    if not paths and spec.mode == "deterministic":
        page = items.get("page")
        if isinstance(page, dict) and isinstance(page.get("path"), str):
            path = char_dir / page["path"]
            if path.is_file():
                paths.append(path)
    out: list[ArtifactRef] = []
    seen: set[str] = set()
    for path in paths:
        try:
            rel = path.relative_to(char_dir).as_posix()
        except ValueError:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        out.append(ArtifactRef(ref=rel, sha256=sha256_file(path)))
    return out


def _deterministic_summary(items: dict[str, Any]) -> str:
    counts = items.get("counts") or {}
    missing = [str(p) for p in counts.get("missing") or []]
    verification = items.get("verification") or {}
    parts = [
        f"파일 {int(counts.get('files', 0))}개, 챕터 {int(counts.get('chapters', 0))}개, "
        f"영상 {int(counts.get('videos', 0))}편",
    ]
    if missing:
        parts.append(f"빠진 파일 {len(missing)}개: {', '.join(missing[:5])}")
    else:
        parts.append("빠진 파일 없음")
    parts.append(f"적재 확인 {verification.get('status', 'NOT_RUN')}")
    return " · ".join(parts)


def _write_review(
    ctx: Context,
    cid: str,
    gate: str,
    rev: str,
    spec: ReviewSpec,
    char_dir: Path,
    rev_dir: Path,
    items: dict[str, Any],
    units: list[ReviewUnit],
) -> Path:
    path = review_path(char_dir, gate, rev)
    if spec.mode == "deterministic":
        review = GateReview(
            subjectId=cid,
            gate=gate,
            rev=rev,
            reviewer=ReviewerRef(
                provider="deterministic", model="package-check", family="deterministic"
            ),
            mode="deterministic",
            shownArtifacts=_shown_artifacts(char_dir, rev_dir, spec, units, items),
            items=[],
            summary=_deterministic_summary(items),
            createdAt=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        write_once_json(path, dump(review))
        return path

    if spec.mode == "vision":
        if not bool(_review_config(ctx).get("vision", False)):
            raise FactoryError(
                "이미지 관문 검토는 [review] vision = true일 때만 돈다(Q-0020 확인 전에는 꺼 둔다)"
            )
        _check_vision_reviewer(ctx)
    else:
        _check_text_reviewer(ctx)
    system = _prompt_text(spec)
    budget = ctx.budget()
    budget.check_plan([CallPlan(stage=gate, description=f"{gate} 사전 검토", calls=len(units))])
    review_items: list[ReviewItem] = []
    summaries: list[str] = []
    reviewer: ReviewerRef | None = None
    for unit in units:
        got, summary, unit_reviewer = _ask_unit(ctx, cid, gate, rev, spec, unit, system, budget)
        review_items.extend(got)
        if summary:
            summaries.append(summary)
        reviewer = unit_reviewer
    if reviewer is None:
        raise FactoryError(f"{gate} 검토 호출이 없었다")
    review = GateReview(
        subjectId=cid,
        gate=gate,
        rev=rev,
        reviewer=reviewer,
        mode=spec.mode,
        shownArtifacts=_shown_artifacts(char_dir, rev_dir, spec, units, items),
        items=review_items,
        summary=" · ".join(summaries),
        createdAt=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    write_once_json(path, dump(review))
    return path


def review_gate(ctx: Context, cid: str, gate: str) -> Path | None:
    """열린 관문의 사전 검토를 하고 기록 경로를 돌려준다. 이미 있으면 그대로 둔다."""
    if gate in NO_REVIEW_GATES:
        raise FactoryError(
            f"{gate}는 사람 판정 자체가 관문의 내용이라 사전 검토를 붙이지 않는다(FR-45)"
        )
    if gate not in REVIEWERS:
        raise FactoryError(f"{gate} 사전 검토 정의가 없다")
    gate_state = ctx.state(cid).gate(gate)
    if gate_state.rev:
        existing = review_path(ctx.character_dir(cid), gate, gate_state.rev)
        if existing.is_file():
            return existing
    spec, units, items, char_dir, rev_dir, rev = _prepare(ctx, cid, gate)
    return _write_review(ctx, cid, gate, rev, spec, char_dir, rev_dir, items, units)


def review_on_open(ctx: Context, cid: str, gate: str) -> Path | None:
    """관문이 AWAITING_HUMAN이 된 뒤 실행기가 부른다. 예외를 밖으로 내지 않는다."""
    spec = REVIEWERS.get(gate)
    if spec is None or gate in NO_REVIEW_GATES:
        return None
    if not ctx.execute or not _review_allowed(ctx, gate, spec):
        return None
    rev = ""
    try:
        gate_state = ctx.state(cid).gate(gate)
        rev = gate_state.rev or ""
        if gate_state.status != "AWAITING_HUMAN":
            return None
        return review_gate(ctx, cid, gate)
    except Exception:  # noqa: BLE001  실행기는 계속 돈다. 실패는 원장에만 남긴다
        try:
            ctx.ledger(cid).record_call(
                stage=gate,
                kind="REVIEW",
                provider="review",
                model="",
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=f"{gate}/{rev}",
            )
        except Exception:  # noqa: BLE001  원장 실패까지 실행기를 멈추지 않는다
            pass
        return None
