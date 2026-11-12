"""Opt-in master-photo preview and explicit consent, independent of persona review."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from urllib.parse import quote

from fastapi import APIRouter
from pydantic import Field

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.common import Strict
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import (
    VIDEO_STAGES,
    graph_for_dir,
    read_reference_image,
    write_reference_image,
)
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError


class ReferenceImageSettings(Strict):
    wardrobe: str = Field(default="", max_length=600)
    background: str = Field(default="", max_length=600)


class ConfirmReference(Strict):
    revision: str = Field(pattern=r"^fr\d+$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Required when the revision also generated a signature middle-frame seed.
    signatureSha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class RetryReference(ReferenceImageSettings):
    revision: str | None = Field(default=None, pattern=r"^fr\d+$")


def install_reference_routes(app, conf, jobs):
    router = APIRouter(prefix="/api/sources")

    def folder_of(cid):
        folder = reads.character_dir(conf.root, cid)
        if not folder.is_dir() or not folder.is_relative_to(conf.root):
            raise WebError(404, "캐릭터를 찾을 수 없어요.")
        return folder

    @contextmanager
    def reference_lock(folder):
        # Only this G4 is mutable here. S4 publishes AWAITING_HUMAN last, and the
        # orchestrator never auto-approves it. StateFile serializes state writes;
        # persona workers can continue without holding the whole-character lock.
        with (folder / "reference-confirm.lock").open("a") as fp:
            fcntl.flock(fp, fcntl.LOCK_EX)
            yield

    def preview(cid):
        folder = folder_of(cid)
        settings = read_reference_image(folder)
        active = jobs.active_for(cid)
        result = dict(
            enabled=settings is not None,
            status="not_started",
            revision=None,
            imageUrl=None,
            sha256=None,
            signatureImageUrl=None,
            signatureSha256=None,
            wardrobe=(settings or {}).get("wardrobe", ""),
            background=(settings or {}).get("background", ""),
            activeJobId=active["jobId"] if active else None,
            error=None,
            validationStatus="unverified",
            videoStatus="none",
        )
        if settings is None:
            return result
        state, error = reads.read_state(folder)
        if error:
            raise WebError(409, "진행 상태를 읽지 못했어요.")
        stage = state.get("stages", {}).get("s4", {})
        gate = state.get("gates", {}).get("G4", {})
        video = state.get("stages", {}).get("s6", {})
        result["videoStatus"] = {
            "RUNNING": "making",
            "APPROVED": "ready",
            "AWAITING_HUMAN": "needs_review",
            "CHECK_FAILED": "failed",
            "REJECTED": "failed",
        }.get(video.get("status"), "none")
        rev = stage.get("currentRev") or gate.get("rev")
        result["revision"] = rev
        if stage.get("status") in {"RUNNING", "CHECK_FAILED", "REJECTED"}:
            result["status"] = "generating" if stage["status"] == "RUNNING" else "failed"
            result["error"] = stage.get("error")
            return result
        if gate.get("status") not in {"AWAITING_HUMAN", "APPROVED"}:
            failed = next(
                (
                    state.get("stages", {}).get(s, {})
                    for s in ("s0", "s2", "s3")
                    if state.get("stages", {}).get(s, {}).get("status") == "CHECK_FAILED"
                ),
                None,
            )
            result["status"] = "failed" if failed else "generating" if active else "not_started"
            if failed:
                result["error"] = failed.get("error") or "사진 생성에 필요한 앞 단계가 멈췄어요."
            return result
        frames = read_json(folder / "s4-frames" / rev / "frames.json")
        if not isinstance(frames, list) or len(frames) != 1:
            raise WebError(409, "기준 사진 기록을 읽지 못했어요.")
        frame = frames[0]
        rel = f"s4-frames/{rev}/{frame['filePath']}"
        path = reads.resolve_file(conf.root, cid, rel)
        digest = sha256_file(path)
        if digest != frame["fileSha256"]:
            raise WebError(409, "기준 사진이 생성 기록과 달라졌어요. 다시 만들어 주세요.")
        result.update(
            status="approved" if gate["status"] == "APPROVED" else "awaiting_confirmation",
            imageUrl=f"/api/files/{quote(cid, safe='')}/{quote(rel, safe='/')}",
            sha256=digest,
        )
        from character_factory_poc.common.errors import CheckFailed
        from character_factory_poc.stages.s4_frames.reference import read_signature_frame

        try:
            seed = read_signature_frame(folder / "s4-frames" / rev)
        except (CheckFailed, OSError, KeyError, ValueError):
            raise WebError(
                409, "시그니처 중간 프레임이 생성 기록과 달라졌어요. 다시 만들어 주세요."
            ) from None
        if seed:
            seed_rel = f"s4-frames/{rev}/{seed['filePath']}"
            result.update(
                signatureImageUrl=f"/api/files/{quote(cid, safe='')}/{quote(seed_rel, safe='/')}",
                signatureSha256=seed["fileSha256"],
            )
        return result

    @router.get("/{cid}/reference")
    def get_reference(cid: str):
        return preview(cid)

    @router.post("/{cid}/reference/confirm")
    def confirm(cid: str, body: ConfirmReference):
        folder = folder_of(cid)
        with reference_lock(folder):
            current = preview(cid)
            if (
                not current["enabled"]
                or current["status"] not in {"awaiting_confirmation", "approved"}
                or current["revision"] != body.revision
                or current["sha256"] != body.sha256
                or current["signatureSha256"] != body.signatureSha256
            ):
                raise WebError(
                    409, "확인할 기준 사진이 바뀌었어요. 최신 사진을 다시 확인해 주세요."
                )
            ctx = Context(config=load_config(conf.root, conf.config_path), execute=True)
            from character_factory_poc.stages.s4_frames.reference import matches_reference_inputs

            if not matches_reference_inputs(ctx, cid, body.revision):
                raise WebError(409, "사진 생성 조건이 바뀌었어요. 기준 사진을 다시 만들어 주세요.")
            if current["status"] != "approved":
                try:
                    approve_gate(
                        ctx,
                        cid,
                        "G4",
                        {
                            "decision": "APPROVE",
                            "reviewer": "기준 사진 확인",
                            "reasons": "인물·복장·배경·구도"
                            + ("와 시그니처 중간 프레임" if body.signatureSha256 else "")
                            + "을 확인하고 영상 6개 생성을 요청했어요.",
                        },
                    )
                except (FactoryError, ValueError) as exc:
                    raise WebError(409, str(exc)) from exc
            job = jobs.request_reference_resume(cid)
            jobs.publish_state(cid, force=True)
            return {
                "jobId": job["jobId"] if job else None,
                "queued": job is None and jobs.active_for(cid) is not None,
            }

    @router.post("/{cid}/reference/retry")
    def retry(cid: str, body: RetryReference):
        folder = folder_of(cid)
        if jobs.active_for(cid):
            raise WebError(409, "진행 중인 작업이 끝나면 기준 사진을 다시 만들 수 있어요.")
        with jobs.locks.hold(cid), reference_lock(folder):
            if jobs.active_for(cid):
                raise WebError(409, "진행 중인 작업이 끝나면 다시 만들어 주세요.")
            current = preview(cid)
            if not current["enabled"] or current["revision"] != body.revision:
                raise WebError(409, "최신 기준 사진을 확인한 뒤 다시 만들어 주세요.")
            if current["status"] == "approved":
                raise WebError(409, "이미 확인한 사진이에요. 기존 영상은 그대로 보존해요.")
            if current["status"] == "awaiting_confirmation":
                ctx = Context(config=load_config(conf.root, conf.config_path), execute=True)
                approve_gate(
                    ctx,
                    cid,
                    "G4",
                    {
                        "decision": "REQUEST_CHANGES",
                        "reviewer": "기준 사진 다시 만들기",
                        "requestedChanges": [
                            {
                                "field": "ch1",
                                "note": "입력한 복장·배경으로 기준 사진을 다시 만든다.",
                            }
                        ],
                    },
                )
            write_reference_image(folder, body.model_dump(exclude={"revision"}))
            job = jobs.submit(
                cid,
                until="G5b",
                trigger="videos-with-chat",
                confirm=[s for s in VIDEO_STAGES if s in graph_for_dir(folder)],
            )
            return {"jobId": job["jobId"]}

    app.include_router(router)
