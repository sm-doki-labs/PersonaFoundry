# 실제 페르소나 대화 품질: 차은결

요청 기준일은 2026-10-28이며 실제 실행은 2026-10-29 KST다. [전체 원문·설계 대조·판정 HTML](2026-10-28-persona-quality.html)을 함께 본다.

## 세 질문의 결론

1. **자연스러움은 부분적으로 만족한다.** 짧은 위로와 정정은 읽을 만하지만, 자유 대화가 약속 조율·확답 보류·경계 설명으로 굳는다. 설렘이나 생활감보다 행동 규칙이 앞선다.
2. **성격은 선택으로 드러난다.** 지각에는 온전한 재약속, 업무 마감과 명시적 거절은 우선 보존, 곤란한 사정에는 작은 도움으로 전환했다. 다만 요청하지 않은 상황에도 규칙을 과잉 적용했다.
3. **말투는 부분적으로 재현된다.** 해체 반말과 ‘~할게’, ‘~는 어려워’는 유지됐지만 기획의 voiceExamples·말높임·생활 배경이 프롬프트까지 온전히 전달되지는 않았다. 전체 문장 길이 중앙값은 긴 24자, 짧은 21자다. 자유 대화만 보면 긴 20자, 짧은 21.5자로, 짧은 프롬프트가 언제나 더 짧은 문장을 만든 것은 아니다.

## 실제 대화 근거

- `long/choice-late/1`: “이번 주 목요일이나 금요일 저녁에 다시 보는 건 어때?”라고 답했다. 이어 넘어진 사정이 나오자 3턴에서 “내가 지금 그쪽으로 가서 짐 같이 정리해 줄까?”라고 전환했다.
- `long/choice-praise/3`: “그냥 네가 좋았어”에 “지금 당장 확답을 주기는 어렵지만”이라고 답해, 재촉이 없는 장면까지 보류 규칙을 가져왔다.
- `long/want-trust/1`: “이번 주 매일 마감”이라는 사용자 조건 뒤에 “마감 없는 일요일”을 만들어 맥락을 어겼다.
- `long/affection/8`: 검색 도구가 없는데 “바로 검색해서 확인해 줄게”라고 말했다. 짧은 조건의 같은 질문에는 모른다고 답했다.

## 경로와 상태

현행 씨앗 → 변형 3안 → G3 경로를 사용했다. 기존 합성 S1 순위·Scout를 재생하고 이미지는 fake 단색, S2는 picked로 통과할 수 있었다. 외모 품질은 시험 범위 밖이다. 26세 여성·독립 책방 직원 씨앗에서 S3 실제 첫 3안을 생성하고, 기다림(v1)·일정 축소(v2)보다 온전한 재약속을 우선하는 v3의 선택 차이가 가장 분명해 reviewer=agent로 골랐다. S7·S8도 실제 생성했으며 G6는 사람 검토 대기 상태다. 전체 공정이나 L3 품질을 통과했다고 기록하지 않았다.

- 캐릭터 ID는 `cf-20261029-persona-quality`다.
- 기획은 `pr1/v3`, 특질은 `tr1`, 프롬프트는 `pv1`이다.
- 긴 프롬프트는 5,141자, 짧은 프롬프트는 1,791자다.
- 프롬프트별 16장면·67응답을 수집했다. 자유 대화 4장면은 각각 사용자 10턴이며, 설계 대조 12장면은 choices 3개·boundaries 4개·wantsAndFears 3개·misreadings 2개를 모두 다뤘다.
- 고정 G6 system + 실제 누적 이력 + 현재 사용자 턴 + 첫 응답 하나를 사용했다. 응답 재추출은 없고 134응답 모두 finish_reason=stop이다.

## 호출 수와 비용

| 용도 | 모델 | 실제 호출 수 |
|---|---|---:|
| S3·S7·S8 생성 | `gpt-6.1-sol` | 4 |
| 긴·짧은 실제 대화 | `google-antigravity/gemini-3.8-flash` | 134 |
| 장면 단위·턴별 결함 판정 | `anthropic/claude-sonnet-5` | 34 |
| 합계 | 텍스트 실제 호출만 센다. | 172 |

대화 모델은 relationship-quest-chat의 `DEFAULT_MODEL_ROUTES`와 `dialogue-gemini-3-8-flash-native-low-v1.json`에서 확인한 기본 모델과 같다. 중계에 있어 모델 대체는 하지 않았다. 실제 배포 환경의 override와 제공자 내부 모델 revision은 확인하지 않았다.

입력 토큰은 656,286개, 출력은 247,306개이며 추론 토큰을 포함한다. 중계에 공식 단가가 없어 **실제 청구액은 모른다.** 실행 전 예상은 입력 $1–10/M·출력 $5–50/M라는 가정에서 $2.35–23.54였고, 실제 사용량에 같은 가정을 적용하면 **$1.89–18.93**다. 공급자 단가나 실제 청구액이 아닌 민감도 계산이다. 저장소 dry run의 `$0.00`은 단가 미입력 값으로 무료를 뜻하지 않는다. 모든 호출 단계와 판정 재시도 앞에 dry run을 저장했다. 합성 Scout와 fake 이미지 호출은 실제 텍스트 호출 수에서 제외했다.

## 첫 출력과 재시도

