# 현행 서비스 기반 성향 프롬프트 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 사용자가 실제 대화의 섹션을 현행 서비스에 두고, 특질을 정규화된 성격 문장의 저작 재료로 쓰도록 구체화했다. 이번 세션에서 이어서 구현한다.

**Goal:** 현행 서비스 v6의 여덟 persona 섹션을 바탕으로, 제작·검증 메타정보와 반응 규칙표·예시·세 챕터가 없는 대화용 프롬프트를 만든다.

**Architecture:** S3/S7의 출처·상황별 선택·검사 자료는 내부에 유지한다. S8은 별도 actor profile projection과 compiler v3로 사실·생활·기본 성향·원하는 것/두려움·해석/긴장·선택 경향·말투·경계를 산문 문장으로 묶는다. 관계·장면은 하나의 선택적 RuntimeContext이며 인물에 모든 챕터를 넣지 않는다. 구형 컴파일러와 과거 bundle은 그대로 읽는다.

**Tech Stack:** Python/Pydantic/pytest, 기존 첫응답 기록·공유 예산 공급자.

**Spec:** PRD §16 → 명세 §19 → LLD §17. 읽기 전용 비교 근거는 relationship-quest-chat의 활성 ko han-somin-quest-v48 → han-somin-r11(v6), split-frame-r5-v40이다. 운영 DB 발행 상태까지 검증한 것은 아니다.

## Global Constraints

- 기존 미커밋 작업·실험·승인 revision을 보존한다. commit/push는 하지 않는다.
- `activeWhen/activateWhen/firstMove/choiceRuleId`, 제작자 표기·출처 ID/해시, 예시 대사, 세 챕터를 runtime 본문에 넣지 않는다.
- 추가 특질은 기본 성향에 합치고 출처별 별도 제목을 달지 않는다. 기본 성격·신원을 대체하지 않는다.
- 현재 관계·장면은 단일 맥락만 받는다. 컨텍스트가 없으면 챕터에서 임의 추정하지 않는다.
- 8000자 초과는 실패이며 조용히 자르지 않는다. 소유권·합의·취소의 공통 경계는 짧게 유지한다.
- 실제 호출은 --execute·사전 상한 보고·첫응답 보존을 지킨다. 구조 정비와 실제 품질 효과를 구분한다.

## Review Focus

- 과거 재현이 새 compiler/section으로 바뀌지 않는가.
- source hash는 맞지만 실제 기본 성격이 최종에서 빠지지 않는가.
- 추가 특질의 원문·출처를 runtime 메타정보나 고정 반응 공식으로 노출하지 않는가.
- 현재 맥락 대신 전체 챕터나 모순된 관계 상태가 주입되지 않는가.
- 짧아졌다는 수치만으로 인물성·자연스러움 개선을 주장하지 않는가.

## Task 1: 서비스 v6 섹션과 성격 문장의 actor projection

**Files:** 새 contracts/actor_persona.py, 새 stages/s8_prompts/actor_persona.py, tests/test_prompt_identity_preservation.py.

**Interfaces:** RuntimePersona는 facts/lifeAndTastes/disposition/wantsAndFears/readingAndTension/choices/voice/boundaries다. project_actor_persona(plan,sheet,bp)는 승인 원문을 사용하며 disposition에 기본 성격과 선택 행동을 출처 제목 없이 통합한다. choices는 우선순위의 경향을 쓰고 상황별 필수 절차를 직렬화하지 않는다.

- [x] 산문 섹션·기본 성격·추가 성향 통합·메타정보 부재를 확인하는 합성 회귀를 작성하고 RED를 확인한다.
- [x] 최소 projection/본문 검증을 구현하고 GREEN을 확인한다.

## Task 2: 현재 맥락·버전 호환·S8 연결

**Files:** 새 actor compiler, choice_voice.py, formation.py, voice_bundle.py, 새 runtime system rules, 기존 flow/creator trait 회귀.

**Interfaces:** compose_actor_runtime(plan,sheet,bp,*,rules_text,runtime_context=None,long_max=8000)는 서비스의 여덟 persona 섹션과 공통 대화 규칙을 출력한다. 기존 compose_choice_voice_text는 과거 재현용으로 유지한다. bundle compilerVersion과 examplesUsage는 예시가 검토용임을 구분한다.

- [x] 예시·세 챕터·규칙표 부재, 단일 RuntimeContext, 길이 초과 거절, 구형 재현과 새 bundle 본문 검증의 회귀를 작성한다.
- [x] RED→GREEN으로 구현하고 기존 형성/G6/creator trait/development 경로를 확인한다.

## Task 3: 내용 뼈대·말투 저작 지시 보완

- [x] 내부 조건·검사 구조는 저작/검증 자산임을 명시한다. 말투 작성의 act는 실제로 말할 최소 의도이며 모든 판단·조건을 발화로 설명하지 않는다.
- [x] 전체 검사와 마지막 독립 코드 검토를 수행하고 중요한 지적을 재현 검사로 수정한다.

## Task 4: 실제 Gemini 관찰

- [x] 기존 runtime A와 새 runtime B를 같은 입력/모델로 비교한다. 구조 전체가 바뀌므로 개별 성분의 인과 효과라고 주장하지 않는다. 친밀한 잡담·자존심 장면도 포함한다.
- [x] 별도 fresh session에서 누적 대화와 소유권·약속 변경을 확인한다. 원문/usage/잘림/이력을 보존한다.
- [x] 사람이 읽을 입력→정규화된 persona→최종 prompt→실제 응답 자료를 남긴다. 사람 블라인드/다인물/정식 검증이 없으면 품질 보장으로 올리지 않는다.

## 범위 정정

초기 누락 복원·예시 선정 개선안에서, 사용자의 추가 지시로 runtime 구조를 현행 서비스 기반으로 교체한다. 예시 선정 개선은 runtime 주입을 전제로 하지 않으므로 이번 구현에서 제외한다. 기존 예시는 내부 저작·검토 자료로만 남는다. 첫 계획의 회귀 RED 6건은 work의 red.log에 보존한다.
