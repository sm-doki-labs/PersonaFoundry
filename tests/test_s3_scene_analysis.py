"""Offline checks for the bounded S3 analysis boundary."""

import json
from hashlib import sha256
from threading import Barrier

import pytest

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s3_plan import scene_analysis

CID = "synthetic"
REV = "pr1"
PREFIX = f"{CID}/{REV}/scene-analysis/"
DIMENSIONS = ("voice", "behavior", "facts-limits")


def _row(source, scene, i, speaker, text, **extra):
    return dict(
        textId=source,
        convId=f"{source}-c{scene:04d}",
        msgId=f"{source}-{i:05d}",
        speaker=speaker,
        name="name-metadata-canary",
        text=text,
        **extra,
    )


def _pair(source, scene, i, **extra):
    return [
        _row(source, scene, i, "USER", f"어제 만든 종이 상자는 어디에 둘까 {i}?", **extra),
        _row(source, scene, i + 1, "SUBJECT", f"책장 아래 빈칸에 놓으면 좋겠어 {i}.", **extra),
    ]


def _ctx(tmp_path, response, mode="sample", **settings):
    ctx = Context.load(tmp_path, execute=True)
    model = FakeTextModel(responses={PREFIX + dim: response for dim in DIMENSIONS})
    model.add("AGENT", response)
    ctx.use_models(model)
    ctx.config.stages["s3t"] = {"analysis_input": mode, **settings}
    return ctx, model


def _run(ctx, folder, corpus, flagged=()):
    return scene_analysis.run(ctx, CID, REV, folder, ctx.budget(), corpus, flagged, "FRIEND_CHAT")


def _payload(req):
    return json.loads(req.messages[1].content)


def _full(req):
    """Header JSON line plus one turn per line, grouped by '## textId convId' segments."""
    head, _, body = req.messages[1].content.partition("\n\n")
    segments = []
    for line in body.splitlines():
        if line.startswith("## "):
            text_id, conv_id = line[3:].split(" ")
            segments.append({"textId": text_id, "convId": conv_id, "turns": []})
        else:
            msg_id, role, text = line.split("\t", 2)
            speaker = "SUBJECT" if role == "S" else "USER"
            segments[-1]["turns"].append({"msgId": msg_id, "speaker": speaker, "text": text})
    return json.loads(head) | {"segments": segments}


