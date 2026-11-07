# 특질·선택 설계와 실제 말투 예시를 결합하는 페르소나 개선 계획

> **For agentic workers:** 구현 시 superpowers:executing-plans 또는 superpowers:subagent-driven-development를 적용한다. 이번 요청의 산출물은 계획과 서브에이전트 검토다. 제품 구현·외부 모델 실험·학습·커밋은 이번에 실행하지 않는다.

**Goal:** 특질에서 일관된 선택을 도출하고, 선택과 사실을 보존한 내용 뼈대에 승인된 말투 예시를 적용해 새 캐릭터의 첫 완성품 품질을 높인다.

**Architecture:** S3의 씨앗→특질→선택 근거를 강화하고, S7을 행동 설계→내용 뼈대→말투 렌더링으로 분리한다. 실제 말투 자료는 재사용 가능한 버전 자산으로 관리하고, S8은 행동·말투의 핵심 사례를 함께 담는다. 생성 완료와 공정의 품질 합격은 계속 구분한다.

**Tech Stack:** 기존 Python 3.12, Pydantic, pytest, cfp, 공급자·예산·revision 체계를 사용한다. 새 서비스나 UI는 만들지 않는다.

**Spec:** 현행 [PRD FR-21·23·48·49](prd.md), [명세 §16](../architecture/spec.md), [LLD §14](../architecture/lld.md)를 확장하는 구현 제안이다. 세부 계약·수량·통과 기준은 아래 제안이며 Task 0에서 PRD→spec→LLD에 반영한다. 사용자가 정한 방향은 특질·선택 개선과 실제 말투 예시 적용이다.

## 1. 현재 근거와 목표

- [원인 분석](../reports/2026-10-29-persona-choice-cause-analysis.md)에서 지각 대응은 12후보의 번호별 틀이 같았고 개발 시험은 모두 v1을 골랐다. 반면 관계 확답의 선택은 캐릭터별로 달랐고 관련 13규칙은 S8까지 전달됐다. 전반적인 개성 소실이나 대화 모델의 한계는 입증되지 않았다.
- 현재 `check_v2.py`는 씨앗의 직업·나이·성별과 첫 행동 문자열 차이를 검사한다. 성격의 의미적 충실도와 같은 행동의 재서술은 검사하지 못한다.
- S7b는 정본·특질·blueprint에서 12개 대화를 직접 쓴다. 턴별 내용 뼈대와 실제 말투 기준을 분리한 단계가 없다.
- S8은 네 슬롯에서 첫 ID를 선택한다. 핵심 선택이 드러나는 예시의 포함은 보장되지 않는다.
- 기존 SFT 제작 문서와 charforge 렌더러에는 `act/facts/tone`과 승인된 말투 예시·규칙을 분리하는 방식이 있다. 이는 재사용할 제작 근거이며, 그 방식 하나가 한소민 학습 성과의 원인이었다는 인과 증거는 아니다.

성공의 기준은 모든 상황에서 캐릭터들이 다른 답을 내는 것이 아니다. 공통 기본기는 지키면서, 우선순위가 충돌하는 상황에서 설계한 선택과 전환 조건이 드러나고 일상 대화도 자연스러워야 한다.

제작 근거는 [기존 내용/말투 분리 문서](</Users/johnhuh619/Documents/Codex/2026-10-14/gem/somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:7>), [선택·말투 팩 작성 가이드](</Users/johnhuh619/Documents/Codex/2026-10-14/gem/charforge/docs/캐릭터-팩-작성-가이드.md:136>), [기존 렌더러](</Users/johnhuh619/Documents/Codex/2026-10-14/gem/charforge/charforge/gen/render.py:71>)다. 이 파일들은 읽기만 했다.

## 2. Global Constraints

- 지원 범위는 현대 한국 배경의 성인 캐릭터·한국어 문자·long 프롬프트다. SFT 및 short 품질은 이 계획의 완료 조건에 넣지 않는다.
- 새 opt-in 프로필 이름은 `ko-text-choice-voice-long-v2`로 제안한다. 기존 `ko-text-prompt-long-v1`과 legacy 파일·승인·소비 경로를 보존한다.
- 정본 불변 사실과 실제 이력의 최신 상태를 지킨다. 예시의 사용자 사실·공동 사건은 `example-local`이며 실제 기억으로 승격하지 않는다.
- 공정에 새 사람 관문을 추가하지 않는다. 기존 G3·G6에서 근거와 결과를 검토한다. 승인된 공통 말투 자산을 재사용해 캐릭터마다 20줄을 새로 수작업하는 일을 기본 경로로 만들지 않는다.
- 원본 대사, 생성한 대사, 사람이 승인한 대사를 구분한다. 모델이 쓴 `approved=true`나 출처 라벨은 승인 증거가 아니다.
- 형식 재시도는 하위 호출당 최대 2회로 제안한다. 의미 실패는 `CHECK_FAILED`로 보존하며 좋은 결과가 나올 때까지 재생성하지 않는다. 수정은 새 revision·새 recipe로 남긴다.
- 선택 의미 검토와 렌더링 보존 검토는 생성 모델과 다른 계열의 검토 모델을 사용하고 실제 모델·설정·원문을 기록한다. 검토 결과를 이유로 생성 대사를 자동 교정하지 않는다.
- 실제 대화는 고정 system + 누적 실제 messages + 현재 user → 첫 assistant 하나를 따른다. 내용 뼈대/렌더러는 페르소나 제작 단계에만 넣는다.
- long은 현재 8,000자 상한을 유지한다. 필수 내용을 담을 수 없으면 명시적으로 실패한다. exact tokenizer 연결이 없는 정식 품질 시험은 계속 막는다(K-0047).
- 다른 저장소는 읽기만 하며 자료는 검증된 입력 자산으로 가져온다. 원문 SNS·실제 대사와 개인 사실을 Git fixture나 허구 정본에 넣지 않는다. 커밋은 사용자 요청 전 실행하지 않는다.

