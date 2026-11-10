"""승인 영상만 재생·선택한다. 모델은 테스트 설정의 가짜 공급자만 쓴다."""

import json

import httpx
import pytest

from character_factory_poc.common import clip_pick
from tests.test_demo_chat import URL, put
from tests.test_demo_chat import setup as demo_setup  # noqa: F401


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    for name in ("TYPESAFE_API_KEY", "JEV_MODEL", "JEV_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def call(demo_setup):  # noqa: F811
    _, folder, fake, client = demo_setup
    rev = folder / "s6-actions/va10"
    rows = []
    for key in (
        "idle_good",
        "pouty_good",
        "angry_bad",
        "pose",
        "speak_good",
        "absent",
        "s2__amused_good_2",
    ):
        path = f"videos/{key} sample.mp4"
        rows.append(dict(clipKey=key, chapterId="ch1", video={"path": path}))
        if key != "absent":
            put(rev / path, key)
    rows[2].update(title="화났어요", useWhen="무례한 말을 들었을 때")
    rows.append(dict(clipKey="outside", chapterId="ch1", video={"path": "../other.mp4"}))
    put(rev.parent / "other.mp4", "outside")
    put(rev / "approved-actions.json", {"clips": rows})
    for version, file in (("va2", "approved-actions.json"), ("va11", "clips.json")):
        put(rev.parent / version / file, {"clips": []})
    return client, fake


def test_inventory(call):
    client, fake = call
    result = client.get(URL + "/clips").json()
    assert result["ready"] and result["chapter"] == "ch1"
    assert result["idle"]["bad"] is None
    assert result["idle"]["good"]["clipKey"] == "idle_good"
    first, second, variant = result["emotion"]
    assert variant["useWhen"] and variant["clipKey"] == "s2__amused_good_2"
    assert first["clipKey"] == "pouty_good" and first["useWhen"] and first["title"]
    assert second["mood"] == "bad" and second["title"] == "화났어요"
    assert second["useWhen"] == "무례한 말을 들었을 때"
    assert [r["clipKey"] for r in result["special"]] == ["pose"]
    video = client.get(first["url"])
    assert video.json() == "pouty_good" and video.headers["content-type"] == "video/mp4"
    assert not client.get(URL + "/clips?chapter=ch2").json()["ready"]
    assert (
        client.post(
            URL + "/clip", json=dict(userMessage="안녕", replyText="네", chapter="ch2")
        ).json()["kind"]
        == "none"
    )
    assert not fake.requests


@pytest.mark.parametrize(
    ("text", "recent", "expected"),
    [
        ("1위: none", [], None),
        ("1위: pouty_good 99\n2위: angry_bad 30", [], "pouty_good"),
        ("1위: pouty_good 99\n2위: angry_bad 30", ["pouty_good"], "angry_bad"),
        ("1위: pouty_good", ["pouty_good", "pouty_good"], "pouty_good"),
        ("1위: pouty_good", ["angry_bad", *(["pouty_good"] * 3)], None),
        ("1위: pouty_good\n2위: angry_bad", ["pouty_good", "angry_bad"], None),
        (
            "1위: pouty_good 90\n2위: angry_bad 89",
            ["pouty_good", "pose", "angry_bad"],
            "pouty_good",
        ),
        ("엉뚱한 답 pouty_good 이에요", [], None),
        ("1위: pose 100", [], None),
        (
            "1위: pouty_good 99\n2위: angry_bad 90\n3위: s2__amused_good_2 75",
            ["pouty_good", "angry_bad"],
            "s2__amused_good_2",
        ),
        (lambda _: (_ for _ in ()).throw(TimeoutError()), [], None),
    ],
)
def test_followup(call, text, recent, expected):
    client, fake = call
    fake.add("*", text)
    result = client.post(
        URL + "/clip", json=dict(userMessage="왜 그래?", replyText="나 삐졌어.", recent=recent)
    ).json()
    if expected:
        assert result["clip"]["clipKey"] == expected and result["kind"] == "emotion"
        assert result["mood"] == result["clip"]["mood"]
        assert set(result["clip"]) == {"clipKey", "url", "title", "mood"}
    else:
        assert result == dict(kind="none", clip=None, mood=None)
    (req,) = fake.requests
    prompt, context = req.messages
    assert "무례한 말을 들었을 때" in prompt.content and "pose" not in prompt.content
    assert context.content == "유저: 왜 그래?\n캐릭터가 방금 한 말: 나 삐졌어."


@pytest.mark.parametrize(
    ("answer", "recent", "expected"),
    [
        ({"pouty_good": 0.7, "angry_bad": 0.2, "none": 0.1}, [], "pouty_good"),
        ({"pouty_good": 0.7, "angry_bad": 0.2}, ["pouty_good"], "angry_bad"),
        ({"none": 0.6, "pouty_good": 0.4}, [], None),
        ({"outside": 0.9, "pouty_good": 0.08}, [], "pouty_good"),
        ({"angry_bad": 0.97, "pouty_good": 0.01}, ["angry_bad"], "angry_bad"),
        (500, [], None),
    ],
)
def test_jev(call, monkeypatch, answer, recent, expected):
    client, fake = call
    seen = []

    def handle(request):
        seen.append(request)
        if answer == 500:
            return httpx.Response(500)
        return httpx.Response(200, json={"answers": {"clip": {"probabilities": answer}}})

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(clip_pick, "_http", httpx.Client(transport=httpx.MockTransport(handle)))
    result = client.post(
        URL + "/clip", json=dict(userMessage="왜 그래?", replyText="나 삐졌어.", recent=recent)
    ).json()
    assert (result["clip"] or {}).get("clipKey") == expected
    assert not fake.requests
    (request,) = seen
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    question = body["questions"]["clip"]
    assert body["model"] == "jev-latest" and question["type"] == "choice"
    assert body["state"] == "유저: 왜 그래?\n캐릭터가 방금 한 말: 나 삐졌어."
    assert "1위" not in question["instructions"] and "속뜻" in question["instructions"]
    assert "pose" not in question["criteria"] and "none" in question["criteria"]
    assert "무례한 말을 들었을 때" in question["criteria"]["angry_bad"]
