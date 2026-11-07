# 페르소나 형성과 기본 품질 검증

새 형성 공정은 한국어 문자·long 전용 프로필이다. 형성 완료와 품질 합격은 다르다. 설정이 없는 과거 실행은 기존 공정을 유지한다.

## 형성

실행 루트의 `factory.toml`에 아래 설정을 둔다.

```toml
[stages.s7]
formation_profile = "ko-text-prompt-long-v1"
# profile_path = "profile.json"  # 없으면 미동결 제안 프로필을 쓴다.
```

승인된 기획 뒤 `cfp persona traits <character_id>`로 호출 계획을 확인하고 `--execute`로 형성한다. S7은 한 호출로 특질·행동·목소리를, 다음 호출로12개 다중 턴 예시를 만든다. 형식 재시도는 단계마다 최대2회다. 의미 검사 실패는 출력 선별이나 문장 교정으로 숨기지 않는다.

`cfp persona prompts <character_id>`는 새 공정에서 모델 호출0회다. `--execute`를 주면 정본·설계·고정4예시를 long으로 묶고 G6 검토 페이지를 만든다. 기존 long/short probe 대신 별도 누적 대화 검증을 사용한다. 생성된 `gate-G6.html`에서 설계·12개 예시·긴 프롬프트를 확인할 수 있다.

새 `prompt-pair-v2`의 short는 미지원 상태다. S9/S10의 short 필수 경로는 명시적으로 거절한다. S11의 long 전용 소비는 short를 만들거나 학습을 제출하지 않는다. 승인 bundle이 참조한 S7 revision을 고정하므로 나중의 새 특질이 이미 승인한 페르소나를 바꾸지 않는다.

## 정식 검증

cohort manifest는 개발/보류 구분, 독립 슬롯, 장면별 사용자 턴·분기·행동 기대값, 프로필·루브릭·공정 해시를 사전에 고정한다. 자세한 규약과 제안 수치는 [개선 계획](../product/2026-10-29-persona-quality-floor-plan.md)을 따른다. 보류 문제는 형성 모델에 전달하지 않는다.

```text
cfp persona qualify plan <cohort.json>
cfp persona qualify run <cohort.json> --execute --tokenizer-url <exact-tokenizer-endpoint>
cfp persona qualify report <run-directory> --human-reviews <reviews.json>
```

실행 루트의 `providers.dialogue`는 프로필의 소비 모델에 결합해야 한다. 정확한 계수 endpoint는 모델·messages를 받고 `{model, exact: true, count}`를 반환해야 한다. 실행 전과 매 요청 전 연결·토큰 한도를 검사한다. 다른 모델의 tokenizer나 추정치를 실측으로 쓰지 않는다. 현재 로컬 중계의 `/v1/tokenize`는404를 반환하므로 그 주소를 그대로 쓰면 정식 검증을 시작할 수 없다.

등록·실제 요청·첫 응답·부분 실패는 `runs/quality/` 아래 남는다. 응답 이후 재추출은 하지 않으며, 결과가 불명확한 이전 요청도 조용히 다시 호출하지 않는다. 실패 슬롯은 첫 통과 분모에서 지우지 않는다. baseline은 동결된 source 경로·해시를 명시하며 새 공정으로 대신 실행하지 않는다.

사람 검토 패킷은 `persona_quality.packet.export_review_packet(run)`으로 내보낸다. 패킷에는 모델·공정 이름이나 LLM 결함 후보를 넣지 않으며 private 매핑은 별도 보관한다. 검토 양식의 모든 장면·턴을 채우고 독립 이중 평가·불일치 조정을 남긴다. 형성 예시나 합성 테스트를 실제 대화 결과로 세지 않는다.

사람 검토가 없으면 `METRICS_ONLY`, 미실행은 `NOT_RUN`, 기준·독립성·원문 완전성 미달은 `NOT_QUALIFIED`다. 동결 프로필과 전체 증거를 충족한 경우만 `QUALIFIED`다. 단가 미확인은 무료가 아니며 실행량·가정 비용·실제 청구액을 구분한다.

## 선택·실제 말투 분리 프로필

`ko-text-choice-voice-long-v2`를 선택하면 새 S3/G3부터 진행한다. 과거 기획에 없는 선택 근거와 승인 기록을 만들어 붙이지 않는다. 기존 프로필과 승인 결과는 그대로 읽을 수 있다.

