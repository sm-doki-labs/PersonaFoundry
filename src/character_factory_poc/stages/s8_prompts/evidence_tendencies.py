"""Scoped speech functions and linguistic realizations; mixed evidence is retained.

This builds review candidates, not statistically established laws or G6 approval.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import write_once_json
from character_factory_poc.stages.s8_prompts.evidence_atomic import UNOBSERVED, partition
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    SECTIONS,
    _text,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_source import validate_card

VERSION = "evidence-pipeline-v4"
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
            or len(out["claims"]) > 12
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
        return validate_phase(phase, out, payload)
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


def state_for(dev, confirm):
    if dev["supportUnits"] < 2 or confirm["supportUnits"] < 1:
        return "insufficient"
    return (
        "mixed"
        if any(s.get(k) for s in [dev, confirm] for k in ["variation", "unclear", "invalidCount"])
        else "evidence_present"
    )


def call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    return _call(
        ctx, cid, folder, budget, phase, key, payload, version=VERSION, validator=validate_transport
    )


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
    dev, confirm, split = partition(source)
    phases = (
        [("tendency-discover", c["id"]) for c in dev]
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
        return dict(chunkId=ch["id"], claims=out["claims"], model=model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        observations = list(pool.map(discover, dev))
    write_once_json(folder / "evidence-observations.json", observations)
    allowed = sorted({r for ch in dev for r in ch["recordIds"]})
    out, model = run_call(
        ctx,
        cid,
        folder,
        budget,
        "tendency-consolidate",
        "all",
        dict(**common, observations=observations, allowedIds=allowed),
    )
    claims = [dict(c, id=f"tendency-{i:02d}") for i, c in enumerate(out["claims"], 1)]
    write_once_json(folder / "evidence-locked-tendencies.json", claims)

    def audit(chunks, phase):
        def one(ch):
            out, model = run_call(
                ctx,
                cid,
                folder,
                budget,
                phase,
                ch["id"],
                dict(**common, chunk=ch, targets=targets(ch), claims=claims),
            )
            return dict(chunkId=ch["id"], findings=out["findings"], model=model)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, chunks)) if claims else []

    development = audit(dev, "tendency-audit")
    confirmation = audit(confirm, "tendency-confirm")
    write_once_json(folder / "evidence-development-audits.json", development)
    write_once_json(folder / "evidence-confirmation-audits.json", confirmation)
    ds = aggregate_evidence(development, claims, source["records"])
    cs = aggregate_evidence(confirmation, claims, source["records"])
    accepted = []
    held = []
    decisions = []
    speech = [t["text"] for ch in source["chunks"] for seg in ch["segments"] for t in seg["turns"]]
    for c in claims:
        d, v = ds[c["id"]], cs[c["id"]]
        state = state_for(d, v)
        decision = dict(claim=c, development=d, confirmation=v, state=state)
        try:
            if profile is not None:
                profile.check_eligibility(c)
            if c["observability"] != "prior_context":
                raise ValueError("응답 이전에 확인할 수 없는 적용 조건")
            if state == "insufficient":
                raise ValueError("기능과 언어 형식의 공동 반복 근거 부족")
            card = build_card(c, sorted(set(d["support"]) | set(v["support"])), state)
            validate_card(card, source["records"], extra_speech=speech)
            compile_prompt(packet | {"sections": [card]})
        except (ValueError, TypeError, KeyError) as exc:
            held.append(dict(decision, reason=str(exc)))
            decision["retained"] = False
        else:
            accepted.append(card)
            decision["retained"] = True
        decisions.append(decision)
    write_once_json(folder / "evidence-tendency-decisions.json", decisions)
    extra_review = {} if profile is None else profile.review_fields(decisions)
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
        records=source["records"],
        cards=accepted,
        held=held,
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
