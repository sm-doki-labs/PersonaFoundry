"""Real studio entry point and runtime graph use the existing workshop engine."""

from fastapi.testclient import TestClient

from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.web.app import create_app


def test_real_studio_runtime_routes_are_installed_without_starting_jobs(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        graph = client.get("/api/runtime/graph")
        assert graph.status_code == 200
        assert graph.json()["mode"] == "live"
        assert {s["id"] for s in graph.json()["stages"]} == set(STAGES)
        assert client.get("/api/jobs").json()["jobs"] == []
        assert client.get("/api/projects").json()["characters"] == []


def test_creator_request_is_saved_but_not_executed_on_open(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/runtime/characters",
            json={
                "slug": "studio-integration",
                "brief": "말수가 적고 도구를 고쳐 쓰는 성인 정비사.",
            },
        )
        assert response.status_code == 201, response.text
        cid = response.json()["characterId"]
        assert client.get("/api/jobs").json()["jobs"] == []
        assert client.get(f"/api/characters/{cid}").json()["pendingGates"] == []
        assert (
            tmp_path / "runs/characters" / cid / "creator-input/brief-r1.md"
        ).read_text().strip() == "말수가 적고 도구를 고쳐 쓰는 성인 정비사."
        assert client.get("/api/projects").json()["characters"][0]["id"] == cid


def test_saved_request_real_queue_rework_and_approval_reach_g6(tmp_path, monkeypatch):
    """Exercise the default JobManager runner, not a UI-only fake state machine."""
    import hashlib
    import time

    import character_factory_poc.web.jobs as jobs_module
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.providers.fake_codex import FakeCodexAgent
    from tests.support.flow import make_ctx
    from tests.test_agentic import BRIEF, _writer

    ctx, _ = make_ctx(
        tmp_path,
        """
[agent]
backend="codex_exec"
model="fake"
[providers.text]
adapter="fake"
model="fake-author"
[providers.judge]
adapter="fake"
model="fake-judge"
[orchestrator]
max_parallel=3
auto_resume=true
resume_until="G6"
""",
    )
    ctx.use_codex(FakeCodexAgent(writer=_writer))
    text = FakeTextModel(model="fake-author")
    text.add("PROBE", lambda req: "응, 같이 해 보자.")
    judge = FakeTextModel(model="fake-judge")
    judge.add("JUDGE", {"pick": "B", "reasons": "합성 검사"})
    ctx.use_models(text, judge)
    monkeypatch.setattr(jobs_module, "Context", lambda **kwargs: ctx)

    def idle(client, cid):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            data = client.get(f"/api/characters/{cid}").json()
            if not data["job"]:
                assert data["lastJob"]["status"] == "succeeded", data["lastJob"]
                return data
            time.sleep(0.02)
        raise AssertionError("real queue did not settle")

    with TestClient(create_app(tmp_path)) as client:
        created = client.post(
            "/api/runtime/characters", json={"slug": "real-queue", "brief": BRIEF}
        )
        assert created.status_code == 201, created.text
        cid = created.json()["characterId"]
        assert client.post("/api/jobs", json={"characterId": cid, "until": "G6"}).status_code == 202
        detail = idle(client, cid)
        assert {g["id"] for g in detail["pendingGates"]} == {"G3"}
        # D-0080: 브리프 등록도 씨앗 → 변형 경로라 G3 전에는 variants.json이 고정본이다.
        first = ctx.character_dir(cid) / "s3-plan/pr1/variants.json"
        old_hash = hashlib.sha256(first.read_bytes()).hexdigest()
        changed = client.post(
            f"/api/characters/{cid}/gates/G3/decision",
            json={
                "decision": "REQUEST_CHANGES",
                "requestedChanges": [{"field": "job", "note": "직업 설명을 구체화"}],
                "reviewer": "integration-test",
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["resumeJob"]
        detail = idle(client, cid)
        assert next(s for s in detail["stages"] if s["id"] == "s3")["rev"] == "pr2"
        assert hashlib.sha256(first.read_bytes()).hexdigest() == old_hash
        stale = client.post(
            f"/api/characters/{cid}/gates/G3/decision",
            json={"decision": "APPROVE", "reviewer": "stale-tab", "expectedRev": "pr1"},
        )
        assert stale.status_code == 409, stale.text
        assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
        approved = client.post(
            f"/api/characters/{cid}/gates/G3/decision",
            json={
                "decision": "APPROVE",
                "reviewer": "integration-test",
            },
        )
        assert approved.status_code == 200, approved.text
        detail = idle(client, cid)
        assert "G6" in {g["id"] for g in detail["pendingGates"]}
        assert next(s for s in detail["stages"] if s["id"] == "s8")["rev"] == "pv1"
        assert detail["lastJob"]["trigger"] == "gate"
        assert client.get(f"/api/characters/{cid}/gates/G6").json()["synthetic"] is False
        assert (
            client.get(f"/api/events?characterId={cid}&limit=1")
            .headers["content-type"]
            .startswith("text/event-stream")
        )
        assert (
            client.post(
                f"/api/characters/{cid}/gates/G3/decision",
                json={"decision": "APPROVE", "reviewer": "integration-test"},
            ).status_code
            == 409
        )
    # A new app instance recovers the same stored revision and request, without submitting anything.
    with TestClient(create_app(tmp_path)) as client:
        restored = client.get(f"/api/characters/{cid}").json()
        assert restored["job"] is None
        assert "G6" in {g["id"] for g in restored["pendingGates"]}
        assert Context.load(tmp_path, execute=False).character_dir(cid) == ctx.character_dir(cid)


def test_runtime_lanes_come_from_the_workshop_read_model(tmp_path):
    from character_factory_poc.web.reads import LANES

    with TestClient(create_app(tmp_path)) as client:
        payload = client.get("/api/runtime/graph").json()
        assert payload["lanes"] == [
            {"id": lane["id"], "label": lane["label"], "stages": list(lane["stages"])}
            for lane in LANES
        ]
