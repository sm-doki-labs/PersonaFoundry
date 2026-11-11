"""합성 단계 상태로 대화 가능과 제작 진행이 독립적인지 확인한다."""

import json
from types import SimpleNamespace

import pytest

from character_factory_poc.pipeline.origin import write_model_mode, write_origin
from character_factory_poc.web import reads


@pytest.mark.parametrize(
    ("stage_status", "gate_status", "expected", "done"),
    [
        ("CHECK_FAILED", "PENDING", "failed", 4),
        # 수정 요청은 실패가 아니라 다시 확인할 일이다(QA 3차).
        ("REJECTED", "PENDING", "needs_review", 4),
        ("AWAITING_HUMAN", "AWAITING_HUMAN", "needs_review", 4),
        ("APPROVED", "APPROVED", "chat_ready", 5),
    ],
)
def test_ready_chat_preserves_actual_progress(
    tmp_path, monkeypatch, stage_status, gate_status, expected, done
):
    folder = tmp_path / "synthetic"
    folder.mkdir()
    write_origin(folder, "SOURCE")
    write_model_mode(folder, "PROMPT_ONLY")
    state = {
        "stages": {sid: {"status": "APPROVED"} for sid in ("s0", "s3", "s7", "s8c")},
        "gates": {"G6": {"status": gate_status}},
    }
    state["stages"]["s8"] = {"status": stage_status}
    (folder / "state.json").write_text(json.dumps(state))
    monkeypatch.setattr(
        reads.Scene, "read", lambda *a, **k: SimpleNamespace(readiness=lambda: {"ready": True})
    )
    row = reads.character_summary(folder)
    assert row["chatReady"] is True
    assert row["status"] == expected
    assert (row["goal"]["done"], row["goal"]["total"]) == (done, 5)
    assert row["progress"]["done"] == done


def test_failed_job_is_visible_even_with_usable_chat():
    row = {"status": "chat_ready", "chatReady": True}
    reads.job_status(row, None, {"status": "failed"})
    assert row["status"] == "failed"
    assert row["chatReady"] is True
