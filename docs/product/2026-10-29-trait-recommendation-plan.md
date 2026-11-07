# 추가 특질 추천 Implementation Plan

> 실행: superpowers:executing-plans. 사용자 요청 "그렇게 개선하자"에 따라 합의한 추천 흐름을 구현한다. 기존 작업 브랜치의 미커밋 내용을 보존하고 commit/push는 하지 않는다.

**Goal:** 내부 제작자가 형용사로 성격을 입력하고 보유 행동 특질을 선택적으로 추가해 상세 기획과 최종 프롬프트까지 보존한다.
**Architecture:** 저작 프리셋의 행동 144개만 출처와 함께 투영한 내장 카탈로그를 사용한다. 로컬 어휘 검색으로 추천/직접 검색을 제공하고, 선택하지 않아도 씨앗을 저장한다. 선택한 특질은 별도 정본 필드로 고정하고 기존 S3 의미 검토 및 S7 설계와 최종 컴파일에 연결한다.
**Tech Stack:** Python 3.12, Pydantic, FastAPI, 기존 정적 HTML/JS 워크숍, pytest.
**Spec:** PRD 신규 §15, 명세 신규 §18, LLD 신규 §16 (동일 세션에 반영).

## 확정된 사용자 의도와 구현 판단

자유 성격 입력, 추가 특질 추천, 내부 제작자 편의 우선은 사용자 확정이다. 추천 한 화면 5개/추가 최대5개, 어휘 기반 첫 버전과 선택 특질 출처 구조는 구현 판단이다. 강한 관련/의외의 면/다른 방향을 제시하지만 조합의 심리학적 타당성이나 품질 합격을 주장하지 않는다. 선택은 자동 적용하지 않으며 후보/관문 승인은 유지한다. SNS 자동 라벨 원문과 원 인물 사실은 이번 저작 카탈로그에 넣지 않는다.

## Global Constraints

- 다른 저장소와 고정된 실험 산출물은 읽기만 한다. 모델 호출/학습/배포/commit/push는 하지 않는다.
- 48개 프리셋의 authored expression_focus 144문장만 사용한다. 성격 검사 측정값이나 실존 인물의 특질로 표기하지 않는다.
- 추천은 optional이고 selectedTraits 기본값은 빈 목록이다. 형용사 원문과 고정 신원은 덮어쓰지 않는다.
- 원 카탈로그 SHA256, preset ID, field path, literal behavior를 묶어 저장한다. 알 수 없는 ID, 중복, 변조, 오래된 화면/씨앗은 거절한다.
- 추가 특질은 기본 성격을 대체하지 않는 조건부 성향이다. 상황이 없는데 약속/종료시간/관계를 생성하는 규칙을 추가하지 않는다.
- 화면은 기존 어두운 워크숍 스타일과 시스템 글꼴을 재사용하며, 태그 144개를 한꺼번에 요구하지 않는다.
- 저장은 유료 생성을 시작하거나 관문을 승인하지 않는다. 다음 실행은 기존 작업 실행 흐름을 사용한다.

## Review Focus

- 추천 새로고침/입력 변경/검색 중 선택한 항목이 사라지거나 이전 추천이 덮어쓰지 않는다.
- 특질 미선택과 모르는 형용사로도 저장할 수 있고 제한된 매칭을 의미 검증으로 오해시키지 않는다.
- 고정 신원/기본 성격, 선택 목록, 출처가 씨앗→기획→설계→최종 프롬프트에서 유지된다.
- 중복/변조 ID, 카탈로그 교체, stale seed revision, 진행 중인 캐릭터 수정은 데이터 변경 없이 실패한다.
- 악성 HTML 문구, 로딩/빈 결과/서버 오류/모바일에서 입력 및 선택 상태를 보존한다.

## Task 1: 저작 카탈로그와 선택 계약

