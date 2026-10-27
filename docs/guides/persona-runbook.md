# 페르소나 축 실행 안내 (S3 import → S7 → S8 → G6)

이 안내는 구현된 범위(D-0013)만 다룬다. 명령은 저장소 루트에서 `uv run acf ...`로 실행한다. 유료 호출은 `--execute`가 있어야 하고 사용자 지시가 있을 때만 한다(D-0009).

## 0. 한 번에 돌리기 (에이전틱)

```
uv run acf run x --new-slug <slug> --until G6 --brief brief.md --probes probes.txt --execute
```

Planner가 브리프와 프리셋 카탈로그로 기획서를 쓰고 G3에서 멈춘다. G3를 `acf gate import ... G3`로 승인한 뒤 같은 명령을 다시 실행하면 S7·S8을 이어서 돌리고 G6에서 멈춘다. 실험에서만 `--auto-approve G3`로 건너뛸 수 있다(기록에 남는다, D-0015). `[agent] backend = "codex_exec"`이면 각 단계 에이전트가 작업 공간 안에서 파일을 읽고 `./check.sh`로 스스로 검사한다. 실행 예는 [에이전틱 실행 보고서](../reports/2026-10-14-agentic-p29-run.md)에 있다.

## 1. 설정

`factory.example.toml`을 `factory.toml`로 복사해 고친다. 생성(`text`)과 판정(`judge`)은 다른 모델 계열이어야 한다(D-0010). 같은 계열을 꼭 써야 하면 `--allow-same-family`를 명시한다. API 키는 `api_key_env`에 적힌 환경변수로만 읽는다.

긴 프롬프트의 시스템 규칙 원문(Q-0006)은 `[stages.s8] system_rules_path`에 경로를 적는다. 비워 두면 내장 기본 규칙(`src/acf/resources/system-rules-default-v1.md`)을 쓰고, 산출물의 `systemRulesRef`에 `builtin:`으로 표시된다.

## 2. 기획서 들여오기 (S3, G3)

[기획서 템플릿](../templates/character-plan-template.json)을 복사해 채운다. 성격은 형용사가 아니라 행동으로 쓴다.

```
uv run acf plan import <slug> --from runs/briefs/<slug>/plan.json
```

`character_id`(`cf-YYYYMMDD-<slug>`)와 `pr1`이 발급되고, G3가 `reviewer=user, manual-plan`으로 승인 기록된다. 산출물은 `runs/characters/<character_id>/s3-plan/pr1/`다.

## 3. 상세 특질 시트 (S7)

```
uv run acf persona traits <character_id>                 # dry run: 호출 계획만
uv run acf persona traits <character_id> --execute       # 실제 생성
```

참조 유형·프리셋이 있으면 `--references refs.json`(`[{"kind":"STANFORD","id":"P29","version":"3.0"}]`)과 카드 본문 `--reference-doc P29.json`을 준다. 첫 실제 실행 기록은 [2026-10-14 보고서](../reports/2026-10-14-dohee-p29-persona-run.md)에 있다. 14유형과 프리셋 사이 대응은 가정하지 않는다(Q-0005). 자동 검사(필수 칸, 낱말 나열, 전환 조건 2개 이상, 상황 3개 이상)에 실패하면 사유를 붙여 최대 `max_check_retries`회 재생성하고, 그래도 실패하면 `CHECK_FAILED`로 멈춘다. 마지막 출력은 `s7-traits/tr<k>/workspace/last-failed.json`에 남는다.

## 4. 프롬프트 쌍과 말투 확인 표본 (S8)

말투 확인 문장을 한 줄에 하나씩 `probes.txt`에 적는다(브리프의 `voiceProbes`에 해당, 5개 이내 권장).

```
uv run acf persona prompts <character_id> --probes probes.txt            # dry run
uv run acf persona prompts <character_id> --probes probes.txt --execute
```

호출 수는 Prompter 1회(+재시도) + 문장당 3회(긴 응답, 짧은 응답, 판정)다. 표본만 다시 돌리려면 `acf persona probe <character_id> --probes probes.txt --execute`를 쓴다(프롬프트 쌍은 그대로, `prompt-probe-r<k>.json` 누적). 산출물은 `s8-prompts/pv<k>/`의 `prompt-pair.json`, `long.md`, `short.md`, `prompt-probe.json`, `gate-G6.html`이다. 짧은 프롬프트는 `shortAdopted=false`로 고정되며 G8(SFT 비교) 전에는 운영에 쓰지 않는다(D-0006).

## 5. G6 검토와 승인

`gate-G6.html`을 브라우저로 연다(서버 없음). 특질 시트, 긴·짧은 프롬프트, 문장별 두 응답을 나란히 보고 결정을 고른 뒤 "답 JSON 복사"로 `answer.json`을 만든다.

```
uv run acf gate import <character_id> G6 --answer answer.json
```

`APPROVE`면 `persona-version.json`이 생기고 `persona_version=pv<k>`가 확정된다. `REQUEST_CHANGES`·`REJECT`면 사유가 기록되고 S8을 다시 돌리면 `pv<k+1>`로 새 revision이 생긴다. 판정 모델의 선택은 참고 자료이며 승인에 자동으로 쓰이지 않는다.

## 6. 상태·원장·검증

```
uv run acf status <character_id>
uv run acf ledger report <character_id>
uv run acf verify <character_id>
```

개발 검증은 `scripts/check.sh`(lint, format, 오프라인 테스트)다. 테스트는 네트워크를 막고 가짜 모델만 쓴다.

