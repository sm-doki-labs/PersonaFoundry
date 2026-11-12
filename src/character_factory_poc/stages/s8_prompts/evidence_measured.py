"""evidence-v6: the v4 tendency pipeline with measured voice and evidence-based retention.

Differences from v4 (D-0196): consolidation keeps every distinct supported tendency instead
of a fixed twelve, a claim needs at least three independent confirmation supports, the
VOICE section opens with counted speech distributions, and unconfirmed continuation or
closing slots are not rendered. v4 artifacts stay byte-for-byte verifiable.
"""

from __future__ import annotations

import re

from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
    aggregate,
    to_card,
    validate_transport,
)

VERSION = "evidence-pipeline-v6"
MIN_CONFIRMATION_SUPPORT = 3
AUDIT_BATCH = 12
# A quoted grammatical form (for example a hedging construction) is described by at most
# this many retained cards; extra cards only multiply the same instruction in the prompt.
MAX_CARDS_PER_FORM = 1
_FORM = re.compile(r"['‘’\"“”](-[^'‘’\"“”]+)['‘’\"“”]")
# Adnominal allomorphs of one construction count as the same form ('-ㄴ/-은/-는 것 같다').
_ADNOMINAL = re.compile(r"^-(?:ㄴ|ㄹ|은|는|던|을)\s+")
# Forms whose measured share depends on answer length (see VOICE "단정 완화"). A card that
# describes one only applies once the answer is already long enough to carry it.
LENGTH_SCOPED_FORMS = {"-N 것 같다": "두세 문장 이상으로 이유나 판단을 풀어 말하는 답일 때만"}
LENGTH_SCOPED_LIMIT = "한두 마디로 끝나는 짧은 답, 사실 확인 답, 인사·수락 답"

__all__ = ["VERSION", "MIN_CONFIRMATION_SUPPORT", "aggregate", "to_card", "call"]


def call(ctx, cid, folder, budget, phase, key, payload):
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import _call

    return _call(
        ctx, cid, folder, budget, phase, key, payload, version=VERSION, validator=validate_transport
    )


def check_eligibility(claim):
    return None


def card_forms(card):
    """Quoted grammatical forms a card describes, normalised ('-어요/-아요' -> two forms)."""
    text = " ".join(str(card.get(k, "")) for k in ("first", "shift", "stop"))
    forms = set()
    for raw in _FORM.findall(text):
        for part in raw.split("/"):
            part = " ".join(part.strip().split())
            if part:
                part = part if part.startswith("-") else "-" + part
                forms.add(_ADNOMINAL.sub("-N ", part))
    return forms


def dedupe_forms(cards):
    """Keep the best-supported card per grammatical form; return (kept, dropped).

    Cards are ranked by evidence count (ties keep source order). A card is dropped when any
    form it describes is already covered by MAX_CARDS_PER_FORM kept cards. Cards without a
    quoted form are never dropped by this rule.
    """
    order = sorted(range(len(cards)), key=lambda i: (-len(cards[i].get("evidence", [])), i))
    used: dict[str, int] = {}
    keep, dropped = set(), []
    for i in order:
        forms = card_forms(cards[i])
        taken = sorted(f for f in forms if used.get(f, 0) >= MAX_CARDS_PER_FORM)
        if taken:
            dropped.append((cards[i], taken))
            continue
        keep.add(i)
        for f in forms:
            used[f] = used.get(f, 0) + 1
    return [c for i, c in enumerate(cards) if i in keep], dropped


def scope_cards(cards):
    """Narrow cards that describe a length-conditioned form to long answers; return (cards, n)."""
    out, scoped = [], 0
    for card in cards:
        conditions = [
            LENGTH_SCOPED_FORMS[f] for f in sorted(card_forms(card)) if f in LENGTH_SCOPED_FORMS
        ]
        if not conditions:
            out.append(card)
            continue
        scoped += 1
        trigger = card["trigger"].rstrip(" .") + ", 그중 " + conditions[0]
        limit = card.get("limit", "").rstrip(" .")
        limit = LENGTH_SCOPED_LIMIT if not limit else LENGTH_SCOPED_LIMIT + ", " + limit
        out.append(card | {"trigger": trigger, "limit": limit})
    return out, scoped


def merge_observations(observations):
    """Merge only identical (section, function, level, dimension) observations; keep the rest.

    The representative wording comes from the observation with the most evidence; evidence
    from merged observations is unioned in first-seen order. No target count is applied.
    """
    groups: dict[tuple, list[dict]] = {}
    for o in observations:
        for c in o["claims"]:
            key = (
                c["section"],
                " ".join(c["function"].split()),
                c["linguisticLevel"],
                c["dimension"],
            )
            groups.setdefault(key, []).append(dict(c, _chunk=o["chunkId"]))
    merged, log = [], []
    for key, items in groups.items():
        rep = max(items, key=lambda c: len(c["evidence"]))
        evidence = list(dict.fromkeys(e for c in items for e in c["evidence"]))
        merged.append({k: v for k, v in rep.items() if k != "_chunk"} | {"evidence": evidence})
        log.append(
            dict(
                section=key[0],
                function=key[1],
                linguisticLevel=key[2],
                dimension=key[3],
                mergedFrom=[c["_chunk"] for c in items],
            )
        )
    return merged, dict(
        rule="identical section/function/linguisticLevel/dimension only",
        discovered=sum(len(o["claims"]) for o in observations),
        kept=len(merged),
        groups=log,
    )


def review_fields(decisions):
    kept = [d for d in decisions if d.get("state") != "insufficient"]
    return {
        "retentionRule": dict(
            minConfirmationSupport=MIN_CONFIRMATION_SUPPORT,
            minDevelopmentSupport=2,
            fixedCount=None,
            candidates=len(decisions),
            supported=len(kept),
            maxCardsPerForm=MAX_CARDS_PER_FORM,
            formDuplicatesHeld=sum(1 for d in decisions if d.get("duplicateForms")),
            retained=sum(1 for d in decisions if d.get("retained")),
        )
    }
