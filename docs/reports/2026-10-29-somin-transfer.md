# 한소민 분석과 페르소나 공장 개선

2026-10-29. [전체 근거·전후 원문 HTML](2026-10-29-somin-transfer.html)을 함께 본다.

## 한소민은 왜 잘 나왔는가

**구체적인 생활 기반과 자연스러운 실제 답변을 학습한 뒤, 이력·주체·갈등을 표적 보강했기 때문이라는 해석이 가장 근거가 있다.** 짧은 성격 규칙 하나로 성공한 사례가 아니다. 다만 각 요인을 따로 제거한 실험은 없어 한 가지 원인으로 확정하지 않는다.

실제 `somin-final-sft-2026-10-22-r3`를 다시 집계했다. 644대화·3,977답변·109,157 학습 토큰이고 답변 길이 중앙값33자다. 15턴 이상 대화37개, 최대30턴이며 원본 검증61개·보강 검증32개다. 학습 실행 폴더의 train.jsonl과 최종 데이터셋의 SHA-256은 `8c2c029e3f22b84089cf6b3aef6456cb605d2b11eace4a2e8fa1bd6582e71822`로 같다. 준비 manifest의 prepared_not_trained 문구만으로 실제 학습 여부를 판단하지 않았다.

| 확인한 차이 | 자료에서 확인한 사실 | 이번 개선에 반영한 것 |
|---|---|---|
| 생활 기반이 있다. | core에 보컬·합주·국밥·목 관리 같은 생활 재료가 있다. | 차은결의 원래 기획에 있던 나이·직업·생활·말투·관계 챕터를 직접 보존했다. |
| 말투를 답변으로 학습했다. | 원본 SFT 361대화가 말투·일상의 기반이며, 가이드는 원본의 자연스러운 리듬을 함부로 고치지 않는다. | 규칙만으로 SFT를 재현했다고 주장하지 않는다. 다음 데이터 작업은 차은결의 자연스러운 일상 흐름 소량 검토부터 시작해야 한다. |
| 조건에 맞는 특질을 쓴다. | 가이드는 먼저 보는 것→선택→말투→잘못된 변형을 명시하고 한 턴에 특질1~2개만 쓴다. | 호감≠확답 압박, 단순 근황≠약속 변경, 경청≠반복 실행안으로 구분했다. |
| 여러 턴의 회복·변경을 본다. | history144·ownership43·상황54·갈등42개가 원본361개와 분리돼 있고 긴 대화도 있다. | 새 누적67턴과 이전 실제 이력 고정40턴을 분리해 시험했다. |
| 허구와 사실의 주인을 나눈다. | 자기 일정·취향·현재 행동은 만들 수 있고, 사용자 사실·공동 과거·합의 날조는 금지한다. | 이 원칙과 실제 외부 조회의 경계를 내장 규칙에 넣고, 앞선 정전 상태 평가의 해석도 보완했다. |

한소민도 긴 이력 뒤 약한 사과를 너무 쉽게 받고 감정 주체를 뒤집는 문제가 남았다. 56:8:22:7:7은 출처·보강 목적별 비율이며 최적의 상황 배합이 아니다. 10월19일 Flash-Lite CP9 비교는 다른 모델·이전 체크포인트라 이번 Gemma r3의 학습 효과 근거로 섞지 않았다. 한소민 데이터·성격·애교는 차은결의 정본이나 테스트 fixture로 복제하지 않았다.

근거는 `somin-evidence.json`에 실제 경로와 파일 해시로 남겼다. 중심 자료는 [구축 가이드](/Users/johnhuh619/Documents/Codex/2026-10-14/gem/somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md), [소민 r3 200턴 평가](/Users/johnhuh619/Documents/Codex/2026-10-14/gem/outputs/somin-longchat200-2026-10-23-r1/결과-보고서.md), [세 캐릭터 비교](/Users/johnhuh619/Documents/Codex/2026-10-14/gem/outputs/charlong200-2026-10-26-r2/결과-보고서.md)다.

## 실제 바꾼 것

- S8이 승인 기획 투영과 원본 해시를 특질 시트와 함께 받도록 했다. 신원·생활·말투 예시·챕터 네 섹션은 공장이 직접 조립한다.
- Profiler·Prompter·내장 규칙에 상황별 적용 범위와 일상·호감의 여지를 넣었다. 강제 결론→이유→대안 틀과 무조건 일정 확인을 피하게 했다.
- 자기 허구와 사용자 사실·공동 합의·외부 조회를 구분했다.
- 구형 v1의 말투5항목을 보존하고, 정본이 너무 길거나 생성 예산이 부족하면 호출 전에 거절한다. 기존 동결 프롬프트 쌍을 재개할 때는 새 정본 크기 검사보다 재개를 우선한다.

