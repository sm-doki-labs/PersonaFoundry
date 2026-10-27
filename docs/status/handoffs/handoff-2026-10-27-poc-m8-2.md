# 인계: 2026-10-27 PoC M8 2차(C·D1·D2·E·G2 합침, 이름 바꾸기)

이전 인계: [handoff-2026-10-27-poc-m8-1.md](handoff-2026-10-27-poc-m8-1.md)

## 1. 지금 상태 한눈에

- S9 데이터셋, S10 학습(dry run)·평가, S11 패키지·우리 앱 내보내기, 관문별 화면이 `main`에 들어왔다. 각 단계는 함수로 있고, 그래프·오케스트레이터·`approve_gate`·CLI 연결(H 갈래)은 아직이다. 그래서 웹에서 G7a·G7·G8·G9 결정은 501을 돌려준다.
- 이름을 바꿨다: 배포 이름 `character-factory-poc`, 코드 모듈 `character_factory_poc`, 명령 `cfp`, 환경변수 접두사 `CFP_`(사용자 요청). 일회용 Docker DB도 `cfp-verify`(관리자 `cfp_admin`)로 바뀌었다.
- `scripts/check.sh` 444 passed(일회용 DB 실제 적재 테스트 포함). 실제 LLM·이미지·학습·영상 호출은 하지 않았다.

## 2. 이번 세션에서 한 일

- 하위 에이전트 다섯(`opencode-go/deepseek-v4.1-flash`)의 브랜치를 합쳤다: C `1fd5065`, D1 `f8dcde1`, D2 `77d029a`, E `effc679`, G2 `225f629`. 파일 겹침은 없었다. 첫 시도 다섯은 차례가 끝나며 사라져 같은 지시로 다시 띄웠다.
- 이름 바꾸기 스크립트로 코드·테스트·설정·현행 문서를 바꿨다. 결정 기록·검증 기록·지난 인계·보고서는 옛 이름 그대로 둔다. 저장소 밖 실제 폴더 경로(`/tmp/acf-*`)도 그대로다.
- Git 밖 `factory.toml`에 PoC 설정을 넣었다: `[stages.s1] previews_per_cluster = 1`, `[stages.s1.collect]`, `[stages.s2] base_photo = "picked"`, `[export.doki_app]`, `[export.verify] admin_url_env = "CFP_PG_ADMIN_URL"`, `[web]`. 기존 `factory.toml`에는 `ACF_` 환경변수가 없었다.

## 3. 결정

- 없음(이름 바꾸기는 사용자 요청. 결정 기록에는 다음 세션의 H 갈래와 함께 남긴다).

## 4. 확인한 사실과 정정

- 하위 에이전트 보고의 계약 보강 제안: `eval-prereg-v2`의 학습 전 모델 칸(`UNBOUND:<provider>`), `Profile` 프로필 카드 네 칸, G7a 클러스터별 관문 기록 이름(`gates/G7a-<rev>-<cluster>.json`), `training-run-v2` 시각·오류 칸, `eval-run-v1` `turnNo`. 계약은 아직 바꾸지 않았다.
- 평가 전체 실행은 응답 약 2,700회라 기본 예산 200회로는 거부된다. `s10` 진입점은 `training-run-v2.modelBinding`이 있는지 확인해야 한다(dry run만 있으면 `s10t`가 `AWAITING_HUMAN`이라 그래프상 통과로 보인다).

## 5. 미결

- K-0037은 G1~G6 화면 연결로 일부 해결, G7a~G9는 H 갈래 뒤.
- 사용자 셸이나 다른 설정에 `ACF_` 변수가 있으면 `CFP_`로 바꿔야 한다.

## 6. 다음 할 일

1. H 갈래: `graph.py` `s9s·s9·s10t·s10·s11·sx` `implemented=True`, 오케스트레이터 러너, `approve_gate`에 G7a·G7·G8·G9, CLI `cfp data|train|eval|release|export`, 웹 `GATE_META` 연결, `tests/test_offline_pipeline.py`(여성·남성 합성 브리프로 S1 → G9 → 적재).
2. 위 계약 보강을 결정 기록과 함께 반영한다.

## 7. 떠 있는 것

- 일회용 Docker DB `cfp-verify-pg-1`(127.0.0.1:55439)이 떠 있다. `scripts/verify_db.sh down`으로 내린다.
- 저장소 밖: `/tmp/cfp-rename.py`, `/tmp/cfp-rename-trial-*`, `/tmp/cfp-old-egg-info`(옛 설치 정보). 지워도 된다.
