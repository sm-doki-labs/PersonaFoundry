"""S1 외모군 미리보기 (LLD §8.1 preview, FR-36).

공통 특징 태그와 비교 범위만으로 프롬프트를 만든다. 순위 목록의 이름은 들어가지 않는다(FR-35).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import NameLeakError
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import write_once_bytes
from character_factory_poc.contracts.reference import (
    SINGLE_FIELDS,
    AppearanceCluster,
    RankingScope,
    ReferencePreview,
    ReferenceReport,
)
from character_factory_poc.providers.base import ImageRequest

# "celebrity likeness"를 넣으면 인물 인상(korean)과 함께 쓰일 때 이미지 안전 시스템이 생성을 막았다
# (2026-10-20 실제 호출 2회 연속 차단, 이 단어만 빼면 통과). 실존 인물이 아니라는 뜻은 본문
# "An original person, not based on any real individual"로 전한다(D-0020).
NEGATIVE = "text, watermark, logo"
GENDER = {"female": "woman", "male": "man", "any": "person"}
# 인물 인상(D-0020). unspecified면 프롬프트에 넣지 않는다.
ORIGIN = {"korean": "Korean", "east-asian": "East Asian", "unspecified": ""}


def subject_phrase(scope: RankingScope) -> str:
    """인물 인상과 성별을 합친 주어(D-0020). 예: "Korean woman"."""
    return " ".join(x for x in (ORIGIN[scope.appearanceOrigin], GENDER[scope.characterGender]) if x)


def appearance_parts(
    cluster: AppearanceCluster, vocab: dict[str, Any], include_looks: bool = True
) -> list[str]:
    """공통 특징 태그를 영어 문장 조각으로 바꾼다. 이름은 들어가지 않는다(FR-35).

    include_looks=False면 얼굴·머리·피부(단일값) 태그를 빼고 스타일링·분위기만 남긴다.
    """
    single = vocab["single"]
    multi = vocab["multi"]
    looks = [
        single[f]["values"][v]["en"]
        for f in SINGLE_FIELDS
        if isinstance(v := cluster.commonTags.get(f), str)
    ]
    parts = []
    if looks and include_looks:
        parts.append("Appearance: " + ", ".join(looks) + ".")
    for field, label in (("styling", "Styling"), ("mood", "Mood")):
        vals = cluster.commonTags.get(field)
        if isinstance(vals, list) and vals:
            parts.append(
                f"{label}: " + ", ".join(multi[field]["values"][v]["en"] for v in vals) + "."
            )
    return parts


# 같은 외모군 안에서 고를 거리를 주려고 얼굴 각도·표정만 바꾼다. 외모 태그는 그대로다(D-0105).
VARIATION_HINTS = (
    "Facing the camera, gentle closed-mouth smile.",
    "Three-quarter view, calm neutral expression.",
    "Slight head tilt, bright open expression.",
)


def face_counts(n_clusters: int, total: int, low: int, high: int) -> list[int]:
    """외모군 순서(추천 순)대로 얼굴 장수를 나눈다(D-0105).

    total을 외모군 수로 나눠 low~high 사이로 맞추고, 남는 장수는 앞 외모군부터 하나씩 더한다.
    예: 4개·10장·2~3장 → [3, 3, 2, 2], 3개 → [3, 3, 3], 5개 → [2, 2, 2, 2, 2].
    """
    if n_clusters <= 0:
        return []
    base = max(low, min(high, total // n_clusters))
    counts = [base] * n_clusters
    left = total - base * n_clusters
    for i in range(n_clusters):
        if left <= 0:
            break
        if counts[i] < high:
            counts[i] += 1
            left -= 1
    return counts


def build_prompt(
    cluster: AppearanceCluster,
    scope: RankingScope,
    vocab: dict[str, Any],
    n: int,
    total: int,
    revision_note: str = "",
) -> str:
    parts = [
        f"Character reference portrait of a fictional {subject_phrase(scope)} "
        f"in their {scope.ageRange}, {scope.artStyle} style."
    ]
    parts += appearance_parts(cluster, vocab)
    parts.append(
        "Upper body, neutral background, soft natural light. "
        "An original person, not based on any real individual."
    )
    if total > 1:
        hint = VARIATION_HINTS[(n - 1) % len(VARIATION_HINTS)]
        parts.append(f"Variation {n} of {total}. {hint}")
    if revision_note:
        # D-0043 (2): G1 REQUEST_CHANGES의 고칠 점. 이름 유출 검사는 호출부가 한다.
        parts.append(f"Revision note: {revision_note}")
    return " ".join(parts)


def generate_previews(
    *,
    image_model,
    subject_id: str,
    rev: str,
    rev_dir: Path,
    report: ReferenceReport,
    vocab: dict[str, Any],
    names: list[str],
    per_cluster: int | list[int],
    size: str,
    revision_note: str = "",
) -> list[ReferencePreview]:
    """프롬프트마다 이름 유출을 먼저 검사하고(FR-35) 통과한 것만 이미지 모델에 보낸다."""
    prompts = []
    counts = (
        per_cluster if isinstance(per_cluster, list) else [per_cluster] * len(report.candidates)
    )
    for c, count in zip(report.candidates, counts, strict=True):
        for n in range(1, count + 1):
            prompt = build_prompt(c, report.scope, vocab, n, count, revision_note=revision_note)
            if find_name_leaks(prompt + " " + NEGATIVE, names):
                raise NameLeakError(
                    f"미리보기 프롬프트({c.clusterId}-{n})에 순위 목록의 이름이 있다. "
                    "이미지 호출 전에 멈췄다(FR-35)"
                )
            prompts.append((c.clusterId, n, prompt))
    out: list[ReferencePreview] = []
    for cid, n, prompt in prompts:
        preview_id = f"{cid}-{n}"
        res = image_model.generate(
            ImageRequest(
                stage="s1",
                prompt=prompt,
                ref=f"{subject_id}/{rev}/{preview_id}",
                negative_prompt=NEGATIVE,
                size=size,
            )
        )
        rel = f"previews/{preview_id}.png"
        write_once_bytes(rev_dir / rel, res.data)
        out.append(
            validate(  # type: ignore[arg-type]
                "reference-preview-v1",
                {
                    "previewId": preview_id,
                    "clusterId": cid,
                    "prompt": prompt,
                    "negativePrompt": NEGATIVE,
                    "model": res.model,
                    "provider": res.provider,
                    "settings": {"size": size, "variation": n},
                    "fileSha256": sha256_file(rev_dir / rel),
                    "filePath": rel,
                },
            )
        )
    return out
