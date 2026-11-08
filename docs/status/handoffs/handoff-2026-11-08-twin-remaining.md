# 인계: 2026-11-08 트윈 남은 일 1~4(프롬프트·화면·다른 저장소·브랜치)

이전 인계: [handoff-2026-11-08-twin-compare-batch-export.md](handoff-2026-11-08-twin-compare-batch-export.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래 계획 §12 순서 1~10과 그 뒤 남은 일 1~3을 구현했다. 남은 것은 순서 11(공급자 사전 확인과 유료 리허설)과 12(발표 점검)다. 둘 다 사용자 자료·승인이 필요하다.
- 공장 전체 시험 1391개 통과, 건너뜀 0(일회용 PostgreSQL을 켜고 api-svc·chat-svc는 아래 새 브랜치 작업 트리를 대상으로). studio 노드 시험 6개 파일 49개 통과. Ruff 깨끗.
- 실제 공급자 호출·학습·push는 하지 않았다.

## 2. 이번 세션에서 한 일

- 메인(남은 일 2): 트윈의 S4 장면·S5 첫 프레임·S6 무표정 프레임 프롬프트에서 '가상 인물' 문구를 빼고 기준 사진 얼굴 유지 문장으로 바꿨다(`pipeline/origin.is_twin`). S5 첫 프레임이 성별과 상관없이 "Korean woman"으로 고정되던 버그를 외모 명세 성별을 따르게 고쳤다(손흥민 영상이 여성 첫 프레임에서 시작할 뻔했다). `tests/test_twin_prompts.py`가 합성 트윈 흐름의 세 단계 프롬프트 기록을 검사한다.
- 서브에이전트 Hubble(Claude Opus): 진행 화면. `studio/shared/flow.js`·`flow.css`·`runtime.js`, `web/runtime.py`, `studio/tests/flow-twin.test.cjs`·fixtures, `tests/test_web_twin_lanes.py`. 캡처 `/tmp/cf-twin-ui/shots/`.
- 서브에이전트 Descartes(Claude Opus): 관문 화면 G0·G1s·트윈 G8. `web/static/shared/gate.js`·`gate.css`·`gate-foundry.css`, `web/gate_items.py`·`reads.py`, `tests/test_web_twin_gates.py`. 캡처 `/tmp/cfp-twin-gates/shots/`.
- 서브에이전트 Galileo(GPT-6 Astra): api-svc `codex/twin-demo-labels`(`/Users/johnhuh619/projects/_wt/api-svc-twin-labels`, 커밋 a99ff24, 마이그레이션 194). 공장 `doki_app/api_svc.py`, `tests/test_twin_export_api_labels.py`.
- 서브에이전트 Franklin(GPT-6 Astra): Android `codex/twin-demo-labels`(`/Users/johnhuh619/projects/_wt/frontend-twin-labels`, 커밋 49de2bf). 캡처 `AND/build/twin-demo-captures/overview.png`.
- 서브에이전트 Avicenna(GPT-6 Astra): chat-svc `codex/per-character-dialogue-model`(`/Users/johnhuh619/projects/_wt/chat-svc-twin-models`, 커밋 209c572a·ce9114c1). 공장 `doki_app/chat_svc.py`, `tests/test_twin_export_chat_models.py`.
- 메인 통합: 결정 API가 G0·G1s를 받게(`web/app.py` → `reads.decision_gates`), 팀 배치를 `reads.graph_lanes` 한 곳으로 모음, 대상 head 갱신(`stages/export/settings.py`: api-svc 194_twin_demo_labels, chat-svc 0030_projection_gap_backoff), `tests/test_twin_export.py` 기대값(시작 버튼 문구는 이제 미매핑이 아니다), `cfp eval import-blind`.
- 남은 일 4: 공장 작업 트리의 트윈·시험 경로 변경을 `codex/twin-track` 브랜치(작업 트리 `/Users/johnhuh619/projects/character-factory-poc-wt/twin-track`)에 커밋했다. 다른 세션의 화면 브랜치 `codex/foundry-screens`(68c5c97) 위에 쌓았다. 화면 작업과 같은 파일을 고쳐서 main 위에 바로 올리면 충돌하기 때문이다. 다른 세션의 학습 데이터 재료 점검 문서(`handoff-2026-11-08-training-data-ux.md`와 K-0004·K-0098·K-0099·Q-0019·현재 상태 한 줄)는 브랜치에서 뺐다. 메인 작업 트리는 그대로 두었다.

## 3. 결정

- D-0139 남은 일 1~3 구현 방식(제안). 다른 세션이 `foundry-screens` 작업 트리에서 D-0134~D-0138을 먼저 썼다. 두 결정 기록을 합칠 때 번호가 겹치지 않는다.

## 4. 확인한 사실과 정정

- api-svc·chat-svc 원격 main이 공장이 알던 head(149, 0028)보다 앞서 있었다(193, 0030). 오리지널 캐릭터도 새 구조에 그대로 적재됐다. 로컬 `~/projects/api-svc`·`~/projects/relationship-quest-chat` main은 오래된 상태라 실제 적재 확인은 `CFP_API_SVC_REPO`·`CFP_CHAT_SVC_REPO`를 새 작업 트리로 줘야 한다.
- chat-svc는 경로(`RQC_CHARACTER_DIALOGUE_ROUTES`)가 없으면 `503 PROVIDER_UNCONFIGURED`로 멈춘다. 가짜 경로로 BIND·TRAIN 통화 한 턴을 확인했다. 실제 학습 가중치 서빙은 하지 않았다.
- Android 영상통화 화면에 '스테이지 1'과 '고백하기' 버튼이 남아 있다. 팬·가족 통화 틀에는 맞지 않는다. iOS는 손대지 않았다.
- 공장 시드의 캐릭터 ID가 고정이라 두 트윈을 같은 DB에 함께 적재하는 시연 경로는 따로 확인해야 한다(Galileo 보고).
- 1280 폭에서 트윈 학습 캐릭터 그래프는 6열이라 칸 글자가 두세 줄로 꺾인다.

## 5. 미결

- 새 질문 없음. push 여부는 사용자 결정(PersonaFoundry는 공개 저장소이고 실존 인물 계획 문서가 들어 있다).

## 6. 다음 할 일

1. 브랜치 정리: `codex/foundry-screens` → `codex/twin-track` 순서로 합친다. api-svc·chat-svc·frontend 브랜치는 각 저장소 규칙대로 PR.
2. Android 영상통화의 '스테이지 n'·'고백하기'를 트윈 틀에 맞추기, iOS 같은 표시.
3. 순서 11: 실존 얼굴 이미지·영상 공급자 사전 확인 → 손흥민 학습 → 손흥민·부모님 병렬 유료 리허설. chat-svc에 학습 모델 경로 등록 필요.
4. 순서 12: D-0126 발표 점검 네 항목.

## 7. 떠 있는 것

- 일회용 DB 컨테이너 `cfp-verify-pg-1`(127.0.0.1:55439)는 서브에이전트들이 함께 써서 켜 두었다가 메인이 마지막에 내린다.
- 서브에이전트 5명은 모두 끝났고 닫았다.
- 새 작업 트리 4개: `~/projects/_wt/api-svc-twin-labels`, `~/projects/_wt/chat-svc-twin-models`, `~/projects/_wt/frontend-twin-labels`, `~/projects/character-factory-poc-wt/twin-track`.
