# 인계: 글래스 시안과 텍스트 제작 공정 연결

## 지금 상태 한눈에

시안 d-ops.html 상단의 텍스트 공정 버튼에서 실제 모델 덱 설정·캐릭터 기록 API를 연다. 개발 opencodex/basic_test를 유지했다. 기존 공장 현장 애니메이션의 시간·비용·진행은 시연 각본이다. 현재 실제 루트에는 캐릭터0건이다.

## 이번 세션에서 한 일

사용자가 연결 대상으로 지정한 채팅을 읽어 실제 작업물 `/Users/johnhuh619/Documents/Codex/2026-10-26/character-factory-main`과 design.md를 확인했다. 그 폴더의 plans/2026-10-30-text-pipeline-connection.md에 계획표와 API 계약을 먼저 작성했다.

기본 spawn 도구에 요청 모델이 없어 로컬 Codex CLI에서 opencodex의 `opencode-go/deepseek-v4.1-flash`와 high를 명시해 두 작업자를 병렬 실행했다. A는 web/text_pipeline.py와 API 검사를, B는 시안의 shared/text-pipeline.js/.css와 Node 검사를 작성했다. 메인은 app/settings/CLI·HTML·작업대 모델 배정·정적 경로·실제 Chrome 검사를 통합했다. 코딩 세션과 캐릭터 공정의 생성 호출을 구분한다.

서버는 실제 factory.toml을 읽으며 작업 큐만 --jobs-dir로 분리한다. /studio에서 기존 시안을 제공하고 계획·작업자 로그는 서빙하지 않는다. 설정 API는 인증 값·환경변수 이름·서버 주소를 반환하지 않는다. 현재 선택과 실제 생성 출처를 구분하고, 미리보기 일부 표시·설정 저장 실패/연결 끊김·빈 목록을 처리한다. 실행과 사람 관문은 기존 워크숍으로 이동한다.

최종 검사838 passed/1 skipped·기존 경고1개, Ruff355개 파일·diff 검사 통과다. UI Node15개, 실제 Chrome2크기와 실패/출처 검사, 기존 G9 시연과 경로45표본을 확인했다. 자세한 실행 근거는 [검증 기록](../verification.md)을 따른다.

## 결정

D-0074는 연결·계획표·DeepSeek 병렬 작업에 대한 사용자 지시이며 D-0075는 기존 시연을 보존한 구현 선택이다.

## 확인한 사실과 정정

character-factory-poc 루트에는 runs/characters가 없다. 옛 agentic-character-factory의 캐릭터3명과 실험별 루트는 별도 데이터다. 새 덱의 생성물로 복사하거나 현재 기록으로 합치지 않았다. 작업대 S8은 시연에서도 모델 호출0회로 고쳤으며 실제 기록 패널과 각본 모델 스냅샷을 구분했다.

하위 작업 환경에서는 uv 캐시 및 Chrome 실행에 제약이 있었다. A는 기존 .venv로 검사했고 B는 순수 함수 검사를 했다. 메인은 실제 Chrome에서 1280/1512·포커스/ESC·프로필 실패 복구·실제 출처 보존·오프라인을 검증했다. mount 반환 컨트롤러 연결, 본문 축약 표시, 워크숍 URL과 미디어 호출 제외를 통합 과정에서 수정했다.

추가 독립 검토 세션은 10분 상한 안에 응답을 받지 못해 중단했다. 완료된 리뷰나 승인으로 집계하지 않는다. 구현 작업자2개는 정상 완료됐으며 위 검사와 메인 검토를 최종 근거로 남긴다.

## 미결

K-0059: 새 패널은 설정·기록 연결이다. 기존 공장 전체를 실제 작업 스트림으로 바꾼 것은 아니다. 다른 기록 루트는 별도 원천/중복 ID·권한 설계가 필요하다. 캐릭터 생성·학습·관문 승인은 이번에 실행하지 않았다.

## 다음 할 일

검토 주소를 열어 상단 텍스트 공정에서 설정과 빈 상태를 확인한다. 캐릭터를 실제 공장 루트에 생성한 뒤에는 단계·관문·최근 호출·자료 출처를 같은 API로 읽는다. 기존 실험 기록까지 필요하면 새 공정의 결과와 혼동하지 않도록 별도 원천으로 연결한다.

## 떠 있는 것

검토용 로컬 서버 http://127.0.0.1:8776 이 실행 중이다. 명령은 `uv run --locked python -m character_factory_poc.web --root /Users/johnhuh619/projects/character-factory-poc --jobs-dir work/studio-web-jobs-20261030 --port 8776 --log-level warning`이다. 실제 공장 설정을 읽고 큐만 분리한다. 외부 생성/학습 작업은 없다. 계획표·코딩 작업자 기록·브라우저 검사 결과는 시안 폴더 plans/integration-work에 보존했다.
