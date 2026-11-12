"""모티브 발표 점검(D-0126, 계획 §12 순서 12).

패키지를 만들 때 코드로 확인할 수 있는 필수 항목을 검사해 `presentation-check.json`
(`twin-presentation-check-v1`)을 G9 검토 페이지 옆에 남긴다.

- 필수 자동: (1) "AI 생성 · 본인과 무관한 기술 시연" 표시가 패키지·앱 시드
  (api-svc disclosure_label)·대화(공개 페르소나 프롬프트)에 들어간다. (2) 추천·협력·공식처럼
  보이는 표현이 없다. (4) 사인(PRIVATE_PERSON)의 동의가 기록돼 있고 사용 범위에 발표가 들어간다.
- 사람 확인: (3) 공인 장면을 홍보물·SNS·앱 마케팅에 다시 쓰지 않는다(필수), 공인 측 허락·
  법무 검토·발표 화면의 카톡 가림(권장, 막지 않음). G9 화면 점검표에 붙고 결정 기록에 남는다.

검사 결과 파일에는 동의한 사람 이름이나 원문을 쓰지 않는다. 검사 대상은 이미 공개용으로
정리된 패키지 문구와 생성 프롬프트뿐이다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.release import CharacterPackage
from character_factory_poc.pipeline.context import Context

SCHEMA = "twin-presentation-check-v1"
CHECK_FILE = "presentation-check.json"
DISCLOSURE = "AI 생성 · 본인과 무관한 기술 시연"
#: 공개 페르소나 프롬프트에 붙는 표시 문단(twin.SourceQuotes.public_prompt). 대화 모델이 읽는다.
CHAT_DISCLOSURE = (
    f"[표시] 이 대화 상대는 {DISCLOSURE}이다. "
    "진짜 본인이냐고 물으면 본인이 아니라 AI가 만든 기술 시연이라고 짧게 밝힌다."
)
#: 기본 금지 표현. D-0214: 기본은 비어 있어 추천·협력 표현 검사가 아무것도 막지 않는다.
#: 다시 켜려면 [stages.s11] presentation_banned_terms에 목록을 넣는다(띄어쓰기는 있어도 없어도
#: 잡는다). 예전 기본값: 공식 협력·파트너·후원·승인·인증·계정·캐릭터·콜라보, 본인이 직접, 협찬,
#: 함께한, 추천, official, endorsed.
DEFAULT_BANNED: tuple[str, ...] = ()
#: 금지 표현이 다른 뜻으로 들어간 공통 문구. 찾기 전에 지운다.
#: [stages.s11] presentation_allowed_phrases로 바꾼다.
#: "매 턴 채울 공식이 아니다"는 모든 캐릭터 프롬프트에 붙는 공통 규칙
#: (resources/system-rules-default-v1.md)이고 '정해진 틀'이라는 뜻이다.
DEFAULT_ALLOWED = ("매 턴 채울 공식이 아니다",)
#: 사인 동의 사용 범위에 들어가야 하는 말. [stages.s11] presentation_scope_terms로 바꾼다.
DEFAULT_SCOPE_TERMS = ("발표",)

#: 사람 확인 항목. kinds는 대상 종류, kakao=True면 카톡 내보내기 출처가 있을 때만 붙는다.
HUMAN_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "id": "noReuse",
        "required": True,
        "kinds": ("PUBLIC_FIGURE",),
        "title": "이 캐릭터가 나오는 장면을 홍보물·SNS·앱 마케팅에 다시 쓰지 않아요",
        "detail": "발표 녹화가 공개되면 이 캐릭터가 나오는 구간을 가리거나 빼 달라고 요청해요.",
    },
    {
        "id": "subjectPermission",
        "required": False,
        "kinds": ("PUBLIC_FIGURE",),
        "title": "본인 측 사용 허락을 받았어요",
        "detail": "권장 항목이에요. 받지 않았어도 승인할 수 있어요.",
    },
    {
        "id": "legalReview",
        "required": False,
        "kinds": ("PUBLIC_FIGURE",),
        "title": "법무 검토를 받았어요",
        "detail": "권장 항목이에요. 받지 않았어도 승인할 수 있어요.",
    },
    {
        "id": "chatMasked",
        "required": False,
        "kinds": ("PUBLIC_FIGURE", "PRIVATE_PERSON"),
        "kakao": True,
        "title": "발표 화면에 나오는 카톡에서 다른 참여자를 가렸어요",
        "detail": "권장 항목이에요. 카톡은 비교 세트에서만 골라 보여 줘요.",
    },
)


def _terms(ctx: Context, key: str, default: tuple[str, ...]) -> list[str]:
    value = ctx.config.stage("s11").get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise FactoryError(f"[stages.s11] {key}는 빈칸 없는 문자열 목록이어야 한다")
    return [v.strip() for v in value]


def _term_pattern(terms: Iterable[str]) -> re.Pattern[str]:
    parts = []
    for term in sorted(set(terms), key=len, reverse=True):
        escaped = r"\s*".join(re.escape(word) for word in term.split())
        # 영어 낱말은 앞쪽 경계만 본다(official·officially는 잡고 unofficial은 넘긴다).
        parts.append(r"(?<![A-Za-z])" + escaped if term[:1].isascii() else escaped)
    return re.compile("|".join(parts) or r"(?!)", re.IGNORECASE)


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 18)
    right = min(len(text), end + 18)
    body = " ".join(text[left:right].split())
    return ("…" if left else "") + body + ("…" if right < len(text) else "")


def _scan(
    targets: list[tuple[str, str]], pattern: re.Pattern[str], allowed: list[str]
) -> list[dict[str, str]]:
    hits = []
    for where, text in targets:
        text = text or ""
        masked = text
        for phrase in allowed:
            masked = masked.replace(phrase, " " * len(phrase))
        for match in pattern.finditer(masked):
            hits.append(
                {
                    "where": where,
                    "term": text[match.start() : match.end()],
                    "excerpt": _excerpt(text, match.start(), match.end()),
                }
            )
    return hits


def _video_prompts(ctx: Context, cid: str) -> list[tuple[str, str]]:
    from character_factory_poc.stages.s5_intro.approve import load_approved_intro
    from character_factory_poc.stages.s6_actions.approve import load_approved_actions

    out = []
    intro, intro_dir = load_approved_intro(ctx, cid)
    actions, actions_dir = load_approved_actions(ctx, cid)
    records = [("영상 프롬프트 · 소개", intro_dir / "assets" / f"{intro.video.id}.json")]
    records += [
        (f"영상 프롬프트 · {clip.chapterId} {clip.clipKey}", actions_dir / "assets" / name)
        for clip in actions.clips
        for name in [f"{clip.actionId}-{clip.video.id}.json"]
    ]
    for where, path in records:
        if path.is_file():
            out.append((where, str(read_json(path).get("settings", {}).get("prompt", ""))))
    return out


def _targets(package: CharacterPackage, rev_dir: Path) -> list[tuple[str, str]]:
    p = package.profile
    out = [
        (f"프로필 · {label}", value)
        for label, value in (
            ("이름", p.name),
            ("직업", p.job),
            ("한 줄 소개", p.tagline),
            ("소개", p.description),
            ("취미", p.hobby),
            ("좋아함", p.likes),
            ("싫어함", p.dislikes),
            ("태그", " ".join(p.tags)),
            ("TMI", " / ".join(item.text for item in p.tmiItems)),
        )
    ]
    for chapter in package.chapters:
        out += [
            (f"챕터 {chapter.chapterNo} · 이름", chapter.title),
            (f"챕터 {chapter.chapterNo} · 소개", chapter.intro),
            (f"챕터 {chapter.chapterNo} · 목표", chapter.goal),
        ]
    if package.twin:
        out.append(("시작 버튼", package.twin.startButtonLabel))
    for video in package.videos:
        label = "소개" if video.kind == "INTRO" else f"챕터 {video.chapterNo} {video.clipKey}"
        out.append((f"영상 · {label}", " ".join((video.title, video.description, video.useWhen))))
    for label, rel in (("긴", package.persona.longPrompt), ("짧은", package.persona.shortPrompt)):
        if rel and (rev_dir / rel).is_file():
            out.append((f"페르소나 프롬프트 · {label}", (rev_dir / rel).read_text("utf-8")))
    return out


def _seed_label(package: CharacterPackage, rev_dir: Path) -> tuple[str | None, str]:
    """앱 시드를 실제 내보내기 함수로 만들어 character.disclosure_label 값을 읽는다."""
    from character_factory_poc.stages.export.doki_app import api_svc
    from character_factory_poc.stages.export.settings import API_SVC_HEAD

    try:
        seed = api_svc.build_seed(
            package, rev_dir, exported_at="1970-01-01T00:00:00Z", alembic_revision=API_SVC_HEAD
        )
        table = seed.bundle["tables"]["character"]
        column = table["columns"].index("disclosure_label")
        return table["rows"][0][column], ""
    except Exception as exc:  # noqa: BLE001 - 시드를 못 만들면 점검 실패로 남긴다
        return None, f"앱 시드를 만들지 못했어요({type(exc).__name__})"


def _check(id_: str, title: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {"id": id_, "title": title, "required": True, "ok": ok, "detail": detail, **extra}


def run_checks(ctx: Context, cid: str, rev_dir: Path, package: CharacterPackage) -> dict[str, Any]:
    """모티브 패키지의 자동 점검. 파일은 쓰지 않는다."""
    twin = package.twin
    if twin is None:
        raise FactoryError(f"{cid}: 발표 점검은 모티브 패키지에만 한다")
    root = ctx.character_dir(cid)
    gate = ctx.state(cid).gate("G0")
    source_dir = root / "s0-source" / str(gate.rev)
    pack = read_json(source_dir / "source-pack.json")
    index = read_json(source_dir / "source-index.json")
    kind = pack["subject"]["kind"]

    # (1) 표시: 패키지 · 앱 시드 · 대화
    seed_value, seed_error = _seed_label(package, rev_dir)
    prompts = {
        label: (rev_dir / rel).read_text("utf-8") if rel and (rev_dir / rel).is_file() else None
        for label, rel in (
            ("긴", package.persona.longPrompt),
            ("짧은", package.persona.shortPrompt),
        )
    }
    places = {
        "package": twin.disclosure == DISCLOSURE,
        "appSeed": seed_value == DISCLOSURE,
        "chat": all(DISCLOSURE in text for text in prompts.values() if text is not None)
        and prompts["긴"] is not None,
    }
    names = {"package": "패키지", "appSeed": "앱 시드", "chat": "대화 프롬프트"}
    missing = [names[k] for k, ok in places.items() if not ok]
    disclosure = _check(
        "disclosure",
        "AI 표시",
        not missing,
        seed_error
        or (
            f"'{DISCLOSURE}' 표시가 없는 곳: {', '.join(missing)}"
            if missing
            else "패키지·앱 시드·대화 프롬프트에 모두 들어가요"
        ),
        places=places,
    )

    # (2) 추천·협력·공식처럼 보이는 표현
    banned = _terms(ctx, "presentation_banned_terms", DEFAULT_BANNED)
    allowed = _terms(ctx, "presentation_allowed_phrases", DEFAULT_ALLOWED)
    hits = _scan(
        _targets(package, rev_dir) + _video_prompts(ctx, cid), _term_pattern(banned), allowed
    )
    endorsement = _check(
        "endorsement",
        "추천·협력 표현",
        not hits,
        f"{len(hits)}곳에서 찾았어요: "
        + ", ".join(sorted({f"{h['where']}('{h['term']}')" for h in hits})[:6])
        if hits
        else (
            f"표현 {len(banned)}개를 프로필·소개·챕터·시작 버튼·영상·페르소나 프롬프트에서 "
            "찾지 못했어요"
            if banned
            else "찾는 표현이 없어 막지 않아요"
        ),
        terms=banned,
        allowed=allowed,
        hits=hits[:50],
    )

    # (4) 사인 발표 공개 동의
    basis = pack["usageBasis"]
    scope_terms = _terms(ctx, "presentation_scope_terms", DEFAULT_SCOPE_TERMS)
    scope = str(basis.get("scope") or "")
    if kind == "PRIVATE_PERSON":
        recorded = bool(
            str(basis.get("consentBy") or "").strip() and str(basis.get("consentDate") or "")
        )
        covers = any(term in scope for term in scope_terms)
        problem = (
            "동의한 사람·날짜가 출처 묶음에 없어요"
            if not recorded
            else f"사용 범위('{scope}')에 {'·'.join(scope_terms)}이 없어요"
            if not covers
            else ""
        )
        consent = _check(
            "consent",
            "공개 동의",
            not problem,
            problem or f"동의 기록이 있고 사용 범위('{scope}')에 발표가 들어가요",
            applies=True,
        )
    else:
        consent = _check(
            "consent",
            "공개 동의",
            True,
            "공인이라 본인 동의 기록 대신 사람 확인 항목으로 점검해요",
            applies=False,
        )

    kakao = any(t.get("kind") == "KAKAO_EXPORT" for t in index.get("texts", []))
    human = [
        {k: item[k] for k in ("id", "required", "title", "detail")}
        for item in HUMAN_ITEMS
        if kind in item["kinds"] and (kakao or not item.get("kakao"))
    ]
    checks = [disclosure, endorsement, consent]
    return {
        "schemaVersion": SCHEMA,
        "characterId": cid,
        "packageRev": package.packageRev,
        "subjectKind": kind,
        "disclosure": DISCLOSURE,
        "status": "PASS" if all(c["ok"] for c in checks) else "FAIL",
        "checks": checks,
        "humanChecks": human,
    }


def write_check(ctx: Context, cid: str, rev_dir: Path, package: CharacterPackage) -> Path:
    """S11이 모티브 패키지를 만든 직후 부른다. 필수 항목이 실패해도 파일만 남기고 G9가 막는다."""
    path = rev_dir / CHECK_FILE
    write_once_json(path, run_checks(ctx, cid, rev_dir, package))
    return path


def view(rev_dir: Path, package: dict[str, Any]) -> dict[str, Any] | None:
    """G9 화면용. 오리지널 패키지는 None이다."""
    if not package.get("twin"):
        return None
    data = read_json(rev_dir / CHECK_FILE) if (rev_dir / CHECK_FILE).is_file() else None
    if not data:
        return {
            "status": "MISSING",
            "disclosure": DISCLOSURE,
            "checks": [
                _check(
                    "presentation",
                    "발표 점검",
                    False,
                    "발표 점검 결과가 없어요. 패키지를 다시 만들어 주세요.",
                )
            ],
            "humanChecks": [],
        }
    return {k: data[k] for k in ("status", "disclosure", "subjectKind", "checks", "humanChecks")}


def guard_g9(
    ctx: Context, cid: str, rev_dir: Path, answer: dict[str, Any]
) -> tuple[list[Path], str]:
    """G9 결정 전에 부른다. 모티브 APPROVE는 필수 점검이 통과해야 받는다.

    돌려주는 값: 결정 기록 shownArtifacts에 더할 파일, reasons에 붙일 사람 확인 요약.
    오리지널 패키지는 ([], "")라 기존 G9가 그대로다.
    """
    package = read_json(rev_dir / "package.json")
    if not package.get("twin"):
        return [], ""
    path = rev_dir / CHECK_FILE
    if not path.is_file():
        if answer.get("decision") == "APPROVE":
            raise FactoryError(f"{cid}: 발표 점검 결과({CHECK_FILE})가 없어 승인할 수 없다")
        return [], ""
    data = read_json(path)
    if answer.get("decision") != "APPROVE":
        return [path], ""
    if data.get("packageRev") != package.get("packageRev"):
        raise FactoryError(f"{cid}: 발표 점검이 다른 패키지 판을 가리킨다")
    failed = [c["title"] for c in data["checks"] if c.get("required") and not c.get("ok")]
    if failed or data.get("status") != "PASS":
        raise FactoryError(f"{cid}: 발표 점검 필수 항목이 통과하지 않았다: {', '.join(failed)}")
    given = answer.get("presentationChecks") or {}
    if not isinstance(given, dict):
        raise FactoryError("presentationChecks는 {항목 ID: true/false} 객체여야 한다")
    left = [
        h["title"] for h in data["humanChecks"] if h["required"] and given.get(h["id"]) is not True
    ]
    if left:
        raise FactoryError(f"{cid}: 발표 점검 사람 확인이 빠졌다: {'; '.join(left)}")
    note = "발표 점검: 자동 {}개 통과".format(len(data["checks"]))
    if data["humanChecks"]:
        note += " · 사람 확인 " + " / ".join(
            ("[예] " if given.get(h["id"]) is True else "[아니오] ") + h["title"]
            for h in data["humanChecks"]
        )
    return [path], note


__all__ = [
    "CHAT_DISCLOSURE",
    "CHECK_FILE",
    "DISCLOSURE",
    "guard_g9",
    "run_checks",
    "view",
    "write_check",
]
