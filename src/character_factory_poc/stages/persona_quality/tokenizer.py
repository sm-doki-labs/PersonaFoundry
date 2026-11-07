"""Tokenize endpoint adapter. Unknown or differently bound counts fail closed."""

from __future__ import annotations

import dataclasses

import httpx


class RemoteTokenCounter:
    def __init__(self, url: str, model: str):
        self.url = url
        self.model = model

    def __call__(self, messages) -> int:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                self.url,
                json=dict(model=self.model, messages=[dataclasses.asdict(m) for m in messages]),
            )
        response.raise_for_status()
        obj = response.json()
        count = obj.get("count", obj.get("token_count"))
        if (
            obj.get("model") != self.model
            or obj.get("exact") is not True
            or type(count) is not int
            or count < 0
        ):
            raise ValueError("tokenizer response is not an exact count for the bound model")
        return count
