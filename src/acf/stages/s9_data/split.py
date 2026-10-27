"""S9 분할 (LLD §5.14·§8.8 5단계, 가이드 §10).

학습·검증·평가를 `skeletonId` 묶음째 나눈다. 같은 뼈대에서 나온 대화가 두 분할에 걸치면
검증이 학습을 그대로 본 것이 되므로, 묶음을 쪼개지 않는다. 남는 목표 차이는 사람에게
경고로 보고한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acf.common.canonical import sha256_of, sha256_text
from acf.common.store import write_once_text
from acf.contracts.dataset import ClusterCount, Conversation, DataPlan, SplitFile
from acf.stages.s9_data.plan import S9Config

SPLITS: tuple[str, ...] = ("train", "validation_base", "validation_augmented", "eval")
FILE_NAME: dict[str, str] = {
    "train": "train.jsonl",
    "validation_base": "validation-base.jsonl",
    "validation_augmented": "validation-augmented.jsonl",
    "eval": "eval.jsonl",
}


def quotas(plan: DataPlan, cfg: S9Config) -> dict[str, dict[str, int]]:
    """클러스터별 목표. 학습은 계획 값, 검증·평가는 가이드의 분리 규칙을 따른다."""
    out: dict[str, dict[str, int]] = {}
    for c in plan.clusters:
        val_base = cfg.validation_base if c.clusterId == "base" else 0
        val_aug = 0
        if (
            c.clusterId != "base"
            and c.targetConversations > 0
            and cfg.validation_augmented_share > 0
        ):
            val_aug = max(1, round(c.targetConversations * cfg.validation_augmented_share))
        out[c.clusterId] = {
            "train": c.targetConversations,
            "validation_base": val_base,
            "validation_augmented": val_aug,
            "eval": cfg.eval_per_cluster,
        }
    return out


def needed(plan: DataPlan, cfg: S9Config) -> dict[str, int]:
    return {c: sum(q.values()) for c, q in quotas(plan, cfg).items()}


@dataclass
class SplitResult:
    splits: dict[str, list[Conversation]] = field(default_factory=dict)
    files: list[SplitFile] = field(default_factory=list)
    index_rows: list[dict[str, Any]] = field(default_factory=list)
    digest: str = ""
    warnings: list[str] = field(default_factory=list)
    quotas: dict[str, dict[str, int]] = field(default_factory=dict)


def _bundle_order(cluster: str, keys: list[str]) -> list[str]:
    return sorted(keys, key=lambda k: sha256_text(f"{cluster}|{k}"))


def _take(
    result: SplitResult,
    available: list[str],
    bundles: dict[str, list[Conversation]],
    target: int,
    dest: str,
) -> None:
    """묶음째 목표 수만큼 가져간다. 목표를 넘을 수 있다(묶음은 쪼개지 않는다)."""
    taken = 0
    for key in list(available):
        if taken >= target:
            break
        result.splits[dest].extend(bundles[key])
        available.remove(key)
        taken += len(bundles[key])


def split(
    conversations: list[Conversation], plan: DataPlan, cfg: S9Config, approx: dict[str, int]
) -> SplitResult:
    result = SplitResult(splits={name: [] for name in SPLITS}, quotas=quotas(plan, cfg))
    grouped: dict[str, dict[str, list[Conversation]]] = {}
    for conv in conversations:
        grouped.setdefault(conv.clusterId, {}).setdefault(conv.skeletonId, []).append(conv)
    for cluster, bundles in grouped.items():
        q = result.quotas.get(cluster)
        if q is None:
            raise ValueError(f"계획에 없는 클러스터가 데이터에 있다: {cluster}")
        available = _bundle_order(cluster, list(bundles))

        _take(result, available, bundles, q["eval"], "eval")
        _take(result, available, bundles, q["validation_base"], "validation_base")
        _take(result, available, bundles, q["validation_augmented"], "validation_augmented")
        for key in list(available):
            result.splits["train"].extend(bundles[key])
            available.remove(key)

    for name in SPLITS:
        result.splits[name].sort(key=lambda c: c.conversationId)
    _check_leak(result.splits)
    for cluster, q in result.quotas.items():
        train = sum(1 for c in result.splits["train"] if c.clusterId == cluster)
        if q["train"] and train < q["train"] * 0.9:
            result.warnings.append(
                f"{cluster}: 학습 목표 {q['train']}대화보다 적다(실제 {train}). 뼈대 묶음 단위로 "
                "나누느라 차이가 났다"
            )
    ordered = sorted(conversations, key=lambda c: c.conversationId)
    payload = [
        {
            "conversationId": c.conversationId,
            "messages": [{"role": "system", "content": c.system}]
            + [{"role": m.role, "content": m.content} for m in c.messages],
        }
        for c in ordered
    ]
    result.digest = sha256_of(payload)
    split_of = {c.conversationId: name for name in SPLITS for c in result.splits[name]}
    result.index_rows = [
        {
            "conversationId": c.conversationId,
            "clusterId": c.clusterId,
            "material": c.material,
            "skeletonId": c.skeletonId,
            "split": split_of[c.conversationId],
            "path": f"conversations/{c.conversationId}.json",
            "replies": sum(1 for m in c.messages if m.role == "assistant"),
            "approxTokens": approx.get(c.conversationId),
        }
        for c in ordered
    ]
    return result


def _check_leak(splits: dict[str, list[Conversation]]) -> None:
    where: dict[str, str] = {}
    for name in SPLITS:
        for conv in splits[name]:
            prev = where.setdefault(conv.skeletonId, name)
            if prev != name:
                raise ValueError(f"뼈대 누출: {conv.skeletonId}가 {prev}와 {name}에 모두 있다")


def jsonl_text(conversations: list[Conversation]) -> str:
    lines = []
    for conv in conversations:
        obj = {
            "messages": [{"role": "system", "content": conv.system}]
            + [{"role": m.role, "content": m.content} for m in conv.messages]
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    return "".join(line + "\n" for line in lines)


def write_splits(rev_dir: Path, result: SplitResult) -> list[SplitFile]:
    files: list[SplitFile] = []
    for name in SPLITS:
        text = jsonl_text(result.splits[name])
        path = rev_dir / FILE_NAME[name]
        write_once_text(path, text)
        files.append(
            SplitFile(
                split=name,  # type: ignore[arg-type]
                path=FILE_NAME[name],
                sha256=sha256_text(text),
                conversations=len(result.splits[name]),
            )
        )
    write_once_text(
        rev_dir / "index.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in result.index_rows),
    )
    return files


def cluster_counts(conversations: list[Conversation]) -> dict[str, ClusterCount]:
    out: dict[str, ClusterCount] = {}
    for conv in conversations:
        cur = out.get(conv.clusterId) or ClusterCount(conversations=0, replies=0)
        out[conv.clusterId] = ClusterCount(
            conversations=cur.conversations + 1,
            replies=cur.replies + sum(1 for m in conv.messages if m.role == "assistant"),
            supervisedTokens=None,
        )
    return out
