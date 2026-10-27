// 데모 데이터: agentic-character-factory의 cf-20261021-s2real 실행 산출물에서 옮겼다.
window.FACTORY_DATA = {
  "seedMeta": "25세 · 필름 현상소 직원",
  "finaleStage": 4,
  "stages": [
    {
      "label": "외모",
      "sub": "얼굴",
      "icon": "face"
    },
    {
      "label": "기획",
      "sub": "성격과 이야기",
      "icon": "doc"
    },
    {
      "label": "장면",
      "sub": "배경과 완성 이미지",
      "icon": "image"
    },
    {
      "label": "영상",
      "sub": "움직임",
      "icon": "film"
    },
    {
      "label": "페르소나",
      "sub": "말투와 프롬프트",
      "icon": "chat"
    },
    {
      "label": "출시",
      "sub": "앱에 올리기",
      "icon": "package"
    }
  ],
  "chapters": [
    {
      "id": "ch1",
      "label": "1장 친해지기"
    },
    {
      "id": "ch2",
      "label": "2장 썸타기"
    },
    {
      "id": "ch3",
      "label": "3장 고백하기"
    }
  ],
  "steps": [
    {
      "id": "hero",
      "gate": "G1",
      "stage": 0,
      "agent": "Scout",
      "kind": "image",
      "ratio": "square",
      "select": "single",
      "slot": "portrait",
      "kicker": "외모 · 관문 G1",
      "title": "어떤 얼굴로 갈까요?",
      "desc": "화제성 순위의 여러 인물이 함께 가진 외모 특징으로 외모군 3개를 묶고, 외모군마다 얼굴을 만들었어요. 여기서 고른 얼굴이 이후 모든 장면과 영상의 기준이 돼요. 인물 이름은 쓰지 않아요.",
      "working": "외모군을 묶고 얼굴을 그리는 중…",
      "arrive": "Scout가 외모군 3개의 얼굴을 만들었어요",
      "judge": "1번 외모군이 순위 목록 두 개에서 반복돼 근거가 가장 단단해요",
      "hint": "얼굴을 눌러 고르세요 · 숫자 키 1~3",
      "confirmLabel": "이 얼굴로 확정",
      "stamp": "확정",
      "doneText": "얼굴을 확정했어요 · 기준 사진은 자동으로 만들어요",
      "tweaks": [
        "더 성숙하게",
        "표정 더 밝게",
        "머리를 더 짧게",
        "메이크업 옅게"
      ],
      "writePlaceholder": "원하는 얼굴을 한두 줄로 적어 주세요. 예) 눈매는 그대로, 앞머리 없이",
      "candidates": [
        {
          "id": "f-c1",
          "img": "assets/hero-b.jpg",
          "alt": "assets/hero-c.jpg",
          "title": "웨이브 미디엄 · 건강한 인상",
          "altTitle": "웨이브 미디엄 · 사랑스러운 인상",
          "desc": "외모군 1 · 4명 공유 · 순위 목록 2개에서 반복",
          "tags": [
            "라이트 브라운",
            "커튼 앞머리",
            "캐주얼"
          ],
          "recommended": true
        },
        {
          "id": "f-c2",
          "img": "assets/hero-a.jpg",
          "alt": "assets/cluster-c2.jpg",
          "title": "긴 생머리 · 청순한 인상",
          "desc": "외모군 2 · 4명 공유 · 순위 목록 1개에서만",
          "tags": [
            "흑발",
            "시스루 앞머리",
            "페미닌"
          ]
        },
        {
          "id": "f-c3",
          "img": "assets/cluster-c3.jpg",
          "alt": "assets/cluster-c3b.jpg",
          "title": "단발 · 시크한 인상",
          "desc": "외모군 3 · 4명 공유 · 순위 목록 1개에서만",
          "tags": [
            "흑발 보브",
            "앞머리 없음",
            "미니멀"
          ]
        }
      ]
    },
    {
      "id": "plan",
      "stage": 1,
      "gate": "G3",
      "agent": "Planner",
      "kind": "text",
      "select": "single",
      "slot": "profile",
      "kicker": "기획 · 관문 G3",
      "title": "누구로 만들까요?",
      "desc": "같은 씨앗으로 성격이 다른 세 사람을 만들었어요. 같은 상황에서 무엇을 먼저 하는지 비교해 보세요.",
      "working": "기획안을 쓰는 중…",
      "arrive": "Planner가 기획안 3개를 만들었어요",
      "judge": "",
      "seed": [
        "25세",
        "여성",
        "필름 현상소 직원",
        "말수는 적지만 좋아하는 것 앞에서 오래 머문다"
      ],
      "situation": "상대가 약속 시간에 30분 늦는다고 연락했을 때",
      "hint": "기획안을 눌러 고르세요 · 숫자 키 1~3",
      "confirmLabel": "이 사람으로 확정",
      "stamp": "확정",
      "doneText": "기획서를 고정했어요",
      "tweaks": [
        "더 다정하게",
        "더 무심하게",
        "말수 더 적게",
        "장난기 조금"
      ],
      "writePlaceholder": "직접 생각한 인물을 적어 주세요. 정리해서 네 번째 안으로 올려 드려요.",
      "candidates": [
        {
          "id": "v1",
          "name": "윤서하",
          "mbti": "ISFP",
          "desc": "기다리는 시간도 한 컷으로 남기는, 자기 속도가 분명한 현상소 직원",
          "move": "'천천히 와'라고만 답하고 근처 골목에서 필름 몇 컷을 찍다가, 도착하면 방금 찍은 곳을 같이 보러 가자고 한다",
          "quote": "괜찮아. 나 저 앞 골목에 있어. 빛 좋거든.",
          "tags": [
            "필름산책",
            "자기속도",
            "말보다사진"
          ]
        },
        {
          "id": "v2",
          "name": "한지우",
          "mbti": "ISTJ",
          "desc": "말은 적어도 필요한 순간에는 먼저 찾아가는, 손이 빠른 현상소 직원",
          "move": "'지금 어디야?'라고 도착 시간을 묻고, 상대 쪽 역으로 장소를 옮겨 자기가 마중 나간다",
          "quote": "어디쯤이야? 그럼 내가 그쪽 역으로 갈게.",
          "tags": [
            "먼저연락",
            "동선기억",
            "손이빠름"
          ]
        },
        {
          "id": "v3",
          "name": "서은결",
          "mbti": "INFJ",
          "desc": "한 번 정한 약속은 제대로 지키고 싶어서, 어긋나면 다시 정하는 현상소 직원",
          "move": "'오늘은 서두르지 말자'고 말하고, 남은 시간이 짧으니 다음 쉬는 날로 약속을 다시 정하자고 한다",
          "quote": "괜찮아. 대신 오늘은 서두르지 말자.",
          "tags": [
            "약속은제대로",
            "다시정하기",
            "준비가길다"
          ]
        }
      ]
    },
    {
      "id": "bg",
      "stage": 2,
      "gate": "G4a",
      "agent": "Location Scout",
      "kind": "image",
      "ratio": "tall",
      "select": "single",
      "slot": "ch1",
      "kicker": "장면 · 관문 G4a",
      "title": "1장 「친해지기」, 어디서 처음 만날까요?",
      "desc": "기획서의 직업과 동선에 맞춰, 사람이 없는 세로 배경 사진 3장을 만들었어요.",
      "working": "배경을 찾는 중…",
      "arrive": "Location Scout가 배경 3곳을 찾았어요",
      "judge": "1번이 기획서의 일터와 가장 잘 이어져요",
      "hint": "배경을 눌러 고르세요 · 숫자 키 1~3",
      "confirmLabel": "이 배경으로 확정",
      "stamp": "확정",
      "doneText": "1장 배경을 확정했어요",
      "tweaks": [
        "더 늦은 시간대",
        "비 오는 날",
        "사람이 조금 있게",
        "실내로"
      ],
      "writePlaceholder": "원하는 배경을 한두 줄로 적어 주세요. 예) 비 오는 날 현상소 유리문 앞",
      "candidates": [
        {
          "id": "ch1-b1",
          "img": "assets/bg-ch1-b1.jpg",
          "alt": "assets/bg-ch2-b1.jpg",
          "title": "필름 현상소 카운터",
          "desc": "평일 오후 · 형광등과 햇빛이 섞인 조용한 가게",
          "tags": [
            "일터",
            "실내"
          ],
          "recommended": true,
          "altTitle": "셔터 내린 공구상가 골목",
          "altDesc": "이른 아침 · 셔터가 내려진 조용한 골목"
        },
        {
          "id": "ch1-b2",
          "img": "assets/bg-ch1-b2.jpg",
          "alt": "assets/bg-ch3-b2.jpg",
          "title": "인쇄소 사이 뒷골목",
          "desc": "쉬는 날 늦은 오후 · 낡은 벽에 길게 떨어지는 햇살",
          "tags": [
            "골목",
            "야외"
          ],
          "altTitle": "오래된 상가 옥상",
          "altDesc": "저녁 · 을지로 지붕 너머로 지는 해"
        },
        {
          "id": "ch1-b3",
          "img": "assets/bg-ch1-b3.jpg",
          "alt": "assets/bg-ch2-b3.jpg",
          "title": "한강 산책로 벤치",
          "desc": "해 질 무렵 · 강 위로 번지는 주황빛",
          "tags": [
            "한강",
            "노을"
          ],
          "altTitle": "한강 다리 아래 계단",
          "altDesc": "해 질 무렵 · 강변 계단에 번지는 빛"
        }
      ]
    },
    {
      "id": "frames",
      "stage": 2,
      "gate": "G4",
      "agent": "Framer",
      "kind": "image",
      "ratio": "tall",
      "select": "multi",
      "kicker": "장면 · 관문 G4",
      "title": "챕터 완성 이미지를 승인해 주세요",
      "desc": "고른 얼굴, 배경, 자세로 세 챕터의 첫 장면을 만들었어요. 승인한 장면이 영상의 첫 프레임이 돼요.",
      "working": "완성 이미지를 합성하는 중…",
      "arrive": "Framer가 완성 이미지 3장을 만들었어요",
      "judge": "세 장 모두 대표 얼굴과 같은 사람으로 보여요",
      "hint": "승인할 장면을 눌러 주세요 · 여러 장 고를 수 있어요",
      "selHint": "{n}장 승인 예정",
      "confirmLabel": "{n}장 승인",
      "stamp": "승인",
      "doneText": "완성 이미지를 승인했어요",
      "tweaks": [
        "표정 더 밝게",
        "손을 자연스럽게",
        "카메라를 더 가까이"
      ],
      "writePlaceholder": "고칠 점을 적어 주세요. 예) 2장은 카메라를 목에 걸게",
      "candidates": [
        {
          "id": "ch1",
          "chapter": "ch1",
          "img": "assets/frame-ch1.jpg",
          "title": "1장 · 친해지기",
          "desc": "현상소 카운터에서 필름 봉투를 건네는 순간"
        },
        {
          "id": "ch2",
          "chapter": "ch2",
          "img": "assets/frame-ch2.jpg",
          "title": "2장 · 썸타기",
          "desc": "셔터 내린 골목에서 카메라를 메고 기다리는 아침"
        },
        {
          "id": "ch3",
          "chapter": "ch3",
          "img": "assets/frame-ch3.jpg",
          "title": "3장 · 고백하기",
          "desc": "영업을 마친 작업대에서 마지막 컷을 건네는 밤"
        }
      ],
      "zeroLabel": "장면을 골라 주세요"
    },
    {
      "id": "motion",
      "stage": 3,
      "gate": "G5b",
      "agent": "Director",
      "kind": "chip",
      "select": "multi",
      "slot": "motion",
      "noRegen": true,
      "kicker": "영상 · 관문 G5b",
      "title": "어떤 움직임을 만들까요?",
      "desc": "앱 통화 화면에서 쓰는 영상 목록이에요. 승인한 완성 이미지에서 시작하는 짧은 영상으로 만들어요.",
      "working": "움직임 목록을 준비하는 중…",
      "arrive": "Director가 자주 쓰는 움직임 18개를 골라 왔어요",
      "judge": "",
      "hint": "만들 움직임을 눌러 고르세요",
      "selHint": "{n}편 선택됨",
      "confirmLabel": "{n}편 만들기",
      "doneText": "움직임 영상을 대기열에 넣었어요",
      "preselect": [
        "idle_good",
        "idle_bad",
        "glad_good",
        "amused_good",
        "shy_good",
        "sorry_good"
      ],
      "presets": [
        {
          "label": "첫 실행 6편",
          "ids": [
            "idle_good",
            "idle_bad",
            "glad_good",
            "amused_good",
            "shy_good",
            "sorry_good"
          ]
        },
        {
          "label": "모두 선택",
          "all": true
        },
        {
          "label": "모두 해제",
          "ids": []
        }
      ],
      "candidates": [
        {
          "id": "idle_good",
          "title": "대기 · 미소"
        },
        {
          "id": "idle_bad",
          "title": "대기 · 무표정"
        },
        {
          "id": "glad_good",
          "title": "반가움"
        },
        {
          "id": "amused_good",
          "title": "웃음"
        },
        {
          "id": "shy_good",
          "title": "수줍음"
        },
        {
          "id": "sorry_good",
          "title": "미안함"
        },
        {
          "id": "joy_good",
          "title": "신남"
        },
        {
          "id": "curious_good",
          "title": "궁금함"
        },
        {
          "id": "surprised_good",
          "title": "놀람"
        },
        {
          "id": "flutter_good",
          "title": "설렘"
        },
        {
          "id": "affection_good",
          "title": "애정"
        },
        {
          "id": "playful_good",
          "title": "장난"
        },
        {
          "id": "pouty_good",
          "title": "삐침"
        },
        {
          "id": "worried_good",
          "title": "걱정"
        },
        {
          "id": "tender_good",
          "title": "다정함"
        },
        {
          "id": "grateful_good",
          "title": "고마움"
        },
        {
          "id": "hurt_good",
          "title": "서운함"
        },
        {
          "id": "sad_good",
          "title": "슬픔"
        }
      ],
      "zeroLabel": "움직임을 골라 주세요"
    }
  ]
};
