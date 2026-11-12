"""Bounded, generation-only scene evidence for the motif S3 planner."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict, deque
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import get_args

from character_factory_poc.common.budget import Budget, CallPlan, RunBudget
from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.source import ChapterTemplate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.stages.s8_prompts.evidence_compiler import _text
from character_factory_poc.stages.s8_prompts.evidence_source import _COPY_SPAN, _UNSAFE

DIMENSIONS = ("voice", "behavior", "facts-limits")
SCHEMA = "s3-scene-analysis-v1"
_MAX_PAIRS = 48
_MAX_ROW_CHARS = 1200
_MAX_PAYLOAD_BYTES = 28_000
_MAX_OUTPUT_TOKENS = 2000
_MAX_RESPONSE_BYTES = 16_000
_MAX_OBSERVATIONS = 8
_MAX_REFS = 4
# Whole-source mode: each analyzer reads every eligible turn once; split only past this size.
_FULL_MAX_CHARS = 700_000
_FULL_LIMITS = dict(observations=16, refs=8, output_tokens=32_000, response_bytes=120_000)
_SAMPLE_LIMITS = dict(observations=8, refs=4, output_tokens=2000, response_bytes=16_000)
_MAX_DESCRIPTION_CHARS = 260

_FENCE = re.compile(r"\s*```(?:json)?\s*(.*?)\s*```\s*", re.S)
_ID = re.compile(r"[A-Za-z0-9_-]{1,160}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_MARKUP = re.compile(r"<\s*/?\s*[A-Za-z!][^>]*>")
_FREQUENCY = re.compile(
    r"(?:전체|전수|대부분의)\s*(?:자료|원문|표본|대화|발화|응답|답변|문답|말뭉치)"
    r"|(?:대화|발화|응답|답변)(?:의|\s*중)?\s*(?:약\s*)?\d+(?:\.\d+)?\s*(?:%|퍼센트)"
    r"|\d+(?:\.\d+)?\s*(?:%|퍼센트)\s*(?:의\s*)?(?:대화|발화|응답|답변)"
    r"|\d+(?:\.\d+)?\s*%\s+of (?:the )?(?:replies|answers|conversations)"
    r"|(?:매번|항상|늘)\s|\b(?:corpus[- ]wide|always|every time|all (?:conversations|answers))\b"
    r"|\b(?:across|throughout)\s+(?:the\s+)?(?:entire\s+)?corpus\b",
    re.IGNORECASE,
)


def _json(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _unit(row: dict) -> tuple[str, str]:
    return row["textId"], row["convId"]


def _row_view(row: dict, flagged: set[str]) -> dict | None:
    text = row.get("text")
    if (
        row["msgId"] in flagged
        or row.get("speaker") not in ("USER", "SUBJECT")
        or not isinstance(text, str)
        or not text.strip()
        or len(text) > _MAX_ROW_CHARS
        or _CONTROL.search(text)
    ):
        return None
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if _UNSAFE.search(unicodedata.normalize("NFKC", text)):
        return None
    # Preserve the real text; a discarded row is a boundary rather than an edited utterance.
    return {k: row[k] for k in ("msgId", "speaker", "text")}


def _candidate_groups(corpus: list[dict], flagged: set[str]) -> dict:
    ids, blocked = set(), set()
    for i, row in enumerate(corpus):
        if not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) or not _ID.fullmatch(row[key])
            for key in ("textId", "convId", "msgId")
        ):
            raise ValueError(f"S3 scene-analysis corpus row {i}: invalid identity")
        if row["msgId"] in ids:
            raise ValueError(f"S3 scene-analysis corpus row {i}: duplicate message ID")
        ids.add(row["msgId"])
        # Normal S0 generation rows have no split marker. Never open the separate holdout file.
        if row.get("split", "generation") not in ("generation", "train"):
            blocked.add(_unit(row))

    sources = defaultdict(lambda: defaultdict(list))
    prev_unit, prior = None, None
    for row in corpus:
        unit = _unit(row)
        current = None if unit in blocked else _row_view(row, flagged)
        if (
            current is not None
            and current["speaker"] == "SUBJECT"
            and unit == prev_unit
            and prior is not None
            and prior["speaker"] == "USER"
        ):
            sources[unit[0]][unit[1]].append(
                {"textId": unit[0], "convId": unit[1], "prior": prior, "subject": current}
            )
        prev_unit, prior = unit, current
    return sources


def _balanced_pairs(groups: dict, scene: ChapterTemplate | None) -> list[dict]:
    # Rotate both levels so a long recording or chat cannot dominate by its size.
    sources = deque(
        deque(
            deque(sorted(pairs, key=lambda p: sha256_text(p["subject"]["msgId"])))
            for _, pairs in sorted(scenes.items(), key=lambda item: sha256_text(item[0]))
        )
        for _, scenes in sorted(groups.items())
    )
    selected = []
    # Reserve envelope bytes for the longest dimension name and each pair's separator.
    remaining = _MAX_PAYLOAD_BYTES - len(
        _json({"dimension": max(DIMENSIONS, key=len), "scene": scene, "pairs": []}).encode("utf-8")
    )
    while sources and len(selected) < _MAX_PAIRS:
        source = sources.popleft()
        candidates = source.popleft()
        pair = candidates.popleft()
        if candidates:
            source.append(candidates)
        if source:
            sources.append(source)
        size = len(_json(pair).encode("utf-8")) + 1
        if size <= remaining:
            selected.append(pair)
            remaining -= size
    return selected


def _full_segments(corpus: list[dict], flagged: set[str]) -> list[dict]:
    """Every eligible generation turn in source order; excluded rows become boundaries."""
    _candidate_groups(corpus, flagged)  # Validates identities and held markers.
    blocked = {
        _unit(row)
        for row in corpus
        if row.get("split", "generation") not in ("generation", "train")
    }
    segments, current, prev_unit = [], None, None
    for row in corpus:
        unit = _unit(row)
        view = None if unit in blocked else _row_view(row, flagged)
        if view is None or unit != prev_unit:
            if current and current["turns"]:
                segments.append(current)
            current = None
        if view is not None:
            if current is None:
                current = {"textId": unit[0], "convId": unit[1], "turns": []}
            current["turns"].append(view)
        prev_unit = unit
    if current and current["turns"]:
        segments.append(current)
    return segments


def _render_lines(segments: list[dict]) -> str:
    """Compact source view: one turn per line, so long chats cost far fewer tokens than JSON."""
    out = []
    for segment in segments:
        out.append(f"## {segment['textId']} {segment['convId']}")
        for turn in segment["turns"]:
            text = " ⏎ ".join(turn["text"].replace("\t", " ").splitlines())
            role = "S" if turn["speaker"] == "SUBJECT" else "U"
            out.append(f"{turn['msgId']}\t{role}\t{text}")
    return "\n".join(out)


def _user_content(header: dict, segments: list[dict] | None) -> str:
    if segments is None:
        return _json(header)
    return _json(header | {"format": "lines"}) + "\n\n" + _render_lines(segments)


def _chunks(segments: list[dict], max_chars: int) -> list[list[dict]]:
    out, part, size = [], [], 0
    for segment in segments:
        n = len(_json(segment))
        if part and size + n > max_chars:
            out.append(part)
            part, size = [], 0
        part.append(segment)
        size += n
    if part:
        out.append(part)
    return out


def _unique_object(fields: list[tuple[str, object]]) -> dict:
    obj = dict(fields)
    if len(obj) != len(fields):
        raise ValueError("duplicate JSON key")
    return obj


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def _copied_spans(
    pairs: list[dict], texts: Iterable[str] | None = None
) -> tuple[set[str], set[str]]:
    if texts is None:
        texts = (p[role]["text"] for p in pairs for role in ("prior", "subject"))
    speeches = {_compact(text) for text in texts}
    return speeches, {
        speech[i : i + _COPY_SPAN]
        for speech in speeches
        for i in range(len(speech) - _COPY_SPAN + 1)
    }


def _validate_observation(
    item: object,
    dimension: str,
    allowed: set[str],
    speeches: set[str],
    spans: set[str],
    max_refs: int = _MAX_REFS,
) -> dict:
    if not isinstance(item, dict) or set(item) != {"description", "evidence"}:
        raise ValueError("expected description and evidence")
    refs = item["evidence"]
    if (
        not isinstance(refs, list)
        or not 1 <= len(refs) <= max_refs
        or any(not isinstance(ref, str) for ref in refs)
    ):
        raise ValueError("expected a bounded nonempty evidence ID list")
    if len(set(refs)) != len(refs):
        raise ValueError("duplicate evidence ID")
    if not set(refs) <= allowed:
        raise ValueError("unsent SUBJECT evidence ID")

    description = item["description"]
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= (
        _MAX_DESCRIPTION_CHARS
    ):
        raise ValueError("expected a bounded nonblank description")
    description = description.strip()
    checked = unicodedata.normalize("NFKC", description)
    if (
        _UNSAFE.search(checked)
        or _CONTROL.search(checked)
        or _MARKUP.search(checked)
        or len(checked.splitlines()) != 1
    ):
        raise ValueError("unsafe description")
    _text(checked, "description")
    if _FREQUENCY.search(checked):
        raise ValueError("unsupported corpus frequency claim")
    compact = _compact(description)
    if compact in speeches or any(
        compact[j : j + _COPY_SPAN] in spans for j in range(len(compact) - _COPY_SPAN + 1)
    ):
        raise ValueError("copied source speech")
    return {"dimension": dimension, "description": description, "evidence": refs}


def _validate(
    raw: str,
    dimension: str,
    allowed: set[str],
    speeches: set[str],
    spans: set[str],
    limits: dict = _SAMPLE_LIMITS,
) -> tuple[list[dict], list[dict]]:
    try:
        if len(raw.encode("utf-8")) > limits["response_bytes"]:
            raise ValueError("response too large")
        fenced = _FENCE.fullmatch(raw)
        obj = json.loads(fenced.group(1) if fenced else raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid JSON response") from exc
    if not isinstance(obj, dict) or set(obj) != {"observations"}:
        raise ValueError("expected an object with only observations")
    items = obj["observations"]
    if not isinstance(items, list) or len(items) > limits["observations"]:
        raise ValueError("expected a bounded observations list")

    # Once the envelope is sound, one optional candidate must not block planning.
    accepted, rejected = [], []
    for i, item in enumerate(items):
        try:
            accepted.append(
                _validate_observation(item, dimension, allowed, speeches, spans, limits["refs"])
            )
        except ValueError as exc:
            rejected.append({"index": i, "reason": str(exc)})
    return accepted, rejected


def run(
    ctx: Context,
    cid: str,
    rev: str,
    folder: Path,
    budget: Budget | RunBudget,
    corpus: list[dict],
    flagged: Iterable[str],
    scene: ChapterTemplate | None,
) -> dict:
    """Analyze one fixed sample through three independent, single-pass calls.

    `corpus` is the approved S0 generation split, in source order. `flagged` contains
    approved digest message IDs to exclude. The assembly layer still checks quotes.
    """
    if scene is not None and scene not in get_args(ChapterTemplate):
        raise ValueError("S3 scene-analysis: invalid chapter template")
    out = folder / "scene-analysis"
    flagged = set(flagged)
    cfg = ctx.config.stage("s3t")
    mode = cfg.get("analysis_input", "full")
    if mode not in ("full", "sample"):
        raise ValueError("S3 scene-analysis: analysis_input must be full or sample")
    system = files("character_factory_poc").joinpath("resources", f"{SCHEMA}.md").read_text("utf-8")
    pairs, segments = [], []
    if mode == "full":
        limits = _FULL_LIMITS
        segments = _full_segments(corpus, flagged)
        parts = _chunks(segments, int(cfg.get("analysis_max_chars", _FULL_MAX_CHARS)))
        payloads = [{"segments": part} for part in parts] or [{"segments": []}]
        if len(payloads) > 1 and budget is not None:
            budget.check_plan(
                [CallPlan("s3", "원문 분할 분석 추가분", 3 * (len(payloads) - 1), None)]
            )
    else:
        limits = _SAMPLE_LIMITS
        pairs = _balanced_pairs(_candidate_groups(corpus, flagged), scene)
        payloads = [{"pairs": pairs}]
    requests = {}
    for dimension in DIMENSIONS:
        for i, payload in enumerate(payloads, 1):
            key = dimension if len(payloads) == 1 else f"{dimension}/part-{i:02}"
            header = {"dimension": dimension, "scene": scene, "mode": mode}
            if mode == "full":
                content = _user_content(header, payload["segments"])
            else:
                content = _user_content(header | payload, None)
            requests[key] = ChatRequest(
                kind="AGENT",
                stage="s3",
                ref=f"{cid}/{rev}/scene-analysis/{key}",
                messages=(Message("system", system), Message("user", content)),
                max_output_tokens=limits["output_tokens"],
                temperature=0.0,
                response_json=True,
            )
    if not write_once_json(
        out / "inputs.json",
        {
            "schemaVersion": SCHEMA,
            "systemPrompt": system,
            "systemPromptSha256": sha256_text(system),
            "scene": scene,
            "mode": mode,
            "pairs": pairs,
            "segmentCount": len(segments),
            "partCount": len(payloads),
            "requests": {
                dimension: {
                    "ref": request.ref,
                    "inputSha256": sha256_text(request.messages[1].content),
                    "maxOutputTokens": request.max_output_tokens,
                    "temperature": request.temperature,
                    "responseJson": request.response_json,
                }
                for dimension, request in requests.items()
            },
        },
    ):
        raise ValueError("S3 scene-analysis: this revision already has an input snapshot")
    if mode == "full":
        turns = [t for segment in segments for t in segment["turns"]]
        subject_ids = [t["msgId"] for t in turns if t["speaker"] == "SUBJECT"]
        speeches, spans = _copied_spans([], (t["text"] for t in turns))
    else:
        subject_ids = [p["subject"]["msgId"] for p in pairs]
        speeches, spans = _copied_spans(pairs)
    allowed = set(subject_ids)
    observations, failures = [], []
    model = ctx.analyzer_model(cid, budget)
    # The tracked model still governs transport, provider capacity, budgets, and ledger rows.
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        pending = {dim: pool.submit(model.complete, req) for dim, req in requests.items()}
        for dimension, future in pending.items():
            phase = {
                "schemaVersion": SCHEMA,
                "dimension": dimension,
                "ref": requests[dimension].ref,
            }
            try:
                response = future.result()
            except Exception as exc:
                failures.append(exc)
                phase.update(status="call-failed", error=type(exc).__name__)
            else:
                raw = getattr(response, "text", None)
                if isinstance(raw, str):
                    # A broken escaped response can contain a lone surrogate. Hash it without
                    # ever retaining or logging the unvalidated response itself.
                    phase["responseSha256"] = sha256(
                        raw.encode("utf-8", "surrogatepass")
                    ).hexdigest()
                try:
                    if not isinstance(raw, str):
                        raise ValueError("expected a text response")
                    found, rejected = _validate(
                        raw, dimension.split("/")[0], allowed, speeches, spans, limits
                    )
                except ValueError as exc:
                    phase.update(status="invalid", error=str(exc))
                    failures.append(ValueError(f"S3 scene-analysis {dimension}: {exc}"))
                else:
                    phase.update(status="ok", observations=found, rejections=rejected)
                    observations.extend(found)
            write_once_json(out / f"{dimension.replace('/', '-')}.json", phase)
    if failures:
        raise failures[0]
    cited = {ref for item in observations for ref in item["evidence"]}
    return {
        "observations": observations,
        "priorityIds": [ref for ref in subject_ids if ref in cited],
    }