```toml
[stages.s7]
formation_profile = "ko-text-choice-voice-long-v2"
voice_packs = ["/data/voice-library/soft/pack.json"]
voice_approval_index = "/data/voice-library/trusted-approvals.json"
voice_policy = "/data/voice-library/policy.json"
budget_run_id = "choice-voice-development-1"
max_run_tokens = 2000000
# 실제 공급자는 두 항목에 검증한 단가 또는 보수적인 상한 단가를 넣어야 한다.
# input_rate_upper_per_million = ...
# output_rate_upper_per_million = ...
# quality_profile = "/data/frozen-quality-profile.json"
```

말투 자산은 [승인 자료 안내](voice-assets.md)를 따른다. 해당 자료의 출처/승인이 확인되지 않으면 생성 전에 멈춘다. 코드가 있다는 사실만으로 실제 자료가 준비되거나 품질이 합격한 것은 아니다.

S3는 요구 목록·후보/선택 근거·독립 의미 검토로 정상 3회, 형식 재시도 포함 최대 9회다. S7은 설계·12개 내용 뼈대·말투 생성·독립 보존 검토로 정상 4회, 최대 12회다. 기본 형성 합계는 정상 7회·최대 21회이며 G3/G6 사전 검토, 새 편집 revision, 실제 대화/평가 호출은 따로 더한다. 명령을 실행하기 전에 dry run과 전체 비용 상한을 확인한다.

G3에서는 후보 하나를 직접 고른다. 선택 근거의 우선순위·감수 비용·전환 조건을 함께 볼 수 있다. 기획을 편집하면 새 pr에서 재설계·검토한 뒤 같은 G3에서 다시 승인한다. 원래 요구를 바꾸는 편집에는 화면의 해당 요구를 선택하거나 답 JSON의 `supersedesRequirements`에 해당 ID를 적는다. 관련 없는 요구의 대체는 거절한다. 명시하지 않은 고정 요구는 유지된다. `--execute`가 없는 편집은 유료 재설계를 하지 않고 준비된 새 revision에서 멈춘다.

S8은 검증된 12대화 중 일상·감정 변화·핵심 선택·조건 변경과 승인 선택 규칙을 포함하는 4대화를 결정적으로 고른다. 커버리지가 부족하거나 8,000자를 넘으면 자르거나 좋은 예시를 다시 뽑지 않고 실패한다. S3의 생성 말투 초안은 승인 팩 기준을 덮어쓰지 않는다.

G6는 정확한 S3/S7/말투/검사 버전 묶음을 승인한다. 대기 중 현재 말투 정책·팩·신뢰 승인 색인이나 생성·검토 모델·지시·평가 프로필이 바뀌면 S7에서 새 revision을 만든 뒤 승인해야 한다. 이미 승인한 과거 묶음은 수정하지 않는다. short 미지원은 유지하며, 파일을 구형 형식으로 바꿔 이 제한을 우회할 수 없다.

형성 단계들은 `runs/budgets/<budget_run_id>.json`의 영속 예약을 공유한다. 예산은 입력과 추론을 포함한 총 출력 토큰·호출·비용을 제한한다. 실패나 결과 미확인의 예약도 재개하면서 지우지 않는다. 복구를 위해 임의로 새 budget_run_id를 붙이지 않는다. 새 ID는 별도 실행 예산을 시작할 때만 사용한다.

정식 비용 상한을 입증할 수 없는 실제 Codex 중첩 도구 실행은 새 프로필에서 거절한다. 가짜 Codex는 오프라인 경로 검사에 쓴다. 실제 형성/검증은 상한화된 API 경로로 수행한다.

## A~D 개발 대조와 정식 판정의 차이

`persona-development-cohort-v2`는 미리 동결한 A~D 산출물과 2장면×6응답을 받는다. B/C/D는 같은 선택/blueprint, B/C는 같은 생성 말투 바인딩, C/D는 같은 내용 뼈대 해시를 사용해야 한다. A~D의 시스템 지침과 컴파일 프로필도 같아야 한다. C는 생성 말투 DRAFT 대조이고 D는 승인된 실제 팩을 사용한다. 준비된 조건의 원본·첫 결과·실패는 각각 보존한다. 수집기가 조건을 새로 만들어 주거나 불리한 산출물을 교체하지 않는다.