## 3. 특질에서 선택까지의 설계

### 3.1 씨앗의 요구를 먼저 분리한다

후보 생성 전에 씨앗 전체(personality/background/notes와 고정 필드)의 요구 목록을 `seed-requirements-v1`로 동결한다. 각 요구를 `명시한 고정 조건`, `창작 가능한 부분`, `정보 부족`으로 나누고 안정적인 requirementId·원문 위치·인용을 남긴다. 후보마다 모든 요구에 `반영됨·창작 재량·미해결`과 구현 근거를 대응시켜, trait→seed뿐 아니라 seed의 필수 요구→후보도 역방향으로 검사한다. 의미 검토자는 원문 전체와 요구 목록의 누락 여부도 확인한다. ‘조용하지만 부당한 부탁은 바로 거절한다’에서 조용함만 반영하면 누락 실패다. ‘내향적’이라는 한 단어로 모든 상황에서 기다리거나 거절하도록 만들지 않는다.

각 특질은 다음 정보를 가진다. 아래 이름은 새 `choice-design-v1` sidecar의 제안 필드다.

| 필드 | 의미 |
|---|---|
| traitId / seedClaims | 어떤 씨앗 요구를 구체화한 특질인지 연결한다. 창작 보완은 별도 표시한다. |
| attention / priority | 먼저 보는 신호와 충돌할 때 지키는 가치를 적는다. |
| firstMove / acceptedCost | 실제 첫 행동과 그 때문에 감수하는 손해를 적는다. |
| activateWhen / doNotActivateWhen | 적용할 조건과 평범하게 반응할 조건을 나눈다. |
| switchWhen / alternative | 새 정보가 들어오면 바뀌는 조건과 허용할 다른 행동을 적는다. |
| wrongTransformation | 말투만 바꾸거나 성격을 과장했을 때 생기는 잘못된 행동을 적는다. |

행동은 literal 대사가 아닌 의미로 쓴다. ‘책을 읽으며 기다린다’와 ‘책을 펴서 도착을 기다린다’는 같은 행동으로 판정한다. 행동 라벨만 다르게 선언해도 통과하지 못하게 원문·우선순위·비용을 함께 검토한다.

### 3.2 후보 번호에서 성격을 떼어 낸다

- `plan_variants.md`에서 기다림→조정→재약속 같은 순서 있는 행동 예시를 제거하고, `_example()`의 고정 성격·고정 상황을 비내용적 형식으로 바꾼다. 형식에는 타입/스키마를 우선 제공한다.
- 같은 씨앗의 후보는 고정 조건을 모두 지키면서 해석 가능한 선택 축에서 달라지게 한다. 모든 상황의 첫 행동을 강제로 다르게 하는 현재 조건은 완화한다. 상황 분류는 `shared|contrast|not_applicable`, 해당 requirementIds, 이유를 갖는다. 검토자는 분류 자체의 정당성도 검사하고 우선순위 충돌을 shared로 면제하지 않는다. ‘그냥 들어줘’에 모두 경청하는 사례는 정상 공유 반응으로 인정한다.
- G3는 기존 사람 선택을 유지한다. 새 프로필에서 복수 후보는 명시적 `SELECT`를 요구하며 대상 없는 `APPROVE`는 첫 후보를 선택하지 않고 거절한다. 구형 프로필의 승인 동작은 보존한다. 실험 자동 선택은 결과를 보기 전에 씨앗 충실도→모순 없음→실제 행동 대비 순의 규칙을 고정하고, 동률이면 번호/배열 순서를 제외한 canonical 내용 해시로 결정한다. 배열·variantId를 바꿔도 같은 내용을 선택해야 한다. 결과를 본 뒤의 다양성 극대화로 고르지 않는다.
- 구조 검사와 별도로 의미 검토 보고서에 후보별 필수 요구의 누락/모순, shared 분류 타당성, 실제 대비, `PASS|FAIL|UNRESOLVED`, 원문 인용과 반례를 남긴다. 보고서 누락·필수 판정 누락·FAIL·UNRESOLVED·입력 해시 불일치는 G3 승인과 S7 입구에서 차단한다. 의미 판정은 형식 재시도/일반 check 재시도 루프 밖에 두며 API·Codex 양쪽에서 의미 실패 후 생성 호출이 늘지 않게 한다. 모델 판정은 결함 탐지 근거이며 실제 품질 합격은 아니다.

### 3.3 S3·S7 책임을 구분한다

S3에서 특질·우선순위·대표 선택을 정하고 G3에서 승인한다. S7은 승인 선택을 다른 상황에 적용하되 수정하거나 새 정본으로 덮어쓰지 않는다. 기획→blueprint 충실도와 blueprint→대사 구현도를 따로 검사한다. 원천 기획이 잘못됐을 때 S7가 말투로 감추지 않는다.

