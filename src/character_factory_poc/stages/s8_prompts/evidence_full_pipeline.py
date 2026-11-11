"""All-source observation, exhaustive candidate audit, and lossless conditions.

Model labels remain evidence for G6 review, never automatic semantic approval.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt
from character_factory_poc.stages.s8_prompts.evidence_source import validate_card

VERSION = "evidence-pipeline-v2"
ATOMIC_RETRIES = 10


def atomic_retry_remaining(folder):
    return max(
        0, ATOMIC_RETRIES - len(list((folder / "analysis" / "retry-permits").glob("*.json")))
    )


def _claim_atomic_retry(folder):
    import fcntl

    permits = folder / "analysis" / "retry-permits"
    permits.mkdir(parents=True, exist_ok=True)
    with (permits / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        count = len(list(permits.glob("*.json")))
        if count >= ATOMIC_RETRIES:
            raise ValueError("전체 원자 분석의 형식 재시도 상한을 소진했다")
        write_once_json(permits / f"{count + 1:02d}.json", dict(reason="invalid response"))


def _validate_phase(phase, out, payload):
    if phase == "audit":
        validate_findings(out, payload["claims"], payload["chunk"])
    else:
        key, maximum = ("observations", 8) if phase == "discover" else ("sections", 10)
        if (
            not isinstance(out, dict)
            or set(out) != {key}
            or not isinstance(out[key], list)
            or len(out[key]) > maximum
        ):
            raise ValueError("분석 단계의 응답 형식이 다르다")


def _call(
    ctx, cid, folder, budget, phase, key, payload, *, version=VERSION, validator=_validate_phase
):
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import instructions

    system = instructions(version)
    body = json.dumps(dict(phase=phase, **payload), ensure_ascii=False, sort_keys=True)
    digest = sha256_text(system + body)
    path = folder / "analysis" / f"{phase}-{key}.json"
    rejected = folder / "analysis" / "rejected"
    receipt = folder / "analysis" / "receipts" / f"{phase}-{key}.json"
    if path.exists():
        if receipt.exists() and read_json(receipt)["cacheSha256"] != sha256_file(path):
            raise ValueError("저장된 분석 응답의 무결성이 변경됐다")
        if (
            version in {"evidence-pipeline-v3", "evidence-pipeline-v4", "evidence-pipeline-v5"}
            and not receipt.exists()
        ):
            raise ValueError("분석 응답의 독립 무결성 기록이 없다. 새 revision이 필요하다")
        saved = read_json(path)
        if saved["requestSha256"] != digest:
            raise ValueError("저장된 분석의 원천이나 지시가 다르다")
        try:
            validator(phase, saved["output"], payload)
        except ValueError:
            rejected.mkdir(parents=True, exist_ok=True)
            suffix = len(list(rejected.glob(f"{phase}-{key}-*.json"))) + 1
            path.rename(rejected / f"{phase}-{key}-cached-{suffix}.json")
            if receipt.exists():
                receipt.rename(rejected / f"{phase}-{key}-receipt-{suffix}.json")
        else:
            return saved["output"], saved["model"]
    for validation_attempt in range(2):
        tries = folder / "analysis" / "attempts"
        attempt = len(list(tries.glob(f"{phase}-{key}-*.json"))) + 1
        write_once_json(tries / f"{phase}-{key}-{attempt}.json", dict(requestSha256=digest))
        response = ctx.text_model(cid, budget).complete(
            ChatRequest(
                kind="AGENT",
                stage="s8",
                ref=f"{cid}/{folder.name}/{phase}/{key}/attempt-{attempt}",
                max_output_tokens=10000,
                temperature=0.2,
                response_json=True,
                messages=(Message("system", system), Message("user", body)),
            )
        )
        try:
            if response.finish_reason not in (None, "stop", "STOP"):
                raise ValueError("전체 분석 응답이 중간에 끝났다")
            out = extract_json_object(response.text)
            validator(phase, out, payload)
        except ValueError as exc:
            write_once_json(
                rejected / f"{phase}-{key}-attempt-{attempt}.json",
                dict(requestSha256=digest, raw=response.text, reason=str(exc)),
            )
            if validation_attempt == 1:
                raise
            if version in {"evidence-pipeline-v3", "evidence-pipeline-v4", "evidence-pipeline-v5"}:
                _claim_atomic_retry(folder)
        else:
            write_once_json(path, dict(requestSha256=digest, output=out, model=response.model))
            write_once_json(receipt, dict(cacheSha256=sha256_file(path)))
            return out, response.model
    raise ValueError("유효한 분석 응답을 받지 못했다")


def _cards(out, key, maximum, packet, records, allowed, held=None, extra_speech=()):
    if (
        not isinstance(out, dict)
        or set(out) != {key}
        or not isinstance(out[key], list)
        or len(out[key]) > maximum
    ):
        raise ValueError("전체 분석 후보 형식이 다르다")
    valid = []
    allowed = set(allowed)
    local_records = [r for r in records if r["id"] in allowed]
    for index, card in enumerate(out[key]):
        try:
            compile_prompt(packet | {"sections": [card]})
            if not set(card["evidence"]) <= allowed:
                raise ValueError("후보가 입력 범위 밖 원문을 인용했다")
            validate_card(card, local_records, min_units=1, extra_speech=extra_speech)
        except (ValueError, TypeError, KeyError) as exc:
            if held is None:
                raise
            held.append(dict(index=index, reason=str(exc)))
        else:
            valid.append(card)
    return valid


def validate_findings(out, claims, chunk):
    if (
        not isinstance(out, dict)
        or set(out) != {"findings"}
        or not isinstance(out["findings"], list)
    ):
        raise ValueError("근거 대조 형식이 다르다")
    expected = {c["id"] for c in claims}
    seen = set()
    for f in out["findings"]:
        if not isinstance(f, dict) or set(f) != {
            "claimId",
            "support",
            "counter",
            "unclear",
            "note",
        }:
            raise ValueError("근거 대조 항목 형식이 다르다")
        if (
            not isinstance(f["claimId"], str)
            or f["claimId"] not in expected
            or f["claimId"] in seen
        ):
            raise ValueError("중복되거나 알 수 없는 특징 대조다")
        seen.add(f["claimId"])
        refs = set()
        for kind in ("support", "counter", "unclear"):
            ids = f[kind]
            if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
                raise ValueError("근거 ID 목록 형식이 다르다")
            if (
                len(ids) != len(set(ids))
                or refs & set(ids)
                or not set(ids) <= set(chunk["recordIds"])
            ):
                raise ValueError("다른 구간 또는 중복 분류된 근거다")
            refs.update(ids)
        if not isinstance(f["note"], str) or not f["note"].strip():
            raise ValueError("근거 해석이 없다")
    if seen != expected:
        raise ValueError("전체 특징의 지지·반례 대조가 누락됐다")
    return out["findings"]


def verify_analysis_files(folder, review):
    if review.get("schemaVersion") not in {
        "evidence-review-v2",
        "evidence-review-v3",
        "evidence-review-v4",
        "evidence-review-v5",
    }:
        return
    if not review.get("coverage", {}).get("complete") or not review.get("auditCoverage", {}).get(
        "complete"
    ):
        raise ValueError("전체 원문 분석이나 대조가 미완료다")
    artifacts = review.get("analysisArtifacts", {})
    if not artifacts:
        raise ValueError("전체 분석 기록이 없다")
    for ref, digest in artifacts.items():
        path = (Path(folder) / ref).resolve()
        if not path.is_relative_to(Path(folder).resolve()) or sha256_file(path) != digest:
            raise ValueError("전체 원문 분석 기록이 변경됐다")


def build_full(ctx, cid, packet, source, binding, folder, budget, rework=None):
    folder = Path(folder)
    if not source.get("coverage", {}).get("complete") or not source["chunks"]:
        raise ValueError("전체 생성용 원문 분석 범위가 누락됐다")
    workers = ctx.config.stage("s8").get("evidence_workers", 2)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("evidence_workers는 1~4 정수여야 한다")
    if budget is not None:
        from character_factory_poc.common.budget import CallPlan

        phases = [
            (phase, chunk["id"]) for phase in ("discover", "audit") for chunk in source["chunks"]
        ]
        phases.append(("consolidate", "all"))
        remaining = sum(
            not (folder / "analysis" / f"{phase}-{key}.json").exists() for phase, key in phases
        )
        budget.check_plan([CallPlan("s8", "전체 원문 관찰·특징별 전수 대조", remaining, None)])
    common = {k: packet[k] for k in ("role", "scene", "facts")}
    if rework:
        common["editorRevision"] = rework
    write_once_json(folder / "evidence-coverage.json", source["coverage"])
    write_once_json(folder / "evidence-chunks.json", source["chunks"])
    write_once_json(folder / "evidence-binding.json", binding)
    chunks, records = source["chunks"], source["records"]
    all_speech = [
        t["text"] for ch in chunks for segment in ch["segments"] for t in segment["turns"]
    ]

    def discover(chunk):
        out, model = _call(
            ctx, cid, folder, budget, "discover", chunk["id"], dict(**common, chunk=chunk)
        )
        held = []
        cards = _cards(
            out,
            "observations",
            8,
            packet,
            records,
            chunk["recordIds"],
            held,
            [t["text"] for segment in chunk["segments"] for t in segment["turns"]],
        )
        return dict(chunkId=chunk["id"], observations=cards, held=held, model=model)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        observations = list(pool.map(discover, chunks))
    write_once_json(folder / "evidence-observations.json", observations)
    out, model = _call(
        ctx, cid, folder, budget, "consolidate", "all", dict(**common, observations=observations)
    )
    cited = {
        ref for row in observations for card in row["observations"] for ref in card["evidence"]
    }
    consolidation_held = []
    cards = _cards(out, "sections", 10, packet, records, cited, consolidation_held, all_speech)
    claims = [dict(id=f"claim-{n:02d}", card=c) for n, c in enumerate(cards, 1)]
    write_once_json(
        folder / "evidence-candidates.json",
        dict(
            output=out,
            responseModel=model,
            bindingSha256=sha256_file(folder / "evidence-binding.json"),
        ),
    )

    def audit(chunk):
        out, audit_model = _call(
            ctx,
            cid,
            folder,
            budget,
            "audit",
            chunk["id"],
            dict(**common, chunk=chunk, claims=claims),
        )
        return dict(
            chunkId=chunk["id"], findings=validate_findings(out, claims, chunk), model=audit_model
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        audited = list(pool.map(audit, chunks)) if claims else []
    write_once_json(folder / "evidence-audits.json", audited)
    accepted, held, decisions = [], list(consolidation_held), []
    for n, claim in enumerate(claims):
        groups = {k: set() for k in ("support", "counter", "unclear")}
        for row in audited:
            f = next(f for f in row["findings"] if f["claimId"] == claim["id"])
            for k in groups:
                groups[k].update(f[k])
        # Overlap context can yield conflicting classifications; never hide the conflict.
        ambiguous = groups["support"] & groups["unclear"]
        support = groups["support"] - groups["counter"] - ambiguous
        decision = dict(index=n, claimId=claim["id"], **{k: sorted(v) for k, v in groups.items()})
        candidate = dict(claim["card"], evidence=sorted(support))
        try:
            if groups["counter"]:
                raise ValueError("적용 범위 안의 반례가 남아 있다")
            validate_card(candidate, records, extra_speech=all_speech)
            compile_prompt(packet | {"sections": [candidate]})
        except (ValueError, TypeError, KeyError) as exc:
            held.append(dict(decision, reason=str(exc)))
        else:
            accepted.append(candidate)
        decisions.append(decision)
    audit_coverage = dict(
        complete=bool(claims) and len(audited) == len(chunks),
        chunks=len(chunks),
        claims=len(claims),
        checkedPairs=len(audited) * len(claims),
    )
    write_once_json(folder / "evidence-decisions.json", decisions)
    files = list((folder / "analysis").glob("*.json"))
    files += [
        folder / n
        for n in (
            "evidence-coverage.json",
            "evidence-chunks.json",
            "evidence-observations.json",
            "evidence-audits.json",
            "evidence-decisions.json",
            "evidence-candidates.json",
        )
    ]
    review = dict(
        schemaVersion="evidence-review-v2",
        status="AWAITING_HUMAN" if accepted else "HELD",
        records=records,
        cards=accepted,
        held=held,
        stats=source["stats"],
        binding=binding,
        coverage=source["coverage"],
        auditCoverage=audit_coverage,
        responseModel=model,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    if not accepted:
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("전체 원문 대조를 통과한 근거 후보가 없다")
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