각 슬롯은 `pair`와 `producer`의 실제 파일 경로·SHA-256을 포함한다. `stages.persona_quality.producers.prepare_development_pair(arm, assets, out)`는 모델을 호출하지 않고 동결한 첫 산출물을 컴파일하며 `prompt-pair.json`과 `producer.json` 참조를 반환한다. 이미 수집한 결과의 출처를 나중에 붙이지 말고 조건별 첫 생성 때 보존한다.

`assets`의 공통 키는 `seed`, `plan`, `trait`, `blueprint`, `systemRules`다. A에는 당시 `profile`, `dialogues`, `legacyBundle`을 준다. B/C/D에는 `choice`, `compilerProfile`, `voiceBinding`, `dialogues`를 준다. B의 dialogues는 직접 생성한 FormationDialogues이고 C/D는 RenderedDialogues다. C/D는 추가로 같은 `beats`를 주며 D에는 `voicePolicy`도 준다. B/C의 voiceBinding은 실제 생성한 DRAFT 기준이다. 원문·검증·생성 초안의 의미가 다른 파일을 라벨만 바꾸어 넣지 않는다.

수집 전에는 생산자 기록의 해시만 보는 것이 아니라 실제 자료로 소비 프롬프트를 다시 조립해 완전히 같은지 검사한다. A는 동결된 v1 bundle을 재현한다. A~D 모두 기존 v1 컴파일러·고정 네 예시 슬롯을 사용하고, v2 blueprint는 기존 필드로 투영하되 실제 원본 해시를 보존한다. B→C는 직접 대사와 내용 뼈대 경로, C→D는 동일 뼈대의 생성 말투와 승인 말투 적용 차이다. 배포용 v2 커버리지 컴파일러의 효과는 이 비교에 섞지 않고 별도 대조로 측정한다. source recipe의 동일성이 결과 문장의 차이를 보장하지는 않으며, 차이가 없다는 결과도 그대로 남긴다.

이 manifest도 같은 `persona qualify plan/run/report` 명령으로 읽는다. 매 요청에 exact tokenizer와 고정 소비 모델을 사용하고, 동일한 중립 후속 질문으로 말투에 따른 잘못된 분기를 막는다. `좋아` 같은 문자열로 합의를 추정하는 분기는 새 프로필에서 지원하지 않는다. 의미 상태 분기가 필요한 실험은 별도로 설계해야 한다.

개발 검토 패킷은 정본·선택 기준·비주입 말투 참조와 대화를 제공하고 공정/모델 이름은 가린다. `human-reviews-template.json`을 복사해 모든 장면의 자연스러움·말투 적합성·선택 충실도와 실제 인용을 채운다. 개발 보고서는 사람 검토가 있어도 `METRICS_ONLY`이며 정식 품질 합격을 내지 않는다.

정식 v2 검증은 실제 source-group manifest를 `overlapAudit` 경로에 두고 프로필의 `splitManifestSha256`과 결합한다. 실제 평가 장면도 감사한 파일 내용과 일치해야 한다. 새로 형성한 보류 슬롯에서 기존 60응답·사람 검토·이중 평가·실패 분모 조건을 유지한다. 구형 코드를 subprocess로 형성하면 공유 예산을 입증할 수 없어 이 경로에서는 거절하며, 구형 비교는 위의 동결 개발 대조로 수행한다. 기존 v1 검증 경로는 유지된다.

## 별도 S8 선정·S3 예시 순서 진단

S8 대조는 `persona-development-cohort-v2`의 `comparison="selection"`과 `CURRENT`/`COVERED` 두 arm을 쓴다. 각 캐릭터의 두 슬롯은 같은 2장면×6응답이다. 앞의 `prepare_development_pair()`에 두 arm을 각각 주며, D의 원천 자산 외에 같은 v2 `profile`, 실제 `coveragePolicy`를 연결한다. 모든 producer 자산이 같아야 한다. CURRENT는 8/2/2 장면을 기존 네 슬롯에 대응시켜 고르고 COVERED는 커버리지를 충족하는 네 예시를 고른다. 나머지 최종 조립·목소리·12개 대사는 동일하다. 결과가 같아도 실패나 재추출 사유로 취급하지 않는다. 이 수집도 기존 qualify 명령과 공유 비용 제한을 사용하며 항상 개발 지표다.