`CharacterPlanV2`를 바로 전면 교체하지 않고 생성용 `plan-variants-output-v2`, 저장용 `plan-variants-v2`, 승인용 `plan-selection-v2`를 함께 도입한다. 각 후보에 `choice-design-v1` sidecar를 연결한다. 승인 기록은 seed/requirements/선택 기획/sidecar/의미 보고서의 파일 해시와 선택한 variant를 묶고 G3 shownArtifacts에도 이 묶음을 남긴다. `load_approved_choice_design(ctx, cid)`는 파일 무결성과 파일들 사이의 characterId/planRev/선택 후보/원천 해시 관계를 검증한다. 각각 유효한 다른 후보 파일을 섞어도 실패해야 한다.

새 `ChoiceArtifactRef`에는 seed/requirements/choice/review 출처 종류를 두고, 기존 SourceRef의 v1 허용값을 소급 변경하지 않는다. 승인 선택은 안정적인 `choiceRuleId`를 갖고 S7의 blueprint-v2·beats·커버리지까지 추적한다. v1 DecisionRule에 ID가 없다는 사실을 생성 모델의 임의 문자열로 보완하지 않는다.

G3 편집은 `편집 원문 저장 → 새 pr 생성·사용자 변경 고정 → 요구 목록/sidecar 재설계·재검토 → 기존 G3 재승인`으로 처리한다. 그동안 S3는 완료가 아니며 S7 진입을 차단한다. 사용자가 수정한 요구는 이전 seed 요구를 대체한 기록과 함께 적용하고, 대체하지 않은 고정 조건은 유지한다. 이 흐름은 G3의 새 프로필 전용 편집 경로이며 현재 G3가 일반 재작업 대상에서 빠져 있다는 점을 구현에 반영한다. 구형 승인 기획은 기존 프로필로 읽고 v2 품질을 소급하지 않는다.

## 4. 실제 말투 자산과 내용 뼈대

### 4.1 재사용 가능한 VoicePack

`voice-pack-v1`은 승인된 실제/사람 교정 예시, 관계·감정·채널 조건, 길이·말풍선·어미·감정 표지의 관찰값, 사용/비사용 조건을 가진다. 예시별 원본 해시·위치·화자·작성/교정 주체·승인 기록·사용 범위를 남긴다. 출처 파일 접근권과 승인 상태를 로더가 확인한다.

팩 준비 시 원본의 화자 사실·사건·숫자와 행동 선택을 분리한 `styleView`를 만들고 변환 계보를 원본과 연결한다. 렌더러에는 필요한 표현 예시와 상황 조건만 주고 원본의 전기·전체 대화·다른 캐릭터의 정본을 주지 않는다. 이 공통 전처리를 팩마다 한 번 수행해 캐릭터별 원문 정리 작업을 줄인다. 변환본을 새로운 실제 원문으로 표시하지 않는다.

- 초기 팩은 기존 소민·세라·연우 자료에서 재사용 가능한 부분의 실제 승인·출처를 확인해 구성한다. 파일에 `by=data`라고 쓰여 있다는 이유만으로 승인했다고 간주하지 않는다.
- 20개 예시와 관계/감정/길이 분포는 초기 제안이다. 짧은 받아침·일상·호감·갈등·사과·진지함을 포함하고, 사용하지 않을 조건도 넣는다. 숫자 빈도는 승인 자료에서 측정하며 캐릭터마다 같은 비율을 강제하지 않는다.
- 캐릭터의 명시된 말투 조건과 맞는 팩을 고르고 `voice-binding-v1`에 이유·버전·해시를 고정한다. 행동 성격과 말투를 독립적으로 다루며 귀여운 말투를 쓴다는 이유로 수용적인 성격을 부여하지 않는다.
- 승인된 팩이 맞지 않으면 `VOICE_SOURCE_MISSING`을 기록한다. 모델 초안은 `DRAFT`로 만들 수 있으나 실제 말투 주입 경로의 완료나 품질 합격으로 표시하지 않는다. 다음 팩 승인·수정은 기존 검토 흐름을 사용한다.
- SNS 참조는 자연스러운 반응 순서와 호흡을 위한 보조 입력이다. 원본 화자의 직업·약속·공동 기억이나 다른 캐릭터의 정체성을 옮기지 않는다. 새 캐릭터별 실제 말투 검증 자료는 주입 예시와 분리한다.

### 4.2 S7의 생성 단계를 나눈다

`S7a 행동 설계 → S7b 12개 내용 뼈대 → S7c 말투 렌더링 → 보존 검사 → S8`로 제안한다.

내용 뼈대는 대사가 없는 `formation-beats-v1`이며 각 턴에 `turnId, role, act, facts, tone, decisionRuleIds, stateBefore, stateAfter`를 둔다. 사실에는 `owner, scope, sourceRef`를 붙인다. 사용자 반응의 의미와 순서는 고정하지만 구체 대사 표현은 렌더러가 작성한다. 실제 대화의 분기와 합의 상태를 계획된 결말에 억지로 맞추지 않는다.