Files: contracts/creator_traits.py; resources/creator-traits-v1.json; stages/s3_plan/trait_recommendations.py; tests/test_trait_recommendations.py.
Interface: load_catalog() -> dict; recommend_traits(personality, *, selected_ids=(), dismissed_ids=(), search="", limit=5) -> dict; resolve_traits(ids, catalog_sha=None) -> list[CreatorTrait].
- [x] 합성 카탈로그로 unknown/duplicate/limit/provenance/empty/selection exclusion RED를 확인한다.
- [x] 실제 원천에서 저작 행동만 내장 투영하고, 추천을 의미 합격으로 표현하지 않는 로컬 순위화를 구현한다.
- [x] targeted GREEN 및 실제 144개 출처 일치를 별도로 검증한다(실제 원문은 test fixture에 넣지 않는다).

## Task 2: 입력/선택 저장과 워크숍 화면

Files: web/trait_authoring.py; web/app.py; web/static/trait-authoring.html; web/static/shared/trait-authoring.js; web/static/shared/trait-authoring.css; web/static/index.html; cli.py; stages/s3_plan/seed.py; contracts/planning.py; tests/test_trait_authoring.py.
API: GET /api/traits/catalog; POST /api/traits/recommend {personality,selectedIds,dismissedIds,search,limit}; GET /api/characters/{id}/seed -> {seed,editable,reason}; POST same {fields,selectedIds,expectedSeedRev,catalogSha256} -> {seed,nextUrl}. catalog/recommend/items use traitId,behavior,category,reason,presetId,sourceField,catalogSha256. GET catalog returns {catalogSha256,totalTraits,totalPresets,items}. No source full paths on UI.
UI: /trait-authoring.html?character=<id>. Select existing character, personality textarea, optional job/age/gender/background/notes, five suggestions, search/browse, independent selected list with remove, save optional selectedIds, show saved revision/next link. UI consumes APIs only. CLI `cfp plan suggest --personality ...`; seed repeat --trait ID.
- [x] API invalid/stale/running/no-selection RED를 확인한다。
- [x] 기존 형식과 새 selectedTraits의 호환 저장 및 화면을 구현한다。
- [x] API GREEN; browser exercises input/select/remove/skip/search/save, keyboard and narrow viewport.

## Task 3: S3/S7/S8 전파

Files: contracts/planning.py; contracts/choice_design.py; stages/s3_plan/variants.py; stages/s3_plan/choice_flow.py; stages/s3_plan/choice_design.py; stages/s7_traits/formation.py; stages/s8_prompts/source.py; stages/s8_prompts/compiler.py; stages/s8_prompts/choice_voice.py; prompts/seed_requirements.md; prompts/choice_variants.md; prompts/persona_choice_formation.md; tests/test_creator_trait_flow.py.
Interface: seed.selectedTraits and plan.selectedTraits: list[CreatorTrait] default empty. Factory binds selected values from seed to every candidate (not model-authored metadata); fixed own-plan revisions retain selected snapshots. v2 requirements include fixed entry per selected behavior. Final DISPOSITION appends selected literal behaviors with situational-use rule in v1/v2 compilers. No changes to original voice assets or shared candidate actions.
- [x] Choice coverage omissions, forged model trait metadata and final compiler loss RED를 확인한다。
- [x] 정의한 전파를 구현하고 v1/v2 호환 GREEN을 확인한다。

## Task 4: 문서·검증·독립 검토

- [x] PRD→spec→LLD와 실행 가이드, 현재 상태/결정/검증/새 handoff/인덱스를 갱신한다.
- [x] scripts/check.sh 전체, 브라우저/패키지/출처 확인 결과를 기록한다.
- [x] 이번 시작점 baseline과의 diff 파일로 새 서브에이전트가 독립 검토한다. 중요한 결함은 재현 테스트 후 수정한다.
- [x] 실제 모델의 생성·대화 품질은 이번에 재실행하지 않았다고 명확히 보고한다.

최종 결과:773 passed/1 skipped, 독립 검토 R1~R4 수정 및 범위 한정 재확인 PASS. 실제 모델 품질은 별도 미검증이다.
