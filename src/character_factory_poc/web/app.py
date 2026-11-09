"""워크숍 웹앱 (PoC 계획서 §6).

맥에서 도는 로컬 서버다. 로그인은 없다. 읽기 API, 관문 결정(cfp gate import와 같은 경로),
작업 큐, SSE, 시안 화면 서빙을 한 앱에 모은다.
"""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.web import reads
from character_factory_poc.web.demo_chat import install_demo_routes
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.events import EventHub, format_sse
from character_factory_poc.web.jobs import JobManager
from character_factory_poc.web.settings import load_settings

GATE_DECISIONS = {"APPROVE", "REJECT", "REQUEST_CHANGES", "SELECT"}
PAID_PLAN_STAGES = {"s5", "s6", "s10"}
_TEXT_TYPES = {"text/html", "text/css", "text/plain", "text/markdown", "application/json"}


class _DevStaticFiles(StaticFiles):
    """화면 파일을 고칠 때 브라우저가 옛 JS·CSS를 계속 쓰지 않게 no-store로 보낸다."""

    async def get_response(self, path: str, scope: Any):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


class _StudioStaticFiles(_DevStaticFiles):
    """Serve the visual surface without publishing plans, logs, or local work."""

    async def get_response(self, path: str, scope: Any):
        name = path.strip("/")
        allowed_html = {
            "",
            ".",
            "index.html",
            "factory.html",
            "sources.html",
            "chat.html",
            "d-ops.html",
            "c-glass.html",
            "a-studio.html",
            "b-editorial.html",
            "help.html",
        }
        if name not in allowed_html and not name.startswith(
            ("shared/", "assets/", "previews/", "recordings/")
        ):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await super().get_response(path, scope)