말투 렌더러는 정본·행동 선택·내용 뼈대·바인딩된 말투 팩만 받는다. 내용에 대한 권한은 승인된 선택과 뼈대에 있으며, 말투 예시는 표현의 기준이다. 예시 속 수락·거절·인간관계·직업을 새 캐릭터의 행동/사실로 가져오지 않는다. 평가 문제와 다른 캐릭터의 정본은 보지 않는다. 모든 예시를 보존하며 임의의 좋은 결과 선별·문장 교정을 하지 않는다.

보존 검사는 turnId/role/턴 수·숫자·정본/예시 소유자·출처를 구조적으로 확인하고, 수락↔거절·합의↔제안·감정/관계 변화·선택의 이유는 의미 검토로 확인한다. 숫자가 같다는 사실만으로 의미 보존을 판정하지 않는다. 생성 대사가 실제로 선택을 구현했는지 원문 인용으로 보고한다. 불명확·불일치는 실패이며 원문은 보존한다.

검토는 생성 대사 전체에서 사실·행동 주장을 찾아 뼈대의 허용 주장과 양방향으로 대조한다. `factRefs`가 없거나 새 사실을 example-local이라고 선언한 경우도 면제하지 않는다. 뼈대에 없는 ‘합주를 마쳤다’ 같은 원본 사실의 추가, 필수 사실/행동의 삭제, 소유자 바꾸기는 모두 실패다. 자연스러운 감탄·머뭇거림은 허용하되 새로운 사건·약속·취향의 추가는 허용 주장에 있어야 한다.

### 4.3 S8과 승인·재개의 연결

현재 12개 생성 수와 최소 4개 삽입 수는 우선 유지한다. 새 선택기는 일상·감정/관계 변화·핵심 선택·조건 변경을 포함하는 후보 조합을 찾고, 결정 규칙·말투 조건 커버리지를 만족하는 조합 중 ID 순으로 하나를 고른다. 결과 점수로 가장 좋은 예시를 고르지 않는다. 네 개로 필수 커버리지를 충족하지 못하면 `COVERAGE_GAP`을 내고 recipe를 고친다.

새 bundle은 기획/choice sidecar/trait/blueprint/beats/rendered dialogues/voice pack/voice binding/보존 보고서/선정 정책/시스템 규칙/소비 프로필의 파일 해시를 묶는다. G6 승인 뒤 S9·패키지·실제 소비는 그 bundle을 읽는다. 말투 팩이나 기획을 바꾸면 새 S7/S8 revision이 필요하다. 중단 재개에서 완료된 호출을 반복하지 않으며 다른 팩 해시의 결과를 재사용하지 않는다.

단계별 `stageFingerprint`는 입력 해시뿐 아니라 생성/검토 모델과 설정·역할 프롬프트·계약·검사 구현·팩 전처리 버전을 포함한다. 변경된 단계와 그 하위 결과를 무효화하고, 대기 중 G6는 새 bundle로 다시 연다. 승인된 과거 bundle은 고치지 않는다. 생성물이 같아도 보존 검사 버전이 바뀌면 이전 PASS를 재사용하지 않는다.

v2의 최종 말투 섹션은 바인딩된 팩의 표현 기준과 검증된 렌더링 예시에서 조립한다. S3 `voiceSummary`는 목표 조건으로 보존하고 일치 여부를 확인하며, S3의 생성 `voiceExamples`는 기획 초안 출처로 남긴다. 초안 예시가 승인된 팩과 충돌할 때 기존 직접 투영 경로로 최종 기준을 덮어쓰지 않는다. 신원·생활·챕터의 정본 보존은 유지한다.

## 5. 검증 설계와 통과 의미

### 5.1 작은 개발 대조부터 한다

기존 개발 4캐릭터를 사용하고 새 보류 세트는 손대지 않는다. 같은 소비 모델·동일 관계/사전 사실·같은 예산·동일 입력으로 아래 조건을 비교한다. 이는 원인 진단이며 정식 품질 합격이 아니다.

| 조건 | 바꾸는 요소 | 고정하는 요소 |
|---|---|---|
| A | 현재 공정을 기준선으로 보존한다. | 기존 기획·blueprint·프롬프트 원문을 동결한다. |
| B | 특질·선택 설계를 개선한다. | 직접 대화 생성과 기존 S8 선정 정책을 유지한다. |
| C | B의 대화를 내용 뼈대→렌더링으로 분리한다. | B의 선택·생성형 말투 기준을 그대로 사용한다. |
| D | C의 렌더러에 승인된 실제 말투 팩을 적용한다. | C와 동일한 선택·내용 뼈대·S8 선정 정책을 사용한다. |

S8 커버리지 선택기 효과는 D의 동일한 12예시로 현행/개선 선택기를 별도 비교한다. B~D의 선택·blueprint는 한 번 만든 결과를 공유하고, C/D는 같은 뼈대 해시를 사용한다. 재생성한 다른 설계를 ‘말투만 바꾼 비교’로 부르지 않는다.

첫 관찰은 캐릭터×조건마다 같은 선택 장면 1개와 일상/감정 장면 1개, 각 6응답으로 제안한다(4×4×12=192응답). 선택 장면은 호출 전에 기획에서 기대 행동·허용 대안·반대 행동을 고정한다. 이미 다른 선택이 정의된 관계 확답을 포함한다. 장면 중 실제로 합의하지 않은 일을 이후 사용자 턴이 합의했다고 전제하지 않도록 분기표를 사용한다.

