"""첫 장면 대화와 공통 시연 표본. 개인이 나눈 대화는 저장하지 않는다."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from character_factory_poc.common.api_routes import billing_for
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.reply_guard import guarded
from character_factory_poc.common.source_store import atomic_write
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.providers.factory import make_text_model
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.tracked import TrackedTextModel
from character_factory_poc.providers.vertex_auth import vertex_openai_base_url

TIMEOUT = 60
DEFAULT = ProviderConfig(
    adapter="openai_compat",
    model="gemini-3.8-flash",
    api_key_env="GEMINI_API_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    extra={"reasoning_effort": "low", "max_retries": 2},
)


class NotReady(ValueError):
    pass


def latest(folder: Path, prefix: str, artifact: str | None = None) -> Path | None:
    paths = (
        p
        for p in folder.glob(f"{prefix}*")
        if re.fullmatch(rf"{prefix}[0-9]+", p.name)
        and p.is_dir()
        and (not artifact or (p / artifact).is_file())
    )
    return max(paths, key=lambda p: int(p.name[len(prefix) :]), default=None)


def load_json(path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return default


def resource(name):
    return load_json(files("character_factory_poc.resources").joinpath(name))


@dataclass(frozen=True)
class Scene:
    folder: Path
    prompt: Path | None
    chapter: Path | None
    name: str

    @classmethod
    def read(cls, folder: Path, *, name: str | None = None) -> Scene:
        if name is None:
            plan = latest(folder / "s3-plan", "pr", "plan.json")
            name = (load_json(plan / "plan.json", {}) if plan else {}).get("name")
            if not name:
                name = (
                    load_json(folder / "source-pack.json", {}).get("subject", {}).get("displayName")
                )
        return cls(
            folder,
            latest(folder / "s8-prompts", "pv", "long.md"),
            latest(folder / "s8-chapters", "cs", "chapter-start.json"),
            name or "캐릭터",
        )

    def _voice(self):
        try:
            voice = (self.prompt / "long.md").read_text("utf-8").rstrip("\n") if self.prompt else ""
        except (UnicodeError, OSError):
            voice = ""
        if not voice.strip():
            raise NotReady("캐릭터의 말투와 성격이 아직 없어요.")
        return voice

    def _scene(self):
        if not self.chapter:
            raise NotReady("첫 통화 장면이 아직 없어요.")
        try:
            ch = next(
                c
                for c in load_json(self.chapter / "chapter-start.json")["chapters"]
                if c["chapterId"] == "ch1"
            )
            r = ch["relationship"]
            speech = {"POLITE": "존댓말", "CASUAL": "반말"}[r["speechLevel"]]

            def bullets(lines):
                return "\n".join("- " + line for line in lines)

            return (
                f"[CURRENT_RELATIONSHIP: {self.chapter.name}-ch1]\n\n"
                f"발화자: {self.name}\n이 장면에서는 끝까지 {speech}을 쓴다. "
                f"호칭과 거리감: {r['addresseeStance']}\n"
                f"entry_posture:\n{bullets(r['entryPosture'])}\nwhy_here={r['presenceReason']}\n"
                f"initiative={r['initiativePolicy']}\nexpression_now:\n{bullets(r['expressionDelta'])}\n\n"
                "relationship_stage_at_start=STRANGER\n\n\n"
                "[CURRENT_SCENE]\n\nchapter=ch1; scene=first-call\n\n"
                f"{bullets(ch['sceneFacts'])}\n\n\n[SCENE_BOUNDARIES]\n\n{bullets(ch['sceneBoundaries'])}\n"
            )
        except (StopIteration, KeyError, TypeError, OSError, ValueError) as exc:
            raise NotReady("첫 대화 장면을 읽을 수 없어요. 장면 설정을 확인해 주세요.") from exc

    def compose(self):
        return self._voice() + "\n\n" + self._scene()

    def readiness(self, *, running=False, draft=False):
        missing, reasons = [], []
        for key, read in (("prompt", self._voice), ("scene", self._scene)):
            try:
                read()
            except NotReady as exc:
                missing.append(key)
                reasons.append(str(exc))
        page = "sources" if draft else "factory"
        from character_factory_poc.pipeline.origin import SOURCE, read_origin

        if missing and read_origin(self.folder) != SOURCE:
            # 오리지널에는 첫 통화 장면(S8c) 단계가 없다(QA v5 C-05).
            # 막다른 안내 대신 쓸 수 없다고 말한다.
            reasons = [
                "지어낸 캐릭터는 아직 대화해 보기를 쓸 수 없어요. "
                "실존 인물로 만든 캐릭터에서 써 보세요."
            ]
            return dict(ready=False, missing=missing, reason=reasons[0], nextHref=None)
        if missing:
            waiting = [
                g
                for g, v in (load_json(self.folder / "state.json", {}) or {})
                .get("gates", {})
                .items()
                if isinstance(v, dict) and v.get("status") == "AWAITING_HUMAN"
            ]
            reasons.append(
                "원문 화면에서 만들기를 시작해 주세요."
                if draft
                else "진행 화면에서 기다리는 확인을 마치면 이어서 만들어요."
                if waiting
                else "진행 화면에서 확인해 주세요."
            )
        return dict(
            ready=not missing,
            missing=missing,
            reason="만드는 중이에요" if missing and running else " ".join(reasons),
            nextHref=f"{page}.html#c/{self.folder.name}" if missing else None,
        )

    def samples(self):
        data = load_json(self.chapter / "samples.json") if self.chapter else None
        if isinstance(data, list):
            return data
        if data and self.prompt and data.get("promptRev") == self.prompt.name:
            return data["samples"]
        return []


def scenarios(folder=None):
    generic = resource("demo-scenarios-v1.json")
    custom = load_json(folder / "demo/scenarios.json", []) if folder else []
    if isinstance(custom, dict):
        custom = custom["scenarios"]
    return custom + generic


def provider(ctx, via, server_mode=False):
    cfg = ctx.config.providers.get("demo_chat", DEFAULT)
    extra = {**DEFAULT.extra, "timeout_s": 15, **cfg.extra}
    if via == "vertex":
        if server_mode or os.getenv("CFP_SERVER_MODE") == "1":
            raise PermissionError("팀 서버에서는 기본 대화 모델을 이용해 주세요.")
        project = extra.get("project") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise ValueError("로컬 대화 모델에 사용할 프로젝트를 먼저 설정해 주세요.")
        base = vertex_openai_base_url(project, extra.get("location", "global"))
        return ProviderConfig(
            adapter="vertex_openai",
            base_url=base,
            model="google/" + cfg.model.removeprefix("google/"),
            extra=extra,
        )
    if cfg.adapter == "vertex_openai":
        raise ValueError("기본 대화 모델 설정을 확인해 주세요.")
    return replace(cfg, extra=extra)


def talk_model(ctx, cid, cfg):
    if not ctx.execute:
        raise ValueError("대화 실행을 먼저 켜 주세요.")
    if cfg.adapter == "openai_compat" and cfg.api_key_env and not cfg.api_key():
        raise ValueError("대화 모델의 인증 설정을 확인해 주세요.")
    inner = make_text_model(cfg)
    if isinstance(inner, FakeTextModel) and not inner.responses:
        inner.add("*", "지금은 대화 연습 중이에요.")
    return TrackedTextModel(
        inner,
        ctx.ledger(cid),
        ctx.budget(),
        billing=billing_for(cfg),
        price_overrides=ctx.price_overrides(),
    )


def respond(model, messages, temperature, deadline=None):
    started = time.monotonic()
    deadline = deadline or started + TIMEOUT
    ref = uuid4().hex

    def generate(attempt):
        if time.monotonic() >= deadline:
            raise TimeoutError
        reply = model.complete(
            ChatRequest(
                "PROBE", "demo", tuple(messages), f"demo-{ref}-{attempt}", temperature=temperature
            )
        )
        if not reply.text.strip():
            raise RuntimeError("답변이 비어 있어요.")
        return reply.text.strip()

    tries = 3
    reply, rejected = guarded(generate, max_tries=tries)
    if time.monotonic() >= deadline:
        raise TimeoutError
    if len(rejected) == tries:
        raise RuntimeError("대화에 쓸 답변을 만들지 못했어요.")
    return dict(
        reply=reply,
        ms=round((time.monotonic() - started) * 1000),
        rejected=len(rejected),
        model=model.model,
    )


def run_samples(ctx: Context, cid: str) -> Path:
    scene = Scene.read(ctx.character_dir(cid))
    system = Message("system", scene.compose())
    path = scene.chapter / "samples.json"
    if scene.samples():
        return path
    model = talk_model(ctx, cid, provider(ctx, "studio"))
    temperature = ctx.config.demo_chat_temperature(True)
    samples = []
    for scenario in scenarios():
        messages, turns = [system], []
        for user in scenario["turns"]:
            messages.append(Message("user", user))
            reply = respond(model, messages, temperature)["reply"]
            turns.append(dict(user=user, reply=reply))
            messages.append(Message("assistant", reply))
        samples.append(dict(scenarioId=scenario["id"], title=scenario["title"], turns=turns))
    data = dict(promptRev=scene.prompt.name, samples=samples)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode())
    return path


def chat_clips(folder: Path, chapter: str, *, for_picker: bool = False) -> dict:
    """G5b가 확정한 최신 판의 영상만 반환한다. 후보 목록은 승인 증거가 아니다."""
    from character_factory_poc.stages.s6_actions.catalog import CATALOG

    result = dict(
        ready=False, chapter=chapter, idle=dict(good=None, bad=None), emotion=[], special=[]
    )
    rev = latest(folder / "s6-actions", "va", "approved-actions.json")
    if not rev or not rev.resolve().is_relative_to(folder.resolve()):
        return result
    manifest = rev / "approved-actions.json"
    if not manifest.resolve().is_relative_to(rev.resolve()):
        return result
    taxonomy = resource("clip-pick-use-when-v1.json")
    rev_root = rev.resolve()
    seen = set()
    for row in load_json(manifest)["clips"]:
        key = row.get("clipKey")
        if row.get("chapterId") != chapter or not key or key in seen:
            continue
        path = (rev / row["video"]["path"]).resolve()
        if not path.is_relative_to(rev_root) or path.suffix.lower() != ".mp4" or not path.is_file():
            continue
        rel = path.relative_to(folder.resolve()).as_posix()
        url = f"/api/files/{quote(folder.name)}/{quote(rel)}"
        item = dict(clipKey=key, url=url)
        raw = re.sub(r"^s\d+__", "", key)
        defaults = CATALOG.get(raw) or CATALOG.get(re.sub(r"_\d+$", "", raw), {})
        mood = row.get("mood") or defaults.get("mood")
        if raw in {"idle_good", "idle_bad"}:
            result["idle"][raw.removeprefix("idle_")] = item
        elif raw.startswith(("idle", "speak")) or raw.endswith("_talking"):
            continue
        else:
            base = re.sub(
                r"_(good|bad)(_\d+|_strong)?$",
                lambda m: "_strong" if m[2] == "_strong" else "",
                raw,
            )
            role = (
                row.get("pickRole")
                or defaults.get("pickRole")
                or ("emotion" if base in taxonomy else "special")
            )
            if for_picker:
                item["description"] = row.get("description") or defaults.get("description") or ""
            result["emotion" if role == "emotion" else "special"].append(
                dict(
                    **item,
                    mood=mood,
                    title=row.get("title") or defaults.get("title") or "몸짓",
                    useWhen=row.get("useWhen") or defaults.get("useWhen") or taxonomy.get(base, ""),
                )
            )
        seen.add(key)
    result["ready"] = bool(seen)
    return result
