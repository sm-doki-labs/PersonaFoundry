# ruff: noqa: E501
"""D-0149: 말로 나가는 답에 섞인 작성 메모를 걸러 다시 생성한다. 예시는 실제로 나온 답이다."""

from character_factory_poc.common.reply_guard import guarded, memo_reason

LEAKS = [
    "상대 장난/놀림 경향: 웃으며 길게 받지 않고 정색한 척 한두 마디로 맞받아침.\n"
    "말투: '뭐', '이제', 짧고 단호하게, 60자 안팎, 존댓말.그거는 제가 이기죠.",
    "상대가 나이/외모 놀림(장난)을 건넴 -> 정색한 척 한두 마디로 맞받아치거나 사실을 바로잡는 척 받아침.",
    "경향: 상대가 장난이나 놀림을 건넬 때 → 웃으며 길게 받지 않고 정색한 척 맞받아친다. 답변 구상: 아직 서른넷인데요.",
    "상대가 장난/외모/나이 놀림을 건넴.\n페르소나: 웃으며 길게 받지 않고 정색한 척. 아직 서른넷인데요.",
    "아, 게임에서는 치달(치고 달리기) 키만 잘 누르면 솔직히 저보다 훨씬 쉽게 넣으시던데요.",
]
CLEAN = [
    "그거는 사실 운이 좋았어요. 다들 엄청 많이 제쳤다고 하시는데 실제로 제친 수비는 두 명뿐이에요, 두 명.",
    "서른넷이에요, 서른넷. 아직 중반 아니고 초반이라고 우길 거예요.",
    "마지막은 아니에요, 은퇴 발표한 적 없고 다시 돌아와서 뛸 거예요. 뛸 거예요, 꼭.",
    "동네에서 '좀' 하신다는 그 말, 저는 못 믿겠는데요. 그렇게 말하는 분들이 제일 무섭더라고요.",
    "날씨는 진짜 최고예요. 제가 더위보다 추위를 훨씬 못 견디거든요, 런던 겨울은 뭐 너무 춥고 축축해서 고생 많이 했어요.",
    "체코는 이겼는데 멕시코랑 남아공한테 1대0으로 지면서 조 3위로 끝나니까 마음이 많이 아팠죠.",
]


def test_flags_observed_memo_leaks_and_parentheses():
    assert all(memo_reason(t) for t in LEAKS)


def test_passes_ordinary_spoken_replies():
    assert [t for t in CLEAN if memo_reason(t)] == []


def test_guarded_regenerates_until_clean():
    seq = iter([LEAKS[0], LEAKS[2], CLEAN[0]])
    text, rejected = guarded(lambda i: next(seq))
    assert text == CLEAN[0]
    assert [r["attempt"] for r in rejected] == [1, 2]


def test_guarded_gives_up_after_max_tries_and_records_all():
    text, rejected = guarded(lambda i: LEAKS[1], max_tries=2)
    assert text == LEAKS[1] and len(rejected) == 2
