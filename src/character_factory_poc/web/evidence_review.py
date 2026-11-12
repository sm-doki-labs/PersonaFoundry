"""Private review projection; never rewrite an immutable persona revision."""

import json
import re
from hashlib import sha256
from pathlib import Path

_ANALYSIS = re.compile(r"analysis/(tendency-discover|tendency-consolidate)-([\w-]+)\.json")


def with_excluded_claims(folder: Path, review: dict | None) -> dict | None:
    if review is None or "excludedClaims" in review:
        return review
    # Older v4 revisions recorded these only in the bound analysis responses.
    # Read those exact files, not a newer revision or unbound analysis attempt.
    excluded, issues = [], []
    for name, expected in review.get("analysisArtifacts", {}).items():
        match = _ANALYSIS.fullmatch(name)
        if match is None:
            continue
        try:
            path = folder / name
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError("분석 파일 경로가 바뀌었어요")
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != expected:
                raise ValueError("저장 당시 분석 파일과 내용이 달라요")
            output = json.loads(raw)["output"]
            for held in output.get("heldClaims", []):
                if not isinstance(held, dict) or not isinstance(held.get("claim"), dict):
                    raise ValueError("제외 특징의 저장 형식을 확인할 수 없어요")
                excluded.append(dict(held, phase=match[1], chunkId=match[2]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            issues.append(dict(artifact=name, reason=str(exc)))
    return dict(review, excludedClaims=excluded, excludedClaimsIssues=issues)
