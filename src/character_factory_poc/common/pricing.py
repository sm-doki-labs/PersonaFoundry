"""단가표 `price-table-v1` 조회와 호출 비용 계산 (명세 §24.4, LLD §22.2 C → D).

단가표는 저장소 자료 파일(`resources/price-table-v1.json`)이고 버전으로만 바뀐다. 단위는
100만 토큰당 USD이며 출력 단가는 추론·생각 토큰을 포함한다. 확인하지 못한 단가는 `None`으로
두고, 비용을 계산할 수 없으면 0이 아니라 미확인(`usd = None`)과 그 이유를 돌려준다.
캐시 쓰기 단가는 OpenAI가 GPT-5.6 이후 모델의 캐시 쓰기를 입력 단가의 1.25배로 청구하는 값을
담는다(https://developers.openai.com/api/docs/guides/prompt-caching).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

TABLE_VERSION = "price-table-v1"
TABLE_FILE = "price-table-v1.json"
OVERRIDE_SOURCE = "factory.toml"
MODEL_PREFIXES = ("google-antigravity/", "openai/")
OVERRIDE_KEYS = (
    "input_per_million",
    "cached_input_per_million",
    "cache_write_per_million",
    "output_per_million",
)

_ENTRY_KEYS = frozenset(
    {
        "model",
        "family",
        "effectiveFrom",
        "effectiveTo",
        "inputPerMillion",
        "cachedInputPerMillion",
        "cacheWritePerMillion",
        "outputPerMillion",
        "source",
        "checkedAt",
    }
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class PriceEntry:
    model: str
    family: str
    effective_from: date
    effective_to: date | None
    input_per_million: float | None
    cached_input_per_million: float | None
    cache_write_per_million: float | None
    output_per_million: float | None
    source: str
    checked_at: str
    basis: Literal["table", "config_override"] = "table"

    def covers(self, day: date) -> bool:
        """적용 기간(양끝 포함)에 `day`가 들어가는지."""
        if day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to


def canonical_model(model: str) -> str:
    """중계·공급자 접두사(`google-antigravity/`, `openai/`)를 뺀 공식 모델 ID."""
    name = str(model).strip()
    for prefix in MODEL_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _family_of(model: str) -> str:
    """덮어쓰기 항목의 계열 표시용. 표에 같은 모델이 있으면 그쪽 계열을 쓴다."""
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("gemini-"):
        return "gemini"
    return "unknown"


def _parse_date(value: Any, field_name: str, where: str) -> date:
    if not isinstance(value, str) or not _DATE.match(value):
        raise ValueError(f"단가표 {where}: {field_name}는 YYYY-MM-DD 문자열이어야 한다: {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"단가표 {where}: {field_name}가 없는 날짜다: {value!r}") from None


def _rate(value: Any, field_name: str, where: str) -> float | None:
    """단가 칸 하나. 비어 있으면 `None`, 숫자가 아니거나 음수면 `ValueError`."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{where}: {field_name}는 숫자여야 한다: {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{where}: {field_name}는 0 이상인 유한한 수여야 한다: {value!r}")
    return number


def _text(value: Any, field_name: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"단가표 {where}: {field_name}는 비어 있지 않은 문자열이어야 한다")
    return value


def _entry(raw: Any, index: int) -> PriceEntry:
    where = f"entries[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"단가표 {where}: 항목은 객체여야 한다")
    keys = set(raw)
    if keys != _ENTRY_KEYS:
        missing = sorted(_ENTRY_KEYS - keys)
        extra = sorted(keys - _ENTRY_KEYS)
        raise ValueError(f"단가표 {where}: 필드가 맞지 않는다 (빠짐 {missing}, 남음 {extra})")
    model = _text(raw["model"], "model", where)
    if canonical_model(model) != model:
        raise ValueError(f"단가표 {where}: model은 접두사 없는 공식 모델 ID여야 한다: {model}")
    start = _parse_date(raw["effectiveFrom"], "effectiveFrom", where)
    end = None
    if raw["effectiveTo"] is not None:
        end = _parse_date(raw["effectiveTo"], "effectiveTo", where)
        if end < start:
            raise ValueError(f"단가표 {where}: effectiveTo가 effectiveFrom보다 앞선다")
    checked = raw["checkedAt"]
    _parse_date(checked, "checkedAt", where)
    return PriceEntry(
        model=model,
        family=_text(raw["family"], "family", where),
        effective_from=start,
        effective_to=end,
        input_per_million=_rate(raw["inputPerMillion"], "inputPerMillion", f"단가표 {where}"),
        cached_input_per_million=_rate(
            raw["cachedInputPerMillion"], "cachedInputPerMillion", f"단가표 {where}"
        ),
        cache_write_per_million=_rate(
            raw["cacheWritePerMillion"], "cacheWritePerMillion", f"단가표 {where}"
        ),
        output_per_million=_rate(raw["outputPerMillion"], "outputPerMillion", f"단가표 {where}"),
        source=_text(raw["source"], "source", where),
        checked_at=checked,
        basis="table",
    )