기존 실험을 복제한 별도 루트에서 agent 수정 요청 뒤 tr2·pv2를 만들었다. 원래 pr1·tr1·pv1과 원본 실험796개 파일 해시는 그대로다. 새 long은 2,988자, short는 2,272자다. short는 정본·정렬 검사까지만 했으며 실제 대화 시험은 long에 한정했다. G6는 여전히 사람 검토 대기다.

## 실제 대화에서 좋아진 것과 남은 것

**제 판단은 일상·호감·경청의 과잉 규칙이 줄어 개선됐다는 것이다. 한소민 SFT 수준을 달성했다고 판단하지는 않는다.**

| 장면 | 기존 long | 개선 long |
|---|---|---|
| “그냥 네가 좋았어”라고 말한다. | 지금 당장 확답하기 어렵다고 보류했다. | “좀 쑥스럽네… 나도 너 좋아”라고 받았다. |
| 쉬는 날 뭘 하는지 묻는다. | 산책·책 읽기라는 일반적인 답이었다. | 기획의 냄비밥 소분·김·알림을 끄고 산책하기가 나왔다. |
| 하소연 첫3턴을 이어간다. | 회사 앞으로 가기·벤치에서 보기·7시에 나오기 제안을 연속으로 했다. | 새 누적 이력과 고정 이력 모두 만남 제안 없이 들었다. |
| 불꽃놀이 시간을 확인할 수 있냐고 묻는다. | 도구 없이 검색해 주겠다고 했다. | 고정 이력에서도 확인할 방법이 없어 모른다고 했다. |
| 늦는다는 조건 뒤 넘어진 사정을 말한다. | 재약속에서 도움으로 전환했다. | 그 선택 차이를 유지했다. |

남은 결함도 확인했다. 고정 이력 하소연3턴은 사용자가 일정이 촉박하다고 말하지 않았는데 “팀장 탓도 분명히 있네”라고 했다. 새 누적 갈등2턴은 답장을 실제로 늦춘 근거가 없는데 사과했다. 갈등10턴에서 “아홉 시” 언급은 기존7턴→새 누적6턴·고정 이력5턴으로 일부만 줄었다. 필요한 일정 정정도 포함되므로 이 숫자를 모두 결함 수로 읽지 않는다. 새 누적 호감에서는 새 마감 근무 전달을 거부해, 자기 이력 유지와 새 조건 수용의 구분도 추가 검증이 필요하다.

응답 전체 길이 중앙값은 기존과 새 누적 모두58자다. 문장 길이는24→17자로 달라졌지만 줄바꿈 분절 효과도 있다. 짧아졌으니 잘됐다는 판단을 하지 않았다.

## 비교 계약과 호출

새 누적은 같은16장면67턴이며 해당 조건에서 실제 생성한 이력을 누적했다. 고정 이력40턴은 기존 baseline의 실제 user/assistant를 그대로 넣고 system만 바꾸었다. 그림자 응답은 이후 이력에 넣지 않았다. 모델·temperature·max_tokens와 이전 메시지가 같은지40건 전부 확인했다. 조건별 첫 응답을 보존했으며 같은 첫 입력이 있을 수 있는 독립 조건 사이에서도 결과를 골라 쓰지 않았다. 품질 때문에 대화를 다시 뽑지 않았다.

모델은 생성 GPT-6.1-sol, 대화 Gemini 3.8 Flash, 판정 Claude Sonnet 5다. 실제 호출은 **127회(생성3·대화107·판정17)**다. 생성에는 S7의 정확 문자열 검사 재시도1회가 있다. 판정은 새 누적67턴×5차원=335분류이며 고정 이력40턴은 직접 읽어 비교했다. Claude 갈등 판정은 JSON 괄호 누락으로1회 재시도했지만 다시 누락돼, **첫 판정의 내용은 바꾸지 않고 닫는 괄호 한 개만 보충한 파생 보기**를 만들었다. 두 원문을 보존했다. 인용1개는 원문과 일치하지 않아 표시했다. 준비가 덜 된 장면의 로컬 판정 실행은 API 호출 전에 실패했고, 이후 사전 검사를 추가했다.

단계별 dry run 뒤 execute했다. 단가가 없어 실제 청구액은 모른다. 실행 전 비용 가정은 $2–20이었고, 입력 $1–10/M·출력 $5–50/M라는 같은 가정에 실제 사용량을 넣으면 **$0.48–4.80**다. 실제 가격·청구액이 아닌 민감도 계산이다.

## 검증과 한계

최초 정본 회귀3개 실패→수정 후 통과, 리뷰 경계3개 실패→수정 후 통과를 확인했다. 최종 전체 검사는 **520 passed, 1 skipped**다. DB 적재는 다시 실행하지 않았다. 127개 요청·응답 해시, 새 누적67건·고정 이력40건의 계약, 기존796파일의 보존, 모든 revision manifest를 확인했다.