C/D의 작은 대조에서는 수락 여부와 관계없이 성립하는 공통 후속 질문을 우선 사용해 실제 사용자 입력을 같게 유지한다. 분기가 필요한 연속 대화에서는 `좋아` 같은 부분 문자열로 합의를 판정하지 않는다. 상태 판정은 `ACCEPT|REFUSE|CONDITIONAL|UNKNOWN`과 원문 근거를 가지며 부정·조건부·복수 조건 처리 및 UNKNOWN일 때의 중립 확인/실패 규칙을 동결한다. 상태 해석 호출이 필요하면 예산에 합산한다. ‘좋아하는 건 맞지만 내일 약속은 못 잡아’를 수락으로 분기하는 합성 반례를 고정한다.

별도의 S3 진단에서는 같은 씨앗과 설정으로 현행/행동 예시 제거/예시 순서 교환을 비교한다. 후보 번호의 행동 분포와 씨앗 충실도를 측정하며, 새 설계 전체의 성과와 예시 순서의 인과 효과를 섞지 않는다.

### 5.2 품질을 세 축으로 따로 본다

| 축 | 확인할 것 | 실패 예 |
|---|---|---|
| 선택 | 씨앗→승인 설계→뼈대→대사의 우선순위·비용·전환 조건을 확인한다. | 다정한 말투를 입히며 거절이 수락으로 바뀐다. |
| 말투·자연스러움 | 주입하지 않은 참조 예시와 비교하고 사람 블라인드 판단으로 실제 대화 가능 여부를 확인한다. | 어미만 반복하거나 심각한 장면에서도 장난을 유지한다. |
| 대화 유지 | 실제 누적 이력에서 소유자·상태 변경·조건 비적용과 자연스러운 이어받기를 확인한다. | 예시 약속을 실제 기억으로 말하거나 매 턴 같은 경계를 반복한다. |

원본 팩 예시를 맞히는 평가만으로 말투 전이를 주장하지 않는다. 새 주제·새 상대 반응·팩에 없는 상황에서 확인한다. 승인 예시/형성 장면/개발 시험/보류 시험은 출처와 의미 중복을 추적한다. 사람은 조건 이름을 가리고 판정하며 LLM 결함 분류는 그 뒤에 보조 자료로 본다.

분리 manifest는 문장 ID/해시 외에 `sourceGroupId, parentSourceIds, originalConversationId, derivedFrom, sceneFamilyId`와 용도별 분할을 기록한다. 같은 원본 대화의 다른 발췌나 재작성본은 같은 그룹이다. 실행/보고 시 manifest의 실제 파일 해시와 주입 입력을 대조하고 중복·감사 미해결이면 합격을 막는다. 공통 승인 팩을 여러 캐릭터가 사용하는 것은 허용하지만 그 팩의 주입 대사를 비주입 검증 예시로 다시 쓰지 않는다. 캐릭터 보류와 말투 원본/주제 전이 검증의 독립성 범위를 별도로 공개한다.

블라인드 평가 자료는 공정명·모델명·원본 캐릭터 이름을 가리고 승인 정본, blueprint, 선택의 허용 대안/반대 행동, 팩의 비주입 참조와 해당 provenance를 제공한다. 자연스러움과 목표 말투 적합성을 별도로 판정한다. 평가자에게 필요한 기준을 숨긴 채 voiceOK·blueprintFaithful을 요구하지 않는다. 참조는 공통 팩에서 준비해 캐릭터마다 새 대사를 수작업하지 않는다.

개발 대조에서 ① 의미상 선택·사실 보존 위반 0건, ② 씨앗 충실도·선택 구현이 A보다 악화되지 않음, ③ D의 자연스러움/말투가 C보다 개선되고 각 캐릭터에서 사용할 수 있음이 확인될 때 통합 후보로 삼는 안을 제안한다. 숫자와 판단 예시는 개발 시작 전에 동결한다. 평균 향상만으로 약한 캐릭터를 덮지 않는다.

통합 뒤에는 기존 기본 품질 계획의 연속 24턴을 포함한 60응답·보류 8캐릭터×2회 규약을 새 recipe에 적용한다. exact tokenizer, 독립 보류, 사람 검토가 없으면 QUALIFIED를 기록하지 않는다. 지원 범위와 관측 통과 수를 제시하고 모든 새 캐릭터의 품질을 보편적으로 보장한다고 말하지 않는다.

## 6. 구현 작업과 인터페이스

아래 파일과 인터페이스는 제안이며 구현 전 현행 호출부와 함께 개정한다. `contracts/`, `stages/`, `prompts/`, `checks/`, `providers/`, `pipeline/`, `common/`, `resources/`는 모두 `src/character_factory_poc/`를 기준으로 한 경로다. `tests/`, `docs/`, `factory.example.toml`은 저장소 루트를 기준으로 한다. 각 작업은 실패를 재현하는 합성 fixture·가짜 공급자 테스트→최소 구현→지정 검증 순서로 진행한다. 실제 대사를 테스트에 넣지 않는다.

### Task 0. 문서·프로필·측정 규약을 고정한다

**Files:** `docs/product/prd.md`, `docs/architecture/spec.md`, `docs/architecture/lld.md`, `docs/guides/persona-quality-runbook.md`, `factory.example.toml`, 새 `resources/persona-quality-profile-choice-voice-v2.json`을 수정/작성한다.