def test_large_corpus_uses_three_bounded_calls_and_balances_sources_and_scenes(tmp_path):
    corpus = []
    for scene in range(110):
        for j in range(50):
            corpus.extend(_pair("archive", scene, (scene * 50 + j) * 2))
    for scene in range(4):
        corpus.extend(_pair("small", scene, scene * 2))

    def answer(request):
        ids = [p["subject"]["msgId"] for p in _payload(request)["pairs"]]
        return {
            "observations": [
                {"description": "물건을 둘 자리를 구체적으로 제안한다.", "evidence": [ids[0]]}
            ]
        }

    ctx, model = _ctx(tmp_path, answer)
    first = tmp_path / "first"
    result = _run(ctx, first, corpus)
    requests = {r.ref.removeprefix(PREFIX): r for r in model.requests}
    assert len(model.requests) == len(requests) == 3
    assert tuple(scene_analysis.DIMENSIONS) == DIMENSIONS
    assert set(requests) == set(DIMENSIONS)
    assert {(r.stage, r.kind) for r in requests.values()} == {("s3", "AGENT")}
    snapshot = read_json(first / "scene-analysis/inputs.json")
    for dimension, request in requests.items():
        pairs = _payload(request)["pairs"]
        rebuilt = json.dumps(
            {
                "dimension": dimension,
                "scene": snapshot["scene"],
                "mode": snapshot["mode"],
                "pairs": snapshot["pairs"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert snapshot["requests"][dimension]["inputSha256"] == sha256(rebuilt).hexdigest()
        assert rebuilt == request.messages[1].content.encode("utf-8")
        assert _payload(request)["dimension"] == dimension
        assert len(request.messages[1].content.encode("utf-8")) < 32_000
        assert 4 < len(pairs) < 100
        archive_scenes = {p["convId"] for p in pairs if p["textId"] == "archive"}
        assert len(archive_scenes) >= 10
        assert max(archive_scenes) >= "archive-c0090"
        assert sum(p["textId"] == "small" for p in pairs) == 4
    evidence = _payload(requests["voice"])["pairs"][0]["subject"]["msgId"]
    assert result == {
        "observations": [
            {
                "dimension": d,
                "description": "물건을 둘 자리를 구체적으로 제안한다.",
                "evidence": [evidence],
            }
            for d in DIMENSIONS
        ],
        "priorityIds": [evidence],
    }
    assert [c["ref"] for c in sorted(ctx.ledger(CID).calls(), key=lambda c: c["ref"])] == sorted(
        PREFIX + d for d in DIMENSIONS
    )

    # Every saved phase and the input snapshot are deterministic across identical runs.
    second = tmp_path / "second"
    assert _run(ctx, second, corpus) == result
    for name in ("inputs", *DIMENSIONS):
        rel = f"scene-analysis/{name}.json"
        assert (first / rel).read_bytes() == (second / rel).read_bytes()
    with pytest.raises(ValueError, match="already"):
        _run(ctx, first, corpus)
    assert len(model.requests) == 6


def test_generation_boundaries_never_reconnect_excluded_context(tmp_path):
    corpus = [
        *_pair("ready", 1, 0),
        _row("barriers", 1, 0, "USER", "질문 경계 앞 문장"),
        _row("barriers", 1, 1, "USER", "flagged-context-canary"),
        _row("barriers", 1, 2, "SUBJECT", "disconnected-subject-canary"),
        _row("barriers", 2, 3, "USER", "prior-to-flagged-answer-canary"),
        _row("barriers", 2, 4, "SUBJECT", "flagged-subject-canary"),
        _row("barriers", 3, 5, "USER", "masked-context [전화번호]"),
        _row("barriers", 3, 6, "SUBJECT", "masked-answer-canary"),
        _row("barriers", 4, 7, "USER", "다른 대화의 마지막 줄"),
        _row("barriers", 5, 8, "SUBJECT", "cross-scene-canary"),
        *_pair("reserved", 1, 0, split="holdout"),
        *_pair("reserved", 1, 2),
        *_pair("private", 1, 0, split="private"),
        *_pair("ready", 2, 2),
    ]
    ctx, model = _ctx(tmp_path, {"observations": []})
    folder = tmp_path / "out"
    assert _run(ctx, folder, corpus, {"barriers-00001", "barriers-00004"}) == {
        "observations": [],
        "priorityIds": [],
    }
    for request in model.requests:
        pairs = _payload(request)["pairs"]
        assert {p["subject"]["msgId"] for p in pairs} == {"ready-00001", "ready-00003"}
        prior = next(p["prior"] for p in pairs if p["subject"]["msgId"] == "ready-00001")
        assert prior == {"msgId": "ready-00000", "speaker": "USER", "text": corpus[0]["text"]}
        assert "canary" not in request.messages[1].content
    assert "canary" not in (folder / "scene-analysis/inputs.json").read_text()


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"description": "제안을 구체화한다.", "evidence": ["missing"]}, "unsent"),
        ({"description": "제안을 구체화한다.", "evidence": ["scene-00000"]}, "unsent"),
        ({"description": "제안을 구체화한다.", "evidence": ["scene-00001"] * 2}, "duplicate"),
        ({"description": "문의는 person@example.org.", "evidence": ["scene-00001"]}, "unsafe"),
        ({"description": "예시: 그렇게 해!", "evidence": ["scene-00001"]}, "dialogue"),
        (
            {"description": "책장 아래 빈칸에 놓으면 좋겠어 0.", "evidence": ["scene-00001"]},
            "copied",
        ),
        (
            {"description": "전체 발화에서 80%의 비율로 이 방식.", "evidence": ["scene-00001"]},
            "frequency",
        ),
        (None, "expected description and evidence"),
    ],
)
def test_invalid_observation_is_held_without_dropping_valid_neighbor(tmp_path, response, error):
    ctx, model = _ctx(tmp_path, {"observations": []})
    description = "집안 물건을 어디에 둘지 정할 때 먼저 배치할 곳을 제안한다."
    valid = {"description": description, "evidence": ["scene-00001"]}
    model.add(PREFIX + "behavior", {"observations": [response, valid]})
    folder = tmp_path / "out"
    result = _run(ctx, folder, _pair("scene", 1, 0))
    assert result == {
        "observations": [{"dimension": "behavior", **valid}],
        "priorityIds": ["scene-00001"],
    }
    assert len(model.requests) == 3
    phase = read_json(folder / "scene-analysis/behavior.json")
    assert phase["status"] == "ok"
    assert phase["rejections"][0]["index"] == 0
    assert error in phase["rejections"][0]["reason"]
    assert phase["responseSha256"]
    assert "person@example.org" not in json.dumps(phase)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ('{"observations":[]} trailing text', "invalid JSON"),
        ('{"observations":[],"observations":[]}', "invalid JSON"),
        ({"observations": None}, "observations list"),
    ],
)
def test_malformed_envelope_fails_and_preserves_other_phase_outcomes(tmp_path, response, error):
    ctx, model = _ctx(tmp_path, {"observations": []})
    model.add(PREFIX + "behavior", response)
    folder = tmp_path / "out"
    with pytest.raises(ValueError, match=rf"behavior.*{error}"):
        _run(ctx, folder, _pair("scene", 1, 0))
    assert len(model.requests) == 3  # one attempt per dimension, even if one envelope is malformed
    failed = read_json(folder / "scene-analysis/behavior.json")
    assert failed["status"] == "invalid"
    assert error in failed["error"]
    assert failed["responseSha256"]
    assert read_json(folder / "scene-analysis/voice.json")["observations"] == []
    assert read_json(folder / "scene-analysis/facts-limits.json")["observations"] == []