S3 1회, S7 2회, S8 1회다. S7 첫 출력이 strict 계약에서 허용하지 않는 이름·나이·직업·성격·챕터 칸을 추가해 오류 피드백으로 한 번 재시도했다. 기획·특질·프롬프트를 품질 때문에 다시 뽑거나 직접 고치지 않았다. G3 결정의 reasons 배열을 문자열로 고친 로컬 입력 오류는 모델 호출을 추가하지 않았다.

Claude 첫 판정 중 긴·짧은 호감 장면은 16,000 출력 토큰 상한에 걸려 각각 한 번씩 reasoning_effort=low로 판정만 다시 수집했다. 실패한 첫 원문도 보존했다. 근거 인용 3개는 assistant 원문과 일치하지 않아 표시했으며 재판정하지 않았다. 총 134턴×5차원=670개 분류를 받았지만 점수나 합격률을 최종 품질로 쓰지 않았다. Claude는 설계된 도움 전환을 성격 major로 잘못 의심했고, 이미 언급된 토요일 마감을 새 사실로 오판했다. 직접 읽은 결론에 이 판정들은 채택하지 않았다.

## 한계와 실행하지 않은 것

캐릭터 한 명·한 생성 기획·각 조건의 첫 응답만 시험했다. 실제 사용자의 블라인드 선호 평가, 다른 두 변형이나 무페르소나 대조군, 동일 실제 이력으로 한 턴만 바꾼 프롬프트 길이 실험은 하지 않았다. 서비스 전체 시스템·챕터 상태 전이를 재현하지 않았다. S8의 CHAPTERS는 원래 chapterArc를 전달받지 못하고 일반 행동 규칙으로 채워졌다.

실제 이미지·영상 생성, 외부 수집, S3r 실제 참고 검색, S9 데이터, 학습 제출, G6 사람 승인, 릴리즈·배포·DB 적재는 하지 않았다. S8 내장 단문 probe는 비워 두고 이 별도 장면 시험으로 비교했다. 기존 오프라인 검사는 **514 passed, 1 skipped**이며 DB 적재 검사는 이번에 실행하지 않았다.

## 재현과 원본 위치

원본은 `/Users/johnhuh619/projects/character-factory-poc/runs/experiments/20261028-persona-quality`에 보존했다. `evidence/`에는 요청·응답 본문과 SHA-256·usage·반환 모델이, `dialogues/`와 `judgments/`에는 턴 원문과 분류가 있다. 단계 결과와 G6 페이지는 `runs/characters/cf-20261029-persona-quality/`에 있다. `direct-review.json`, `metrics.json`, `voice-statistics.json`, `dialogue-verification.json`, `judgment-verification.json`을 함께 보존했다.

실행 스크립트는 기본이 dry run이며 실제 호출에는 `--execute`가 필요하다. 생성 스크립트는 bootstrap·s3·s7·s8을, 대화 스크립트는 dialogue·judge와 mode/kind/scene 필터를 제공한다. report 스크립트는 외부 호출 없이 보존 원문으로 HTML을 다시 만든다. `work/persona-quality/recover_judgments.py`는 인용 검증으로 파생 보기가 빠진 최초 판정 원문 2개를 외부 호출 없이 복구한 임시 도구다.

## 변경 파일 전체 목록

커밋하지 않았고 다른 저장소는 읽기만 했다. 애플리케이션의 src·테스트·계약은 바꾸지 않았다. Git 제외 실행 산출물은 위 `runs/`와 임시 `work/`에 있다.

- [docs/README.md](/Users/johnhuh619/projects/character-factory-poc/docs/README.md) 파일을 추가하거나 갱신했다.
- [docs/reports/2026-10-28-persona-quality.html](/Users/johnhuh619/projects/character-factory-poc/docs/reports/2026-10-28-persona-quality.html) 파일을 추가하거나 갱신했다.
- [docs/reports/2026-10-28-persona-quality.md](/Users/johnhuh619/projects/character-factory-poc/docs/reports/2026-10-28-persona-quality.md) 파일을 추가하거나 갱신했다.
- [docs/status/README.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/README.md) 파일을 추가하거나 갱신했다.
- [docs/status/current-state.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/current-state.md) 파일을 추가하거나 갱신했다.
- [docs/status/decisions.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/decisions.md) 파일을 추가하거나 갱신했다.
- [docs/status/known-issues.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/known-issues.md) 파일을 추가하거나 갱신했다.
- [docs/status/verification.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/verification.md) 파일을 추가하거나 갱신했다.
- [docs/status/handoffs/handoff-2026-10-29-persona-quality.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/handoffs/handoff-2026-10-29-persona-quality.md) 파일을 추가하거나 갱신했다.
- [scripts/persona_quality_20261028.py](/Users/johnhuh619/projects/character-factory-poc/scripts/persona_quality_20261028.py) 파일을 추가하거나 갱신했다.
- [scripts/persona_dialogue_20261028.py](/Users/johnhuh619/projects/character-factory-poc/scripts/persona_dialogue_20261028.py) 파일을 추가하거나 갱신했다.
- [scripts/persona_report_20261028.py](/Users/johnhuh619/projects/character-factory-poc/scripts/persona_report_20261028.py) 파일을 추가하거나 갱신했다.
