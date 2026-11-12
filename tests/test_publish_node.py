"""D-0212: 테스터 발행 노드(px)와 기준 사진 흐름의 시연 모드(전부 자동 승인)."""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common import notify as notify_mod
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.pipeline.demo import REVIEWER, demo_answer
from character_factory_poc.stages.export import preview
from tests.support.flow import make_ctx
from tests.test_reference_frontend_flow import intake
from tests.test_video_evidence_handoff import wait_idle


@pytest.fixture
def sent(monkeypatch):
    messages: list[dict] = []
    monkeypatch.setenv(notify_mod.WEBHOOK_ENV, "https://discord.com/api/webhooks/1/test")
    monkeypatch.setattr(
        notify_mod, "_post", lambda url, body: messages.append(json.loads(body)) or 204
    )
    return messages


def _result(cid, status, **kw):
    return preview.PreviewResult(characterId=cid, target="dev", status=status, name="합성", **kw)


def _ready(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = "cf-20261113-px"
    ctx.character_dir(cid).mkdir(parents=True)
    ctx.state(cid).set_gate("G9", "APPROVED", "pk1", None)
    return ctx, cid


def test_publish_node_records_success_and_notifies(tmp_path, sent, monkeypatch):
    ctx, cid = _ready(tmp_path)
    monkeypatch.setattr(
        preview, "publish_preview", lambda c, i, **kw: _result(i, "PUBLISHED", apiCharacterId=7)
    )
    preview.run_px(ctx, cid)
    assert ctx.state(cid).stage("px").status == "APPROVED"
    assert [m["embeds"][0]["title"] for m in sent] == ["✅ 테스터 미리보기 발행 · 합성"]
    assert "앱 캐릭터 번호 7" in sent[0]["embeds"][0]["description"]


def test_publish_node_failure_is_check_failed_and_notified(tmp_path, sent, monkeypatch):
    ctx, cid = _ready(tmp_path)
    failed = _result(cid, "FAILED")
    failed.steps.append(preview.PreviewStep("넣기", False, "HTTP 502"))
    monkeypatch.setattr(preview, "publish_preview", lambda c, i, **kw: failed)
    with pytest.raises(CheckFailed):
        preview.run_px(ctx, cid)
    st = ctx.state(cid).stage("px")
    assert st.status == "CHECK_FAILED" and "502" in (st.lastError or "")
    assert sent and sent[0]["embeds"][0]["title"].startswith("❌")


def test_demo_g9_answer_marks_only_required_presentation_checks(tmp_path):
    ctx, cid = _ready(tmp_path)
    ctx.state(cid).set_gate("G9", "AWAITING_HUMAN", "pk1", None)
    folder = ctx.character_dir(cid) / "s11-release" / "pk1"
    folder.mkdir(parents=True)
    checks = {
        "humanChecks": [
            {"id": "noReuse", "required": True},
            {"id": "legalReview", "required": False},
        ]
    }
    (folder / "presentation-check.json").write_text(json.dumps(checks))
    answer = demo_answer(ctx, cid, "G9")
    assert answer["reviewer"] == REVIEWER
    assert answer["presentationChecks"] == {"noReuse": True}


def test_reference_flow_demo_approves_photo_and_reaches_publish_node(tmp_path, sent, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    calls = []

    def fake_publish(ctx_, cid_, **kw):
        calls.append(ctx_.state(cid_).gate("G9").status)
        return _result(cid_, "PUBLISHED", apiCharacterId=9)

    monkeypatch.setattr(preview, "publish_preview", fake_publish)
    # 개인 인물은 본인 동의 기록이 있어야 공개 점검을 통과한다(시연 모드도 건너뛰지 않는다).
    draft = ctx.character_dir(cid) / "s0-source" / "intake.json"
    data = json.loads(draft.read_text())
    data["usageBasis"] |= {"consentBy": "본인", "consentDate": "2026-11-13", "scope": "발표 시연"}
    draft.write_text(json.dumps(data, ensure_ascii=False))
    switched = client.put(url + "/demo-mode", json={"enabled": True, "budgetUsd": 5})
    assert switched.is_success, switched.text
    launched = client.post(url + "/finalize")
    assert launched.is_success, launched.text
    wait_idle(jobs, cid)
    state = ctx.state(cid)
    job = jobs.get(launched.json()["jobId"])
    assert state.gate("G4").status == "APPROVED", job
    assert state.gate("G9").status == "APPROVED", [
        x for x in (job.get("log") or []) if "G9" in x or "s11" in x or "px" in x
    ]
    assert state.stage("px").status == "APPROVED", job
    assert calls == ["APPROVED"]
    assert state.stage("sx").status == "PENDING"
    # 알림은 발행이 끝났을 때 한 번만 간다(시작 알림 없음).
    assert [m["embeds"][0]["title"] for m in sent] == ["✅ 테스터 미리보기 발행 · 합성"]
