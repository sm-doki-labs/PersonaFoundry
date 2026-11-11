"""Source-specific register, intensity, turn ending and softening conditions."""

from __future__ import annotations

import sys
from collections import Counter
from copy import deepcopy

from character_factory_poc.stages.s8_prompts import evidence_tendencies as base

VERSION = "evidence-pipeline-v5"
AXES = {
    "register": "어휘 사용역",
    "intensity": "표현 강도",
    "ending": "말차례 종료",
    "softening": "표현 완화·전환",
    "other": "기타 언어 행동",
}
BASES = {"explicit_user_act", "visible_turn_sequence", "response_derived", "unknown"}


def to_card(claim, refs, state):
    if not isinstance(claim.get("usageAxis"), str) or claim["usageAxis"] not in AXES:
        raise ValueError("말투 사용 조건 축이 없거나 알 수 없다")
    card = base.to_card(claim, refs, state)
    field = {"response": "first", "continuation": "shift", "closure": "stop"}[claim["dimension"]]
    card[field] = f"{AXES[claim['usageAxis']]}의 조건부 경향. " + card[field]
    return card


def validate_transport(phase, out, payload):
    if phase in {"tendency-discover", "tendency-consolidate"}:
        if (
            not isinstance(out, dict)
            or set(out) != {"claims"}
            or not isinstance(out["claims"], list)
        ):
            raise ValueError("사용 조건 후보 형식 오류")
        stripped = []
        for claim in out["claims"]:
            if not isinstance(claim, dict) or set(claim) != base.FIELDS | {"usageAxis"}:
                raise ValueError("사용 조건 축을 포함한 정확한 후보 필드가 필요하다")
            stripped.append({k: v for k, v in claim.items() if k != "usageAxis"})
        try:
            base.validate_transport(phase, {"claims": stripped}, payload)
        except (KeyError, TypeError) as exc:
            raise ValueError("후보 필드의 타입이나 범주가 잘못됐다") from exc
        for claim in out["claims"]:
            to_card(claim, claim["evidence"], "mixed")
        return
    # Validate the envelope first, then each position against a clean copy.
    # Validation must never strip fields from the original evidence item.
    normalized = deepcopy(out)
    if not isinstance(normalized, dict) or not isinstance(normalized.get("findings"), list):
        raise ValueError("사용 조건 판독 형식 오류")
    originals = []
    notes = []
    for finding in normalized["findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("items"), list):
            raise ValueError("사용 조건 판독 묶음 오류")
        originals.append(finding["items"])
        notes.append(finding.get("note"))
        if finding.get("note") == "":
            finding["note"] = "묶음 요약 미제공; 개별 항목 사유를 별도 검증한다."
        finding["items"] = []
    try:
        base.validate_transport(phase, normalized, payload)
    except (KeyError, TypeError) as exc:
        raise ValueError("판독 묶음의 타입이나 범주가 잘못됐다") from exc
    skeleton = {
        "findings": [
            {k: ([] if k == "items" else f[k]) for k in ("claimId", "items", "note")}
            for f in normalized["findings"]
        ]
    }
    for index, (finding, items) in enumerate(zip(normalized["findings"], originals, strict=True)):
        counts = Counter(
            it.get("responseTurnId")
            for it in items
            if isinstance(it, dict) and isinstance(it.get("responseTurnId"), str)
        )
        for raw in items:
            try:
                if (
                    not isinstance(raw, dict)
                    or not isinstance(raw.get("conditionBasis"), str)
                    or raw["conditionBasis"] not in BASES
                ):
                    raise ValueError("조건을 답변 이전에 관찰할 수 있는지 판독하지 않음")
                probe = deepcopy(skeleton)
                probe["findings"][index]["items"] = [
                    {k: v for k, v in raw.items() if k != "conditionBasis"}
                ]
                base.validate_phase(phase, probe, payload)
                if counts[raw["responseTurnId"]] > 1:
                    raise ValueError("한 후보 안의 중복 응답은 보류한다")
            except (ValueError, TypeError, KeyError) as exc:
                finding["invalidItems"].append(dict(item=raw, reason=str(exc)))
            else:
                finding["items"].append(raw)
    for finding, note in zip(normalized["findings"], notes, strict=True):
        finding["note"] = note
    out.clear()
    out.update(normalized)


def aggregate(audits, claims, records):
    normalized = deepcopy(audits)
    for row in normalized:
        for finding in row["findings"]:
            for it in finding["items"]:
                if it.get("conditionBasis") not in {"explicit_user_act", "visible_turn_sequence"}:
                    it["applicability"] = "unclear"
    return base.aggregate(normalized, claims, records)


def check_eligibility(claim):
    if claim["usageAxis"] == "softening" and claim["dimension"] != "continuation":
        raise ValueError("표현 완화는 이전 본인 발화와 후속 반응의 변화 근거가 필요하다")


def review_fields(decisions):
    coverage = {}
    for axis in AXES:
        rows = [d for d in decisions if d["claim"]["usageAxis"] == axis]
        retained = [d["claim"]["id"] for d in rows if d["retained"]]
        coverage[axis] = dict(
            label=AXES[axis],
            candidates=[d["claim"]["id"] for d in rows],
            retained=retained,
            status="review_candidate" if retained else "insufficient" if rows else "unobserved",
        )
    return dict(usageCoverage=coverage)


def call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    return _call(
        ctx, cid, folder, budget, phase, key, payload, version=VERSION, validator=validate_transport
    )


def build_usage(ctx, cid, packet, source, binding, folder, budget, rework=None):
    return base.build_tendencies(
        ctx, cid, packet, source, binding, folder, budget, rework, profile=sys.modules[__name__]
    )