def test_independent_dimensions_can_overlap_under_provider_capacity(tmp_path):
    rendezvous = Barrier(3, timeout=5)

    def answer(_request):
        rendezvous.wait()
        return {"observations": []}

    ctx, model = _ctx(tmp_path, answer)
    ctx.config.orchestrator["provider_limits"] = {"text": 3}
    assert _run(ctx, tmp_path / "out", _pair("scene", 1, 0))["observations"] == []
    assert len(model.requests) == 3


def test_full_mode_gives_every_eligible_turn_to_each_analyzer_once(tmp_path):
    corpus = []
    for scene in range(30):
        for j in range(20):
            corpus.extend(_pair("archive", scene, (scene * 20 + j) * 2))
    flagged = {corpus[5]["msgId"]}
    subjects = [
        r["msgId"] for r in corpus if r["speaker"] == "SUBJECT" and r["msgId"] not in flagged
    ]
    ctx, model = _ctx(tmp_path, {"observations": []}, mode="full")
    _run(ctx, tmp_path, corpus, flagged)
    assert len(model.requests) == 3
    for req in model.requests:
        body = _full(req)
        sent = [
            t["msgId"] for s in body["segments"] for t in s["turns"] if t["speaker"] == "SUBJECT"
        ]
        assert body["mode"] == "full" and body["format"] == "lines" and sent == subjects
        assert all(t["msgId"] not in flagged for s in body["segments"] for t in s["turns"])
        # A removed row is a boundary: turns on either side are never joined into one segment.
        around = [s for s in body["segments"] if s["convId"] == corpus[5]["convId"]]
        assert len(around) == 2


def test_full_mode_splits_only_past_the_input_limit(tmp_path):
    corpus = []
    for scene in range(40):
        corpus.extend(_pair("archive", scene, scene * 2))
    ctx, model = _ctx(tmp_path, {"observations": []}, mode="full", analysis_max_chars=1500)
    _run(ctx, tmp_path, corpus)
    parts = {}
    for req in model.requests:
        body = _full(req)
        ids = [t["msgId"] for s in body["segments"] for t in s["turns"]]
        parts.setdefault(body["dimension"], []).extend(ids)
    assert len(model.requests) > 3 and len(model.requests) % 3 == 0
    everything = [r["msgId"] for r in corpus]
    assert all(sorted(ids) == sorted(everything) for ids in parts.values())
