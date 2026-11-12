"""D-0204: a gate decision is recorded while a job is still running, and never overwrites a
revision the job opened in the meantime.

Synthetic offline flow only.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.orchestrator import RunLog
from character_factory_poc.pipeline.state import DECISION_SNAPSHOT, StateFile
from character_factory_poc.web import create_app
from tests.support.web_gates import answer_for
from tests.test_web_auto_resume import _start


def test_decision_does_not_wait_for_a_running_job(tmp_path: Path) -> None:
    root = tmp_path / "f"
    ctx, cid, _ = _start(root)
    release = threading.Event()
    started = threading.Event()

    def runner(job, stream) -> RunLog:  # a long parallel stage such as s8c
        started.set()
        assert release.wait(timeout=20)
        return RunLog()

    app = create_app(root, runner=runner)
    client = TestClient(app)
    app.state.jobs.submit(cid, until="sx")
    assert started.wait(timeout=5) and app.state.jobs.active_for(cid)
    items = client.get(f"/api/characters/{cid}/gates/G1").json()["items"]
    t0 = time.monotonic()
    res = client.post(f"/api/characters/{cid}/gates/G1/decision", json=answer_for("G1", items))
    elapsed = time.monotonic() - t0
    try:
        assert res.status_code == 200, res.text
        assert elapsed < 5, f"decision waited {elapsed:.1f}s for the running job"
        assert ctx.state(cid).gate("G1").status == "APPROVED"
        assert app.state.jobs.active_for(cid)  # the job is still running
    finally:
        release.set()


def test_decision_is_refused_when_the_gate_moved_to_a_new_revision(tmp_path: Path) -> None:
    state = StateFile(tmp_path / "state.json", "c1")
    state.set_gate("G6", "AWAITING_HUMAN", "pv1", None)
    token = DECISION_SNAPSHOT.set({"G6": ("AWAITING_HUMAN", "pv1")})
    try:
        # The job opens pv2 between the reviewer's check and the write.
        StateFile(tmp_path / "state.json", "c1").set_gate("G6", "PENDING", "pv2", None)
        with pytest.raises(FactoryError):
            state.set_gate("G6", "APPROVED", "pv1", "gates/G6-pv1.json")
    finally:
        DECISION_SNAPSHOT.reset(token)
    fresh = StateFile(tmp_path / "state.json", "c1").gate("G6")
    assert (fresh.status, fresh.rev) == ("PENDING", "pv2")

    token = DECISION_SNAPSHOT.set({"G6": ("PENDING", "pv2")})
    try:
        state.set_gate("G6", "APPROVED", "pv2", "gates/G6-pv2.json")
    finally:
        DECISION_SNAPSHOT.reset(token)
    assert StateFile(tmp_path / "state.json", "c1").gate("G6").status == "APPROVED"
