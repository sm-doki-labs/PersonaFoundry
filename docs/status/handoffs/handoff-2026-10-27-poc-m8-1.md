# 인계: 2026-10-27 PoC M8 1차(계약 + A·B·F·G 갈래)

이전 인계: [handoff-2026-10-27-poc-plan.md](handoff-2026-10-27-poc-plan.md)

## 1. 지금 상태 한눈에

- 작업 위치가 새 Git 프로젝트 `/Users/johnhuh619/projects/character-factory-poc`로 바뀌었다. 원본 `agentic-character-factory`(Git 없음)의 2026-10-27 상태를 첫 커밋 `c3a85e9`으로 옮겼다. 원본은 고치지 않았다.
- PoC 계약(`f8bc6e4`)과 A·B·F·G 갈래를 `main`에 합쳤다. `scripts/check.sh` 347 passed.
- 남은 갈래: C S9 데이터셋, D S10 학습·평가, E 패키지·우리 앱 변환기, G 2차(관문별 화면), H 통합. 그래프에는 아직 S9~S11이 `implemented=False`다.
- 실제 공급자는 부르지 않았다.

## 2. 이번 세션에서 한 일

- 새 프로젝트를 만들고 Git을 초기화했다(사용자 요청). 워크숍 서버용 `fastapi`·`uvicorn`을 `main`에 먼저 넣었다(`14434ae`).
- 계약 갈래: `src/acf/contracts/dataset.py`·`training.py`·`release.py`(새 계약 14개)와 PRD·명세·LLD v1.3. 두 앱의 적재 경로를 읽기만 해서 확인했다: api-svc `scripts.seed load`(`dokilabs-seed/1`), chat-svc `scripts.db_ops.content_release publish`(`data/` 트리).
- 하위 에이전트 네 개(`opencode-go/deepseek-v4.1-flash`, 사용자 지정)를 갈래별 브랜치·worktree에서 돌렸다: A `codex/poc-a-face-once`(`ec4eb50`), F `codex/poc-f-grok-oauth`(`cd62676`), B `codex/poc-b-ranking`(`4234f5c`), G `codex/poc-g-workshop`(`5266cc5`). 파일 겹침 없이 `--no-ff`로 합쳤다.
- 통합 연결: `acf ref collect`(dry run 기본, 테스트 2개), S5·S6 비용 계획에 `grok_oauth`, `factory.example.toml`에 `[stages.s1.collect]`·`grok_oauth` 예시·`[web]`, `pyproject.toml` package-data에 `web/static/**/*`. LLD에 갈래별 구현 메모를 더했다.
- 실행하지 않은 것: 실제 순위 수집, 실제 이미지·LLM·영상·학습 호출. 워크숍 화면은 하위 에이전트가 합성 루트로 브라우저 확인했고 통합 담당은 다시 열어 보지 않았다.

## 3. 결정

- D-0046(제안): 순위 출처 랭키파이 채택, 한국기업평판연구소 제외.

## 4. 확인한 사실과 정정

- 랭키파이 목록은 분류당 10명이라 기본 군집 설정과 맞지 않는다(K-0035).
- xAI 공식 문서는 영상 API 인증을 API 키 Bearer로만 설명한다. OAuth 토큰 수용은 미확인이다(K-0036).
- `base_photo`의 문서상 기본값은 `generate`라 PoC 설정은 `picked`를 명시해야 한다.

## 5. 미결

- Q-0022(새로): 랭키파이 원자료 재사용 허락.
- K-0034(일부 해결: `generate`만 남음), K-0035·K-0036·K-0037(새로).

## 6. 다음 할 일

1. C·D·E 갈래를 계약(LLD §5.14·§5.15·§5.17·§8.8~§8.11)대로 병렬 구현한다. 쓰기 범위: C `src/acf/stages/s9_data/`, D `src/acf/providers/training/`·`src/acf/stages/s10_train/`·`s10_eval/`, E `src/acf/stages/s11_release/`·`src/acf/stages/export/`. 그래프 연결은 H가 한다.
2. G 2차: 관문별 상세 화면(K-0037).
3. H 통합: 그래프에 `s9s`·`s9`·`s10t`·`s10`·`s11`·`sx`, `tests/test_offline_pipeline.py`(여성·남성 합성 브리프).
4. 사용자 지시가 있으면 순위 수집·이미지·LLM 실제 1회(P-24). 그 전에 Q-0022 확인.

## 7. 떠 있는 것

- 하위 에이전트는 모두 닫았다. worktree 네 개는 정리했고 브랜치는 남겼다.
- 저장소 밖: `/tmp/acf-snapshot-20261027-poc/`(원본 저장소 스냅샷), `/tmp/acf-*.py`·`/tmp/acf-*.json`(문서 편집 스크립트). 지워도 된다.