def _overlaps(a: PriceEntry, b: PriceEntry) -> bool:
    a_end = a.effective_to or date.max
    b_end = b.effective_to or date.max
    return a.effective_from <= b_end and b.effective_from <= a_end


def parse_table(data: Any) -> tuple[PriceEntry, ...]:
    """단가표 JSON 객체를 검증해 항목 묶음으로 바꾼다. 표 오류는 `ValueError`다."""
    if not isinstance(data, dict):
        raise ValueError("단가표는 JSON 객체여야 한다")
    if data.get("version") != TABLE_VERSION:
        raise ValueError(f"단가표 version이 {TABLE_VERSION}이 아니다: {data.get('version')!r}")
    if data.get("currency") != "USD":
        raise ValueError("단가표 currency는 USD여야 한다")
    if data.get("unit") != "per_million_tokens":
        raise ValueError("단가표 unit은 per_million_tokens여야 한다")
    if data.get("outputIncludesReasoning") is not True:
        raise ValueError("단가표 outputIncludesReasoning은 true여야 한다")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("단가표 entries는 목록이어야 한다")
    entries = tuple(_entry(raw, i) for i, raw in enumerate(raw_entries))
    by_model: dict[str, list[PriceEntry]] = {}
    for entry in entries:
        by_model.setdefault(entry.model, []).append(entry)
    for model, group in by_model.items():
        if len({e.family for e in group}) > 1:
            raise ValueError(f"단가표: {model}의 family가 항목마다 다르다")
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if _overlaps(a, b):
                    raise ValueError(
                        f"단가표: {model}의 적용 기간이 겹친다 "
                        f"({a.effective_from}~{a.effective_to or ''}, "
                        f"{b.effective_from}~{b.effective_to or ''})"
                    )
    return entries


@lru_cache(maxsize=1)
def _default_table() -> tuple[PriceEntry, ...]:
    text = files("character_factory_poc.resources").joinpath(TABLE_FILE).read_text("utf-8")
    return parse_table(json.loads(text))


def load_table(path: Path | str | None = None) -> tuple[PriceEntry, ...]:
    """단가표를 읽는다. `path`가 없으면 저장소 자료 파일을 한 번만 읽어 둔다."""
    if path is None:
        return _default_table()
    return parse_table(json.loads(Path(path).read_text(encoding="utf-8")))


def normalize_overrides(overrides: Mapping[str, Any] | None) -> dict[str, dict[str, float | None]]:
    """설정의 단가 덮어쓰기를 공식 모델 ID 키로 맞추고 값을 검증한다.

    값은 `input_per_million`·`cached_input_per_million`·`cache_write_per_million`·
    `output_per_million`만 받는다. 빠진 칸은 `None`(미확인)이다. 숫자가 아니거나 음수,
    모르는 칸, 같은 공식 모델 ID로 모이는 키가 둘이면 `ValueError`다.
    """
    if not overrides:
        return {}
    if not isinstance(overrides, Mapping):
        raise ValueError("단가 덮어쓰기는 모델 → 단가 표여야 한다")
    normalized: dict[str, dict[str, float | None]] = {}
    for raw_model, rates in overrides.items():
        where = f"pricing.models.{raw_model!r}"
        if not isinstance(rates, Mapping):
            raise ValueError(f"{where}: 단가 표여야 한다")
        unknown = sorted(set(rates) - set(OVERRIDE_KEYS))
        if unknown:
            raise ValueError(f"{where}: 모르는 칸 {unknown}")
        if not rates:
            raise ValueError(f"{where}: 단가 칸이 하나도 없다")
        model = canonical_model(raw_model)
        if not model:
            raise ValueError(f"{where}: 모델 이름이 비었다")
        if model in normalized:
            raise ValueError(f"{where}: 같은 모델 {model}의 덮어쓰기가 둘이다")
        normalized[model] = {key: _rate(rates.get(key), key, where) for key in OVERRIDE_KEYS}
    return normalized


def _utc_day(at: datetime | date) -> date:
    """호출 시각의 UTC 날짜. 시간대가 없는 시각은 UTC로 본다."""
    if isinstance(at, datetime):
        if at.tzinfo is None:
            return at.date()
        return at.astimezone(UTC).date()
    return at


def lookup(model: str, at: datetime, overrides: dict | None = None) -> PriceEntry | None:
    """공식 모델 ID와 호출 시각(UTC 날짜)으로 단가 항목을 찾는다.

    설정 덮어쓰기가 있으면 기간과 무관하게 우선하고 `basis = config_override`다.
    맞는 항목이 없으면 `None`이다.
    """
    key = canonical_model(model)
    table = load_table()
    override = normalize_overrides(overrides).get(key)
    if override is not None:
        family = next((e.family for e in table if e.model == key), _family_of(key))
        return PriceEntry(
            model=key,
            family=family,
            effective_from=date.min,
            effective_to=None,
            input_per_million=override["input_per_million"],
            cached_input_per_million=override["cached_input_per_million"],
            cache_write_per_million=override["cache_write_per_million"],
            output_per_million=override["output_per_million"],
            source=OVERRIDE_SOURCE,
            checked_at="",
            basis="config_override",
        )
    day = _utc_day(at)
    for entry in table:
        if entry.model == key and entry.covers(day):
            return entry
    return None


