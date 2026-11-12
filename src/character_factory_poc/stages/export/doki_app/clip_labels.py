"""앱 통화 클립의 jev 선택 라벨 — 반응 키워드와 공장이 지은 몸짓의 '이럴 때' 문구.

api-svc 는 통화 중 몸짓을 jev(OpenCode Zen, CLIP_PICK_LLM_PROVIDER=opencode)로 고른다. 후보 한 줄은
"제목 | 밝음/어두움 | 설명 | 이럴 때: use_when" 이고(api-svc clip_picker._describe), 후보에는
clip_mode 가 emotion 인 클립만 들어간다(routes/characters.py). 그래서

- 자동으로 골라야 하는 몸짓은 pick_role=emotion 으로 낸다. 모르는 이름은 special 로 떨어져
  후보에서 빠진다(clip_taxonomy.mode).
- use_when 은 운영 감정 세트(api-svc data/call_clips.json)와 같은 모양으로 쓴다:
  "감정 — 상황. 상대가 하는 말 예: 「…」. 틀지 않는다: 다른 상황 → 다른 몸짓".
  '틀지 않는다' 에는 이 캐릭터에게 실제로 있는 몸짓만 가리킨다.
- 반응 키워드(character_clip_trigger)는 운영 세트처럼 감정 클립마다 이름 첫 낱말 하나다
  (amused_good_strong → amused). 대기·말하기에는 없다. jev 후보 줄에는 들어가지 않는다.

영상 만들기(s6)의 useWhen 은 바꾸지 않는다 — 그 값이 바뀌면 시그니처 영상을 다시 만든다
(catalog.signature_matches). 이 모듈은 내보낼 때만 문구를 바꾼다.
"""

from __future__ import annotations

from collections.abc import Iterable

from character_factory_poc.contracts.release import Video
from character_factory_poc.stages.s6_actions.catalog import SIGNATURE_KEY

#: 모티브 Lite(D-0191, call_loop.RECIPES)의 반응 몸짓. 앱 감정 세트에 없는 이름이라 직접 적는다.
CALL_LOOP_REACTIONS = frozenset({"cheering_good", "laughing_good", "greeting_good"})
_SIGNATURE_DEFAULTS = (
    "반가운 인사, 축하, 자기를 대표하는 순간을 이야기할 때.",
    "이 인물을 대표하는 동작을 요청할 때.",
)


def is_structural(clip_key: str) -> bool:
    return clip_key.startswith(("idle", "speak")) or clip_key.endswith("_talking")


def trigger_of(clip_key: str) -> str | None:
    """운영 감정 세트 규칙: 이름 첫 낱말. 대기·말하기는 없다."""
    if not clip_key or is_structural(clip_key):
        return None
    return clip_key.split("_", 1)[0]


def _present(videos: Iterable[Video]) -> set[str]:
    return {trigger_of(v.clipKey) for v in videos if trigger_of(v.clipKey)}


def _avoid(present: set[str], rules: list[tuple[str, tuple[str, ...]]]) -> str:
    """'틀지 않는다' 줄. 가리킬 몸짓이 이 캐릭터에게 없으면 그 상황은 영상 없이 둔다."""
    parts = []
    for situation, candidates in rules:
        target = next((c for c in candidates if c in present), None)
        parts.append(f"{situation} → {target or '영상 없이 idle'}")
    parts.append("평범한 안부·일상 대화 → 영상 없이 idle")
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return " · ".join(seen)


def _signature_hint(video: Video) -> str:
    """s6 가 만든 문구에서 사용자가 적은 '이럴 때' 만 꺼낸다."""
    text = (video.useWhen or "").strip()
    prefix = f"{video.title.strip()} — 이 사람을 대표하는 시그니처 포즈."
    if text.startswith(prefix):
        text = text[len(prefix) :].strip()
    return "" if text in _SIGNATURE_DEFAULTS else text


