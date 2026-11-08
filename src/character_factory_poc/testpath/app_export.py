# ruff: noqa: E501
"""시험 경로 8번: 시험 경로 산출물을 character-package-v1 모양으로 묶어 기존 앱 변환기에 넣는다.

정식 S11 패키지는 G4·G5·G5b·G8·G9 승인을 요구한다. 시험 경로는 그 관문을 거치지 않으므로
같은 계약(CharacterPackage)을 직접 채우고, 변환기(api-svc 시드·chat-svc 콘텐츠 트리)는 그대로 쓴다.
페르소나 여덟 섹션은 S8 긴 프롬프트(long.md)의 [PERSONA / ...] 블록을 그대로 옮긴다.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.release import (
    Appearance,
    Chapter,
    CharacterPackage,
    PackageFile,
    Persona,
    Profile,
    TmiItem,
    Video,
)
from character_factory_poc.stages.export.doki_app import api_svc, chat_svc

SECTION_KEYS = {
    "FACTS": "facts",
    "LIFE_AND_TASTES": "lifeAndTastes",
    "DISPOSITION": "disposition",
    "WANTS_AND_FEARS": "wantsAndFears",
    "READING_AND_TENSION": "readingAndTension",
    "CHOICES": "choices",
    "VOICE": "voice",
    "KNOWS_AND_LIMITS": "boundaries",
}


def persona_sections(long_md: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"^\[PERSONA / ([A-Z_]+)\]\n(.*?)(?=^\[|\Z)", long_md, re.S | re.M):
        key = SECTION_KEYS.get(m.group(1))
        if key:
            lines = [ln.strip() for ln in m.group(2).splitlines() if ln.strip()]
            out[key] = lines
    missing = [k for k in SECTION_KEYS.values() if k not in out]
    if missing:
        raise ValueError(f"긴 프롬프트에 페르소나 섹션이 없다: {missing}")
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_package(
    *,
    out_dir: Path,
    character_id: str,
    char_dir: Path,
    hero: Path,
    chapters: list[dict[str, Any]],
    videos: list[dict[str, Any]],
) -> tuple[CharacterPackage, Path]:
    """chapters: [{chapterNo, chapterId, title, stage, intro, goal, frame(Path), facts(dict)}]
    videos: [{file(Path), clipKey, chapterNos, title, description, useWhen, expression, provider}]"""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    files: list[PackageFile] = []

    def put(src: Path | None, rel: str, data: bytes | None = None) -> str:
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if data is not None:
            dest.write_bytes(data)
        else:
            shutil.copyfile(src, dest)
        files.append(PackageFile(path=rel, sha256=_sha(dest), bytes=dest.stat().st_size))
        return rel

    plan = json.loads(
        (char_dir / "s3-plan" / _latest(char_dir / "s3-plan", "pr") / "plan.json").read_text(
            "utf-8"
        )
    )
    pv = _latest(char_dir / "s8-prompts", "pv")
    long_md = (char_dir / "s8-prompts" / pv / "long.md").read_text("utf-8")
    tr = _latest(char_dir / "s7-traits", "tr")
    card = plan.get("profileCard") or {}
    profile = Profile(
        name=plan["name"],
        gender="female" if plan.get("gender") in ("female", "여성", "F") else "female",
        age=str(plan["age"]),
        job=plan.get("job", ""),
        tagline=plan.get("tagline", ""),
        description=plan.get("background", ""),
        hobby=card.get("hobby", ""),
        likes=card.get("likes", ""),
        dislikes=card.get("dislikes", ""),
        tags=list(card.get("tags") or [])[:4],
        tmiItems=[
            TmiItem(text=t["text"], revealStage=int(t.get("revealStage", 0)))
            for t in card.get("tmi") or []
        ],
    )
    hero_rel = put(hero, "appearance/hero.png")
    chs = []
    for c in chapters:
        frame_rel = put(c["frame"], f"chapters/{c['chapterId']}/frame.png")
        facts_rel = put(
            None,
            f"chapters/{c['chapterId']}/facts.json",
            json.dumps(c["facts"], ensure_ascii=False, indent=2).encode(),
        )
        chs.append(
            Chapter(
                chapterNo=c["chapterNo"],
                chapterId=c["chapterId"],
                title=c["title"],
                relationshipStage=c["stage"],
                intro=c["intro"],
                goal=c["goal"],
                facts=facts_rel,
                frame=frame_rel,
                background=c.get("background", ""),
            )
        )
    vids = []
    for v in videos:
        rel = put(v["file"], f"videos/{v['file'].name}")
        seconds = float(v.get("durationS", 6.0))
        if v.get("intro"):
            vids.append(
                Video(
                    videoId=f"intro-{v['clipKey']}",
                    kind="INTRO",
                    title="소개 영상",
                    description=v["description"],
                    durationS=seconds,
                    file=rel,
                    provider=v["provider"],
                    synthetic=False,
                )
            )
        for n in v["chapterNos"]:
            vids.append(
                Video(
                    videoId=f"{v['clipKey']}-ch{n}",
                    kind="ACTION",
                    chapterNo=n,
                    clipKey=v["clipKey"],
                    title=v["title"],
                    description=v["description"],
                    useWhen=v.get("useWhen", ""),
                    expression=v.get("expression", ""),
                    durationS=seconds,
                    file=rel,
                    provider=v["provider"],
                    synthetic=False,
                )
            )
    sheet_rel = put(char_dir / "s7-traits" / tr / "trait-sheet.json", "persona/trait-sheet.json")
    long_rel = put(char_dir / "s8-prompts" / pv / "long.md", "persona/long.md")
    package = CharacterPackage(
        characterId=character_id,
        packageRev="pk1",
        builtAt=datetime.now(UTC).isoformat(timespec="seconds"),
        profile=profile,
        appearance=Appearance(
            appearanceRev="testpath-s07",
            heroImage=hero_rel,
            spec="시험 경로 베이스 시드 s07(GPT Image 2.6)",
        ),
        chapters=chs,
        videos=vids,
        persona=Persona(personaVersion=pv, traitSheet=sheet_rel, longPrompt=long_rel),
        gates=[],
        files=files,
    )
    (out_dir / "package.json").write_text(
        json.dumps(dump(package), ensure_ascii=False, indent=2), "utf-8"
    )
    return package, long_md


def _latest(parent: Path, prefix: str) -> str:
    revs = sorted(
        (p.name for p in parent.iterdir() if re.fullmatch(prefix + r"\d+", p.name)),
        key=lambda n: int(n[len(prefix) :]),
    )
    return revs[-1]


def convert(
    package: CharacterPackage, package_dir: Path, long_md: str, out_dir: Path, *, api_head: str
) -> dict[str, Any]:
    seed = api_svc.build_seed(
        package,
        package_dir,
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
        alembic_revision=api_head,
    )
    tree = chat_svc.build_tree(package, package_dir)
    sections = persona_sections(long_md)
    for path, payload in tree.files.items():
        if path.startswith("personas/"):
            payload.update(sections)
    problems = [
        *api_svc.validate_seed_bundle(seed.bundle),
        *chat_svc.validate_content_tree(tree.files),
    ]
    if problems:
        raise ValueError("변환 결과 검사 실패: " + "; ".join(problems[:8]))
    seed_path = out_dir / "api-svc" / "seed.json"
    api_svc.write_seed(seed_path, seed.bundle)
    chat_svc.write_tree(out_dir / "chat-svc", tree)
    return {
        "seed": str(seed_path),
        "tree": str(out_dir / "chat-svc"),
        "unmapped": [*seed.unmapped, *tree.unmapped],
    }
