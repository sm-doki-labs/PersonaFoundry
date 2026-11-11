"""시연 모드: 켜면 관문을 모두 자동 승인하고 패키지 승인 뒤 테스터 미리보기 발행·알림까지 간다."""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common import notify as notify_mod
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline import demo_flow
from character_factory_poc.pipeline.demo import REVIEWER, read_demo_mode, write_demo_mode
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.providers.fake_vision import FakeVisionModel, all_pass
from character_factory_poc.stages.export import preview
from tests.support.flow import make_ctx
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_evidence_pipeline import candidate
from tests.test_scene_flow import backgrounds, poses, scenes
from tests.test_source_s0 import _good_digest, _twin
from tests.test_twin_flow import _pack
from tests.test_twin_s3 import _answer


@pytest.fixture
def sent(monkeypatch):
    messages: list[dict] = []
    monkeypatch.setenv(notify_mod.WEBHOOK_ENV, "https://discord.com/api/webhooks/1/test")

    def sender(url, body):
        messages.append(json.loads(body))
        return 204

    monkeypatch.setattr(notify_mod, "_post", sender)
    return messages


def _motif(tmp_path, monkeypatch=None):
    ctx, agents = make_ctx(tmp_path)
    from character_factory_poc.common import demo_chat
    from character_factory_poc.common.config import ProviderConfig
    from character_factory_poc.providers.fake import FakeTextModel

    ctx.config.providers["demo_chat"] = ProviderConfig(adapter="fake", model="synthetic")
    if monkeypatch is not None:
        fake = FakeTextModel(model="synthetic", responses={"*": "응, 잘 들었어."})
        monkeypatch.setattr(demo_chat, "make_text_model", lambda cfg: fake)
    # 얼굴 묘사(s2)만 faceShape를 돌려주고, 나머지 판정은 모두 통과다.
    ctx.use_vision(
        FakeVisionModel(
            responder=lambda req: (
                {"faceShape": "oval"} if "<rubric>" not in req.prompt else all_pass(req)
            )
        )
    )
    cid = _twin(ctx, "cf-20261112-demo")
    write_model_mode(ctx.character_dir(cid), "PROMPT_ONLY")
    for stage, fn in [
        ("s0", _good_digest),
        ("s3-twin", _answer),
        ("s4a", backgrounds),
        ("s4b-scene", scenes),
        ("s4b-pose", poses),
        ("s7", lambda req: trait_sheet_for(ctx, cid)),
        ("s8", candidate),
        ("s8c", lambda req: _start().model_dump() | {"characterId": cid}),
    ]:
        agents.set(stage, fn)
    return ctx, cid


def test_demo_runs_every_gate_and_publishes(tmp_path, sent, monkeypatch):
    ctx, cid = _motif(tmp_path, monkeypatch)
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=5)
    calls = []

    def fake_publish(ctx_, cid_, **kw):
        calls.append(cid_)
        assert ctx_.state(cid_).gate("G9").status == "APPROVED"
        return preview.PreviewResult(
            characterId=cid_, target="test", status="PUBLISHED", apiCharacterId=41, name="엄마"
        )

    monkeypatch.setattr(preview, "publish_preview", fake_publish)
    log = run_until(ctx, cid, RunOptions(until="G6", source_pack=_pack(tmp_path), web=True))
    state = ctx.state(cid)
    gates = ["G0", "G1s", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6", "G8", "G9"]
    assert {g: state.gate(g).status for g in gates} == {g: "APPROVED" for g in gates}, log.steps
    records = list((ctx.character_dir(cid) / "gates").rglob("*.json"))
    reviewers = {
        json.loads(p.read_text())["reviewer"] for p in records if "reviewer" in p.read_text()
    }
    assert reviewers == {REVIEWER}
    assert calls == [cid]
    assert [m["embeds"][0]["title"] for m in sent] == ["✅ 테스터 미리보기 발행 · 엄마"]
    assert "앱 캐릭터 번호 41" in sent[0]["embeds"][0]["description"]
    assert (
        json.loads((ctx.character_dir(cid) / demo_flow.STATUS_FILE).read_text())["phase"]
        == "published"
    )

    # 다시 돌려도 두 번 발행하지 않는다.
    monkeypatch.setattr(demo_flow, "_already_published", lambda c, i: {"apiCharacterId": 41})
    run_until(ctx, cid, RunOptions(until="G6", web=True))
    assert calls == [cid]


def test_budget_stop_notifies(tmp_path, sent, monkeypatch):
    ctx, cid = _motif(tmp_path, monkeypatch)
    write_demo_mode(ctx.character_dir(cid), enabled=True, budget_usd=5)
    monkeypatch.setattr("character_factory_poc.pipeline.demo.spent_since", lambda *a: 6.0)
    log = run_until(ctx, cid, RunOptions(until="G6", source_pack=_pack(tmp_path), web=True))
    assert any("시연 예산 상한" in s for s in log.steps)
    assert sent and sent[-1]["embeds"][0]["title"].startswith("⚠️ 예산 상한 도달")


def test_without_demo_human_gates_wait(tmp_path, sent):
    ctx, cid = _motif(tmp_path)
    log = run_until(ctx, cid, RunOptions(until="G3", source_pack=_pack(tmp_path)))
    assert "G0" in log.waiting and sent == []


def test_demo_only_for_prompt_only(tmp_path):
    folder = tmp_path / "c"
    folder.mkdir()
    write_model_mode(folder, "TRAIN")
    with pytest.raises(FactoryError, match="PROMPT_ONLY"):
        write_demo_mode(folder, enabled=True)
    write_model_mode_prompt = tmp_path / "d"
    write_model_mode_prompt.mkdir()
    assert write_demo_mode(write_model_mode_prompt, enabled=True).enabled
    write_demo_mode(write_model_mode_prompt, enabled=False)
    assert read_demo_mode(write_model_mode_prompt) is None


def test_notify_is_quiet_without_webhook(monkeypatch):
    monkeypatch.delenv(notify_mod.WEBHOOK_ENV, raising=False)
    assert notify_mod.notify("published", "x", ["y"]).sent is False
    monkeypatch.setenv(notify_mod.WEBHOOK_ENV, "https://example.com/hook")
    assert notify_mod.notify("published", "x", ["y"]).reason == "디스코드 웹후크 주소가 아님"
