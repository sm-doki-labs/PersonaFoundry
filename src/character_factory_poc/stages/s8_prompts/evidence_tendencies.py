"""Scoped speech functions and linguistic realizations; mixed evidence is retained.

This builds review candidates, not statistically established laws or G6 approval.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.stages.s8_prompts.evidence_atomic import UNOBSERVED, partition
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    SECTIONS,
    _text,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_source import validate_card

VERSION = "evidence-pipeline-v4"
# A claim is kept when independent confirmation chunks support it at least this many times.
MIN_CONFIRMATION_SUPPORT = 1  # v4 as approved for pv6; v6 raises it to 3
# Thin-support filter, applied before compilation; the decision records the numbers.
# conversations: distinct conversations with joint function+form support across both halves,
# capped at the source's conversation count. share: support among applicable responses whose
# function and form were both judged (support / (support + variation)). Calibrated on Ikjun:
# every approved pv6 card had 18+ conversations and share 0.61+; held 5-ref cards had 3-5.
# Audits cite at most a few representative responses per chunk, so share is a sample ratio,
# not an occurrence rate. Override with [stages.s8] evidence_min_support = { ... }.
MIN_SUPPORT = dict(conversations=8, share=0.5)
MAX_CONSOLIDATED = 40
FIELDS = {
    "section",
    "function",
    "dimension",
    "trigger",
    "realization",
    "linguisticLevel",
    "exclusion",
    "observability",
    "evidence",
}
LEVELS = {"morphology", "syntax", "discourse", "lexical_register", "turn_management"}
BLANK_NOTE = "묶음 요약 없음(모델이 비워 둠). 판단은 개별 항목 사유로 한다."
LEVEL_LABELS = {
    "morphology": "어미·말높임",
    "syntax": "생략·절 연결",
    "discourse": "담화 표지·수선",
    "lexical_register": "어휘 사용역",
    "turn_management": "말차례 길이·종료",
}


def targets(chunk):
    """Bind every eligible response to its actual speaker and preceding turns."""
    result = {}
    for seg in chunk["segments"]:
        turns = seg["turns"]
        for i, t in enumerate(turns):
            if t["speaker"] != "SUBJECT" or not i or turns[i - 1]["speaker"] != "USER":
                continue
            result[t["id"]] = dict(
                responseTurnId=t["id"],
                precedingUserIds=[p["id"] for p in turns[:i] if p["speaker"] == "USER"],
                previousSubjectTurnId=next(
                    (p["id"] for p in reversed(turns[:i]) if p["speaker"] == "SUBJECT"), None
                ),
            )
    return result


def to_card(c, refs, state):
    for k in FIELDS - {"evidence"}:
        _text(c[k], k)
        if re.search(r"[ㄱ-ㅎㅏ-ㅣ]{2,}", c[k]):
            raise ValueError("특징에 발화 예시 표기가 있다")
    values = dict(first=UNOBSERVED, shift=UNOBSERVED, stop=UNOBSERVED)
    values[{"response": "first", "continuation": "shift", "closure": "stop"}[c["dimension"]]] = (
        f"가능한 반응 경향의 대화 기능은 {c['function']}이다. "
        f"언어적 실현({LEVEL_LABELS[c['linguisticLevel']]}): {c['realization']}"
    )
    limit = c["exclusion"] + " 이 특징은 매번 수행할 의무나 고정된 반응 순서가 아니다."
    if state == "mixed":
        limit += (
            " 같은 적용 범위에서 다른 반응 또는 미판정 근거도 있어"
            " 단일한 방식으로 일반화하지 않는다."
        )
    return dict(
        section=c["section"],
        trigger=c["trigger"],
        **values,
        limit=limit,
        evidence=refs,
        rule=c["function"],
    )


def validate_phase(phase, out, payload):
    if phase in {"tendency-discover", "tendency-consolidate"}:
        if (
            not isinstance(out, dict)
            or set(out) != {"claims"}
            or not isinstance(out["claims"], list)
            # Discovery stays a bounded per-chunk scan; consolidation has no target count and
            # only a transport guard. Retention is decided by evidence (state_for), D-0196.
            or len(out["claims"])
            > (
                payload.get("discoverLimit", 12)
                if phase == "tendency-discover"
                else MAX_CONSOLIDATED
            )
        ):
            raise ValueError("조건부 특징 형식 오류")
        for c in out["claims"]:
            if not isinstance(c, dict) or set(c) != FIELDS:
                raise ValueError("기능/언어 형식 분리 필드가 다르다")
            if (
                c["section"] not in SECTIONS[1:]
                or c["dimension"] not in {"response", "continuation", "closure"}
                or c["linguisticLevel"] not in LEVELS
                or c["observability"] not in {"prior_context", "unknown"}
            ):
                raise ValueError("알 수 없는 특징 범주")
            refs = c["evidence"]
            if (
                not isinstance(refs, list)
                or not refs
                or any(not isinstance(r, str) for r in refs)
                or len(set(refs)) != len(refs)
                or not set(refs) <= set(payload["allowedIds"])
            ):
                raise ValueError("허용 원문 밖의 특징 근거")
            to_card(c, refs, "mixed")
        return
    if (
        not isinstance(out, dict)
        or set(out) != {"findings"}
        or not isinstance(out["findings"], list)
    ):
        raise ValueError("근거 대조 형식 오류")
    claims = {c["id"]: c for c in payload["claims"]}
    seen = set()
    ts = {t["id"]: t for s in payload["chunk"]["segments"] for t in s["turns"]}
    for f in out["findings"]:
        if (
            not isinstance(f, dict)
            or set(f) != {"claimId", "items", "note"}
            or f["claimId"] not in claims
            or f["claimId"] in seen
            or not isinstance(f["items"], list)
            or not isinstance(f["note"], str)
            or not f["note"].strip()
        ):
            raise ValueError("누락되거나 중복된 특징 대조")
        seen.add(f["claimId"])
        ids = set()
        for it in f["items"]:
            if not isinstance(it, dict) or set(it) != {
                "responseTurnId",
                "conditionTurnId",
                "conditionQuote",
                "responseQuote",
                "applicability",
                "functionMatch",
                "formMatch",
                "reason",
            }:
                raise ValueError("말차례 대조 필드 오류")
            rid = it["responseTurnId"]
            target = payload["targets"].get(rid)
            if target is None or rid in ids:
                raise ValueError("입력 밖 또는 중복 응답")
            ids.add(rid)
            for k, allowed in [
                ("applicability", {"yes", "no", "unclear"}),
                ("functionMatch", {"present", "absent", "unclear"}),
                ("formMatch", {"present", "absent", "unclear"}),
            ]:
                if it[k] not in allowed:
                    raise ValueError("알 수 없는 대조 분류")
            if (
                claims[f["claimId"]]["dimension"] == "continuation"
                and not target["previousSubjectTurnId"]
                and it["applicability"] == "yes"
            ):
                raise ValueError("후속 응답 이전의 본인 발화가 없다")
            uid = it["conditionTurnId"]
            quote = it["conditionQuote"]
            if (
                uid not in target["precedingUserIds"]
                or not isinstance(quote, str)
                or not quote
                or quote not in ts[uid]["text"]
            ):
                raise ValueError("조건 인용은 같은 문맥의 이전 USER여야 한다")
            if (
                not isinstance(it["responseQuote"], str)
                or not it["responseQuote"]
                or it["responseQuote"] not in ts[rid]["text"]
            ):
                raise ValueError("지정 응답의 정확한 원문 인용이 아니다")
            if not isinstance(it["reason"], str) or not it["reason"].strip():
                raise ValueError("판독 사유가 없다")
    if seen != set(claims):
        raise ValueError("특징별 대조가 누락됐다")


def validate_transport(phase, out, payload):
    """Keep erroneous citations verbatim but exclude them from evidence counts."""
    from collections import Counter
    from copy import deepcopy

    if phase in {"tendency-discover", "tendency-consolidate"}:
        return _hold_quoted_claims(phase, out, payload)
    if (
        not isinstance(out, dict)
        or set(out) != {"findings"}
        or not isinstance(out["findings"], list)
    ):
        return validate_phase(phase, out, payload)
    normalized = deepcopy(out)
    skeleton = {"findings": []}
    for f in normalized["findings"]:
        if (
            not isinstance(f, dict)
            or set(f)
            not in ({"claimId", "items", "note"}, {"claimId", "items", "note", "invalidItems"})
            or not isinstance(f.get("items"), list)
        ):
            raise ValueError("대조 묶음 형식이 다르다")
        if isinstance(f["note"], str) and not f["note"].strip():
            # 근거가 없는 특징은 모델이 요약을 비워 두곤 한다. 판단은 항목별 사유로만 한다(D-0186).
            f["note"] = BLANK_NOTE
        skeleton["findings"].append(
            {k: ([] if k == "items" else f[k]) for k in ("claimId", "items", "note")}
        )
    validate_phase(phase, skeleton, payload)
    for index, f in enumerate(normalized["findings"]):
        invalid = f.get("invalidItems", [])
        if not isinstance(invalid, list) or any(
            not isinstance(x, dict)
            or set(x) != {"item", "reason"}
            or not isinstance(x["reason"], str)
            for x in invalid
        ):
            raise ValueError("보류 인용 형식 오류")
        counts = Counter(
            i.get("responseTurnId")
            for i in f["items"]
            if isinstance(i, dict) and isinstance(i.get("responseTurnId"), str)
        )
        valid = []
        for it in f["items"]:
            probe = deepcopy(skeleton)
            probe["findings"][index]["items"] = [it]
            try:
                validate_phase(phase, probe, payload)
                if counts[it["responseTurnId"]] > 1:
                    raise ValueError("한 후보 안의 중복 응답은 보류한다")
            except (ValueError, TypeError, KeyError) as exc:
                invalid.append(dict(item=it, reason=str(exc)))
            else:
                valid.append(it)
        f["items"], f["invalidItems"] = valid, invalid
    out.clear()
    out.update(normalized)


def _hold_quoted_claims(phase, out, payload):
    """후보 특징은 G6 검토 전 후보다. 문장에 발화를 인용한 특징 하나 때문에 묶음 전체를 버리지 않고,
    그 특징만 사유와 함께 heldClaims로 보관한 뒤 나머지로 진행한다(D-0186).

    형식·범주·근거 범위가 틀린 응답은 지금처럼 통째로 거절한다. 최종 프롬프트 검사는 그대로다."""
    from copy import deepcopy

    if (
        not isinstance(out, dict)
        or not set(out) <= {"claims", "heldClaims"}
        or "claims" not in out
        or not isinstance(out["claims"], list)
    ):
        return validate_phase(phase, out, payload)
    held = out.get("heldClaims", [])
    if not isinstance(held, list) or any(
        not isinstance(h, dict)
        or set(h) != {"claim", "reason"}
        or not isinstance(h["reason"], str)
        or not h["reason"].strip()
        for h in held
    ):
        raise ValueError("보류 특징 형식 오류")
    # 문장 내용을 빼고 형식·범주·근거만 먼저 본다. 여기서 틀리면 응답 전체를 거절한다.
    shape = deepcopy(out["claims"])
    for c in shape:
        if isinstance(c, dict):
            for k in ("function", "trigger", "realization", "exclusion"):
                if isinstance(c.get(k), str) and c[k].strip():
                    c[k] = "검사용 문장"
    validate_phase(phase, {"claims": shape}, payload)
    kept = []
    for c in out["claims"]:
        try:
            validate_phase(phase, {"claims": [c]}, payload)
        except ValueError as exc:
            held = [*held, dict(claim=c, reason=str(exc))]
        else:
            kept.append(c)
    out.clear()
    out["claims"] = kept
    if held:
        out["heldClaims"] = held


def aggregate(audits, claims, records):
    units = {r["id"]: tuple(r["unit"]) for r in records}
    result = {}
    for c in claims:
        groups = {
            k: set()
            for k in [
                "support",
                "variation",
                "outside",
                "unclear",
                "functionPresent",
                "formPresent",
            ]
        }
        classifications = {}
        invalid_count = 0
        for row in audits:
            for f in row["findings"]:
                if f["claimId"] != c["id"]:
                    continue
                invalid_count += len(f.get("invalidItems", []))
                for it in f["items"]:
                    rid = it["responseTurnId"]
                    if rid not in units:
                        raise ValueError("집계 대상 응답이 원문 기록에 없다")
                    app = it["applicability"]
                    if app == "no":
                        kind = "outside"
                    elif app == "unclear" or "unclear" in (it["functionMatch"], it["formMatch"]):
                        kind = "unclear"
                    elif it["functionMatch"] == it["formMatch"] == "present":
                        kind = "support"
                    else:
                        kind = "variation"
                    groups[kind].add(rid)
                    classifications.setdefault(rid, set()).add(kind)
                    if app == "yes":
                        if it["functionMatch"] == "present":
                            groups["functionPresent"].add(rid)
                        if it["formMatch"] == "present":
                            groups["formPresent"].add(rid)
        conflicts = {r for r, ks in classifications.items() if len(ks) > 1}
        for k in groups:
            groups[k] -= conflicts
        groups["unclear"] |= conflicts
        result[c["id"]] = {k: sorted(v) for k, v in groups.items()}
        result[c["id"]].update(
            supportUnits=len({units[r] for r in groups["support"]}),
            conflicts=sorted(conflicts),
            invalidCount=invalid_count,
        )
    return result


def state_for(dev, confirm, min_confirm=MIN_CONFIRMATION_SUPPORT):
    if type(min_confirm) is not int or min_confirm < 1:
        raise ValueError("min_confirmation_support는 1 이상의 정수다")
    if dev["supportUnits"] < 2 or confirm["supportUnits"] < min_confirm:
        return "insufficient"
    return (
        "mixed"
        if any(s.get(k) for s in [dev, confirm] for k in ["variation", "unclear", "invalidCount"])
        else "evidence_present"
    )


def support_rule(cfg, conversations, default=MIN_SUPPORT):
    raw = cfg.get("evidence_min_support", {})
    if not isinstance(raw, dict) or not set(raw) <= {"conversations", "share"}:
        raise ValueError("evidence_min_support는 conversations·share만 받는다")
    rule = dict(default) | raw
    n, share = rule["conversations"], rule["share"]
    if type(n) is not int or n < 1:
        raise ValueError("evidence_min_support.conversations는 1 이상의 정수다")
    if type(share) not in (int, float) or not 0 <= share <= 1:
        raise ValueError("evidence_min_support.share는 0~1 사이 수다")
    return dict(
        minConversations=n,
        minShare=float(share),
        sourceConversations=conversations,
        requiredConversations=max(1, min(n, conversations)),
        shareBasis="support / (support + variation), 발견·확인 합계",
    )


def support_stats(dev, confirm, units):
    support = set(dev["support"]) | set(confirm["support"])
    variation = (set(dev["variation"]) | set(confirm["variation"])) - support
    applicable = len(support) + len(variation)
    return dict(
        responses=len(support),
        conversations=len({units[r] for r in support}),
        developmentConversations=dev["supportUnits"],
        confirmationConversations=confirm["supportUnits"],
        applicable=applicable,
        share=round(len(support) / applicable, 4) if applicable else 0.0,
    )


def thin_support(stats, rule):
    """Return the hold reason when support is too thin, else None."""
    few = stats["conversations"] < rule["requiredConversations"]
    low = stats["responses"] < rule["minShare"] * stats["applicable"] or not stats["applicable"]
    if not (few or low):
        return None
    failed = "·".join(x for x, bad in [("대화 수", few), ("지지 비율", low)] if bad)
    return (
        f"지지 근거가 얇다({failed} 미달): 기능·형식을 함께 지지한 대화 "
        f"{stats['conversations']}개(기준 {rule['requiredConversations']}개), "
        f"판정된 적용 응답 중 지지 {stats['responses']}/{stats['applicable']}건"
        f"({stats['share']:.0%}, 기준 {rule['minShare']:.0%})"
    )


def call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    return _call(
        ctx, cid, folder, budget, phase, key, payload, version=VERSION, validator=validate_transport
    )


# --- evidence-v7: compact transport and per-conversation citation ------------------------
# v7 keeps v4's claims, thresholds and cards. It changes only what is sent and how audit
# citations are bounded: chunks travel as one line per turn, targets/allowedIds are rebuilt
# locally for validation, and each claim may cite one response per conversation per kind,
# so the support rule counts supporting conversations instead of chunks.
COMPACT_VERSION = "evidence-pipeline-v7"
# Claims per audit call. With all 12 claims in one call the model cited about one response
# per claim per chunk, so supporting-conversation counts tracked the chunk count again. Four
# claims per call keeps the model on each claim across the ~20 conversations of a chunk.
COMPACT_AUDIT_BATCH = 4
# Discovery reads chunks ~4.5x larger than v4's, so the per-chunk observation cap scales too
# (v4: 27 chunks x 6 = 162 observations; v7: 6 chunks x 18 = 108).
COMPACT_DISCOVER_LIMIT = 18
# Response-size safety line for one audit call. v4 items averaged ~200 output tokens (24 items
# ~4.7k). v7 audits get 32k output tokens (evidence_full_pipeline._output_limit) and a 40-char
# reason, so 96 items (8 per claim at 12 claims) stay well inside it. Fewer chunks must not cap
# the supporting-conversation count near the 8-conversation rule.
AUDIT_ITEM_LIMIT = 96
_AUDIT_PHASES = {"tendency-audit", "tendency-confirm"}


def citation_limits(claims):
    per_claim = max(2, AUDIT_ITEM_LIMIT // max(1, len(claims)))
    return dict(
        perConversation=dict(support=1, variation=1, outsideOrUnclear=1),
        perClaim=per_claim,
        perCall=AUDIT_ITEM_LIMIT,
    )


def _citation_kind(it):
    if it["applicability"] != "yes" or "unclear" in (it["functionMatch"], it["formMatch"]):
        return "outsideOrUnclear"
    if it["functionMatch"] == it["formMatch"] == "present":
        return "support"
    return "variation"


def compact_payload(phase, payload):
    """The request body actually sent: one-line chunk text, no locally derivable ID lists."""
    from character_factory_poc.stages.s8_prompts.evidence_full_source import compact_chunk

    body = {k: v for k, v in payload.items() if k not in {"targets", "allowedIds", "chunk"}}
    if "chunk" in payload:
        body["chunk"] = compact_chunk(payload["chunk"])
    if phase in _AUDIT_PHASES:
        body["citationLimits"] = citation_limits(payload["claims"])
    return body


def validate_compact(phase, out, payload):
    """v4 item checks on the full local payload, then per-conversation citation caps.

    Citations past a cap stay verbatim in overflowItems and are never counted. They are not
    citation errors, so they do not mark a claim as mixed. Re-validating a saved output is a
    no-op.
    """
    if phase not in _AUDIT_PHASES:
        return validate_transport(phase, out, payload)
    if not isinstance(out, dict) or not isinstance(out.get("findings"), list):
        return validate_transport(phase, out, payload)
    carried = []
    for f in out["findings"]:
        extra = f.pop("overflowItems", []) if isinstance(f, dict) else []
        if not isinstance(extra, list) or any(
            not isinstance(x, dict) or set(x) != {"item", "reason"} for x in extra
        ):
            raise ValueError("초과 인용 형식 오류")
        carried.append(extra)
    validate_transport(phase, out, payload)
    unit_of = {
        t["id"]: tuple(seg["unit"]) for seg in payload["chunk"]["segments"] for t in seg["turns"]
    }
    limits = citation_limits(payload["claims"])
    total = 0
    for f, overflow in zip(out["findings"], carried, strict=True):
        kept, slots = [], set()
        for it in f["items"]:
            slot = (unit_of[it["responseTurnId"]], _citation_kind(it))
            if slot in slots:
                reason = "같은 대화의 같은 판정은 한 건만 센다"
            elif len(kept) >= limits["perClaim"] or total >= limits["perCall"]:
                reason = "호출 인용 상한을 넘었다"
            else:
                slots.add(slot)
                kept.append(it)
                total += 1
                continue
            overflow = [*overflow, dict(item=it, reason=reason)]
        f["items"] = kept
        if overflow:
            f["overflowItems"] = overflow


def aggregate_compact(audits, claims, records):
    result = aggregate(audits, claims, records)
    for c in claims:
        result[c["id"]]["overflowCount"] = sum(
            len(f.get("overflowItems", []))
            for row in audits
            for f in row["findings"]
            if f["claimId"] == c["id"]
        )
    return result


def audit_batch(ctx, profile):
    """Claims per audit call. v7 reads [stages.s8] evidence_audit_batch (1~40) when set."""
    default = getattr(profile, "AUDIT_BATCH", None)
    if default is None:
        return None
    value = ctx.config.stage("s8").get("evidence_audit_batch", default)
    if type(value) is not int or not 1 <= value <= 40:
        raise ValueError("evidence_audit_batch는 1~40 정수다")
    return value


def compact_call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    if phase == "tendency-discover":
        payload = dict(payload, discoverLimit=COMPACT_DISCOVER_LIMIT)

    def check(phase, out, _sent):
        validate_compact(phase, out, payload)

    return _call(
        ctx,
        cid,
        folder,
        budget,
        phase,
        key,
        compact_payload(phase, payload),
        version=COMPACT_VERSION,
        validator=check,
    )


def _compact_partition(source):
    from character_factory_poc.stages.s8_prompts.evidence_atomic import partition_compact

    return partition_compact(source)


SEEDED_VERSION = "evidence-pipeline-v8"
# One chunk per half: the analyzer reads the whole development (or confirmation) half at once.
SEEDED_CHUNK_CHARS = 1_000_000


def seeded_call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    def check(phase, out, _sent):
        validate_compact(phase, out, payload)

    return _call(
        ctx,
        cid,
        folder,
        budget,
        phase,
        key,
        compact_payload(phase, payload),
        version=SEEDED_VERSION,
        validator=check,
        model_for=ctx.analyzer_model,
    )


def _seeded_partition(source):
    from character_factory_poc.stages.s8_prompts.evidence_atomic import partition_compact

    wide = dict(source, transport=dict(source["transport"], maxChunkChars=SEEDED_CHUNK_CHARS))
    return partition_compact(wide)


def s3_observations(ctx, cid, dev):
    """S3 scene-analysis observations of the approved plan, cited only on development turns."""
    rev = ctx.state(cid).gate("G3").rev
    folder = ctx.character_dir(cid) / "s3-plan" / str(rev) / "scene-analysis"
    allowed = {r for ch in dev for r in ch["recordIds"]}
    out = []
    for dimension in ("voice", "behavior", "facts-limits"):
        path = folder / f"{dimension}.json"
        if not path.is_file():
            raise ValueError("S3 원문 분석 결과가 없다. v8은 장면 분석 S3가 필요하다")
        data = read_json(path)
        claims = []
        for o in data.get("observations", []):
            refs = [r for r in o.get("evidence", []) if r in allowed]
            if refs:
                claims.append(
                    dict(description=o["description"], dimension=o["dimension"], evidence=refs)
                )
        out.append(
            dict(
                chunkId=f"s3-{rev}-{dimension}", claims=claims, model=data.get("ref"), heldClaims=[]
            )
        )
    if not any(o["claims"] for o in out):
        raise ValueError("S3 관찰 중 개발용 원문에 근거가 남는 것이 없다")
    return out


# --- evidence-v9: per-response labels, counted in code ----------------------------------
# S3 notes seed one consolidation call. Then the labeler reads every target response once and
# marks, per candidate, S (function and form present), V (condition holds, other reaction) or
# U (unclear). Labels are converted into the v4 finding items so aggregation, cards and the
# review checks stay the same. Counting every response gives real rates, so the support rule is
# 8 conversations and a 20% share ("this can happen in this situation"), D-0201.
LABELED_VERSION = "evidence-pipeline-v9"
LABEL_TARGETS_PER_CALL = 800
LABELED_MIN_SUPPORT = dict(conversations=8, share=0.2)
_LABEL_KINDS = {
    "S": ("yes", "present", "present"),
    "V": ("yes", "present", "absent"),
    "U": ("unclear", "unclear", "unclear"),
}


def _labeled_partition(source):
    """One half per call group: split each half on conversation borders into <= N targets."""
    dev, check, split = _seeded_partition(source)

    def cut(chunks, prefix):
        out, part, count = [], [], 0
        for ch in chunks:
            for seg in ch["segments"]:
                n = len(targets(dict(segments=[seg])))
                if part and count + n > LABEL_TARGETS_PER_CALL:
                    out.append(part)
                    part, count = [], 0
                part.append(seg)
                count += n
        if part:
            out.append(part)
        return [
            dict(
                id=f"{prefix}-{i:04d}",
                segments=segs,
                recordIds=[t["id"] for s in segs for t in s["turns"] if t["speaker"] == "SUBJECT"],
            )
            for i, segs in enumerate(out, 1)
        ]

    dev, check = cut(dev, "dev"), cut(check, "check")
    split = dict(
        split,
        developmentChunks=[dict(id=c["id"], recordIds=c["recordIds"]) for c in dev],
        confirmationChunks=[dict(id=c["id"], recordIds=c["recordIds"]) for c in check],
    )
    return dev, check, split


def _label_number(claims):
    return {c["id"]: f"{i:02d}" for i, c in enumerate(claims, 1)}


def label_payload(phase, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_source import compact_chunk

    number = _label_number(payload["claims"])
    keep = ("section", "dimension", "trigger", "function", "realization", "exclusion")
    return dict(
        role=payload["role"],
        scene=payload["scene"],
        facts=payload["facts"],
        claims=[dict(n=number[c["id"]], **{k: c[k] for k in keep}) for c in payload["claims"]],
        chunk=compact_chunk(payload["chunk"]),
    )


def validate_labels(out, payload):
    """Exact shape; unknown targets or codes are kept aside, never counted."""
    if (
        not isinstance(out, dict)
        or set(out) - {"labels"}
        or not isinstance(out.get("labels"), list)
    ):
        raise ValueError("응답별 표시 형식 오류")
    allowed = set(payload["targets"])
    number = set(_label_number(payload["claims"]).values())
    seen, invalid = set(), []
    for row in out["labels"]:
        ok = (
            isinstance(row, list)
            and row
            and isinstance(row[0], str)
            and row[0] in allowed
            and row[0] not in seen
            and all(
                isinstance(x, str) and len(x) == 3 and x[:2] in number and x[2] in _LABEL_KINDS
                for x in row[1:]
            )
        )
        if ok:
            seen.add(row[0])
        else:
            invalid.append(row)
    if len(invalid) > max(5, len(out["labels"]) // 20):
        raise ValueError("응답별 표시 중 잘못된 행이 많다")
    return invalid


def labels_to_findings(out, payload):
    """Deterministic: each label becomes a v4 item quoting the whole turns it refers to."""
    turns = {t["id"]: t for s in payload["chunk"]["segments"] for t in s["turns"]}
    tg = payload["targets"]
    by_number = {v: k for k, v in _label_number(payload["claims"]).items()}
    items = {c["id"]: [] for c in payload["claims"]}
    invalid = validate_labels(out, payload)
    for row in out["labels"]:
        if row in invalid:
            continue
        rid = row[0]
        uid = tg[rid]["precedingUserIds"][-1]
        for code in dict.fromkeys(row[1:]):
            app, fn, form = _LABEL_KINDS[code[2]]
            items[by_number[code[:2]]].append(
                dict(
                    responseTurnId=rid,
                    conditionTurnId=uid,
                    conditionQuote=turns[uid]["text"],
                    responseQuote=turns[rid]["text"],
                    applicability=app,
                    functionMatch=fn,
                    formMatch=form,
                    reason="응답별 표시 " + code[2],
                )
            )
    findings = [
        dict(claimId=c["id"], items=items[c["id"]], note="응답별 전수 표시")
        for c in payload["claims"]
    ]
    if invalid:
        findings[0]["invalidItems"] = [dict(item=row, reason="표시 형식 오류") for row in invalid]
    return {"findings": findings}


def labeled_call(ctx, cid, folder, budget, phase, key, payload, *, version=None, model_for=None):
    version = version or LABELED_VERSION
    model_for = model_for or ctx.labeler_model
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    if phase == "tendency-consolidate":

        def check(phase, out, _sent):
            # The labeler sometimes adds a few USER or out-of-half IDs among 100+ citations.
            # Drop just those IDs (and candidates left with none) instead of the whole answer;
            # every remaining ID is still checked, and the audit counts support independently.
            allowed = set(payload["allowedIds"])
            if isinstance(out, dict) and isinstance(out.get("claims"), list):
                for c in out["claims"]:
                    if isinstance(c, dict) and isinstance(c.get("evidence"), list):
                        c["evidence"] = [r for r in c["evidence"] if r in allowed]
                out["claims"] = [
                    c for c in out["claims"] if not isinstance(c, dict) or c.get("evidence")
                ]
            # v10 candidates may carry statedFacts (what the person said about themselves).
            # The v4 field check is exact, so set them aside while it runs and reattach them to
            # the same claim objects afterwards. Malformed lists are dropped, never counted.
            stash = {}
            if version == "evidence-pipeline-v10" and isinstance(out, dict):
                for c in out.get("claims") or []:
                    if isinstance(c, dict) and "statedFacts" in c:
                        facts = c.pop("statedFacts")
                        if (
                            isinstance(facts, list)
                            and len(facts) <= 3
                            and all(isinstance(f, str) and 0 < len(f.strip()) <= 120 for f in facts)
                        ):
                            stash[id(c)] = [f.strip() for f in facts]
            validate_compact(phase, out, payload)
            for c in out.get("claims") or []:
                if id(c) in stash:
                    c["statedFacts"] = stash[id(c)]

        return _call(
            ctx,
            cid,
            folder,
            budget,
            phase,
            key,
            compact_payload(phase, payload),
            version=version,
            validator=check,
            model_for=model_for,
        )
    local = dict(payload, targets=targets(payload["chunk"]))

    def check_labels(phase, out, _sent):
        validate_labels(out, local)

    out, model = _call(
        ctx,
        cid,
        folder,
        budget,
        phase,
        key,
        label_payload(phase, local),
        version=version,
        validator=check_labels,
        model_for=model_for,
    )
    return labels_to_findings(out, local), model


class CompactProfile:
    """build_tendencies profile for evidence-v7; v4 retention values are unchanged."""

    VERSION = COMPACT_VERSION
    MIN_CONFIRMATION_SUPPORT = MIN_CONFIRMATION_SUPPORT
    MIN_SUPPORT = MIN_SUPPORT
    AUDIT_BATCH = COMPACT_AUDIT_BATCH
    call = staticmethod(compact_call)
    to_card = staticmethod(to_card)
    aggregate = staticmethod(aggregate_compact)
    partition = staticmethod(_compact_partition)

    @staticmethod
    def check_eligibility(claim):
        return None

    @staticmethod
    def review_fields(decisions):
        return {}


class SeededProfile(CompactProfile):
    """evidence-v8: S3 whole-source observations seed one consolidation call, then the S3
    analyzer model audits each half in one chunk. Thresholds and cards are v4's."""

    VERSION = SEEDED_VERSION
    AUDIT_BATCH = 3
    call = staticmethod(seeded_call)
    partition = staticmethod(_seeded_partition)
    seed = staticmethod(s3_observations)


