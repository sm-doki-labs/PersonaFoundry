# 인계: Foundry 브랜드·3단 화면·관문 화면 테마(D-0102)

## 지금 상태 한눈에

- 진행 화면 `studio/factory.html`이 Foundry 브랜드의 3단 화면(왼쪽 탐색, 가운데 공정, 오른쪽 단계 정보)과 오른쪽 검토 시트로 바뀌었다. 밝은·어두운 화면을 고를 수 있다.
- 디자인 토큰 `shared/foundry-tokens.css`(studio와 web/static 두 사본)를 새로 두었고, 시트 안 관문 화면은 `gate-foundry.css`로 같은 톤을 입는다. 따로 연 관문 화면은 기존 글래스 모양이다.
- 가짜 공급자 합성 캐릭터로 밝은·어두운 화면 각각 17/17 단계·12/12 관문을 이 화면에서만 조작해 완주했다. 실제 모델 호출은 0회, 실제 `runs/characters`는 건드리지 않았다.
- commit/push는 하지 않았다.

## 이번 세션에서 한 일

사용자는 진행 화면의 색과 구조가 프로페셔널하지 않다며 디자인 업계 용어로 형태를 정의하고 현행 서비스 색을 참고해 브랜딩하라고 했다. 형태(운영 콘솔, 앱 셸 3단, 시트), 색 원칙(중립 우선 + 의미색 + 강조 하나), 토큰 세 층, 출처 팔레트(Radix Slate·Violet·Blue, GitHub Primer 상태색), 브랜드(Foundry)를 제안했고, 사용자가 "좋아 이 기준대로 진행해줘. 3-pane 구조랑 브랜드 적용하고 관문 화면도 같은 톤으로 맞춘 다음, 밝은·어두운 화면 둘 다 가짜 모델로 돌려서 확인해줘"로 확정했다.

1. 토큰: `studio/shared/foundry-tokens.css`, `src/character_factory_poc/web/static/shared/foundry-tokens.css`(같은 내용).
2. 진행 화면: `studio/factory.html`(파비콘, 테마 미리 읽기, 3단 골격, 시트), `studio/shared/flow.css`(전면 재작성, 반응형), `studio/shared/flow.js`(순수 함수 유지, mount 재작성: 사이드바·머리줄·캔버스·인스펙터·시트, 테마 전환, 로고).
3. 관문 화면: `src/character_factory_poc/web/static/gate.html`이 토큰과 `shared/gate-foundry.css`를 읽고, `?skin=foundry&theme=`일 때만 `body.fd`를 붙인다.
4. 시험: `studio/tests/flow.test.cjs`에 토큰 일치·관문 덮어쓰기 범위 시험 1개(총 7개).
5. 스튜디오 첫 페이지 카드 문구와 미리보기 `studio/previews/flow.jpg`(Git 밖)를 새 화면으로 바꿨다. 디자인 기준 `studio/.ui-craft/brief.md`에 Foundry 기준을 더했다.
6. 문서: PRD v1.16 §22(FR-73), 명세 v1.16 §26, LLD v1.17 §24, [공장 화면 안내](../../guides/agentic-studio.md), 결정·알려진 문제·검증 기록·현재 상태.
7. 검증: 서버 1230 passed/1 skipped, 화면 노드 42 passed, ruff·format·diff 검사 통과. 밝은(8796)·어두운(8798) 화면 가짜 공급자 완주, 좁은 폭(8799, 1280·390) 확인. 명령과 캡처 경로는 검증 기록 2026-11-07 D-0102 항목에 있다.

## 결정

D-0102(형태·구조·팔레트 출처 확정, 세부 값·로고·문구 제안).

## 확인한 사실과 정정

- 기존 `studio/.ui-craft/brief.md`의 "새 브랜드·폰트·효과를 추가하지 않는다"는 2026-10-30 연결 작업의 기준이었다. 이번 사용자 지시로 진행 화면 범위에서는 Foundry 기준을 따르도록 고쳤다. d-ops·시연·따로 연 관문 화면은 글래스 기준 그대로다.
- 관문 화면은 안쪽 구획에 인라인 반투명 배경(`rgba(0,0,0,.14)`)이 있어 변수만 바꾸면 밝은 화면에서 탁해졌다. `gate-foundry.css`가 `body.fd` 안에서 덮는다.
- 390px에서는 사이드바가 숨으므로 테마 버튼이 보이지 않는다(K-0088).
- 참고한 상용 서비스(Linear, Vercel, GitHub, Radix)의 색값은 공개 팔레트(Radix Colors, Primer) 기준이며, Linear 화면의 실제 값은 확인하지 않았다.

## 미결

K-0085는 해결 표로 옮겼다. K-0086은 어두운 화면 부분이 확인됐고 실패·반려 브라우저 표시가 남았다. K-0088(좁은 폭 테마 버튼)을 새로 열었다. K-0084, K-0087은 그대로다. 새 질문은 없다.

## 다음 할 일

1. K-0086: `work/factory-flow-20261107/e2e_server.py`를 고쳐 가짜 공급자에 실패를 넣고, 실패 → 다시 실행, 반려 → 다시 만들기, 수정 상한 도달을 `factory.html`에서 밝은·어두운 화면으로 확인한다.
2. K-0088: 머리줄에 테마 메뉴를 두어 좁은 폭에서도 바꿀 수 있게 한다.
3. K-0084: 캐릭터 상세에 외모 입력 유무를 내주고 외모 갈래를 "건너뜀"으로 그린다.
4. 사용자가 로고·문구·세부 색을 확정하면 D-0102의 제안 부분을 확정으로 바꾼다.

## 떠 있는 것

- 임시 서버 8796(`/tmp/cf-flow-e2e-light`), 8798(`/tmp/cf-flow-e2e-dark`), 8799(`/tmp/cf-flow-narrow`)는 모두 강제 종료했다. 떠 있는 서버·프로세스는 없다. 내장 브라우저 시험 탭도 닫았다.
- 임시 자료: `/tmp/cf-flow-e2e-light/`, `/tmp/cf-flow-e2e-dark/`, `/tmp/cf-flow-narrow/`, `work/factory-flow-20261107/`(서버 스크립트, 시험 로그, 캡처 shots-light·shots-dark·shots-narrow, 조작 기록).
