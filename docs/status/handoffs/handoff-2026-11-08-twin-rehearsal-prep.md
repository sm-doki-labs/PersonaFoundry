# 인계: 2026-11-08 트윈 리허설 준비(두 트윈 같은 DB·발표 점검·사전 확인·main 병합)

이전 인계: [handoff-2026-11-08-twin-remaining.md](handoff-2026-11-08-twin-remaining.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래(트윈)는 계획 §12 순서 1~10과 남은 일을 마쳤다. 순서 11은 사용자 자료·비용 승인 직전까지, 순서 12는 공장 안 점검(자동 + G9 사람 확인)까지 준비했다.
- 작업은 `codex/twin-track` 브랜치(작업 트리 `/Users/johnhuh619/projects/character-factory-poc-wt/twin-track`)에 있고 원격 main(22e54fa, 화면·학습 경로·README PR #1~#3)을 병합했다. 충돌은 결정 기록·`studio/shared/flow.js`·`flow.css` 셋이었다.
- 병합 결과 전체 1440개 통과(일회용 PostgreSQL 적재 포함, api-svc·chat-svc는 새 브랜치 작업 트리 기준), studio 노드 시험 52개, ruff·format 깨끗. 실제 공급자 호출·push 없음.
- 메인 작업 트리(`/Users/johnhuh619/projects/character-factory-poc`)의 커밋 안 된 트윈 사본은 이제 낡았다. 트윈 작업은 `codex/twin-track`에서 이어 간다.

## 2. 이번 세션에서 한 일

- 서브에이전트 Goodall(GPT-6 Astra): 앱 시드 ID를 캐릭터별 구간으로(`doki_app/naming.api_seed_ids`, `api_svc.py`), `tests/test_export_two_characters.py`(두 트윈을 같은 api-svc·chat-svc DB에 적재·재적재).
- 서브에이전트 James(Claude Opus): 발표 점검 `stages/s11_release/presentation.py`(`twin-presentation-check-v1`), 트윈 대화 표시 문단(`s11_release/twin.py`), G9 점검표 화면(`gate_items.py`·`gate.js`·`gate.css`), `tests/test_twin_presentation_check.py`.
- 서브에이전트 Kepler(GPT-6 Astra): `cfp twin precheck`(`stages/s0_source/precheck.py`), `examples/twin/`, `docs/guides/twin-rehearsal.md`, `tests/test_twin_precheck.py`.
- 서브에이전트 Kant(Claude Opus): 진행 화면 6열 트윈 그래프 노트북 폭 배치(`flow.css`·`flow.js`), 390 폭 긴 프롬프트 그래프 찌그러짐 수정.
- 메인: G9 서버 차단 연결(`s11_release/approve.py` → `guard_g9`)과 웹 결정 경로 끝까지 시험, 시험 격리(`tests/conftest.py`: 실제 적재가 없으면 대상 저장소 head를 로컬 체크아웃에서 읽지 않음), 결정 번호 정리, origin/main 병합.

## 3. 결정

- D-0143 남은 일 정리와 순서 11·12 준비(제안).
- 번호 옮김: 다른 세션이 D-0130·D-0131·D-0134~D-0139를 먼저 main에 합쳤다. 트윈의 D-0130(s0 구현)·D-0131(순서 3·4·7)·D-0139(남은 일 1~3)를 D-0140·D-0141·D-0142로 옮기고, 아직 합쳐지지 않은 트윈 인계·계획·코드 주석의 참조도 함께 고쳤다. 커밋 8dc4f0d의 메시지에는 옛 번호가 남아 있다.

## 4. 확인한 사실과 정정

- 지난 인계의 "전체 1391개 통과"는 `CFP_API_SVC_REPO`·`CFP_CHAT_SVC_REPO`를 새 브랜치로 준 상태였다. 환경변수 없이 돌리면 흐름 시험 5개가 로컬 `~/projects/api-svc`(149)·`relationship-quest-chat`(0028)의 옛 head 때문에 실패했다. `tests/conftest.py`로 고쳤다.
- 공장 설정(메인 작업 트리 factory.toml)의 영상 공급자는 `fake`다. `cfp twin precheck` 계획에 `fake-video`가 나온다. 실제 사전 확인 전에 영상 공급자를 xAI로 설정해야 한다.
- 앱 시드 새 ID는 2,000,000부터 캐릭터당 1,024칸, 최대 약 10억 7천만(Android Int 안). api-svc 시드 로더는 적재 뒤 시퀀스를 최댓값으로 맞춘다. 로컬 시연 DB 전용 방식이고 운영 DB에는 쓰지 않는다.
- 2026-11-07 로컬 시험 스택(`work/tp-stack`, `tp_local_stack.py`)의 `db` 단계는 기존 DB를 지운다. 두 트윈을 올릴 때는 쓰지 않고 `scripts.seed --file … load`(`--replace` 없이)와 chat-svc `publish`·`verify`로 더한다(Goodall 보고, 실행 안 함).
- Android 영상통화 화면 변경은 AI 표시 배지와 서버 단계 이름뿐이다. '고백하기'·'스테이지 n'은 사용자 질문에 따라 고치지 않는다. iOS는 시연 기기가 Android라 범위 밖이다.

## 5. 미결

- push·PR 여부(사용자 결정): 공장 `codex/twin-track`(공개 저장소, 실존 인물 계획 문서 포함), api-svc `codex/twin-demo-labels`, chat-svc `codex/per-character-dialogue-model`, frontend `codex/twin-demo-labels`.

## 6. 다음 할 일

1. 사용자 자료·승인: 손흥민 출처 자료와 사진, 부모님 카톡 내보내기·사진·발표 공개 동의, 비용 승인.
2. 영상 공급자를 xAI로 설정한 뒤 `cfp twin precheck --photo … --execute`(이미지 1·영상 1, 약 $0.19 + 구독 이미지).
3. [리허설 안내서](../../guides/twin-rehearsal.md) 순서대로 `cfp batch run --spec … --execute`.

## 7. 떠 있는 것

- 일회용 DB 컨테이너 `cfp-verify-pg-1`은 마지막에 내렸다.
- 서브에이전트 4명은 끝났고 닫았다.
- 작업 트리: `~/projects/character-factory-poc-wt/twin-track`, `~/projects/_wt/api-svc-twin-labels`, `~/projects/_wt/chat-svc-twin-models`, `~/projects/_wt/frontend-twin-labels`.
