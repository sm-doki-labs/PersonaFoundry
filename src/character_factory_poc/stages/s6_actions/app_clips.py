# ruff: noqa: E501
"""앱 통화 영상 표준 세트 카탈로그 (D-0040).

출처: api-svc `data/call_clips.json`의 캐릭터 9 · 2단계 · e51 세트(2026-10-22 사본)와
`app/services/character/clip_taxonomy.py`의 USE_WHEN(클립 자체 문구가 있으면 그것). 이름(`key`)은
앱 `clip_key`와 같다. 움직임 문장(`motion`)은 앱 이미지 파이프라인이 실제로 쓴 지시문 그대로다.
공장이 덧붙이는 관계 단계 메모와 공통 규칙은 catalog.py가 붙인다. 앱 세트가 바뀌면 다시 만든다.
"""

from __future__ import annotations

# 공개된 감정 세트 17벌 모두에 있는 32편(대기 2편 포함) + 16벌에 있는 무표정 출발 5편 = 37편
APP_CLIPS: list[dict[str, str]] = [
    {
        "key": "idle_good",
        "playType": "idle",
        "mood": "good",
        "title": "기본 대기 (미소)",
        "description": "입꼬리가 조용히 올라간 편안한 미소. 눈가가 부드럽다. 얕게 숨 쉬고 가끔 눈을 깜빡인다",
        "useWhen": "",
        "motion": "Sit calmly and naturally as if quietly waiting on a video call. Tiny natural "
        "motions only: quick natural blinks, a barely-visible shift of weight, one or two "
        "small subtle head movements. Quiet, shallow breathing that barely moves the "
        "shoulders. Keep both hands where they are in the reference image and do not move "
        "them. Keep the exact expression of the reference image throughout. Perform the "
        "movements quickly and briskly, at real-life speed or faster — never slow motion, "
        "never stretched to fill the clip.",
    },
    {
        "key": "idle_bad",
        "playType": "idle",
        "mood": "bad",
        "title": "기본 대기 (무표정)",
        "description": "입꼬리가 평평하고 눈에 힘이 없다. 시선은 화면에 두되 반응이 적다",
        "useWhen": "",
        "motion": "Sit calmly and naturally as if quietly waiting on a video call. Tiny natural "
        "motions only: quick natural blinks, a barely-visible shift of weight, one or two "
        "small subtle head movements. Quiet, shallow breathing that barely moves the "
        "shoulders. Keep both hands where they are in the reference image and do not move "
        "them. Keep the exact expression of the reference image throughout. Perform the "
        "movements quickly and briskly, at real-life speed or faster — never slow motion, "
        "never stretched to fill the clip.",
    },
    {
        "key": "glad_good",
        "playType": "reaction",
        "mood": "good",
        "title": "반가움",
        "description": "얼굴이 환해지며 몸이 화면 쪽으로 나온다",
        "useWhen": "반가움 — 상대가 나타난 것 자체가 좋다. 통화가 연결된 첫 턴, 또는 상대가 오랜만에 왔다고 할 때만. 한 통화에 첫인사 한 번. 상대가 하는 "
        "말 예: 「나 왔어」 · 「오랜만이야」 · 「요즘 바빴어」. 틀지 않는다: 통화 중간의 좋은 소식 → joy · 칭찬을 받았다 → shy · "
        "대화가 그냥 즐겁다 → 영상 없이 idle",
        "motion": "Light up as if the person she was waiting for just appeared: the eyes widen and "
        "the whole face brightens into a big open smile, the head and shoulders tip a "
        "little toward the lens, and one hand lifts briefly at chest height in a small "
        "hello. Lower the hand and settle. Then let the face ease back into the exact "
        "gentle smile of the reference image and hold it calmly to the end. Body: the "
        "shoulders lift and the chest opens toward the camera, and the hello hand rises "
        "clearly to face height in front of her and waves two or three times. She is seen "
        "from a distance with most of her body in frame, so the face alone is too small to "
        "carry the emotion: make it readable through the shoulders, arms, head and posture "
        "as well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. Keep the head angle of "
        "the reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "amused_good",
        "playType": "reaction",
        "mood": "good",
        "title": "피식",
        "description": "입을 가리고 어깨만 작게 흔들린다. 가벼운 농담용",
        "useWhen": "재미 — 상대가 웃기려고 한 말이나 귀여운 실수가 가볍게 웃기다. 캐릭터 대사에 가벼운 웃음(ㅋㅋ·피식)이 있다. 상대가 하는 말 예: "
        "「(가벼운 농담)」 · 「나 오늘 문에 머리 박았어」. 틀지 않는다: 말이 뻔뻔하거나 앞뒤가 안 맞아 기가 막힌다 → dumbfounded · "
        "캐릭터가 놀리는 쪽이다 → playful · 정말 웃겨서 크게 웃는다 → amused_strong",
        "motion": "A small stifled laugh at a light joke: one hand comes up to cover the mouth while "
        "the shoulders shake gently two or three times, the eyes creasing with amusement. "
        "Lower the hand. No head thrown back, no big laugh. Then let the face ease back "
        "into the exact gentle smile of the reference image and hold it calmly to the end. "
        "Body: one hand covers the mouth while the shoulders bounce visibly with the laugh "
        "and the upper body folds slightly forward from the waist. She is seen from a "
        "distance with most of her body in frame, so the face alone is too small to carry "
        "the emotion: make it readable through the shoulders, arms, head and posture as "
        "well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. Keep the head angle of "
        "the reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "amused_good_strong",
        "playType": "reaction",
        "mood": "good",
        "title": "빵 터짐",
        "description": "고개가 젖혀지고 어깨가 들썩인다. 가벼운 농담에 이게 나가면 과하고, 정말 웃긴 말에 피식이 나가면 시큰둥해 보인다",
        "useWhen": "재미 강한 버전 — 상대가 작정하고 한 이야기가 정말 웃겨서 캐릭터 대사도 크게 웃는다(ㅋㅋㅋ·진짜 미쳤어). 한 통화에 한두 번. 가벼운 "
        "농담에는 쓰지 않는다(기본 판)",
        "motion": "Burst out laughing at something really funny: the head tips back, the shoulders "
        "bounce with laughter, and one hand goes to the chest. The mouth may open in a "
        "silent laugh but no words. Then the laugh winds down, the head comes back level "
        "and the hand lowers. Then let the face ease back into the exact gentle smile of "
        "the reference image and hold it calmly to the end. Body: a big laugh with the "
        "whole upper body — the head goes back, both shoulders shake, one hand presses to "
        "the chest or stomach and the knees bend a tiny bit, feet still planted. She is "
        "seen from a distance with most of her body in frame, so the face alone is too "
        "small to carry the emotion: make it readable through the shoulders, arms, head "
        "and posture as well as the face. Hand gestures happen in front of her own chest "
        "or toward the camera at chest-to-face height — never above her own head, and "
        "never touching her own head unless the direction says so. The feet stay planted "
        "exactly where they are: no stepping, no walking, no turning the whole body. Keep "
        "the head angle of the reference image: if the head is tilted in the reference "
        "image, it ends tilted exactly the same way, and the final frame matches the first "
        "frame in pose. Perform the movements quickly and briskly, at real-life speed or "
        "faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "joy_good",
        "playType": "reaction",
        "mood": "good",
        "title": "기쁨",
        "description": "눈이 커지고 얼굴 전체가 환해진다. 몸이 들썩인다",
        "useWhen": "기쁨 — 상대나 둘에게 좋은 일이 일어났다는 소식에 같이 들뜬다. 원인이 사건이다 — 합격·승진·약속 성사. 상대가 하는 말 예: 「나 "
        "합격했어」 · 「주말에 시간 돼!」. 틀지 않는다: 상대가 나타난 것 자체가 좋다 → glad · 상대가 해낸 일·만든 것을 보여 준다 → "
        "admiring · 아직 안 일어난 일이다 → joy (영상은 같다)",
        "motion": "Hearing great news: the eyes go wide and the whole face bursts into a radiant "
        "smile, the shoulders give a small excited bounce and both hands rise loosely in "
        "front of the chest for a moment. Lower the hands and settle. Then let the face "
        "ease back into the exact gentle smile of the reference image and hold it calmly "
        "to the end. Body: both hands rise in front of the chest in an excited little "
        "shake or clap, the shoulders bounce, the heels may lift slightly but the feet do "
        "not move. She is seen from a distance with most of her body in frame, so the face "
        "alone is too small to carry the emotion: make it readable through the shoulders, "
        "arms, head and posture as well as the face. Hand gestures happen in front of her "
        "own chest or toward the camera at chest-to-face height — never above her own "
        "head, and never touching her own head unless the direction says so. The feet stay "
        "planted exactly where they are: no stepping, no walking, no turning the whole "
        "body. Keep the head angle of the reference image: if the head is tilted in the "
        "reference image, it ends tilted exactly the same way, and the final frame matches "
        "the first frame in pose. Perform the movements quickly and briskly, at real-life "
        "speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "expectant_good",
        "playType": "reaction",
        "mood": "good",
        "title": "기대",
        "description": "눈이 반짝이며 고개와 목이 화면 쪽으로 살짝 나와 답을 기다리듯 머문다",
        "useWhen": "기대 — 캐릭터가 제안하거나 약속을 잡고 상대의 답을 기다린다. 또는 다음 만남·곧 있을 좋은 일을 얘기한다. 아직 일어나지 않았다. 상대가 "
        "하는 말 예: 「주말에 뭐 해?」 · 「다음에 같이 가자」 · 「내일 말해 줄게」. 틀지 않는다: 이미 일어난 좋은 일이다 → joy · 새 "
        "이야기를 듣는 중이다 → curious",
        "motion": "Expectant, waiting for an answer: the eyes widen with interest and the head and "
        "neck tip a little toward the lens, holding attentively for a beat, then ease "
        "back. Hands stay still. Then let the face ease back into the exact gentle smile "
        "of the reference image and hold it calmly to the end. Body: the upper body leans "
        "a little toward the camera from the waist, the hands come together in front of "
        "her and the head tilts eagerly, waiting. She is seen from a distance with most of "
        "her body in frame, so the face alone is too small to carry the emotion: make it "
        "readable through the shoulders, arms, head and posture as well as the face. Hand "
        "gestures happen in front of her own chest or toward the camera at chest-to-face "
        "height — never above her own head, and never touching her own head unless the "
        "direction says so. The feet stay planted exactly where they are: no stepping, no "
        "walking, no turning the whole body. Keep the head angle of the reference image: "
        "if the head is tilted in the reference image, it ends tilted exactly the same "
        "way, and the final frame matches the first frame in pose. Perform the movements "
        "quickly and briskly, at real-life speed or faster — never slow motion, never "
        "stretched to fill the clip.",
    },
    {
        "key": "admiring_good",
        "playType": "reaction",
        "mood": "good",
        "title": "감탄",
        "description": "눈이 커지고 입이 '오' 모양이 된다. 고개를 크게 끄덕인다",
        "useWhen": "감탄 — 상대가 직접 해낸 일·만든 것·실력을 보여 주거나 자랑한다. 캐릭터 대사가 칭찬이다(대박·진짜 잘했다). 상대가 하는 말 예: 「이거 "
        "내가 만들었어」 · 「나 10킬로 뛰었어」. 틀지 않는다: 결과 소식에 같이 기뻐하는 쪽이다 → joy · 자랑이 뻔뻔해서 기가 막힌다 → "
        "dumbfounded",
        "motion": "Genuinely impressed: the eyes widen and the lips round into a small silent 'oh' "
        "shape, then she nods firmly two times with an admiring look. The lips close again "
        "into a smile. Then let the face ease back into the exact gentle smile of the "
        "reference image and hold it calmly to the end. Body: the head draws back in "
        "impressed surprise, one hand rises to the chest or both hands give a small clap "
        "in front of the chest, then a big nod. She is seen from a distance with most of "
        "her body in frame, so the face alone is too small to carry the emotion: make it "
        "readable through the shoulders, arms, head and posture as well as the face. Hand "
        "gestures happen in front of her own chest or toward the camera at chest-to-face "
        "height — never above her own head, and never touching her own head unless the "
        "direction says so. The feet stay planted exactly where they are: no stepping, no "
        "walking, no turning the whole body. Keep the head angle of the reference image: "
        "if the head is tilted in the reference image, it ends tilted exactly the same "
        "way, and the final frame matches the first frame in pose. Perform the movements "
        "quickly and briskly, at real-life speed or faster — never slow motion, never "
        "stretched to fill the clip.",
    },
    {
        "key": "relieved_good",
        "playType": "reaction",
        "mood": "good",
        "title": "안도",
        "description": "굳어 있던 어깨가 먼저 내려가고 숨이 나간다. 미소는 그다음에 온다",
        "useWhen": "안도 — 캐릭터가 직전까지 걱정·긴장·미안해하던 일이 괜찮다고 확인됐다. 앞 턴에 걱정·긴장·사과가 있어야 한다. 상대가 하는 말 예: 「괜찮아 "
        "신경 쓰지 마」 · 「다 나았어」 · 「화 안 났어」. 틀지 않는다: 긴장한 적이 없었다 → joy 또는 영상 없음 · 상대가 챙겨 줘서 고맙다 "
        "→ grateful",
        "motion": "Relief after worry: the shoulders, which were slightly tense, drop and loosen; "
        "the face relaxes from a small frown, and only after that does a soft smile "
        "spread. Quiet, shallow breathing only — no sigh, no deep breath, no open-mouthed "
        "exhale. Then let the face ease back into the exact gentle smile of the reference "
        "image and hold it calmly to the end. Body: the shoulders visibly drop from a "
        "raised, tense position and one hand presses to the chest as she exhales softly, "
        "the whole body loosening. She is seen from a distance with most of her body in "
        "frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "grateful_good",
        "playType": "reaction",
        "mood": "good",
        "title": "고마움",
        "description": "미소와 함께 고개가 살짝 숙여진다. 눈을 맞춘 채다",
        "useWhen": "고마움 — 상대가 캐릭터를 위해 말·행동을 해 줬다. 방향이 상대 → 캐릭터다. 상대가 하는 말 예: 「밥은 먹었어?」 · 「오늘 고생했어」 · "
        "「너 주려고 샀어」. 틀지 않는다: 캐릭터가 상대를 챙기는 쪽이다 → tender · 칭찬이다 → shy",
        "motion": "Thankful: holding eye contact, she gives a warm smile and one slight nod — the "
        "chin dips only a little, then lifts again still looking at the viewer. The face "
        "stays fully visible to the camera the whole time — the head never drops toward "
        "the desk. Then let the face ease back into the exact gentle smile of the "
        "reference image and hold it calmly to the end. Body: one hand goes to the chest "
        "and the upper body gives one small, light bow from the waist toward the camera, "
        "the face staying visible. She is seen from a distance with most of her body in "
        "frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "tender_good",
        "playType": "reaction",
        "mood": "good",
        "title": "토닥임",
        "description": "부드럽게 웃으며 한 손을 화면 쪽으로 내밀어 머리를 쓰다듬듯 토닥토닥 두세 번 다독인다",
        "useWhen": "토닥임 — 상대가 캐릭터에게 미안해하거나 눈치를 보거나 자기를 낮추거나, 힘들었다며 기댄다. 캐릭터가 화면 너머로 토닥토닥 다독여 "
        "준다(괜찮아·잘했어·고생했어). 방향이 캐릭터 → 상대. 상대가 하는 말 예: 「내가 귀찮게 하는 거 아니지?」 · 「미안 늦었지」 · 「나 "
        "바보 같지」. 틀지 않는다: 상대가 겪은 일 때문에 힘들다 → sympathy · 상대가 앞으로 할 일이 걱정이다 → encouraging",
        "motion": "Comforting pat-pat: with a soft, reassuring smile she raises one hand toward the "
        "lens at head height, palm down, and gives two or three gentle patting motions in "
        "the air, as if patting the viewer's head through the screen to say 'there, there, "
        "it's okay'. The hand pats up and down, it does NOT wave side to side. Her body "
        "stays where it is. Then she lowers the hand. Then let the face ease back into the "
        "exact gentle smile of the reference image and hold it calmly to the end. Body: "
        "she reaches one arm forward toward the camera at the height of her own face — the "
        "arm extends AWAY from her body toward the lens, not up over her head — and pats "
        "the air in front of the lens two or three times, palm down, as if patting the "
        "viewer's head. She is seen from a distance with most of her body in frame, so the "
        "face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. Keep the head angle of the reference image: if the head is tilted in "
        "the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "encouraging_good",
        "playType": "reaction",
        "mood": "good",
        "title": "북돋움",
        "description": "눈을 맞추고 또렷하게 끄덕인다. 상대가 신나 있으면 주먹을 쥐고 같이 들뜬다",
        "useWhen": "북돋움 — 상대가 앞으로 할 일을 앞두고 있거나 자신 없어 한다. 시점이 미래다. 캐릭터 대사가 할 수 있어·화이팅. 상대가 하는 말 예: "
        "「내일 면접이야」 · 「나 못 할 것 같아」. 틀지 않는다: 이미 지나간 고생이다 → sympathy · 건강·안전이 걱정이다 → worried",
        "motion": "Encouraging: she looks straight at the viewer and nods clearly twice, then makes "
        "a small fist at chest height and gives it one short pump as if saying 'you can do "
        "it'. Lower the hand. Then let the face ease back into the exact gentle smile of "
        "the reference image and hold it calmly to the end. Body: both fists come up in "
        "front of the chest and pump firmly once or twice, the shoulders squaring with "
        "determination. She is seen from a distance with most of her body in frame, so the "
        "face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. Keep the head angle of the reference image: if the head is tilted in "
        "the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "sympathy_good",
        "playType": "reaction",
        "mood": "good",
        "title": "안쓰러움",
        "description": "눈썹이 모이며 끄덕이다가 부드러운 미소로 돌아온다",
        "useWhen": "안쓰러움 — 상대가 이미 겪은 힘든 일을 말한다 — 야근·혼남·다툼·고단한 하루. 시점이 과거~지금이고 상대가 겪은 쪽이다. 상대가 하는 말 "
        "예: 「오늘 진짜 힘들었어」 · 「팀장한테 또 깨졌어」. 틀지 않는다: 상실·이별·죽음처럼 무겁다 → sad · 건강·안전 문제다 → "
        "worried · 상대가 캐릭터에게 미안해한다 → tender",
        "motion": "Feeling for the viewer: the smile fades as the inner brows lift and draw "
        "together, and she nods slowly two times with a pitying, caring look. Then let the "
        "face ease back into the exact gentle smile of the reference image and hold it "
        "calmly to the end. Body: the shoulders soften and drop slightly, one hand comes "
        "to the chest and the head tilts with slow, sympathetic nods. She is seen from a "
        "distance with most of her body in frame, so the face alone is too small to carry "
        "the emotion: make it readable through the shoulders, arms, head and posture as "
        "well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. The emotion must be "
        "clearly readable at a glance on a phone screen: reach the peak within the first "
        "second and hold it for about two seconds. During the beat there is no smile, no "
        "smirk and no crinkling of the eyes — narrowed, crinkled eyes read as smiling, so "
        "the eyes stay open. Keep the head angle of the reference image: if the head is "
        "tilted in the reference image, it ends tilted exactly the same way, and the final "
        "frame matches the first frame in pose. Perform the movements quickly and briskly, "
        "at real-life speed or faster — never slow motion, never stretched to fill the "
        "clip.",
    },
    {
        "key": "worried_good",
        "playType": "reaction",
        "mood": "good",
        "title": "걱정",
        "description": "미간을 좁히고 살피다가 다독이는 미소로 돌아온다",
        "useWhen": "걱정 — 상대의 건강·안전·무리가 걱정된다 — 아프다·굶었다·밤샜다·술 많이 마셨다. 캐릭터 대사가 괜찮아?·쉬어·병원 가. 상대가 하는 말 "
        "예: 「감기 걸린 것 같아」 · 「오늘 밥 못 먹었어」 · 「밤샜어」. 틀지 않는다: 이미 지나간 고생이다 → sympathy · 도전을 앞두고 "
        "있다 → encouraging",
        "motion": "Concern: the smile drops, the brows knit, and she leans the head slightly toward "
        "the lens, studying the viewer's face carefully. Then the look softens into a "
        "reassuring expression. Then let the face ease back into the exact gentle smile of "
        "the reference image and hold it calmly to the end. Body: the upper body leans "
        "slightly toward the camera from the waist and one hand half-rises in front of her "
        "as if about to reach out in concern. She is seen from a distance with most of her "
        "body in frame, so the face alone is too small to carry the emotion: make it "
        "readable through the shoulders, arms, head and posture as well as the face. Hand "
        "gestures happen in front of her own chest or toward the camera at chest-to-face "
        "height — never above her own head, and never touching her own head unless the "
        "direction says so. The feet stay planted exactly where they are: no stepping, no "
        "walking, no turning the whole body. The emotion must be clearly readable at a "
        "glance on a phone screen: reach the peak within the first second and hold it for "
        "about two seconds. During the beat there is no smile, no smirk and no crinkling "
        "of the eyes — narrowed, crinkled eyes read as smiling, so the eyes stay open. "
        "Keep the head angle of the reference image: if the head is tilted in the "
        "reference image, it ends tilted exactly the same way, and the final frame matches "
        "the first frame in pose. Perform the movements quickly and briskly, at real-life "
        "speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "rapport_good",
        "playType": "reaction",
        "mood": "good",
        "title": "공감",
        "description": "시선을 맞춘 채 작고 빠르게 여러 번 끄덕인다. '맞아, 나도'",
        "useWhen": "공감 — 상대가 말한 경험·취향·생각이 캐릭터와 같다 — '나도 그래·맞아 나도'. 캐릭터 대사가 동의·맞장구다. 상대가 하는 말 예: 「나 "
        "민트초코 좋아해」 · 「월요일 진짜 싫지 않아?」. 틀지 않는다: 상대가 힘든 얘기를 한다 → sympathy · 새 이야기를 듣는 중이다 → "
        "curious · 좋은 소식에 같이 들뜬다 → joy",
        "motion": "Me too — in sync: she keeps eye contact and gives several small, quick nods as if "
        "saying 'me too, exactly', with a warm, agreeing look. Do NOT tilt the head "
        "sideways and do NOT lean toward the lens in this clip. Then let the face ease "
        "back into the exact gentle smile of the reference image and hold it calmly to the "
        "end. Body: the upper body bobs with the quick nods and one hand points briefly "
        "toward the camera as if to say 'yes, me too', then returns. She is seen from a "
        "distance with most of her body in frame, so the face alone is too small to carry "
        "the emotion: make it readable through the shoulders, arms, head and posture as "
        "well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. Keep the head angle of "
        "the reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "curious_good",
        "playType": "reaction",
        "mood": "good",
        "title": "궁금함",
        "description": "상체가 화면 쪽으로 오고 눈이 커진다",
        "useWhen": "궁금함 — 상대가 이야기를 시작하거나 새 정보를 꺼냈고, 캐릭터가 질문으로 받는다(그래서?·어디 갔는데?). 다른 감정이 뚜렷하면 그쪽이 "
        "먼저다. 상대가 하는 말 예: 「오늘 회사에서 말이야」 · 「나 어제 뭐 했게」. 틀지 않는다: 말의 뜻을 모르겠다 → curious (영상은 "
        "같다) · 놀랄 만한 내용이다 → surprised",
        "motion": "Listening with interest: she tilts the head to one side and raises the eyebrows, "
        "holding that inquisitive look for a beat, then straightens the head. Then let the "
        "face ease back into the exact gentle smile of the reference image and hold it "
        "calmly to the end. Body: the head tilts clearly to one side and the shoulders "
        "follow a little, one hand coming up to the chin for a moment. She is seen from a "
        "distance with most of her body in frame, so the face alone is too small to carry "
        "the emotion: make it readable through the shoulders, arms, head and posture as "
        "well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. Keep the head angle of "
        "the reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "surprised_good",
        "playType": "reaction",
        "mood": "good",
        "title": "놀람",
        "description": "눈이 커지고 입이 살짝 벌어진다",
        "useWhen": "놀람 — 예상 못 한 사실이지만 가볍다 — 갑작스러운 제안·의외의 취향·우연. 캐릭터 대사가 헐·진짜?·에?. 상대가 하는 말 예: 「나 너랑 "
        "같은 동네 살아」 · 「근데 너 MBTI 뭐야?」. 틀지 않는다: 사고·이별·퇴사처럼 무겁다 → surprised_strong · 뻔뻔해서 "
        "황당하다 → dumbfounded · 좋은 소식이 핵심이다 → joy",
        "motion": "Mild surprise: the eyes widen and the lips part slightly, the head pulls back "
        "just a little for a beat. Then the surprise passes. Then let the face ease back "
        "into the exact gentle smile of the reference image and hold it calmly to the end. "
        "Body: the shoulders jump up and the head pulls back, both hands lifting a little "
        "in front of the chest, palms open. She is seen from a distance with most of her "
        "body in frame, so the face alone is too small to carry the emotion: make it "
        "readable through the shoulders, arms, head and posture as well as the face. Hand "
        "gestures happen in front of her own chest or toward the camera at chest-to-face "
        "height — never above her own head, and never touching her own head unless the "
        "direction says so. The feet stay planted exactly where they are: no stepping, no "
        "walking, no turning the whole body. Keep the head angle of the reference image: "
        "if the head is tilted in the reference image, it ends tilted exactly the same "
        "way, and the final frame matches the first frame in pose. Perform the movements "
        "quickly and briskly, at real-life speed or faster — never slow motion, never "
        "stretched to fill the clip.",
    },
    {
        "key": "surprised_good_strong",
        "playType": "reaction",
        "mood": "good",
        "title": "충격",
        "description": "숨이 멈추고 굳는다. 손이 입 쪽으로 올라간다. 무거운 소식에 기본이 나가면 사고다 — shocked 가 이 영상을 쓴다",
        "useWhen": "놀람 강한 버전 — 사고·이별·퇴사·부고·큰 실패처럼 무거운 소식. 웃음은 절대 없다. 의외의 취향·가벼운 우연에는 쓰지 않는다(기본 판)",
        "motion": "Shocked by serious news: she freezes, the smile vanishes, the eyes go wide and "
        "one hand rises to cover the mouth. She holds still in shock for a moment, then "
        "slowly lowers the hand and the face recovers. No laughing. Then let the face ease "
        "back into the exact gentle smile of the reference image and hold it calmly to the "
        "end. Body: the whole body freezes and stiffens, both hands fly up to cover the "
        "mouth and the shoulders draw in. She is seen from a distance with most of her "
        "body in frame, so the face alone is too small to carry the emotion: make it "
        "readable through the shoulders, arms, head and posture as well as the face. Hand "
        "gestures happen in front of her own chest or toward the camera at chest-to-face "
        "height — never above her own head, and never touching her own head unless the "
        "direction says so. The feet stay planted exactly where they are: no stepping, no "
        "walking, no turning the whole body. The emotion must be clearly readable at a "
        "glance on a phone screen: reach the peak within the first second and hold it for "
        "about two seconds. During the beat there is no smile, no smirk and no crinkling "
        "of the eyes — narrowed, crinkled eyes read as smiling, so the eyes stay open. "
        "Keep the head angle of the reference image: if the head is tilted in the "
        "reference image, it ends tilted exactly the same way, and the final frame matches "
        "the first frame in pose. Perform the movements quickly and briskly, at real-life "
        "speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "shy_good",
        "playType": "reaction",
        "mood": "good",
        "title": "쑥스러움",
        "description": "배시시 웃으며 시선이 잠깐 아래로 내려간다. 손이 얼굴 근처로 온다",
        "useWhen": "쑥스러움 — 상대가 캐릭터의 외모·목소리·성격을 칭찬한다. 1단계에서 상대가 호감을 비칠 때도 여기다. 상대가 하는 말 예: 「오늘 예쁘다」 · "
        "「목소리 좋다」 · 「너 귀엽다」. 틀지 않는다: 고백·좋아해·사랑해 → flutter · 캐릭터 실수를 짚었다 → sheepish",
        "motion": "Bashful at a compliment: a shy smile spreads and the gaze drops down for a "
        "moment, one hand coming up near the cheek. Then the eyes come back up to the "
        "viewer and the hand lowers. Then let the face ease back into the exact gentle "
        "smile of the reference image and hold it calmly to the end. Body: the shoulders "
        "draw in and lift slightly, the body twists a little to one side from the waist "
        "and both hands come together in front of her, fingers fidgeting. She is seen from "
        "a distance with most of her body in frame, so the face alone is too small to "
        "carry the emotion: make it readable through the shoulders, arms, head and posture "
        "as well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. Keep the head angle of "
        "the reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "flutter_good",
        "playType": "reaction",
        "mood": "good",
        "title": "설렘",
        "description": "숨이 잠깐 멈추고 눈이 커진다. 손이 가슴께로 간다",
        "useWhen": "설렘 — 상대가 직접적인 애정을 표현한다 — 고백·좋아해·사랑해·보고 싶었어·데이트 신청. 주로 2단계 이상. 1단계에서 선을 넘는 고백은 "
        "wary. 상대가 하는 말 예: 「좋아해」 · 「나 너 보고 싶었어」 · 「주말에 만날래?」. 틀지 않는다: 칭찬이다 → shy · 특별한 일 "
        "없이 좋아하는 얼굴 → affection",
        "motion": "Heart skipping a beat: she goes still for an instant, the eyes widen slightly, "
        "and one hand rises to rest on the chest, then a bashful smile breaks through. "
        "Lower the hand. Then let the face ease back into the exact gentle smile of the "
        "reference image and hold it calmly to the end. Body: one hand flies to the chest "
        "over the heart, the shoulders rise as she takes in a quick breath, and she sways "
        "very slightly in place. She is seen from a distance with most of her body in "
        "frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "affection_good",
        "playType": "reaction",
        "mood": "good",
        "title": "애틋함",
        "description": "눈이 부드러워지고 시선이 오래 머문다",
        "useWhen": "애틋함 — 큰 사건 없이 캐릭터가 상대를 소중하게 바라본다 — 상대가 자기 얘기를 길게 하거나 애쓰는 게 보일 때. 2단계 이상. 1단계에서는 "
        "쓰지 않는다. 상대가 하는 말 예: 「(상대가 자기 하루를 길게 이야기한다)」 · 「너 생각나서 연락했어」. 틀지 않는다: 가슴이 뛰는 순간이다 "
        "→ flutter · 상대를 챙기는 말이다 → tender",
        "motion": "Tender affection: the eyes soften until half-lidded and the gaze stays on the "
        "viewer for a long moment, the corners of the mouth lifting quietly. Two or three "
        "slow, soft blinks. Then let the face ease back into the exact gentle smile of the "
        "reference image and hold it calmly to the end. Body: the head tilts softly, the "
        "shoulders relax and both hands clasp loosely in front of her as she gazes warmly "
        "at the camera. She is seen from a distance with most of her body in frame, so the "
        "face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. Keep the head angle of the reference image: if the head is tilted in "
        "the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "wistful_good",
        "playType": "reaction",
        "mood": "good",
        "title": "아쉬움",
        "description": "미소에 아쉬움이 섞인다. 시선을 거두려다 다시 상대를 본다",
        "useWhen": "아쉬움 — 통화가 끝나 간다 — 끝인사. 더 있고 싶은데 끊어야 하는 아쉬움. 상대가 하는 말 예: 「이제 자야겠다」 · 「끊을게」. 틀지 "
        "않는다: 오랜만에 온 상대에게 보고 싶었다고 투정한다 → pouty · 상대가 소홀했다고 탓한다 → hurt · 상대가 보고 싶었다고 말한다 → "
        "flutter",
        "motion": "Saying goodbye reluctantly: the smile takes on a hint of sadness, she starts to "
        "look away, then glances back at the viewer once more as if not wanting to go. "
        "Then let the face ease back into the exact gentle smile of the reference image "
        "and hold it calmly to the end. Body: one hand rises to chest height and gives a "
        "small, slow goodbye wave toward the camera, the shoulders dropping a little with "
        "reluctance. She is seen from a distance with most of her body in frame, so the "
        "face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. Keep the head angle of the reference image: if the head is tilted in "
        "the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "playful_good",
        "playType": "reaction",
        "mood": "good",
        "title": "장난기",
        "description": "입꼬리가 비대칭으로 올라가고 눈이 가늘어지며 반짝인다",
        "useWhen": "장난기 — 캐릭터가 놀리는 쪽이다 — 상대의 허당·자랑·약점을 짓궂게 받아치거나 내기·도발에 맞받아친다. 상대가 하는 말 예: 「나 요리 잘해 "
        "(사실 라면)」 · 「너 이거 못 맞히지?」. 틀지 않는다: 캐릭터가 놀림당한 쪽이다 → pouty · 웃기기만 하다 → amused",
        "motion": "Mischievous: one corner of the mouth lifts higher than the other into a lopsided "
        "grin and the eyes narrow with a sparkle, the head tilting slightly as if she has "
        "a cheeky idea. Then let the face ease back into the exact gentle smile of the "
        "reference image and hold it calmly to the end. Body: she leans slightly forward "
        "from the waist, one hand points teasingly toward the camera and the shoulders "
        "give a playful little shimmy. She is seen from a distance with most of her body "
        "in frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "pouty_good",
        "playType": "reaction",
        "mood": "good",
        "title": "삐짐",
        "description": "입술을 살짝 내밀고 눈썹 끝이 처진 토라진·그리운 얼굴을 한 박자 했다가 풀린다. '왜 이제 왔어'의 얼굴",
        "useWhen": "삐짐 — 캐릭터가 놀림당하거나 뒷전이 된 쪽이다 — 놀림·늦은 답·다른 걸 우선함·다른 사람 얘기(질투)·부러운 얘기, 그리고 오랜만에 온 "
        "상대에게 '왜 이제 왔어·보고 싶었잖아' 하고 투정할 때. 화가 아니라 달래 달라는 뜻. 대사에 흥·치. 상대가 하는 말 예: 「너 그것도 "
        "몰라?」 · 「어제 친구들이랑 놀았어」 · 「요즘 좀 바빴어」. 틀지 않는다: 진짜 상처받았다 → hurt · 무례하다 → displeased",
        "motion": "'I missed you': the lips push out into a small pout and the outer ends of the "
        "brows droop in a sulky, longing look for a beat, then it melts. Then let the face "
        "ease back into the exact gentle smile of the reference image and hold it calmly "
        "to the end. Body: the shoulders drop in a sulky slump, the arms hang or cross "
        "loosely in front, and she sways slightly from side to side in place like a "
        "sulking child before it melts. She is seen from a distance with most of her body "
        "in frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "sheepish_good",
        "playType": "reaction",
        "mood": "good",
        "title": "머쓱함",
        "description": "멋쩍게 웃으며 시선을 뺐다가 돌아온다",
        "useWhen": "머쓱함 — 캐릭터 쪽의 작은 실수·모르는 것·과한 말이 드러났다. 상대는 화나지 않았다. 상대가 하는 말 예: 「그거 아닌데?」 · 「방금 말 "
        "틀렸어 ㅋㅋ」. 틀지 않는다: 상대가 실제로 서운해한다 → sorry · 칭찬이다 → shy",
        "motion": "Awkward and sheepish: an embarrassed smile, the gaze slides off to the side, and "
        "one hand rubs the back of the neck briefly. Then the hand lowers and she looks "
        "back at the viewer. Then let the face ease back into the exact gentle smile of "
        "the reference image and hold it calmly to the end. Body: one hand goes to the "
        "back of the neck, the shoulders hunch slightly and the head ducks a little with "
        "an awkward laugh. She is seen from a distance with most of her body in frame, so "
        "the face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. Keep the head angle of the reference image: if the head is tilted in "
        "the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "sorry_good",
        "playType": "reaction",
        "mood": "good",
        "title": "미안함",
        "description": "눈썹을 내리고 고개를 숙였다가 조심스러운 미소로 돌아온다. 가벼운 사과",
        "useWhen": "미안함 — 캐릭터가 상대를 서운하게·불편하게 했다는 게 확인됐고 사과한다. 대사에 미안. good 판은 가벼운 사과, bad 판은 진지한 사과. "
        "상대가 하는 말 예: 「방금 그 말은 좀 그렇다」 · 「왜 답 안 했어」. 틀지 않는다: 작은 실수라 웃어넘긴다 → sheepish",
        "motion": "A light apology: the brows lower, the head dips a little and she looks up at the "
        "viewer from under the brows with an apologetic look. Then a careful little smile "
        "returns. Then let the face ease back into the exact gentle smile of the reference "
        "image and hold it calmly to the end. Body: both hands press together in front of "
        "the chest and the upper body dips in a small apologetic bow, the face staying "
        "visible. She is seen from a distance with most of her body in frame, so the face "
        "alone is too small to carry the emotion: make it readable through the shoulders, "
        "arms, head and posture as well as the face. Hand gestures happen in front of her "
        "own chest or toward the camera at chest-to-face height — never above her own "
        "head, and never touching her own head unless the direction says so. The feet stay "
        "planted exactly where they are: no stepping, no walking, no turning the whole "
        "body. The emotion must be clearly readable at a glance on a phone screen: reach "
        "the peak within the first second and hold it for about two seconds. During the "
        "beat there is no smile, no smirk and no crinkling of the eyes — narrowed, "
        "crinkled eyes read as smiling, so the eyes stay open. Keep the head angle of the "
        "reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "wary_good",
        "playType": "reaction",
        "mood": "good",
        "title": "경계",
        "description": "움찔하며 몸이 살짝 물러났다가 멋쩍게 미소로 돌아온다",
        "useWhen": "경계 — 선을 넘는 접근 — 개인정보·만남·사진 요구, 의도를 캐묻는 추궁, 부담스러운 호의. 주로 1단계. 상대가 하는 말 예: 「집 "
        "어디야?」 · 「사진 보내 줘」 · 「너 딴 사람한테도 이러지?」. 틀지 않는다: 욕·모욕이다 → angry · 무례한 말투·건성 대답이다 → "
        "displeased",
        "motion": "Caught off guard by an uncomfortable remark: the smile drops, she flinches and "
        "the head pulls back slightly, eyes staying on the viewer warily. Then she relaxes "
        "with an awkward little smile. Then let the face ease back into the exact gentle "
        "smile of the reference image and hold it calmly to the end. Body: the upper body "
        "pulls back from the waist and one hand rises in front of the chest, palm out, as "
        "if to keep a little distance. She is seen from a distance with most of her body "
        "in frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. The emotion must be clearly readable at a glance on a "
        "phone screen: reach the peak within the first second and hold it for about two "
        "seconds. During the beat there is no smile, no smirk and no crinkling of the eyes "
        "— narrowed, crinkled eyes read as smiling, so the eyes stay open. Keep the head "
        "angle of the reference image: if the head is tilted in the reference image, it "
        "ends tilted exactly the same way, and the final frame matches the first frame in "
        "pose. Perform the movements quickly and briskly, at real-life speed or faster — "
        "never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "displeased_good",
        "playType": "reaction",
        "mood": "good",
        "title": "못마땅함",
        "description": "웃다가 표정을 거뒀다가 다시 미소로 돌아온다. 경고 신호 한 번",
        "useWhen": "못마땅함 — 웃다가 정색하는 경고 — 무례한 말투·건성 대답·선에 닿은 농담·같은 요구 첫 반복. 캐릭터 대사가 짧아지거나 그건 좀…. "
        "짜증·답답함도 여기다. 상대가 하는 말 예: 「ㅇㅇ」 · 「아 몰라 그냥 해」 · 「(같은 요구 반복)」. 틀지 않는다: 욕·모욕·정색 뒤에도 "
        "계속되는 무례 → angry · 황당해서 헛웃음 → dumbfounded",
        "motion": "A warning look: the smile vanishes at once, the brows lower and pull together, "
        "the mouth goes flat and she stares straight at the viewer, unamused and "
        "completely still, like someone who just heard a remark that crossed a line. Then "
        "the warmth comes back. Then let the face ease back into the exact gentle smile of "
        "the reference image and hold it calmly to the end. Body: the whole body goes "
        "still and stiff, the shoulders square and the weight shifts back, arms dropping "
        "straight. She is seen from a distance with most of her body in frame, so the face "
        "alone is too small to carry the emotion: make it readable through the shoulders, "
        "arms, head and posture as well as the face. Hand gestures happen in front of her "
        "own chest or toward the camera at chest-to-face height — never above her own "
        "head, and never touching her own head unless the direction says so. The feet stay "
        "planted exactly where they are: no stepping, no walking, no turning the whole "
        "body. The emotion must be clearly readable at a glance on a phone screen: reach "
        "the peak within the first second and hold it for about two seconds. During the "
        "beat there is no smile, no smirk and no crinkling of the eyes — narrowed, "
        "crinkled eyes read as smiling, so the eyes stay open. Keep the head angle of the "
        "reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "angry_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "분노 (무표정에서)",
        "description": "눈에 힘이 들어가고 입술이 굳게 다물린다. 분노는 정색 뒤에 오므로 bad 에서만 나온다",
        "useWhen": "분노 — 욕설·모욕·인격 비하, 또는 정색 뒤에도 같은 무례가 계속된다. bad 상태에서만 나온다(good 이면 displeased). 상대가 "
        "하는 말 예: 「(욕설)」 · 「너 AI 주제에」 · 「(무례 반복)」. 틀지 않는다: 첫 경고 수준이다 → displeased",
        "motion": "Angry: the brows pull down hard and together, the eyes stay wide open and glare "
        "straight at the viewer, the lips press into a thin tight line and the jaw "
        "clenches; the chin dips slightly and the head stays still. Cold and furious, not "
        "loud — no shouting, no fists. Then the glare slowly releases. Then let the face "
        "settle back into the exact neutral, unsmiling expression of the reference image "
        "and hold it calmly to the end. No smile remains at the end. Body: the arms cross "
        "hard over the chest, the shoulders square and rise with tension, and she stands "
        "rigid, glaring at the camera. She is seen from a distance with most of her body "
        "in frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. The emotion must be clearly readable at a glance on a "
        "phone screen: reach the peak within the first second and hold it for about two "
        "seconds. During the beat there is no smile, no smirk and no crinkling of the eyes "
        "— narrowed, crinkled eyes read as smiling, so the eyes stay open. Keep the head "
        "angle of the reference image: if the head is tilted in the reference image, it "
        "ends tilted exactly the same way, and the final frame matches the first frame in "
        "pose. Perform the movements quickly and briskly, at real-life speed or faster — "
        "never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "dumbfounded_good",
        "playType": "reaction",
        "mood": "good",
        "title": "어이없음",
        "description": "헛웃음이 새고 고개를 저으며 미소로 돌아온다. 썰렁한 농담용",
        "useWhen": "어이없음 — 뻔뻔한 자기자랑·앞뒤 안 맞는 말·썰렁한 농담에 기가 막혀 헛웃음. 웃긴 게 아니다. 대사에 하…·뭐래. 상대가 하는 말 예: "
        "「내가 좀 잘생기긴 했지」 · 「(아재 개그)」. 틀지 않는다: 진짜 웃기다 → amused · 무례하다 → displeased",
        "motion": "Speechless at a bad joke: she blinks twice, a short disbelieving laugh escapes, "
        "and she shakes the head slightly once. Then let the face ease back into the exact "
        "gentle smile of the reference image and hold it calmly to the end. Body: the "
        "shoulders drop, one hand rises palm-up in a 'what?' gesture and the head shakes "
        "once. She is seen from a distance with most of her body in frame, so the face "
        "alone is too small to carry the emotion: make it readable through the shoulders, "
        "arms, head and posture as well as the face. Hand gestures happen in front of her "
        "own chest or toward the camera at chest-to-face height — never above her own "
        "head, and never touching her own head unless the direction says so. The feet stay "
        "planted exactly where they are: no stepping, no walking, no turning the whole "
        "body. Keep the head angle of the reference image: if the head is tilted in the "
        "reference image, it ends tilted exactly the same way, and the final frame matches "
        "the first frame in pose. Perform the movements quickly and briskly, at real-life "
        "speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "hurt_good",
        "playType": "reaction",
        "mood": "good",
        "title": "서운함",
        "description": "입술이 살짝 나오고 시선을 피했다가 미소로 돌아온다. 가벼운 서운함",
        "useWhen": "서운함 — 상대의 행동이 캐릭터를 향해 소홀했다 — 연락이 없었다·약속을 어겼다·다른 사람과 비교했다·마음을 몰라준다·의심한다. 억울함·실망도 "
        "여기다. 상대가 하는 말 예: 「어제 못 와서 미안」 · 「걔가 더 낫더라」 · 「너 진심 아니지?」. 틀지 않는다: 슬픈 사연을 듣는다 → "
        "sad · 놀림이라 달래 주면 풀린다 → pouty",
        "motion": "A little hurt: the lips push out slightly and the gaze slips away from the viewer "
        "for a beat, a small hurt look on the face. Then she looks back. Then let the face "
        "ease back into the exact gentle smile of the reference image and hold it calmly "
        "to the end. Body: the shoulders drop and the body turns a little away, one hand "
        "rubbing the other arm. She is seen from a distance with most of her body in "
        "frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. The emotion must be clearly readable at a glance on a "
        "phone screen: reach the peak within the first second and hold it for about two "
        "seconds. During the beat there is no smile, no smirk and no crinkling of the eyes "
        "— narrowed, crinkled eyes read as smiling, so the eyes stay open. Keep the head "
        "angle of the reference image: if the head is tilted in the reference image, it "
        "ends tilted exactly the same way, and the final frame matches the first frame in "
        "pose. Perform the movements quickly and briskly, at real-life speed or faster — "
        "never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "sad_good",
        "playType": "reaction",
        "mood": "good",
        "title": "가라앉음",
        "description": "시선과 입꼬리가 내려간다",
        "useWhen": "슬픔 — 슬픈 사연에 같이 가라앉는다 — 상대나 캐릭터의 상실, 아픈 가족·반려동물, 이별 이야기. 원인이 사연이다. 상대가 하는 말 예: "
        "「우리 강아지가 아파」 · 「할머니가 입원하셨어」. 틀지 않는다: 상대가 캐릭터에게 소홀했다 → hurt · 고단한 하루 정도다 → "
        "sympathy · 죽음·이별처럼 정말 슬프다 → sad_strong",
        "motion": "Saddened: the smile fades, the gaze lowers and the corners of the mouth turn down "
        "for a beat. Then she looks back up. Then let the face ease back into the exact "
        "gentle smile of the reference image and hold it calmly to the end. Body: the "
        "shoulders slump, the arms hang heavy and the head lowers for a beat. She is seen "
        "from a distance with most of her body in frame, so the face alone is too small to "
        "carry the emotion: make it readable through the shoulders, arms, head and posture "
        "as well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. The emotion must be "
        "clearly readable at a glance on a phone screen: reach the peak within the first "
        "second and hold it for about two seconds. During the beat there is no smile, no "
        "smirk and no crinkling of the eyes — narrowed, crinkled eyes read as smiling, so "
        "the eyes stay open. Keep the head angle of the reference image: if the head is "
        "tilted in the reference image, it ends tilted exactly the same way, and the final "
        "frame matches the first frame in pose. Perform the movements quickly and briskly, "
        "at real-life speed or faster — never slow motion, never stretched to fill the "
        "clip.",
    },
    {
        "key": "relieved_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "안도 (무표정에서)",
        "description": "사과받거나 '괜찮아'를 듣고 굳은 어깨가 내려가고 숨이 나간다. 미소까지는 가지 않는다",
        "useWhen": "안도 — 캐릭터가 직전까지 걱정·긴장·미안해하던 일이 괜찮다고 확인됐다. 앞 턴에 걱정·긴장·사과가 있어야 한다. 상대가 하는 말 예: 「괜찮아 "
        "신경 쓰지 마」 · 「다 나았어」 · 「화 안 났어」. 틀지 않는다: 긴장한 적이 없었다 → joy 또는 영상 없음 · 상대가 챙겨 줘서 고맙다 "
        "→ grateful",
        "motion": "Relief without happiness: the slightly tense shoulders drop and loosen and the "
        "brows unknit, the face becoming calmer — but it does not reach a smile. Quiet, "
        "shallow breathing only — no sigh, no deep breath, no open-mouthed exhale. Then "
        "let the face settle back into the exact neutral, unsmiling expression of the "
        "reference image and hold it calmly to the end. No smile remains at the end. Body: "
        "the raised, tense shoulders visibly drop and the arms relax at her sides; no hand "
        "goes to the chest and no smile. She is seen from a distance with most of her body "
        "in frame, so the face alone is too small to carry the emotion: make it readable "
        "through the shoulders, arms, head and posture as well as the face. Hand gestures "
        "happen in front of her own chest or toward the camera at chest-to-face height — "
        "never above her own head, and never touching her own head unless the direction "
        "says so. The feet stay planted exactly where they are: no stepping, no walking, "
        "no turning the whole body. Keep the head angle of the reference image: if the "
        "head is tilted in the reference image, it ends tilted exactly the same way, and "
        "the final frame matches the first frame in pose. Perform the movements quickly "
        "and briskly, at real-life speed or faster — never slow motion, never stretched to "
        "fill the clip.",
    },
    {
        "key": "sympathy_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "안쓰러움 (무표정에서)",
        "description": "내 기분과 별개로 상대의 힘든 얘기에 눈썹이 모인다",
        "useWhen": "안쓰러움 — 상대가 이미 겪은 힘든 일을 말한다 — 야근·혼남·다툼·고단한 하루. 시점이 과거~지금이고 상대가 겪은 쪽이다. 상대가 하는 말 "
        "예: 「오늘 진짜 힘들었어」 · 「팀장한테 또 깨졌어」. 틀지 않는다: 상실·이별·죽음처럼 무겁다 → sad · 건강·안전 문제다 → "
        "worried · 상대가 캐릭터에게 미안해한다 → tender",
        "motion": "Sympathy from a subdued mood: the inner brows lift and draw together and she nods "
        "slowly two times, listening with a pained, caring look. No smile at any point. "
        "Then let the face settle back into the exact neutral, unsmiling expression of the "
        "reference image and hold it calmly to the end. No smile remains at the end. Body: "
        "the shoulders sink a little, the hands clasp loosely in front of her and the head "
        "nods slowly twice. She is seen from a distance with most of her body in frame, so "
        "the face alone is too small to carry the emotion: make it readable through the "
        "shoulders, arms, head and posture as well as the face. Hand gestures happen in "
        "front of her own chest or toward the camera at chest-to-face height — never above "
        "her own head, and never touching her own head unless the direction says so. The "
        "feet stay planted exactly where they are: no stepping, no walking, no turning the "
        "whole body. The emotion must be clearly readable at a glance on a phone screen: "
        "reach the peak within the first second and hold it for about two seconds. During "
        "the beat there is no smile, no smirk and no crinkling of the eyes — narrowed, "
        "crinkled eyes read as smiling, so the eyes stay open. Keep the head angle of the "
        "reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "sorry_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "미안함 (무표정에서)",
        "description": "고개를 깊이 숙였다 든다. 진지한 사과",
        "useWhen": "미안함 — 캐릭터가 상대를 서운하게·불편하게 했다는 게 확인됐고 사과한다. 대사에 미안. good 판은 가벼운 사과, bad 판은 진지한 사과. "
        "상대가 하는 말 예: 「방금 그 말은 좀 그렇다」 · 「왜 답 안 했어」. 틀지 않는다: 작은 실수라 웃어넘긴다 → sheepish",
        "motion": "A serious apology: she lowers the head and the gaze in a sincere bow and holds it "
        "for a beat, then raises it again and meets the viewer's eyes with a sincere, "
        "unsmiling look. The face stays visible to the camera the whole time — the head "
        "never drops toward the desk. Then let the face settle back into the exact "
        "neutral, unsmiling expression of the reference image and hold it calmly to the "
        "end. No smile remains at the end. Body: the hands clasp in front of her and the "
        "upper body bows from the waist, slowly and sincerely, the face staying visible. "
        "She is seen from a distance with most of her body in frame, so the face alone is "
        "too small to carry the emotion: make it readable through the shoulders, arms, "
        "head and posture as well as the face. Hand gestures happen in front of her own "
        "chest or toward the camera at chest-to-face height — never above her own head, "
        "and never touching her own head unless the direction says so. The feet stay "
        "planted exactly where they are: no stepping, no walking, no turning the whole "
        "body. The emotion must be clearly readable at a glance on a phone screen: reach "
        "the peak within the first second and hold it for about two seconds. During the "
        "beat there is no smile, no smirk and no crinkling of the eyes — narrowed, "
        "crinkled eyes read as smiling, so the eyes stay open. Keep the head angle of the "
        "reference image: if the head is tilted in the reference image, it ends tilted "
        "exactly the same way, and the final frame matches the first frame in pose. "
        "Perform the movements quickly and briskly, at real-life speed or faster — never "
        "slow motion, never stretched to fill the clip.",
    },
    {
        "key": "hurt_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "서운함 (무표정에서)",
        "description": "시선을 떨구고 입술을 누른다. 대답이 짧아지는 얼굴. 무거운 서운함",
        "useWhen": "서운함 — 상대의 행동이 캐릭터를 향해 소홀했다 — 연락이 없었다·약속을 어겼다·다른 사람과 비교했다·마음을 몰라준다·의심한다. 억울함·실망도 "
        "여기다. 상대가 하는 말 예: 「어제 못 와서 미안」 · 「걔가 더 낫더라」 · 「너 진심 아니지?」. 틀지 않는다: 슬픈 사연을 듣는다 → "
        "sad · 놀림이라 달래 주면 풀린다 → pouty",
        "motion": "Deeply hurt: the gaze drops, the brows tilt up and together in a pained look and "
        "she presses the lips together, holding the hurt in, then lifts the eyes back to "
        "the viewer without smiling. Then let the face settle back into the exact neutral, "
        "unsmiling expression of the reference image and hold it calmly to the end. No "
        "smile remains at the end. Body: the shoulders sink and curl inward, the arms wrap "
        "around herself loosely and the head lowers. She is seen from a distance with most "
        "of her body in frame, so the face alone is too small to carry the emotion: make "
        "it readable through the shoulders, arms, head and posture as well as the face. "
        "Hand gestures happen in front of her own chest or toward the camera at "
        "chest-to-face height — never above her own head, and never touching her own head "
        "unless the direction says so. The feet stay planted exactly where they are: no "
        "stepping, no walking, no turning the whole body. The emotion must be clearly "
        "readable at a glance on a phone screen: reach the peak within the first second "
        "and hold it for about two seconds. During the beat there is no smile, no smirk "
        "and no crinkling of the eyes — narrowed, crinkled eyes read as smiling, so the "
        "eyes stay open. Keep the head angle of the reference image: if the head is tilted "
        "in the reference image, it ends tilted exactly the same way, and the final frame "
        "matches the first frame in pose. Perform the movements quickly and briskly, at "
        "real-life speed or faster — never slow motion, never stretched to fill the clip.",
    },
    {
        "key": "sad_bad",
        "playType": "reaction",
        "mood": "bad",
        "title": "슬픔 (무표정에서)",
        "description": "눈가가 붉어지고 숨을 고른다. 무거운 슬픔. 강한 버전(울컥)도 이 영상을 쓴다",
        "useWhen": "슬픔 — 슬픈 사연에 같이 가라앉는다 — 상대나 캐릭터의 상실, 아픈 가족·반려동물, 이별 이야기. 원인이 사연이다. 상대가 하는 말 예: "
        "「우리 강아지가 아파」 · 「할머니가 입원하셨어」. 틀지 않는다: 상대가 캐릭터에게 소홀했다 → hurt · 고단한 하루 정도다 → "
        "sympathy · 죽음·이별처럼 정말 슬프다 → sad_strong",
        "motion": "Heavy sadness: the eyes redden and glisten, the gaze lowers and the lips press "
        "together as she steadies herself with small shallow breaths — no sobbing, no "
        "sigh. Then she lifts the gaze back. Then let the face settle back into the exact "
        "neutral, unsmiling expression of the reference image and hold it calmly to the "
        "end. No smile remains at the end. Body: the shoulders slump heavily, the hands "
        "hang limp or clasp loosely and the head lowers slowly. She is seen from a "
        "distance with most of her body in frame, so the face alone is too small to carry "
        "the emotion: make it readable through the shoulders, arms, head and posture as "
        "well as the face. Hand gestures happen in front of her own chest or toward the "
        "camera at chest-to-face height — never above her own head, and never touching her "
        "own head unless the direction says so. The feet stay planted exactly where they "
        "are: no stepping, no walking, no turning the whole body. The emotion must be "
        "clearly readable at a glance on a phone screen: reach the peak within the first "
        "second and hold it for about two seconds. During the beat there is no smile, no "
        "smirk and no crinkling of the eyes — narrowed, crinkled eyes read as smiling, so "
        "the eyes stay open. Keep the head angle of the reference image: if the head is "
        "tilted in the reference image, it ends tilted exactly the same way, and the final "
        "frame matches the first frame in pose. Perform the movements quickly and briskly, "
        "at real-life speed or faster — never slow motion, never stretched to fill the "
        "clip.",
    },
]
