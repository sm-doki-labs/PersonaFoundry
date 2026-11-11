"""Local creator input and optional trait selection; no model calls or gate approvals."""

from typing import Literal

from fastapi import FastAPI
from pydantic import Field

from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.common import Strict
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.seed import SeedConflict, load_latest_seed, write_seed
from character_factory_poc.stages.s3_plan.trait_recommendations import (
    catalog_view,
    recommend_traits,
    resolve_traits,
)
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError


class SeedFields(Strict):
    personality: str = Field(min_length=1, max_length=5000)
    job: str = Field(default="", max_length=1000)
    age: int | None = Field(default=None, ge=18, le=150)
    gender: Literal["female", "male", "other"] | None = None
    background: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=5000)


class SaveSeed(Strict):
    fields: SeedFields
    selectedIds: list[str] = Field(default_factory=list, max_length=5)
    expectedSeedRev: str | None = Field(default=None, pattern=r"^sd\d+$")
    catalogSha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RecommendTraits(Strict):
    personality: str = Field(default="", max_length=5000)
    selectedIds: list[str] = Field(default_factory=list, max_length=5)
    dismissedIds: list[str] = Field(default_factory=list, max_length=144)
    search: str = Field(default="", max_length=200)
    limit: int = Field(default=5, ge=1, le=5, strict=True)


def install_authoring_routes(app: FastAPI, root, conf, jobs) -> None:
    def context():
        return Context(config=load_config(root, conf.config_path), execute=False)

    def editable(cid):
        char = reads.character_dir(root, cid)
        state, error = reads.read_state(char)
        if error:
            return False, "캐릭터 진행 상태를 읽지 못했습니다. 상태 파일을 먼저 확인해 주세요."
        status = (state.get("stages", {}).get("s3") or {}).get("status", "PENDING")
        if status in {"RUNNING", "APPROVED", "AWAITING_HUMAN"} or jobs.active_for(cid):
            return False, "현재 기획을 검토하거나 수정 요청을 남긴 뒤 기본 설정을 바꿀 수 있습니다."
        return True, ""

    @app.get("/api/traits/catalog")
    def get_catalog():
        return catalog_view()

    @app.post("/api/traits/recommend")
    def recommend(body: RecommendTraits):
        try:
            return recommend_traits(
                body.personality,
                selected_ids=body.selectedIds,
                dismissed_ids=body.dismissedIds,
                search=body.search,
                limit=body.limit,
            )
        except ValueError as exc:
            raise WebError(400, str(exc)) from exc

    @app.get("/api/characters/{cid}/seed")
    def get_seed(cid: str):
        can_edit, reason = editable(cid)
        seed = load_latest_seed(context(), cid)
        return {"seed": dump(seed) if seed else None, "editable": can_edit, "reason": reason}

    @app.post("/api/characters/{cid}/seed")
    def save_seed(cid: str, body: SaveSeed):
        reads.character_dir(root, cid)
        with jobs.locks.hold(cid):
            can_edit, reason = editable(cid)
            if not can_edit:
                raise WebError(409, reason)
            ctx = context()
            old = load_latest_seed(ctx, cid)
            if (old.seedRev if old else None) != body.expectedSeedRev:
                raise WebError(
                    409, "다른 화면에서 설정이 바뀌었습니다. 최신 설정을 다시 불러와 주세요."
                )
            if body.selectedIds and not body.catalogSha256:
                raise WebError(400, "추천 목록을 먼저 불러와 주세요.")
            try:
                selected = resolve_traits(body.selectedIds, catalog_sha=body.catalogSha256)
            except ValueError as exc:
                code = 409 if "카탈로그" in str(exc) else 400
                raise WebError(code, str(exc)) from exc
            try:
                seed = write_seed(
                    ctx,
                    cid,
                    dict(dump(body.fields), selectedTraits=[dump(t) for t in selected]),
                    expected_seed_rev=body.expectedSeedRev,
                )
            except SeedConflict as exc:
                raise WebError(409, str(exc)) from exc
            except (FactoryError, ValueError) as exc:
                raise WebError(400, str(exc)) from exc
        return {"seed": dump(seed), "nextUrl": f"/studio/factory.html#c/{cid}"}
