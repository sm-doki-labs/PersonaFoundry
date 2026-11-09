"""승인 영상만 재생·선택한다. 모델은 테스트 설정의 가짜 공급자만 쓴다."""

import pytest

from tests.test_demo_chat import URL, put
from tests.test_demo_chat import setup as demo_setup  # noqa: F401


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
