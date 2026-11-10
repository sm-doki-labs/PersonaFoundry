"""모티브 출처 초안과 원본 업로드. 확정한 묶음만 S0 작업에 넘긴다."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, StringConstraints, ValidationError

from character_factory_poc.common.config import load_config
from character_factory_poc.common.source_store import (
    MAX_BYTES,
    LocalSourceStore,
    S3SourceStore,
    SourcePathError,
    SourceStore,
    atomic_write,
    inside,
    local_copy,
)
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.source import (
    SourcePack,
    SourceSubject,
    SourceText,
    SubjectKind,
    UsageBasis,
    default_register,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import (
    SOURCE,
    VIDEO_STAGES,
    VideoTier,
    read_auto_review,
    read_origin,
    read_signature,
    read_video_tier,
    write_model_mode,
    write_origin,
    write_signature,
    write_video_tier,
)
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s3_plan.common import new_character
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError

EXTENSIONS = {".txt", ".srt", ".vtt", ".csv", ".json"}
FIELDS = ("textId", "kind", "register", "subjectSpeaker", "userSpeaker", "date", "sourceUrl")


class KnownFacts(Strict):
    """S3 기획이 인물 소개 첫 줄로 쓰는 기본 정보(source-pack-v1 knownFacts)."""

    age: str = Field(default="", max_length=20)
    gender: str = Field(default="", max_length=20)
    job: str = Field(default="", max_length=60)
    background: str = Field(default="", max_length=400)


class SignaturePose(Strict):
    """유저가 정하는 시그니처 포즈(D-0165). 모든 영상 등급에 한 편씩 들어간다."""

    # 앞뒤 공백을 뗀 뒤 길이를 본다(공백만 적은 이름·동작은 받지 않는다).
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    motion: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
    useWhen: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""


class Settings(Strict):
    videoTier: VideoTier
    signaturePose: SignaturePose | None = None


def _signature(pose: SignaturePose) -> dict:
    return {k: v.strip() for k, v in pose.model_dump().items()}


class Draft(Strict):
    videoTier: VideoTier = "none"
    signaturePose: SignaturePose | None = None
    displayName: str = Field(min_length=1)
    subjectKind: SubjectKind
    usageBasis: UsageBasis = Field(default_factory=UsageBasis)
    modelMode: Literal["PROMPT_ONLY", "BIND_EXISTING", "TRAIN"] = "PROMPT_ONLY"
    autoReview: bool = True
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL"] | None = None
    knownFacts: KnownFacts = Field(default_factory=KnownFacts)


class Upload(Strict):
    filename: str
    size: int = Field(gt=0, le=MAX_BYTES)
    contentType: str = Field(min_length=1)


class ImportPath(Strict):
    path: str


class IntakeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                return await handler(request)
            except SourcePathError:
                raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
            except RequestValidationError:
                path = request.url.path
                if path.endswith(("/settings", "/videos")):
                    raise WebError(
                        422,
                        "입력한 내용을 확인해 주세요. 시그니처 이름은 30자, 동작은 400자, "
                        "나오는 때는 200자까지 적을 수 있어요.",
                    ) from None
                if path.endswith("/drafts"):
                    raise WebError(422, "입력한 내용을 확인해 주세요.") from None
                raise WebError(422, "입력한 내용과 파일 크기를 확인해 주세요.") from None

        return checked


def save(path: Path, data: dict) -> None:
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


PHOTO_FORMATS = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".webp": b"RIFF",
}
PHOTO_LIMIT = 15 * 1024 * 1024


def photo_ok(name, data):
    import cv2
    import numpy as np

    ext = Path(name).suffix.lower()
    if not data.startswith(PHOTO_FORMATS[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
        return False
    try:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_REDUCED_COLOR_8) is not None
    except cv2.error:
        return False


def record(spec: Upload) -> dict:
    name = spec.filename
    photo = Path(name).suffix.lower() in PHOTO_FORMATS
    if photo and spec.size > PHOTO_LIMIT:
        raise WebError(413, "사진은 15MB 이하로 올려 주세요.")
    if (
        Path(name).name != name
        or "\\" in name
        or len(name.encode()) > 255
        or any(ord(c) < 32 for c in name)
        or Path(name).suffix.lower() not in EXTENSIONS
        and not photo
    ):
        raise WebError(400, "원문 파일 이름과 형식을 확인해 주세요.")
    return dict(
        fileType="photo" if photo else "text",
        fileId=uuid4().hex,
        filename=name,
        size=spec.size,
        sha256=None,
        status="pending",
        detectedSpeakers=[],
        suggested=dict(
            subjectSpeaker=None, userSpeaker=None, subjectChoices=[], kind=None, register=None
        ),
        problems=[],
        **dict.fromkeys(FIELDS),
    )


def find_file(draft, fid):
    for item in draft["files"]:
        if item["fileId"] == fid:
            return item
    raise WebError(404, "등록한 파일을 찾을 수 없어요.")


def summary(draft):
    problems = []
    files = draft["files"]
    if not any(f.get("fileType", "text") == "text" for f in files):
        problems.append("대화나 글이 담긴 원문을 하나 이상 올려 주세요.")
    if draft["videoTier"] != "none" and not any(
        f["fileType"] == "photo" and f["status"] == "ready" for f in files
    ):
        problems.append("영상을 만들려면 인물 사진을 한 장 이상 올려 주세요.")
    if draft["videoTier"] != "none" and not draft.get("signaturePose"):
        problems.append("영상을 만들려면 시그니처 포즈를 정해 주세요.")
    ids = [f["textId"] for f in files if f["textId"]]
    if len(ids) != len(set(ids)):
        problems.append("원문 이름이 겹쳐요.")
    for f in files:
        problems.extend(f"{f['filename']}: {p}" for p in f["problems"])
    ready = bool(files) and all(f["status"] == "ready" for f in files)
    return problems, ready and not problems and not draft.get("jobId")


def source_text(folder, item):
    return SourceText(
        **{k: item[k] for k in FIELDS},
        path=str(local_copy(folder, item["fileId"], item["filename"]).relative_to(folder)),
    )


def suggested_kind(filename, raw):
    hint = filename.lower() + " " + raw[:180].lower()
    if re.search(
        r"카카오톡|카톡|kakao|date,\s*user,\s*message|\[(?:오전|오후) \d|오[전후] \d+:\d+,", hint
    ):
        return "KAKAO_EXPORT"
    if Path(filename).suffix.lower() in {".vtt", ".srt"} or re.search(
        r"브이로그|vlog|녹취|자막|일상", hint
    ):
        return "TRANSCRIPT"
    if re.search(r"기사|article|보도자료", hint):
        return "ARTICLE"
    return "INTERVIEW"


def auto_text_id(item, files):
    stem = Path(item["filename"]).stem
    base = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")
        or "source-" + hashlib.sha256(stem.encode()).hexdigest()[:8]
    )
    taken = {f.get("textId") for f in files if f["fileId"] != item["fileId"]}
    result, n = base, 1
    while result in taken:
        n += 1
        result = f"{base}-{n}"
    return result


# 카톡을 내보낸 본인은 파일에 "나"로 적힌다. 대상 인물 후보에서는 맨 뒤로 미루고 권하지 않는다.
# 1:1 카톡에서는 내보낸 본인이 대화 상대라 상대 화자로 먼저 권한다(QA v5 A-03·A-23).
SELF_NAMES = {"나", "me"}


def is_self(name):
    return name.strip().lower() in SELF_NAMES


def speaker_suggestions(messages, display):
    """원문 화자 목록(본인은 뒤로), 표시 이름과 맞는 대상 화자, 고를 후보를 돌려준다.

    표시 이름과 맞는 화자가 없으면 줄 수로 아무나 고르지 않고 대상 화자를 비워 둔다.
    """
    counts = Counter(m.name for m in messages)
    ranked = [name for name, _ in counts.most_common()]
    ranked = [n for n in ranked if not is_self(n)] + [n for n in ranked if is_self(n)]

    def score(name):
        if name == display:
            return (1, 1, 1.0, counts[name])
        if is_self(name):
            return (0, 0, 0.0, 0)
        similarity = SequenceMatcher(None, display, name).ratio()
        return (0, int(name in display or display in name), similarity, counts[name])

    best = max(ranked, key=score, default=None)
    matched = best is not None and (score(best)[1] or score(best)[2] >= 0.5)
    choices = [n for n in ranked if not is_self(n)]
    return [dict(name=n, lines=counts[n]) for n in ranked], best if matched else None, choices


def user_suggestion(names, subject, kind):
    others = [n for n in names if n != subject]
    if kind == "KAKAO_EXPORT":
        me = next((n for n in others if is_self(n)), None)
        if me or not subject:
            return me
    return others[0] if subject and others else None


def install_source_routes(app, conf, jobs):
    router = APIRouter(prefix="/api/sources", route_class=IntakeRoute)
    store: SourceStore = (
        S3SourceStore(conf.source_bucket, conf.source_prefix)
        if conf.source_store == "s3"
        else LocalSourceStore()
    )
    if conf.source_store == "s3":
        from botocore.exceptions import BotoCoreError, ClientError
        from fastapi.responses import JSONResponse

        async def storage_error(request, exc):
            return JSONResponse({"detail": "원문 저장소에 연결하지 못했어요."}, status_code=502)

        for error in (BotoCoreError, ClientError):
            app.add_exception_handler(error, storage_error)
    allow_import = not conf.server_mode and conf.source_store == "local"

    @contextmanager
    def opened(cid, *, edit=False, purge=False, settings=False):
        try:
            folder = reads.character_dir(conf.root, cid)
        except WebError as exc:
            raise WebError(exc.status, "만들던 초안을 찾을 수 없어요.") from None
        try:
            state = inside(folder, "s0-source", "intake.json")
            lock = inside(folder, "s0-source", "intake.lock")
        except ValueError:
            raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
        legacy = (
            settings
            and not state.is_file()
            and lock.parent.is_dir()
            and read_origin(folder) == SOURCE
        )
        if not folder.is_relative_to(conf.root) or not (state.is_file() or legacy):
            raise WebError(404, "만들던 초안을 찾을 수 없어요.")
        with lock.open("a") as fp:
            fcntl.flock(fp, fcntl.LOCK_EX)
            draft = {} if legacy else json.loads(state.read_text("utf-8"))
            draft["videoTier"] = read_video_tier(folder) or "none"
            draft["signaturePose"] = read_signature(folder)
            for item in draft.get("files", []):
                item.setdefault("fileType", "text")
            if edit and (jobs.active_for(cid) or (draft.get("jobId") and not purge)):
                raise WebError(409, "이미 만들기를 시작해서 원문을 바꿀 수 없어요.")
            yield folder, draft
            if edit:
                save(state, {k: v for k, v in draft.items() if k != "signaturePose"})

    @router.post("/drafts")
    def create(body: Draft):
        inside(conf.root, "runs", "characters")
        ctx = Context(config=load_config(conf.root, conf.config_path), execute=False)
        cid = new_character(ctx, f"motif-{uuid4().hex[:16]}")
        folder = ctx.character_dir(cid)
        write_origin(folder, SOURCE, auto_review=body.autoReview)
        write_video_tier(folder, body.videoTier)
        if body.signaturePose:
            write_signature(folder, _signature(body.signaturePose))
        write_model_mode(folder, body.modelMode)
        subject = SourceSubject(displayName=body.displayName, kind=body.subjectKind)
        save(
            inside(folder, "s0-source", "intake.json"),
            dict(
                characterId=cid,
                createdAt=datetime.now(UTC).isoformat(),
                subject=subject.model_dump(),
                usageBasis=body.usageBasis.model_dump(),
                chapterTemplate=body.chapterTemplate,
                knownFacts={
                    k: v.strip() for k, v in body.knownFacts.model_dump().items() if v.strip()
                },
                files=[],
            ),
        )
        return {"characterId": cid}

    @router.get("/drafts")
    def drafts():
        result = []
        for folder in reads.visible_folders(conf.root):
            draft = reads.read_json_file(folder / "s0-source/intake.json")
            if not draft or draft.get("jobId") or jobs.active_for(folder.name):
                continue
            state, _ = reads.read_state(folder)
            if reads.is_draft(draft, state.get("stages", {}).values()):
                result.append(
                    dict(
                        characterId=folder.name,
                        displayName=reads.display_name(reads._persona(folder), draft),
                        createdAt=reads.created_at(folder, draft),
                        files=len(draft["files"]),
                    )
                )
        return sorted(result, key=lambda r: r["createdAt"], reverse=True)

    @router.get("/{cid}")
    def detail(cid: str):
        with opened(cid) as (_, draft):
            problems, ready = summary(draft)
            return {k: draft[k] for k in ("characterId", "subject", "usageBasis", "files")} | {
                "videoTier": draft["videoTier"],
                "signaturePose": draft["signaturePose"],
                "knownFacts": draft.get("knownFacts", {}),
                "store": conf.source_store,
                "allowPathImport": allow_import,
                "problems": problems,
                "canFinalize": bool(ready),
                "jobId": draft.get("jobId"),
            }

    @router.post("/{cid}/files")
    def presign(cid: str, body: Upload):
        with opened(cid, edit=True) as (folder, draft):
            item = record(body)
            upload = store.upload(folder, item["fileId"], body.size, body.contentType)
            draft["files"].append(item)
            return {"fileId": item["fileId"], "upload": upload}

    @router.put("/{cid}/files/{fid}/content")
    async def content(cid: str, fid: str, request: Request):
        if conf.source_store != "local":
            raise WebError(403, "파일을 올릴 때 받은 주소를 이용해 주세요.")
        with opened(cid) as (_, draft):
            size = find_file(draft, fid)["size"]
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > size:
                raise WebError(413, "처음 고른 파일보다 크기가 커요.")
            data.extend(chunk)
        if len(data) != size:
            raise WebError(400, "처음 고른 파일과 크기가 달라요.")
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            path = local_copy(folder, fid, item["filename"])
            if path.exists():
                raise WebError(409, "이미 올린 파일이에요.")
            atomic_write(path, data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
        return {"fileId": fid}

    def check(folder, draft, item, body):
        if body.keys() - set(FIELDS):
            raise WebError(422, "바꿀 수 없는 항목이 있어요.")
        if item["fileType"] == "photo":
            if body:
                raise WebError(422, "사진에는 화자 정보를 넣지 않아도 돼요.")
            try:
                data = store.read(folder, item["fileId"], item["filename"], item["size"])
                digest = hashlib.sha256(data).hexdigest()
                if item["sha256"] not in (None, digest) or not photo_ok(item["filename"], data):
                    raise ValueError
            except (OSError, ValueError):
                item.update(
                    status="problem",
                    problems=["사진을 열 수 없어요. 원본 사진을 다시 올려 주세요."],
                )
            else:
                item.update(status="ready", sha256=digest, problems=[])
            return item
        candidate = item | body
        display = draft["subject"]["displayName"]
        problems = []
        raw = ""
        try:
            data = store.read(folder, item["fileId"], item["filename"], item["size"])
            digest = hashlib.sha256(data).hexdigest()
            if item["sha256"] and item["sha256"] != digest:
                raise ValueError
            raw = data.decode("utf-8-sig")
            candidate["sha256"] = digest
        except UnicodeError:
            problems.append("한글을 읽을 수 있도록 파일을 UTF-8로 저장해 주세요.")
        except (ValueError, OSError):
            problems.append("원문을 확인할 수 없어 파일을 다시 올려야 해요.")

        kind = suggested_kind(item["filename"], raw)
        candidate["kind"] = candidate["kind"] or kind

        if (
            not candidate["textId"]
            or isinstance(candidate["textId"], str)
            and not candidate["textId"].strip()
        ):
            candidate["textId"] = auto_text_id(item, draft["files"])
        try:
            spec = source_text(folder, candidate)
        except ValidationError:
            raise WebError(422, "원문 이름과 선택한 종류, 말한 자리를 확인해 주세요.") from None
        if spec.register is None:
            candidate["register"] = default_register(spec.kind)
        detected, subject, user, choices = [], None, None, []
        if not problems:
            try:
                messages = parse.source_messages(spec, raw, display)
                detected, subject, choices = speaker_suggestions(messages, display)
                if not (spec.subjectSpeaker or "").strip():
                    spec.subjectSpeaker = candidate["subjectSpeaker"] = subject
                names = [s["name"] for s in detected]
                chosen = spec.subjectSpeaker if spec.subjectSpeaker in names else subject
                user = user_suggestion(names, chosen, spec.kind)
                if not spec.subjectSpeaker and spec.kind != "ARTICLE":
                    problems.append(
                        f"원문에 ‘{display}’ 이름이 없어요. 누가 이 사람인지 골라 주세요. "
                        f"원문에 있는 이름: {', '.join(names)}"
                        if names
                        else "원문에 누가 말했는지 이름을 적어 주세요."
                    )
                for name in (spec.subjectSpeaker, spec.userSpeaker):
                    if spec.kind != "ARTICLE" and name and name not in names:
                        problems.append(
                            f"‘{name}’ 대신 원문에 있는 이름({', '.join(names)})을 골라 주세요."
                        )
                same = spec.subjectSpeaker and spec.subjectSpeaker == spec.userSpeaker
                if spec.kind != "ARTICLE" and same:
                    problems.append("대상 화자와 상대 화자를 다른 사람으로 골라 주세요.")
            except (ValueError, KeyError, TypeError):
                problems.append("원문을 읽을 수 없어 날짜와 파일 종류, 화자 표기를 확인해 주세요.")
        candidate.update(
            detectedSpeakers=detected,
            suggested=dict(
                subjectSpeaker=subject,
                userSpeaker=user,
                subjectChoices=choices,
                kind=kind,
                register=default_register(kind),
            ),
            warnings=[
                f"원문에 ‘{warning.split(': ', 1)[-1]}’ 안내가 있어요."
                for warning in parse.restriction_problems(raw)
            ],
        )
        item.update(candidate, status="problem" if problems else "ready", problems=problems)
        return item

    @router.post("/{cid}/files/{fid}/complete")
    @router.patch("/{cid}/files/{fid}")
    def complete(cid: str, fid: str, body: dict):
        with opened(cid, edit=True) as (folder, draft):
            return check(folder, draft, find_file(draft, fid), body)

    @router.post("/{cid}/import-path")
    def import_path(cid: str, body: ImportPath):
        if not allow_import:
            raise WebError(403, "이 컴퓨터에 저장할 때만 파일 위치로 가져올 수 있어요.")
        path = Path(body.path).expanduser()
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise WebError(400, "가져올 파일의 위치와 크기를 확인해 주세요.")
        item = record(
            Upload(filename=path.name, size=path.stat().st_size, contentType="text/plain")
        )
        with opened(cid, edit=True) as (folder, draft):
            with path.open("rb") as fp:
                data = fp.read(item["size"] + 1)
            if len(data) != item["size"]:
                raise WebError(409, "원문 파일의 크기가 바뀌었어요.")
            atomic_write(local_copy(folder, item["fileId"], path.name), data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            draft["files"].append(item)
            return item

    @router.delete("/{cid}/files/{fid}")
    def remove(cid: str, fid: str):
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            store.delete(folder, fid)
            draft["files"].remove(item)
        return {"fileId": fid}

    @router.delete("/{cid}")
    def purge(cid: str):
        with opened(cid, edit=True, purge=True) as (folder, draft):
            store.delete(folder)
            draft["files"].clear()
        return {"characterId": cid}

    @router.post("/{cid}/finalize")
    def finalize(cid: str):
        with opened(cid, edit=True) as (folder, draft):
            problems, ready = summary(draft)
            if not ready:
                raise WebError(409, "; ".join(problems) or "올린 원문을 모두 확인해 주세요.")
            texts, photos = [], []
            for item in draft["files"]:
                try:
                    data = store.read(folder, item["fileId"], item["filename"], item["size"])
                    if hashlib.sha256(data).hexdigest() != item["sha256"]:
                        raise ValueError("확인한 원본 해시와 다르다")
                except (ValueError, OSError):
                    message = "확인한 원문과 달라서 파일을 다시 올려야 해요."
                    item.update(status="problem", problems=[message])
                    save(inside(folder, "s0-source", "intake.json"), draft)
                    raise WebError(409, message) from None
                if conf.source_store == "s3":
                    atomic_write(local_copy(folder, item["fileId"], item["filename"]), data)
                if item["fileType"] == "photo":
                    photos.append(
                        {
                            "path": str(
                                local_copy(folder, item["fileId"], item["filename"]).relative_to(
                                    folder
                                )
                            )
                        }
                    )
                else:
                    texts.append(source_text(folder, item))
            opts = {"chapterTemplate": draft["chapterTemplate"]} if draft["chapterTemplate"] else {}
            pack = SourcePack(
                subject=draft["subject"],
                knownFacts=draft.get("knownFacts", {}),
                usageBasis=draft["usageBasis"],
                texts=texts,
                photos=photos,
                **opts,
            )
            save(inside(folder, "source-pack.json"), pack.model_dump(mode="json"))
            if read_auto_review(folder) and draft["videoTier"] != "none":
                job = video_job(cid, prepare_chat=True)
            else:
                job = jobs.submit(cid, until="s8c" if read_auto_review(folder) else "G0")
            draft["jobId"] = job["jobId"]
            return {"jobId": draft["jobId"]}

    def video_job(cid, *, prepare_chat=False):
        return jobs.submit(
            cid,
            until="G5b",
            confirm=list(VIDEO_STAGES),
            trigger="videos-with-chat" if prepare_chat else "videos",
        )

    def change_settings(folder, draft, cid, tier, signature=None):
        if jobs.active_for(cid):
            raise WebError(409, "만들기가 끝난 뒤에 바꿀 수 있어요.")
        if (draft.get("jobId") or "files" not in draft) and not reads.character_summary(folder)[
            "chatReady"
        ]:
            raise WebError(409, "대화 준비가 끝난 뒤에 바꿀 수 있어요.")
        write_video_tier(folder, tier)
        if signature:
            write_signature(folder, _signature(signature))
            draft["signaturePose"] = read_signature(folder)

    @router.patch("/{cid}/settings")
    def settings(cid: str, body: Settings):
        with opened(cid, settings=True) as (folder, draft):
            change_settings(folder, draft, cid, body.videoTier, body.signaturePose)
            return {"videoTier": body.videoTier, "signaturePose": read_signature(folder)}

    videos = APIRouter(route_class=IntakeRoute)

    @videos.post("/api/characters/{cid}/videos")
    def start_videos(cid: str, body: Settings):
        with opened(cid, settings=True) as (folder, draft):
            row = reads.character_summary(folder)
            if not row["chatReady"]:
                raise WebError(409, "대화 준비가 끝나면 영상을 만들 수 있어요.")
            if body.videoTier == "none":
                raise WebError(422, "만들 영상의 등급을 골라 주세요.")
            if not body.signaturePose and not read_signature(folder):
                raise WebError(422, "영상을 만들려면 시그니처 포즈를 정해 주세요.")
            gate = next(
                (g for g in row["gates"] if g["id"] == "G0" and g["status"] == "APPROVED"), {}
            )
            if not gate.get("rev") or not (
                reads.read_json_file(inside(folder, "s0-source", gate["rev"], "source-pack.json"))
                or {}
            ).get("photos"):
                raise WebError(409, "영상을 만들려면 사진이 담긴 원문 묶음이 필요해요.")
            change_settings(folder, draft, cid, body.videoTier, body.signaturePose)
            return {"jobId": video_job(cid)["jobId"]}

    app.include_router(videos)
    app.include_router(router)