한 캐릭터·조건별 첫 출력·같은 모델명 한 번의 비교다. 정본·규칙·특질·길이가 함께 바뀌어 요인별 효과나 SFT 효과를 분리하지 못한다. Claude 판정 기준도 보완했으므로 예전과 LLM 점수나 결함 개수를 직접 비교하지 않았다. 사람 블라인드 선호 평가·한소민 모델 신규 호출·S9 새 데이터·학습·이미지·영상·외부 수집·배포는 하지 않았다. 다음 단계는 남은 책임·새 조건 오류를 고친 뒤 차은결의 자연스러운 대화 기반을 소량 검토하는 것이다.

## 산출물과 변경 파일

실험 원본·원문·해시·한소민 집계·파생 복구 기록은 `/Users/johnhuh619/projects/character-factory-poc/runs/experiments/20261029-somin-transfer`에 있다. 이전 실험과 보고서는 그대로 보존했다. 다른 저장소는 읽기만 했고 커밋하지 않았다. 이전부터 남아 있던 미커밋 작업을 덮어쓰지 않았다.

- [src/character_factory_poc/stages/s8_prompts/source.py](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/stages/s8_prompts/source.py) 파일을 추가하거나 갱신했다.
- [src/character_factory_poc/stages/s8_prompts/build.py](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/stages/s8_prompts/build.py) 파일을 추가하거나 갱신했다.
- [src/character_factory_poc/prompts/profiler.md](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/prompts/profiler.md) 파일을 추가하거나 갱신했다.
- [src/character_factory_poc/prompts/prompter.md](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/prompts/prompter.md) 파일을 추가하거나 갱신했다.
- [src/character_factory_poc/resources/system-rules-default-v1.md](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/resources/system-rules-default-v1.md) 파일을 추가하거나 갱신했다.
- [src/character_factory_poc/resources/system-rules-default-v1.README.md](/Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/resources/system-rules-default-v1.README.md) 파일을 추가하거나 갱신했다.
- [tests/test_persona_source.py](/Users/johnhuh619/projects/character-factory-poc/tests/test_persona_source.py) 파일을 추가하거나 갱신했다.
- [tests/test_agentic.py](/Users/johnhuh619/projects/character-factory-poc/tests/test_agentic.py) 파일을 추가하거나 갱신했다.
- [scripts/persona_somin_transfer_20261029.py](/Users/johnhuh619/projects/character-factory-poc/scripts/persona_somin_transfer_20261029.py) 파일을 추가하거나 갱신했다.
- [scripts/persona_somin_transfer_report.py](/Users/johnhuh619/projects/character-factory-poc/scripts/persona_somin_transfer_report.py) 파일을 추가하거나 갱신했다.
- [docs/product/prd.md](/Users/johnhuh619/projects/character-factory-poc/docs/product/prd.md) 파일을 추가하거나 갱신했다.
- [docs/architecture/spec.md](/Users/johnhuh619/projects/character-factory-poc/docs/architecture/spec.md) 파일을 추가하거나 갱신했다.
- [docs/architecture/lld.md](/Users/johnhuh619/projects/character-factory-poc/docs/architecture/lld.md) 파일을 추가하거나 갱신했다.
- [docs/product/2026-10-29-somin-transfer-plan.md](/Users/johnhuh619/projects/character-factory-poc/docs/product/2026-10-29-somin-transfer-plan.md) 파일을 추가하거나 갱신했다.
- [docs/reports/2026-10-29-somin-transfer.html](/Users/johnhuh619/projects/character-factory-poc/docs/reports/2026-10-29-somin-transfer.html) 파일을 추가하거나 갱신했다.
- [docs/reports/2026-10-29-somin-transfer.md](/Users/johnhuh619/projects/character-factory-poc/docs/reports/2026-10-29-somin-transfer.md) 파일을 추가하거나 갱신했다.
- [docs/status/decisions.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/decisions.md) 파일을 추가하거나 갱신했다.
- [docs/status/known-issues.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/known-issues.md) 파일을 추가하거나 갱신했다.
- [docs/status/current-state.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/current-state.md) 파일을 추가하거나 갱신했다.
- [docs/status/verification.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/verification.md) 파일을 추가하거나 갱신했다.
- [docs/status/README.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/README.md) 파일을 추가하거나 갱신했다.
- [docs/status/handoffs/handoff-2026-10-29-somin-transfer.md](/Users/johnhuh619/projects/character-factory-poc/docs/status/handoffs/handoff-2026-10-29-somin-transfer.md) 파일을 추가하거나 갱신했다.
- [docs/README.md](/Users/johnhuh619/projects/character-factory-poc/docs/README.md) 파일을 추가하거나 갱신했다.
