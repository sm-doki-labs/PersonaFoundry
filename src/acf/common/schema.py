"""계약 검증 (LLD §5). pydantic 모델을 이름으로 찾고 extra 필드를 거절한다."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from acf.common.errors import ValidationFailed

_REGISTRY: dict[str, type[BaseModel]] = {}


def register(name: str):
    def deco(cls: type[BaseModel]):
        _REGISTRY[name] = cls
        return cls

    return deco


def contract(name: str) -> type[BaseModel]:
    if name not in _REGISTRY:
        raise KeyError(f"알 수 없는 계약: {name}")
    return _REGISTRY[name]


def validate(name: str, obj: Any) -> BaseModel:
    cls = contract(name)
    try:
        return cls.model_validate(obj)
    except ValidationError as e:
        problems = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"]) or "<root>"
            problems.append(f"{loc}: {err['msg']}")
        raise ValidationFailed(name, problems) from None


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def known_contracts() -> list[str]:
    return sorted(_REGISTRY)