def create_app(
    root: Path, config_path: Path | None = None, *, runner=None, jobs_dir: Path | None = None
) -> FastAPI:
    """공장 루트 하나에 붙는 워크숍 앱을 만든다. runner는 시험에서 작업 실행 함수를 바꿀 때 쓴다."""
    root = Path(root).expanduser().resolve()
    conf = load_settings(root, config_path)
    root = conf.root
    if jobs_dir is not None:
        conf = replace(conf, jobs_dir=Path(jobs_dir))
    hub = EventHub()
    jobs = JobManager(root, conf, hub, runner=runner)
    app = FastAPI(
        title="캐릭터 공장 워크숍",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.root = root
    app.state.settings = conf
    app.state.hub = hub
    app.state.jobs = jobs
    from character_factory_poc.web.sources import install_source_routes

    install_source_routes(app, conf, jobs)
    install_demo_routes(app, root, conf)
    from character_factory_poc.web.trait_authoring import install_authoring_routes

    install_authoring_routes(app, root, conf, jobs)
    from character_factory_poc.web.text_pipeline import install_text_pipeline_routes

    install_text_pipeline_routes(app, root, conf, jobs)
    from character_factory_poc.web.runtime import install_runtime_routes

    install_runtime_routes(app, root, conf, jobs)

    @app.exception_handler(WebError)
    async def _web_error(_request: Request, exc: WebError) -> JSONResponse:  # pragma: no cover
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    # ---- 읽기 ----

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "time": reads.now_iso(),
            "root": str(root),
            "config": conf.as_dict(),
            "counts": reads.health_snapshot(root),
            "jobs": {"active": len(jobs.active_jobs())},
            "sse": {"subscribers": hub.subscriber_count()},
        }

    @app.get("/api/projects")
    def projects() -> dict[str, Any]:
        data = reads.list_projects(root)
        for character in data["characters"]:
            character["job"] = jobs.active_for(character["id"])
            recent = jobs.list(character_id=character["id"], limit=1)
            character["lastJob"] = recent[0] if recent else None
            # 개요·받은 일이 모든 캐릭터의 유료 확인 대기를 상세 화면과 같은 기준으로 센다.
            character["held"] = _held(character["id"], character["lastJob"])
        data["totals"]["runningJobs"] = len(jobs.active_jobs())
        data["jobs"] = jobs.list(limit=20)
        return data

    @app.get("/api/characters/{character_id}")
    def character(character_id: str) -> dict[str, Any]:
        data = reads.character_detail(root, character_id)
        data["job"] = jobs.active_for(character_id)
        data["jobs"] = jobs.list(character_id=character_id, limit=10)
        data["lastJob"] = data["jobs"][0] if data["jobs"] else None
        data["held"] = _held(character_id, data["lastJob"])
        data["modelPath"] = _model_path(character_id)
        return data

    def _model_path(character_id: str) -> dict[str, Any]:
        from character_factory_poc.web.model_path import model_path

        char_dir = reads.character_dir(root, character_id)
        return model_path(char_dir, reads.read_state(char_dir)[0])

    @app.get("/api/characters/{character_id}/model-path")
    def model_path_view(character_id: str) -> dict[str, Any]:
        """모델 만들기 화면: 재료 → 데이터셋 → 학습 → 평가(D-0130). 읽기만 한다."""
        return _model_path(character_id)

    @app.post("/api/characters/{character_id}/training/stop", status_code=202)
    def training_stop(character_id: str) -> dict[str, Any]:
        """도는 학습을 멈춘다. drive가 다음 확인 때 GPU를 반납하고 끝낸다(D-0130)."""
        from character_factory_poc.stages.s10_train.io import request_stop
        from character_factory_poc.web.model_path import _latest

        active = jobs.active_for(character_id)
        if not active or active.get("action") != "train":
            raise WebError(409, "지금 도는 학습이 없어요")
        rev = _latest(reads.character_dir(root, character_id) / "s10-train", "tr")
        if rev is None:
            raise WebError(409, "학습 기록이 없어요")
        request_stop(rev, reads.now_iso())
        return {"stopRequested": True, "rev": rev.name, "job": active.get("jobId")}

    @app.post("/api/characters/{character_id}/training/release")
    def training_release(character_id: str) -> dict[str, Any]:
        """결과 받기에 실패해 남겨 둔 GPU를 결과를 버리고 반납한다(D-0130)."""
        from character_factory_poc.providers.training.errors import TrainingError
        from character_factory_poc.stages.s10_train.drive import cleanup_s10t
        from character_factory_poc.stages.s10_train.io import ensure_failed, read_run, write_run
        from character_factory_poc.web.model_path import _latest, training_view

        char_dir = reads.character_dir(root, character_id)
        if jobs.active_for(character_id):
            raise WebError(
                409, "작업이 도는 중이라 반납할 수 없어요. 작업이 끝난 뒤 다시 눌러 주세요"
            )
        if training_view(char_dir, reads.read_state(char_dir)[0])["state"] != "hold":
            raise WebError(409, "반납할 GPU나 받지 못한 결과가 없어요")
        ctx = Context(config=load_config(root, conf.config_path), execute=True)
        with jobs.locks.hold(character_id):
            try:
                removed = cleanup_s10t(ctx, character_id)
            except (TrainingError, FactoryError) as exc:
                raise WebError(502, f"GPU를 반납하지 못했어요: {exc}") from exc
            rev = _latest(char_dir / "s10-train", "tr")
            for path in sorted(rev.glob("*/training-run.json")) if rev else []:
                run = read_run(path)
                if run.appliedConfig.get("collectPending") or run.status not in {
                    "FAILED",
                    "CANCELLED",
                    "SUCCEEDED",
                }:
                    applied = {k: v for k, v in run.appliedConfig.items() if k != "collectPending"}
                    applied["error"] = "사람이 결과를 버리고 GPU를 반납했다"
                    write_run(
                        path,
                        run.model_copy(
                            update={
                                "status": "CANCELLED",
                                "appliedConfig": applied,
                                "modelBinding": None,
                            }
                        ),
                    )
            if rev is not None:
                ensure_failed(ctx.state(character_id), rev.name, "결과를 버리고 GPU를 반납했다")
        jobs.publish_state(character_id, force=True)
        return {"released": removed}

    def _held(character_id: str, last_job: dict[str, Any] | None) -> list[dict[str, Any]]:
        """마지막 작업이 실행 확인을 기다리게 둔 유료 단계(D-0049, LLD §6.7)."""
        if not last_job or not last_job.get("held"):
            return []
        from character_factory_poc.pipeline.scheduler import paid_providers

        ctx = Context(config=load_config(root, conf.config_path), execute=False)
        state = reads.read_state(reads.character_dir(root, character_id))[0]
        stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
        out = []
        for sid in last_job["held"]:
            status = (stages.get(sid) or {}).get("status", "PENDING")
            if status in {"APPROVED", "AWAITING_HUMAN", "SKIPPED"}:
                continue
            providers = paid_providers(ctx, sid) or (["gpu: vast"] if sid == "s10" else [])
            out.append({"stage": sid, "providers": providers})
        return out

    @app.get("/api/characters/{character_id}/gates/{gate}")
    def gate(character_id: str, gate: str) -> dict[str, Any]:
        return reads.gate_view(root, character_id, gate)

    @app.get("/api/characters/{character_id}/stages/{stage}/plan")
    def stage_plan(character_id: str, stage: str) -> dict[str, Any]:
        """유료 단계(S5·S6) 실행 전 호출 수와 예상 비용(D-0129). 계획만 세우고 부르지 않는다."""
        if stage not in PAID_PLAN_STAGES:
            raise WebError(404, f"예상 비용을 계산하는 단계가 아니다: {stage}")
        reads.character_dir(root, character_id)
        ctx = Context(config=load_config(root, conf.config_path), execute=False)
        pcfg = ctx.config.provider("video")
        out: dict[str, Any] = {
            "stage": stage,
            "plans": [],
            "estUsd": None,
            "adapter": pcfg.adapter,
            "model": pcfg.model,
            "unitPrices": dict(pcfg.extra.get("price_per_second") or {}),
            "reason": "",
        }
        if stage == "s10":
            # 평가 GPU 비용은 평가 세트(턴 수)를 사전 등록한 뒤 정해진다. 상한만 알린다(D-0130).
            cap = float(ctx.config.stage("s10").get("gpu_budget_usd", 5.0))
            out.update(adapter="vast", model="", unitPrices={})
            out["reason"] = (
                "평가 GPU 비용은 평가 세트를 고정한 뒤 계산해요. 많아도 $"
                + format(cap, ".2f")
                + "에서 멈춰요."
            )
            return out
        try:
            if stage == "s5":
                from character_factory_poc.stages.s5_intro import run as s5

                plans = s5.plan_calls(ctx, s5.s5_config(ctx))
            else:
                from character_factory_poc.stages.s6_actions import run as s6

                plans = s6.plan_calls(ctx, s6.s6_config(ctx), character_id)
        except FactoryError as exc:
            out["reason"] = str(exc)
            return out
        rows = [
            {"description": p.description, "calls": p.calls, "estUsd": p.est_cost_usd}
            for p in plans
        ]
        out["plans"] = rows
        if all(r["estUsd"] is not None for r in rows):
            out["estUsd"] = round(sum(float(r["estUsd"]) for r in rows), 4)
        return out

    @app.get("/api/files/{character_id}/{path:path}")
    def file(character_id: str, path: str) -> FileResponse:
        target = reads.resolve_file(root, character_id, path)
        media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if media in _TEXT_TYPES or media.startswith("text/"):
            media = f"{media}; charset=utf-8"
        return FileResponse(
            target,
            media_type=media,
            headers={"Cache-Control": "no-store"},
        )

    # ---- 관문 결정 ----

    @app.post("/api/characters/{character_id}/gates/{gate}/decision")
    def decide(
        character_id: str,
        gate: str,
        body: Annotated[dict[str, Any], Body()],
    ) -> dict[str, Any]:
        if gate not in reads.decision_gates():
            raise WebError(
                404, f"관문이 없다: {gate}({', '.join(reads.decision_gates())} 중 하나다)"
            )
        answer = _clean_answer(body)
        expected_rev = answer.pop("expectedRev", None)
        if expected_rev is not None and not isinstance(expected_rev, str):
            raise WebError(400, "expectedRev는 문자열이어야 한다")
        char_dir = reads.character_dir(root, character_id)
        with jobs.locks.hold(character_id):
            state, state_error = reads.read_state(char_dir)
            if state_error:
                raise WebError(409, "진행 상태를 읽지 못해 결정을 기록할 수 없다")
            raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
            gate_state = raw_gates.get(gate) if isinstance(raw_gates.get(gate), dict) else {}
            if expected_rev is not None and gate_state.get("rev") != expected_rev:
                raise WebError(409, "검토한 revision이 바뀌었다. 최신 후보를 다시 확인한다")
            if gate_state.get("status") in {"APPROVED", "REJECTED"}:
                raise WebError(
                    409,
                    f"{gate}는 이미 결정이 기록됐다. 새 revision으로 다시 돌린 뒤 결정한다",
                )
            ctx = Context(config=load_config(root, conf.config_path), execute=True)
            try:
                output = approve_gate(ctx, character_id, gate, answer)
            except FactoryError as exc:
                raise WebError(409, str(exc)) from exc
            except ValueError as exc:
                message = str(exc)
                status = 501 if "아직 구현되지 않았다" in message else 400
                raise WebError(status, message) from exc
        detail = reads.character_detail(root, character_id)
        view = reads.gate_view(root, character_id, gate)
        hub.publish(
            "gate",
            {
                "type": "gate",
                "characterId": character_id,
                "gate": gate,
                "decision": answer["decision"],
                "recordRef": view["recordRef"],
            },
            character_id,
        )
        jobs.publish_state(character_id, force=True)
        # D-0049(LLD §6.7): 결정 뒤 의존이 풀린 갈래를 이어서 돌린다.
        resume = jobs.request_resume(character_id)
        return {
            "characterId": character_id,
            "gate": gate,
            "decision": answer["decision"],
            "output": str(output),
            "recordRef": view["recordRef"],
            "record": view["record"],
            "state": detail["state"],
            "character": detail["summary"],
            "resumeJob": resume,
        }

    # ---- 작업 큐 ----

    @app.post("/api/jobs", status_code=202)
    def start_job(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise WebError(400, "작업 본문은 JSON 객체여야 한다")
        character_id = body.get("characterId")
        if not isinstance(character_id, str) or not character_id.strip():
            raise WebError(400, "characterId가 필요하다")
        action = body.get("action", "run")
        if not isinstance(action, str):
            raise WebError(400, "action은 문자열이어야 한다")
        until = body.get("until")
        if until is not None and not isinstance(until, str):
            raise WebError(400, "until은 문자열이어야 한다")
        confirm = body.get("confirm", [])
        if not isinstance(confirm, list):
            raise WebError(400, "confirm은 단계 ID 목록이어야 한다")
        return jobs.submit(character_id.strip(), action, until, confirm=confirm)

    @app.get("/api/jobs")
    def list_jobs(
        characterId: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        return {"jobs": jobs.list(character_id=characterId, limit=limit)}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return jobs.get(job_id)

    # ---- SSE ----

    @app.get("/api/events")
    async def events(
        request: Request,
        characterId: str | None = Query(default=None),
        limit: int | None = Query(default=None),
    ) -> StreamingResponse:
        if limit is not None and not 1 <= limit <= 1000:
            raise WebError(400, "limit은 1~1000 사이여야 한다")
        heartbeat = float(conf.sse_heartbeat_s)

        async def stream():
            sub = hub.subscribe(characterId)
            sent = 0
            try:
                yield format_sse(
                    "hello",
                    {
                        "type": "hello",
                        "serverTime": reads.now_iso(),
                        "characterId": characterId,
                        "counts": reads.health_snapshot(root),
                        "jobs": jobs.active_jobs(),
                    },
                )
                sent += 1
                while limit is None or sent < limit:
                    try:
                        payload = await asyncio.wait_for(sub.queue.get(), timeout=heartbeat)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": keep-alive\n\n"
                        continue
                    yield format_sse(payload["event"], payload["data"])
                    sent += 1
            finally:
                hub.unsubscribe(sub)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers=headers,
        )

    @app.get("/api")
    def api_index() -> dict[str, Any]:
        return {
            "name": "캐릭터 공장 워크숍",
            "endpoints": [
                "GET /api/health",
                "GET /api/text-pipeline",
                "POST /api/text-pipeline/selection",
                "GET /api/text-pipeline/characters",
                "GET /api/text-pipeline/characters/{id}",
                "GET /api/projects",
                "GET /api/runtime/graph",
                "POST /api/runtime/characters",
                "GET /api/characters/{id}",
                "GET /api/characters/{id}/gates/{gate}",
                "POST /api/characters/{id}/gates/{gate}/decision",
                "GET /api/files/{id}/{path}",
                "POST /api/jobs",
                "GET /api/jobs/{jobId}",
                "GET /api/events",
                "GET /api/traits/catalog",
                "POST /api/traits/recommend",
                "GET /api/characters/{id}/seed",
                "POST /api/characters/{id}/seed",
            ],
        }

    studio_dir = conf.studio_path
    if studio_dir is not None:
        if not studio_dir.is_dir():
            raise ValueError("[web] studio_dir 폴더를 찾을 수 없다")
        app.mount(
            "/studio", _StudioStaticFiles(directory=str(studio_dir), html=True), name="studio"
        )

    static_dir = conf.static_path
    if static_dir.is_dir():
        app.mount("/", _DevStaticFiles(directory=str(static_dir), html=True), name="static")
    else:

        @app.get("/")
        def missing_static() -> dict[str, Any]:
            return {
                "detail": "화면 폴더가 없다. src/character_factory_poc/web/static을 확인한다",
                "staticDir": str(static_dir),
            }

    return app


def _clean_answer(body: Any) -> dict[str, Any]:
    """cfp gate import의 답 JSON과 같은 형식인지만 확인한다. 관문별 차이는 approve_gate가 맡는다."""
    if not isinstance(body, dict):
        raise WebError(400, "결정 본문은 JSON 객체여야 한다")
    answer = dict(body)
    for key in ("decision", "reviewer"):
        if key not in answer:
            raise WebError(400, f'결정 본문에 "{key}"가 없다(cfp gate import 답 JSON과 같은 형식)')
    if not isinstance(answer["decision"], str) or answer["decision"] not in GATE_DECISIONS:
        raise WebError(400, f"decision은 {', '.join(sorted(GATE_DECISIONS))} 중 하나다")
    if not isinstance(answer["reviewer"], str):
        raise WebError(400, "reviewer는 문자열이어야 한다")
    if "minutes" in answer:
        try:
            answer["minutes"] = float(answer["minutes"])
        except (TypeError, ValueError) as exc:
            raise WebError(400, "minutes는 숫자여야 한다") from exc
    if "reasons" in answer and not isinstance(answer["reasons"], str):
        raise WebError(400, "reasons는 문자열이어야 한다")
    for key in ("selections", "referencePreviews"):
        if key in answer:
            value = answer[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise WebError(400, f"{key}는 문자열 배열이어야 한다")
    if "requestedChanges" in answer:
        changes = answer["requestedChanges"]
        if not isinstance(changes, list) or not all(isinstance(c, dict) for c in changes):
            raise WebError(400, "requestedChanges는 {field, note} 객체 배열이어야 한다")
    return answer
