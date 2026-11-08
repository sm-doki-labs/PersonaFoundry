"""시험 경로 2번(교차 태깅·외모군·베이스 시드) 오프라인 시험. 네트워크 없음."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.testpath import seeds as sd
from character_factory_poc.testpath.image_api import ImageResult
from character_factory_poc.testpath.tagging import cross_check
from character_factory_poc.testpath.vocab2 import UNKNOWN, all_field_names, load_vocab2

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
NAMES = [f"가상인물{i:02d}" for i in range(1, 13)]
ARCHETYPES = [
    {
        "faceShape": "oval",
        "eyeShape": "large-double",
        "hairLength": "long",
        "hairColor": "black",
        "skinTone": "fair",
        "featureIntensity": "soft",
        "vibe": ["innocent"],
        "eyelid": "double",
        "makeup": "natural",
        "noseBridge": "medium",
        "ageImpression": "early-20s",
    },
    {
        "faceShape": "small-v",
        "eyeShape": "upturned",
        "hairLength": "medium",
        "hairColor": "ash",
        "skinTone": "light",
        "featureIntensity": "striking",
        "vibe": ["chic", "girl-crush"],
        "eyelid": "inner-double",
        "makeup": "smoky",
        "noseBridge": "high",
        "ageImpression": "mid-20s",
    },
    {
        "faceShape": "round",
        "eyeShape": "round",
        "hairLength": "bob",
        "hairColor": "light-brown",
        "skinTone": "fair",
        "featureIntensity": "balanced",
        "vibe": ["lovely", "playful"],
        "eyelid": "double",
        "makeup": "blush",
        "noseBridge": "low",
        "ageImpression": "youthful",
    },
]


def _ranking() -> dict:
    lists = []
    for li, chunk in enumerate((NAMES[:6], NAMES[6:])):
        lists.append(
            {
                "listId": f"fake-list-{li}",
                "source": "가짜",
                "category": "여자 아이돌",
                "period": "2026-10",
                "entries": [{"rank": r, "name": n} for r, n in enumerate(chunk, 1)],
            }
        )
    return {
        "schemaVersion": "popularity-ranking-v2",
        "scope": {
            "characterGender": "female",
            "ageRange": "20-29",
            "artStyle": "photorealistic",
            "appearanceOrigin": "korean",
        },
        "lists": lists,
    }


def _tagger(variant: str):
    vocab = load_vocab2()

    def respond(req) -> str:
        user = req.messages[-1].content
        pids = re.findall(r"- (p\d{3}): ", user)
        people = []
        for pid in pids:
            n = int(pid[1:])
            arch = ARCHETYPES[(n - 1) % 3]
            tags = {f: arch.get(f, UNKNOWN) for f in all_field_names(vocab) if f != "vibe"}
            tags["vibe"] = arch["vibe"]
            if variant == "b" and n == 1:
                tags["eyelid"] = "monolid"  # 한 칸 불일치
            gender = "male" if (variant == "b" and n == 12) else "female"
            people.append(
                {
                    "personId": pid,
                    "recognized": True,
                    "gender": gender,
                    "tags": tags,
                    "confidence": {f: 0.8 for f in tags},
                }
            )
        return json.dumps({"people": people})

    return FakeTextModel(model=f"fake-{variant}", responses={"*": respond})


class FakeImages:
    model = "fake-image"

    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt, *, size, quality, complexity=None):
        self.prompts.append(prompt)
        return ImageResult(data=PNG, elapsed_ms=1, usage={"total_tokens": 1})


@pytest.fixture
def cfg(tmp_path: Path) -> sd.SeedRunConfig:
    run = tmp_path / "run"
    (run / "ranking").mkdir(parents=True)
    (run / "ranking" / "ranking.json").write_text(
        json.dumps(_ranking(), ensure_ascii=False), "utf-8"
    )
    return sd.SeedRunConfig(run_dir=run, batch_size=5)


def test_seed_flow_end_to_end(cfg):
    sd.step_people(cfg)
    sd.step_tags(cfg, {"gpt": _tagger("a"), "gemini": _tagger("b")})
    merged = json.loads((cfg.run_dir / "tags-merged.json").read_text("utf-8"))
    assert merged["stats"]["kept"] == 11  # p012는 성별 불일치로 빠진다
    assert merged["merged"]["p001"]["tags"]["eyelid"] == UNKNOWN
    assert merged["stats"]["agreement"]["eyelid"]["agreed"] == 10

    sd.step_clusters(cfg)
    clusters = json.loads((cfg.run_dir / "clusters.json").read_text("utf-8"))
    assert len(clusters["clusters"]) == 3
    assert sum(a["count"] for a in clusters["allocation"]) == 10
    assert all(set(c["members"]) for c in clusters["clusters"])

    sd.step_prompts(cfg)
    plan = json.loads((cfg.run_dir / "seeds" / "plan.json").read_text("utf-8"))
    assert len(plan["seeds"]) == 10
    text = "\n".join(s["prompt"] for s in plan["seeds"])
    assert not any(n in text for n in NAMES)
    assert "smoky eye" in text and "fictional adult Korean woman" in text

    images = FakeImages()
    sd.step_images(cfg, images)
    assert len(images.prompts) == 10
    assert len(list((cfg.run_dir / "seeds" / "images").glob("s*.png"))) == 10
    assert (cfg.run_dir / "seeds" / "gallery.html").is_file()
    sd.step_images(cfg, images)  # 이미 있는 파일은 다시 만들지 않는다
    assert len(images.prompts) == 10


def test_prompt_step_stops_on_name_leak(cfg):
    pass


def test_signatures_are_distinct_and_set_expression(cfg):
    cfg.signatures = True
    cfg.look = "beauty"
    sd.step_people(cfg)
    sd.step_tags(cfg, {"gpt": _tagger("a"), "gemini": _tagger("a")})
    sd.step_clusters(cfg)
    sd.step_prompts(cfg)
    plan = json.loads((cfg.run_dir / "seeds" / "plan.json").read_text("utf-8"))
    keys = [s["tags"]["signature"] for s in plan["seeds"]]
    assert len(set(keys)) == 10
    tooth = next(s for s in plan["seeds"] if s["tags"]["signature"] == "snaggletooth")
    assert (
        "Signature detail" in tooth["prompt"] and "showing a little of her teeth" in tooth["prompt"]
    )
    assert "official profile photo" in tooth["prompt"]


def test_prompt_step_stops_on_name_leak_v2(cfg):
    sd.step_people(cfg)
    sd.step_tags(cfg, {"gpt": _tagger("a"), "gemini": _tagger("a")})
    sd.step_clusters(cfg)
    path = cfg.run_dir / "clusters.json"
    data = json.loads(path.read_text("utf-8"))
    data["clusters"][0]["label"] = NAMES[0] + " 느낌"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    with pytest.raises(RuntimeError):
        sd.step_prompts(cfg)


def test_cross_check_drops_unrecognized():
    vocab = load_vocab2()
    tags = {f: UNKNOWN for f in all_field_names(vocab)}
    tags["vibe"] = []
    row = {
        "recognized": True,
        "gender": "female",
        "tags": dict(tags),
        "confidence": {f: 1.0 for f in tags},
    }
    a = {"p001": row, "p002": row}
    b = {"p001": {**row, "recognized": False}, "p002": row}
    merged, stats = cross_check(a, b, vocab)
    assert list(merged) == ["p002"]
    assert stats["dropped"]["p001"] == "한 모델 이상이 모름"
