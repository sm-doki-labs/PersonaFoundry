"""창작 인물 QLoRA 운영 정책 읽기 (D-0078).

정본은 docs/guides/qlora-authored/policy-v1.json이고, 실행 코드는 같은 내용을 패키지 자원
resources/qlora-authored-policy-v1.json에서 읽는다. 정책의 모든 수치는 {"value", "source"} 형태다.
source가 "proposal"인 값은 검증된 최적값이 아니라 운영 시작값이다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

POLICIES = {"qlora-authored-v1": "qlora-authored-policy-v1.json"}


@lru_cache(maxsize=4)
def load_policy(name: str = "qlora-authored-v1") -> dict[str, Any]:
    if name not in POLICIES:
        raise ValueError(f"알 수 없는 QLoRA 정책: {name} ({', '.join(POLICIES)})")
    text = (
        resources.files("character_factory_poc.resources")
        .joinpath(POLICIES[name])
        .read_text("utf-8")
    )
    data = json.loads(text)
    if data.get("schemaVersion") != "qlora-authored-policy-v1":
        raise ValueError("정책 파일의 schemaVersion이 qlora-authored-policy-v1이 아니다")
    return data


def value(node: Any, default: Any = None) -> Any:
    """{"value": x, "source": ...} 이면 x, 아니면 node 자체(없으면 default)."""
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return default if node is None else node


def source(node: Any) -> str:
    return str(node.get("source", "")) if isinstance(node, dict) else ""


def clusters(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return list(policy.get("clusters") or [])


def cluster_shares(policy: dict[str, Any]) -> dict[str, float]:
    return {c["id"]: float(value(c["targetShare"])) for c in clusters(policy)}


def turn_mix(policy: dict[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    """턴 구간별 (최소, 최대) 비율. 단위는 학습 대화당 assistant 턴 수다."""
    mix = (policy.get("dataset") or {}).get("turnMix") or {}
    out: dict[str, tuple[float | None, float | None]] = {}
    for band, spec in mix.items():
        if band == "unit" or not isinstance(spec, dict):
            continue
        out[band] = (value(spec.get("min")), value(spec.get("max")))
    return out


def failure_types(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return list((policy.get("improvement") or {}).get("failureTypes") or [])


def suites(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return list((policy.get("evaluation") or {}).get("suites") or [])


def decisions(policy: dict[str, Any]) -> list[str]:
    return list((policy.get("evaluation") or {}).get("decisions") or [])
