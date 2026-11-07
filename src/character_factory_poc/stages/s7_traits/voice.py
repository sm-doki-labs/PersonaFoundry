"""Verify trusted human approval evidence before supplying style-only examples."""

import re
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.voice import VoiceBinding, VoicePack
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.formation import field_text

# Process-local proof cache only: raw VoicePack objects cannot assert verification.
# Every bind rechecks the files; the cache supplies locations, not authorization.
_VERIFIED: dict[str, tuple[Path, Path, str, str]] = {}


def _within(root, name):
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError(f"voice source/approval missing or outside root: {name}")
    return p


def load_voice_pack(path: Path, *, approval_index: Path) -> VoicePack:
    path, approval_index = Path(path).resolve(), Path(approval_index).resolve()
    pack = VoicePack.model_validate(read_json(path))
    pack.check_split()
    record_path = _within(path.parent, pack.approvalFile)
    if sha256_file(record_path) != pack.approvalSha256:
        raise ValueError("voice approval hash mismatch")
    index = read_json(approval_index)
    trusted = index.get("approvals", {})
    # Registry paths are relative to the registry, not controlled by a generated pack.
    approved = any(
        (approval_index.parent / name).resolve() == record_path and digest == pack.approvalSha256
        for name, digest in trusted.items()
    )
    if not approved:
        raise ValueError("voice approval is not in the trusted registry")
    record = read_json(record_path)
    content = dump(pack)
    content.pop("approvalFile")
    content.pop("approvalSha256")
    if (
        record.get("assetSha256") != body_hash(content)
        or record.get("reviewer") != "user"
        or record.get("decision") != "APPROVE"
        or record.get("scope") != "voice-pack"
    ):
        raise ValueError("voice approval does not cover this asset")
    covered = set(record.get("sourceGroupIds", []))
    if not {e.sourceGroupId for e in [*pack.examples, *pack.validationExamples]} <= covered:
        raise ValueError("voice approval lacks source groups")
    for example in [*pack.examples, *pack.validationExamples]:
        if example.material == "model-draft":
            raise ValueError("model draft is not an actual approved voice source")
        source = _within(path.parent, example.sourceFile)
        if sha256_file(source) != example.sourceSha256:
            raise ValueError("voice source hash mismatch")
        raw = read_json(source) if source.suffix == ".json" else source.read_text("utf-8")
        if field_text(raw, example.fieldPath) != example.sourceQuote:
            raise ValueError("voice source quote mismatch")
    _VERIFIED[body_hash(dump(pack))] = (
        path,
        approval_index,
        sha256_file(path),
        sha256_file(approval_index),
    )
    return pack


def resolved_voice_sources(pack):
    proof = _VERIFIED.get(body_hash(dump(pack)))
    if proof is None:
        raise ValueError("voice source audit requires a verified pack")
    path, index, _, _ = proof
    fresh = load_voice_pack(path, approval_index=index)
    if fresh != pack:
        raise ValueError("voice source changed before audit")
    return [
        (example, _within(path.parent, example.sourceFile), split)
        for examples, split in (
            (pack.examples, "injection"),
            (pack.validationExamples, "voice-validation"),
        )
        for example in examples
    ]


def bind_voice(plan, packs: list[VoicePack], policy) -> VoiceBinding:
    raw = dump(plan) if hasattr(plan, "model_dump") else plan
    cid = raw["characterId"]
    base = dict(characterId=cid, planSha256=body_hash(raw), policySha256=body_hash(policy))
    summary = raw.get("voiceSummary", "")
    target = policy.get("targets", {}).get(cid)
    negative = bool(re.search(r"쓰지|사용하지|아니|않|금지|말고|절대|\b안\s", summary))
    constrained = isinstance(target, dict) and any(
        target.get(k) for k in ("requiredTags", "forbiddenTags")
    )
    if constrained:
        constrained = all(
            isinstance(target.get(k, []), list)
            and all(isinstance(t, str) and bool(t.strip()) for t in target.get(k, []))
            for k in ("requiredTags", "forbiddenTags", "positiveTags")
        )
    if negative and not constrained:
        return VoiceBinding(
            **base,
            status="VOICE_SOURCE_MISSING",
            reason="부정·예외가 있는 말투 목표는 구조화한 targets가 필요하다",
        )
    target = target or {}
    required = set(target.get("requiredTags", []))
    forbidden = set(target.get("forbiddenTags", []))
    if not negative:
        required.update(tag for tag in ("반말", "존댓말") if tag in summary)
    positive = set(target.get("positiveTags", [])) | required
    if not negative:
        positive.update(re.findall(r"[가-힣A-Za-z0-9_-]+", summary))
    selected = policy.get("assignments", {}).get(cid)
    reason = "명시한 캐릭터별 배정"
    if selected is None:
        for rule in policy.get("rules", []):
            if rule.get("requires") and set(rule["requires"]) <= positive:
                selected = rule["packId"]
                reason = "말투 목표 조건과 일치"
                break
    if selected is None:
        selected = policy.get("defaultPackId")
        reason = "명시한 공통 기본 팩"
    matches = [p for p in packs if p.packId == selected]
    if len(matches) != 1:
        return VoiceBinding(
            **base, status="VOICE_SOURCE_MISSING", reason="적합한 승인 말투 팩이 없다"
        )
    pack = matches[0]
    if (
        not required <= set(pack.tags)
        or forbidden & set(pack.tags)
        or set(pack.doNotUseWhen) & {"text", "문자", "문자 대화"}
    ):
        return VoiceBinding(
            **base,
            status="VOICE_SOURCE_MISSING",
            reason="말투 팩이 목표의 필수·금지 조건과 충돌한다",
        )
    verification = _VERIFIED.get(body_hash(dump(pack)))
    if verification is None:
        raise ValueError("voice pack must be verified through load_voice_pack")
    path, index, digest, index_digest = verification
    if sha256_file(path) != digest or sha256_file(index) != index_digest:
        raise ValueError("voice pack/approval registry changed after loading")
    load_voice_pack(path, approval_index=index)
    return VoiceBinding(
        **base,
        status="READY",
        packId=pack.packId,
        packPath=str(path),
        packSha256=digest,
        approvalIndexPath=str(index),
        approvalIndexSha256=index_digest,
        rules=pack.rules,
        doNotUseWhen=pack.doNotUseWhen,
        tags=pack.tags,
        examples=[
            dict(
                id=e.id,
                situation=e.situation,
                relationship=e.relationship,
                emotion=e.emotion,
                styleView=e.styleView,
                sourceGroupId=e.sourceGroupId,
            )
            for e in pack.examples
        ],
        reason=reason,
    )


def verify_voice_binding(binding: VoiceBinding, plan, policy) -> VoicePack:
    if binding.status != "READY" or not binding.packPath or not binding.approvalIndexPath:
        raise ValueError("VOICE_SOURCE_MISSING")
    pack = load_voice_pack(Path(binding.packPath), approval_index=Path(binding.approvalIndexPath))
    fresh = bind_voice(plan, [pack], policy)
    if fresh != binding:
        raise ValueError("voice binding differs from current approved inputs")
    return pack
