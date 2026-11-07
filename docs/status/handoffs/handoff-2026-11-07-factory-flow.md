# 인계: 진행 화면과 단계 이력(D-0101)

## 지금 상태 한눈에

- 새 기본 진행 화면 `studio/factory.html`(+`shared/flow.js`, `shared/flow.css`)이 있다. 팀 묶음 그래프, 지금 할 일, 단계 상세·회차 이력, 상세 영역 안의 관문 검토, 시작 전 목표 고르기, 첫 화면(캐릭터 없음), 연결 상태를 실제 서버 기록으로 그린다.
- 서버는 단계 상태 전이를 `ledger/stage-events.jsonl`에 덧붙이고, 캐릭터 상세에 시작·종료·결정 시각, 회차 이력, 관문 열린 시각, 추정 비용을 싣는다. 그래프 응답에 유료 단계와 자동 재개 설정이 있다.
- 가짜 공급자 합성 캐릭터 완주를 이 화면에서만 조작해 확인했다. 실제 모델 호출은 0회다. 실제 `runs/characters`는 건드리지 않았다.
- commit/push는 하지 않았다.

## 이번 세션에서 한 일

사용자는 공장 화면이 조잡하다며 n8n 같은 파이프라인 도구의 모양을 원했다. 상용 화면(GitHub Actions, Figma Weave, Trigger.dev 등)을 참고한 시안 세 개를 그렸다. 서브에이전트 세 명(시각·사용 흐름·구현 가능성)의 검토와 UX 빠진 상태 검토를 거쳐 팀 묶음 그래프 시안 v3를 정했다. 그 뒤 "이 시안대로 실제 공장 화면에 적용해줘. 서버에 단계 이력 기록이랑 관문 대기 시각도 추가하고, 가짜 모델로 처음부터 끝까지 돌려서 확인해줘"를 지시했다. 이전 인계(공식 API)의 다음 할 일보다 이 요청을 우선했다.

1. 서버: `pipeline/state.py`(전이 기록), `web/reads.py`(stage_timeline, gate_timeline, cost_summary, 시각 칸, history, cost, 서명에 회차·revision, 팀 상태 순서), `web/runtime.py`(paid, orchestrator), `web/app.py`(factory.html 허용). 시험 `tests/test_web_history.py` 8개.
2. 화면: `studio/factory.html`, `studio/shared/flow.js`(runtime.js 순수 함수 재사용), `studio/shared/flow.css`, `studio/tests/flow.test.cjs` 6개. 스튜디오 첫 페이지에 진행 화면 카드와 미리보기 `studio/previews/flow.jpg`를 더했다.
3. 문서: PRD v1.15 §21(FR-70~72), 명세 v1.15 §25, LLD v1.16 §23, [공장 화면 안내](../../guides/agentic-studio.md), 결정·알려진 문제·검증 기록·현재 상태.
4. 검증: 서버 1230 passed/1 skipped, 화면 노드 41 passed, ruff·diff 검사 통과. 가짜 공급자 완주와 빈 화면·등록·연결 끊김 브라우저 확인. 자세한 명령과 결과 경로는 검증 기록 2026-11-07에 있다.

시안 원본은 대화 시각화 폴더에 있고 저장소에는 넣지 않았다. 브라우저 조작은 Codex 내장 브라우저의 locator로 했으며, 재사용할 수 있는 스크립트 파일은 남기지 않았다. 조작 순서와 결과는 `work/factory-flow-20261107/e2e-steps.json`에 있다.

## 결정

D-0101(범위 확정, 표시 세부 제안).

## 확인한 사실과 정정

- 실행 확인 작업은 그 단계만 `until`로 돌린다. 그래서 마지막 작업의 `until`을 목표로 보이면 "소개 영상까지"처럼 잘못 보였다. 화면은 확인 작업이 아닌 가장 최근 작업에서 목표를 읽는다.
- 관문 결정 뒤 자동 재개는 `resume_until`(실제 설정 sx)까지 이어서 돈다. 시작 전 목표는 첫 작업의 끝일 뿐이다. 시작 전 화면이 이를 문장으로 알린다.
- 실제 관문 제목은 "프롬프트 승인"처럼 `reads.GATE_TITLES`를 따른다. 시안의 "프롬프트 검토" 같은 문구는 쓰지 않았다.
- uvicorn은 SSE 연결이 열려 있으면 Ctrl-C로 끝나지 않는다(K-0087).

## 미결

K-0084(브리프만 있는 캐릭터의 외모 갈래 건너뜀 미표시), K-0085(관문 화면 테마 불일치), K-0086(어두운 설정·실패·반려·실제 공급자 브라우저 미검증), K-0087(서버 종료). 새 질문은 없다.

## 다음 할 일

1. K-0086: 가짜 공급자에 실패를 넣은 임시 서버(`work/factory-flow-20261107/e2e_server.py`를 고쳐 쓴다)로 실패 → 다시 실행, 반려(REJECT) → 처음부터 다시 만들기, 수정 상한 도달을 `factory.html`에서 확인하고 어두운 설정 캡처를 남긴다.
2. K-0084: 캐릭터 상세에 외모 입력 유무(순위 목록·외모 자료)를 내주고, 화면이 외모 갈래를 "건너뜀"으로 그리게 한다.
3. K-0085: `gate.css`에 embedded 밝은 테마를 더한다.
4. 실제 서버(8776)를 띄울 때는 안내의 명령을 쓰고 `/studio/factory.html`을 연다.

## 떠 있는 것

- 임시 서버 8796(`/tmp/cf-flow-e2e-r1`, 가짜 공급자)과 8797(`/tmp/cf-flow-empty-r1`)은 모두 종료했다. 떠 있는 서버·프로세스는 없다.
- 임시 자료: `/tmp/cf-flow-e2e-r1/`, `/tmp/cf-flow-empty-r1/`, `work/factory-flow-20261107/`(서버 스크립트, 시험 로그, 캡처, 조작 기록).
