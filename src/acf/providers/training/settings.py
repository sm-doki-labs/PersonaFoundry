"""학습 공급자 설정 읽기. factory.toml의 [providers.*] 값을 타입까지 확인한다."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from acf.providers.training.errors import TrainingError


def pick(extra: dict[str, Any], keys: Iterable[str], default: Any) -> Any:
    """snake_case와 camelCase 가운데 먼저 있는 값을 쓴다."""
    for key in keys:
        if key in extra:
            return extra[key]
    return default


def as_str(extra: dict[str, Any], keys: Iterable[str], default: str) -> str:
    value = pick(extra, keys, default)
    if not isinstance(value, str):
        raise TrainingError(f"설정 {next(iter(keys), '')}는 문자열이어야 한다")
    return value


def as_int(
    extra: dict[str, Any],
    keys: Iterable[str],
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    value = pick(extra, keys, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TrainingError(f"설정 {next(iter(keys), '')}는 정수여야 한다")
    if minimum is not None and value < minimum:
        raise TrainingError(f"설정 {next(iter(keys), '')}는 {minimum} 이상이어야 한다")
    return value


def as_float(
    extra: dict[str, Any],
    keys: Iterable[str],
    default: float,
    *,
    minimum: float | None = None,
) -> float:
    value = pick(extra, keys, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TrainingError(f"설정 {next(iter(keys), '')}는 숫자여야 한다")
    number = float(value)
    if minimum is not None and number < minimum:
        raise TrainingError(f"설정 {next(iter(keys), '')}는 {minimum} 이상이어야 한다")
    return number


def as_bool(extra: dict[str, Any], keys: Iterable[str], default: bool) -> bool:
    value = pick(extra, keys, default)
    if not isinstance(value, bool):
        raise TrainingError(f"설정 {next(iter(keys), '')}는 boolean이어야 한다")
    return value


def as_int_list(extra: dict[str, Any], keys: Iterable[str], default: list[int]) -> list[int]:
    value = pick(extra, keys, default)
    if not isinstance(value, list) or any(
        isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in value
    ):
        raise TrainingError(f"설정 {next(iter(keys), '')}는 1 이상 정수 목록이어야 한다")
    return list(value)