**Interfaces:** 현행 profile loader를 사용해 새 프로필을 읽고 이전 profileId를 유지한다. §5의 비교 조건·출처 분리·실패 분모·모델/프롬프트/선정 정책 해시를 protocol에 저장한다.

- [ ] `test_choice_voice_profile_is_opt_in`에서 기본 설정은 기존 경로이고 새 프로필은 명시 설정으로만 선택되는지 확인한다.
- [ ] PRD→spec→LLD에 §2~5의 범위와 계약·세부 기본값을 반영하고 설정을 추가한다. 프로필 수치가 미동결일 때 합격할 수 없게 한다.
- [ ] `uv run pytest tests/test_formation_contracts.py tests/test_persona_qualification.py -q`를 실행한다. 기존 프로필 회귀와 새 프로필 구분이 통과해야 한다.

### Task 1. 선택 근거 계약과 S3 의미 검토를 만든다

**Files:** 새 `contracts/choice_design.py`, `stages/s3_plan/choice_design.py`, `prompts/seed_requirements.md`, `prompts/choice_review.md`, `tests/test_plan_choice_design.py`; 기존 `contracts/planning.py`, `stages/s3_plan/{variants,check_v2,approve,importer,page}.py`, `prompts/plan_variants.md`, `checks/registry.py`, `providers/{fake,fake_codex}.py`, `pipeline/agent.py`, `pipeline/rework.py`, `tests/test_plan_variants.py`를 수정한다. page는 기존 G3에 근거를 전달하는 범위로 바꾸고 새 화면은 만들지 않는다.

**Interfaces:** `SeedRequirements`, `ChoiceDesign`, `ChoiceArtifactRef`, `ChoiceReview`를 등록한다. `build_seed_requirements(ctx, cid, seed, *, budget) -> SeedRequirements`, `review_choice_design(seed, requirements, plans, designs, *, reviewer) -> ChoiceReview`, `check_choice_design(seed, plan, design) -> list[str]`, `load_approved_choice_design(ctx, cid) -> ChoiceDesign`, `prepare_g3_choice_edit(ctx, cid, answer) -> Path`를 정의한다. 생성/저장/선택 v2 계약을 모두 연결하며 문자열/행동 라벨 검사는 의미 검토를 대체하지 않는다.

- [ ] `test_same_action_paraphrases_do_not_establish_contrast`, `test_shared_action_is_allowed_with_reason`, `test_shared_cannot_hide_seed_conflict`, `test_seed_required_clause_cannot_be_omitted`, `test_g3_rejects_review_missing_failed_or_unresolved`, `test_mixed_candidate_sidecar_cannot_load`, `test_g3_edit_reopens_new_revision_before_s7`, `test_semantic_failure_has_no_api_or_codex_redraw`, `test_v2_approve_requires_explicit_selection`, `test_selection_is_invariant_to_candidate_order_and_id`를 작성한다.
- [ ] 고정 행동 예시를 제거하고 선택 근거를 생성·검토·저장한다. 의미 실패의 자동 재생성을 막고 G3에서 기존 선택과 근거를 함께 읽게 한다.
- [ ] `uv run pytest tests/test_plan_variants.py tests/test_plan_choice_design.py -q`를 실행한다. 합성 반례가 실패하고 정상 공유 반응·구형 기획이 통과해야 한다.

### Task 2. 승인된 말투 자산과 바인딩을 만든다

**Files:** 새 `contracts/voice.py`, `stages/s7_traits/voice.py`, `tests/test_voice_assets.py`, `docs/guides/voice-assets.md`; `contracts/__init__.py`를 수정한다. 실제 팩 원문은 Git 밖 입력 자산에 둔다.

**Interfaces:** `VoicePack`, `VoiceBinding`, `load_voice_pack(path: Path) -> VoicePack`, `bind_voice(plan, packs: list[VoicePack], policy) -> VoiceBinding`을 정의한다. 바인딩은 자료 해시·검증된 승인 참조·선정 근거·`READY|DRAFT|VOICE_SOURCE_MISSING`을 반환한다.

- [ ] `test_generated_examples_cannot_self_approve`, `test_missing_source_or_approval_is_not_ready`, `test_voice_binding_does_not_import_source_facts`, `test_voice_pack_hash_change_invalidates_binding`을 작성한다.
- [ ] 자산 로더·출처/승인 확인·결정적 바인딩을 구현하고, 기존 팩 재사용 여부는 실제 승인 증거로 감사한다. 모델 초안은 실제 원본으로 둔갑시키지 않는다.
- [ ] `uv run pytest tests/test_voice_assets.py -q`를 실행한다. 미확인 입력은 READY가 되지 않아야 한다.

### Task 3. 내용 뼈대와 선택을 연결한다

**Files:** 새 `contracts/dialogue_beats.py`, `stages/s7_traits/beats.py`, `prompts/persona_choice_formation.md`, `prompts/persona_beats.md`, `tests/test_persona_beats.py`; `contracts/formation.py`, `stages/s7_traits/formation.py`를 수정한다. 새 역할 프롬프트로 기존 프로필의 설계 지시를 보존한다.

