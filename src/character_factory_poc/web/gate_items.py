"""관문 상세 화면이 쓰는 읽기 자료 (LLD §6.5, K-0037).

관문마다 사람이 고를 항목을 단계 revision의 계약 파일에서 읽어 화면 모양으로 바꾼다. 쓰기는
하지 않는다. 파일이 없으면 problems에 이유를 적고 빈 목록을 돌려준다. 화면은 그 자리에 안내를
보여 주고, 결정은 지금까지처럼 `pipeline.approve.approve_gate` 한 경로로만 보낸다.

S9~S11(G7a·G7·G8·G9)은 단계 코드가 없어 `reads.GATE_META`가 connected=False이고, 지금은
`gate_fixtures`의 계약 모양 예시만 보여 준다. 단계가 붙을 때 이 파일에 빌더를 더한다.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from character_factory_poc.contracts.planning import EDITABLE_FIELDS
from character_factory_poc.contracts.scene import POSE_FIELDS
from character_factory_poc.web import gate_fixtures

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
_VOCAB: dict[str, Any] | None = None


def file_url(character_id: str, rel: str) -> str:
    return f"/api/files/{quote(character_id)}/{quote(rel, safe='/')}"


def read_json(path: Path) -> dict[str, Any] | None:
    """JSON 객체 하나를 읽는다. 없거나 깨졌으면 None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_list(path: Path) -> list[Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    if suffix == ".json":
        return "json"
    return "file"


def asset(char_dir: Path, character_id: str, stage_dir: str, rev: str, rel: Any) -> dict | None:
    """revision 안 상대 경로를 화면이 바로 쓰는 파일 항목으로 바꾼다."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    clean = rel.strip().lstrip("/")
    char_rel = f"{stage_dir}/{rev}/{clean}" if rev else f"{stage_dir}/{clean}"
    target = Path(char_dir) / char_rel
    return {
        "path": char_rel,
        "name": Path(clean).name,
        "url": file_url(character_id, char_rel),
        "exists": target.is_file(),
        "kind": _kind(clean),
    }


def tag_vocab() -> dict[str, Any]:
    """외모 어휘. 없으면 빈 사전을 돌려주고 값 그대로 화면에 쓴다."""
    global _VOCAB
    if _VOCAB is None:
        try:
            text = (
                resources.files("character_factory_poc.resources")
                .joinpath("appearance-tag-vocab-v1.json")
                .read_text("utf-8")
            )
            data = json.loads(text)
        except (OSError, ValueError):
            data = {}
        _VOCAB = data if isinstance(data, dict) else {}
    return _VOCAB


def _tags(common: Any) -> list[dict[str, str]]:
    """공통 특징을 한국어 라벨과 값으로 편다. 어휘에 없으면 원래 값을 쓴다."""
    if not isinstance(common, dict):
        return []
    vocab = tag_vocab()
    out: list[dict[str, str]] = []
    for field, value in common.items():
        group = vocab.get("multi" if isinstance(value, list) else "single", {}).get(field, {})
        values = value if isinstance(value, list) else [value]
        labels = [
            str(group.get("values", {}).get(str(v), {}).get("ko", v)) for v in values if v != ""
        ]
        out.append(
            {
                "field": str(field),
                "label": str(group.get("label", field)),
                "value": ", ".join(str(v) for v in values),
                "text": ", ".join(labels),
            }
        )
    return out


def _qa_summary(qa: Any, character_id: str) -> dict[str, Any] | None:
    if not isinstance(qa, dict):
        return None
    summary = dict(qa)
    report = qa.get("report")
    summary["reportUrl"] = file_url(character_id, str(report)) if report else None
    summary.pop("report", None)
    summary["passed"] = qa.get("status") == "PASS"
    return summary


def _empty(kind: str, problems: list[str]) -> dict[str, Any]:
    return {"kind": kind, "source": "artifacts", "problems": problems}


def faces(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G1: 외모군마다 얼굴 한 장, 추천 표시, 구성원(검토용)."""
    folder = Path(char_dir) / stage_dir / rev
    report = read_json(folder / "report.json")
    previews = read_list(folder / "previews.json") or []
    people = read_json(folder / "people.json") or {}
    problems: list[str] = []
    if report is None:
        return _empty("faces", ["report.json이 없다. S1을 먼저 돌린다"])
    if not previews:
        problems.append("previews.json이 비었다. cfp ref faces로 얼굴을 만든다")
    names = {
        str(p.get("personId")): str(p.get("name", ""))
        for p in people.get("people", [])
        if isinstance(p, dict)
    }
    ordering = [o for o in report.get("ordering", []) if isinstance(o, dict)]
    rationale = {str(o.get("clusterId")): str(o.get("rationale", "")) for o in ordering}
    recommended = str(ordering[0].get("clusterId")) if ordering else None
    clusters = []
    for candidate in report.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        cluster_id = str(candidate.get("clusterId", ""))
        cluster_faces = []
        for preview in previews:
            if not isinstance(preview, dict) or str(preview.get("clusterId")) != cluster_id:
                continue
            file = asset(char_dir, character_id, stage_dir, rev, preview.get("filePath"))
            settings = preview.get("settings") if isinstance(preview.get("settings"), dict) else {}
            variation = settings.get("variation")
            if not isinstance(variation, int):
                variation = 1
            cluster_faces.append(
                {
                    "previewId": preview.get("previewId"),
                    "prompt": preview.get("prompt", ""),
                    "sha256": preview.get("fileSha256", ""),
                    "file": file,
                    "variation": variation,
                    # 추천 외모군의 첫 얼굴 한 장만 추천으로 표시한다(D-0105, 외모군당 여러 장).
                    "recommended": cluster_id == recommended and not cluster_faces,
                }
            )
        members = [
            {"personId": pid, "name": names.get(str(pid), "")}
            for pid in candidate.get("members", [])
        ]
        clusters.append(
            {
                "clusterId": cluster_id,
                "recommended": cluster_id == recommended,
                "memberCount": candidate.get("memberCount", len(members)),
                "rationale": _plain_rationale(candidate, rationale.get(cluster_id, "")),
                "tags": _tags(candidate.get("commonTags")),
                "limitations": candidate.get("limitations", []),
                "popularity": candidate.get("popularity"),
                "members": members,
                "faces": cluster_faces,
            }
        )
    return {
        "kind": "faces",
        "source": "artifacts",
        "problems": problems,
        "scope": report.get("scope"),
        "cautions": report.get("cautions", []),
        "normalization": report.get("normalization", ""),
        "recommended": recommended,
        "clusters": clusters,
        "helper": (
            "외모군마다 각도·표정이 다른 얼굴이 2~3장 있어요. 한 장을 고르면 그 얼굴이 기준 사진이 "
            "되고, 이후 모든 장면과 영상의 얼굴 기준이 돼요."
        ),
    }


_EXAMPLES = "상대가 하는 말 예:"


def plain_use_when(text: Any) -> str:
    """동작의 '이럴 때' 규칙(모델용 원문)을 검토자가 읽는 한 줄로 줄인다(QA v5 C-07).

    원문은 '<이름> — 상황. … 상대가 하는 말 예: 「…」 · 「…」. 틀지 않는다: … → key' 꼴이다.
    상대가 하는 말 예가 있으면 그 예만, 없으면 영어가 섞이지 않은 첫 문장만 쓴다. 원문은
    대화 중 영상 고르기에 그대로 쓰이고 화면에만 이 글을 보인다.
    """
    s = " ".join(str(text or "").split()).split("틀지 않는다", 1)[0]
    head, sep, rest = s.partition(" — ")
    situation, _, examples = (rest if sep else head).partition(_EXAMPLES)
    quotes = re.findall(r"「[^」]+」", examples)
    if quotes:
        return "이런 말에 나와요: " + " · ".join(quotes)
    for sentence in re.split(r"(?<=[.!?])\s+", situation):
        line = sentence.strip().rstrip(".")
        if line and not re.search(r"[A-Za-z]", line):
            return "이럴 때: " + line
    return ""


def _plain_rationale(candidate: dict[str, Any], fallback: str) -> str:
    """외모군 근거를 검토자가 읽는 말로 바꾼다. 원래 근거(백분위·IQR)는 보고서에 그대로 남는다."""
    lists = candidate.get("listCount")
    members = candidate.get("memberCount")
    if not isinstance(lists, int) or not isinstance(members, int):
        return fallback
    text = f"순위 목록 {lists}개에 걸쳐 {members}명이 함께 가진 특징이에요."
    pop = candidate.get("popularity") or {}
    median = pop.get("medianPercentile")
    if isinstance(median, (int, float)):
        # 백분위는 1위가 1.0이다. 사람이 읽기 쉽게 '목록 위에서 몇 % 지점'으로 바꾼다.
        top = max(1, min(100, round((1 - float(median)) * 100)))
        text += f" 구성원 순위는 중간값으로 목록 위에서 {top}% 지점이에요."
        spread = pop.get("iqr")
        if isinstance(spread, (int, float)) and spread >= 0.3:
            text += " 사람마다 순위 차이가 커요."
    else:
        text += " 목록이 짧아 순위를 비교하지 못했어요."
    return text


# 기획안 말투 칸에 섞여 들어오는 원문 통계 문장(예: "종결형은 높임 459, 반말 0, 미분류 379였다").
# 화면에는 캐릭터 설명만 두고, 통계는 접힌 '기술 정보'로 옮긴다. 원래 칸 값은 그대로 둔다.
_STAT_SENTENCE = re.compile(r"(종결형|미분류|높임\s*\d|반말\s*\d|\d+(?:\.\d+)?\s*%)")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")


def split_stat_sentences(text: Any) -> tuple[str, list[str]]:
    """글을 문장으로 나눠 통계 문장과 나머지를 가른다. 화면 표시용이다."""
    if not isinstance(text, str) or not text.strip():
        return (text if isinstance(text, str) else ""), []
    keep: list[str] = []
    stats: list[str] = []
    for sentence in _SENTENCE_END.split(text.strip()):
        (stats if _STAT_SENTENCE.search(sentence) else keep).append(sentence)
    if not keep:
        # 문장을 나누지 못해 설명까지 통계로 보이면 원래 글을 그대로 둔다.
        return text, []
    return " ".join(keep), stats


def _plan_display(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for c in candidates:
        voice, stats = split_stat_sentences(c.get("voiceSummary"))
        if stats:
            out[str(c.get("variantId"))] = {"voiceSummary": voice, "voiceStats": stats}
    return out


def _same_prompt(long: Any, short: Any) -> bool:
    a = long.get("text") if isinstance(long, dict) else None
    b = short.get("text") if isinstance(short, dict) else None
    return bool(a) and a == b


def plan_variants(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G3: 변형 3안, 고칠 수 있는 칸, 직접 쓴 안."""
    folder = Path(char_dir) / stage_dir / rev
    variants = read_json(folder / "variants.json")
    plan = read_json(folder / "plan.json")
    selection = read_json(folder / "selection.json")
    if variants is None and plan is None:
        return _empty("planVariants", ["variants.json이 없다. S3 변형을 먼저 돌린다"])
    candidates = []
    mode = "variants"
    axis = ""
    seed_rev = None
    if variants is not None:
        mode = str(variants.get("mode", "variants"))
        axis = str(variants.get("axisNote", ""))
        seed_rev = variants.get("seedRev")
        candidates = [c for c in variants.get("candidates", []) if isinstance(c, dict)]
    else:
        mode = "plan"
        seed_rev = plan.get("seedRev") if plan else None
        candidates = [plan] if plan else []
    choice_evidence = {}
    requirements = []
    choice_problems = []
    explicit = bool(variants and variants.get("schemaVersion") == "plan-variants-v2")
    if explicit:
        from character_factory_poc.contracts.choice_design import ChoiceArtifactRef
        from character_factory_poc.stages.s3_plan.choice_design import verified_ref

        try:
            req_ref = ChoiceArtifactRef.model_validate(variants["requirements"])
            req = read_json(verified_ref(Path(char_dir), req_ref))
            requirements = [
                dict(id=r["requirementId"], quote=r["quote"]) for r in req["requirements"]
            ]
            for variant, ref in variants["designs"].items():
                body = read_json(
                    verified_ref(Path(char_dir), ChoiceArtifactRef.model_validate(ref))
                )
                choice_evidence[variant] = [
                    {k: r[k] for k in ("situation", "priority", "acceptedCost", "switchWhen")}
                    for r in body["rules"]
                ]
        except (ValueError, OSError, KeyError) as exc:
            choice_problems.append(f"선택 근거를 확인할 수 없다: {exc}")
    return {
        "kind": "planVariants",
        "source": "artifacts",
        "problems": choice_problems if candidates else ["후보가 비었다"],
        "requireExplicitSelection": explicit,
        "choiceEvidence": choice_evidence,
        "seedRequirements": requirements,
        "mode": mode,
        "axisNote": axis,
        "seedRev": seed_rev,
        "editableFields": list(EDITABLE_FIELDS),
        "candidates": candidates,
        # 화면 표시용: 말투 칸의 통계 문장을 뺀 글과 뺀 문장(기술 정보로 접는다).
        "planDisplay": _plan_display(candidates),
        "selection": selection,
        "approvedPlan": plan,
        "helper": (
            "같은 상황에서 무엇을 먼저 고르는지 비교한 뒤 한 안을 골라요. 고른 안의 칸은 "
            "확정할 때 함께 고칠 수 있어요."
        ),
    }


def backgrounds(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G4a: 챕터별 배경 후보·배경 사진·직접 정의."""
    folder = Path(char_dir) / stage_dir / rev
    data = read_json(folder / "background-candidates.json")
    selection = read_json(folder / "selection.json")
    if data is None:
        return _empty("backgrounds", ["background-candidates.json이 없다. S4a를 먼저 돌린다"])
    chapters = []
    for chapter in data.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        candidates = []
        for candidate in chapter.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            candidates.append(
                {
                    "candidateId": candidate.get("candidateId"),
                    "place": candidate.get("place", ""),
                    "timeOfDay": candidate.get("timeOfDay", ""),
                    "why": candidate.get("why", ""),
                    "props": candidate.get("props", []),
                    "mood": candidate.get("mood", ""),
                    "sceneFactsDraft": candidate.get("sceneFactsDraft", []),
                    "boundariesDraft": candidate.get("boundariesDraft", []),
                    "plateBrief": candidate.get("plateBrief", ""),
                    "plate": asset(
                        char_dir,
                        character_id,
                        stage_dir,
                        rev,
                        (candidate.get("plate") or {}).get("path"),
                    ),
                    "qa": _qa_summary(candidate.get("qa"), character_id),
                }
            )
        chapters.append(
            {
                "chapterId": chapter.get("chapterId"),
                "title": chapter.get("title", ""),
                "arc": chapter.get("arc", ""),
                "candidates": candidates,
            }
        )
    return {
        "kind": "backgrounds",
        "source": "artifacts",
        "problems": [],
        "aspectRatio": data.get("aspectRatio"),
        "chapters": chapters,
        "selection": selection,
        "helper": "챕터마다 배경 하나를 고르거나 원하는 배경을 한두 줄로 직접 적는다.",
    }


def poses(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G4b: 장면 사실·자세 후보·직접 정의·세부 수정."""
    folder = Path(char_dir) / stage_dir / rev
    scene = read_json(folder / "scene-plan.json")
    data = read_json(folder / "pose-candidates.json")
    selection = read_json(folder / "selection.json")
    if data is None:
        return _empty("poses", ["pose-candidates.json이 없다. S4b를 먼저 돌린다"])
    scenes = {
        str(s.get("chapterId")): s for s in (scene or {}).get("chapters", []) if isinstance(s, dict)
    }
    chapters = []
    for chapter in data.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        chapter_id = str(chapter.get("chapterId"))
        facts = scenes.get(chapter_id, {})
        candidates = [
            {
                **{f: candidate.get(f) for f in POSE_FIELDS},
                "poseId": candidate.get("poseId"),
                "title": candidate.get("title", ""),
                "animatable": candidate.get("animatable"),
            }
            for candidate in chapter.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        chapters.append(
            {
                "chapterId": chapter_id,
                "place": facts.get("place", ""),
                "timeOfDay": facts.get("timeOfDay", ""),
                "mood": facts.get("mood", ""),
                "sceneFacts": facts.get("sceneFacts", []),
                "meetingContext": facts.get("meetingContext", ""),
                "relationshipCanon": facts.get("relationshipCanon", []),
                "sceneBoundaries": facts.get("sceneBoundaries", []),
                "plate": asset(
                    char_dir, character_id, stage_dir, rev, (facts.get("plate") or {}).get("path")
                ),
                "qa": _qa_summary(facts.get("qa"), character_id),
                "candidates": candidates,
            }
        )
    return {
        "kind": "poses",
        "source": "artifacts",
        "problems": [],
        "poseFields": list(POSE_FIELDS),
        "chapters": chapters,
        "selection": selection,
        "helper": (
            "장면 사실을 확인하고 챕터마다 자세·의상을 하나 고른다. 고른 후보의 칸은 "
            "세부 수정으로 바꿀 수 있다(D-0027)."
        ),
    }


def frames(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G4: 챕터별 완성 이미지와 승인·수정 요청."""
    folder = Path(char_dir) / stage_dir / rev
    items = read_list(folder / "frames.json") or []
    inputs = read_json(folder / "inputs.json") or {}
    approved = read_json(folder / "approved-frames.json")
    if not items:
        return _empty("frames", ["frames.json이 없다. S4를 먼저 돌린다"])
    out = []
    for frame in items:
        if not isinstance(frame, dict):
            continue
        out.append(
            {
                "chapterId": frame.get("chapterId"),
                "frameId": frame.get("frameId"),
                "prompt": frame.get("prompt", ""),
                "provider": frame.get("provider", ""),
                "model": frame.get("model", ""),
                "file": asset(char_dir, character_id, stage_dir, rev, frame.get("filePath")),
                "qa": _qa_summary(frame.get("qa"), character_id),
            }
        )
    return {
        "kind": "frames",
        "source": "artifacts",
        "problems": [],
        "appearanceRev": inputs.get("appearanceRev"),
        "sceneRev": inputs.get("sceneRev"),
        "planRev": inputs.get("planRev"),
        "referenceCrop": inputs.get("referenceCrop"),
        "cropNote": inputs.get("cropNote", ""),
        "referenceImage": asset(
            char_dir, character_id, stage_dir, rev, (inputs.get("referenceImage") or {}).get("path")
        ),
        "identityReference": asset(
            char_dir,
            character_id,
            stage_dir,
            rev,
            (inputs.get("identityReference") or {}).get("path"),
        ),
        "frames": out,
        "approved": approved,
        "helper": (
            "얼굴·장소·자세를 확인하고 챕터마다 승인하거나 바꿀 내용을 적는다. 수정 요청한 "
            "챕터만 다시 만든다."
        ),
    }


def intro(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G5: 소개 영상 후보와 첫 프레임."""
    folder = Path(char_dir) / stage_dir / rev
    inputs = read_json(folder / "inputs.json")
    assets = read_list(folder / "videos.json") or []
    approved = read_json(folder / "approved-intro.json")
    if inputs is None or not assets:
        return _empty("intro", ["inputs.json 또는 videos.json이 없다. S5를 먼저 돌린다"])
    source = inputs.get("firstFrameSource") or {}
    candidates = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "candidateId": item.get("candidateId"),
                "videoId": item.get("videoId"),
                "provider": item.get("provider", ""),
                "model": item.get("model", ""),
                "probe": item.get("probe"),
                "estCostUsd": item.get("estCostUsd"),
                "file": asset(char_dir, character_id, stage_dir, rev, item.get("filePath")),
            }
        )
    return {
        "kind": "intro",
        "source": "artifacts",
        "problems": [],
        "provider": inputs.get("provider"),
        "model": inputs.get("model"),
        "settings": inputs.get("settings"),
        "firstFrame": asset(
            char_dir, character_id, stage_dir, rev, (inputs.get("firstFrame") or {}).get("path")
        ),
        "hero": asset(
            char_dir,
            character_id,
            stage_dir,
            rev,
            ((source.get("hero") or {}).get("path")) if isinstance(source, dict) else None,
        ),
        "firstFrameSource": {
            "mode": source.get("mode") if isinstance(source, dict) else None,
            "model": source.get("model") if isinstance(source, dict) else None,
            "croppedSize": source.get("croppedSize") if isinstance(source, dict) else None,
        },
        "prompt": (inputs.get("settings") or {}).get("prompt", ""),
        "candidates": candidates,
        "approved": approved,
        "helper": "첫 프레임과 같은 사람으로 자연스럽게 움직이는 영상을 하나 고른다.",
    }


def _carried_choices(
    char_dir: Path, inputs: dict[str, Any], by_action: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """다시 만든 판이면 지난 판에서 정한 쓰기·빼기 중 그대로 쓸 수 있는 것만 돌려준다(D-0115).

    다시 만든 동작은 영상이 바뀌어 넘기지 않는다. 쓰기는 지난 판에서 고른 영상을 이 판이
    그대로 재사용했을 때만 넘긴다.
    """
    prev = inputs.get("previousRev")
    if not prev:
        return None
    draft = read_json(Path(char_dir) / "choices" / f"G5b-{prev}.json")
    if not draft:
        return None
    regenerate = set(inputs.get("regenerate") or [])
    picks: dict[str, str] = {}
    for aid, candidate in (draft.get("picks") or {}).items():
        if aid in regenerate:
            continue
        same = [c for c in by_action.get(aid, []) if c.get("candidateId") == candidate]
        if same and same[0].get("reusedFrom") == prev:
            picks[aid] = candidate
    excluded = [
        aid for aid in draft.get("excluded") or [] if aid not in regenerate and aid in by_action
    ]
    return {
        "fromRev": prev,
        "picks": picks,
        "excluded": excluded,
        "regenerated": sorted(regenerate),
    }


def actions(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G5b: 동작별 후보 고르기·빼기·다시 만들기."""
    folder = Path(char_dir) / stage_dir / rev
    inputs = read_json(folder / "inputs.json")
    clips = read_list(folder / "clips.json") or []
    approved = read_json(folder / "approved-actions.json")
    if inputs is None or not clips:
        return _empty("actions", ["inputs.json 또는 clips.json이 없다. S6을 먼저 돌린다"])
    by_action: dict[str, list[dict[str, Any]]] = {}
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        entry = {
            "candidateId": (clip.get("asset") or {}).get("candidateId"),
            "videoId": (clip.get("asset") or {}).get("videoId"),
            "reusedFrom": clip.get("reusedFrom"),
            "file": asset(
                char_dir,
                character_id,
                stage_dir,
                rev,
                (clip.get("asset") or {}).get("filePath"),
            ),
        }
        by_action.setdefault(str(clip.get("actionId")), []).append(entry)
    chapters = []
    for chapter in inputs.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        specs = []
        for spec in chapter.get("actions", []):
            if not isinstance(spec, dict):
                continue
            specs.append(
                {
                    "actionId": spec.get("actionId"),
                    "actionKey": spec.get("actionKey"),
                    "playType": spec.get("playType"),
                    "pickRole": spec.get("pickRole"),
                    "actionCategory": spec.get("actionCategory"),
                    "mood": spec.get("mood"),
                    "title": spec.get("title", ""),
                    "description": spec.get("description", ""),
                    "useWhen": spec.get("useWhen", ""),
                    "whenText": plain_use_when(spec.get("useWhen", "")),
                    "duration": spec.get("duration"),
                    "prompt": spec.get("prompt", ""),
                    "reviewNote": spec.get("reviewNote", ""),
                    "candidates": by_action.get(str(spec.get("actionId")), []),
                }
            )
        chapters.append(
            {
                "chapterId": chapter.get("chapterId"),
                "stageNote": chapter.get("stageNote", ""),
                "goodFrame": asset(
                    char_dir,
                    character_id,
                    stage_dir,
                    rev,
                    (chapter.get("goodFrame") or {}).get("path"),
                ),
                "badFrame": asset(
                    char_dir,
                    character_id,
                    stage_dir,
                    rev,
                    (chapter.get("badFrame") or {}).get("path"),
                ),
                "actions": specs,
            }
        )
    return {
        "kind": "actions",
        "source": "artifacts",
        "problems": [],
        "carried": _carried_choices(char_dir, inputs, by_action),
        "frameRev": inputs.get("frameRev"),
        "preset": inputs.get("preset"),
        "resolution": inputs.get("resolution"),
        "aspectRatio": inputs.get("aspectRatio"),
        "chapters": chapters,
        "approved": approved,
        "helper": (
            "동작마다 영상 하나를 고르거나 뺀다. 챕터마다 하나 이상은 남긴다. 다시 만들 동작은 "
            "수정 요청에 메모를 적는다."
        ),
    }


def _latest_trait_sheet(char_dir: Path, character_id: str) -> dict[str, Any] | None:
    folder = Path(char_dir) / "s7-traits"
    if not folder.is_dir():
        return None
    paths = sorted(folder.glob("*/trait-sheet.json"), key=lambda p: p.stat().st_mtime)
    if not paths:
        return None
    sheet = read_json(paths[-1])
    if sheet is None:
        return None
    rel = paths[-1].relative_to(Path(char_dir)).as_posix()
    return {
        "path": rel,
        "url": file_url(character_id, rel),
        "card": sheet.get("card"),
        "choice": sheet.get("choice"),
        "unresolved": sheet.get("unresolved", []),
    }


def _motif_review(char_dir: Path, pair: dict, rev: str) -> dict:
    import re

    from character_factory_poc.common.canonical import sha256_file
    from character_factory_poc.common.demo_chat import Scene, latest, resource
    from character_factory_poc.pipeline.origin import is_twin

    if not is_twin(char_dir):
        return {}
    scene = Scene.read(char_dir)
    result = {"inferredTraits": []}
    if scene.prompt and scene.prompt.name == rev and (samples := scene.samples()):
        result["samples"] = samples
    traits = char_dir / "s7-traits"
    folder = latest(traits, "tr")
    if digest := pair.get("traitSheetSha256"):
        # 지금 검토하는 프롬프트에 실제로 쓰인 특질만 보여 준다.
        folder = next(
            (p.parent for p in traits.glob("tr*/trait-sheet.json") if sha256_file(p) == digest),
            None,
        )
    if folder is None:
        return result
    entries = (read_json(folder / "trait-ledger.json") or {}).get("traits", [])
    inferred = [t for t in entries if t.get("basis") == "INFERRED"]
    gate = (read_json(char_dir / "state.json") or {}).get("gates", {}).get("G0", {})
    rows = {}
    if gate.get("status") == "APPROVED" and re.fullmatch(r"sp[0-9]+", gate.get("rev") or ""):
        rows = _corpus_rows(
            char_dir / "s0-source" / gate["rev"] / "corpus.jsonl",
            {t.get("sourceRef") for t in inferred},
        )
    names = resource("motif-demo-situations-v1.json")
    for t in inferred:
        situation = t.get("demoSituation")
        msg = t.get("sourceRef")
        refs = [{"msgId": msg, "quote": rows[msg]["text"]}] if msg in rows else []
        result["inferredTraits"].append(
            dict(
                situation=situation,
                situationKo=names.get(situation, "그 밖의 상황"),
                behavior=t["behavior"],
                refs=refs,
            )
        )
    return result


def prompts(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G6: 긴·짧은 프롬프트와 표본 응답."""
    folder = Path(char_dir) / stage_dir / rev
    pair = read_json(folder / "prompt-pair.json")
    probe = read_json(folder / "prompt-probe.json")
    # Private dialogue stays in this gate view, pinned to the displayed S8 revision.
    from character_factory_poc.web.evidence_review import with_excluded_claims

    evidence_review = with_excluded_claims(folder, read_json(folder / "evidence-review.json"))
    if pair is None:
        return _empty("prompts", ["prompt-pair.json이 없다. S8을 먼저 돌린다"])
    bundle = read_json(folder / "persona-bundle.json")
    trait = _latest_trait_sheet(char_dir, character_id)
    extras = {}
    if bundle is not None:
        # Read the pinned revision shown by this G6, not a newer S7 revision.
        from character_factory_poc.stages.s8_prompts.formation import pinned_path

        trait_dir = pinned_path(char_dir, "s7-traits", str(bundle.get("traitRevision")))
        trait = read_json(trait_dir / "trait-sheet.json")
        extras = {
            "bundle": bundle,
            "blueprint": read_json(trait_dir / "blueprint.json"),
            "formationDialogues": read_json(trait_dir / "formation-dialogues.json"),
            "qualityProfile": read_json(trait_dir / "profile.json"),
        }
    return {
        **extras,
        **_motif_review(char_dir, pair, rev),
        "kind": "prompts",
        "source": "artifacts",
        "problems": [] if probe is not None else ["prompt-probe.json이 없다(표본 응답 없음)"],
        "personaVersion": pair.get("personaVersion"),
        "sections": pair.get("sections", []),
        "long": pair.get("long"),
        "short": pair.get("short"),
        # 화면 표시용: 긴·짧은 프롬프트 글이 같으면 하나만 보여 준다.
        "samePrompt": _same_prompt(pair.get("long"), pair.get("short")),
        "systemRulesRef": pair.get("systemRulesRef", ""),
        "systemRulesSha256": pair.get("systemRulesSha256", ""),
        "shortAdopted": pair.get("shortAdopted", False),
        "probes": (probe or {}).get("probes", []),
        "judgeModel": (probe or {}).get("judgeModel", ""),
        "probeNote": (probe or {}).get("note", ""),
        "traitSheet": trait,
        "evidenceReview": evidence_review,
        "helper": (
            "자동 구조 검사만 통과했어요. 원문 근거가 규칙과 적용 조건을 의미상 뒷받침하는지는 "
            "사람이 읽고 확인해야 해요. 원문은 내부 검토용이에요."
            if evidence_review is not None
            else "긴 프롬프트·짧은 프롬프트·표본 응답을 비교하고 승인하거나 고칠 점을 적는다. "
            "판정은 참고용이고 승인은 사람이 한다."
        ),
    }


# ---------------------------------------------------------------- G7a·G7·G8·G9 (H 갈래)
# 합성 예시(gate_fixtures)와 같은 모양으로 실제 산출물을 읽는다. 화면 코드는 그대로 쓴다.

_VERDICTS = ["ADOPT", "FIX", "REJECT"]


def _conv_view(conv: dict[str, Any]) -> dict[str, Any]:
    return {k: conv.get(k) for k in ("conversationId", "clusterId", "system", "messages")}


def _sent_verdicts(path: Path) -> dict[str, Any]:
    """이미 보낸 판정(qa 파일)을 화면이 다시 보이도록 읽는다. 없으면 빈 값이다."""
    qa = read_json(path) or {}
    return {"sentVerdicts": qa.get("verdicts") or {}, "sentNotes": qa.get("notes") or {}}


def data_samples(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G7a: 클러스터별 인계안과 샘플 전문, 이미 판정한 클러스터 표시."""
    from character_factory_poc.stages.s9_data.samples import load_samples

    rev_dir = Path(char_dir) / stage_dir / rev
    plan = read_json(rev_dir / "plan.json")
    if plan is None:
        return _empty("samples", ["plan.json이 없다. cfp data samples를 먼저 돌린다"])
    clusters = []
    for c in plan.get("clusters", []):
        cid = c["clusterId"]
        try:
            convs = [_conv_view(x.model_dump(mode="json")) for x in load_samples(rev_dir, cid)]
        except Exception as exc:  # noqa: BLE001  화면 읽기는 깨진 파일이 있어도 나머지를 보여 준다
            convs = []
            plan.setdefault("problems", []).append(f"{cid} 샘플을 읽지 못했다: {exc}")
        clusters.append(
            {
                "clusterId": cid,
                "handoff": read_json(rev_dir / "handoffs" / f"{cid}.json"),
                "samples": convs,
                "reviewed": (Path(char_dir) / "gates" / f"G7a-{rev}-{cid}.json").is_file(),
                **_sent_verdicts(rev_dir / "qa" / f"G7a-{cid}.json"),
            }
        )
    return {
        "kind": "samples",
        "source": "artifacts",
        "plan": plan,
        "clusters": clusters,
        "verdicts": _VERDICTS,
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G7a.html"),
    }


def data_dataset(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G7: 분할·검사 요약과 표본 20개(대화 ID 순 앞 20개)."""
    rev_dir = Path(char_dir) / stage_dir / rev
    dataset = read_json(rev_dir / "dataset.json")
    if dataset is None:
        return _empty("dataset", ["dataset.json이 없다. cfp data build를 먼저 돌린다"])
    rows = []
    index = rev_dir / "index.jsonl"
    if index.is_file():
        for line in index.read_text("utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    samples = []
    for row in sorted(rows, key=lambda r: str(r.get("conversationId")))[:20]:
        conv = read_json(rev_dir / str(row.get("path", "")))
        if conv is not None:
            samples.append(_conv_view(conv))
    report = read_json(rev_dir / "check-report.json") or {}
    notes = [
        f"차단 실패 {dataset.get('blockingFailures', 0)}건, 경고 {dataset.get('warnings', 0)}건"
    ]
    if isinstance(report, dict):
        from character_factory_poc.web.model_path import plain_note

        notes += [plain_note(str(n)) for n in report.get("warnings", [])][:5]
    plan = read_json(rev_dir / "plan.json") or {}
    labels = {
        str(c.get("clusterId")): str(c.get("label") or c.get("clusterId"))
        for c in plan.get("clusters", [])
        if isinstance(c, dict)
    }
    return {
        "kind": "dataset",
        "source": "artifacts",
        "clusterLabels": labels,
        "dataset": dataset,
        "samples": samples,
        "notes": notes,
        "verdicts": _VERDICTS,
        **_sent_verdicts(rev_dir / "qa" / f"G7-{rev}.json"),
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G7.html"),
    }


def eval_report(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G8: 지표·기준과 사람 블라인드 쌍. 조건 이름은 쌍에 넣지 않는다."""
    rev_dir = Path(char_dir) / stage_dir / rev
    prompt_only = read_json(rev_dir / "prompt-only.json")
    if prompt_only is not None:
        # K-0038: 학습 결과 없이 연 G8. 블라인드 비교 대신 '긴 프롬프트로 진행' 결정을 받는다.
        options = prompt_only.get("adoptOptions", ["LONG_BASE"])
        twin_doc = prompt_only.get("schemaVersion") == "eval-twin-decision-v1"
        return {
            "kind": "eval",
            "viewKind": "promptOnly",
            "title": "긴 프롬프트 채택" if twin_doc else "학습 없이 진행",
            "source": "artifacts",
            "decision": prompt_only,
            "adoptOptions": options,
            # 화면 버튼 문구와 결정 본문에 실을 값. BIND_EXISTING은 reads.gate_view가 덮어쓴다.
            "adoptLabel": "긴 프롬프트로 진행",
            "adoptTarget": options[0] if options else "LONG_BASE",
            "twin": twin_comparison(char_dir, character_id, stage_dir, rev),
            "page": asset(char_dir, character_id, stage_dir, rev, "gate-G8.html"),
        }
    report = read_json(rev_dir / "report-final.json") or read_json(rev_dir / "report.json")
    pairs_doc = read_json(rev_dir / "pairs.json")
    prereg = read_json(rev_dir / "prereg.json")
    if report is None or pairs_doc is None or prereg is None:
        return _empty("eval", ["평가 보고서·짝 판정·사전 등록 가운데 없는 파일이 있다"])
    by_id = {p.get("pairId"): p for p in pairs_doc.get("pairs", [])}
    pairs = []
    for pid in pairs_doc.get("humanPairIds", []):
        p = by_id.get(pid)
        if p is None:
            continue
        prompt = (f"{p['history']}\n\n" if p.get("history") else "") + str(p.get("user", ""))
        pairs.append({"pairId": pid, "prompt": prompt, "a": p.get("replyA"), "b": p.get("replyB")})
    options = ["LONG_BASE"] + [
        a["model"]
        for a in prereg.get("arms", [])
        if a.get("armId") != "LONG_BASE" and not str(a.get("model", "")).startswith("UNBOUND:")
    ]
    criteria = [
        {
            "id": c["id"],
            "metric": c["metric"],
            "rule": f"{c['comparator']} {c['threshold']}",
        }
        for c in prereg.get("criteria", [])
    ]
    return {
        "kind": "eval",
        "source": "artifacts",
        "report": report,
        "criteria": criteria,
        "pairs": pairs,
        "adoptOptions": options,
        "twin": twin_comparison(char_dir, character_id, stage_dir, rev),
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G8.html"),
    }


def twin_comparison(
    char_dir: Path, character_id: str, stage_dir: str, rev: str
) -> dict[str, Any] | None:
    """모티브 G8의 실제 답 비교 요약(twin-comparison-v1). 없으면 None이다.

    장면별 정답 키(trials)와 원문은 넣지 않는다. 가족 블라인드 파일은 조건 이름 없이 판 번호로만
    알리고, 실제 답과 생성 답을 나란히 보이는 시연 화면은 그 판의 가족 판정을 가져온 뒤에만 연다.
    """
    from character_factory_poc.stages.s10_eval import blind

    rev_dir = Path(char_dir) / stage_dir / rev
    path = blind.latest(rev_dir)
    doc = read_json(path) if path is not None else None
    if path is None or doc is None or doc.get("schemaVersion") != "twin-comparison-v1":
        return None
    phase = {blind.REVIEWED: "REVIEWED", blind.BASE: "RUN", blind.PLAN: "PLANNED"}[path.name]
    conditions: list[dict[str, Any]] = []
    ballots: list[dict[str, Any]] = []
    for c in doc.get("conditions", []):
        if not isinstance(c, dict):
            continue
        trials = [t for t in c.get("trials", []) if isinstance(t, dict)]
        ballot = c.get("ballot") if isinstance(c.get("ballot"), str) else None
        voted = bool(ballot) and (rev_dir / f"twin-votes-{ballot}.json").is_file()
        kinds: dict[str, int] = {}
        for t in trials:
            for k in t.get("overlap") or []:
                kinds[str(k)] = kinds.get(str(k), 0) + 1
        conditions.append(
            {
                "armId": c.get("armId"),
                "model": c.get("model"),
                "servingModel": c.get("servingModel"),
                "status": c.get("status"),
                "modelScore": c.get("modelScore"),
                "humanScore": c.get("humanScore"),
                "trials": len(trials),
                "exact": sum(bool(t.get("exact")) for t in trials),
                "overlap": sum(bool(t.get("overlap")) for t in trials),
                "overlapKinds": kinds,
                "voted": voted,
                "blind": bool(ballot),
                "demo": (
                    asset(char_dir, character_id, stage_dir, rev, f"twin-demo-{ballot}.html")
                    if voted
                    else None
                ),
            }
        )
        if ballot:
            ballots.append(
                {
                    "ballot": ballot,
                    "file": asset(
                        char_dir, character_id, stage_dir, rev, f"twin-blind-{ballot}.html"
                    ),
                    "answerFile": f"answers-{ballot}.json",
                    "voted": voted,
                }
            )
    # 판 번호 순으로 늘어놓아 조건 표의 순서로 어느 판이 어느 조건인지 짐작하지 못하게 한다.
    ballots.sort(key=lambda b: b["ballot"])
    return {
        "phase": phase,
        "mode": doc.get("mode"),
        "sceneCount": doc.get("sceneCount"),
        "plannedCalls": doc.get("plannedCalls"),
        "costUpperUsd": doc.get("costUpperUsd"),
        "judgeModel": doc.get("judgeModel"),
        "overlapChars": doc.get("overlapChars"),
        "conditions": conditions,
        "ballots": ballots,
        "importHint": (
            "가족이 블라인드 화면에서 '답 파일 저장'을 누르면 answers-<판 번호>.json이 저장돼요. "
            "그 파일을 받아 공장에서 가져오면 사람 구별률이 채워지고 시연 화면이 열려요."
        ),
        "importCall": "stages.s10_eval.blind.import_blind_answers(ctx, characterId, 답 파일 경로)",
    }


# ---------------------------------------------------------------- G0·G1s (모티브 갈래)


def _corpus_rows(path: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    """corpus.jsonl에서 화면에 필요한 메시지만 고른다. 비교 세트(holdout.jsonl)는 열지 않는다."""
    out: dict[str, dict[str, Any]] = {}
    if not wanted or not path.is_file():
        return out
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and str(row.get("msgId")) in wanted:
            out[str(row["msgId"])] = row
    return out


def source_pack(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G0: s0이 정리한 출처 목록·화자·가린 개인정보·대화 수·사용 근거·출처 정리 에이전트 의견.

    비교 세트는 개수만 보인다. 원문(holdout.jsonl)은 load_holdout만 읽는다(D-0120).
    사진은 원본 경로(파일 이름에 개인정보가 있을 수 있다) 대신 장수와 받은 곳만 보인다.
    """
    folder = Path(char_dir) / stage_dir / rev
    index = read_json(folder / "source-index.json")
    if index is None:
        return _empty("sourcePack", ["source-index.json이 없다. s0을 먼저 돌린다"])
    pack = read_json(folder / "source-pack.json") or {}
    digest = read_json(folder / "digest.json")
    problems = (
        [] if digest is not None else ["digest.json이 없다. 출처 정리 에이전트 결과를 확인한다"]
    )
    digest = digest or {}
    specs = {str(t.get("textId")): t for t in pack.get("texts", []) if isinstance(t, dict)}
    texts = []
    for t in index.get("texts", []):
        if not isinstance(t, dict):
            continue
        spec = specs.get(str(t.get("textId")), {})
        texts.append(
            {
                **{
                    k: t.get(k)
                    for k in (
                        "textId",
                        "kind",
                        "messages",
                        "subjectMessages",
                        "conversations",
                        "first",
                        "last",
                    )
                },
                "subjectSpeaker": spec.get("subjectSpeaker"),
                "userSpeaker": spec.get("userSpeaker"),
                "date": spec.get("date"),
                "register": t.get("register") or spec.get("register"),
                "sourceUrl": spec.get("sourceUrl"),
            }
        )
    reps = [r for r in digest.get("representative", []) if isinstance(r, dict)]
    flags = [f for f in digest.get("piiFlags", []) if isinstance(f, dict)]
    rows = _corpus_rows(folder / "corpus.jsonl", {str(x.get("msgId")) for x in reps + flags})

    def text_of(msg_id: Any) -> str:
        return str(rows.get(str(msg_id), {}).get("text", ""))

    basis = pack.get("usageBasis") if isinstance(pack.get("usageBasis"), dict) else {}
    subject = pack.get("subject") if isinstance(pack.get("subject"), dict) else {}
    photos = [p for p in pack.get("photos", []) if isinstance(p, dict)]
    masked = index.get("masked") if isinstance(index.get("masked"), dict) else {}
    check = digest.get("speakerCheck") if isinstance(digest.get("speakerCheck"), dict) else {}
    return {
        "kind": "sourcePack",
        "publicFacts": read_json(folder / "facts.json"),
        "source": "artifacts",
        "problems": problems,
        "sourceRev": index.get("sourceRev"),
        "subject": {
            "displayName": subject.get("displayName", ""),
            "kind": index.get("subjectKind") or subject.get("kind"),
        },
        "usage": {
            "scope": basis.get("scope") or "",
            "consentBy": basis.get("consentBy"),
            "consentDate": basis.get("consentDate"),
            "notes": basis.get("notes") or "",
        },
        "usageProblems": [str(p) for p in index.get("usageProblems", [])],
        "texts": texts,
        "photos": {
            "count": len(index.get("photos", [])),
            "origins": [str(p.get("origin") or "") for p in photos],
        },
        "counts": {
            "conversations": sum(int(t.get("conversations") or 0) for t in texts),
            "corpusMessages": index.get("corpusMessages", 0),
            "corpusSubjectMessages": index.get("corpusSubjectMessages", 0),
            "holdoutConversations": index.get("holdoutConversations", 0),
            "holdoutMessages": index.get("holdoutMessages", 0),
            "otherParticipants": index.get("otherParticipants", 0),
        },
        "masked": {str(k): int(v) for k, v in masked.items() if isinstance(v, int)},
        "agent": {
            "speakerCheck": {
                "confirmed": bool(check.get("confirmed")),
                "note": str(check.get("note") or ""),
            },
            "representative": [
                {
                    "msgId": r.get("msgId"),
                    "category": r.get("category"),
                    "why": r.get("why", ""),
                    "text": text_of(r.get("msgId")),
                }
                for r in reps
            ],
            "observations": [str(o) for o in digest.get("observations", [])],
            "piiFlags": [
                {
                    "msgId": f.get("msgId"),
                    "reason": f.get("reason", ""),
                    "text": text_of(f.get("msgId")),
                }
                for f in flags
            ],
            "qualityNotes": [str(n) for n in digest.get("qualityNotes", [])],
        },
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G0.html"),
    }


def source_photos(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G1s: G0에서 승인한 사진 후보와 비전 태그. 첫 후보가 기본이다(approve_g1s)."""
    folder = Path(char_dir) / stage_dir / rev
    doc = read_json(folder / "photo-options.json")
    if doc is None:
        return _empty("sourcePhotos", ["photo-options.json이 없다. 모티브 s2를 먼저 돌린다"])
    photos = []
    for i, option in enumerate(doc.get("options", [])):
        if not isinstance(option, dict):
            continue
        ref = option.get("referenceImage") if isinstance(option.get("referenceImage"), dict) else {}
        photos.append(
            {
                "photoId": ref.get("id"),
                "n": i + 1,
                "default": i == 0,
                "file": asset(char_dir, character_id, stage_dir, rev, ref.get("path")),
                "tags": _tags(option.get("tags")),
                "descriptionKo": option.get("descriptionKo", ""),
                "descriptionEn": option.get("descriptionEn", ""),
                "notes": option.get("notes", ""),
            }
        )
    return {
        "kind": "sourcePhotos",
        "source": "artifacts",
        "problems": []
        if photos
        else ["사진 후보가 없다. 사진이 있는 출처 묶음으로 G0을 다시 받는다"],
        "sourceRev": doc.get("sourceRev"),
        "photos": photos,
        "helper": (
            "G0에서 승인한 사진이에요. 본인과 가장 닮고 얼굴이 잘 보이는 한 장을 고르면, 그 사진이 "
            "이후 모든 장면과 영상의 얼굴 기준이 돼요."
        ),
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G1s.html"),
    }


def release_package(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G9: 패키지 요약. 적재 확인은 G9 승인 뒤 cfp export doki-app --verify가 한다."""
    rev_dir = Path(char_dir) / stage_dir / rev
    package = read_json(rev_dir / "package.json")
    if package is None:
        return _empty("package", ["package.json이 없다. cfp release build를 먼저 돌린다"])
    files = package.get("files", [])
    missing = [f["path"] for f in files if not (rev_dir / f["path"]).is_file()]
    out = {
        "kind": "package",
        "source": "artifacts",
        "package": package,
        "counts": {
            "files": len(files),
            "chapters": len(package.get("chapters", [])),
            "videos": len(package.get("videos", [])),
            "missing": missing,
        },
        "verification": {"status": "NOT_RUN", "disposableDb": True, "steps": []},
        "page": asset(char_dir, character_id, stage_dir, rev, "gate-G9.html"),
    }
    # D-0126: 모티브만 발표 점검(자동 결과·사람 확인 항목)을 붙인다. 오리지널 G9는 그대로다.
    from character_factory_poc.stages.s11_release.presentation import view

    check = view(rev_dir, package)
    if check is not None:
        out["presentation"] = check
    return out


BUILDERS = {
    "faces": faces,
    "planVariants": plan_variants,
    "backgrounds": backgrounds,
    "poses": poses,
    "frames": frames,
    "intro": intro,
    "actions": actions,
    "prompts": prompts,
    "samples": data_samples,
    "dataset": data_dataset,
    "eval": eval_report,
    "package": release_package,
    "sourcePack": source_pack,
    "sourcePhotos": source_photos,
}


def build_gate_items(
    *,
    gate: str,
    kind: str,
    connected: bool,
    char_dir: Path,
    character_id: str,
    stage_dir: str,
    rev: str | None,
) -> dict[str, Any]:
    """관문 화면의 항목. 단계 코드가 없는 관문은 계약 모양의 합성 예시를 돌려준다."""
    if not connected:
        fixture = gate_fixtures.fixture_for(gate, character_id)
        if fixture is not None:
            fixture.setdefault("kind", kind)
            return fixture
    builder = BUILDERS.get(kind)
    if builder is None:
        return _empty(
            kind,
            [f"{kind} 화면은 아직 합성 예시만 있다. 계약 파일을 읽는 빌더를 gate_items에 더한다"],
        )
    if not rev:
        return _empty(kind, ["이 관문에 아직 revision이 없다. 단계를 먼저 돌린다"])
    return builder(char_dir, character_id, stage_dir, rev)
