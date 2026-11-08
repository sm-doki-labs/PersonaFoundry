"""출처 원문 읽기·정리 (계획 §4, D-0120). 모델을 부르지 않는 결정적 함수만 둔다.

- 카톡 내보내기: PC 텍스트(날짜 구분선 + "[이름] [오전 9:12] 내용"), 모바일 텍스트
  ("2026년 11월 1일 오전 9:12, 이름 : 내용" 또는 "2026. 11. 1. 오전 9:12, 이름 : 내용"),
  CSV(Date,User,Message).
- 인터뷰·녹취: "화자: 발화" 줄. 기사: 문단, 따옴표 안 문장은 대상 인물의 인용으로 본다.
- 가리기: 전화번호·이메일·계좌 모양 번호, 다른 참여자 이름.
- 대화 나누기와 비교 세트: 시간 간격으로 대화를 나누고, 질문 → 대상 인물 답이 있는 대화 가운데
  날짜 뒤쪽 일부를 대화 단위로 떼어 둔다.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from character_factory_poc.contracts.source import SourcePack, SourceText

MEDIA = {
    "사진",
    "동영상",
    "이모티콘",
    "(이모티콘)",
    "삭제된 메시지입니다.",
    "음성메시지",
    "보이스톡 해요.",
    "페이스톡 해요.",
}

_PC_DATE = re.compile(r"^-{3,}\s*(\d{4})년 (\d{1,2})월 (\d{1,2})일")
_PC_MSG = re.compile(
    r"^\[(?P<name>[^\]]+)\] \[(?P<ampm>오전|오후) (?P<h>\d{1,2}):(?P<m>\d{2})\] (?P<text>.*)$"
)
_MOBILE_MSG = re.compile(
    r"^(?P<y>\d{4})(?:년|\.)\s*(?P<mo>\d{1,2})(?:월|\.)\s*(?P<d>\d{1,2})(?:일|\.)?\s*"
    r"(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<m>\d{2}),\s*(?P<rest>.*)$"
)
_MOBILE_DATE_ONLY = re.compile(
    r"^\d{4}(?:년|\.)\s*\d{1,2}(?:월|\.)\s*\d{1,2}(?:일|\.)?\s*\S*요일\s*$"
)
_SPEAKER_LINE = re.compile(r"^(?P<name>[^:：\n]{1,24}?)\s*[:：]\s*(?P<text>.+)$")
_QUOTE = re.compile(r"[“\"]([^”\"]{4,})[”\"]")

_PHONE = re.compile(r"(?:\+82[-\s]?)?0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ACCOUNT = re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,8}\b")


@dataclass
class Msg:
    textId: str
    seq: int
    at: datetime | None
    name: str
    text: str
    speaker: str = "OTHER"
    convId: str = ""
    quote: bool = False
    extra_lines: list[str] = field(default_factory=list)

    @property
    def msgId(self) -> str:
        return f"{self.textId}-{self.seq:05d}"

    def as_row(self) -> dict:
        return {
            "msgId": self.msgId,
            "textId": self.textId,
            "convId": self.convId,
            "at": self.at.isoformat(timespec="minutes") if self.at else None,
            "speaker": self.speaker,
            "name": self.name,
            "text": self.text,
        }


class SourceError(ValueError):
    """원문 형식·화자 지정 문제. s0는 CheckFailed로 바꿔 알린다."""


def _clock(ampm: str, h: str, m: str) -> tuple[int, int]:
    hour = int(h) % 12
    if ampm == "오후":
        hour += 12
    return hour, int(m)


def read_kakao(text_id: str, raw: str) -> list[Msg]:
    raw = raw.lstrip("\ufeff")
    first = raw.splitlines()[0] if raw.strip() else ""
    if first.replace(" ", "").lower().startswith("date,user,message"):
        return _read_kakao_csv(text_id, raw)
    msgs: list[Msg] = []
    day: tuple[int, int, int] | None = None
    for line in raw.splitlines():
        if m := _PC_DATE.match(line):
            day = (int(m[1]), int(m[2]), int(m[3]))
            continue
        if (m := _PC_MSG.match(line)) and day is not None:
            hh, mm = _clock(m["ampm"], m["h"], m["m"])
            msgs.append(
                Msg(text_id, len(msgs) + 1, datetime(*day, hh, mm), m["name"].strip(), m["text"])
            )
            continue
        if m := _MOBILE_MSG.match(line):
            rest = m["rest"]
            if " : " not in rest:
                continue  # 들어옴·나감 같은 시스템 줄
            name, body = rest.split(" : ", 1)
            hh, mm = _clock(m["ampm"], m["h"], m["m"])
            at = datetime(int(m["y"]), int(m["mo"]), int(m["d"]), hh, mm)
            msgs.append(Msg(text_id, len(msgs) + 1, at, name.strip(), body))
            continue
        if _MOBILE_DATE_ONLY.match(line.strip()) or not msgs:
            continue  # 머리말·날짜 줄
        if line.strip():
            msgs[-1].text += "\n" + line
    return [m for m in msgs if m.text.strip() not in MEDIA and not m.text.startswith("파일:")]


def _read_kakao_csv(text_id: str, raw: str) -> list[Msg]:
    msgs: list[Msg] = []
    for row in csv.DictReader(io.StringIO(raw)):
        row = {k.strip().lower(): (v or "") for k, v in row.items() if k}
        body = row.get("message", "")
        if not body.strip() or body.strip() in MEDIA:
            continue
        try:
            at = datetime.fromisoformat(row.get("date", "").strip())
        except ValueError as e:
            raise SourceError(f"{text_id}: CSV 날짜를 읽지 못했다: {row.get('date')!r}") from e
        msgs.append(Msg(text_id, len(msgs) + 1, at, row.get("user", "").strip(), body))
    return msgs


def read_dialogue(text_id: str, raw: str, date: str | None) -> list[Msg]:
    """인터뷰·녹취: "화자: 발화" 줄. 화자 없는 줄은 앞 발화에 잇는다."""
    at = datetime.fromisoformat(date) if date else None
    msgs: list[Msg] = []
    for line in raw.lstrip("\ufeff").splitlines():
        if not line.strip():
            continue
        if m := _SPEAKER_LINE.match(line.strip()):
            msgs.append(Msg(text_id, len(msgs) + 1, at, m["name"].strip(), m["text"].strip()))
        elif msgs:
            msgs[-1].text += "\n" + line.strip()
    return msgs


def read_article(text_id: str, raw: str, date: str | None, subject_name: str) -> list[Msg]:
    """기사: 문단은 기자 서술(OTHER), 따옴표 안 문장은 대상 인물의 인용(SUBJECT 후보)."""
    at = datetime.fromisoformat(date) if date else None
    msgs: list[Msg] = []
    for para in re.split(r"\n\s*\n", raw.lstrip("\ufeff")):
        para = para.strip()
        if not para:
            continue
        msgs.append(Msg(text_id, len(msgs) + 1, at, "기자", para))
        for q in _QUOTE.findall(para):
            msgs.append(Msg(text_id, len(msgs) + 1, at, subject_name, q.strip(), quote=True))
    return msgs


def assign_speakers(msgs: list[Msg], spec: SourceText, subject_name: str) -> None:
    names = sorted({m.name for m in msgs})
    if spec.kind == "ARTICLE":
        for m in msgs:
            m.speaker = "SUBJECT" if m.quote else "OTHER"
        return
    subject = spec.subjectSpeaker
    if not subject:
        raise SourceError(
            f"{spec.textId}: subjectSpeaker가 필요하다(원문 화자: {', '.join(names)})"
        )
    if subject not in names:
        raise SourceError(
            f"{spec.textId}: subjectSpeaker {subject!r}가 원문에 없다"
            f"(원문 화자: {', '.join(names)})"
        )
    user = spec.userSpeaker
    if spec.kind == "KAKAO_EXPORT" and not user:
        others = [n for n in names if n != subject]
        if len(others) == 1:
            user = others[0]
    if user and user not in names:
        raise SourceError(f"{spec.textId}: userSpeaker {user!r}가 원문에 없다")
    for m in msgs:
        if m.name == subject:
            m.speaker = "SUBJECT"
        elif spec.kind in {"INTERVIEW", "TRANSCRIPT"} or m.name == user:
            m.speaker = "USER"  # 인터뷰에서는 질문자가 대화 상대다
        else:
            m.speaker = "OTHER"


def mask(msgs: list[Msg]) -> dict[str, int]:
    """전화번호·이메일·계좌 모양 번호와 다른 참여자 이름을 가린다. 종류별 개수를 돌려준다."""
    counts = {"phone": 0, "email": 0, "account": 0, "participant": 0}
    others = sorted({m.name for m in msgs if m.speaker == "OTHER" and m.name != "기자"})
    alias = {name: f"참여자{i + 1}" for i, name in enumerate(others)}
    for m in msgs:
        text = m.text
        for key, pattern, repl in (
            ("email", _EMAIL, "[이메일]"),
            ("phone", _PHONE, "[전화번호]"),
            ("account", _ACCOUNT, "[번호]"),
        ):
            text, n = pattern.subn(repl, text)
            counts[key] += n
        for name, label in alias.items():
            if len(name) >= 2 and name in text:
                counts["participant"] += text.count(name)
                text = text.replace(name, label)
        m.text = text
        if m.name in alias:
            m.name = alias[m.name]
    counts["otherParticipants"] = len(alias)
    return counts


def segment(msgs: list[Msg], spec: SourceText, gap_hours: float) -> int:
    """대화 단위를 정한다. 카톡은 시간 간격, 인터뷰·녹취는 질문마다, 기사는 파일 하나."""
    n = 0
    prev: Msg | None = None
    for m in msgs:
        new = prev is None
        if spec.kind == "KAKAO_EXPORT" and prev is not None and m.at and prev.at:
            new = m.at - prev.at > timedelta(hours=gap_hours)
        elif spec.kind in {"INTERVIEW", "TRANSCRIPT"} and prev is not None:
            new = m.speaker == "USER" and prev.speaker == "SUBJECT"
        if new:
            n += 1
        m.convId = f"{spec.textId}-c{n:04d}"
        prev = m
    return n


def _has_exchange(conv: list[Msg]) -> bool:
    pairs = zip(conv, conv[1:], strict=False)
    return any(a.speaker == "USER" and b.speaker == "SUBJECT" for a, b in pairs)


def split_holdout(msgs: list[Msg], fraction: float) -> tuple[list[Msg], list[Msg]]:
    """질문 → 대상 인물 답이 있는 대화 가운데 날짜 뒤쪽 비율만큼을 대화 단위로 떼어 둔다."""
    convs: dict[str, list[Msg]] = {}
    for m in msgs:
        convs.setdefault(m.convId, []).append(m)
    eligible = [cid for cid, conv in convs.items() if _has_exchange(conv)]
    if len(eligible) < 2:
        return list(msgs), []
    order = {cid: i for i, cid in enumerate(convs)}

    def key(cid: str) -> tuple[str, int]:
        times = [m.at for m in convs[cid] if m.at]
        return (max(times).isoformat() if times else "", order[cid])

    eligible.sort(key=key)
    k = max(1, round(fraction * len(eligible)))
    held = set(eligible[-k:])
    return [m for m in msgs if m.convId not in held], [m for m in msgs if m.convId in held]


def usage_problems(pack: SourcePack) -> list[str]:
    """사용 근거가 비면 G0 승인을 잠근다(D-0120, D-0126)."""
    basis = pack.usageBasis
    problems: list[str] = []
    if not basis.scope.strip():
        problems.append("usageBasis.scope(사용 범위)가 비었다")
    if pack.subject.kind == "PRIVATE_PERSON":
        if not (basis.consentBy or "").strip():
            problems.append("사인(PRIVATE_PERSON)은 usageBasis.consentBy(동의한 사람)가 필요하다")
        if not (basis.consentDate or "").strip():
            problems.append("사인(PRIVATE_PERSON)은 usageBasis.consentDate(동의 날짜)가 필요하다")
    return problems