def _tokens(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError
    return value


def estimate(usage: dict | None, entry: PriceEntry | None) -> dict:
    """`usage-v1`과 단가 항목으로 호출 비용(USD)을 계산한다.

    `inputTokens`는 캐시 읽기(`cachedInputTokens`)와 캐시 쓰기(`cacheWriteTokens`)를 포함한
    전체 입력이다. 비용 = ((입력 − 캐시 읽기 − 캐시 쓰기) × 입력 단가 + 캐시 읽기 × 캐시 읽기 단가
    + 캐시 쓰기 × 캐시 쓰기 단가 + 출력 × 출력 단가) / 1e6. 캐시 읽기·쓰기 토큰이 `None`이면 0이다.
    캐시 읽기 토큰이 있는데 캐시 읽기 단가가 없으면 그 부분에 입력 단가를 쓰고
    `upperBound = True`다. 계산할 수 없으면 `usd = None`이고 `reason`은 `no_price`(항목 없음),
    `missing_rate`(입력·출력 단가 미확인, 또는 캐시 쓰기 토큰이 있는데 쓰기 단가 미확인),
    `no_usage`(사용량 미상), `invalid_usage`(음수·정수가 아닌 값, 또는 캐시 읽기와 쓰기의
    합이 입력보다 큼) 가운데 하나다.
    """
    if entry is None:
        return {"usd": None, "upperBound": False, "reason": "no_price"}
    if entry.input_per_million is None or entry.output_per_million is None:
        return {"usd": None, "upperBound": False, "reason": "missing_rate"}
    if usage is None:
        return {"usd": None, "upperBound": False, "reason": "no_usage"}
    try:
        input_tokens = _tokens(usage.get("inputTokens"))
        output_tokens = _tokens(usage.get("outputTokens"))
        cached_tokens = _tokens(usage.get("cachedInputTokens")) or 0
        write_tokens = _tokens(usage.get("cacheWriteTokens")) or 0
    except TypeError:
        return {"usd": None, "upperBound": False, "reason": "invalid_usage"}
    if input_tokens is None or output_tokens is None:
        return {"usd": None, "upperBound": False, "reason": "no_usage"}
    if cached_tokens + write_tokens > input_tokens:
        return {"usd": None, "upperBound": False, "reason": "invalid_usage"}
    write_rate = entry.cache_write_per_million
    if write_tokens > 0 and write_rate is None:
        return {"usd": None, "upperBound": False, "reason": "missing_rate"}
    cached_rate = entry.cached_input_per_million
    upper_bound = False
    if cached_rate is None:
        cached_rate = entry.input_per_million
        upper_bound = cached_tokens > 0
    usd = (
        (input_tokens - cached_tokens - write_tokens) * entry.input_per_million
        + cached_tokens * cached_rate
        + write_tokens * (write_rate or 0.0)
        + output_tokens * entry.output_per_million
    ) / 1_000_000
    return {"usd": usd, "upperBound": upper_bound, "reason": None}


def price_ref(entry: PriceEntry | None) -> dict | None:
    """원장 행의 `price` 칸. 덮어쓰기는 표에서 온 값이 아니므로 표 버전과 기간을 비운다."""
    if entry is None:
        return None
    from_table = entry.basis == "table"
    return {
        "table": TABLE_VERSION if from_table else None,
        "model": entry.model,
        "effectiveFrom": entry.effective_from.isoformat() if from_table else None,
        "effectiveTo": (
            entry.effective_to.isoformat() if from_table and entry.effective_to else None
        ),
        "source": entry.source,
        "basis": entry.basis,
    }


def _priced(entry: PriceEntry | None) -> bool:
    return (
        entry is not None
        and entry.input_per_million is not None
        and entry.output_per_million is not None
    )


def missing_prices(models: Iterable[str], at: datetime, overrides: dict | None = None) -> list[str]:
    """입력·출력 단가를 정할 수 없는 모델 이름(받은 그대로, 처음 나온 순서, 중복 없이)."""
    missing: list[str] = []
    for model in models:
        if model not in missing and not _priced(lookup(model, at, overrides)):
            missing.append(model)
    return missing


def max_rates(
    models: Iterable[str], at: datetime, overrides: dict | None = None
) -> tuple[float, float] | None:
    """모든 모델의 (입력 단가 최댓값, 출력 단가 최댓값).

    모델마다 입력 상한은 max(입력 단가, 캐시 쓰기 단가)다. 캐시 쓰기 단가가 없으면 입력 단가만
    본다. 하나라도 입력·출력 단가가 미확인이거나 모델이 없으면 `None`이다.
    """
    entries = [lookup(model, at, overrides) for model in models]
    priced = [e for e in entries if _priced(e)]
    if not entries or len(priced) != len(entries):
        return None
    inputs = [
        max(e.input_per_million, e.cache_write_per_million or 0.0)
        for e in priced
        if e.input_per_million is not None
    ]
    outputs = [e.output_per_million for e in priced if e.output_per_million is not None]
    return max(inputs), max(outputs)
