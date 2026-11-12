"""Hedged text calls: if a call is still running after a delay, send the same request once more
and use whichever answer arrives first.

The slower call is not cancelled; it finishes in the background so its usage still reaches the
ledger. Both calls are billed. Used by evidence-v10 for the labeler, whose latency varies
several fold for the same work (Son 2026-11-12: one labelling call 509 s, similar ones 130-200 s).
"""

from __future__ import annotations

import threading
from dataclasses import replace

from character_factory_poc.providers.base import ChatRequest, ChatResponse


class HedgedTextModel:
    def __init__(self, inner, after_s: float, on_hedge=None):
        self.inner = inner
        self.after_s = float(after_s)
        self.on_hedge = on_hedge

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, request: ChatRequest) -> ChatResponse:
        if self.after_s <= 0:
            return self.inner.complete(request)
        done = threading.Condition()
        results: list = []  # (label, response or None, exception or None)

        def run(label, req):
            try:
                out = (label, self.inner.complete(req), None)
            except BaseException as exc:  # noqa: BLE001 - reported to the waiting caller
                out = (label, None, exc)
            with done:
                results.append(out)
                done.notify_all()

        threading.Thread(target=run, args=("first", request), daemon=False).start()
        with done:
            done.wait_for(lambda: results, timeout=self.after_s)
            if results and results[0][1] is not None:
                return results[0][1]
            if results:  # the first call failed before the hedge delay: behave as before
                raise results[0][2]
        hedge = replace(request, ref=request.ref + "-hedge")
        if self.on_hedge is not None:
            self.on_hedge(request.ref, self.after_s)
        threading.Thread(target=run, args=("hedge", hedge), daemon=False).start()
        with done:
            while True:
                done.wait_for(lambda: any(r[1] is not None for r in results) or len(results) == 2)
                ok = [r for r in results if r[1] is not None]
                if ok:
                    return ok[0][1]
                if len(results) == 2:
                    raise results[0][2]
