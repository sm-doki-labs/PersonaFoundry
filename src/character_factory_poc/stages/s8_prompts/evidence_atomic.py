"""Atomic conditional claims with disjoint development/confirmation units.

Model labels are never human approval. Confirmation may only retain or hold;
its contents cannot repair a candidate in this revision.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.store import write_once_json
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    SECTIONS,
    _text,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_source import validate_card

VERSION = "evidence-pipeline-v3"
UNOBSERVED = "이 항목은 독립 근거로 확인하지 않아 별도 반응을 지시하지 않는다."
FIELDS = {"section", "function", "dimension", "trigger", "behavior", "exclusion", "evidence"}


def partition(source):
    units = {tuple(seg["unit"]) for ch in source["chunks"] for seg in ch["segments"]}
    if len(units) < 3:
        raise ValueError("발견과 독립 확인을 분리할 대화가 세 개 이상 필요하다")
    ordered = sorted(units, key=lambda u: sha256_text(json.dumps(u, ensure_ascii=False)))
    confirmation = set(ordered[: max(1, len(ordered) // 4)])

    def subset(check):
        out = []
        for ch in source["chunks"]:
            segs = [s for s in ch["segments"] if (tuple(s["unit"]) in confirmation) == check]
            if segs:
                out.append(
                    dict(
                        id=ch["id"],
                        segments=segs,
                        recordIds=list(
                            dict.fromkeys(
                                t["id"]
                                for s in segs
                                for t in s["turns"]
                                if t["speaker"] == "SUBJECT"
                            )
                        ),
                    )
                )
        return out

    dev, check = subset(False), subset(True)
    return (
        dev,
        check,
        dict(
            schemaVersion="evidence-partition-v1",
            complete=True,
            developmentUnits=[list(u) for u in ordered if u not in confirmation],
            confirmationUnits=[list(u) for u in ordered if u in confirmation],
            policy="fixed hash split before discovery; confirmation never used for repair",
        ),
    )


def partition_compact(source):
    """evidence-v7: the same fixed unit split, each half repacked into as few chunks as fit.

    v4 kept the confirmation half on the original whole-source chunk borders, so many calls
    carried only a few turns. Here each half is packed again on the one-line transport bound,
    keeping a conversation in one chunk whenever it fits. Membership is identical to partition().
    """
    from character_factory_poc.stages.s8_prompts.evidence_full_source import (
        TRANSPORT,
        lines_size,
        make_chunk,
        pack_units,
    )

    transport = source.get("transport") or {}
    bound = transport.get("maxChunkChars")
    if transport.get("format") != TRANSPORT or type(bound) is not int:
        raise ValueError("한 줄 원문 형식으로 준비한 원문이 아니다")
    dev, check, split = partition(source)

    def repack(chunks, prefix):
        pieces = [seg for ch in chunks for seg in ch["segments"]]
        bins = pack_units(pieces, lambda parts: lines_size(parts) <= bound)
        return [make_chunk(b, f"{prefix}-{n:04d}") for n, b in enumerate(bins, 1)]

    def summary(chunks):
        return [
            dict(
                id=ch["id"],
                units=[list(u) for u in dict.fromkeys(tuple(s["unit"]) for s in ch["segments"])],
                turns=sum(len(s["turns"]) for s in ch["segments"]),
                records=len(ch["recordIds"]),
                chars=lines_size(ch["segments"]),
            )
            for ch in chunks
        ]

    dev, check = repack(dev, "dev"), repack(check, "check")
    split = dict(
        split,
        schemaVersion="evidence-partition-v2",
        transport=TRANSPORT,
        maxChunkChars=bound,
        developmentChunks=summary(dev),
        confirmationChunks=summary(check),
        policy=split["policy"] + "; each half repacked on conversation borders",
    )
    return dev, check, split


def to_card(c, refs):
    # Letter sequences presented as things to say are lexical examples, even
    # when they evade the quoted-dialogue guard. Describe them linguistically.
    if any(
        re.search(r"[ㄱ-ㅎㅏ-ㅣ]{2,}", c[k])
        for k in ("function", "trigger", "behavior", "exclusion")
    ):
        raise ValueError("최종 특징에 구체 발화 표기 예시가 있다")
    values = dict(first=UNOBSERVED, shift=UNOBSERVED, stop=UNOBSERVED)
    values[{"response": "first", "continuation": "shift", "closure": "stop"}[c["dimension"]]] = c[
        "behavior"
    ]
    return dict(
        section=c["section"],
        trigger=c["trigger"],
        **values,
        limit=c["exclusion"],
        evidence=refs,
        rule=c["function"] + "의 " + c["dimension"],
    )


def validate_atoms(out, payload):
    if (
        not isinstance(out, dict)
        or set(out) != {"atoms"}
        or not isinstance(out["atoms"], list)
        or len(out["atoms"]) > 12
    ):
        raise ValueError("원자 주장 형식 또는 개수 오류")
    allowed = set(payload["allowedIds"])
    echoed = set()
    for c in out["atoms"]:
        if isinstance(c, dict) and set(c) == FIELDS | {"id"}:
            known = {a["id"] for a in payload.get("claims", [])}
            if not isinstance(c["id"], str) or c["id"] not in known or c["id"] in echoed:
                raise ValueError("알 수 없거나 중복된 원자 식별자")
            echoed.add(c.pop("id"))
        if not isinstance(c, dict) or set(c) != FIELDS:
            raise ValueError("원자 주장 필드가 다르다")
        if c["section"] not in SECTIONS[1:] or c["dimension"] not in {
            "response",
            "continuation",
            "closure",
        }:
            raise ValueError("원자 주장 기능/차례가 다르다")
        for k in FIELDS - {"evidence"}:
            _text(c[k], k)
        refs = c["evidence"]
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(r, str) for r in refs)
            or len(set(refs)) != len(refs)
            or not set(refs) <= allowed
        ):
            raise ValueError("원자 주장이 입력 밖의 원문을 참조했다")
    return out["atoms"]


def validate_audit(out, claims, chunk):
    if (
        not isinstance(out, dict)
        or set(out) != {"findings"}
        or not isinstance(out["findings"], list)
    ):
        raise ValueError("원자 검증 응답 형식 오류")
    expected = {c["id"] for c in claims}
    seen = set()
    for f in out["findings"]:
        if (
            not isinstance(f, dict)
            or set(f) != {"atomId", "items", "note"}
            or not isinstance(f["atomId"], str)
            or f["atomId"] not in expected
            or f["atomId"] in seen
        ):
            raise ValueError("원자 검증 주장이 누락되거나 중복됐다")
        seen.add(f["atomId"])
        refs = set()
        if (
            not isinstance(f["items"], list)
            or not isinstance(f["note"], str)
            or not f["note"].strip()
        ):
            raise ValueError("원자 검증 사유가 없다")
        for item in f["items"]:
            if not isinstance(item, dict) or set(item) != {
                "recordId",
                "applicable",
                "behavior",
                "triggerReason",
                "behaviorReason",
            }:
                raise ValueError("원자 검증 근거 형식 오류")
            rid = item["recordId"]
            if not isinstance(rid, str) or rid in refs or rid not in chunk["recordIds"]:
                raise ValueError("입력 밖 또는 중복 원자 근거")
            refs.add(rid)
            if item["applicable"] not in {"yes", "no", "unclear"} or item["behavior"] not in {
                "support",
                "counter",
                "unclear",
            }:
                raise ValueError("원자 검증 판정 오류")
            if any(
                not isinstance(item[k], str) or not item[k].strip()
                for k in ("triggerReason", "behaviorReason")
            ):
                raise ValueError("조건과 행동의 별도 해석이 필요하다")
    if seen != expected:
        raise ValueError("전체 원자 주장의 대조가 누락됐다")
    return out["findings"]


def aggregate(audits, claims, records):
    by_id = {r["id"]: r for r in records}
    result = {}
    for c in claims:
        groups = {k: set() for k in ("support", "counter", "unclear", "outside")}
        for row in audits:
            for f in row["findings"]:
                if f["atomId"] != c["id"]:
                    continue
                for item in f["items"]:
                    rid = item["recordId"]
                    r = by_id[rid]
                    kind = (
                        "outside"
                        if item["applicable"] == "no"
                        else "unclear"
                        if item["applicable"] == "unclear"
                        else item["behavior"]
                    )
                    # A later response cannot be observed without the intervening friend turn.
                    if kind in ("support", "counter") and (
                        not r["context"]
                        or (
                            c["dimension"] == "continuation"
                            and (r["next"] is None or r["followup"] is None)
                        )
                    ):
                        kind = "unclear"
                    groups[kind].add(rid)
        groups["unclear"] |= groups["outside"] & (groups["support"] | groups["counter"])
        groups["support"] -= groups["counter"] | groups["unclear"]
        result[c["id"]] = {k: sorted(v) for k, v in groups.items()}
        result[c["id"]]["supportUnits"] = len({tuple(by_id[r]["unit"]) for r in groups["support"]})
    return result


def preserve_counters(initial, initial_stats, revised, revised_stats, records):
    """Wording edits cannot erase observed counterevidence at unchanged scope."""
    by_id = {r["id"]: r for r in records}
    scope = ("dimension", "trigger", "exclusion")
    for c in revised:
        carried = set()
        for old in initial:
            if all(c[k] == old[k] for k in scope):
                carried.update(initial_stats[old["id"]]["counter"])
        stats = revised_stats[c["id"]]
        stats["carriedCounterIds"] = sorted(carried)
        stats["counter"] = sorted(set(stats["counter"]) | carried)
        stats["support"] = sorted(set(stats["support"]) - carried)
        stats["supportUnits"] = len({tuple(by_id[r]["unit"]) for r in stats["support"]})


def eligible(dev, confirm):
    return (
        dev["supportUnits"] >= 2
        and confirm["supportUnits"] >= 1
        and not dev["counter"]
        and not confirm["counter"]
    )


def _validate(phase, out, payload):
    if phase in {"atomic-discover", "atomic-consolidate", "atomic-refine"}:
        validate_atoms(out, payload)
    else:
        validate_audit(out, payload["claims"], payload["chunk"])


def call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    return _call(
        ctx, cid, folder, budget, phase, key, payload, version=VERSION, validator=_validate
    )


def build_atomic(ctx, cid, packet, source, binding, folder, budget, rework=None):
    if not source.get("coverage", {}).get("complete"):
        raise ValueError("전체 원문 범위가 미완료다")
    dev, confirm, split = partition(source)
    if budget is not None:
        from character_factory_poc.common.budget import CallPlan

        phases = [
            (phase, ch["id"])
            for phase in ("atomic-discover", "atomic-audit", "atomic-reaudit")
            for ch in dev
        ]
        phases += [("atomic-confirm", ch["id"]) for ch in confirm]
        phases += [("atomic-consolidate", "all"), ("atomic-refine", "all")]
        remaining = sum(
            not (folder / "analysis" / f"{phase}-{key}.json").exists() for phase, key in phases
        )
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import (
            atomic_retry_remaining,
        )

        remaining += atomic_retry_remaining(folder) if remaining else 0
        budget.check_plan([CallPlan("s8", "원자 특징 공정의 남은 호출 최대치", remaining, None)])
    workers = ctx.config.stage("s8").get("evidence_workers", 2)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("evidence_workers는 1~4다")
    records = source["records"]
    by_id = {r["id"]: r for r in records}
    all_speech = [
        t["text"] for ch in source["chunks"] for seg in ch["segments"] for t in seg["turns"]
    ]
    common = {k: packet[k] for k in ("role", "scene", "facts")}
    if rework:
        common["editorRevision"] = rework
    for name, value in [
        ("coverage", source["coverage"]),
        ("chunks", source["chunks"]),
        ("binding", binding),
        ("partition", split),
    ]:
        write_once_json(folder / f"evidence-{name}.json", value)

    def extract(chunk):
        out, model = call(
            ctx,
            cid,
            folder,
            budget,
            "atomic-discover",
            chunk["id"],
            dict(**common, chunk=chunk, allowedIds=chunk["recordIds"]),
        )
        return dict(chunkId=chunk["id"], atoms=out["atoms"], model=model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        observations = list(pool.map(extract, dev))
    write_once_json(folder / "evidence-observations.json", observations)
    dev_ids = [r for ch in dev for r in ch["recordIds"]]
    out, model = call(
        ctx,
        cid,
        folder,
        budget,
        "atomic-consolidate",
        "all",
        dict(**common, observations=observations, allowedIds=sorted(set(dev_ids))),
    )
    claims = [dict(c, id=f"atom-{i:02d}") for i, c in enumerate(out["atoms"], 1)]
    write_once_json(folder / "evidence-initial-atoms.json", claims)

    def audit(chunks, claims, phase):
        if not claims:
            return []

        def one(chunk):
            out, model = call(
                ctx,
                cid,
                folder,
                budget,
                phase,
                chunk["id"],
                dict(**common, chunk=chunk, claims=claims),
            )
            return dict(chunkId=chunk["id"], findings=out["findings"], model=model)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, chunks))

    first_audits = audit(dev, claims, "atomic-audit")
    first_stats = aggregate(first_audits, claims, records)
    initial_claims = claims
    write_once_json(folder / "evidence-initial-audits.json", first_audits)
    # A single bounded narrowing round uses development data only. Every revised
    # atom is then re-audited against ALL development chunks, not just its examples.
    if any(s["counter"] or s["supportUnits"] < 2 for s in first_stats.values()):
        refs = set()
        for stats in first_stats.values():
            for kind in ("counter", "unclear", "support"):
                # Keep all counters; deterministically cap only supplementary evidence.
                refs.update(stats[kind] if kind == "counter" else stats[kind][:12])
        out, model = call(
            ctx,
            cid,
            folder,
            budget,
            "atomic-refine",
            "all",
            dict(
                **common,
                claims=claims,
                assessment=first_stats,
                records=[by_id[r] for r in sorted(refs)],
                allowedIds=sorted(refs),
            ),
        )
        claims = [dict(c, id=f"atom-{i:02d}") for i, c in enumerate(out["atoms"], 1)]
        dev_audits = audit(dev, claims, "atomic-reaudit")
    else:
        dev_audits = first_audits
    dev_stats = aggregate(dev_audits, claims, records)
    preserve_counters(initial_claims, first_stats, claims, dev_stats, records)
    write_once_json(folder / "evidence-locked-atoms.json", claims)
    write_once_json(folder / "evidence-development-audits.json", dev_audits)
    # No further writing/refining call occurs after opening confirmation text.
    confirm_audits = audit(confirm, claims, "atomic-confirm")
    confirm_stats = aggregate(confirm_audits, claims, records)
    write_once_json(folder / "evidence-confirmation-audits.json", confirm_audits)
    accepted = []
    held = []
    decisions = []
    for c in claims:
        d, v = dev_stats[c["id"]], confirm_stats[c["id"]]
        decision = dict(atom=c, development=d, confirmation=v, eligible=eligible(d, v))
        refs = sorted(set(d["support"]) | set(v["support"]))
        try:
            if not decision["eligible"]:
                raise ValueError("독립 대화 지지 부족 또는 적용 범위 안 반례")
            card = to_card(c, refs)
            validate_card(card, records, extra_speech=all_speech)
            compile_prompt(packet | {"sections": [card]})
        except (ValueError, KeyError, TypeError) as exc:
            held.append(dict(decision, reason=str(exc)))
        else:
            accepted.append(card)
        decisions.append(decision)
    write_once_json(folder / "evidence-atomic-decisions.json", decisions)
    files = list((folder / "analysis").glob("*.json")) + list(folder.glob("evidence-*.json"))
    files += list((folder / "analysis" / "receipts").glob("*.json"))
    # Do not include a previous terminal HELD review in its own checksum on resume.
    files = [p for p in files if p.name not in {"evidence-review.json", "evidence-packet.json"}]
    review = dict(
        schemaVersion="evidence-review-v3",
        status="AWAITING_HUMAN" if accepted else "HELD",
        records=records,
        cards=accepted,
        held=held,
        stats=source["stats"],
        binding=binding,
        coverage=source["coverage"],
        partition=split,
        auditCoverage=dict(
            complete=bool(claims),
            developmentChunks=len(dev),
            confirmationChunks=len(confirm),
            claims=len(claims),
            checkedPairs=(len(dev_audits) + len(confirm_audits)) * len(claims),
        ),
        responseModel=model,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    if not accepted:
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("독립 확인을 통과한 원자 특징이 없다")
    packet = packet | {"sections": accepted}
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    review["packetSha256"] = sha256_file(folder / "evidence-packet.json")
    write_once_json(folder / "evidence-review.json", review)
    return text, dict(
        compiler=VERSION,
        responseModel=model,
        status="AWAITING_HUMAN",
        evidenceReviewSha256=sha256_file(folder / "evidence-review.json"),
    )
