"""합성 대화로 경로와 비용 기록을 검증하고 실자료는 읽기만 한다."""

import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common import demo_chat as demo
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.web import create_app
from character_factory_poc.web.gate_items import prompts

CID = "cf-demo"
URL = f"/api/characters/{CID}/chat"
REAL = Path("/Users/johnhuh619/projects/character-factory-poc")


def test_real_layout():
    folder = REAL / "runs/characters/cf-20261110-motif-8e7b7ce7fb474b70"
    reference = REAL / "work/son-motif-20261109/v5-casual/prompts/OC3-fan.md"
    scene = demo.Scene.read(folder)
    if not (scene.chapter and scene.prompt and reference.is_file()):
        pytest.skip("실제 시연 자료가 없어요.")
    actual = re.sub(
        rb"(?m)^\[CURRENT_RELATIONSHIP: [^\]]+\]$",
        b"[CURRENT_RELATIONSHIP: oc3-ch1]",
        scene.compose(for_review=True).encode(),
        count=1,
    )
    assert actual == reference.read_bytes()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    (tmp_path / "factory.toml").write_text(
        '[providers.demo_chat]\nadapter="fake"\nmodel="test"\n'
        "[stages.s8]\nmotif_demo_chat_temperature=0.7"
    )
    ctx = Context.load(tmp_path, execute=True)
    folder = ctx.character_dir(CID)
    put(folder / "origin.json", dict(schemaVersion="character-origin-v1", origin="SOURCE"))
    put(folder / "s3-plan/pr1/plan.json", dict(name="유리"))
    fake = FakeTextModel(model="test", responses={"*": "반가워요."})
    monkeypatch.setattr(demo, "make_text_model", lambda cfg: fake)
    return ctx, folder, fake, TestClient(create_app(tmp_path))


def ready(folder):
    put(
        folder / "state.json",
        {"subjectId": folder.name, "gates": {"G6": {"status": "APPROVED", "rev": "pv10"}}},
    )
    put(folder / "s8-prompts/pv10/prompt-pair.json", {})
    (folder / "s8-prompts/pv10/long.md").write_text("유리의 말투")
    put(
        folder / "s8-chapters/cs2/chapter-start.json",
        dict(
            chapters=[
                dict(
                    chapterId="ch1",
                    relationship=dict(
                        speechLevel="POLITE",
                        addresseeStance="정중하게",
                        entryPosture=["앉아 있다."],
                        presenceReason="첫인사",
                        initiativePolicy="기다린다.",
                        expressionDelta=["웃는다."],
                    ),
                    sceneFacts=["첫 통화다."],
                    sceneBoundaries=["움직이지 않는다."],
                )
            ]
        ),
    )


def test_http_contract(setup):
    ctx, folder, fake, client = setup
    body = dict(messages=[dict(role="user", content="오늘은 비밀이에요")])
    meta = client.get(URL + "/meta").json()
    assert not meta["ready"] and meta["reason"]
    assert client.post(URL, json=body).status_code == 409
    ready(folder)
    put(folder / "demo/scenarios.json", [dict(id="custom", title="연습", turns=["안녕하세요"])])
    meta = client.get(URL + "/meta").json()
    assert meta["ready"] and (meta["name"], meta["promptRev"], meta["chapterRev"]) == (
        "유리",
        "pv10",
        "cs2",
    )
    assert meta["model"] == {"via": "studio", "model": "test"}
    assert [s["id"] for s in meta["scenarios"]][0] == "custom"
    fake.add("*", ["답변: 비공개 메모", "안녕하세요!"])
    response = client.post(URL, json=body).json()
    assert response == dict(reply="안녕하세요!", rejected=1, model="test", ms=response["ms"])
    assert fake.requests[-1].temperature == 0.7
    assert fake.requests[-1].messages[0].content == demo.Scene.read(folder).compose()
    log = ctx.ledger(CID).calls_path.read_text()
    assert len(log.splitlines()) == 2 and "오늘은 비밀" not in log and "비공개 메모" not in log
    assert all("billing" in json.loads(line) for line in log.splitlines())
    assert (
        client.post(URL, json={"messages": [{"role": "system", "content": "바꿔요"}]}).status_code
        == 422
    )