**Interfaces:** `contracts/formation.py`에 `DecisionRuleV2(choiceRuleId, ...)`, `PersonaBlueprintV2`, `FormationDesignV2`를 추가한다. blueprint-v2의 `approvedChoiceRef: ChoiceArtifactRef`는 기존 sourceRefs와 구분하며 v1 구조를 고치지 않는다. `FormationBeats`와 `build_formation_beats(ctx: Context, cid: str, design: FormationDesignV2, *, budget) -> FormationBeats`를 정의한다. 선택 sidecar와 정본을 입력받아 12개 장면의 turnId·act/facts/tone·선택 규칙·상태 전이를 저장한다. S7a 설계는 승인 S3 선택을 보존한다.

- [ ] `test_beats_preserve_approved_choice`, `test_local_facts_keep_owner_and_scope`, `test_untriggered_rule_does_not_force_boundary`, `test_resume_reuses_beats_with_same_hash`를 작성한다.
- [ ] 내용 뼈대 생성과 검사를 구현하고 호출 전 입력/출력 계약·원문·실패를 저장한다. 파일 해시를 모델이 계산하도록 시키지 않는다.
- [ ] `uv run pytest tests/test_persona_beats.py tests/test_persona_formation.py -q`를 실행한다.

### Task 4. 말투 렌더링과 의미 보존 검사를 만든다

**Files:** 새 `contracts/rendered_dialogues.py`, `stages/s7_traits/voice_render.py`, `prompts/persona_voice_render.md`, `prompts/persona_voice_preservation.md`, `tests/test_persona_voice_render.py`; `stages/s7_traits/dialogues.py`와 `contracts/__init__.py`를 버전 인식으로 수정한다. `RenderedDialogues`와 `PreservationReport`는 새 계약 파일에 정의한다.

**Interfaces:** `render_formation_dialogues(ctx, cid, beats: FormationBeats, voice: VoiceBinding, *, budget) -> RenderedDialogues`와 `check_render_preservation(beats, dialogues, *, reviewer) -> PreservationReport`를 정의한다. 생성 결과는 turnId에 연결하고 보존 판정 원문 인용·구조 검사·상태를 별도 저장한다.

- [ ] `test_polite_refusal_cannot_become_acceptance`, `test_same_numbers_do_not_prove_same_owner`, `test_voice_source_fact_cannot_be_added_even_as_example_local`, `test_undeclared_or_deleted_claim_is_rejected`, `test_serious_scene_uses_contextual_voice`, `test_semantic_failure_is_not_redrawn`을 작성한다.
- [ ] 승인 팩과 뼈대를 실제 입력으로 주고 관계·감정별 표현을 생성한다. 검사는 선택·합의 상태·소유자 의미를 확인하며 실패/불명확을 성공으로 넘기지 않는다.
- [ ] `uv run pytest tests/test_persona_voice_render.py tests/test_persona_formation_flow.py -q`를 실행한다.

### Task 5. 커버리지 컴파일과 승인·재개를 연결한다

**Files:** 새 `contracts/voice_bundle.py`에 `PersonaBundleV2`와 `CoveragePolicy`를 정의한다. `contracts/formation.py`, `contracts/persona.py`, `stages/s8_prompts/{compiler,formation,approve}.py`, `stages/s7_traits/{sheet,formation}.py`, `pipeline/review.py`, `common/budget.py`, `stages/s9_data/plan.py`, `stages/s11_release/package.py`, `web/gate_items.py`, 새 `tests/test_choice_voice_bundle.py`와 기존 compiler/pipeline 테스트를 수정한다.

**Interfaces:** `select_covered_examples(dialogues: RenderedDialogues, policy: CoveragePolicy) -> list[str]`와 `verify_bundle_v2(bundle: PersonaBundleV2, roots: Mapping[str, Path]) -> None`을 정의한다. 검증은 논리 자산명→파일 경로인 roots에서 실제 파일 해시를 확인한다. `persona-bundle-v2`는 §4.3의 모든 입력/선정 정책 해시와 보존 성공을 요구한다. 구형 bundle은 기존 검증기로 보낸다. 완료된 하위 단계는 정확한 입력 해시가 같을 때만 재사용한다.

- [ ] `test_core_choice_is_in_selected_examples`, `test_coverage_gap_fails_without_truncation`, `test_g6_pins_voice_and_beats_hashes`, `test_voice_change_cannot_resume_old_render`, `test_renderer_or_judge_change_invalidates_downstream`, `test_plan_voice_drafts_cannot_override_bound_pack`, `test_v1_approval_and_consumer_still_work`를 작성한다.
- [ ] 새 프로필의 S7 하위 단계·S8·G6·S9/패키지를 연결하고 dry run의 실제 호출 상한을 갱신한다. 의미 실패를 회복 성공과 섞지 않는다.
- [ ] `uv run pytest tests/test_persona_compiler.py tests/test_choice_voice_bundle.py tests/test_persona_pipeline.py tests/test_persona_formation_flow.py -q`와 `bash scripts/check.sh`를 실행한다.

### Task 6. 대조·블라인드 평가 실행 도구를 확장한다

**Files:** `stages/persona_quality/{protocol,run,packet,report}.py`, `common/{budget,ledger}.py`, `pipeline/context.py`, `tests/test_persona_qualification.py`, 새 `tests/test_choice_voice_protocol.py`, `tests/test_shared_run_budget.py`를 수정/작성한다. 합성 테스트만 실행하고 실제 실행 파일은 runs/에 둔다.

