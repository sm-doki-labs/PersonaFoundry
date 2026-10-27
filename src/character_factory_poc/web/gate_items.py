"""관문 상세 화면이 쓰는 읽기 자료 (LLD §6.5, K-0037).

관문마다 사람이 고를 항목을 단계 revision의 계약 파일에서 읽어 화면 모양으로 바꾼다. 쓰기는
하지 않는다. 파일이 없으면 problems에 이유를 적고 빈 목록을 돌려준다. 화면은 그 자리에 안내를
보여 주고, 결정은 지금까지처럼 `pipeline.approve.approve_gate` 한 경로로만 보낸다.

S9~S11(G7a·G7·G8·G9)은 단계 코드가 없어 `reads.GATE_META`가 connected=False이고, 지금은
`gate_fixtures`의 계약 모양 예시만 보여 준다. 단계가 붙을 때 이 파일에 빌더를 더한다.
"""

from __future__ import annotations

import json
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
            cluster_faces.append(
                {
                    "previewId": preview.get("previewId"),
                    "prompt": preview.get("prompt", ""),
                    "sha256": preview.get("fileSha256", ""),
                    "file": file,
                    "recommended": cluster_id == recommended,
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
                "rationale": rationale.get(cluster_id, ""),
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
            "외모군마다 얼굴 한 장이다. 얼굴 하나를 고르면 외모군이 그 얼굴에서 정해지고, "
            "S2 기준 이미지와 이후 장면·영상의 얼굴 기준이 된다(D-0042)."
        ),
    }


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
    return {
        "kind": "planVariants",
        "source": "artifacts",
        "problems": [] if candidates else ["후보가 비었다"],
        "mode": mode,
        "axisNote": axis,
        "seedRev": seed_rev,
        "editableFields": list(EDITABLE_FIELDS),
        "candidates": candidates,
        "selection": selection,
        "approvedPlan": plan,
        "helper": (
            "같은 상황에서 무엇을 먼저 고르는지 비교한 뒤 한 안을 고른다. 고칠 칸은 "
            "수정 요청 JSON으로 함께 보낼 수 있다(D-0033)."
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


def prompts(char_dir: Path, character_id: str, stage_dir: str, rev: str) -> dict[str, Any]:
    """G6: 긴·짧은 프롬프트와 표본 응답."""
    folder = Path(char_dir) / stage_dir / rev
    pair = read_json(folder / "prompt-pair.json")
    probe = read_json(folder / "prompt-probe.json")
    if pair is None:
        return _empty("prompts", ["prompt-pair.json이 없다. S8을 먼저 돌린다"])
    return {
        "kind": "prompts",
        "source": "artifacts",
        "problems": [] if probe is not None else ["prompt-probe.json이 없다(표본 응답 없음)"],
        "personaVersion": pair.get("personaVersion"),
        "sections": pair.get("sections", []),
        "long": pair.get("long"),
        "short": pair.get("short"),
        "systemRulesRef": pair.get("systemRulesRef", ""),
        "systemRulesSha256": pair.get("systemRulesSha256", ""),
        "shortAdopted": pair.get("shortAdopted", False),
        "probes": (probe or {}).get("probes", []),
        "judgeModel": (probe or {}).get("judgeModel", ""),
        "probeNote": (probe or {}).get("note", ""),
        "traitSheet": _latest_trait_sheet(char_dir, character_id),
        "helper": (
            "긴 프롬프트·짧은 프롬프트·표본 응답을 비교하고 승인하거나 고칠 점을 적는다. "
            "판정은 참고용이고 승인은 사람이 한다."
        ),
    }


BUILDERS = {
    "faces": faces,
    "planVariants": plan_variants,
    "backgrounds": backgrounds,
    "poses": poses,
    "frames": frames,
    "intro": intro,
    "actions": actions,
    "prompts": prompts,
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