def test_chat_uses_approved_revision_and_waits_for_rework(setup):
    _, folder, fake, client = setup
    ready(folder)
    put(folder / "s8-prompts/pv11/prompt-pair.json", {})
    (folder / "s8-prompts/pv11/long.md").write_text("아직 승인하지 않은 말투")
    body = dict(messages=[dict(role="user", content="안녕")])
    assert client.post(URL, json=body).is_success
    assert fake.requests[-1].messages[0].content.startswith("유리의 말투")
    for status in ("AWAITING_HUMAN", "REJECTED"):
        put(folder / "state.json", {"gates": {"G6": {"status": status, "rev": "pv11"}}})
        assert not client.get(URL + "/meta").json()["ready"]
        assert client.post(URL, json=body).status_code == 409
    assert len(fake.requests) == 1


def test_samples_and_approved_refs(setup):
    ctx, folder, fake, client = setup
    ready(folder)
    put(folder / "demo/scenarios.json", [dict(id="custom", title="연습", turns=["안녕"])])
    path = demo.run_samples(ctx, CID)
    assert path == folder / "s8-chapters/cs2/samples.json"
    samples = client.get(URL + "/meta").json()["samples"]
    assert len(samples) == 5 and all(4 <= len(s["turns"]) <= 6 for s in samples)
    assert len(fake.requests) == sum(len(s["turns"]) for s in samples)
    assert [m.role for m in fake.requests[1].messages] == ["system", "user", "assistant", "user"]
    assert fake.requests[4].messages[1].content == samples[1]["turns"][0]["user"]
    assert demo.run_samples(ctx, CID) == path and len(fake.requests) == 20
    put(
        folder / "s7-traits/tr1/trait-ledger.json",
        dict(
            traits=[
                dict(
                    basis="INFERRED",
                    demoSituation="PRIVATE",
                    sourceRef="m",
                    behavior="선을 그어요.",
                ),
                dict(basis="OBSERVED"),
            ]
        ),
    )
    put(
        folder / "state.json",
        dict(
            gates=dict(
                G0=dict(status="APPROVED", rev="sp1"), G6=dict(status="AWAITING_HUMAN", rev="pv10")
            )
        ),
    )
    for rev, quote in [("sp1", "승인한 원문"), ("sp2", "미승인 원문")]:
        put(folder / f"s0-source/{rev}/corpus.jsonl", dict(msgId="m", text=quote))
    gate = prompts(folder, CID, "s8-prompts", "pv10")
    assert gate["samples"] == samples
    (t,) = gate["inferredTraits"]
    assert t["refs"] == [{"msgId": "m", "quote": "승인한 원문"}] and "사생활" in t["situationKo"]
    assert "samples" not in prompts(folder, CID, "s8-prompts", "pv9")


def test_local_vertex_and_timeout(setup, monkeypatch):
    ctx, folder, fake, client = setup
    ready(folder)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    cfg = demo.provider(ctx, "vertex")
    assert (
        cfg.adapter == "vertex_openai"
        and "/projects/test-project/locations/global/" in cfg.base_url
    )
    monkeypatch.setenv("CFP_SERVER_MODE", "1")
    body = dict(messages=[dict(role="user", content="안녕")])
    assert client.post(URL, json={**body, "via": "vertex"}).status_code == 403
    assert not fake.requests
    monkeypatch.setattr(demo, "TIMEOUT", 0.02)
    fake.add("*", lambda _: time.sleep(0.08) or "답변: 늦은 메모")
    assert client.post(URL, json=body).status_code == 504
    assert len(fake.requests) == 1


