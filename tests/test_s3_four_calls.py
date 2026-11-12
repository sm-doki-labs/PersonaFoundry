"""Default motif planning: three whole-source analyses and one assembly with bounded fixes."""


from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s3_plan.twin import _assembly_sample, plan_calls, run_s3_twin
from tests.test_s3_scene_analysis import _full
from tests.test_twin_s3 import CANARY, LINES, _answer, _ready


def _s3(model):
    return [r for r in model.requests if r.stage in {"s3", "s3-twin"}]


def test_each_analyzer_reads_the_whole_generation_source_once(tmp_path):
    ctx, model, cid = _ready(tmp_path, template="FRIEND_CHAT")
    plan = plan_calls(ctx, 5318)
    assert [p.calls for p in plan] == [3, 4]  # Assembly: one pass plus up to three fixes.
    folder = run_s3_twin(ctx, cid)
    requests = _s3(model)
    analyses = [r for r in requests if "/scene-analysis/" in r.ref]
    assert len(requests) == 4 and len(analyses) == 3
    for request in analyses:
        body = _full(request)
        assert body["mode"] == "full"
        said = [
            t["text"] for s in body["segments"] for t in s["turns"] if t["speaker"] == "SUBJECT"
        ]
        assert said == [answer for _, answer in LINES]
    assert {_full(r)["dimension"] for r in analyses} == {
        "voice",
        "behavior",
        "facts-limits",
    }
    assert all(CANARY not in m.content for r in requests for m in r.messages)
    assert not (folder / "tendency-tags.json").exists()
    assert read_json(folder / "variants.json")["candidates"][0]["variantId"] == "v1"


def test_assembly_fixes_a_failed_check_in_the_same_revision(tmp_path):
    ctx, model, cid = _ready(tmp_path, template="FRIEND_CHAT")

    def wrong_background(req):
        out = _answer(req)
        out["evidence"]["background"] = out["evidence"]["job"]
        return out

    model.add("AGENT", [wrong_background, _answer])
    folder = run_s3_twin(ctx, cid)
    assembly = [r for r in _s3(model) if r.stage == "s3-twin"]
    assert folder.name == "pr1" and len(assembly) == 2
    assert "knownFacts.background" in assembly[-1].messages[-1].content


def test_assembly_never_receives_flagged_or_contact_text():
    base = {"textId": "synthetic", "convId": "scene", "speaker": "SUBJECT"}
    rows = [
        base | {"msgId": "old", "speaker": "USER", "text": "앞선 다른 상황을 묻는다."},
        base | {"msgId": "flagged", "text": "제외 표시한 원문"},
        base | {"msgId": "contact", "text": "주소는 private@example.test"},
        base | {"msgId": "accepted", "text": "상황이 달라져서 다시 결정했어요."},
    ]
    sample = _assembly_sample(rows, {"flagged"}, 20, ["flagged", "accepted"])
    assert [(row["msgId"], row["text"]) for row in sample] == [("accepted", rows[-1]["text"])]