S3 진단은 `stages.persona_quality.s3_diagnostics`의 `export_s3_diagnostic(manifest, out)`와 `report_s3_diagnostic(out, human_reviews)`를 사용한다. 이 두 함수는 외부 모델을 호출하지 않는다. 기존/예시 제거/순서 교환 조건을 한 번씩 생성할 때 첫 요청·결과 또는 실패를 보존한 뒤 연결하는 감사·검토 도구다.

`S3Diagnostic`은 `s3-diagnostic-v1`, `id`, `expectedCandidates`, 세 `arms`를 가진다. arm은 `original`, `removed`, `reordered`다. 각 항목은 `id`, 같은 `seed`/`template`/`examples` 파일 참조, `exampleOrder`, 실제 `renderedInput`, `firstAttempt`, 같은 `modelBinding`, `firstOutput` 또는 `failure` 중 하나를 포함한다. 참조는 `{path, sha256}`다. template에는 `{{SEED_JSON}}`, `{{BEHAVIOR_EXAMPLES}}`가 정확히 한 번씩 있어야 한다. 씨앗은 키 순서 정렬·한국어 유지 JSON으로, 예시는 지정 순서대로 줄바꿈 결합한다. 원래 조건은 모든 예시를 한 번씩, 제거는 빈 목록, 교환은 같은 목록의 다른 순서를 사용한다. 다른 지시나 모델 설정도 바꾸면 거절한다.

`firstAttempt`는 `attemptOrdinal: 1`, `inputSha256`, `modelBinding`, `resultSha256`를 실제 파일과 결합한다. `firstOutput`은 기존 PlanVariantsOutput을 그대로 읽으므로 `schemaVersion`, `axisNote`, `variants`의 실제 CharacterPlanV2 후보들을 보존한다. 원본 필드를 제거해 해시를 바꾸지 않는다. 실패 arm을 빼거나 성공 결과로 교체하지 않는다. 출력 packet은 arm 이름을 가리고 후보 위치·씨앗·기획을 제시한다. 사람이 `seedFaithful`, `choiceCategory`, 원문 `evidence`를 채운 뒤 위치별 행동 분포와 씨앗 충실도를 집계한다. 전체 예정 후보 수에는 실패 arm의 후보도 남는다. `METRICS_ONLY`이며 인과 효과나 품질 합격을 자동으로 선언하지 않는다.

## 2026-10-29 실제 개발 관찰의 상태

[실제 검증 보고서](../reports/2026-10-29-persona-choice-voice-live-validation.md)는 API183요청·대화132응답을 다룬다. 원래 형성4슬롯은 모두 첫 완료에 실패했고, 저장된 두 원천 묶음을 평가용으로 재검증했다. 이 결과를 정식 qualify 실행이나 운영 G6 승인으로 읽지 않는다.

이 관찰의 전용 실행기는 `scripts/persona_choice_voice_live_20261029.py`, 보고/검증기는 `scripts/persona_choice_voice_live_report.py`다. `runs/experiments/20261029-choice-voice-live-r1`은 동결 증거다. 원본 실패나 raw응답을 수정해 재실행하지 않는다. 별도 실험에는 새 실행 루트·모델/프롬프트/상한 등록이 필요하다.

exact tokenizer 없이 수행한 한정 관찰은 직렬화 바이트+여유분 상한과 실제 반환 사용량 사후 검사로 구분했다. 이것을 기존 qualify 경로의 exact 요건을 충족한 것으로 표시하면 안 된다. 신규/재개 모두 실패·잘림·사용량 미확인 응답에서 멈추며, 같은 조건의 두 수집기는 잠금으로 직렬화한다.

최종 네 예시에서 규칙 ID를 다뤘더라도 활성/비활성 조건이 모두 검증된 것은 아니다. 실제 이력에 없는 종료 시각을 가정한 오류와 말투 개선 미확인이 남았으므로 새 프로필 기본값을 올리지 않았다.

실험의 비교 상황을 고정하려면 새 프로필의 `[stages.s3] choice_situations` 에 중복되지 않는 비어 있지 않은 문자열 목록을 지정한다. 미지정 시 같은 상황 집합을 생성자가 설계한다. 지정 시 모든 후보의 situation이 목록과 일치하지 않으면 실패한다.