class LabeledProfile(CompactProfile):
    """evidence-v9: S3-seeded candidates, every response labelled once, code counts."""

    VERSION = LABELED_VERSION
    MIN_SUPPORT = LABELED_MIN_SUPPORT
    AUDIT_BATCH = 12
    call = staticmethod(labeled_call)
    aggregate = staticmethod(aggregate)
    partition = staticmethod(_labeled_partition)
    seed = staticmethod(s3_observations)


def build_tendencies(
    ctx, cid, packet, source, binding, folder, budget, rework=None, *, profile=None
):
    from character_factory_poc.common.budget import CallPlan
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import (
        atomic_retry_remaining,
    )

    run_call = call if profile is None else profile.call
    build_card = to_card if profile is None else profile.to_card
    aggregate_evidence = aggregate if profile is None else profile.aggregate
    version = VERSION if profile is None else profile.VERSION
    folder = Path(folder)
    if not source.get("coverage", {}).get("complete"):
        raise ValueError("전체 원문 범위 미완료")
    dev, confirm, split = getattr(profile, "partition", partition)(source)
    seed = getattr(profile, "seed", None)
    phases = (
        ([] if seed else [("tendency-discover", c["id"]) for c in dev])
        + [("tendency-consolidate", "all")]
        + [("tendency-audit", c["id"]) for c in dev]
        + [("tendency-confirm", c["id"]) for c in confirm]
    )
    remaining = sum(not (folder / "analysis" / f"{p}-{k}.json").exists() for p, k in phases)
    if budget is not None:
        budget.check_plan(
            [
                CallPlan(
                    "s8",
                    "기능·말투 분리와 전체 원문 대조",
                    remaining + (atomic_retry_remaining(folder) if remaining else 0),
                    None,
                )
            ]
        )
    workers = ctx.config.stage("s8").get("evidence_workers", 2)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("evidence_workers는 1~4다")
    common = {k: packet[k] for k in ["role", "scene", "facts"]}
    if rework:
        common["editorRevision"] = rework
    for name, value in [
        ("coverage", source["coverage"]),
        ("chunks", source["chunks"]),
        ("binding", binding),
        ("partition", split),
    ]:
        write_once_json(folder / f"evidence-{name}.json", value)

    def discover(ch):
        out, model = run_call(
            ctx,
            cid,
            folder,
            budget,
            "tendency-discover",
            ch["id"],
            dict(**common, chunk=ch, targets=targets(ch), allowedIds=ch["recordIds"]),
        )
        return dict(
            chunkId=ch["id"],
            claims=out["claims"],
            model=model,
            heldClaims=out.get("heldClaims", []),
        )

    if seed:
        # v8: the S3 whole-source analysis replaces per-chunk discovery. Its evidence is
        # limited to development responses so confirmation stays an independent check.
        observations = seed(ctx, cid, dev)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            observations = list(pool.map(discover, dev))
    write_once_json(folder / "evidence-observations.json", observations)
    excluded_claims = [
        dict(h, phase="tendency-discover", chunkId=o["chunkId"])
        for o in observations
        for h in o["heldClaims"]
    ]
    allowed = sorted({r for ch in dev for r in ch["recordIds"]})
    merge = getattr(profile, "merge_observations", None)
    if merge is not None:
        # v6: code merges only identical (section, function, level, dimension) observations.
        # A single model call tended to collapse distinct tendencies (57 found -> 8 kept).
        merged, merge_log = merge(observations)
        write_once_json(folder / "evidence-consolidation.json", merge_log)
        model = observations[0]["model"] if observations else None
        claims = [dict(c, id=f"tendency-{i:02d}") for i, c in enumerate(merged, 1)]
    else:
        out, model = run_call(
            ctx,
            cid,
            folder,
            budget,
            "tendency-consolidate",
            "all",
            dict(
                **common,
                observations=[
                    {k: v for k, v in o.items() if k != "heldClaims"} for o in observations
                ],
                allowedIds=allowed,
                # v8 writes claims from S3 notes, so it also reads the cited development text.
                **(
                    {}
                    if not seed
                    else dict(chunk=dev[0])
                    if len(dev) == 1
                    else dict(
                        chunk=dict(
                            id="dev-all",
                            segments=[s for ch in dev for s in ch["segments"]],
                            recordIds=allowed,
                        )
                    )
                ),
            ),
        )
        claims = [dict(c, id=f"tendency-{i:02d}") for i, c in enumerate(out["claims"], 1)]
        excluded_claims.extend(
            dict(h, phase="tendency-consolidate", chunkId="all") for h in out.get("heldClaims", [])
        )
    write_once_json(folder / "evidence-locked-tendencies.json", claims)
    batch = audit_batch(ctx, profile) or len(claims) or 1
    groups = [claims[i : i + batch] for i in range(0, len(claims), batch)]

    # Every (phase, chunk, claim group) call is independent, so they share one pool. Results are
    # reassembled in chunk and group order, so the saved audits match a sequential run.
    jobs = [
        (phase, ch, n, group)
        for phase, chunks in (("tendency-audit", dev), ("tendency-confirm", confirm))
        for ch in chunks
        for n, group in enumerate(groups, 1)
    ]

    def one(job):
        phase, ch, n, group = job
        key = ch["id"] if len(groups) == 1 else f"{ch['id']}-g{n:02d}"
        return run_call(
            ctx,
            cid,
            folder,
            budget,
            phase,
            key,
            dict(**common, chunk=ch, targets=targets(ch), claims=group),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = (
            dict(zip([id(j) for j in jobs], pool.map(one, jobs), strict=True)) if claims else {}
        )

    def audit(chunks, phase):
        if not claims:
            return []
        out = []
        for ch in chunks:
            findings, model = [], None
            for job in jobs:
                if job[0] == phase and job[1] is ch:
                    found, model = results[id(job)]
                    findings.extend(found["findings"])
            out.append(dict(chunkId=ch["id"], findings=findings, model=model))
        return out

    development = audit(dev, "tendency-audit")
    confirmation = audit(confirm, "tendency-confirm")
    write_once_json(folder / "evidence-development-audits.json", development)
    write_once_json(folder / "evidence-confirmation-audits.json", confirmation)
    ds = aggregate_evidence(development, claims, source["records"])
    cs = aggregate_evidence(confirmation, claims, source["records"])
    accepted = []
    held = []
    decisions = []
    owner = {}
    speech = [t["text"] for ch in source["chunks"] for seg in ch["segments"] for t in seg["turns"]]
    min_confirm = ctx.config.stage("s8").get(
        "min_confirmation_support",
        getattr(profile, "MIN_CONFIRMATION_SUPPORT", MIN_CONFIRMATION_SUPPORT),
    )
    units = {r["id"]: tuple(r["unit"]) for r in source["records"]}
    rule = support_rule(
        ctx.config.stage("s8"),
        len(split["developmentUnits"]) + len(split["confirmationUnits"]),
        getattr(profile, "MIN_SUPPORT", MIN_SUPPORT),
    )
    for c in claims:
        d, v = ds[c["id"]], cs[c["id"]]
        state = state_for(d, v, min_confirm)
        stats = support_stats(d, v, units)
        decision = dict(claim=c, development=d, confirmation=v, state=state, support=stats)
        try:
            if profile is not None:
                profile.check_eligibility(c)
            if c["observability"] != "prior_context":
                raise ValueError("응답 이전에 확인할 수 없는 적용 조건")
            if state == "insufficient":
                raise ValueError(
                    "기능과 언어 형식의 공동 반복 근거 부족"
                    f"(발견 쪽 {d['supportUnits']}건·확인용 원문 {v['supportUnits']}건, "
                    f"기준 2건·{min_confirm}건)"
                )
            thin = thin_support(stats, rule)
            if thin:
                raise ValueError(thin)
            card = build_card(c, sorted(set(d["support"]) | set(v["support"])), state)
            validate_card(card, source["records"], extra_speech=speech)
            compile_prompt(packet | {"sections": [card]})
        except (ValueError, TypeError, KeyError) as exc:
            held.append(dict(decision, reason=str(exc)))
            decision["retained"] = False
        else:
            accepted.append(card)
            owner[id(card)] = decision
            decision["retained"] = True
        decisions.append(decision)
    dedupe = getattr(profile, "dedupe_forms", None)
    if dedupe is not None:
        accepted, duplicates = dedupe(accepted)
        for card, forms in duplicates:
            decision = owner[id(card)]
            decision["retained"] = False
            decision["duplicateForms"] = forms
            held.append(
                dict(
                    decision,
                    reason="같은 언어 형식("
                    + ", ".join(f"'{f}'" for f in forms)
                    + ")을 근거가 더 많은 카드가 이미 설명함",
                )
            )
    scope = getattr(profile, "scope_cards", None)
    if scope is not None:
        accepted, _ = scope(accepted)
    write_once_json(folder / "evidence-tendency-decisions.json", decisions)
    extra_review = {} if profile is None else profile.review_fields(decisions)
    if "retentionRule" in extra_review:
        # Record the threshold actually applied, including a configured override.
        extra_review["retentionRule"]["minConfirmationSupport"] = min_confirm
    if extra_review:
        write_once_json(folder / "evidence-usage-coverage.json", extra_review)
    files = (
        list((folder / "analysis").glob("*.json"))
        + list((folder / "analysis/receipts").glob("*.json"))
        + list(folder.glob("evidence-*.json"))
    )
    files = [p for p in files if p.name not in {"evidence-review.json", "evidence-packet.json"}]
    review = dict(
        schemaVersion="evidence-review-" + version.rsplit("-", 1)[-1],
        **extra_review,
        status="AWAITING_HUMAN" if accepted else "HELD",
        supportRule=rule,
        records=source["records"],
        cards=accepted,
        held=held,
        excludedClaims=excluded_claims,
        stats=source["stats"],
        binding=binding,
        coverage=source["coverage"],
        partition=split,
        auditCoverage=dict(
            complete=bool(claims)
            and len(development) == len(dev)
            and len(confirmation) == len(confirm),
            developmentChunks=len(dev),
            confirmationChunks=len(confirm),
            claims=len(claims),
            checkedPairs=(len(development) + len(confirmation)) * len(claims),
        ),
        responseModel=model,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    if not accepted:
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("반복 근거를 갖춘 조건부 특징이 없다")
    packet = packet | {"sections": accepted}
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    review["packetSha256"] = sha256_file(folder / "evidence-packet.json")
    write_once_json(folder / "evidence-review.json", review)
    return text, dict(
        compiler=version,
        responseModel=model,
        status="AWAITING_HUMAN",
        evidenceReviewSha256=sha256_file(folder / "evidence-review.json"),
    )