**Interfaces:** `DevelopmentCohortV2`는 A~D 및 S8 대조, 2장면×6응답을 지원하고 정식 QUALIFIED를 출력할 수 없다. 기존 7장면·old/new를 강제하는 v1 Cohort는 보존하고 정식 검증에는 별도의 버전 인식 로더를 쓴다. cohort에 공유 choice/blueprint/beats hash, 실제 source-group split manifest, selectionPolicyHash를 고정한다. `plan_qualification(cohort)`는 단계별 호출 수·최악 토큰/비용·응답 분모를 계산한다. `run_qualification`은 프로필 레지스트리로 지원 경로를 고른다. `RunBudget`은 `common/budget.py`에 정의하고 모든 하위 작업에 같은 인스턴스를 전달한다.

- [ ] `test_voice_comparison_requires_identical_beats`, `test_negative_like_phrase_does_not_branch_to_acceptance`, `test_source_group_overlap_or_unresolved_audit_blocks_qualification`, `test_review_packet_has_canon_blueprint_and_blind_voice_reference`, `test_missing_humans_or_counter_cannot_qualify`, `test_failed_formation_stays_in_denominator`, `test_consumer_budget_counts_reasoning_tokens`, `test_resume_does_not_reset_shared_budget`, `test_unknown_price_is_not_zero_cost`를 작성한다.
- [ ] A~D와 별도 S8 대조·S3 예시 순서 진단의 해시/분모를 기록하고 블라인드 평가 자료를 만든다. 실제 실행에는 `--execute`와 실행 요청이 필요하다.
- [ ] `uv run pytest tests/test_choice_voice_protocol.py tests/test_persona_qualification.py -q`와 `bash scripts/check.sh`를 실행한다. 실제 호출 전에는 dry run만 보고한다.

## 7. 호출·비용과 실행 순서

구현 의존성은 Task 0 → Task 1/2 → Task 3 → Task 4 → Task 5 → Task 6이다. Task 1과 Task 2는 계약 합의 뒤 독립적으로 진행할 수 있고, 나머지는 앞 단계의 계약·해시 검증이 통과한 뒤 연결한다.

호출 수는 코드 구현 뒤 dry run에서 확정한다. 초기 상한 제안은 S3 요구 목록 1+후보 생성 1+의미 검토 1, S7 설계 1+뼈대 1+렌더링 1+보존 검토 1로 정상 7회다. 각 호출에 형식 재시도 최대 2회를 적용하면 최대 21회이며, 기존 G3/G6 사전 검토와 형식 교정·외부 판정이 있다면 별도 합산한다. 한 호출에 여러 캐릭터/단계를 숨겨 비용을 누락하지 않는다. 팩 준비·승인 감사·G3 편집 revision과 실제 대화 응답은 이 수에 포함되지 않는다.

단순 호출 예약을 넘어 생성·의미 검토·분기 해석·실제 대화가 같은 실행 예산과 영속 원장을 사용하게 한다. 호출 전 requestId로 최대 입력/총 출력 토큰과 비용을 예약하고 결과의 실제 사용량을 정산한다. 재개 시 기존 실패/재시도/미정산 예약을 복원하며 상한을 초기화하지 않는다. 미확인 단가는 0으로 합산하지 않는다. 실행 설정의 보수적 단가 상한이 없으면 화폐 상한을 입증할 수 없으므로 실제 실행을 막고 사유를 보고한다. 기존 슬롯당 9호출 예약과 하위 `ctx.budget()`의 독립 생성 경로를 새 프로필에서 제거한다.

개발 192응답·S3 진단·S8 대조·연속 대화·정식 보류를 한 번에 실행하지 않는다. `오프라인 구현 → 출처 확인/팩 준비 → 기존 long의 선택 실행 확인 → S3 최소 진단 → A~D 개발 대조 → S8 대조 → 통합·연속 이력 → 정식 보류` 순서로 진행한다. 각 실제 실행 전에 모델·토큰·시간·화폐 비용 상한을 보고하고 상한을 넘으면 중단한다. 소비 총 출력 예산은 reasoning을 포함하며 이전 500예산 잘림과 별도 2400조건 관찰을 숨기지 않는다.

## 8. Review Focus와 완료 조건

1. 씨앗과 모순되는 설계가 세련된 대사를 만든 경우에도 실패해야 한다(Task 1·3).
2. 실제 출처가 없는 모델 대사가 승인 원본으로 오인되지 않아야 한다(Task 2).
3. 렌더링이 수락/거절·합의·소유자를 바꾼 경우 숫자 보존만으로 통과하면 안 된다(Task 4).
4. 말투 팩 변경 뒤 재개·G6·패키지가 이전 결과를 읽지 않아야 한다(Task 5).
5. 평가 예시 유출·부족한 사람 검토·미완성 슬롯을 좋은 결과로 처리하면 안 된다(Task 6).

계획 완료는 위 설계·작업·검증·위험에 대한 독립 검토가 반영된 문서가 있는 상태다. 구현 완료는 오프라인 검증까지이며, 페르소나 기본 품질 합격은 별도의 실제 모델·사람·보류 근거가 있어야 한다. 이번 작업에서 달성할 것은 계획 완료다.

## 9. 검토와 후속 기록

독립 검토 결과와 반영 여부는 [검토 보고서](../reports/2026-10-29-persona-choice-voice-plan-review.md)에 남긴다. 검토자는 계획의 선택 설계와 말투·품질 검증을 나누어 읽는다. 제품 구현과 실제 품질 검증은 아직 실행하지 않았다.