def signature_use_when(video: Video, present: set[str]) -> str:
    title = video.title.strip() or "시그니처 포즈"
    hint = _signature_hint(video)
    return (
        f"시그니처 — {title}. 이 사람을 대표하는 포즈라 아껴 쓴다(한 통화에 한두 번). 이럴 때만: "
        "상대가 이 포즈나 그 이름을 말하며 보여 달라고 할 때, 상대가 팬이라며 크게 반가워할 때, "
        "상대나 이 사람의 큰 좋은 일(우승·골·합격·승리)을 함께 크게 기뻐할 때."
        + (f" 그 밖에: {hint.rstrip('.')}." if hint else "")
        + f" 상대가 하는 말 예: 「{title} 해 주세요」 · 「그 포즈 한 번만 보여 주세요」 · "
        "「저 완전 팬이에요!」 · 「저 합격했어요!」. 틀지 않는다: "
        + _avoid(
            present,
            [
                ("첫인사·작별 인사", ("greeting", "glad")),
                ("가벼운 농담", ("laughing", "amused")),
                ("도전을 앞둔 응원", ("cheering", "encouraging")),
                ("칭찬을 받았다", ("shy",)),
            ],
        )
    )


def _call_loop_use_when(clip_key: str, present: set[str]) -> str:
    if clip_key == "greeting_good":
        return (
            "인사 — 통화가 연결된 첫 턴, 또는 상대가 먼저 인사하거나 작별 인사를 할 때만. "
            "한 통화에 처음 한 번, 끝날 때 한 번. "
            "상대가 하는 말 예: 「안녕하세요」 · 「처음 뵙겠습니다」 · "
            "「오늘 고마웠어요, 들어가세요」. 틀지 않는다: "
            + _avoid(present, [("상대가 팬이라며 크게 반가워하거나 포즈를 청한다", ("signature",))])
        )
    if clip_key == "laughing_good":
        return (
            "웃음 — 상대가 웃기려고 한 말·귀여운 실수·재미있는 일화가 실제로 웃기다. 캐릭터 대사에 "
            "웃음(ㅋㅋ·하하)이 있다. 상대가 하는 말 예: 「(농담)」 · "
            "「경기 보다가 소리 질러서 혼났어요」 · 「저 오늘 길에서 넘어졌어요 ㅋㅋ」. "
            "틀지 않는다: "
            + _avoid(
                present,
                [
                    ("그냥 기분 좋은 대화·칭찬", ()),
                    ("좋은 소식을 함께 크게 기뻐한다", ("signature", "joy")),
                    ("상대가 진지하게 고민을 털어놓는다", ("sympathy",)),
                ],
            )
        )
    if clip_key == "cheering_good":
        return (
            "응원 — 상대가 시험·면접·경기·새 도전을 앞두고 있거나 자신 없어 한다. 시점이 미래다. "
            "캐릭터 대사가 할 수 있어·화이팅·응원할게. 상대가 하는 말 예: 「내일 시험이에요」 · "
            "「저 잘할 수 있을까요?」 · 「힘 좀 주세요」. 틀지 않는다: "
            + _avoid(
                present,
                [
                    ("이미 끝난 좋은 결과", ("signature", "joy")),
                    ("이미 겪은 힘든 일을 털어놓는다", ("sympathy",)),
                    ("농담", ("laughing", "amused")),
                ],
            )
        )
    raise KeyError(clip_key)


def jev_use_when(video: Video, videos: Iterable[Video]) -> str | None:
    """공장이 지은 몸짓이면 jev 용 문구, 아니면 None(s6 문구 그대로)."""
    if video.clipKey == SIGNATURE_KEY:
        return signature_use_when(video, _present(videos))
    if video.clipKey in CALL_LOOP_REACTIONS:
        return _call_loop_use_when(video.clipKey, _present(videos))
    return None


__all__ = [
    "CALL_LOOP_REACTIONS",
    "is_structural",
    "jev_use_when",
    "signature_use_when",
    "trigger_of",
]
