"""합성 승인·비교 기록만 사용해 공정 종료와 품질 판정을 구분한다."""

import json

import pytest

from character_factory_poc.pipeline.origin import write_model_mode, write_origin
from character_factory_poc.web import reads


def put(folder, name, value):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def character(tmp_path):
    folder = tmp_path / "runs/characters/synthetic"
    folder.mkdir(parents=True)
    write_origin(folder, "SOURCE")
    write_model_mode(folder, "PROMPT_ONLY")
    state = {
        "stages": {
            "s8": {"status": "APPROVED", "currentRev": "pv6"},
            "s10": {"status": "APPROVED", "currentRev": "ev2"},
            "s11": {"status": "AWAITING_HUMAN", "currentRev": "pkg1"},
        },
        "gates": {
            "G6": {"status": "APPROVED", "rev": "pv6", "recordRef": "gates/G6-pv6.json"},
            "G8": {"status": "APPROVED", "rev": "ev2", "recordRef": "gates/G8-ev2.json"},
            "G9": {"status": "AWAITING_HUMAN", "rev": "pkg1"},
        },
    }
    put(folder, "state.json", state)
    for gate, rev in (("G6", "pv6"), ("G8", "ev2")):
        put(
            folder,
            f"gates/{gate}-{rev}.json",
            {
                "gate": gate,
                "rev": rev,
                "decision": "APPROVE",
                "reviewer": "시연 자동 승인",
                "reasons": "시연 모드 자동 승인.",
            },
        )
    return folder, state


def comparison(folder, statuses):
    put(
        folder,
        "s10-eval/ev2/twin-comparison.json",
        {
            "schemaVersion": "twin-comparison-v1",
            "characterId": "synthetic",
            "revision": "ev2",
            "conditions": [
                {
                    "armId": f"arm-{i}",
                    "status": status,
                    "modelScore": {"correct": 0, "total": 0, "rate": None},
                    "humanScore": {"correct": 0, "total": 0, "rate": None},
                }
                for i, status in enumerate(statuses)
            ],
        },
    )


def test_auto_approval_and_skipped_comparison_are_not_quality_pass(character, tmp_path):
    folder, _ = character
    comparison(folder, ["SKIPPED", "NO_SERVING"])
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    row = reads.character_summary(folder)
    q = row.get("qualityStatus", {})
    assert q.get("status") == "evaluation_skipped"
    assert q["verified"] is False
    assert q["comparison"]["status"] == "SKIPPED"
    assert q["comparison"]["reportRef"] == "s10-eval/ev2/twin-comparison.json"
    approvals = {g["gate"]: g for g in q["approvals"]}
    assert approvals["G6"]["status"] == approvals["G8"]["status"] == "auto_approved"
    assert approvals["G6"]["reviewer"] == "시연 자동 승인"
    assert row["status"] == "needs_review"
    assert reads.character_detail(tmp_path, "synthetic")["qualityStatus"] == q
    assert before == {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


@pytest.mark.parametrize("reviewer", ["자동 진행", "auto:--auto-approve", "시연 자동 승인"])
def test_automatic_reviewer_is_not_human_review(character, reviewer):
    folder, _ = character
    put(
        folder,
        "gates/G6-pv6.json",
        {
            "gate": "G6",
            "rev": "pv6",
            "decision": "APPROVE",
            "reviewer": reviewer,
        },
    )
    q = reads.character_summary(folder).get("qualityStatus", {})
    assert q.get("verified") is False
    assert next(g for g in q["approvals"] if g["gate"] == "G6")["status"] == "auto_approved"


def test_human_approval_and_complete_comparison_do_not_imply_quality_pass(character):
    folder, _ = character
    comparison(folder, ["COMPLETE"])
    for gate, rev in (("G6", "pv6"), ("G8", "ev2")):
        put(
            folder,
            f"gates/{gate}-{rev}.json",
            {
                "gate": gate,
                "rev": rev,
                "decision": "SELECT",
                "reviewer": "synthetic reviewer",
            },
        )
    q = reads.character_summary(folder).get("qualityStatus", {})
    assert q.get("verified") is False
    assert q["comparison"]["status"] == "COMPLETE"
    assert q["status"] == "review_recorded"
    assert all(
        g["status"] == "approval_recorded" for g in q["approvals"] if g["gate"] in ("G6", "G8")
    )


def test_old_approval_and_old_comparison_are_not_current_evidence(character):
    folder, state = character
    comparison(folder, ["COMPLETE"])
    state["stages"]["s8"]["currentRev"] = "pv7"
    state["stages"]["s10"]["currentRev"] = "ev3"
    put(folder, "state.json", state)
    q = reads.character_summary(folder).get("qualityStatus", {})
    assert q.get("verified") is False
    assert q["comparison"]["status"] == "MISSING"
    assert next(g for g in q["approvals"] if g["gate"] == "G6")["status"] == "unverified"


@pytest.mark.parametrize(
    "bad", [[], {"revision": "old", "conditions": []}, {"revision": "ev2", "conditions": "bad"}]
)
def test_bad_comparison_does_not_break_summary_or_claim_review(character, bad):
    folder, _ = character
    put(folder, "s10-eval/ev2/twin-comparison.json", bad)
    q = reads.character_summary(folder).get("qualityStatus", {})
    assert q.get("verified") is False
    assert q["comparison"]["status"] == "UNREADABLE"


def test_succeeded_job_waiting_g9_remains_review_pending_with_usable_chat():
    row = {"status": "chat_ready", "chatReady": True}
    reads.job_status(row, None, {"status": "succeeded", "waiting": ["G9"]})
    assert row["status"] == "needs_review"
    assert row["chatReady"] is True


def test_old_waiting_job_does_not_override_new_gate_approval():
    row = {"status": "chat_ready", "gates": [{"id": "G9", "status": "APPROVED"}]}
    reads.job_status(row, None, {"status": "succeeded", "waiting": ["G9"]})
    assert row["status"] == "chat_ready"