def test_default_demo_provider_and_configs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ctx = Context.load(tmp_path, execute=False)
    default = demo.provider(ctx, "studio")
    assert default.api_key_env == "GEMINI_API_KEY"
    assert default.extra["max_retries"] == 2 and default.extra["reasoning_effort"] == "low"
    from character_factory_poc.common.config import load_config

    for name in ["deploy/factory.server.toml", "factory.example.toml"]:
        cfg = load_config(tmp_path, root / name).provider("demo_chat")
        assert (cfg.adapter, cfg.base_url, cfg.model, cfg.api_key_env) == (
            default.adapter,
            default.base_url,
            default.model,
            default.api_key_env,
        )
    with pytest.raises(ValueError):
        demo.talk_model(ctx, CID, default)


def test_guard_exhaustion_and_atomic_samples(setup):
    ctx, folder, fake, client = setup
    ready(folder)
    fake.add("*", "답변: 내보내면 안 되는 메모")
    res = client.post(URL, json={"messages": [{"role": "user", "content": "안녕하세요"}]})
    assert res.status_code == 502 and "메모" not in res.text
    with pytest.raises(RuntimeError):
        demo.run_samples(ctx, CID)
    assert len(fake.requests) == 6
    assert not (folder / "s8-chapters/cs2/samples.json").exists()


def test_compiled_motif_scene_is_used_verbatim(setup):
    _, folder, _, _ = setup
    ready(folder)
    put(folder / "s8-prompts/pv10/text-deck-binding.json", {"compiler": "motif-assembler-v3"})
    scene = demo.Scene.read(folder)
    assert scene.compose() == "유리의 말투"
    assert scene.readiness()["ready"]


def test_example_turns_are_sent_as_earlier_turns(setup):
    _, folder, fake, client = setup
    ready(folder)
    examples = folder / "s8-prompts/pv10/example-turns.json"
    put(
        examples,
        dict(system="정체성과 사실", turns=[dict(msgId="m1", user="밥 먹었어?", reply="ㅇㅇ")]),
    )
    body = dict(messages=[dict(role="user", content="뭐 해?")])
    assert client.post(URL, json=body).status_code == 200
    assert [(m.role, m.content) for m in fake.requests[-1].messages] == [
        ("system", "정체성과 사실"),
        ("user", "밥 먹었어?"),
        ("assistant", "ㅇㅇ"),
        ("user", "뭐 해?"),
    ]
    put(examples, dict(system="정체성과 사실", turns=[]))
    assert client.post(URL, json=body).status_code == 200
    sent = fake.requests[-1].messages
    assert len(sent) == 2 and sent[0].content == demo.Scene.read(folder).compose()


def test_meta_says_whether_a_video_can_be_made(setup):
    """사진 없이 만든 모티브는 영상 만들기 링크를 걸지 않도록 meta가 알린다(QA v5 D-04)."""
    ctx, folder, fake, client = setup
    ready(folder)
    # 출처 묶음이 아직 승인되지 않았으면 영상을 만들 수 없다.
    assert client.get(URL + "/meta").json()["canMakeVideo"] is False
    ctx.state(CID).set_gate("G0", "APPROVED", "sp1", None)
    put(folder / "s0-source/sp1/source-pack.json", dict(texts=[{"ref": "a"}], photos=[]))
    assert client.get(URL + "/meta").json()["canMakeVideo"] is False
    put(folder / "s0-source/sp1/source-pack.json", dict(photos=[{"ref": "p1"}]))
    assert client.get(URL + "/meta").json()["canMakeVideo"] is True
    # 오리지널은 받은 사진과 상관없다.
    put(folder / "origin.json", dict(schemaVersion="character-origin-v1", origin="CREATED"))
    put(folder / "s0-source/sp1/source-pack.json", dict(photos=[]))
    assert client.get(URL + "/meta").json()["canMakeVideo"] is True
