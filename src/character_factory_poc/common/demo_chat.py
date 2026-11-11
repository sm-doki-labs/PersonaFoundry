"""첫 장면 대화와 시연 표본. 개인 대화의 저장은 web.chat_history가 담당한다."""

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
    review_preview: bool = False

    @classmethod
    def read(cls, folder: Path, *, name: str | None = None, review_preview: bool = False) -> Scene:
        if name is None:
            plan = latest(folder / "s3-plan", "pr", "plan.json")
            name = (load_json(plan / "plan.json", {}) if plan else {}).get("name")
            if not name:
                name = (
                    load_json(folder / "source-pack.json", {}).get("subject", {}).get("displayName")
                )
        prompt = latest(folder / "s8-prompts", "pv", "long.md")
        # A new evidence attempt must not silently fall back to an older prompt.
        try:
            state = load_json(folder / "state.json", {})
        except (ValueError, OSError) as exc:
            raise NotReady("대화 상태를 읽을 수 없어요. 저장 상태를 확인해 주세요.") from exc
        rev = state.get("stages", {}).get("s8", {}).get("currentRev")
        if isinstance(rev, str) and re.fullmatch(r"pv[0-9]+", rev):
            current = folder / "s8-prompts" / rev
            if (current / "evidence-intent.json").is_file():
                prompt = current
        return cls(
            folder,
            prompt,
            latest(folder / "s8-chapters", "cs", "chapter-start.json"),
            name or "캐릭터",
            review_preview,
        )

    def _voice(self):
        if self.prompt:
            from character_factory_poc.stages.s8_prompts.evidence_pipeline import (
                is_evidence,
                verify_snapshot,
            )

            try:
                if is_evidence(self.prompt):
                    verify_snapshot(self.folder, self.prompt, review_preview=self.review_preview)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise NotReady(
                    "원문 근거 검토와 승인을 확인해 주세요. 자료가 바뀌었다면 다시 생성해야 해요."
                ) from exc
        try:
            voice = (self.prompt / "long.md").read_text("utf-8").rstrip("\n") if self.prompt else ""
        except (UnicodeError, OSError):
            voice = ""
        if not voice.strip():
            raise NotReady("캐릭터의 말투와 성격이 아직 없어요.")
        return voice

    def _scene(self):
        if not self.chapter:
            raise NotReady("대화 시작 장면이 아직 없어요.")
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

    def _has_compiled_scene(self):
        if not self.prompt:
            return False
        from character_factory_poc.stages.s8_prompts.evidence_pipeline import is_evidence

        if is_evidence(self.prompt):
            return True  # _voice has verified the authoritative evidence binding.
        binding = load_json(self.prompt / "text-deck-binding.json", {})
        return binding.get("compiler") in {
            "motif-assembler-v3",
            "evidence-pipeline-v1",
            "evidence-pipeline-v2",
            "evidence-pipeline-v3",
            "evidence-pipeline-v4",
            "evidence-pipeline-v5",
        }

    def compose(self):
        voice = self._voice()
        return voice if self._has_compiled_scene() else voice + "\n\n" + self._scene()

    def example_turns(self):
        """S8이 남긴 실제 문답 묶음(D-0173). 없거나 비어 있으면 None."""
        if self.prompt and load_json(self.prompt / "text-deck-binding.json", {}).get(
            "compiler"
        ) in {
            "evidence-pipeline-v1",
            "evidence-pipeline-v2",
            "evidence-pipeline-v3",
            "evidence-pipeline-v4",
            "evidence-pipeline-v5",
        }:
            return None
        data = load_json(self.prompt / "example-turns.json") if self.prompt else None
        if not isinstance(data, dict) or not data.get("system") or not data.get("turns"):
            return None
        return data

    def opening(self) -> list[Message]:
        """대화 앞에 놓는 메시지. 실제 문답 묶음이 있으면 이전 턴으로 넣는다."""
        data = self.example_turns()
        if not data:
            return [Message("system", self.compose())]
        self._voice()
        messages = [Message("system", data["system"])]
        for turn in data["turns"]:
            messages += [Message("user", turn["user"]), Message("assistant", turn["reply"])]
        return messages

    def readiness(self, *, running=False, draft=False):
        missing, reasons = [], []
        required = [("prompt", self._voice)]
        if not self._has_compiled_scene():
            required.append(("scene", self._scene))
        for key, read in required:
            try:
                read()
            except NotReady as exc:
                missing.append(key)
                reasons.append(str(exc))
        page = "sources" if draft else "factory"
        if missing:
            reasons.append(
                "원문 화면에서 만들기를 시작해 주세요." if draft else "진행 화면에서 확인해 주세요."
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


def base_scenarios(folder=None):
    pack = load_json(folder / "source-pack.json", {}) if folder else {}
    name = {
        "FRIEND_CHAT": "demo-scenarios-friend-v1.json",
        "INTERVIEW": "demo-scenarios-interview-v1.json",
    }.get(pack.get("chapterTemplate"), "demo-scenarios-v1.json")
    return resource(name)


def scenarios(folder=None):
    generic = base_scenarios(folder)
    custom = load_json(folder / "demo/scenarios.json", []) if folder else []
    if isinstance(custom, dict):
        custom = custom["scenarios"]
    return custom + generic


def configured_provider(ctx):
    """Use the same configured provider for samples and interactive dialogue."""
    return ctx.config.providers.get("demo_chat", ctx.config.providers.get("text", DEFAULT))


def provider(ctx, via, server_mode=False):
    cfg = configured_provider(ctx)
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
    if cfg.adapter == "vertex_openai" and (server_mode or os.getenv("CFP_SERVER_MODE") == "1"):
        raise PermissionError("팀 서버에서는 기본 대화 모델을 이용해 주세요.")
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
    scene = Scene.read(ctx.character_dir(cid), review_preview=True)
    opening = scene.opening()
    path = scene.chapter / "samples.json"
    if scene.samples():
        return path
    model = talk_model(ctx, cid, provider(ctx, "studio"))
    temperature = ctx.config.demo_chat_temperature(True)
    samples = []
    for scenario in base_scenarios(scene.folder):
        messages, turns = [*opening], []
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
