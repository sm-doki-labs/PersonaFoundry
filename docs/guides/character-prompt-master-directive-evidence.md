# 캐릭터 공장 마스터 프롬프트 지시서 근거표

작성 2026-11-05, review-1·review-2 반영. 대상 본문: /Users/johnhuh619/projects/character-factory-poc/docs/guides/character-prompt-master-directive.md

입력 교훈: /Users/johnhuh619/projects/character-factory-poc/work/master-directive/ 의 다섯 묶음(S 19개, A1 68개, A2 69개, B 62개, C 79개, 합계 297개). 검토: /Users/johnhuh619/projects/character-factory-poc/work/master-directive/review-1.md, review-2.md. 출력 계약은 /Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/contracts/ 의 planning.py, persona.py, formation.py, choice_design.py를 읽었다. 작성 중 모델 호출은 하지 않았고 현재 지시문, 조립 코드, 서비스 프레임은 읽기만 했다.

## 1. 읽는 법

- 2절의 두 표는 본문과 교훈 파일을 기계로 대조해 만들었다. 본문 규칙 114개의 대괄호를 읽어 규칙별 근거를 만들고, 교훈 파일의 근거 칸과 강도 칸을 읽어 교훈별 원천 경로와 강도를 옮겼다. 본문을 고치면 두 표를 다시 만든다.
- 강도 표기는 교훈 묶음의 표기를 따른다: 실측 대조로 확인, 여러 번 반복 관측, 한 번 관측, 가설·제안, 나중에 뒤집힘. S 묶음에는 실측 확인, 반복 관측, 코드·자료 확인 표기도 있다.
- 충돌은 세 기준을 순서대로 적용해 정했다. 첫째, 실측 대조로 확인된 쪽을 따른다. 둘째, 같은 강도라면 최근 기록(2026-11-04~05 실측 S 묶음, 서비스 현행 프레임 v40과 관계 설정 v3)을 따른다. 셋째, 현행 서비스 프레임(영상통화 구어, 3문장 상한, 소유자 분리)과 맞는 쪽을 따른다. 뒤집힌 교훈은 대체한 쪽만 본문에 넣었다.
- 학습 데이터 전용 교훈은 대화 프롬프트, 생성 지시문, 평가 설계로 옮길 수 있는 부분만 반영했다. 서운함 결말 경로(C-25), 약속 재확인 비율(C-58), 장기 대화 반복(B-32)은 데이터 비율 대신 대화 규칙과 시험 설계로 옮겼다.
- review-1 반영으로 6절 규칙 번호가 바뀌었다(구 6.1~6.19 → 신 6.1~6.23, 대응은 검토 반영 기록 (review-1) 절 끝). 0절에 MD-0.4~0.6이 생겼고, 4절 소절 이름은 4.A 용어집, 4.B 칸 작성 규칙으로 바뀌었다. 나머지 절의 규칙 번호는 그대로다. review-2 반영에서는 MD-0.7만 새로 생겼고 번호는 바뀌지 않았다. 본문의 계약 변경 필요 표시는 7절 목록과 짝을 이룬다.

## 2. 규칙과 근거

### 2.1 규칙별 근거와 강도

가장 강한 근거 강도 열은 인용한 교훈 가운데 가장 강한 강도이고 괄호는 강도별 교훈 수다(실측: 실측 대조로 확인·실측 확인, 반복: 여러 번 반복 관측·반복 관측, 자료: 코드·자료 확인, 한번: 한 번 관측, 가설: 가설·제안, 뒤집힘: 나중에 뒤집힘). 핵심 구절 강도 열은 규칙의 핵심 구절이 가장 강한 근거보다 약한 근거나 계약 대조 같은 판단에 기대는 경우를 적었다(review-1 P2-14). 비어 있으면 핵심 구절도 가장 강한 근거와 같은 수준이다. 각 교훈의 원천 경로는 2.2에 있다.

| 규칙 | 근거 교훈 | 가장 강한 근거 강도 | 핵심 구절 강도 |
|---|---|---|---|
| MD-0.1 | B-46, S-12 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-0.2 | S-15, A2-44 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-0.3 | A2-68, B-62 | 여러 번 반복 관측 (반복2) |  |
| MD-0.4 | S-15, A2-44 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-0.5 | B-60, C-73, A1-67 | 여러 번 반복 관측 (반복3) |  |
| MD-0.6 | A1-33, A2-41, B-48, S-11 | 실측 대조로 확인 (실측3·가설1) | 공유 프레임 동기화 구절: S-11은 공장 규칙에서만 시험(서비스 프레임 미시험). 비교 의무는 A1-33·A2-41 실측 |
| MD-0.7 | B-46, A2-40, B-35 | 여러 번 반복 관측 (반복2·한번1) | 출력 계약과 발췌 규칙의 대응은 review-2 P1-3의 계약 대조에서 나온 운영 규칙이며 대조 실험은 없음 |
| MD-1.1 | C-01, B-38, A2-13, A1-02, B-37, C-22 | 실측 대조로 확인 (실측1·반복4·한번1) |  |
| MD-1.2 | S-1, S-2, A1-39, A2-35, A2-36, B-01, C-34, C-35 | 실측 대조로 확인 (실측1·반복5·한번1·가설1) |  |
| MD-1.3 | A1-39, B-03, B-04, B-08, B-09, C-36 | 실측 대조로 확인 (실측1·반복2·한번2·가설1) |  |
| MD-1.4 | A1-28, A2-39, S-18, A1-22, A1-29, C-54 | 여러 번 반복 관측 (반복3·자료1·한번1·가설1) |  |
| MD-1.5 | C-21, B-07, B-11, C-38, A2-17, B-06 | 여러 번 반복 관측 (반복2·한번1·가설3) |  |
| MD-1.6 | S-9, B-15, C-43 | 여러 번 반복 관측 (반복1·가설2) |  |
| MD-1.7 | S-5, S-6 | 여러 번 반복 관측 (반복1·한번1) | 관찰을 보조 단서로 두는 구절: S-5 한 번 관측(검증 대기) |
| MD-1.8 | S-6, A1-06, A1-55, A2-55, C-16 | 여러 번 반복 관측 (반복2·가설2·뒤집힘1) |  |
| MD-1.9 | A2-04, A2-05, B-47, C-70 | 여러 번 반복 관측 (반복3·가설1) |  |
| MD-2.1 | B-40, A2-17, C-21 | 여러 번 반복 관측 (반복1·한번1·가설1) |  |
| MD-2.2 | A1-01, A2-10, A1-17, A2-20, A2-21, B-40 | 여러 번 반복 관측 (반복2·한번2·가설1·뒤집힘1) | 인과 묶음을 먼저 정하는 순서는 A1-01·A2-10 반복 관측. 핵심 긴장 네 부분 구조는 A1-17·A2-20 한 번 관측(검증 대기). 칸 지정은 계약 대조에 따른 임시 처리 |
| MD-2.3 | S-2, B-01, B-34, B-37 | 여러 번 반복 관측 (반복2·한번2) |  |
| MD-2.4 | S-8, S-19, C-03, C-09, C-10, A1-02 | 반복 관측 (반복4·한번2) |  |
| MD-2.5 | S-19, A1-03, A2-12, A1-15 | 반복 관측 (반복4) |  |
| MD-2.6 | A1-04, A2-16, B-43, A2-22, A2-38, C-14, C-15 | 여러 번 반복 관측 (반복3·한번2·가설2) |  |
| MD-2.7 | A1-05, A2-18, B-44, A1-07 | 가설·제안 (가설4) |  |
| MD-2.8 | S-4, S-3, S-6, B-14 | 실측 대조로 확인 (실측2·반복2) | 기획 초안 말투 요약을 등급 이름과 기능 서술로 한정하는 구절은 review-1 P1-2의 조립 정합 판단. 등급 하나 원칙은 S-4·S-3 실측 |
| MD-2.9 | B-46, B-22, B-09, S-1, C-34 | 여러 번 반복 관측 (반복3·한번2) |  |
| MD-2.10 | S-14, B-41 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-2.11 | A1-11, A2-34 | 한 번 관측 (한번1·가설1) |  |
| MD-3.1 | A1-18, A2-19, A1-60 | 실측 대조로 확인 (실측3) |  |
| MD-3.2 | B-39, C-03, C-04, A1-12, A1-20, A2-06, A2-11, C-02, S-7 | 여러 번 반복 관측 (반복5·한번3·가설1) | 필수 항목 중 비적용 경우는 A1-20 반복 관측, 한 줄 조립은 S-7 한 번 관측. 검토용 칸(가치, 비용, 잘못된 변형)은 B-39 가설·제안, 형성 첫 통과 0/4(검증 대기) |
| MD-3.3 | A1-02, A1-47, A2-52, A2-56 | 여러 번 반복 관측 (반복3·한번1) | 대화 종료를 기본값으로 두지 않는 구절은 A2-56 반복 관측 |
| MD-3.4 | A1-12, A1-13, S-19 | 여러 번 반복 관측 (반복3) |  |
| MD-3.5 | A1-14, A2-15, A1-47 | 여러 번 반복 관측 (반복3) |  |
| MD-3.6 | A2-02, A2-57, S-19, S-5 | 반복 관측 (반복1·한번3) |  |
| MD-3.7 | S-7, C-61, C-04 | 한 번 관측 (한번3) |  |
| MD-3.8 | C-05, C-07, B-51, A2-03, A1-19, A1-31, B-23, C-06 | 실측 대조로 확인 (실측4·반복1·한번2·가설1) |  |
| MD-3.9 | S-10 | 여러 번 반복 관측 (반복1) |  |
| MD-3.10 | B-22, A2-56, A2-32, C-13, A1-15 | 실측 대조로 확인 (실측1·반복4) |  |
| MD-3.11 | C-11, C-12 | 실측 대조로 확인 (실측1·반복1) |  |
| MD-3.12 | B-43, B-23, A2-56 | 실측 대조로 확인 (실측1·반복1·한번1) |  |
| MD-3.13 | A1-16, A2-14, C-22, A2-08, A1-23, A2-24 | 실측 대조로 확인 (실측1·반복4·한번1) |  |
| MD-3.14 | C-66, A1-44 | 여러 번 반복 관측 (반복1·한번1) | 끝부분 경향 구절은 C-66 한 번 관측(검증 대기) |
| MD-3.15 | B-35, A1-58, A1-21, A2-29 | 실측 대조로 확인 (실측1·반복1·한번1·가설1) |  |
| MD-4.1 | S-3, S-18, A1-22, A2-23, B-14 | 실측 대조로 확인 (실측1·반복2·자료1·한번1) |  |
| MD-4.2 | A1-23, A2-24, A1-24, C-42, C-40, S-1 | 여러 번 반복 관측 (반복4·한번1·가설1) | 혼용 범위(해라체·주체높임 제외)는 표준 문법과 C-40에 따른 정의 정리이며 실측 대조 없음. 허용 예외는 C-42 반복 관측 |
| MD-4.3 | B-13, A2-26, C-39, C-41, C-02, S-1, A1-22, B-30 | 여러 번 반복 관측 (반복4·한번2·가설2) | 말버릇 다섯 칸 대응은 계약 대조에 따른 임시 처리(계약 변경 필요). 항목 자체는 B-13·A2-26·C-39 |
| MD-4.4 | A1-27, A2-26, C-14, A2-38 | 여러 번 반복 관측 (반복2·한번1·가설1) |  |
| MD-4.5 | A1-43, A2-30, C-53 | 실측 대조로 확인 (실측1·뒤집힘2) |  |
| MD-4.6 | C-45, S-16, A1-27 | 여러 번 반복 관측 (반복2·한번1) |  |
| MD-4.7 | S-3, C-40, C-44 | 실측 대조로 확인 (실측1·반복1·뒤집힘1) | 종결을 기능으로 쓰는 방식은 3절 충돌 3번의 해결로 만든 규칙이며 직접 대조 없음(검증 대기). S-3 실측은 등급 소유 분리에 대한 것 |
| MD-4.8 | C-56, A2-50, C-50, C-62 | 실측 대조로 확인 (실측1·반복3) |  |
| MD-4.9 | C-44, C-64 | 한 번 관측 (한번1·뒤집힘1) |  |
| MD-4.10 | A1-25, A2-28, C-47, C-48, C-49, C-42 | 실측 대조로 확인 (실측1·반복4·가설1) |  |
| MD-4.11 | C-51, B-16, C-24 | 여러 번 반복 관측 (반복3) |  |
| MD-4.12 | S-16, C-46 | 한 번 관측 (한번2) | 운율을 구조로 쓰는 구절은 S-16 한 번 관측(가설)(검증 대기) |
| MD-4.13 | A2-27, A2-32, A1-22 | 실측 대조로 확인 (실측1·반복1·한번1) |  |
| MD-4.14 | A1-30, A2-27, S-15 | 실측 대조로 확인 (실측1·한번2) |  |
| MD-4.15 | C-54, A1-29, A1-25 | 실측 대조로 확인 (실측1·반복1·가설1) |  |
| MD-5.1 | C-28, C-30, A1-33, B-45, B-42 | 실측 대조로 확인 (실측2·한번3) |  |
| MD-5.2 | B-46, B-21, B-62 | 실측 대조로 확인 (실측1·반복1·한번1) |  |
| MD-5.3 | S-7, B-04, A1-19, B-39 | 한 번 관측 (한번3·가설1) |  |
| MD-5.4 | S-1, A2-35, B-04, B-05, A1-31, A1-32, A2-21, C-32, A2-44, A1-40, A2-37, C-28, B-10, C-30, A2-47, A1-60, S-15 | 실측 대조로 확인 (실측6·반복3·한번4·뒤집힘4) | 가짜 수락 턴·프리필 구절은 A1-40 실측 대조(이점 없음)이며 모든 프리필이 무효라는 뜻은 아니어서 조건부로 씀 |
| MD-5.5 | S-18, A1-23, A1-36, A1-37, A1-41, A2-33, B-45, C-42 | 실측 대조로 확인 (실측1·반복1·자료1·한번4·가설1) |  |
| MD-5.6 | A1-34, A1-35, A2-42, A2-43, A1-15 | 실측 대조로 확인 (실측2·반복2·한번1) |  |
| MD-5.7 | A1-36, A1-37, A1-38, A2-46, A2-08 | 실측 대조로 확인 (실측1·한번1·가설1·뒤집힘2) |  |
| MD-5.8 | C-29, A2-43 | 실측 대조로 확인 (실측1·반복1) |  |
| MD-5.9 | A1-33, A2-41, A1-43, S-5 | 실측 대조로 확인 (실측3·한번1) |  |
| MD-5.10 | A2-45, A1-51 | 여러 번 반복 관측 (반복1·가설1) |  |
| MD-5.11 | A2-31, A2-25, A1-27, A1-56 | 여러 번 반복 관측 (반복3·한번1) |  |
| MD-5.12 | A2-40, A2-48, A1-61, A2-09 | 실측 대조로 확인 (실측2·반복1·한번1) |  |
| MD-6.1 | C-67, A1-46, S-9 | 여러 번 반복 관측 (반복2·가설1) |  |
| MD-6.2 | S-6, C-18 | 여러 번 반복 관측 (반복2) |  |
| MD-6.3 | S-11, C-16, B-25, A1-49, A2-55 | 실측 확인 (실측1·반복3·뒤집힘1) | 기록과 대조해 틀린 주장을 받지 않는 구절은 S-11 실측 확인 |
| MD-6.4 | A1-06, A1-55, A2-61 | 한 번 관측 (한번1·가설2) |  |
| MD-6.5 | A1-46, B-20, A2-49 | 여러 번 반복 관측 (반복3) |  |
| MD-6.6 | A1-44, B-30, C-57, A1-32, A1-45 | 실측 대조로 확인 (실측1·반복3·뒤집힘1) |  |
| MD-6.7 | A1-43, A2-59, C-53, A1-42 | 실측 대조로 확인 (실측2·뒤집힘2) |  |
| MD-6.8 | A2-53, C-56, S-10 | 실측 대조로 확인 (실측1·반복2) |  |
| MD-6.9 | A1-52, A1-20 | 여러 번 반복 관측 (반복2) |  |
| MD-6.10 | C-16, B-26, C-17, A1-49 | 여러 번 반복 관측 (반복3·뒤집힘1) |  |
| MD-6.11 | C-16, C-19, A1-49, S-11 | 실측 확인 (실측1·반복2·뒤집힘1) | 기록이 다루지 않는 과거 주장 처리는 이 경우를 직접 시험한 교훈이 없고 제품 판단이 필요함(검증 대기) |
| MD-6.12 | B-27, C-20 | 여러 번 반복 관측 (반복2) |  |
| MD-6.13 | C-18, A2-54, B-28 | 여러 번 반복 관측 (반복3) |  |
| MD-6.14 | A1-47, A2-52 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-6.15 | A2-51, B-29, C-25, A1-48, A1-47 | 실측 대조로 확인 (실측1·반복3·한번1) | 자기비난을 결함인 인물에 한정한 구절은 A1-48 한 번 관측. 동반 사과 금지와 반응을 맡기는 구절은 C-25 실측·B-29 반복 |
| MD-6.16 | A2-50, A2-49, A2-58 | 실측 대조로 확인 (실측1·반복1·한번1) |  |
| MD-6.17 | C-25, B-33, C-59 | 실측 대조로 확인 (실측1·반복2) |  |
| MD-6.18 | C-23, C-65, C-24, A2-61 | 여러 번 반복 관측 (반복2·한번2) |  |
| MD-6.19 | A1-53, A2-62 | 여러 번 반복 관측 (반복1·한번1) |  |
| MD-6.20 | B-31, C-58, C-60 | 실측 대조로 확인 (실측2·반복1) |  |
| MD-6.21 | A1-27, C-62, C-45, C-63 | 여러 번 반복 관측 (반복3·한번1) | 호칭과 말버릇을 정해진 소유자에 맡기는 구절은 A1-27 반복 관측과 MD-1.4 소유 원칙 |
| MD-6.22 | A1-50, A1-54, A2-61 | 여러 번 반복 관측 (반복1·한번1·가설1) |  |
| MD-6.23 | A2-25 | 여러 번 반복 관측 (반복1) |  |
| MD-7.1 | S-2, B-01, B-02, A2-36, B-52, A1-29 | 여러 번 반복 관측 (반복2·한번1·가설3) |  |
| MD-7.2 | A2-01, A2-02, C-70, S-19 | 실측 대조로 확인 (실측1·반복2·한번1) |  |
| MD-7.3 | A1-58, A2-07 | 한 번 관측 (한번2) |  |
| MD-7.4 | B-46, B-50 | 한 번 관측 (한번1·가설1) |  |
| MD-7.5 | B-18, C-68 | 여러 번 반복 관측 (반복2) |  |
| MD-7.6 | C-69, C-72, C-49, A1-45, B-19, C-47 | 실측 대조로 확인 (실측2·반복3·한번1) |  |
| MD-7.7 | S-15, A1-46, A2-44 | 여러 번 반복 관측 (반복2·한번1) |  |
| MD-7.8 | S-12, B-50, A1-57, A2-64, C-34, A2-25 | 여러 번 반복 관측 (반복5·가설1) |  |
| MD-7.9 | B-49, C-75, C-71 | 여러 번 반복 관측 (반복2·가설1) |  |
| MD-7.10 | S-13, B-50, A1-67 | 여러 번 반복 관측 (반복1·한번1·가설1) | 모델 우열 판단은 S-13 한 번 관측과 B-50 가설뿐이라 규칙은 자동 대체 금지와 명시만 정함 |
| MD-7.11 | B-60, C-73, B-12 | 여러 번 반복 관측 (반복2·가설1) |  |
| MD-7.12 | B-53 | 한 번 관측 (한번1) |  |
| MD-9.1 | B-54, C-10, C-75, B-37, A2-13, C-08, A1-62, A2-64 | 실측 대조로 확인 (실측1·반복3·한번3·가설1) |  |
| MD-9.2 | S-17, A1-66, B-36, A2-65, A1-59 | 실측 대조로 확인 (실측1·반복1·한번2·가설1) |  |
| MD-9.3 | A1-65, A2-65, C-76, B-58, A2-66, B-36, C-75 | 실측 대조로 확인 (실측3·반복3·가설1) |  |
| MD-9.4 | A1-63, A2-67, C-77, B-59, B-29, C-78 | 실측 대조로 확인 (실측1·반복4·가설1) |  |
| MD-9.5 | C-75, B-49, B-57, A2-68 | 여러 번 반복 관측 (반복3·가설1) |  |
| MD-9.6 | A1-64, B-56, C-79, C-33, C-59, B-32, A2-63 | 실측 대조로 확인 (실측3·반복3·가설1) |  |
| MD-9.7 | A2-69, B-24, C-74, B-59, B-56, C-26 | 실측 대조로 확인 (실측1·반복1·한번1·가설3) |  |
| MD-9.8 | A1-67, B-55, C-75, C-31 | 실측 대조로 확인 (실측1·반복3) |  |
| MD-9.9 | A1-42, B-17, C-52, C-45, A2-60, A1-56, A2-25, A2-38 | 실측 대조로 확인 (실측1·반복6·뒤집힘1) |  |
| MD-9.10 | A1-68, A2-68, B-62, B-19 | 여러 번 반복 관측 (반복3·한번1) |  |

### 2.2 교훈별 원천 경로와 강도

원천 경로는 각 교훈의 근거 칸에 적힌 경로를 파일 단위로 최대 세 개 옮겼다. 접두어 rqc:는 /Users/johnhuh619/projects/relationship-quest-chat/, cfp:는 /Users/johnhuh619/projects/character-factory-poc/, gsp:는 /Users/johnhuh619/projects/gemini-sft-poc/, gem:은 /Users/johnhuh619/Documents/Codex/2026-10-14/gem/, mem:은 /Users/johnhuh619/.codex/memories/ 를 뜻한다. S 묶음의 경로는 character-factory-poc 저장소 기준 상대 경로이며, 경로 대신 상태 기록 번호만 적힌 교훈은 근거 문장을 옮겼다. @stash749471c3 표기는 A2 묶음이 쓴 git stash 판 표기다. 강도는 교훈의 강도 칸을 90자까지 옮겼다.

| 교훈 | 제목 | 원천 경로 | 강도 | 반영 규칙 |
|---|---|---|---|---|
| S-1 | 대화 프롬프트 안의 인용 대사는 그대로 복제된다 | cfp:runs/characters/cf-20261105-api-cost-argon-v2/s8-prompts/pv1/long.md:54<br>runs/experiments/20261105-argon-video/argon-2/responses.json<br>runs/characters/cf-20261104-api-cost-v4/s8-prompts/pv1/long.md:51<br>외 2개 파일 | 여러 번 반복 관측 | MD-1.2, MD-2.9, MD-4.2, MD-4.3, MD-5.4 |
| S-2 | 생성 지시문 속 예시는 모든 캐릭터의 후보를 같은 틀로 만든다 | src/character_factory_poc/prompts/plan_variants.md:17<br>docs/reports/2026-10-29-persona-choice-cause-analysis.md | 여러 번 반복 관측(예시 제거 대조 실험은 아직 없음) | MD-1.2, MD-2.3, MD-7.1 |
| S-3 | 말버릇 칸이 종결어미를 정하면 청자 대우법이 흔들린다 | runs/experiments/20261105-k0073-video/summary.json<br>src/character_factory_poc/stages/s7_traits/check.py | 실측 대조로 확인 | MD-2.8, MD-4.1, MD-4.7 |
| S-4 | 말투 확정 단계는 상대높임 등급을 섞는다 | runs/experiments/20261105-argon-voice-replay-b/results.json<br>runs/characters/cf-20261105-api-cost-argon-v2/s3-plan/pr1/deck-voice/output.json | 실측 대조로 확인(1회) | MD-2.8 |
| S-5 | 관찰 단서를 성격의 중심으로 쓰게 하면 상대의 말보다 카메라를 앞세운다 | 근거 기록: 이전 지시문 다섯 곳의 관찰 문장 → v4 시트가 말보다 화면 행동을 먼저 본다고 정함. 수정 뒤 v6 시트는 말을 출발점으로 둠(D-0085). 영상통화 시험 관찰 언급 0~1/13. | 한 번 관측(대조 전후) | MD-1.7, MD-3.6, MD-5.9 |
| S-6 | 영상통화의 외모·몸 상태 넘겨짚기 | 근거 기록: K-0070(하진우 13응답 중 7건), D-0082 뒤 v3·v6·argon-v2 외모 언급 0. Flash 말투 단계는 브리프 문장을 지우고 태도를 잃음(K-0075), Argon+수정 지시문은 소리 단서로 바꿔 태도 유지. | 여러 번 반복 관측 | MD-1.7, MD-1.8, MD-2.8, MD-6.2 |
| S-7 | 조립에서 상황이 빠지면 조건 없는 행동이 된다 | 근거 기록: v4 pv1 CHOICES의 dilemma 누락·'..'(K-0073), D-0085 _choice_lines. | 한 번 관측 | MD-3.2, MD-3.7, MD-5.3 |
| S-8 | 판단 상황은 대화에서 실제로 생기는 일로 쓴다 | 근거 기록: v4 시트의 '~할 것인지의 충돌' 상황 → 조립 시 언제 하는 행동인지 흐림. 지시문 수정 뒤 v6·argon-v2는 관찰 가능한 계기로 씀. | 한 번 관측 | MD-2.4 |
| S-9 | 공통 규칙은 서비스 채널(영상통화의 구어)에 맞춘다 | 근거 기록: actor-system-rules-v1의 문자 대화 문구(D-0085로 v2). 시험의 글자 표현 0. | 가설·제안(채널 차이 효과 대조 없음) | MD-1.6, MD-6.1 |
| S-10 | 한 칸의 '가끔' 지시는 과잉 적용된다 | 근거 기록: v6 시트 질문 칸 → 페르소나 효과 대조에서 끼니 언급 9/20, 영상통화 시험 3·2/13(K-0074). argon-v2 4·2/13. | 여러 번 반복 관측 | MD-3.9, MD-6.8 |
| S-11 | 사용자가 주장한 공동 기억을 받아들인다 | runs/experiments/20261105-persona-lift/*/results.json | 실측 확인(서비스 프레임 미시험) | MD-0.6, MD-6.3, MD-6.11 |
| S-12 | 생성 단계 사이의 다른 모델 검토 → 수정 고리는 품질보다 정지를 늘렸다 | 근거 기록: K-0072(v4 네 번 다른 이유로 정지), Argon 첫 실행 재검토 정지, D-0086 뒤 같은 브리프 한 번에 G6. | 여러 번 반복 관측 | MD-0.1, MD-7.8 |
| S-13 | 최종 말투·성격 확정은 상위 모델이 낫다(1회 관측) | runs/experiments/20261105-argon-video/summary.json | 한 번 관측(서로 다른 기획으로 비교, 같은 기획 대조 없음) | MD-7.10 |
| S-14 | 자동 후보 선택은 가장 무난한 후보로 기운다 | 근거 기록: --auto-approve G3가 v2·v3·v4·argon-v2 모두 v1 선택. v4는 브리프 직설에 가까운 v2, argon-v2는 대비가 강한 v3를 버림. | 여러 번 반복 관측 | MD-2.10 |
| S-15 | 생성 지시문 문장이 산출물 칸으로 새어 든다 | runs/characters/cf-20261105-api-cost-argon-v2/s8-prompts/pv1/long.md | 한 번 관측 | MD-0.2, MD-0.4, MD-4.14, MD-5.4, MD-7.7 |
| S-16 | 운율 기술이 문장부호 버릇으로 번역된다 | 근거 기록: argon-v2 '반 박자 쉬어 반응' 기술 → 응답 대부분이 말줄임표로 시작(K-0075 갱신). | 한 번 관측(가설) | MD-4.6, MD-4.12 |
| S-17 | 판정자에게 설정 원문을 주면 설정 소재 재현을 캐릭터성으로 판단한다 | runs/experiments/20261105-persona-lift/*/results.json | 한 번 관측 | MD-9.2 |
| S-18 | 관계·말높임은 페르소나가 아니라 관계 설정이 소유한다 | data/relationship_profiles/han-somin-video-call-r6.json | 코드·자료 확인 | MD-1.4, MD-4.1, MD-5.5 |
| S-19 | 서비스 페르소나는 칸마다 동기·오독·결함을 담는다 | 근거 기록: 서비스 v6(박세라 r14·한소민 r11)의 READING_AND_TENSION·CHOICES 구조와 한도윤 v6 비교. 페르소나 효과 대조에서 위로·사과·축하 응답은 최소 프롬프트와 거의 같음. | 반복 관측(구조 비교 + 1회 대조) | MD-2.4, MD-2.5, MD-3.4, MD-3.6, MD-7.2 |
| A1-01 | 표면보다 압력 아래의 선택을 먼저 설계한다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:76-88<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:540 | 여러 번 반복 관측(여러 제작 차수에서 정착한 절차이며, 효과를 대조한 수치는 문서에 없다) | MD-2.2 |
| A1-02 | 같은 압력을 넣었을 때 다른 선택이 나오는지로 캐릭터 중복을 판정한다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:460-473<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:45-46 | 여러 번 반복 관측 | MD-1.1, MD-2.4, MD-3.3 |
| A1-03 | 포트폴리오가 쉽게 수렴하는 순한 원형을 금지 목록으로 먼저 둔다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:391-406 | 여러 번 반복 관측 | MD-2.5 |
| A1-04 | 피해 행동을 지워도 남는 매력과 사용자 없이 굴러가는 생활이 있어야 한다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:519-525<br>rqc:docs/character-authoring/persona-decision-model-v1.md:13<br>rqc:data/personas/han-somin-r11.json:20-28 | 가설·제안(품질 관문으로 정의했으며 대조 수치는 없다) | MD-2.6 |
| A1-05 | 심리 이론과 유형 라벨은 해석 렌즈로만 쓰고 캐릭터 시트에 넣지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:153-160<br>rqc:docs/character-authoring/persona-decision-model-v1.md:14 | 가설·제안(연구 대조에 근거한 저작 판단) | MD-2.7 |
| A1-06 | 안전 금지선은 고정하고 문화에 민감한 행동을 결함으로 코딩하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1161-1173<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:81<br>rqc:data/personas/han-somin-r11.json:61-62 | 가설·제안 | MD-1.8, MD-6.4 |
| A1-07 | 관계를 확인하는 장치로 숨은 시험을 쓰지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:680-698 | 가설·제안 | MD-2.7 |
| A1-08 | 실존 인물은 저작 전에 어떤 결함을 상품에 넣을지 서면으로 합의한다 | rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:21-27 | 가설·제안(설문 설계 문서이며 시행 결과는 보고되지 않았다) | 채택하지 않음(4.1) |
| A1-09 | 실존 인물의 인과는 자기 진단이 아니라 사건 회상에서 추출하고, 사각지대는 주변인에게서 얻는다 | rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:51-53 | 가설·제안 | 채택하지 않음(4.1) |
| A1-10 | 실존 인물의 사실마다 출처·제3자 포함·공개 등급을 붙이고, 본인 여부 질문의 답을 미리 정한다 | rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:34-36 | 가설·제안 | 채택하지 않음(4.1) |
| A1-11 | 다른 언어 판은 번역하지 않고 같은 구조로 그 언어에서 새로 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:263-269<br>rqc:docs/content/prompt-authoring-guide.md:159-162 | 가설·제안 | MD-2.11 |
| A1-12 | 결함은 관찰 가능한 동사와 그 동사가 가져가는 권리로 쓴다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:90-101<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:67<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:27-43<br>외 1개 파일 | 여러 번 반복 관측 | MD-3.2, MD-3.4 |
| A1-13 | 결함에는 반복되는 이유와 실제 피해를 함께 둔다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:103-113<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:478-479 | 여러 번 반복 관측 | MD-3.4 |
| A1-14 | 수습은 사과문이 아니라 가져간 권리를 돌려주고 자기 비용을 치르는 행동이다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:115-123<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:264-269<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:113<br>외 1개 파일 | 여러 번 반복 관측(설계 원칙이며 효과 수치는 없다) | MD-3.5 |
| A1-15 | 결함을 금지 문장이나 순화로 지워 무해화하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:125-134<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:21-27<br>rqc:data/relationship_profiles/han-somin-video-call-r6.json:10<br>외 1개 파일 | 여러 번 반복 관측 | MD-2.5, MD-3.10, MD-5.6 |
| A1-16 | 관계가 가까워져도 성격·결함·목소리는 치료되지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:136-151<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:140-173<br>rqc:docs/character-authoring/persona-decision-model-v1.md:33<br>외 1개 파일 | 여러 번 반복 관측(STAYS/CHANGES/NOT YET 형식 자체는 가설·제안이며, 현행 관계 설정 v3에는 이 칸이 없다) | MD-3.13 |
| A1-17 | 핵심 긴장 하나를 먼저 한 문단으로 쓰고 욕구·두려움·해석 습관을 그 변형으로 묶는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1030-1038<br>rqc:docs/content/prompt-authoring-guide.md:125<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:212-213<br>외 1개 파일 | 한 번 관측(단일 캐릭터에서 두 차례 연속 통과) | MD-2.2 |
| A1-18 | 해석·선택·발화를 서로 다른 칸에 나눠 쓴다 | rqc:docs/character-authoring/persona-decision-model-v1.md:9-33 | 실측 대조로 확인(여덟 칸 전체 묶음의 효과. 4/5/6 구분 단독 효과는 가설) | MD-3.1 |
| A1-19 | 선택 문장 하나가 한 턴의 말투를 통째로 끌고 간다 — 조건을 좁게 쓴다 | rqc:docs/content/prompt-authoring-guide.md:129-131<br>rqc:docs/character-authoring/persona-decision-model-v1.md:72<br>rqc:data/prompt_frames/split-frame-r5-v40.json:53 | 한 번 관측(K60 사례) | MD-3.8, MD-5.3 |
| A1-20 | 발동 조건에는 발동하지 않는 경우도 함께 쓰고, 같은 턴에 판정 가능하게 쓴다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:294-297<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:33-34<br>rqc:docs/runbooks/agent-character-onboarding.md:115 | 여러 번 반복 관측(두 캐릭터의 개별 관측) | MD-3.2, MD-6.9 |
| A1-21 | 해석·선택 칸의 심리·언어학 개념어는 설명 어휘로만 쓴다 | rqc:docs/character-authoring/persona-decision-model-v1.md:52<br>rqc:docs/content/prompt-authoring-guide.md:125-128<br>rqc:data/personas/han-somin-r11.json:39-49 | 가설·제안(사용자 결정으로 채택했으며 품질 효과는 미확인) | MD-3.15 |
| A1-22 | 개인어와 청자 대우법을 다른 층에 둔다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1060-1076<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:48-57<br>rqc:docs/content/prompt-authoring-guide.md:134-136<br>외 4개 파일 | 한 번 관측(단일 캐릭터 전후 비교) 뒤 현행 스키마·프레임의 기본 구조로 채택 | MD-1.4, MD-4.1, MD-4.3, MD-4.13 |
| A1-23 | 말높임 흔들림 — 말높임은 관계 진전의 보상이 아니다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:148-151<br>rqc:data/prompt_frames/split-frame-r5-v40.json:70<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:364-365<br>외 2개 파일 | 한 번 관측(단일 캐릭터 수정 전후) | MD-3.13, MD-4.2, MD-5.5 |
| A1-24 | 존댓말은 복종이 아니고, 반말 자체는 무례의 근거가 아니다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:56<br>rqc:data/prompt_frames/split-frame-r5-v40.json:16<br>rqc:docs/content/prompt-authoring-guide.md:136 | 가설·제안(규칙으로 명문화했으며 별도 수치는 없다) | MD-4.2 |
| A1-25 | 구어 특징은 정확한 용어로 지시하되, 쓸 조건과 함께 허용 목록으로 둔다 | rqc:data/prompt_frames/split-frame-r5-v40.json:11<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:59-60<br>rqc:docs/runbooks/agent-character-onboarding.md:130<br>외 1개 파일 | 실측 대조로 확인(용어 지시의 추가 이점은 확인되지 않았다는 결과) | MD-4.10, MD-4.15 |
| A1-26 | 실존 인물의 말투는 자기 설명이 아니라 여러 감정 상태의 녹음에서 뽑는다 | rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:285-286 | 가설·제안 | 채택하지 않음(4.1) |
| A1-27 | 같은 시작말·호칭·질문·마무리와 대표 말버릇을 반복하지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:11<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:50-52<br>rqc:docs/runbooks/agent-character-onboarding.md:131<br>외 1개 파일 | 여러 번 반복 관측 | MD-4.4, MD-4.6, MD-5.11, MD-6.21 |
| A1-28 | 한 규칙에는 소유자를 하나만 둔다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:13-25<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:26-32<br>rqc:docs/content/prompt-authoring-guide.md:39-45<br>외 3개 파일 | 여러 번 반복 관측 | MD-1.4 |
| A1-29 | 공유 프레임에는 특정 인물의 말버릇이나 반응을 넣지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:21<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:302<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:280-281 | 가설·제안 | MD-1.4, MD-4.15, MD-7.1 |
| A1-30 | 매 턴 실리는 칸은 매 턴 작동하고, 말투 칸은 특히 강하게 작동한다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:273-275<br>rqc:docs/content/prompt-authoring-guide.md:135<br>rqc:data/prompt_frames/split-frame-r5-v40.json:16 | 한 번 관측 | MD-4.14 |
| A1-31 | 긴 행동 루프를 매 턴 주입하지 않는다 — 규칙 과잉 적용 | rqc:docs/character-authoring/persona-decision-model-v1.md:71<br>rqc:docs/content/prompt-authoring-guide.md:132-133<br>rqc:data/prompt_frames/split-frame-r5-v40.json:13<br>외 2개 파일 | 실측 대조로 확인 | MD-3.8, MD-5.4 |
| A1-32 | 한 턴에는 주된 반응 하나만 앞세운다(과거 루프 결정 순서에서 남은 부분) | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:262-297<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:102-107<br>rqc:docs/character-authoring/persona-decision-model-v1.md:37<br>외 1개 파일 | 나중에 뒤집힘(루프 주입·결정 순서·슬롯 카탈로그는 v6 페르소나와 v39·v40 프레임에서 wire에서 빠지고 선택 칸으로 대체되었다. 한 턴에 주된 반응 … | MD-5.4, MD-6.6 |
| A1-33 | 매 턴 블록에는 매 턴 바뀌는 것과 길이만 둔다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:214-224<br>rqc:data/prompt_frames/split-frame-r5-v40.json:22<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:46 | 실측 대조로 확인 | MD-0.6, MD-5.1, MD-5.9 |
| A1-34 | 캐릭터가 지금 이 자리에 있는 이유를 장면 사실에서 한 문장으로 준다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:226-230<br>rqc:data/prompt_frames/split-frame-r5-v40.json:57<br>rqc:data/relationship_profiles/han-somin-video-call-r6.json:23 | 한 번 관측 | MD-5.6 |
| A1-35 | 장면 사실과 어긋나는 상태 문장은 모델을 흔든다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:243-244<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1084-1092<br>rqc:docs/content/prompt-authoring-guide.md:137<br>외 2개 파일 | 여러 번 반복 관측(두 차수의 관측) | MD-5.6 |
| A1-36 | 지금 마음은 금지가 아니라 상태로, 경계가 풀리는 방향으로 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:206-212<br>rqc:docs/content/prompt-authoring-guide.md:138<br>rqc:data/relationship_profiles/han-somin-video-call-r6.json:25-27 | 한 번 관측(K32 사례). 구조는 관계 설정 v3로 채택 | MD-5.5, MD-5.7 |
| A1-37 | 깊은 사정은 금지로 막지 말고 믿게 되면 꺼낼 수 있는 이야기로 둔다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:247-252<br>rqc:docs/content/prompt-authoring-guide.md:138<br>rqc:data/relationship_profiles/han-somin-video-call-r6.json:28 | 가설·제안(이 칸 단독 효과의 수치는 문서에 없다) | MD-5.5, MD-5.7 |
| A1-38 | 공개는 범위만이 아니라 시점·선후·뒤처리까지 정한다(옛 공개 상한 방식) | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1098-1110<br>rqc:docs/character-authoring/real-person-licensed-character-intake-v1.md:55-66 | 나중에 뒤집힘(관계 설정 v3에서 고정 공개 상한이 지금 마음과 믿게 되면 꺼낼 이야기로 대체되었다. 결함보다 사정이 먼저 풀리면 무해화된다는 관측은 유효하다) | MD-5.7 |
| A1-39 | 정답 대사나 성공한 출력을 프롬프트에 붙이지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:127-131<br>rqc:docs/character-authoring/persona-decision-model-v1.md:18<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:69<br>외 2개 파일 | 가설·제안(여러 문서가 같은 규칙을 두지만, 예시를 넣은 경우와 뺀 경우를 대조한 수치는 이 묶음에 없다) | MD-1.2, MD-1.3 |
| A1-40 | 가짜 수락 턴·프리필은 비교 실험 없이 기본으로 넣지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:133-135<br>rqc:docs/content/prompt-authoring-guide.md:145<br>rqc:data/prompt_frames/split-frame-r5-v40.json:6-10 | 실측 대조로 확인(이점 없음. 모든 프리필 방식이 무효라는 뜻은 아니다) | MD-5.4 |
| A1-41 | 표현 변화는 고를 수 있는 성향 목록으로 쓰고, 고정 진행과 반복 문구를 뺀다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:784-801<br>rqc:data/prompt_frames/split-frame-r5-v40.json:86-87<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:389-393 | 실측 대조로 확인(단일 캐릭터 10회 실행) | MD-5.5 |
| A1-42 | 길이는 프롬프트 상한만으로 보장되지 않는다 — 후처리 호출을 기본으로 삼지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:113-125<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1118-1120<br>rqc:docs/content/prompt-authoring-guide.md:100-102 | 나중에 뒤집힘(문장 선택 후처리는 단일 provider 스트림으로 대체되어 실험 재현용으로 분리되었다. 상한만으로 보장되지 않는다는 관측은 유효하다) | MD-6.7, MD-9.9 |
| A1-43 | 한 턴은 대개 1~2문장으로 끝내고 분량 하한을 두지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:99-104<br>rqc:data/prompt_frames/split-frame-r5-v40.json:14<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1004<br>외 1개 파일 | 실측 대조로 확인(사람 평가는 수행하지 않았다). 120~250자 목표는 나중에 뒤집혔다 | MD-4.5, MD-5.9, MD-6.7 |
| A1-44 | 주된 화행 하나를 끝내면 턴을 넘긴다 — 질문 끝맺음과 화행 쌓기 | rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:105<br>rqc:docs/runbooks/agent-character-onboarding.md:129-130<br>외 1개 파일 | 여러 번 반복 관측(수치는 길이 지침과 묶여 있다, {G}:172-174) | MD-3.14, MD-6.6 |
| A1-45 | 짧게 만들어도 그 턴에 필요한 의미 요소는 남긴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:107-108<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1002 | 실측 대조로 확인(65개 문장 선택 검사에서 자유 재작성의 실패 관측) | MD-6.6, MD-7.6 |
| A1-46 | 상담사·작가·진행자 말투로 이탈하지 않고, 상대 기분을 수습하는 담당자가 되지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:80-81<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:44<br>외 1개 파일 | 여러 번 반복 관측 | MD-6.1, MD-6.5, MD-7.7 |
| A1-47 | 사과 과잉과 불만 접수식 응대 — 모욕·불평·정당한 항의를 구분한다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:83-95<br>rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/runbooks/agent-character-onboarding.md:137-138<br>외 3개 파일 | 여러 번 반복 관측 | MD-3.3, MD-3.5, MD-6.14, MD-6.15 |
| A1-48 | 자기비난·불안·사과를 반복하거나 증폭하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1004-1005<br>rqc:data/prompt_frames/split-frame-r5-v40.json:16 | 한 번 관측(단일 캐릭터 수정 전후) | MD-6.15 |
| A1-49 | 공동 기억을 날조하거나 상대의 외모·상태를 넘겨짚지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:22<br>rqc:docs/runbooks/agent-character-onboarding.md:133-134<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.3, MD-6.10, MD-6.11 |
| A1-50 | 이력이 비어 있어도 장면과 관계는 이미 있다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:62-67<br>rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/runbooks/agent-character-onboarding.md:133<br>외 1개 파일 | 여러 번 반복 관측 | MD-6.22 |
| A1-51 | 장기 대화 붕괴 — 과거 기록은 증거일 뿐 정본을 덮지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:25<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:44<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:159 | 여러 번 반복 관측(연구 근거와 진단 항목. 장기 턴 수 기준의 실측 결과는 이 묶음에 없다) | MD-5.10 |
| A1-52 | 사용자가 밝힌 경계는 그 턴에서 지킨다 | rqc:data/prompt_frames/split-frame-r5-v40.json:16<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:290-292<br>rqc:data/relationship_profiles/han-somin-video-call-r6.json:14<br>외 1개 파일 | 여러 번 반복 관측 | MD-6.9 |
| A1-53 | 사용자가 내릴 결론을 캐릭터가 먼저 확정하지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:15<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:43<br>rqc:docs/runbooks/agent-character-onboarding.md:199-201<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.19 |
| A1-54 | 정체성은 고정하고, 사용자의 자기 정정은 가장 최근 것을 따른다 | rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:155<br>rqc:docs/runbooks/agent-character-onboarding.md:195 | 가설·제안(진단 항목으로 정의했으며 결과 수치는 없다) | MD-6.22 |
| A1-55 | 혐오·노골 요구에는 정책 안내문 대신 캐릭터의 태도로 선을 긋고, 허용된 호감은 지우지 않는다 | rqc:data/prompt_frames/split-frame-r5-v40.json:5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:90-92<br>rqc:docs/runbooks/agent-character-onboarding.md:139-140<br>외 2개 파일 | 가설·제안(규칙이며 결과 수치는 없다) | MD-1.8, MD-6.4 |
| A1-56 | 고정 오프닝과 문맥 자산에 남은 이전 설정이 새어 나온다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:76-78<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:43<br>rqc:docs/runbooks/agent-character-onboarding.md:135-136<br>외 1개 파일 | 여러 번 반복 관측 | MD-5.11, MD-9.9 |
| A1-57 | 캐릭터 서술을 공통 템플릿 함수로 조립하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1195<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:242 | 여러 번 반복 관측(포트폴리오 감사에서 반복된 실패) | MD-7.8 |
| A1-58 | 지시문은 주어를 밝히고 한 문장에 한 사실만 둔다 — 대사에는 이 문서체를 적용하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1057-1058<br>rqc:docs/content/prompt-authoring-guide.md:127-128<br>rqc:data/personas/han-somin-r11.json:12-62<br>외 1개 파일 | 한 번 관측(단일 캐릭터 재구성의 일부로 통과) | MD-3.15, MD-7.3 |
| A1-59 | 판정 규칙은 서술형 대신 긍정·부정 쌍으로 쓰고 공통 정의보다 앞에 둔다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1123-1131<br>rqc:docs/content/prompt-authoring-guide.md:140 | 한 번 관측(단일 챕터 전후) | MD-9.2 |
| A1-60 | 속으로 먼저 생각하게 하는 별도 추론 단계를 기본으로 넣지 않는다 | rqc:docs/character-authoring/persona-decision-model-v1.md:7<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:221-223<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:311 | 실측 대조로 확인(블록 전체를 바꾼 비교이며 추론 지시 단독 효과는 아니다). 연구 근거도 함께 있다 | MD-3.1, MD-5.4 |
| A1-61 | 압축·근접 배치·윤문만으로는 생성 품질이 오르지 않는다 | rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:348-401<br>rqc:docs/character-authoring/persona-decision-model-v1.md:73<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:185 | 실측 대조로 확인 | MD-5.12 |
| A1-62 | 평가의 기대 결과는 정답 대사가 아니라 의미·허용 반응·실패 조건으로 적는다 | rqc:docs/content/prompt-authoring-guide.md:153-155<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:148-149 | 가설·제안 | MD-9.1 |
| A1-63 | 평가 축을 나누고 평균 점수로 치명 실패를 덮지 않는다 | rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:49<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:9-11<br>rqc:docs/character-authoring/persona-decision-model-v1.md:74<br>외 3개 파일 | 여러 번 반복 관측 | MD-9.4 |
| A1-64 | 실제 최종 발화를 다음 턴에 넣는 다중 턴 여정을 두 번 연속 통과해야 한다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:161-162<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:982-990<br>rqc:docs/runbooks/agent-character-onboarding.md:68-74<br>외 1개 파일 | 여러 번 반복 관측 | MD-9.6 |
| A1-65 | 최종 판정은 사람 블라인드로 하고 LLM 심사는 보조로만 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:257-261<br>rqc:docs/content/prompt-authoring-guide.md:164-170 | 실측 대조로 확인(LLM 심사와 사람 판정 일치율 57%) | MD-9.3 |
| A1-66 | 이름을 가린 시험과 행동이 대비되는 캐릭터를 함께 본다 | rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:45<br>rqc:docs/character-authoring/persona-decision-model-v1.md:65<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:52<br>외 1개 파일 | 가설·제안(외부 연구 근거이며 내부 대조 결과는 이 묶음에 없다) | MD-9.2 |
| A1-67 | 한 실험에서는 한 자산만 바꾸고, 모델 조건과 실제 전송 요청을 고정해 남긴다 | rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:484-486<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:137-146<br>rqc:docs/content/prompt-authoring-guide.md:100-102 | 여러 번 반복 관측(원인 분리 실패가 여러 번 기록됨) | MD-0.5, MD-7.10, MD-9.8 |
| A1-68 | 구조 검증과 정산 통과는 의미 통과가 아니고, 품질을 키워드 검증기로 판정하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:928<br>rqc:docs/content/prompt-authoring-guide.md:152<br>rqc:docs/character-authoring/research-grounded-persona-writer-standard-v1.md:342-346<br>외 1개 파일 | 여러 번 반복 관측 | MD-9.10 |
| A2-01 | 행동을 지시하지 말고 그 사람이 상황을 겪는 조건과 해석을 준다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:9-11(원칙<br>rqc:docs/superpowers/plans/2026-09-24-behavior-loop-to-appraisal-plan.md:14(같은 | 실측 대조로 확인 | MD-7.2 |
| A2-02 | 한쪽 해석·한쪽 충동만 주면 규칙처럼 작동한다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:39(K13 | 한 번 관측 | MD-3.6, MD-7.2 |
| A2-03 | 선택 문장 하나가 한 턴의 말투를 통째로 끌 수 있으므로 적용 조건을 좁게 쓴다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:88(K60<br>rqc:docs/content/prompt-authoring-guide.md:129-131(선택<br>rqc:docs/character-authoring/persona-decision-model-v1.md:72 | 실측 대조로 확인 | MD-3.8 |
| A2-04 | 금지문은 약하고, 같은 내용을 긍정형 습관으로 쓰면 지켜진다 | rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:43-44(첫마디<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:89(K61<br>rqc:docs/reports/2026-09-23-dialogue-foreign-word-leak.md:31-39(외국 | 여러 번 반복 관측 | MD-1.9 |
| A2-05 | 특정 행동을 강제하려고 허용·강조 문구를 누적하지 않는다 | rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/flirting-live-report-v1.md:36-50(사적<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:59-60(용어를<br>rqc:docs/superpowers/specs/2026-09-05-natural-character-dialogue-design.md:29(규칙을 | 여러 번 반복 관측 | MD-1.9 |
| A2-06 | 발동 조건과 철회 조건에는 해당하지 않는 경우도 함께 쓴다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1052-1055(무엇이<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:33-34 | 한 번 관측(단일 인물 두 차례 연속 통과) | MD-3.2 |
| A2-07 | 지시문 문장은 주어를 밝히고 한 문장에 한 사실만 두되, 그 문서체를 대사에 강요하지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1057-1058(주어<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:110-111(fluent-korean은<br>rqc:docs/superpowers/plans/2026-10-17-persona-studio-design-audit.md:34(페르소나 | 한 번 관측 | MD-7.3 |
| A2-08 | 상태를 묘사하는 문장은 금지나 지시가 아니라 지금의 상태로, 가까워질수록 경계가 풀리는 쪽으로 쓴다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:57(K32<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:235-238(경계가<br>rqc:docs/superpowers/plans/2026-09-25-mood-ladder-handoff.md:32-35 | 실측 대조로 확인 | MD-3.13, MD-5.7 |
| A2-09 | 페르소나를 줄이거나 윤문하거나 용어로 압축하는 것만으로 품질 개선을 주장하지 않는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:81(K53<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:185(윤문·용어<br>rqc:docs/character-authoring/editorial-20260910/evaluation/README.md:3<br>외 1개 파일 | 실측 대조로 확인(개선이 확인되지 않음) | MD-5.12 |
| A2-10 | 인물의 독창성 단위는 직업·말투가 아니라 인과 묶음이다 | rqc:docs/character-authoring/modern-women-10-v1/design-brief.md:7-17(승인<br>rqc:docs/character-authoring/modern-women-10-v1/reference-and-duplication-audit.md:7-22<br>rqc:docs/character-authoring/modern-women-20-v1/design-brief.md:9-17<br>외 2개 파일 | 여러 번 반복 관측(세 세트 저작 감사 + 라이브 1건) | MD-2.2 |
| A2-11 | 기본 선택은 성격 형용사가 아니라 관찰 가능한 동사로 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:27-46(모호한<br>rqc:docs/character-authoring/modern-women-10-v1/self-audit.md:112(대표<br>rqc:docs/character-authoring/modern-women-20-v1/self-audit.md:119<br>외 2개 파일 | 여러 번 반복 관측(저작 감사) | MD-3.2 |
| A2-12 | 결함 소거와 모범 조력자 수렴 | rqc:docs/character-authoring/modern-women-10-v1/reference-and-duplication-audit.md:121(모범<br>rqc:docs/character-authoring/modern-women-10-v1/authoring-notes.md:5(매력적인<br>rqc:docs/character-authoring/modern-women-20-v1/notes-06-10.md:243(친밀도가<br>외 2개 파일 | 여러 번 반복 관측(저작 감사 반복, 대화 출력으로는 문해원 편입 검증 1건) | MD-2.5 |
| A2-13 | 같은 상황에서 다른 선택을 하는지로 인물을 구별하고 검증한다 | rqc:docs/character-authoring/modern-women-10-v1/reference-and-duplication-audit.md:162-187(직업·trauma·호감<br>rqc:docs/character-authoring/modern-women-20-v1/taxonomy-and-30-crosswalk.md:128-137(category<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:45(같은<br>외 2개 파일 | 실측 대조로 확인 | MD-1.1, MD-9.1 |
| A2-14 | 관계 단계는 결함을 치료하지 않고 행동 형식·범위·수습 비용을 바꾼다 | rqc:docs/character-authoring/modern-women-10-v1/self-audit.md:131-148<br>rqc:docs/character-authoring/modern-women-20-v1/README.md:45-60<br>rqc:docs/character-authoring/modern-women-100-v1/quality-upgrade-audit.md:17 | 여러 번 반복 관측(저작 감사) | MD-3.13 |
| A2-15 | 수습은 사과문이 아니라 빼앗은 권리의 반환과 인물이 실제로 치르는 비용이다 | rqc:docs/character-authoring/modern-women-10-v1/reference-and-duplication-audit.md:129(모든<br>rqc:docs/character-authoring/modern-women-10-v1/self-audit.md:201<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1199(repair가<br>외 1개 파일 | 여러 번 반복 관측(저작 감사) | MD-3.5 |
| A2-16 | 매력은 피해 행동과 분리해 따로 둔다 | rqc:docs/character-authoring/modern-women-100-v1/quality-upgrade-audit.md:16<br>rqc:docs/character-authoring/modern-women-100-v1/README.md:85-91<br>rqc:docs/character-authoring/modern-women-100-v1/toxic-candidate-acceptance-checklist.md:142-147 | 여러 번 반복 관측(저작 감사, 100명) | MD-2.6 |
| A2-17 | 사용자가 먼저 보는 정본에 페르소나와 장면 전제를 맞춘다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:58(K18 | 한 번 관측(전후 동일 대본 비교는 아님) | MD-1.5, MD-2.1 |
| A2-18 | 분류 라벨과 표면 태그는 원인도 면책도 아니며 생성 입력에 넣지 않는다 | rqc:docs/character-authoring/modern-women-20-v1/README.md:41<br>rqc:docs/character-authoring/modern-women-20-v1/taxonomy-and-30-crosswalk.md:141-149(category<br>rqc:docs/character-authoring/modern-women-100-v1/README.md:91<br>외 1개 파일 | 가설·제안(저작 규칙, 대화 출력 비교 없음) | MD-2.7 |
| A2-19 | 페르소나는 사실·생활과 취향·성향·바람과 두려움·해석과 긴장·선택·말투·경계로 나누고, 해석과 선택을 분리한다 | rqc:docs/character-authoring/persona-decision-model-v1.md:9-23<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:87(K59 | 실측 대조로 확인(같은 모델 계열 독자 소표본, 사람 선호 미판정) | MD-3.1 |
| A2-20 | 인물을 움직이는 핵심 긴장 하나를 먼저 쓰고 욕구·두려움은 그 변형으로 쓴다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1030-1038(욕구·두려움을<br>rqc:docs/content/prompt-authoring-guide.md:123-126(v6 | 한 번 관측(단일 인물 세 챕터 두 차례 연속 통과) | MD-2.2 |
| A2-21 | 결론까지 적힌 행동 루프를 대사 입력에 넣지 않는다 | rqc:docs/superpowers/plans/2026-08-09-persona-r5-prior-successful-transcript-carryover.md:78-81(초기<br>rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/first-meeting-live-report-v7.md:44-49(공용<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:32(K6<br>외 1개 파일 | 나중에 뒤집힘. r5 시기의 enabled loop 매 턴 주입과 결정 사다리 방식이 2026-09-24 이후 wire 제외로 바뀌었고, v6 페르소나는 루프… | MD-2.2, MD-5.4 |
| A2-22 | 대화 재료는 구체적이어야 하지만 재료를 더하는 것만으로 자발성·응대 말투가 풀리지 않는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:27(K1<br>rqc:docs/character-authoring/editorial-20260910/evaluation/README.md:17 | 여러 번 반복 관측(결과가 엇갈림) | MD-2.6 |
| A2-23 | 개인어와 청자 대우법을 다른 층에 둔다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1060-1082(두<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:48-57<br>rqc:docs/content/prompt-authoring-guide.md:134-136(v6<br>외 2개 파일 | 여러 번 반복 관측 | MD-4.1 |
| A2-24 | 말높임은 정해진 슬롯과 전환 규칙으로 정하고, 관계 단계 상승을 전환 허가로 보지 않는다 | rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1072-1075(기본<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:54-57<br>rqc:docs/character-authoring/r5-templates/generation-contract-card-template.md:39-46<br>외 2개 파일 | 여러 번 반복 관측 | MD-3.13, MD-4.2 |
| A2-25 | 말높임·호칭 흔들림은 결정론 검사와 이력 점검으로 막는다 | rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/flirting-live-report-v1.md:52-58(씨+한테<br>rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:17-18(seed<br>rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/first-date-live-report-r8.md:20(r6에서<br>외 1개 파일 | 여러 번 반복 관측 | MD-5.11, MD-6.23, MD-7.8, MD-9.9 |
| A2-26 | 말투 칸은 대표 대사가 아니라 특징으로 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:50-52(개인어<br>rqc:docs/character-authoring/r5-templates/generation-contract-card-template.md:49-54(대표<br>rqc:docs/character-authoring/modern-women-100-v1/quality-upgrade-audit.md:15(고유<br>외 1개 파일 | 가설·제안(저작 기준. 100명 감사에서 적용했지만 대화 출력 대조는 없음) | MD-4.3, MD-4.4 |
| A2-27 | 말투 칸이 가장 강한 지렛대이므로 행동 태도와 일상 습관을 서술형으로 적는다 | rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:36-38(발행본에서<br>rqc:docs/content/prompt-authoring-guide.md:135(voice는<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:83(K55 | 실측 대조로 확인(캐릭터당 1~3회 소표본) | MD-4.13, MD-4.14 |
| A2-28 | 구어체 규범을 언어학 용어로 기술했지만 용어화의 효과는 따로 검증되지 않았다 | rqc:docs/superpowers/specs/2026-08-11-writer-spoken-register-username-design.md:4-5(라이브<br>rqc:docs/superpowers/plans/2026-08-19-prompt-code-separation.md:835(frame의<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:59-60(용어만 | 가설·제안(용어 기술 단독 효과는 분리되지 않음) | MD-4.10 |
| A2-29 | 해석·선택 칸을 언어학·심리학 개념어로 써도 누출은 없었지만 품질 효과는 중립이다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:90(K62<br>rqc:docs/character-authoring/persona-decision-model-v1.md:52<br>rqc:docs/content/prompt-authoring-guide.md:126-128 | 실측 대조로 확인(효과 중립. 사용자 결정으로 채택은 유지) | MD-3.15 |
| A2-30 | 말의 양을 인물 조건으로 적는 문장은 인물에 따라 득실이 갈렸고 서빙 입력에서 빠졌다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:51-52(K26·K27<br>rqc:docs/superpowers/plans/2026-09-25-mood-ladder-handoff.md:15(예외를 | 나중에 뒤집힘(말하는 방식 한 문장을 매 턴 블록에 넣던 방식이 v39에서 빠짐, 스키마 칸만 남음) | MD-4.5 |
| A2-31 | 상대 이름이 없으면 모델이 빈 호칭으로 공백을 메운다 | rqc:docs/superpowers/specs/2026-08-11-writer-spoken-register-username-design.md:4-5(대체<br>rqc:docs/reports/2026-10-14-hi-colloquial-review.md:73-74(이름은<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:76-78(지원되지 | 한 번 관측(원인은 가설) | MD-5.11 |
| A2-32 | 지시가 없거나 호감이 오르면 기본 다정체로 돌아가 개인어가 사라진다 | rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/first-date-live-report-r8.md:20-22<br>rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/flirting-live-report-v1.md:21<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:57(K32<br>외 1개 파일 | 여러 번 반복 관측 | MD-3.10, MD-4.13 |
| A2-33 | 같은 문맥은 같은 표현으로 수렴하므로, 표현 다양성은 고정 구성 대신 문맥에 맞는 성향 선택으로 만든다 | rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/flirting-final-confession-report-v2.md:11-15(표현 | 한 번 관측 | MD-5.5 |
| A2-34 | 다른 언어 판은 한국어를 옮기지 말고 그 언어의 거리감 방식으로 새로 쓴다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:263-269<br>rqc:docs/reports/2026-09-22-global-locale-dialogue-review.md:19<br>rqc:docs/content/prompt-authoring-guide.md:159-161 | 한 번 관측 | MD-2.11 |
| A2-35 | 서빙 프롬프트에 정답 대사·대표 대사·인용형 예시를 넣지 않는다 | rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:48(말투<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:127-131(기본<br>rqc:docs/superpowers/specs/2026-09-05-natural-character-dialogue-design.md:16(서빙<br>외 4개 파일 | 여러 번 반복 관측(복제 자체는 3/3 실측) | MD-1.2, MD-5.4 |
| A2-36 | 금지할 표현을 따옴표로 인용하면 그 표현이 대사로 샌다 | rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:48-49(금지 | 한 번 관측 | MD-1.2, MD-7.1 |
| A2-37 | 가짜 수락 턴과 작가 수락 프리필을 기본으로 넣지 않는다 | rqc:docs/product/relationship-quest-character-chat-prd.md:1288<br>rqc:docs/superpowers/plans/2026-08-09-persona-r5-prior-successful-transcript-carryover.md:93-94(첫<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:133-140<br>외 3개 파일 | 나중에 뒤집힘. 초기 PRD의 작가 역할+수락 프리필 구조가 2026-09-06 비교(160출력) 뒤 기본 해법에서 빠지고 writerRegister v3의 … | MD-5.4 |
| A2-38 | 설정 속 구체 소재 한 줄이 대화마다 반복 모티프가 된다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:41(K15 | 여러 번 반복 관측 | MD-2.6, MD-4.4, MD-9.9 |
| A2-39 | 한 규칙에는 소유자를 하나만 두고 같은 한도·대우법·표를 여러 곳에 반복하지 않는다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:13-25<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:42(K16<br>rqc:docs/content/prompt-authoring-guide.md:28<br>외 2개 파일 | 여러 번 반복 관측 | MD-1.4 |
| A2-40 | 필드가 있다는 것과 모델에 실제로 전송된다는 것은 다르다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:24-25<br>rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/flirting-live-report-v1.md:44-50(initiativePolicy는<br>rqc:docs/content/prompt-authoring-guide.md:100-102(필드만<br>외 1개 파일 | 여러 번 반복 관측 | MD-0.7, MD-5.12 |
| A2-41 | 사용자 마지막 말 바로 앞 블록에는 매 턴 달라지는 상태와 길이만 둔다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:50(K25<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:216-224<br>rqc:docs/superpowers/plans/2026-09-25-mood-ladder-handoff.md:139 | 실측 대조로 확인(사용자 블라인드 3짝씩, 배치·이음새 한계 명시) | MD-0.6, MD-5.9 |
| A2-42 | 이 자리에 있는 이유가 비면 모델이 장면과 반대되는 이유를 지어내므로 장면 사실에서 한 문장으로 앞쪽에 둔다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:226-230(이유가<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:64(K36<br>rqc:docs/superpowers/plans/2026-09-25-mood-ladder-handoff.md:14<br>외 1개 파일 | 실측 대조로 확인 | MD-5.6 |
| A2-43 | 새 문장을 넣기 전에 장면 사실과 대조하고, 서로 부딪히는 두 사실을 함께 주지 않는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:53(K28<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:243-244(먼저<br>rqc:docs/superpowers/plans/2026-09-25-mood-ladder-handoff.md:20<br>외 1개 파일 | 실측 대조로 확인 | MD-5.6, MD-5.8 |
| A2-44 | 모델 입력에 제작 메타·revision·원형 이름·분류 라벨·관계 수치를 넣지 않는다 | rqc:docs/superpowers/specs/2026-09-03-assembled-prompt-omits-content-revision.md:8-17(revision은<br>rqc:docs/character-authoring/r5-templates/generation-contract-card-template.md:27-29(원형<br>rqc:docs/character-authoring/modern-women-100-v1/session-handoff-2026-08-11.md:73-75(사용자<br>외 3개 파일 | 여러 번 반복 관측 | MD-0.2, MD-0.4, MD-5.4, MD-7.7 |
| A2-45 | 이전 대화 기록은 끝난 장면으로 넣고 현재 장면이 권위를 갖게 한다 | rqc:docs/superpowers/plans/2026-08-09-persona-r5-prior-successful-transcript-carryover.md:84-90 | 가설·제안(설계 원칙, 검증 항목은 계획 단계) | MD-5.10 |
| A2-46 | 고정된 공개·애정 한도 대신 대화에 따라 움직이는 현재 마음을 주고, 깊은 이야기는 막지 않는다 | rqc:docs/character-authoring/modern-women-10-v1/schema-pressure-notes.md:61-71(초기<br>rqc:docs/character-authoring/persona-authoring-methodology-v1.md:1100-1109(공개<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:43(K17<br>외 2개 파일 | 나중에 뒤집힘. 저작 세트의 고정 ceiling 방식이 2026-09-25 관계 설정 v3의 지금 마음과 믿게 되면 꺼낼 이야기로 대체됐다. 새 방식의 효과는… | MD-5.7 |
| A2-47 | 별도 속마음 출력이나 추론 수준 상향을 인물 연기 개선 수단으로 기본 채택하지 않는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:35(K9 | 실측 대조로 확인 | MD-5.4 |
| A2-48 | 프롬프트가 허용한 표현이 코드 가드에 막히는지 확인한다 | rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:60-62(최종<br>rqc:docs/content/prompt-authoring-guide.md:103 | 한 번 관측 | MD-5.12 |
| A2-49 | 상담사·접객 말투(응대 말투) | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:28(K2<br>rqc:docs/superpowers/plans/2026-09-24-behavior-loop-to-appraisal-plan.md:119(해석<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:69(상담원처럼<br>외 1개 파일 | 여러 번 반복 관측(원인은 미분리) | MD-6.5, MD-6.16 |
| A2-50 | 상대의 말과 행동을 해석해 되돌려 주는 정식화 대신, 자기 경험에서 나온 자기 서술과 대등한 받기를 쓰게 한다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:91(K63<br>rqc:docs/character-authoring/editorial-20260910/evaluation/han-somin-comparison.md:3 | 실측 대조로 확인(사용자 정의를 판정 기준으로 옮긴 재판정, 사람 라벨 교정 전 제안 단계) | MD-4.8, MD-6.16 |
| A2-51 | 사과 과잉·사과 나선·업무형 사과 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:30<br>rqc:docs/character-authoring/editorial-20260910/evaluation/seo-jian-comparison.md:3<br>rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/first-date-live-report-r8.md:20(사과<br>외 3개 파일 | 여러 번 반복 관측 | MD-6.15 |
| A2-52 | 근거 없는 모욕·일상 불평·정당한 항의를 같은 사과나 같은 공격으로 처리한다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:83-95<br>rqc:docs/character-authoring/r5-templates/generation-contract-card-template.md:107-114<br>rqc:docs/superpowers/specs/2026-09-05-natural-character-dialogue-design.md:13<br>외 1개 파일 | 한 번 관측(2026-09-05~07 실험 묶음에서 도출한 규칙) | MD-3.3, MD-6.14 |
| A2-53 | 질문 끝맺음과 고정 응답 공식 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:37(K11<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:105<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:67(모든<br>외 4개 파일 | 실측 대조로 확인 | MD-6.8 |
| A2-54 | 사용자의 상태·외모·습관·동기를 넘겨짚는다 | rqc:docs/character-authoring/editorial-20260910/evaluation/lee-seoyeon-comparison.md:14(1턴에<br>rqc:docs/character-authoring/editorial-20260910/evaluation/lee-haeun-comparison.md:14(바쁘다·혼자가<br>rqc:docs/character-authoring/editorial-20260910/evaluation/park-sera-comparison.md:14(사용자의<br>외 4개 파일 | 여러 번 반복 관측 | MD-6.13 |
| A2-55 | 공동 기억 날조와 빈 이력 채우기 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:22<br>rqc:docs/superpowers/reports/2026-09-22-free-call-fun-probe.md:50(모르면<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:84<br>외 1개 파일 | 여러 번 반복 관측 | MD-1.8, MD-6.3 |
| A2-56 | 규칙 과잉 적용·과교정과 축객 | rqc:docs/character-authoring/wang-dagyeong-r2-candidate/evaluation/first-date-live-report-r8.md:21-22(voice<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:32(K6<br>rqc:docs/character-authoring/editorial-20260910/README.md:14(낯선<br>외 3개 파일 | 여러 번 반복 관측 | MD-3.3, MD-3.10, MD-3.12 |
| A2-57 | 가벼운 말이나 상대의 개인 선택을 관계의 깊은 의미로 과잉 해석한다 | rqc:docs/character-authoring/editorial-20260910/evaluation/lee-haeun-comparison.md:3<br>rqc:docs/character-authoring/editorial-20260910/evaluation/seo-jian-comparison.md:10<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:62(짧은 | 한 번 관측 | MD-3.6 |
| A2-58 | 반복 확인·안심 요구를 덜어 내면 다른 형태의 평가 말로 옮겨 간다 | rqc:docs/character-authoring/editorial-20260910/evaluation/README.md:7<br>rqc:docs/character-authoring/editorial-20260910/evaluation/han-somin-comparison.md:9<br>rqc:docs/character-authoring/r5-templates/generation-contract-card-template.md:61 | 한 번 관측 | MD-6.16 |
| A2-59 | 한 턴의 길이는 대개 1~2문장, 3문장 상한으로 두고 길이 기준은 생성 직전에 다시 둔다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:99-108<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:62(K34<br>rqc:docs/superpowers/plans/2026-09-07-rp-turn-economy.md:79-83(길이<br>외 3개 파일 | 실측 대조로 확인 | MD-6.7 |
| A2-60 | 한국어 대사에 외국 낱말 하나가 섞인다 | rqc:docs/reports/2026-09-23-dialogue-foreign-word-leak.md:19(실험<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:33(K7 | 실측 대조로 확인 | MD-9.9 |
| A2-61 | 역할과 장면을 유지하고 거절·전환도 정책 안내문이 아니라 인물의 말투로 한다 | rqc:docs/superpowers/specs/2026-09-05-natural-character-dialogue-design.md:10-14<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:80-81<br>rqc:docs/reports/2026-10-14-hi-colloquial-review.md:76-80(역할 | 한 번 관측 | MD-6.4, MD-6.18, MD-6.22 |
| A2-62 | 대사가 관계 결과나 약속을 정산보다 먼저 확정한다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:78(K50<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:26 | 한 번 관측(결정론 재현, 실제 모델 발생 빈도 미측정) | MD-6.19 |
| A2-63 | 여러 챕터를 이어 갈 때 장면·기억·관계 시점이 어긋난다 | rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:159(앞<br>rqc:docs/superpowers/plans/2026-08-09-persona-r5-prior-successful-transcript-carryover.md:670-673<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:67(K39 | 가설·제안(연쇄 여정은 6턴 × 3챕터 한 번 관측. 이 묶음 문서에는 수십~수백 턴 장기 대화의 붕괴 실측이 없다) | MD-9.6 |
| A2-64 | 여러 인물이 공통 작가 목소리로 수렴한다 | rqc:docs/character-authoring/modern-women-100-v1/quality-upgrade-audit.md:41-46(인물<br>rqc:docs/character-authoring/modern-women-100-v1/session-handoff-2026-08-11.md:73-75<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:86(K58 | 여러 번 반복 관측 | MD-7.8, MD-9.1 |
| A2-65 | 판정의 기준은 사용자 블라인드이고 LLM 판정과 결정론 지표는 방향 참고다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:18(MiMo<br>rqc:docs/superpowers/plans/2026-08-07-llm-judge-persona-grounding.md:20-21(판정<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:175-177 | 실측 대조로 확인 | MD-9.2, MD-9.3 |
| A2-66 | 비교는 끝까지 이어 생성한 여정·좌우 섞기·사전 등록 기준으로 하고, 한두 쌍 결론을 채택하지 않는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md:19(한<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:256-260<br>rqc:docs/character-authoring/editorial-20260910/evaluation/README.md:43-45(평가자 | 여러 번 반복 관측 | MD-9.3 |
| A2-67 | 사실과 앎의 경계를 먼저 판정하고, 나머지 품질 축은 따로 판정한다 | rqc:docs/character-authoring/persona-decision-model-v1.md:74<br>rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:212(E5<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:166-174<br>외 1개 파일 | 여러 번 반복 관측 | MD-9.4 |
| A2-68 | 정적 검증·스키마 통과·챕터 PASS는 대화 품질의 증거가 아니다 | rqc:docs/character-authoring/modern-women-10-v1/README.md:52(validator<br>rqc:docs/content/park-sera-card-alignment-2026-09-29.md:221<br>rqc:docs/character-authoring/roleplay-prompt-authoring-practice.md:10-11<br>외 3개 파일 | 여러 번 반복 관측 | MD-0.3, MD-9.5, MD-9.10 |
| A2-69 | 평가 대본에는 확인하려는 행동이 나올 기회를 넣는다 | rqc:docs/superpowers/plans/character-chat-hypothesis-board.md@stash749471c3:95(K67<br>rqc:docs/superpowers/plans/2026-08-09-persona-r5-prior-successful-transcript-carryover.md:670-671(행동별 | 한 번 관측 | MD-9.7 |
| B-01 | 기획 지시문의 순서 있는 행동 예시는 후보 번호별 공통 틀로 복제된다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:11<br>cfp:docs/reports/2026-10-29-persona-quality-floor-implementation.md:39<br>cfp:docs/status/known-issues.md:58<br>외 2개 파일 | 여러 번 반복 관측(공통 틀은 두 보고서에서 관측, 예시가 원인이라는 인과는 가설로 남음) | MD-1.2, MD-2.3, MD-7.1 |
| B-02 | 출력 형식 예시에 실제 성격 문장을 넣으면 형식과 내용이 섞인다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:31<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:59<br>cfp:src/character_factory_poc/prompts/common-procedure.md:5<br>외 1개 파일 | 가설·제안 | MD-7.1 |
| B-03 | 규칙 커버리지만 보고 고른 대화 예시는 설명·협의 패턴을 끌어오고 인물 고유 표현을 떨어뜨린다 | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:29<br>cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:54<br>cfp:docs/reports/2026-10-29-persona-choice-voice-live-validation.md:33 | 여러 번 반복 관측(선정 편향은 확인, 응답에 미친 효과는 가설) | MD-1.3 |
| B-04 | 실제 대화 본문에는 예시 대화·내부 조건표·챕터 전체를 넣지 않고 경향 문장으로 전달한다 | cfp:docs/status/decisions.md:76<br>cfp:docs/guides/actor-persona.md:20<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:56<br>외 1개 파일 | 한 번 관측(한 인물 96응답, 사람 블라인드 없음). B-05의 예시 삽입 방식을 대체한 결정이다. | MD-1.3, MD-5.3, MD-5.4 |
| B-05 | 긴 프롬프트에 고정 슬롯 대화 예시 4개를 넣는 방식 | cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:86<br>cfp:docs/reports/2026-10-29-persona-quality-floor-plan-review.md:42<br>cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:29<br>외 1개 파일 | 나중에 뒤집힘. D-0070과 B-04(경향 문장만 넣는 서비스 8섹션 조립)가 대체했다. | MD-5.4 |
| B-06 | 예시 속 사용자 사실·약속은 그 예시 안에서만 유효하다 | cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:79<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:29<br>cfp:src/character_factory_poc/prompts/persona_dialogues.md:15<br>외 1개 파일 | 가설·제안(설계와 회귀 검사, 실제 유출 관측 기록은 없음) | MD-1.5 |
| B-07 | 말투 원천 예시는 표현만 떼어 주고 원 화자의 사실·선택은 옮기지 않는다 | cfp:docs/guides/voice-assets.md:21<br>cfp:docs/reports/2026-10-29-persona-choice-voice-plan-review.md:30<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:98<br>외 2개 파일 | 가설·제안(여러 문서가 채택한 설계 규칙, 위반 관측 기록은 없음) | MD-1.5 |
| B-08 | 실제 말투 예시를 중간 단계에 줬다는 사실이 최종 대화의 말투를 보장하지 않는다 | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:45<br>cfp:docs/reports/2026-10-29-persona-choice-voice-live-validation.md:39<br>cfp:docs/status/known-issues.md:61 | 실측 대조로 확인(A~D 조건 대조에서 개선을 확인하지 못함, 사람 블라인드는 없음) | MD-1.3 |
| B-09 | 모델이 쓴 초안 대사와 자기 승인 표시는 말투 기준이 아니다 | cfp:docs/reports/2026-10-29-voice-source-audit.md:7<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:31<br>cfp:docs/reports/2026-10-29-persona-choice-voice-implementation.md:11<br>외 2개 파일 | 한 번 관측(자료 감사 1회) | MD-1.3, MD-2.9 |
| B-10 | 프리필(가짜 확인 대사)로 이력 문제를 덮으면 없는 일정을 만든다 | cfp:docs/guides/qlora-authored/01-dataset.md:60<br>cfp:docs/guides/qlora-authored/04-continuous-improvement.md:57<br>cfp:docs/guides/qlora-authored/03-evaluation.md:7 | 한 번 관측(소민 데이터 작업) | MD-5.4 |
| B-11 | 실제 대화 자료는 흐름만 가져오고 대사는 새로 쓴다 | cfp:docs/status/decisions.md:13<br>cfp:docs/guides/qlora-authored/README.md:39<br>cfp:docs/guides/qlora-authored/01-dataset.md:36<br>외 1개 파일 | 가설·제안(확정 결정이지만 효과를 대조한 기록은 이 묶음에 없음) | MD-1.5 |
| B-12 | 평가 문항·보류 자료를 예시나 생성 입력으로 재사용하지 않는다 | cfp:docs/status/decisions.md:13<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:80<br>cfp:docs/guides/qlora-authored/04-continuous-improvement.md:66<br>외 1개 파일 | 가설·제안 | MD-7.11 |
| B-13 | 말투는 형용사가 아니라 항목별 관찰값으로 적는다 | cfp:docs/guides/qlora-authored/01-dataset.md:19<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:78<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:68<br>외 2개 파일 | 한 번 관측(범용 설명으로 인한 손실은 공장 감사 1회, 항목별 규칙표는 소민 정본에서 사용) | MD-4.3 |
| B-14 | 말높임은 관계 단계·채널마다 하나로 정하고 유지를 따로 잰다 | cfp:docs/guides/qlora-authored/README.md:30<br>cfp:docs/guides/qlora-authored/01-dataset.md:16<br>cfp:docs/guides/qlora-authored/03-evaluation.md:73<br>외 2개 파일 | 여러 번 반복 관측 | MD-2.8, MD-4.1 |
| B-15 | 채널에 따라 표기를 바꾼다 | cfp:docs/guides/qlora-authored/01-dataset.md:17<br>cfp:docs/guides/qlora-authored/03-evaluation.md:87<br>cfp:src/character_factory_poc/resources/actor-system-rules-v2.md:5 | 가설·제안(소민 정본 규칙, 위반율 측정 기록은 이 묶음에 없음) | MD-1.6 |
| B-16 | 말버릇은 나오는 자리와 빠지는 자리를 정하고 빈도 상한을 둔다 | cfp:docs/guides/qlora-authored/04-continuous-improvement.md:47<br>cfp:docs/guides/qlora-authored/03-evaluation.md:87<br>cfp:docs/guides/qlora-authored/01-dataset.md:15<br>외 1개 파일 | 여러 번 반복 관측(두 인물) | MD-4.11 |
| B-17 | 글자 수·물음표 수는 진단 지표이지 자연스러움 점수가 아니다 | cfp:docs/reports/2026-10-28-persona-quality.md:9<br>cfp:docs/reports/2026-10-29-somin-transfer.md:46<br>cfp:docs/reports/2026-10-29-persona-choice-voice-live-validation.md:41<br>외 3개 파일 | 여러 번 반복 관측 | MD-9.9 |
| B-18 | 내용과 말투를 한 번에 쓰게 하면 번역투·상담원 말투가 나온다 | cfp:docs/guides/qlora-authored/01-dataset.md:37<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:92<br>cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:62<br>외 2개 파일 | 여러 번 반복 관측 | MD-7.5 |
| B-19 | 말투 보존 검토는 뜻·정중함 보존만으로 목소리 보존을 인정하지 않는다 | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:72<br>cfp:docs/reports/2026-10-29-trait-persona-gemini-live.md:36<br>cfp:src/character_factory_poc/prompts/persona_voice_preservation.md:8 | 한 번 관측 | MD-7.6, MD-9.10 |
| B-20 | 상담사 말투: 감정 장면에서 다정한 상담자처럼 초대·설명·질문한다 | cfp:docs/reports/2026-10-29-trait-persona-gemini-live.md:5<br>cfp:docs/status/known-issues.md:68<br>cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:5<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.5 |
| B-21 | 기본 성격과 결함이 조립 과정에서 빠진다(결함 소거) | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:7<br>cfp:docs/reports/2026-10-28-persona-quality.md:9<br>cfp:docs/reports/2026-10-29-somin-transfer.md:25<br>외 1개 파일 | 실측 대조로 확인(같은 입력으로 최종 본문을 정확히 재현해 누락 경로를 추적했고, 수정 뒤 실제 96응답으로 확인) | MD-5.2 |
| B-22 | 결함을 친절하게 고치지도, 모든 장면의 공격으로 키우지도 않는다 | cfp:docs/research/2026-10-30-text-model-deck-source.md:32<br>cfp:docs/reports/2026-10-29-trait-persona-gemini-live.md:73<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:76<br>외 2개 파일 | 여러 번 반복 관측(소거와 과장 양쪽이 관측됨, 대응책의 효과는 미검증) | MD-2.9, MD-3.10 |
| B-23 | 규칙 과잉 적용: 조건이 없는 장면에도 보류·재약속·경계를 끌어온다 | cfp:docs/reports/2026-10-28-persona-quality.md:7<br>cfp:docs/reports/2026-10-29-somin-transfer.md:38<br>cfp:docs/status/known-issues.md:52 | 실측 대조로 확인(같은 장면·고정 이력 40턴 전후 대조, 한 캐릭터) | MD-3.8, MD-3.12 |
| B-24 | 비적용 조건 오적용: 이력에 없는 합의를 가정해 규칙을 켠다 | cfp:docs/reports/2026-10-29-persona-choice-voice-live-validation.md:25<br>cfp:docs/status/known-issues.md:60 | 여러 번 반복 관측(세 조건에서 같은 오류) | MD-9.7 |
| B-25 | 공동 기억·사용자 사실 날조와 주인 혼동 | cfp:docs/reports/2026-10-29-somin-transfer.md:17<br>cfp:docs/guides/qlora-authored/01-dataset.md:66<br>cfp:docs/guides/qlora-authored/03-evaluation.md:30<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.3 |
| B-26 | 사실 규칙을 너무 넓게 쓰면 자기 일정조차 못 만들고 새 조건을 거부한다 | cfp:docs/guides/qlora-authored/04-continuous-improvement.md:39<br>cfp:docs/guides/qlora-authored/README.md:40도<br>cfp:docs/reports/2026-10-29-persona-quality-floor-plan-review.md:34<br>외 3개 파일 | 여러 번 반복 관측 | MD-6.10 |
| B-27 | 할 수 없는 외부 조회를 약속한다 | cfp:docs/reports/2026-10-28-persona-quality.md:16<br>cfp:docs/status/known-issues.md:53<br>cfp:docs/reports/2026-10-29-somin-transfer.md:41<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.12 |
| B-28 | 근거 없는 편들기와 사용자 사정 넘겨짚기 | cfp:docs/reports/2026-10-29-somin-transfer.md:44<br>cfp:docs/status/known-issues.md:52<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:80<br>외 1개 파일 | 여러 번 반복 관측 | MD-6.13 |
| B-29 | 사과 과잉과 잘못 없는 동반 사과, 그리고 사과 한 번을 결함으로 세는 오판 | cfp:docs/reports/2026-10-29-service-persona-runtime.md:76<br>cfp:docs/reports/2026-10-29-somin-transfer.md:44<br>cfp:docs/guides/qlora-authored/03-evaluation.md:37<br>외 3개 파일 | 여러 번 반복 관측(한 건의 결함 판정은 나중에 뒤집혀 수용 가능한 조정으로 정정됨) | MD-6.15, MD-9.4 |
| B-30 | 질문 끝맺음과 공식형 답변: 요약·공감·설명·대안·질문을 매번 붙인다 | cfp:docs/reports/2026-10-29-trait-persona-gemini-live.md:53<br>cfp:docs/reports/2026-10-29-persona-choice-voice-live-validation.md:39<br>cfp:docs/reports/2026-10-29-persona-quality-floor-implementation.md:37<br>외 5개 파일 | 여러 번 반복 관측 | MD-4.3, MD-6.6 |
| B-31 | 이미 정한 약속을 매 턴 다시 붙인다 | cfp:docs/status/known-issues.md:52<br>cfp:docs/reports/2026-10-29-somin-transfer.md:44<br>cfp:docs/guides/qlora-authored/01-dataset.md:94<br>외 1개 파일 | 여러 번 반복 관측 | MD-6.20 |
| B-32 | 장기 대화 붕괴: 후반 반복 루프와 긴 문맥 뒤 감정 판단 약화 | cfp:docs/guides/qlora-authored/01-dataset.md:82<br>cfp:docs/guides/qlora-authored/03-evaluation.md:35 | 실측 대조로 확인(턴 분포를 바꾼 전후 반복률 대조, 일부 확인) | MD-9.6 |
| B-33 | 갈등 결말이 한쪽으로 쏠리면 무조건 풀리거나 관계 위협으로 간다 | cfp:docs/guides/qlora-authored/01-dataset.md:62<br>cfp:docs/guides/qlora-authored/03-evaluation.md:38 | 여러 번 반복 관측 | MD-6.17 |
| B-34 | 같은 행동을 말만 바꾼 재서술이 선택 차이로 통과한다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:48<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:55<br>cfp:src/character_factory_poc/prompts/choice_review.md:10 | 한 번 관측(합성 반례) | MD-2.3 |
| B-35 | 성격 칸을 명사형 표제어나 낱말 나열로 쓰면 검사에서 멈춘다 | cfp:docs/reports/2026-10-14-dohee-p29-persona-run.md:25<br>cfp:docs/reports/2026-10-14-agentic-p29-run.md:24<br>cfp:docs/reports/2026-10-30-tsundere-persona-live.md:31<br>외 2개 파일 | 여러 번 반복 관측 | MD-0.7, MD-3.15 |
| B-36 | 자동 판정이 경향을 의무로 오해하고 인용·범위를 틀린다 | cfp:docs/reports/2026-10-28-persona-quality.md:45<br>cfp:docs/status/known-issues.md:55(K-0045<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:96<br>외 2개 파일 | 여러 번 반복 관측 | MD-9.2, MD-9.3 |
| B-37 | 공통 기본기를 선택 차이 부족의 증거로 잘못 읽는다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:52<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:21<br>cfp:src/character_factory_poc/prompts/choice_review.md:12 | 한 번 관측 | MD-1.1, MD-2.3, MD-9.1 |
| B-38 | 같은 상황에서 다른 선택이 캐릭터성이다: 장면별 선택을 정본에 먼저 정의한다 | cfp:docs/status/decisions.md:40<br>cfp:docs/guides/qlora-authored/01-dataset.md:24<br>cfp:docs/guides/qlora-authored/03-evaluation.md:20<br>외 2개 파일 | 여러 번 반복 관측 | MD-1.1 |
| B-39 | 선택 규칙마다 주의 대상·우선순위·첫 행동·감수 비용·적용/비적용·전환·잘못된 변형을 적는다 | cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:44<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:67<br>cfp:docs/reports/2026-10-14-dohee-p29-persona-run.md:38<br>외 1개 파일 | 가설·제안(설계 제안, 실제 형성 첫 통과는 0/4) | MD-3.2, MD-5.3 |
| B-40 | 씨앗 요구를 후보 생성 전에 분리해 고정하고, 함께 적힌 조건의 누락을 역방향으로 검사한다 | cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:42<br>cfp:docs/reports/2026-10-29-persona-choice-voice-plan-review.md:19<br>cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:13<br>외 1개 파일 | 가설·제안 | MD-2.1, MD-2.2 |
| B-41 | 후보 선택 규약: 첫 후보 자동 선택은 후보 안의 다양성을 버린다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:12<br>cfp:docs/reports/2026-10-29-persona-choice-voice-plan-review.md:22<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:61 | 한 번 관측 | MD-2.10 |
| B-42 | 추가 특질은 기본 성격을 대체하지 않고 같은 성향 문장으로 합친다 | cfp:docs/guides/actor-persona.md:18<br>cfp:docs/product/2026-10-29-trait-recommendation-plan.md:20<br>cfp:docs/reports/2026-10-29-trait-recommendation-implementation.md:32<br>외 4개 파일 | 한 번 관측 | MD-5.1 |
| B-43 | 일상 대화에 쓸 생활 재료를 기획 단계에서 만든다 | cfp:docs/reports/2026-10-28-persona-quality.md:7<br>cfp:docs/reports/2026-10-29-somin-transfer.md:13<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:53 | 한 번 관측(한 캐릭터 전후 대조) | MD-2.6, MD-3.12 |
| B-44 | 외모로 성격을 추정하지 않는다 | cfp:docs/status/decisions.md:11<br>cfp:docs/reports/2026-10-14-dohee-p29-persona-run.md:37 | 가설·제안(확정 원칙, 위반 관측 기록은 없음) | MD-2.7 |
| B-45 | 대화 본문은 서비스 섹션으로 조립하고 현재 관계·장면은 하나의 맥락으로만 준다 | cfp:docs/guides/actor-persona.md:7<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:13<br>cfp:docs/status/decisions.md:77<br>외 1개 파일 | 한 번 관측 | MD-5.1, MD-5.5 |
| B-46 | 승인 정본은 모델이 다시 쓰지 않고 코드가 그대로 옮기며, 길이 초과는 실패시킨다 | cfp:docs/reports/2026-10-29-somin-transfer.md:25<br>cfp:docs/product/2026-10-29-somin-transfer-plan.md:31<br>cfp:docs/research/2026-10-30-text-model-deck-source.md:36<br>외 2개 파일 | 한 번 관측 | MD-0.1, MD-0.7, MD-2.9, MD-5.2, MD-7.4 |
| B-47 | 대화 규칙은 내부에서 확인할 조건과 상대에게 말할 내용을 구분해 짧게 쓴다 | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:68<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:41<br>cfp:docs/product/2026-10-29-trait-persona-prompt-fix-plan.md:19 | 가설·제안 | MD-1.9 |
| B-48 | 짧은 프롬프트는 비교 평가를 통과하기 전에는 긴 프롬프트를 대신하지 않는다 | cfp:docs/status/decisions.md:12<br>cfp:docs/reports/2026-10-14-dohee-p29-persona-run.md:39<br>cfp:docs/reports/2026-10-14-agentic-p29-run.md:36<br>외 2개 파일 | 가설·제안 | MD-0.6 |
| B-49 | 의미 실패는 재추첨·교정으로 숨기지 않고 형식 재시도만 허용한다 | cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:45<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:32<br>cfp:docs/guides/text-model-deck.md:68<br>외 2개 파일 | 가설·제안(운영 원칙) | MD-7.9, MD-9.5 |
| B-50 | 생성과 검토는 다른 계열 모델로 나누고, 검토 모델은 문장을 대신 쓰지 않는다 | cfp:docs/status/decisions.md:16<br>cfp:docs/guides/persona-runbook.md:15도<br>cfp:docs/research/2026-10-30-text-model-deck-source.md:31<br>외 1개 파일 | 가설·제안 | MD-7.4, MD-7.8, MD-7.10 |
| B-51 | 항상·절대 식 행동 규칙을 두지 않고 관계 변화와 예외를 함께 적는다 | cfp:docs/research/2026-10-30-text-model-deck-source.md:33<br>cfp:docs/guides/voice-assets.md:23<br>cfp:docs/guides/qlora-authored/04-continuous-improvement.md:39<br>외 1개 파일 | 가설·제안 | MD-3.8 |
| B-52 | 여러 인물에 재사용하는 고정 지시문에 성별·자세·구도·관계 단계를 박아 두지 않는다 | cfp:docs/reports/2026-10-29-video-pipeline-audit.md:78<br>cfp:docs/status/known-issues.md:44 | 가설·제안(정적 감사, 실제 실패율 미검증) | MD-7.1 |
| B-53 | 에이전트 작업 지시는 작업 공간 안의 경로만 쓰게 하고, 말투 표기를 경로로 오인하지 않게 검사한다 | cfp:docs/status/known-issues.md:39<br>cfp:src/character_factory_poc/prompts/common-procedure.md:4 | 한 번 관측 | MD-7.12 |
| B-54 | 인물별 선택은 같은 상황 매칭 비교로 보고, 기대 행동을 호출 전에 봉인한다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:15<br>cfp:docs/reports/2026-10-29-persona-quality-floor-plan-review.md:24<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:136 | 한 번 관측 | MD-9.1 |
| B-55 | 한 번에 한 변수만 바꿔 대조한다 | cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:83<br>cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:60<br>cfp:docs/reports/2026-10-29-service-persona-runtime.md:64<br>외 2개 파일 | 여러 번 반복 관측(묶음 변경 때문에 인과를 가르지 못한 사례가 반복됨) | MD-9.8 |
| B-56 | 고정 이력과 누적 이력을 구분하고, 첫 응답만 쓰며, 턴마다 다른 시드를 쓴다 | cfp:docs/reports/2026-10-29-somin-transfer.md:50<br>cfp:docs/guides/qlora-authored/03-evaluation.md:14<br>cfp:docs/reports/2026-10-29-persona-choice-voice-plan-review.md:31<br>외 3개 파일 | 실측 대조로 확인(시드 정책 변경 전후 반복 0) | MD-9.6, MD-9.7 |
| B-57 | 출력 상한에는 추론 토큰이 포함된다: 잘린 응답은 품질 판단에 쓰지 않는다 | cfp:docs/reports/2026-10-14-dohee-p29-persona-run.md:28<br>cfp:docs/reports/2026-10-29-persona-quality-floor-implementation.md:23<br>cfp:docs/reports/2026-10-28-persona-quality.md:45<br>외 1개 파일 | 여러 번 반복 관측 | MD-9.5 |
| B-58 | 사람 블라인드 평가에서 자연스러움·말투 적합성·선택 충실도를 따로 판정한다 | cfp:docs/reports/2026-10-29-persona-choice-voice-plan-review.md:35<br>cfp:docs/product/2026-10-29-persona-choice-voice-plan.md:139<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:145<br>외 2개 파일 | 가설·제안(정식 사람 평가는 이 묶음 기간에 실행되지 않음) | MD-9.3 |
| B-59 | 중대 오류는 점수 평균으로 상쇄하지 않고, 생성 표본에는 위험 유형을 일부러 넣는다 | cfp:docs/guides/qlora-authored/03-evaluation.md:98<br>cfp:docs/guides/qlora-authored/README.md:76<br>cfp:docs/product/2026-10-29-persona-quality-floor-plan.md:116<br>외 1개 파일 | 가설·제안 | MD-9.4, MD-9.7 |
| B-60 | 소량 표본을 사람이 검토한 뒤 확대하고, 한 줄 교정본은 전부 읽는다 | cfp:docs/guides/qlora-authored/01-dataset.md:102 | 여러 번 반복 관측 | MD-0.5, MD-7.11 |
| B-61 | 보강 자료가 반말·문자 채널로 쏠리지 않게 관계·채널을 따로 배정하고 길이 목표를 똑같이 적용한다 | cfp:docs/guides/qlora-authored/02-cluster-ratios.md:69 | 한 번 관측(소민 r3 집계) | 채택하지 않음(4.1) |
| B-62 | 문자열 보존·해시 일치·스키마 통과·의미 보존 PASS를 인물 품질 합격으로 기록하지 않는다 | cfp:docs/reports/2026-10-29-persona-choice-cause-analysis.md:44<br>cfp:docs/reports/2026-10-29-trait-persona-prompt-audit.md:25<br>cfp:docs/reports/2026-10-29-persona-choice-voice-implementation.md:43<br>외 2개 파일 | 여러 번 반복 관측 | MD-0.3, MD-5.2, MD-9.10 |
| C-01 | 캐릭터성은 같은 상황에서 고르는 행동의 차이로 정의한다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:7<br>gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:82<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:25<br>외 7개 파일 | 여러 번 반복 관측 | MD-1.1 |
| C-02 | 선택은 조건과 동사로 끝나는 관찰 가능한 행동 문장으로 쓴다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:10<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:22<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:66<br>외 2개 파일 | 여러 번 반복 관측 | MD-3.2, MD-4.3 |
| C-03 | 성격 정의는 먼저 알아차리는 것→고르는 행동→말투→잘못된 변형의 네 칸으로 쓴다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:85<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:52<br>mem:MEMORY.md:1908 | 여러 번 반복 관측(기준 사례 세 캐릭터에 적용, 형식 자체의 대조 실험은 없음) | MD-2.4, MD-3.2 |
| C-04 | 특질 축은 켜지는 조건·원하는 결과·꺼지는 조건·반대 근거를 함께 적는다 | gsp:docs/reports/2026-10-20-persona-composition-opus-review-checked.md:3<br>gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:11<br>gsp:docs/reports/2026-10-20-somin-brief-feedback-counterfactual.md:3<br>외 4개 파일 | 한 번 관측(조건당 표본 1, 권고는 여러 문서에서 반복) | MD-3.2, MD-3.7 |
| C-05 | 한 특질을 모든 상황의 최우선 규칙으로 두지 않는다 | gsp:docs/reports/2026-10-19-somin-companionship-neutralization.md:3<br>gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:7<br>gsp:docs/research/somin-cause-opus55-2026-10-18.md:5<br>외 2개 파일 | 실측 대조로 확인(같은 원문·분석·검수; 카드 길이 181자 축소가 함께 바뀜) | MD-3.8 |
| C-06 | 공통 경계(거절·피로·사정 존중)는 성격 우선순위가 아니라 공통 규칙으로 둔다 | gsp:docs/reports/2026-10-22-character-rebuild-distinctness.md:73<br>gsp:docs/reports/2026-10-22-character-rebuild-r2-comparison.md:5<br>gsp:docs/reports/2026-10-22-character-rebuild-r3-comparison.md:87<br>외 1개 파일 | 한 번 관측(원인 후보; 수정 효과 미확인) | MD-3.8 |
| C-07 | 한 답변에는 그 상황에서 작동하는 특질 1~2개만 쓴다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:85<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:18<br>gsp:docs/research/sera-flirting-design-2026-10-02.md:35<br>외 3개 파일 | 여러 번 반복 관측 | MD-3.8 |
| C-08 | 대조 캐릭터 칸을 쓰고 같은 장면 시범으로 겹침을 확인한다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:105<br>gem:charforge/docs/범용화-결과.md:61<br>gem:charforge/docs/차도윤-팩-점검.md:37<br>외 1개 파일 | 한 번 관측 | MD-9.1 |
| C-09 | 표준 상황 사전의 모든 상황에 선택을 정의하고 빈칸을 남기지 않는다 | gem:somin-qlora-project/docs/캐릭터별-현황-2026-10-27.md:105<br>gem:somin-qlora-project/docs/캐릭터-생성-자동화-구현-기획.md:36<br>gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:141<br>외 3개 파일 | 한 번 관측(블라인드 수치는 시드 1·판정 모델 1) | MD-2.4 |
| C-10 | 성격 시험 장면은 기본 반응과 갈리는 갈림을 넣고 정답 단서를 빼서 설계한다 | gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:72<br>gsp:docs/reports/2026-10-20-neutral-card-costed-scene.md:3<br>gsp:docs/reports/2026-10-22-character-rebuild-r2-comparison.md:61<br>외 3개 파일 | 여러 번 반복 관측 | MD-2.4, MD-9.1 |
| C-11 | 모델 기본 반응과 반대 방향을 요구하는 특질은 잘 따라지지 않는다 | gsp:docs/reports/2026-10-21-new-characters-single-call-r2.md:5<br>gsp:docs/reports/2026-10-22-character-rebuild-distinctness.md:65<br>gsp:docs/reports/2026-10-22-character-rebuild-r3-comparison.md:76<br>외 1개 파일 | 여러 번 반복 관측(원인 미검증; 재구축 카드에서 일부 개선) | MD-3.11 |
| C-12 | 결점과 첫 반응을 현재형으로 보존하고 성장 서사로 지우지 않는다 | gsp:docs/guides/character-interview-present-behavior-2026-10-17.md:3<br>gsp:docs/reports/2026-10-16-somin-interview-trait-card.md:3<br>gsp:docs/reports/2026-10-14-somin-stanford-interview.md:39<br>외 5개 파일 | 실측 대조로 확인(앵커 보존 전후 비교; 일부 앵커는 여전히 0%) | MD-3.11 |
| C-13 | 핵심 특성을 막는 억제 조항과 항상·절대 규칙은 상담사식·어른스러운 대사를 만든다 | gsp:docs/reports/2026-10-17-somin-sft-data-diagnosis.md:11<br>mem:MEMORY.md:525<br>gsp:docs/reports/2026-10-08-sera-judge-calibration-v4.md:52 | 실측 대조로 확인(8장면 A/B, 순서를 바꿔도 플래그 약 3배 차이) | MD-3.10 |
| C-14 | 규칙보다 구체 생활 재료를 주고, 정체성 소재는 어울리는 자리에서만 자연스럽게 반복되게 한다 | gsp:docs/reports/2026-10-17-somin-sft-data-diagnosis.md:70<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:46<br>gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:26<br>외 2개 파일 | 한 번 관측 | MD-2.6, MD-4.4 |
| C-15 | 영구 사실 카드는 바뀌지 않는 구체 사실만 짧게, 현실 배경으로 쓴다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:59<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:43<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:46<br>외 1개 파일 | 가설·제안(작성 규칙으로 반복 채택, 대조 실험 없음) | MD-2.6 |
| C-16 | 자기 일정·취향은 만들게 하고, 사용자 정보·공동 과거·합의만 근거 없이 만들지 못하게 좁게 금지한다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:261<br>gem:somin-qlora-project/docs/insights.md:43<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:85<br>외 2개 파일 | 나중에 뒤집힘(넓은 금지 규칙을 좁은 금지 + 자기 일정 허용으로 대체) | MD-1.8, MD-6.3, MD-6.10, MD-6.11 |
| C-17 | 제안·확정·취소, 계획·진행·완료를 구분하고 미정 약속을 확정처럼 말하지 않는다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:200<br>gsp:docs/guides/character-turn-evidence-2026-10-18.md:45<br>gsp:docs/guides/character-action-progress-2026-10-19.md:9<br>외 3개 파일 | 여러 번 반복 관측 | MD-6.10 |
| C-18 | 상대의 표정·감정 원인·신체 상태·속마음을 근거 없이 단정하지 않는다 | gsp:docs/reports/2026-10-21-seoyeon-prompt-restructure.md:31<br>gsp:docs/research/character-generation-insights-2026-10-18.md:148<br>gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:85<br>외 3개 파일 | 여러 번 반복 관측 | MD-6.2, MD-6.13 |
| C-19 | 정정과 부정도 앞선 사실로 하고, 틀린 전제에 동조하거나 없는 발언을 만들어 반박하지 않는다 | gem:somin-qlora-project/docs/insights.md:37<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:97<br>gem:somin-qlora-project/docs/short-prompt-history-training-plan-2026-10-21.md:61<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.11 |
| C-20 | 성격을 드러내려고 없는 사실(핑계 일정·수량·능력·제작 고생)을 만들지 않는다 | gsp:docs/research/character-generation-insights-2026-10-18.md:70<br>gsp:docs/guides/character-interview-current-motives-2026-10-18.md:52<br>gsp:docs/reports/2026-10-21-seoyeon-prompt-restructure.md:31<br>외 4개 파일 | 여러 번 반복 관측(금지 문장 한 줄의 효과는 부분적) | MD-6.12 |
| C-21 | 생성 단계에서 새로 생긴 설정은 정본으로 자동 채택하지 않는다 | gsp:docs/reports/2026-10-14-somin-stanford-interview.md:37<br>gem:somin-qlora-project/docs/rp-training-recipes-2026-10-21.md:74<br>gsp:docs/research/character-generation-cause-literature-2026-10-18.md:28<br>외 1개 파일 | 여러 번 반복 관측 | MD-1.5, MD-2.1 |
| C-22 | 관계 단계는 거리·관심·시간 투자를 바꾸고 성격과 자기 기준은 유지시킨다 | gsp:docs/research/reaction-habits-evidence-2026-10-01/common-criteria.md:82<br>gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:54<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:67<br>외 6개 파일 | 여러 번 반복 관측 | MD-1.1, MD-3.13 |
| C-23 | 관계 단계를 넘는 표현과 진지한 장면의 연애화는 거침없어도 실패로 본다 | gsp:docs/trials/2026-10-01-exp-v4/README.md:67<br>gsp:docs/reports/2026-10-08-sera-judge-calibration-v4.md:46<br>gsp:docs/reports/reaction-choice-r4-2026-10-02.md:23<br>외 2개 파일 | 여러 번 반복 관측(사용자 1인 블라인드 판정 기반) | MD-6.18 |
| C-24 | 장난·도발·질투·애교는 거둘 조건을 정하고, 진지한 장면에서는 장식을 쓰지 않는다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:83<br>gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:22<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:186<br>외 4개 파일 | 여러 번 반복 관측 | MD-4.11, MD-6.18 |
| C-25 | 사과 과잉·잘못 없는 동반 사과·증명 요구·관계 위협을 막고, 상대가 바뀌지 않을 때의 담백한 거리 두기 경로를 준다 | gem:somin-qlora-project/docs/insights.md:9<br>gem:somin-qlora-project/docs/handoff.md:17<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:203<br>외 1개 파일 | 실측 대조로 확인(같은 대본 × 시드 3 × 어댑터 비교; 제안한 세 번째 경로는 미검증) | MD-6.15, MD-6.17 |
| C-26 | 사용자가 먼저 밝힌 선호를 자동으로 따라가는지 점검한다 | gsp:docs/research/somin-cause-opus55-2026-10-18.md:28 | 가설·제안 | MD-9.7 |
| C-27 | core는 신상·선택·말투·공통 사실 규칙의 네 문단으로 쓰고, 말투 문단 끝에 길이·재확인 제한을 둔다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:40<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:46<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:70<br>외 3개 파일 | 여러 번 반복 관측 | 채택하지 않음(4.1) |
| C-28 | 입력은 system → 실제 이력 → 마지막 사용자 말 순서로만 조립하고 프리필·가짜 확인 대사·이력 복사본을 넣지 않는다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:23<br>gem:somin-qlora-project/docs/short-prompt-history-training-plan-2026-10-21.md:11<br>gem:somin-qlora-project/docs/insights.md:263<br>외 2개 파일 | 실측 대조로 확인 | MD-5.1, MD-5.4 |
| C-29 | 시작 장면에는 이미 확인된 사실만 한두 문장으로 쓰고, 정답·다음 전개·메타 지시를 넣지 않는다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:42<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:93<br>gem:somin-qlora-project/docs/short-prompt-history-training-plan-2026-10-21.md:13<br>외 2개 파일 | 여러 번 반복 관측 | MD-5.8 |
| C-30 | 최종 대화 생성은 턴당 한 번의 호출로 하고, 앞선 호출이 만든 목표·행동·요약을 주입하지 않는다 | gsp:docs/guides/character-single-call-prompt-2026-10-20.md:3<br>gsp:docs/status/handoff-2026-10-20-character-generation.md:5<br>mem:MEMORY.md:2293 | 한 번 관측(조건당 1표본) + 사용자 결정 | MD-5.1, MD-5.4 |
| C-31 | 생성 전 준비 단계와 지시 블록을 계속 쌓아 개성 문제를 풀려 하지 않는다 | gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:42<br>gsp:docs/research/character-generation-insights-2026-10-18.md:5<br>gsp:docs/reports/2026-10-19-six-character-decision-pilot.md:3<br>외 4개 파일 | 실측 대조로 확인(같은 검수에서 차이 0) | MD-9.8 |
| C-32 | 런타임에 인터뷰 원문 발췌나 전문가 분석을 덧붙이지 않는다 | gsp:docs/reports/2026-10-22-character-interview-context-comparison.md:5<br>gsp:docs/reports/2026-10-18-somin-expert-comparison.md:7<br>gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:47<br>외 1개 파일 | 실측 대조로 확인 | MD-5.4 |
| C-33 | 출력 길이 계약을 명시하되, 긴 대화에서 답이 점점 길어지는 드리프트를 따로 감시한다 | gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:42<br>gsp:docs/reports/2026-10-10-sera-journey-eval.md:39<br>gsp:docs/reports/2026-10-12-sera-lite-journey-eval.md:35<br>외 1개 파일 | 여러 번 반복 관측 | MD-9.6 |
| C-34 | 지시·카드 안에 넣은 대사 문구는 그대로 복제되거나 퍼진다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:94<br>gem:charforge/docs/범용화-결과.md:27<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:153<br>외 2개 파일 | 여러 번 반복 관측 | MD-1.2, MD-2.9, MD-7.8 |
| C-35 | 지시문에 예시 어법을 넣기 전에 실제 코퍼스에 있는 어법인지 확인하고, 금지형 설명보다 지정형 한 줄로 고친다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:279<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:44 | 실측 대조로 확인(확산 건수와 수정 후 비율 측정) | MD-1.2 |
| C-36 | 사람이 다듬은 예시 대사를 말투 기준으로 쓰되, 복사 대상이 아니라 길이·끊기·어미·높임·세기의 기준으로 준다 | gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:84<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:64<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:139<br>외 3개 파일 | 여러 번 반복 관측 | MD-1.3 |
| C-37 | 예시 묶음은 관계·채널·짧은 받아침·평범한 받아침을 고르게 덮고, 예시 길이를 목표 길이 안에 넣는다 | gem:charforge/docs/캐릭터-팩-작성-가이드.md:140<br>gem:charforge/docs/차도윤-팩-점검.md:22<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:76 | 여러 번 반복 관측 | 채택하지 않음(4.1) |
| C-38 | 실제 대화 말뭉치는 흐름·리듬 참고로만 쓰고, 원문 사람·사실·관계·대사는 옮기지 않는다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:166<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:16<br>gsp:docs/reports/2026-10-17-somin-sft-data-diagnosis.md:13<br>외 3개 파일 | 여러 번 반복 관측 | MD-1.5 |
| C-39 | 말버릇은 사용 조건→하는 일→표현→위치→반복·변주·중단 조건으로 기술하고 여섯 축으로 관찰한다 | gsp:docs/research/dialogue-style-operationalization-2026-10-03.md:11<br>gsp:docs/research/sft-reaction-dataset-design-2026-10-01.md:42<br>gsp:docs/research/reaction-habits-evidence-2026-10-01/common-criteria.md:58<br>외 1개 파일 | 가설·제안(설계안; 분류 일치율 게이트는 통과) | MD-4.3 |
| C-40 | 용어집 1: 높임·종결어미·표기 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:97<br>gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:111<br>gsp:docs/reports/2026-10-16-somin-p106r2-voice-audit.md:11<br>외 6개 파일 | 여러 번 반복 관측(용어 정의 모음) | MD-4.2, MD-4.7 |
| C-41 | 용어집 2: 담화·발화 구조·측정 단위 | gsp:docs/research/dialogue-style-operationalization-2026-10-03.md:33<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:75<br>gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:147<br>외 12개 파일 | 여러 번 반복 관측(용어 정의 모음) | MD-4.3 |
| C-42 | 관계별 높임 기본값을 명시하고 높임 흔들림을 따로 검사한다 | mem:MEMORY.md:217<br>gsp:docs/reports/2026-10-08-sera-r7-polish-gemini.md:16<br>gsp:docs/reports/2026-10-07-g5-gemini-return-review.md:6<br>외 3개 파일 | 여러 번 반복 관측 | MD-4.2, MD-4.10, MD-5.5 |
| C-43 | 통화·대면 채널은 소리로 읽히는 표기만 쓰게 하고 채널 규칙을 메신저 말투보다 우선한다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:75<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:92<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:68<br>외 3개 파일 | 여러 번 반복 관측 | MD-1.6 |
| C-44 | 태도·기분·길이는 서로 다른 언어 자원으로 신호하게 한다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:33 | 나중에 뒤집힘(길이로 태도 등급을 주던 방식과 고정 기분 비율을 화행 비율·상대 대역으로 대체; 대체안은 실측 검정으로 확인) | MD-4.7, MD-4.9 |
| C-45 | 앞머리와 첫마디 분포를 기계로 재고 한 형태로 몰리지 않게 한다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:151<br>gem:somin-qlora-project/docs/캐릭터별-현황-2026-10-27.md:76<br>gem:charforge/docs/범용화-결과.md:19<br>외 1개 파일 | 여러 번 반복 관측 | MD-4.6, MD-6.21, MD-9.9 |
| C-46 | 문장 부호를 기능으로 고르고 진지한 장면에서는 뜻을 흐리지 않는 부호를 쓴다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:89<br>gsp:docs/research/sera-punctuation-and-recurring-style-2026-10-03.md:33<br>gsp:docs/research/dialogue-style-operationalization-2026-10-03.md:35 | 한 번 관측 | MD-4.12 |
| C-47 | 주어·목적어·조사는 문맥에서 복원될 때만 생략하고, 교정 중 생략이 주인과 대비를 지우지 않게 한다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:52<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:72<br>gsp:docs/reports/2026-10-08-sera-r7-rp-audit-gemini.md:26 | 여러 번 반복 관측 | MD-4.10, MD-7.6 |
| C-48 | 담화 표지·호칭어·간투사·자기 수정은 그 자리에서 하는 기능이 있을 때만 쓴다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:54<br>gsp:docs/research/dialogue-style-operationalization-2026-10-03.md:40<br>mem:MEMORY.md:2087<br>외 1개 파일 | 여러 번 반복 관측 | MD-4.10 |
| C-49 | 번역투를 걸러 내되 끝맺지 않은 구어와 실제 발화 분포를 교정된 문장으로 바꾸지 않는다 | gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:132<br>gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:85<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:51<br>외 4개 파일 | 여러 번 반복 관측 | MD-4.10, MD-7.6 |
| C-50 | 반복은 종류를 나눠 보고 기능 없는 같은 틀의 반복만 고친다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:91<br>gsp:docs/research/sera-punctuation-and-recurring-style-2026-10-03.md:5<br>gsp:docs/status/handoff-2026-10-12.md:99<br>외 2개 파일 | 여러 번 반복 관측 | MD-4.8 |
| C-51 | 말버릇과 감정 표지에는 나오는 자리·빠지는 자리·목표 빈도·상한·하한을 함께 둔다 | mem:skills/character-voice-calibration/SKILL.md:24<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:74<br>gem:somin-qlora-project/docs/캐릭터-생성-자동화-구현-기획.md:43<br>외 5개 파일 | 여러 번 반복 관측 | MD-4.11 |
| C-52 | 표지는 사용할 기회를 분모로 세고, 비율은 설명값으로만 쓴다 | gsp:docs/research/dialogue-style-operationalization-2026-10-03.md:113<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:186<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:100<br>외 4개 파일 | 여러 번 반복 관측 | MD-9.9 |
| C-53 | 턴 길이와 짧은 받아침 목표는 다듬은 예시와 같은 연령대 실제 대화를 재서 정하고, 짧음과 내용 누락을 구분한다 | gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:72<br>gem:somin-qlora-project/docs/insights.md:118<br>gem:somin-qlora-project/docs/short-prompt-history-training-plan-2026-10-21.md:118<br>외 3개 파일 | 나중에 뒤집힘(초기 말투 기준의 두 문장 40~60자 중심·단답 금지 — /Users/johnhuh619/projects/gemini-sft-poc/docs/… | MD-4.5, MD-6.7 |
| C-54 | 공통 자연스러움 규칙과 캐릭터 말투 규칙표를 분리한다 | mem:skills/character-voice-calibration/SKILL.md:23<br>gem:charforge/docs/캐릭터-팩-작성-가이드.md:130<br>gem:charforge/docs/범용화-결과.md:40<br>외 2개 파일 | 여러 번 반복 관측 | MD-1.4, MD-4.15 |
| C-55 | 특질을 표현하는 어법은 실제 코퍼스의 형태를 따른다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:22<br>gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:284<br>gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:153 | 실측 대조로 확인 | 채택하지 않음(4.1) |
| C-56 | 질문 끝맺음·시험 질문·임의 조건 덧붙이기를 막고 장난은 현재 말에서 바로 복원되게 한다 | gsp:docs/reports/sera-flirt-linguistic-audit-2026-10-02.md:19<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:53<br>gsp:docs/research/sera-flirting-design-2026-10-02.md:39<br>외 2개 파일 | 여러 번 반복 관측 | MD-4.8, MD-6.8 |
| C-57 | 평범한 답 뒤에 성격 증명 문장을 붙이지 말고, 응수를 먼저 고른 뒤 처음부터 그 말투로 쓴다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:13<br>gsp:docs/research/2026-10-08-sera-sft-authoring-lessons.md:17<br>gsp:docs/research/sera-flirting-design-2026-10-02.md:36<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.6 |
| C-58 | 긴 대화에서 이미 정한 약속을 묻지 않았는데 다시 말하거나 같은 마무리 문장으로 끝내지 않게 한다 | gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:269<br>gem:somin-qlora-project/docs/캐릭터별-현황-2026-10-27.md:73<br>gem:somin-qlora-project/docs/캐릭터-생성-자동화-구현-기획.md:30<br>외 2개 파일 | 실측 대조로 확인(데이터 모양과 core 문장을 함께 바꾼 뒤 200턴 재평가) | MD-6.20 |
| C-59 | 긴 대화 후반에도 성격이 드러날 계기를 장면에 넣고, 긴 문맥에서 감정이 희석되는지 따로 본다 | gem:somin-qlora-project/docs/캐릭터-생성-자동화-구현-기획.md:32<br>gem:somin-qlora-project/docs/캐릭터별-현황-2026-10-27.md:36<br>gem:somin-qlora-project/docs/insights.md:3<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.17, MD-9.6 |
| C-60 | 같은 일을 다시 약속하거나 진행을 예고하지 않도록 상대 발화의 기능을 구분해 응수하게 한다 | gsp:docs/guides/character-action-progress-2026-10-19.md:11<br>gsp:docs/research/character-generation-insights-2026-10-18.md:129<br>gsp:docs/reports/2026-10-19-somin-progress-pilot.md:3<br>외 1개 파일 | 실측 대조로 확인(작은 표본) | MD-6.20 |
| C-61 | 충족된 요청은 멈추고, 거절은 그 요청만 멈추게 하며, 독립된 새 기회에서는 특질이 다시 작동하게 한다 | gsp:docs/guides/character-turn-evidence-2026-10-18.md:47<br>gsp:docs/guides/character-interview-current-motives-2026-10-18.md:31<br>gsp:docs/research/character-generation-insights-2026-10-18.md:64<br>외 2개 파일 | 한 번 관측 | MD-3.7 |
| C-62 | 같은 문장 틀·리듬·꼬리 문장이 굳는 AI 티를 검사한다 | gsp:docs/status/handoff-2026-10-12.md:89<br>gsp:docs/status/handoff-2026-10-13.md:15<br>gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:111<br>외 3개 파일 | 여러 번 반복 관측 | MD-4.8, MD-6.21 |
| C-63 | 부탁을 받아들이거나 거절한 뒤 다시 확인하거나 못 박지 않게 하고, 투정 표현이 한쪽으로 모이는지 본다 | gsp:docs/reports/2026-10-14-somin-close-friend.md:57<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:90<br>gsp:docs/reports/2026-10-17-somin-sft-data-diagnosis.md:63 | 한 번 관측 | MD-6.21 |
| C-64 | 기분은 해설하지 말고 표현 방식으로 보여 주며, 그 원인은 장면이 제공한다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:106 | 한 번 관측 | MD-4.9 |
| C-65 | 호감은 이유와 결론을 다 설명하지 말고 구체적 순간 하나로 드러내며, 같은 이유·제안을 되풀이하지 않는다 | gsp:docs/research/sera-flirting-design-2026-10-02.md:13<br>gsp:docs/reports/2026-10-21-seoyeon-prompt-restructure.md:15 | 한 번 관측 | MD-6.18 |
| C-66 | 대사의 첫 행동뿐 아니라 마지막 한마디도 캐릭터 행동으로 설계하고 판정한다 | gsp:docs/reports/2026-10-22-character-rebuild-r3-comparison.md:8<br>gsp:docs/reports/2026-10-22-character-rebuild-r2-comparison.md:65 | 한 번 관측 | MD-3.14 |
| C-67 | 상대 대사·행동을 대신 쓰지 않고, 대사 밖 행동 지문으로 성격을 보강하지 않는다 | gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:52<br>gsp:docs/research/sera-flirting-design-2026-10-02.md:43<br>gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:79<br>외 2개 파일 | 여러 번 반복 관측 | MD-6.1 |
| C-68 | 내용과 말투를 한 번에 쓰게 하지 말고, 내용 뼈대를 먼저 만들고 말투를 따로 입힌다 | gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:7<br>gem:somin-qlora-project/docs/캐릭터-생성-자동화-구현-기획.md:28<br>gem:somin-qlora-project/docs/캐릭터-생성-프로젝트-맥락.md:83<br>외 3개 파일 | 여러 번 반복 관측(이 방식으로 만든 데이터의 학습 효과는 별도 확인 대상) | MD-7.5 |
| C-69 | 다듬기·윤문·재작성 지시가 고유 표지와 성격 강도를 지우지 않게 보존 조건을 명시한다 | gsp:docs/reports/2026-10-16-somin-p106r2-voice-audit.md:7<br>gsp:docs/trials/2026-10-01-exp-v4/README.md:56<br>gsp:docs/reports/reaction-choice-r3-character-review-2026-10-01.md:5<br>외 3개 파일 | 실측 대조로 확인 | MD-7.6 |
| C-70 | 금지만 주지 말고 허용된 성격 행동을 분명히 요구하되, 상세 기준을 통째로 넣는 지시는 최소 지시와 비교해 고른다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:238<br>gsp:docs/reports/2026-10-08-sera-judge-calibration-v4.md:51<br>gsp:docs/reports/2026-10-08-sera-r7-polish-gemini.md:7 | 여러 번 반복 관측 | MD-1.9, MD-7.2 |
| C-71 | 수정 지시는 결함 목록이 아니라 판정 근거와 함께 주고, 수치 기준은 작성 모델의 자가 측정 대신 기계 검사로 확인한다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:186<br>gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:153 | 여러 번 반복 관측 | MD-7.9 |
| C-72 | 수리는 대화 전체 맥락에서 하고, 넣는 작업 뒤에 걷어내는 라운드를 두며, 교정 뒤 의미를 다시 검사한다 | gsp:docs/guides/dialogue-distribution-authoring-2026-10-03.md:172<br>gsp:docs/research/2026-10-08-sera-sft-authoring-lessons.md:27<br>gem:somin-qlora-project/docs/캐릭터-SFT-데이터셋-구축-현행.md:349<br>외 2개 파일 | 여러 번 반복 관측 | MD-7.6 |
| C-73 | 작성 모델의 유창함을 맥락 정확성으로 믿지 말고, 첫 12개를 먼저 승인받은 뒤 확대한다 | gem:somin-qlora-project/docs/insights.md:215<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:159<br>gem:somin-qlora-project/docs/캐릭터-SFT-구축-템플릿.md:148<br>외 1개 파일 | 여러 번 반복 관측 | MD-0.5, MD-7.11 |
| C-74 | 캐릭터가 AI처럼 무너지기 쉬운 압력 상황을 시험 장면에 섞는다 | gsp:docs/advice/advice-1.md:110<br>gsp:docs/advice/2026-10-07-surface-authoring-model-advice.md:100<br>gsp:docs/research/sera-dialogue-style-feedback-review-2026-10-03.md:13<br>외 1개 파일 | 가설·제안(프로브 1회 관측 포함) | MD-9.7 |
| C-75 | 평가는 수정 없는 첫 수신 대사로 하고, 행동 판정을 카드 대조보다 먼저 고정하며, 같은 장면의 중립을 분포로 비교한다 | gsp:docs/status/handoff-2026-10-20-character-generation.md:22<br>gsp:docs/reports/2026-10-20-persona-composition-opus-review.md:136<br>gsp:docs/guides/character-decision-disposition-2026-10-19.md:23<br>외 5개 파일 | 여러 번 반복 관측 | MD-7.9, MD-9.1, MD-9.3, MD-9.5, MD-9.8 |
| C-76 | LLM 판정자를 사용자 선호의 대리로 쓰지 않는다 | gsp:docs/reports/2026-10-08-sera-judge-calibration-v4.md:3<br>gsp:docs/reports/2026-10-08-sera-data-ceiling-check.md:3<br>gsp:docs/reports/2026-10-09-sera-r6-sft-final.md:42<br>외 6개 파일 | 실측 대조로 확인 | MD-9.3 |
| C-77 | 말투·선택·사실·반복·태도를 따로 채점하고 하나의 장점으로 다른 결함을 상쇄하지 않는다 | gsp:docs/guides/korean-dialogue-authoring-2026-10-02.md:95<br>gsp:docs/guides/character-interview-present-behavior-2026-10-17.md:29<br>gsp:docs/research/character-factory-choice-learning-2026-10-01.md:132<br>외 4개 파일 | 여러 번 반복 관측 | MD-9.4 |
| C-78 | 태도·관계 신호는 대화 평균이 아니라 응답 하나 단위로 요구하고 판정한다 | gsp:docs/reports/sera-sft-v5s-evaluation-2026-10-04.md:139<br>gsp:docs/reports/sera-sft-v5s-mentor-summary-2026-10-04.md:53<br>gsp:docs/reports/sera-dialogue-style-v5s-insight-audit-2026-10-04.md:28<br>외 1개 파일 | 실측 대조로 확인(학습 실험 결과이나 평가 단위 교훈은 프롬프트 평가에도 적용) | MD-9.4 |
| C-79 | 연속 대화 평가는 실제 생성 이력을 누적하고 턴마다 시드를 바꾼다 | gem:somin-qlora-project/docs/insights.md:15<br>gem:somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md:236<br>gem:somin-qlora-project/docs/short-prompt-history-training-plan-2026-10-21.md:120<br>외 1개 파일 | 실측 대조로 확인 | MD-9.6 |

## 3. 충돌과 해결

| 번호 | 부딪힌 교훈 | 쟁점 | 해결 | 판단 근거 | 반영 규칙 |
|---|---|---|---|---|---|
| 1 | C-36, C-02(사람이 다듬은 실제 예시가 추상 지시보다 잘 먹힌다), B-05(긴 프롬프트에 예시 대화 4개) 대 S-1, S-2, A1-39, A2-35, B-04, C-34 | 예시 대사를 프롬프트와 지시문에 넣을 것인가 | 생성 지시문과 대화 프롬프트에는 예시를 넣지 않는다. 사람이 다듬은 예시는 검토와 평가의 기준 자료로만 둔다 | 첫째, 과제의 사용자 원칙(예시를 넣으면 생성물이 복제한다). 둘째, S-1은 2026-11-05 실측 세 경로에서 대화 프롬프트 인용 문장의 복제를 확인했다. S-2와 B-01의 생성 지시문 틀 복제는 예시 제거 대조가 없는 가설이므로 본문 이유 문장은 S-1에 한정했다(review-1 P3-4). B-08은 중간 단계 예시가 최종 말투를 개선하지 못함을 대조로 확인했다. B-05는 D-0070으로 뒤집혔다 | MD-1.2, MD-1.3, MD-5.4 |
| 2 | 현재 기획 지시문의 모든 상황 firstMove 상이 요구, A1-02 대 B-37, C-22 | 모든 상황에서 인물이 달라야 하는가 | 공통 기본기 상황은 같은 행동을 허용하고 차이는 우선순위가 부딪히는 상황에서 본다 | B-37·C-22가 정상 수용을 차이 부족으로 잘못 읽은 사례를 기록했다. A1-02는 압력 상황 비교라 양립한다 | MD-1.1, MD-2.3, MD-9.1 |
| 3 | B-13, C-27, C-42(말투 칸에 어미와 높임을 적는다), S-3의 단서(다른 칸에 짧은 말 단위 허용) 대 S-3 본문, A1-22, S-1 | 성격 시트 말투 칸이 종결 형태를 정해도 되는가 | 등급은 관계 설정과 기획 말투 요약이 소유하고 개인어 칸은 종결을 기능으로만 쓴다. 짧은 말 단위도 넣지 않는다 | S-3 실측 대조(13/13 → 3~4/13), A1-22 서비스 구조, S-1 복제 관측. 기능 서술 방식 자체는 대조가 없어 검증 대기로 둔다 | MD-4.1, MD-4.2, MD-4.7 |
| 4 | A1-15, A2-12(결함을 지우지 않는다) 대 A1-31, A1-19, B-23(과잉 적용) | 결함을 남기면 매 턴 결함이 나오는가 | 결함은 시트에 남기되 발동 조건이 성립할 때만, 한 턴 특질 한두 개, 균형 조항 | A1-31 실측(축객 5/72 → 1/72), A2-56 균형 조항 통과 | MD-2.5, MD-3.8, MD-3.10 |
| 5 | A1-14, A2-15(수습은 권리 반환과 자기 비용) 대 A1-47(실제 잘못은 짧게 인정하고 멈춘다) | 수습을 대화에서 얼마나 길게 하는가 | 시트에는 수습의 내용을, 대화 한 턴에서는 그 행동만 짧게 | 현행 서비스 프레임 정합 | MD-3.5, MD-6.15 |
| 6 | A2-04, C-70(금지문은 약하다) 대 A2-04의 반대 관측(금지 줄을 줄이자 상담원 말투), C-13 대 C-24, C-25 | 금지문을 쓸 것인가 | 바깥 선은 금지로(6.A), 그 안쪽은 긍정형 습관으로(6.B). 기존 금지 줄은 대신할 습관과 비교한 뒤 지운다 | 과제 지시와 A2-04 반복 관측. review-1 P2-5에 따라 6절을 두 층으로 나눴다 | MD-1.8, MD-1.9, 6절 |
| 7 | A2-27(말투 칸에 행동 습관 서술이 효과) 대 A2-01(행동을 적으면 말버릇이 된다) | 말투 칸에 행동을 쓸 것인가 | 습관은 서술하되 조건을 좁히고 예시 없이 범주로 쓴다 | 둘 다 실측. A2-03은 조건 축소 실측 | MD-4.13, MD-4.14, MD-3.8 |
| 8 | A1-21, A2-29(개념어 허용) 대 A1-58, A1-25(쉬운 문장, 용어 이점 미확인) | 개념어를 시트에 쓸 것인가 | 인물 주어의 쉬운 문장이 기본이고 개념어는 설명 어휘로만 | A2-29 누출 0, 효과 중립 실측 | MD-3.15, MD-4.15 |
| 9 | 서비스 문서 v27 기준(4문장, 400자), 현재 공통 규칙(조금 길어질 수 있다), C-53(복잡한 상황은 상한 해제) 대 A1-43, A2-59(3문장 상한) | 한 턴 길이 상한 | 대개 한두 문장, 많아도 세 문장 | 현행 프레임 v40과 A1-43 실측. A2-59의 반대 관측(사용자가 긴 쪽을 고름)은 길이를 상한으로만 쓰는 방식으로 반영 | MD-6.7, MD-9.9 |
| 10 | C-16(사용자가 처음 꺼낸 모순 없는 공동 과거는 받아들인다) 대 S-11, A1-49 | 이력에 없는 공동 기억 주장 | 두 경우로 나눈다. 기록과 대조해 틀린 주장은 받아들이지 않는다(MD-6.3). 기록이 다루지 않는 과거는 사실로 확정하지 않고 확인할 수 없다는 태도로 받으며 세부를 덧붙이지 않는다(MD-6.11) | S-11 실측(8/8 수용 실패)은 이력과 대조해 틀린 주장의 경우만 받친다. 기록 밖 과거는 S-11이 시험하지 않았으므로 C-16의 수용과 A1-49의 근거 원칙 사이에서 확정하지 않는 쪽을 택했고, 이 경우의 제품 판단은 사람이 정한다(검증 대기, review-1 P2-15) | MD-6.3, MD-6.11 |
| 11 | B-50(생성과 검토를 다른 계열로) 대 S-12 | 생성 단계 사이 검토 | 검토·수정 고리를 두지 않고 결정적 검사와 사람 관문. 다른 계열 모델은 평가 보조에만 | S-12 반복 관측(K-0072, D-0086), 최신 | MD-7.8, MD-9.3 |
| 12 | 현재 공통 절차의 검사 통과까지 반복, B-35 대 B-49, B-34 | 자가 수정 범위 | 형식과 표기 검사에만 자가 수정, 의미 실패는 보존 | B-34 합성 반례 | MD-7.9 |
| 13 | S-7(상황·조건을 한 단위로) 대 B-04(내부 조건 필드 직렬화 금지) | 선택 경향 조립 형식 | 계기, 첫 행동, 전환은 한 줄로 넣고 적용·비적용 표, 검토용 칸, ID, 출처는 뺀다 | S-7 조립 수정 시험(K-0073), B-04 확정 결정(D-0070) | MD-3.2, MD-5.3 |
| 14 | A1-32, A2-21(행동 루프 주입, 뒤집힘) 대 A2-10(인과 묶음이 저작 단위) | 행동 루프를 어디에 쓰는가 | 인과 묶음은 저작 도구, 대화 프롬프트에는 경향 문장 | A1-31 실측, 현행 v6·v40 | MD-2.2, MD-5.4 |
| 15 | A1-38, A2-46(고정 공개 한도, 뒤집힘) | 깊은 사정의 공개 방식 | 지금 마음과 믿게 되면 꺼낼 이야기로 대체, 사정이 결함보다 먼저 풀리지 않게 하는 관측만 유지 | 관계 설정 v3 | MD-5.7 |
| 16 | C-44, C-53(초기 길이 기준, 뒤집힘), C-56(초기 반문 비율 목표) | 길이와 형식의 수치 목표 | 길이는 상한, 태도는 화행, 기분은 덧붙임 양. 비율 목표를 의무로 두지 않는다 | C-44 대체안 실측 검정 | MD-4.5, MD-4.9, MD-6.7 |
| 17 | C-70 내부(저작은 수치 발주, 윤문은 최소 지시), C-71 | 지시문에 수치를 쓸 것인가 | 허용된 성격 행동은 분명히 요구하고 수치 기준은 기계 검사로 | C-71 반복 관측 | MD-7.2, MD-7.9 |
| 18 | 현재 기획 지시문(브리프 문장을 대표 대사 기준으로) 대 S-6 | 브리프 문장과 영상통화 규칙 | 태도를 규칙 안의 다른 표현으로 옮기고, 대표 대사는 다음 단계 입력과 대화 프롬프트에서 뺀다 | S-6 관측(K-0075), C-34 생성 입력 복제 | MD-2.8, MD-2.9 |
| 19 | B-03(예시 선정 기준) 대 B-04(대화 본문에 예시 없음) | 예시 선정 기준의 쓰임 | 선정 기준은 검토·평가 자료에만 | B-04 확정 결정 | MD-1.3 |
| 20 | A2-47(추론 상향을 연기 개선책으로 쓰지 않는다) 대 A2-60(추론을 낮추자 외국 낱말이 줄었다) | 추론 설정 | 연기 개선책으로 쓰지 않고 외국 낱말은 출력 검사 지표로 | 서로 다른 지표의 실측 | MD-5.4, MD-9.9 |
| 21 | A1-22(개인어는 관계 단계와 무관), S-18(관계 설정 소유) 대 이전 본문 MD-4.3의 감정과 관계에 따른 변화 항목, A2-32(호감 장면에서 유지할 개인어) | 관계 단계별 말투 변화를 어느 칸이 소유하는가 | 개인어 칸은 감정과 압력에 따른 변화와 호감이 올라도 유지할 개인어만 쓰고, 관계 단계에 따라 달라지는 표현은 관계 설정의 표현 변화 칸이 소유한다 | A1-22 전후 비교와 서비스 v40 PERSONA / VOICE 머리말(말버릇은 관계 단계와 무관), MD-1.4 소유 원칙(review-1 P1-1) | MD-4.3, MD-4.13, MD-5.5 |
| 22 | C-42(관계별 허용 예외로 장난 존댓말을 명시), C-40(반말 고정과 장난 존댓말의 양립은 별도 판단) 대 A1-23, A2-24(한 턴 혼용 금지) | 반말 관계의 빌려 쓴 존대가 혼용인가 | 관계 설정이 허용 예외로 적은 경우에만 쓰고, 그 관계의 등급 검사는 위반으로 세지 않는다(MD-4.2 사람용 문장, review-2 P3-1). 지금 계약에서는 허용 예외를 addresseeStance 문장에 쓴다 | C-42 반복 관측(review-1 P2-1). 예외를 적지 않은 관계에서는 A1-23 혼용 금지가 그대로 선다 | MD-4.2, MD-5.5 |
| 23 | B-39(선택 규칙 여덟 항목, 가설) 대 S-7(한 줄 조립), B-04(내부 필드 직렬화 금지), 형성 첫 통과 0/4 관측 | 선택 규칙 항목을 모두 필수로 할 것인가 | 계기, 첫 행동, 전환, 비적용 경우만 필수로 하고 가치, 비용, 잘못된 변형은 검토용 칸으로 둔다. 필수 여부는 소량 표본 뒤 정한다 | B-39가 가설이고 첫 통과가 0/4였다(review-1 P1-5). 조립 코드가 한 줄로 잇는 칸만 대화 프롬프트에 닿는다 | MD-3.2, MD-5.3 |
| 24 | 6절 긍정형 전환(MD-1.9, A2-04: 금지문은 약하다) 대 C-25, B-29, B-33, A2-51, A1-47, C-56, A2-53, B-31, C-58, B-27, C-57, A1-46(반복·실측 교훈의 제한) | 긍정형으로 바꾸며 제한을 지워도 되는가 | 긍정형으로 쓸 수 있으면 하는 행동으로 쓰고, 쓸 수 없는 제한은 금지절로 남긴다. 동반 사과, 감정 주체, 진정 요구, 조심 약속, 시험 질문, 약속 재확인의 만, 외부 조회, 성격 증명 덧붙임, 작가·진행자 자리를 되살렸다 | 반복·실측 교훈이 가설·제안 수준의 표현 원칙보다 앞선다. MD-1.9는 기존 금지 문장을 비교 없이 지우지 말라고 한다(review-2 P1-2) | MD-6.5, MD-6.6, MD-6.8, MD-6.12, MD-6.14, MD-6.15, MD-6.17, MD-6.20 |
| 25 | A1-43(길이 기준을 생성 직전에 둔다) 대 A1-33과 서비스 코드(지금 마음 블록에 믿게 되면 꺼낼 이야기와 길이를 함께 넣고 관찰을 그 뒤에 둔다) | 매 턴 블록의 순서와 내용 | 지금 마음, 허용된 턴의 믿게 되면 꺼낼 이야기, 관찰, 길이를 두고 길이 줄을 사용자 말 바로 앞에 둔다 | 길이 위치는 A1-43 실측 대조, 블록 내용은 A1-33 실측 대조와 서비스 코드. 서비스의 관찰·길이 순서 변경은 서비스 저장소 할 일로 둔다(review-2 P2-4) | MD-5.9 |
| 26 | B-40(씨앗 고정 요구 보존) 대 이전 MD-2.2(원하는 것을 후보마다 다르게) | 원하는 것을 후보마다 바꿀 수 있는가 | 씨앗이 정했으면 모든 후보가 지키고 방어와 선택에서 갈라지며, 정하지 않았으면 후보마다 다르게 둔다 | MD-2.1 고정 요구 원칙(review-2 P2-5) | MD-2.1, MD-2.2 |

해결한 충돌: 26건(review-1 이후 21~23번, review-2 이후 22번 갱신과 24~26번 추가).

## 4. 채택하지 않은 교훈

### 4.1 본문에 반영하지 않은 교훈(8개)

| 교훈 | 이유 |
|---|---|
| A1-08 실존 인물 결함 상품화 합의 | 범위 밖. 공장은 허구 인물만 만들고 현재 기획 지시문도 실존 인물 이름을 금지한다. 실존 인물 경로를 열면 계약 절차와 함께 별도 지시서로 다룬다. 강도도 가설·제안이다 |
| A1-09 실존 인물 인과를 사건 회상에서 추출 | 범위 밖(위와 같음). 사건과 동사로 쓰라는 일반 원칙은 A1-12와 A2-11을 근거로 MD-3.2에 이미 있다 |
| A1-10 실존 인물 사실의 출처·공개 등급 | 범위 밖(위와 같음) |
| A1-26 실존 인물 말투를 녹음에서 추출 | 범위 밖(위와 같음) |
| B-61 보강 자료의 관계·채널 배정과 길이 목표 | 학습 데이터 전용 |
| C-27 대화 system 고정부를 네 문단으로 구성 | 서비스 여덟 칸 조립(B-45, A2-19 실측)으로 대체됐다. 길이와 재확인 제한은 다른 근거로 MD-5.9와 MD-6.20에 들어갔다 |
| C-37 예시 묶음의 관계·채널·길이 분포 | 학습·말투 팩 전용. 지시문과 대화 프롬프트에 예시를 넣지 않으므로 옮길 곳이 없다(review-1도 타당하다고 확인) |
| C-55 특질 표현 어법을 코퍼스 형태에 맞춤 | 학습 데이터 저작의 어법 단위 지시. 예시 없이 범주로 쓰는 지시문에 옮길 수 없고 번역투 회피(MD-4.10)와 일부만 겹친다 |

### 4.2 일부만 반영하고 나머지를 채택하지 않은 교훈

| 교훈 | 채택하지 않은 부분 | 이유 | 반영한 부분 |
|---|---|---|---|
| A1-32 | 루프 결정 순서와 기능 슬롯 카탈로그 | 나중에 뒤집힘 | 한 턴에 주된 반응 하나(MD-6.6) |
| A1-38 | 고정 공개 상한 | 나중에 뒤집힘 | 사정이 결함보다 먼저 풀리지 않게(MD-5.7) |
| A1-42 | 문장 선택 후처리 호출 | 나중에 뒤집힘 | 상한만으로 길이가 보장되지 않는다(MD-6.7, MD-9.9) |
| A1-43 | 초기 120~250자 목표, 4문장·400자 허용 | 나중에 뒤집힘 | 3문장 상한(MD-6.7) |
| A2-21 | 행동 루프 매 턴 주입 | 나중에 뒤집힘 | 인과 묶음은 저작 도구(MD-2.2) |
| A2-30 | 말하는 방식 한 문장을 매 턴 블록에 넣기 | 나중에 뒤집힘 | 말이 늘고 주는 조건(MD-4.5) |
| A2-37 | 작가 수락 프리필 | 나중에 뒤집힘 | 비교 전에는 넣지 않는다(MD-5.4) |
| A2-46 | 고정 공개·애정 한도 | 나중에 뒤집힘 | 지금 마음과 믿게 되면 꺼낼 이야기(MD-5.7) |
| B-05 | 예시 대화 4개 삽입 | 나중에 뒤집힘(D-0070) | 예시 대화 금지(MD-5.4) |
| B-39 | 여덟 항목 전체의 필수화 | 가설이고 첫 통과 0/4(3절 23번) | 필수 네 항목과 검토용 칸(MD-3.2) |
| C-16 | 사용자가 처음 꺼낸 공동 과거의 수용 | 기록 밖 과거는 확정하지 않는 쪽을 택함(3절 10번) | 자기 일정 허용과 좁은 금지(MD-6.10), 세부를 덧붙이지 않음(MD-6.11) |
| C-44 | 길이로 태도 등급 주기 | 나중에 뒤집힘 | 자원 분리(MD-4.9) |
| C-53 | 초기 두 문장 40~60자, 단답 금지 | 나중에 뒤집힘 | 짧음과 누락 구분(MD-6.6, MD-6.7) |
| C-56 | 초기 반문 끝맺음 비율 목표 | 비율 강제 불채택 | 시험 질문 습관 회피(MD-6.8) |
| S-3 | 다른 칸에 짧은 말 단위를 적는 허용 구절 | S-1 복제 관측과 충돌(3절 3번) | 말버릇 칸은 등급과 종결을 정하지 않는다(MD-4.1) |
| C-36 | 예시 대사 약 20개를 렌더러 기준으로 주기 | 학습 데이터 렌더링 맥락(3절 1번) | 기준 자료로 보관(MD-1.3) |

채택하지 않은 교훈 수: 전부 채택하지 않은 교훈 8개, 일부만 채택하지 않은 교훈 16개.

## 5. 용어집 용어별 출처 교훈

| 용어 | 출처 교훈 |
|---|---|
| 상대높임 등급 | S-3, S-4, A2-24, C-40, B 용어표(말높임). 세 갈래 한정은 review-1 P1-3과 표준 국어문법의 등급 체계 |
| 하십시오체 | S-3, S-4 |
| 해요체 | S-4, C-40 |
| 해체 | C-40(해체 반말), B 용어표 |
| 해라체 | C-40(해체 반말 정의가 반말 종결 전반을 포함), review-1 P1-3(표준 등급 체계) |
| 한다체 | C-40, C-49. 정의는 review-1 P1-3에 따라 해라체 평서형의 문어 사용으로 고침 |
| 음슴체 | C-40 |
| 주체높임 | review-1 P2-2(표준 국어문법). 등급 혼용 오탐 방지를 위해 넣음. 교훈에 직접 정의는 없음 |
| 청자 대우법 | A1-22, A2-23, A2 용어표. 표준 의미(상대높임법)는 사람용 문장으로 병기(review-1 P2-2, review-2 P2-1) |
| 호칭어 | C-41, A2-31, A1-27 |
| 지칭어 | C-41(호칭어 야, 너의 쓰임), review-1 P2-2 |
| 종결어미 | S-3, C-40, B 용어표 |
| 문장 유형(문장 종결법) | C-40(명령형·설명조 종결), C-41(물음표의 기능). 이름은 review-1 P2-2에 따라 바꿈 |
| 확인 종결(확인 의문) | C-40(상대 확인과 공동 이해를 조정하는 종결) |
| 근거절 덧붙임 | C-40, C-41(덧붙임), C-44 |
| 개인어(이디올렉트) | A1-22, A2-23, A2-26, A2 용어표. review-2 P2-7에 따라 정의는 범위만 두고 항목은 MD-4.3이 소유 |
| 사용역 | A1-25, A2-28, A1-46, A2-49 |
| 어휘장 | A2-26, B-13(lexicon), C-39 |
| 담화 표지 | A1-25, C-41, C-48. 대인 기능은 review-1 P3-9 |
| 간투사 | A1-25, A2-28, C-48 |
| 맞장구(백채널) | A1-25, A2-28, C-41 |
| 짧은 받아침 | B 용어표, C-53, S-16 |
| 조사 생략 | A1-25, A2-28 |
| 성분 생략 | C-41, C-47 |
| 구어 축약 | A1-25, A2-28 |
| 후치(우측 전위) | A1-25, A2-28, C-41 |
| 비완결 발화 | A1-25, C-49 |
| 앞머리 | C-41, C-45 |
| 턴(말차례) | C-41(왕복과 발화 차례), A1-44 |
| 화행 | A1-44, A1-21, C-41, A2 용어표 |
| 주된 화행 | A1-44 |
| 화행 쌓기 | A1-44, B-30 |
| 턴 넘기기 | A1-44, B 용어표(차례를 넘긴다) |
| 턴 점유 | A1-44(발언권 점유) |
| 발화 길이 | A1-43, C-53, A2 용어표 |
| 반문·되묻기 | A1-25, A2-50, C-41, B 용어표 |
| 되받는 반복 | C-41, C-50 |
| 강조 반복 | C-41, C-50 |
| 자기 수정 | C-41, C-48 |
| 정식화 | A2-50, A2 용어표. 평가까지 넓힌 것은 이 지시서의 확장(review-1 P3-9) |
| 응대 행위 | A2-49, A2-50, A2 용어표 |
| 자기 서술 | A2-50, A2 용어표 |
| 대등한 받기 | A2-50, A2 용어표 |
| 표현 강도 | B-21, B 용어표 |
| 운율 | S-16 |
| 번역투 | C-41, C-49, B-18 |
| 말버릇(습관 표지) | C-39, C-51, B-16 |
| 장식 표지 | B 용어표(장식), C-51, review-1 P3-9 |

용어집에는 48개 용어를 두었다. 과제가 검토를 요구한 항목은 모두 교훈에 근거가 있어 넣었다. 상대높임 등급(하십시오체·해요체·해체), 청자 대우법, 종결어미 유형, 개인어, 사용역, 어휘장, 담화 표지, 간투사, 맞장구, 조사 생략, 구어 축약, 후치, 비완결 발화, 화행과 턴 넘기기, 발화 길이와 턴 점유, 반문·되묻기, 강조·반복, 운율이 여기에 든다. 운율은 S-16에 따라 표기 기호로 지시하지 않는다는 규칙(MD-4.12)과 함께 정의했다. review-1에 따라 해라체, 주체높임, 지칭어, 음슴체, 턴(말차례), 장식 표지를 더했고 서법을 문장 유형(문장 종결법)으로 바꿨다. 측정 용어(말풍선 반복률, 절 수, 끝 글자 근사 등, C-41)는 본문 규칙에 쓰이지 않아 넣지 않았다.

## 6. 부록: 현재 공장 지시문과의 차이

점검 기준: 2026-11-05 작업 트리(커밋하지 않은 변경 포함)를 직접 읽었다. 대상은 /Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/prompts/ 와 /Users/johnhuh619/projects/character-factory-poc/src/character_factory_poc/resources/actor-system-rules-v2.md 다. B 묶음의 현재 지시문 점검과 S 묶음 실측, review-1을 바탕으로 이 지시서와 어긋나는 곳만 적었고 고치지는 않았다. 판정·데이터·이미지·장면 단계 지시문(checkpoint_pair_judge, curator, data_*, eval_*, image_judge, pose_director, probe_judge, scene_scout, scene_writer, scout)은 캐릭터 텍스트 생성 단계가 아니어서 점검하지 않았다. 줄 번호는 점검 시점 기준이다. 아래 모든 지시문에 공통으로 사람용 표시와 검증 대기 표시가 없으므로, 발췌로 바꿀 때 MD-0.2와 MD-0.5에 따라 사람용 문장을 걸러야 한다.

### plan_variants.md (기획 변형 초안)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 20~21 | 모든 상황에서 firstMove가 변형마다 달라야 한다고 요구한다 | MD-1.1, MD-2.3 | B-37 |
| 22~23 | 상대가 늦는 상황의 순서 있는 행동 예시 세 갈래가 남아 있다. 원인 분석이 지목한 앵커링 후보이며 v4·argon-v2 후보에서 같은 틀이 재현됐다 | MD-1.2, MD-7.1 | S-2, B-01 |
| 13~14, 33 | 브리프 말투 문장을 voiceExamples 기준으로 삼고 voiceSummary에 어미와 반응 순서를 쓰게 한다. 본문은 기획 초안의 말투 요약을 등급 이름과 기능 서술로 한정한다 | MD-2.8, MD-4.2, MD-4.7, MD-6.6 | S-1, S-3, B-30 |
| 18~25, 27~34 | 압력 상황, 결함과 그 이득·비용, 핵심 긴장, 선택이 바뀌는 조건 요구가 없다 | MD-2.2, MD-2.4, MD-2.5, MD-3.4 | S-19, A1-03, A2-12 |
| 36~38 | profileCard에 mbti를 정하게 한다. 유형명은 시트와 프롬프트에 넣지 않는다. 현행 actor_persona 조립은 profileCard를 쓰지 않지만 s8 투영 필드 목록(source.py 15~29)에는 profileCard와 voiceExamples가 있어 이 투영을 받는 단계 입력에 들어갈 수 있다 | MD-2.7, MD-2.9 | A1-05, A2-18 |
| 64 | 카메라 관찰을 괄호 속 예시 어구로 나열한다 | MD-1.2 | S-1, S-2 |
| 해당 없음 | 지시문 메타 문장을 산출물에 옮기지 말라는 지시가 없다 | MD-7.7 | S-15 |

### seed_requirements.md (씨앗 요구 추출)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 9 | 함께 적힌 조건을 설명하려고 구체 성격 조합을 예로 든다 | MD-1.2, MD-7.1 | S-2 |
| 15 | 카메라 관찰 예시 어구 | MD-1.2 | S-1 |

요구 분리와 역방향 확인(MD-2.1)은 반영돼 있다.

### deck_plan_voice.md (말투 확정)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 3 | 설정 검토를 거친 draft를 전제한다. D-0086으로 검토 고리는 빠졌지만 문장이 남아 있다 | MD-7.8 | S-12 |
| 4 | voiceExamples를 대표 대사로 완성하게 하면서, 대표 대사가 검토용 초안이고 다음 단계 입력과 대화 프롬프트에서 빠진다는 지위를 적지 않는다 | MD-2.9 | B-09, S-1, C-34 |
| 9~10 | 어미 형태를 따옴표로 예시하고 섞어 적지 말아야 할 표현을 따옴표로 인용한다. 등급 혼용의 범위(해라체, 주체높임 제외)도 없다 | MD-1.2, MD-4.2, MD-7.1 | S-1, A2-36, C-40 |
| 11~12 | 브리프 태도를 괄호 속 예시 어구로 든다 | MD-1.2 | S-2 |
| 해당 없음 | voiceSummary를 어떤 항목(MD-4.3)으로 채울지, 말버릇 자리와 빈도, 운율을 표기로 지시하지 말라는 기준이 없다. Argon 결과에서 응답 대부분이 말줄임표로 시작했다 | MD-4.3, MD-4.11, MD-4.12 | B-13, C-51, S-16 |
| 해당 없음 | 메타 문장 누출 금지가 없다 | MD-7.7 | S-15 |

### profiler.md (성격·특질 시트)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 7 | 낱말 나열 반례와 문장 형식을 따옴표로 예시한다 | MD-1.2, MD-7.1 | A2-36, S-2 |
| 8~11 | 선택 규칙 칸이 필수 네 항목과 검토용 칸으로 나뉘어 있지 않고, 판단 상황을 따옴표 예시(관계 확답 상황)로 든다 | MD-3.2, MD-1.2, MD-7.1 | B-39, S-2 |
| 12 | 질문 습관에 화행 기능, 빈도 상한, 반복 금지 기준이 없고 말버릇에 자리와 빈도 기준이 없다 | MD-3.9, MD-4.4, MD-4.11 | S-10, B-16, C-51 |
| 13 | 칸 안에 짧은 예시 말을 넣는 것을 허용한다 | MD-1.2 | S-1 |
| 21~22 | 경향과 공식을 구분하는 메타 문장이 그대로 있고 산출물에 옮기지 말라는 지시가 없다. argon-v2 VOICE 칸에 이 문장이 섞였다 | MD-7.7, MD-4.14 | S-15 |
| 27 | 카메라 관찰 예시 어구 | MD-1.2 | S-1 |
| 해당 없음 | 결함 보존과 균형, 압력 상황의 판단 우선순위, 결함의 이득·비용, 대화 종료를 기본값으로 두지 않는 조건이 없다 | MD-3.3, MD-3.4, MD-3.10 | S-19, A2-56, B-22 |

말높임·종결어미를 칸에 정하지 않기, 상대 말을 먼저 받기(MD-4.1, MD-3.6)는 반영돼 있다.

### prompter.md (구형 대화 본문 작성 경로)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 9 | 특정 캐릭터 이름을 지시문에 쓴다 | MD-7.1 | A1-29, S-2 |
| 11 | 2인칭 산문으로 쓰게 한다. 본문은 인물 주어 문장을 요구한다 | MD-3.15 | A1-58 |
| 6 | 앎의 경계 칸 기준에 사실 소유권, 공동 기억, 외부 조회 기준이 없다 | MD-6.3, MD-6.10, MD-6.11, MD-6.12 | B-25, B-27, S-11 |

### common-procedure.md (에이전트 공통 절차)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 6 | 검사가 통과할 때까지 반복하게 한다. 의미 휴리스틱이 섞인 검사까지 자가 수정 대상이 된다 | MD-7.9 | B-49, B-34 |

### persona_beats.md (검증용 내용 뼈대)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 8 | 4개 예시로 핵심 규칙을 보여 주도록 장면을 설계하게 한다(구형 전제) | MD-1.3, MD-5.4 | B-04, B-05 |
| 해당 없음 | 같은 규칙의 적용·비적용·조건 변경 짝 설계 요구가 없다 | MD-3.2, MD-9.7 | B-24 |

### persona_choice_formation.md (선택 보존 특질 작성)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 6~7 | 기본 성격의 표현 강도와 결함 보존을 요구하지 않는다 | MD-5.2, MD-3.10 | B-21, B-22 |
| 11~12 | voiceProfile 항목에 말버릇 자리·빈도와 질문 습관 기준이 없고, 관계에 따른 변화를 개인어에서 떼라는 기준이 없다 | MD-4.11, MD-3.9, MD-4.3 | C-51, S-10, A1-22 |

### persona_dialogues.md (구형 자연 대화 작성)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 전체 | 내용과 말투를 한 번에 쓰는 구조다 | MD-7.5 | B-18, C-68 |
| 24 | 특정 캐릭터 이름을 쓴다 | MD-7.1 | A1-29 |

### persona_formation.md (행동·목소리 설계)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 14~16 | decisionRules의 일곱 칸을 모두 필수로 쓰게 하고 검토용 칸을 구분하지 않는다 | MD-3.2, MD-5.3 | B-39 |
| 17~18 | voiceProfile에 speechLevel과 relationshipDistance를 쓰게 한다. 조립 코드가 speechLevel을 VOICE 칸에 넣으므로 말투 칸이 등급을 갖고, 관계 거리가 개인어 칸에 섞인다 | MD-4.1, MD-4.3, MD-1.4 | S-3, A1-22, S-18 |
| 26 | 특정 캐릭터 이름을 쓴다 | MD-7.1 | A1-29 |
| 해당 없음 | 결함 보존, 말버릇 자리·빈도 지시가 없다 | MD-3.10, MD-4.11 | B-22, C-51 |

### persona_voice_preservation.md (보존 검토)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 18 | 문맥 지시어와 시각 표현을 따옴표로 예시한다 | MD-1.2 | S-1, A2-36 |
| 해당 없음 | 이력에 없는 합의를 전제한 대사를 따로 잡는 항목, 설명 증가 판정, 말버릇 반복 검사가 없다 | MD-3.2, MD-9.7, MD-4.11 | B-24, B-19, B-16 |

### persona_voice_render.md (말투 입히기)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 8 | 관계가 멀면 말높임을 조절하게 해 렌더러가 등급을 바꿀 여지를 둔다 | MD-4.1, MD-4.2 | S-3, A1-23 |
| 해당 없음 | 영상통화 표기 기준, 말버릇 상한, 등급·결함을 포함한 보존 조건, 해요체 비완결 발화의 높임 유지가 없다 | MD-1.6, MD-4.10, MD-4.11, MD-7.6 | B-15, C-42, C-51, C-69 |

### choice_review.md (선택 설계 의미 검토)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 전체 | 다른 모델의 의미 검토가 실패하면 사람 관문(G3) 전에 실행이 멈춘다(choice_flow의 require_choice_pass). 수정 고리는 없지만 판단을 모델 판정이 대신한다 | MD-7.8 | S-12, A1-65 |
| 해당 없음 | 결함이 후보에서 지워졌는지, 비적용 조건이 타당한지 검토하지 않는다 | MD-2.5, MD-3.2 | S-19, B-24 |

### choice_variants.md (선택 근거를 갖춘 기획)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 7 | 규칙에 의미, 주의 대상, 우선순위, 비용, 적용·비적용, 전환, 대안을 모두 요구하고 검토용 칸을 구분하지 않는다 | MD-3.2 | B-39 |
| 14 | 명사형 표제어 반례를 따옴표로 인용한다 | MD-1.2, MD-7.1 | A2-36 |
| 해당 없음 | 압력 상황과 결함 설계를 요구하지 않는다 | MD-2.4, MD-2.5 | S-19 |

후보 번호에 성격을 배정하지 않기, 공통 기본기 허용, 같은 행동 재서술 금지(MD-2.3)는 반영돼 있다.

### plan_normalizer.md (직접 쓴 기획 정리)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 9~10 | 말투를 어미와 반응 순서로 정리하게 한다 | MD-2.8, MD-4.2, MD-4.7 | S-3 |
| 37 | 카메라 관찰 예시 어구 | MD-1.2 | S-1 |

### resources/actor-system-rules-v2.md (공장 검증용 공유 프레임)

| 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|
| 5 | 쓰지 않을 표기를 실제 글자로 인용한다 | MD-1.2 | A2-36 |
| 5 | 자기 이야기나 설명은 조금 길어질 수 있다고만 하고 세 문장 상한이 없다 | MD-6.7 | A1-43, A2-59 |
| 7 | 명시적 거절에 설득을 멈추게 할 뿐 캐묻기와 조건 붙이기를 피하는 습관과 아쉬움 유지가 없다 | MD-6.9 | A1-52 |
| 해당 없음 | 이력과 대조해 틀린 공동 기억 주장과 기록 밖 과거 주장의 처리가 없다. 2026-11-05 시험에서 8/8이 없는 약속을 받아들였다 | MD-6.3, MD-6.11 | S-11 |
| 해당 없음 | 근거 없는 모욕, 일상 불평, 실제 잘못의 구분, 사과의 덧붙임과 말투 탓, 사과한 상대를 몰아붙이지 않기가 없다(실제 잘못 인정만 있다) | MD-6.14, MD-6.15 | A1-47, A2-51, B-29 |
| 해당 없음 | 결론 선점, 약속 재확인, 외부 조회 약속, 같은 시작과 마무리 반복, 빈 이력 처리, 역할 교체 요구, 정식화와 응대 행위, 말높임 지적 처리 규칙이 없다 | MD-6.19, MD-6.20, MD-6.12, MD-6.21, MD-6.22, MD-6.16, MD-6.23 | A1-53, B-31, B-27, A1-27, A1-50, A2-50, A2-25 |
| 해당 없음 | 바깥 선과 습관이 한 문단에 섞여 있고 사실 소유권과 관찰 규칙은 조립 코드가 페르소나 경계 칸에 붙인다 | 6절 구조, MD-1.4 | A2-04, A1-28 |
| 전체 | 서비스 프레임 v40과 문장이 다르다. 이 파일로 얻은 시험 결과(예: S-11)를 서비스 동작으로 주장할 수 없다 | MD-0.6 | S-11 |

인물로서 말하기, 현재 관계 기준, 영상통화 구어, 화행 쌓기 회피와 차례 넘기기, 상대 대사 대필 금지, 혐오·노골 요구에 인물의 태도로 대응(MD-6.5, MD-6.6, MD-1.6, MD-6.4, MD-6.1)은 반영돼 있다.

### 서비스 공유 프레임 split-frame-r5-v40과의 차이

/Users/johnhuh619/projects/relationship-quest-chat/data/prompt_frames/split-frame-r5-v40.json 과 /Users/johnhuh619/projects/relationship-quest-chat/src/relationship_quest_chat/domain/prompting/split_dialogue.py 를 읽었다(review-1 P2-6, P3-5, P3-7). v40은 본문의 기준 프레임이므로 대부분의 대화 공통 규칙이 이미 들어 있다. 아래는 본문과 어긋나거나 본문에 새로 옮긴 차이다.

| 위치 | 현재 상태 | 관련 규칙 | 근거 |
|---|---|---|---|
| writer.spokenRegisterNorm(SPOKEN_KOREAN) | 캐릭터 어휘, 관찰 습관, 문장 리듬을 우선하라고 한다. 본문은 카메라 관찰을 보조 단서로 두므로 같은 낱말이 다른 뜻으로 읽힌다 | MD-1.7 | S-5 |
| writer.currentResponsePriority | 이제 없는 반응 고리를 여전히 가리킨다(loopApplicationRules는 null) | MD-5.4 | A1-31 |
| CONFLICT_OWNERSHIP | 근거 없는 시비에 대한 공통 첫 반응을 정한다. 본문은 반응의 세기를 인물 자산에 둔다 | MD-3.3, MD-6.14 | A1-47, A2-52 |
| dialogueOutputContract | 소리 내어 말할 수 없는 표기의 금지가 없다 | MD-1.6, MD-6.1 | S-9 |
| writer.acceptance 세 칸 | v40 묶음은 writerRegister v3라 요청에 실리지 않는다. 실리는 경로는 v1·v2(split_dialogue.py 114~146)뿐이다. 칸을 지우거나 v3 미사용을 표시하는 일이 서비스 저장소에 남는다 | MD-5.4 | A1-40, A2-37 |
| context.pastToCurrentRules, CONFLICT_OWNERSHIP | 임시 상태 이어받기, 생활 소재를 사용자 행동으로 바꾸지 않기, 말투 탓 금지, 욕설 의무 아님, 사과한 상대를 몰아붙이지 않기가 있다. 본문에 옮겼다 | MD-5.10, MD-6.10, MD-6.14, MD-6.15 | A1-51, A1-49, A1-47 |
| split_dialogue.py 156~166, 196~231, writer.moodTurnBlock | 실제 순서는 지금 마음과 믿게 되면 꺼낼 이야기, 길이(같은 블록), 관찰, 사용자 말이다. review-1 반영 때 부록에 적은 이 순서에 맞췄다는 문장은 틀렸다(review-2 P2-4). 본문 MD-5.9는 내용은 코드와 같게 두고 길이 줄을 사용자 말 바로 앞에 두라고 하므로, 관찰과 길이의 순서를 바꾸는 일이 서비스 저장소에 남는다 | MD-5.9, 5절 표 | S-5, A1-33, A1-43 |

### 참고: 지시문 밖 코드

과제의 점검 대상은 아니지만, 위 차이가 실제 프롬프트에 닿는 경로라 함께 적는다.

| 파일 | 줄 | 현재 상태 | 어긋난 규칙 | 근거 |
|---|---|---|---|---|
| src/character_factory_poc/stages/s3_plan/variants.py | 130~134 | 형식 예시에 실제 성격 문장 두 개와 모든 씨앗에 같은 상황 세 개가 들어 있다 | MD-7.1, MD-2.4 | B-02, S-2 |
| src/character_factory_poc/stages/s8_prompts/actor_persona.py | 125~126 | voiceProfile.speechLevel과 relationshipDistance를 VOICE 칸에 넣는다 | MD-4.1, MD-4.3 | S-3, S-18, A1-22 |
| src/character_factory_poc/stages/s8_prompts/actor_persona.py | 136~145, 282~287 | 사실 소유권과 관찰 규칙을 페르소나 경계 칸에 붙인다 | MD-1.4 | A1-28 |
| src/character_factory_poc/stages/s8_prompts/source.py | 15~29 | 기획 투영 필드에 voiceExamples와 profileCard가 있다 | MD-2.9, MD-2.7 | B-09, C-34 |
| src/character_factory_poc/stages/export/doki_app/chat_svc.py | 466~492 | 등급을 모든 챕터에서 CASUAL로 고정하고, 호칭·거리감(addresseeStance), 주도성, 표현 변화, 믿게 되면 꺼낼 이야기, 장면 욕구를 틀 문장과 시트 칸으로 채운다(K-0077) | MD-5.5 | S-18 |

선택 경향을 상황, 선택, 전환 한 줄로 조립하는 _choice_lines(actor_persona.py 226~238)는 MD-5.3과 맞다.

## 7. 출력 계약 변경 필요 목록

review-2 P1-3에 따라 발췌 규칙이 요구하는 칸을 생성 단계 출력 계약과 대조했다. 읽은 계약은 contracts/planning.py(CharacterPlanV2, Choice, ProfileCard), contracts/persona.py(TraitSheet, Choice, JudgmentPriority, DialogueHabits, Situational, Card, Reference), contracts/formation.py(DecisionRule, VoiceProfile), contracts/choice_design.py(DesignedChoice)다. 계약은 모두 Strict라서 칸을 더할 수 없다. 아래 항목마다 본문은 지금 계약 안에서 지킬 수 있는 형태로 규칙을 고쳤고, 그 규칙에 계약 변경 필요 표시를 붙였다(MD-0.7). 코드와 계약 파일은 고치지 않았다.

| 번호 | 계약과 칸 | 지시서 요구 | 지금 계약 안의 처리(본문 규칙) | 필요한 계약 변경 |
|---|---|---|---|---|
| 1 | character-plan-v2 Choice는 situation, firstMove 두 칸뿐 | 전환 조건과 비적용 경우(MD-3.2) | 기획은 두 칸만 쓰고, 전환과 비적용은 성격 시트 단계에서 쓴다(MD-3.2) | 기획 Choice에 전환과 비적용 칸을 더하거나, 기획 choices를 계기·첫 행동 전용으로 계약 설명에 명시 |
| 2 | character-plan-v2에 핵심 긴장 칸이 없음 | 핵심 긴장 한 문단(MD-2.2) | 원하는 것과 두려움(wantsAndFears) 첫 항목에 한 문장으로 쓴다(MD-2.2) | 핵심 긴장 칸 추가 |
| 3 | character-plan-v2에 즉시 이득·장기 비용·뒤집히는 조건 칸이 없음 | 결함의 이득과 비용(MD-2.2, MD-3.4) | 이득과 비용은 coreTraits 문장 안에, 뒤집히는 조건은 contrastTrait에 쓴다(MD-2.2) | choices나 coreTraits에 이득·비용 칸 추가 |
| 4 | character-plan-v2 voiceExamples가 최소 두 개 필수 | 기획 초안 말투 요약은 등급 이름과 기능 서술만, 대표 대사는 말투 확정의 산출(MD-2.8, MD-2.9) | 초안은 임시 대표 대사로 칸을 채우고 말투 확정이 다시 쓰며, 다음 단계 입력과 대화 프롬프트에서 뺀다(MD-2.8, MD-2.9) | 초안 단계에서 voiceExamples 최소 개수를 0으로 낮추거나 검토 전용 칸으로 분리 |
| 5 | character-plan-v2 profileCard.mbti | 유형명 금지(MD-2.7) | null로 둔다(MD-2.7) | 칸 제거 또는 앱 표시 전용 자료로 분리 |
| 6 | trait-sheet-v1에 비적용 칸이 없음(Situational은 condition, reaction, returnOrSwitch) | 비슷하지만 적용하지 않는 경우(MD-3.2) | situational의 condition 문장 안에 적용과 비적용을 함께 쓴다(MD-3.2) | Situational이나 JudgmentPriority에 비적용 칸 추가 |
| 7 | trait-sheet-v1 dialogueHabits가 order, directness, questions, evidence, lexicon 다섯 칸이고 order는 답변 순서 | 개인어 항목(MD-4.3), 고정 반응 순서 금지(B-30) | 다섯 칸에 항목을 나눠 쓰고 order에는 고정 순서 대신 앞머리와 종결 기능을 쓴다(MD-4.3) | 개인어 항목에 맞춰 칸을 재구성하고 order 칸 이름과 설명 변경 |
| 8 | trait-sheet-v1 card.bigFiveNotes | 이론 범주 금지(MD-2.7) | 빈 문자열로 둔다(MD-2.7) | 칸 제거 |
| 9 | formation VoiceProfile.speechLevel, relationshipDistance 필수(조립 코드가 VOICE 칸에 넣음) | 등급과 관계 거리는 관계 설정 소유(MD-4.1, MD-4.3) | speechLevel에는 말투 요약의 등급 이름만 옮기고 relationshipDistance에는 관계 설정을 따른다고만 쓴다(MD-4.1) | 두 칸을 VoiceProfile에서 빼고 관계 설정으로 옮김. 조립 코드(actor_persona.py 125~126)도 함께 고침 |
| 10 | 공장에 관계 설정 저작 단계와 계약이 없고(내보내기 코드가 틀 문장으로 채움), chapter-relationship-profile-v3에 허용 예외 칸이 없음 | 인물별 관계 설정 저작(MD-5.5), 등급 허용 예외(MD-4.2) | 허용 예외는 addresseeStance 문장에 쓴다(MD-5.5). 0절 표의 관계 설정 저작 행에 계약 변경 필요를 표시했다 | 공장 관계 설정 저작 단계와 계약 신설, 허용 예외 칸 추가 |

계약 변경 필요 목록: 10개.

변경이 필요 없다고 본 칸:
- trait-sheet-v1 references(SNS14, STANFORD 등의 프리셋 ID). 입력 출처를 적는 메타 칸이고, 성격 칸이 아니며 조립 검사(FORBIDDEN)가 대화 프롬프트에서 막는다. MD-2.7의 유형명 금지는 성격 서술을 겨냥하므로 이 칸은 그대로 둔다(review-2 P1-3의 이 부분은 반영하지 않음).
- choice_design DesignedChoice의 acceptedCost, wrongTransformation, alternative 필수 칸. MD-3.2가 칸이 있는 경로의 검토용 칸으로 쓰게 하므로 계약과 맞는다. 필수 여부 재검토는 소량 표본 뒤로 둔다(검증 대기).

## 검토 반영 기록 (review-1)

판정 기준: 교훈 근거와 맞는 지적은 반영했다. 교훈 근거나 과제 지시와 부딪히는 부분은 반영하지 않고 이유를 적었다. 바뀐 규칙 ID는 review-1 반영 뒤 번호다.

| 지적 | 판정 | 바뀐 규칙 ID와 위치 | 메모 |
|---|---|---|---|
| P1-1 개인어 칸과 관계 변화 소유 충돌 | 반영함 | MD-4.3, MD-4.13, 용어집 개인어, 근거표 3절 21번 | 감정과 압력에 따른 변화만 개인어 칸에 남김 |
| P1-2 발췌표 누락 | 반영함 | 0절 표, MD-0.4, MD-2.8, MD-6.2, MD-6.13 | 공유 프레임 행에 MD-1.6~1.8, 관계 설정 행에 MD-1.2·1.8·3.13, 시트 행에 MD-1.8, 뼈대 행에 MD-1.2·1.6·4.2, 기획 두 행에 MD-2.8·4.2·4.7. 모델용 규칙의 다른 규칙 ID 참조를 없앰 |
| P1-3 한다체 정의, 해라체 누락 | 반영함 | 용어집(상대높임 등급, 해라체, 한다체, 주체높임), MD-4.2, MD-7.8 | 혼용 범위를 존대와 반말 사이, 하십시오체와 해요체 사이로 한정 |
| P1-4 핵심 긴장 틀의 동기 고정 | 반영함 | MD-2.2, 근거표 2.1 | 동기 종류는 씨앗에서 정하고 구조는 검증 대기 |
| P1-5 선택 규칙 여덟 항목 필수화 | 반영함 | MD-3.2, MD-5.3, 5절 표, 근거표 3절 23번 | 필수 네 항목과 검토용 칸으로 나눔 |
| P2-1 의도된 등급 변화, 비완결 발화 높임 | 반영함 | MD-4.2, MD-4.10, MD-5.5, 근거표 3절 22번 | |
| P2-2 용어 정의 | 일부 반영 | 용어집 | 문장 유형, 간투사, 호칭어·지칭어, 주체높임은 반영. 청자 대우법은 이름을 유지하고 표준 의미를 병기함. 과제가 이 이름을 요구했고 A1-22·A2-23이 넓은 뜻으로 쓰기 때문이다. 개인어는 반응 습관을 뺐다. 관찰 단위와 비유는 A2-26이 개인어의 말맛으로 정의하므로 남겼다 |
| P2-3 용어집 번호 겹침과 발췌 경로 | 반영함 | 4.A, 4.B, MD-0.4 | |
| P2-4 사람용 문장 섞임 | 반영함 | MD-0.2, MD-0.4, MD-0.5, 사람용 표시(MD-1.3, 1.9, 2.5, 2.8, 2.9, 2.10, 3.1, 3.2, 3.11, 3.14, 4.4, 4.15), MD-6.7, MD-6.21 | 6절은 모든 문장을 대화 인물이 따르는 문장으로 고침 |
| P2-5 6절 금지문 위주 | 반영함 | 6.A(MD-6.1~6.4), 6.B(MD-6.5~6.23) | 바깥 선과 습관을 나누고 습관은 하는 행동으로 고쳐 씀 |
| P2-6 공유 프레임 둘, v40 보호 규칙 누락 | 반영함 | MD-0.6, MD-5.10, MD-6.10, MD-6.14, MD-6.15, 부록 v40 차이 표 | |
| P2-7 매 턴 블록과 관찰 블록 | 반영함 | 5절 표, MD-5.9, MD-1.4 | 순서는 지금 마음, 관찰, 사용자 말 |
| P2-8 대표 대사의 지위 | 반영함 | MD-2.9, MD-4.3 | |
| P2-9 상위 모델 지정 근거 | 반영함 | MD-7.10 | 우열 대신 명시와 자동 대체 금지 |
| P2-10 정식화 범위 | 반영함 | MD-6.16 | |
| P2-11 대화 종료 기본값, 관계 설정 결함 교차 확인 | 반영함 | MD-3.3, MD-5.6 | |
| P2-12 A2-25 내용 누락 | 반영함 | MD-6.23, MD-9.9 | |
| P2-13 발췌 분량 | 일부 반영 | MD-0.6, MD-5.12 | 교체 전 같은 조건 비교와 글자 수 기록은 반영함. 단계별 글자 수 상한 수치는 교훈에 근거가 없어 두지 않음. A1-33·A2-41은 블록을 더할 때 비교하라는 교훈이지 수치를 정하지 않는다 |
| P2-14 최강 강도 표기 | 반영함 | 근거표 2.1 핵심 구절 강도 열, 검증 대기 표시(MD-1.7, 2.2, 3.2, 3.14, 4.7, 4.12, 6.11), MD-0.5 | |
| P2-15 충돌 10번 근거 | 반영함 | MD-6.3, MD-6.11, 근거표 3절 10번, 4.2 C-16 | 기록 밖 과거는 확정하지 않고 사람이 제품 판단을 함 |
| P3-1 원형 이름 나열 | 반영함 | MD-2.5 | 원형 목록은 사람용 점검표로 옮김 |
| P3-2 끝맺음 닫힌 목록 | 반영함 | MD-3.14 | |
| P3-3 상황 범주의 용도 | 반영함 | MD-2.4 | |
| P3-4 예시 금지 이유 문장 | 반영함 | MD-1.2, 근거표 3절 1번 | |
| P3-5 프리필 금지 강도 | 반영함 | MD-5.4, 부록 v40 표 | 서비스 쪽 칸 정리는 서비스 저장소 일로 기록만 함 |
| P3-6 상대높임 전환 문장 | 반영함 | MD-3.13 | |
| P3-7 v40과의 작은 어긋남 | 반영함 | 부록 v40 차이 표 | |
| P3-8 작은 구절 누락 | 반영함 | MD-6.8, MD-6.11, MD-9.1, MD-9.3, MD-9.9, 8절 | C-56은 금지문 대신 긍정형으로 반영(MD-6.8). 8절 소재 반복 행은 표를 줄이며 뺐고 지표는 MD-9.9에 넣음 |
| P3-9 용어집 보완 | 반영함 | 용어집(화행, 정식화, 담화 표지, 앞머리, 턴, 확인 종결, 음슴체, 장식 표지), MD-4.10 | 앞머리 정의 속 하위 유형은 정의 없이 쓰이지 않게 뺐다 |
| P3-10 부록 누락 차이 | 반영함 | 부록 plan_variants 36~38행, deck_plan_voice 3행, 코드 표의 chat_svc 466~492행과 source.py | |
| P3-11 S-13 인용 정리 | 반영함 | MD-3.3, MD-6.14 | S-13은 MD-7.10에만 남김 |
| P3-12 9절 발췌 범위 | 반영함 | MD-0.2 | |

집계: P1 5건 반영. P2 13건 반영, 2건 일부 반영(P2-2, P2-13). P3 12건 반영. 반영하지 않은 지적은 없고, 일부 반영한 두 건의 남긴 부분과 이유는 위 메모에 있다.

6절 번호 대응(구 → 신): 6.1 → 6.5, 6.2 → 6.6, 6.3 → 6.7, 6.4 → 6.8, 6.5 → 6.9, 6.6 → 6.10과 6.3, 6.7 → 6.3과 6.11, 6.8 → 6.12, 6.9 → 6.13과 6.2, 6.10 → 6.14, 6.11 → 6.15, 6.12 → 6.16, 6.13 → 6.17, 6.14 → 6.18과 6.4, 6.15 → 6.19, 6.16 → 6.20, 6.17 → 6.21, 6.18 → 6.22, 6.19 → 6.1, 신설 6.23. 0절 신설 0.4~0.6. 5.12의 교체 전 비교는 0.6으로 옮김.

review-2 반영 뒤 일부 문장이 다시 바뀌었다. 바뀐 내용은 아래 review-2 기록에 있다.

## 검토 반영 기록 (review-2)

판정 기준은 review-1과 같다. 6절 규칙 번호는 바꾸지 않았고 MD-0.7만 새로 생겼다.

### review-1 부분 판정 8건의 남은 부분

| review-1 지적 | 판정 | 바뀐 규칙 ID와 위치 | 메모 |
|---|---|---|---|
| R1-P2-1 의도된 등급 변화 | 반영함 | MD-4.2(사람용 문장), MD-5.5, 근거표 3절 22번 | 등급 검사가 허용 예외를 혼용으로 세지 않는다는 문장을 본문에 넣음 |
| R1-P2-2 용어 정의 | 반영함 | 용어집 개인어, MD-4.3, MD-4.4 | 관찰 단위를 개인어 정의에서 빼고 자주 주목해 말로 꺼내는 대상의 종류로 바꿔 어휘장(MD-4.4)에 합침. 비유는 MD-4.3 lexicon 항목에 넣음 |
| R1-P2-4 사람용 문장 섞임 | 반영함 | 0절 공유 프레임 행, MD-1.6, MD-1.8, MD-3.2, MD-3.8, MD-4.7, MD-4.10, MD-4.15, 용어집 4개 정의, MD-0.4 | 새 P2-1과 같이 처리 |
| R1-P2-5 6절 금지문 위주 | 반영함 | 6절 머리, 6.A, MD-6.5~6.21 | 6.A 설명을 바로잡고(새 P2-2), 사라진 제한을 되살림(새 P1-2). 긍정형으로 쓸 수 없는 제한은 금지절로 남겼다 |
| R1-P2-6 v40 보호 규칙 | 반영함 | MD-6.14, MD-6.15 | 뜻이 바뀐 세 곳을 v40 쪽으로 되돌리고(새 P2-3), 진정 요구 금지를 MD-6.15에 넣음 |
| R1-P2-7 매 턴 블록 | 반영함 | MD-5.9, 5절 표, 부록 v40 차이 표, 근거표 3절 25번 | 새 P2-4 |
| R1-P2-13 발췌 분량 | 추가 조치 없음 | MD-0.6 | review-2가 비교 의무 방식을 타당하다고 판정했다. 공유 프레임 발췌가 현행 공장 규칙보다 크므로 MD-0.6 비교 없이 교체하지 않는다 |
| R1-P2-14 검증 대기 처리 | 반영함 | MD-0.5, MD-6.11 | 새 P2-6 |

### 새 지적

| 지적 | 판정 | 바뀐 규칙 ID와 위치 | 메모 |
|---|---|---|---|
| P1-1 MD-6.21 턴마다 바꾸기 | 반영함 | MD-6.21 | 호칭은 관계 설정, 말버릇은 개인어가 정한 자리와 빈도로 쓰게 함 |
| P1-2 6절 제한 누락 | 반영함 | MD-6.5, MD-6.6, MD-6.8, MD-6.12, MD-6.14, MD-6.15, MD-6.17, MD-6.20, 근거표 3절 24번 | 검토가 든 아홉 제한을 모두 되살림. 교체 전 v40 비교는 MD-0.6이 정한다 |
| P1-3 출력 계약 칸 부재 | 일부 반영 | MD-0.1, MD-0.7, MD-2.2, MD-2.7, MD-2.8, MD-3.2, MD-4.1, MD-4.3, MD-5.5, 0절 관계 설정 행, 근거표 7절 | 과제 지시대로 지시서 쪽에서 해결함. 규칙마다 쓸 칸을 지정하고 계약 변경 필요 10개를 목록으로 만듦. 반영하지 않은 부분은 references 칸이다. 입력 출처 메타 칸이며 성격 칸이 아니고 조립 검사가 막으므로 MD-2.7과 부딪히지 않는다고 판단했다 |
| P2-1 모델 발췌의 저자용 문장 | 반영함 | 0절 공유 프레임 행, MD-0.4, MD-1.6, MD-1.8, MD-3.2, MD-3.8, MD-4.7, MD-4.10, MD-4.15, 용어집 | MD-0.4에 메타 낱말 잔존 검사를 더함 |
| P2-2 6.A 설명과 중복 금지 | 반영함 | 6절 머리, MD-1.8, MD-6.2, MD-6.4, 0절 공유 프레임 행 | 바깥 선 목록을 MD-6.4로 모으고 공유 프레임 행을 MD-1.7, 6절, MD-4.10으로 줄임. MD-6.2의 관찰 블록 문장은 MD-1.7과 겹쳐 뺐다 |
| P2-3 v40 의미 변경 | 반영함 | MD-6.14, MD-6.15 | 일상 불평은 훈계 대신 짧게 받기, 사과한 상대는 더 몰아붙이지 않기, 자기비난은 결함인 인물에 한정 |
| P2-4 매 턴 블록 순서 | 반영함 | MD-5.9, 5절 표, 부록 v40 차이 표 | 서비스 순서 변경은 서비스 저장소 할 일로 기록 |
| P2-5 원하는 것과 씨앗 고정 요구 | 반영함 | MD-2.2, 근거표 3절 26번 | |
| P2-6 검증 대기 처리 | 반영함 | MD-0.5, MD-6.11 | 검증 대기 구절은 표시를 떼고 발췌하고, 처음 들어간 지시문은 소량 표본 뒤 확대. MD-6.11 첫 문장은 사람이 판단하기 전까지 발췌하지 않음 |
| P2-7 개인어 정의와 MD-4.3 | 반영함 | 용어집 개인어, MD-4.3, MD-4.4 | |
| P3-1 허용 예외 검사 제외 | 반영함 | MD-4.2 | |
| P3-2 공통 상한 명시 | 반영함 | MD-4.5 | |
| P3-3 호감 장면과 단계 상승 구분 | 반영함 | MD-4.13 | |
| P3-4 C-23 일부 누락 | 반영함 | MD-6.18 | |
| P3-5 음슴체와 사용역 | 반영함 | MD-4.10 | 피할 사용역과 문체로 고침 |
| P3-6 기획 단계 결함·거절·맞대응 요구 | 반영함(기록) | 변경 없음 | 의도한 변경이다. 7절은 지시문 작성자용이라 사람용으로 두었다. 기획 변형 초안 발췌에는 결함 요구(MD-2.5)와 거절 선택지(MD-3.3)가 이미 있다 |

집계: review-1 부분 판정 8건 중 7건 반영, 1건(R1-P2-13) 추가 조치 없음. 새 P1은 2건 반영, 1건 일부 반영(P1-3, references 칸 제외). 새 P2 7건과 새 P3 6건은 모두 반영했다(P3-6은 기록만). 반영하지 않은 지적은 P1-3 가운데 references 칸 한 부분이다.

길이를 맞추려고 합치거나 줄인 곳도 있다. 8절 표는 20행으로 줄였고 계약 불일치 행을 더했다. 바깥 선 목록은 MD-1.8에서 MD-6.4로 옮겼다. MD-3.3의 맞대응 복사 금지 문장은 MD-1.4(공유 프레임에 특정 인물의 말버릇 금지)와 겹쳐 뺐다.

## 8. 사용자 결정과 소량 검증 결과 (2026-11-05)

### 8.1 사용자 결정

| 쟁점 | 결정 | 반영 규칙 |
|---|---|---|
| 말투를 대표 대사로 줄 것인가 | 예시 대신 언어학 범주로 기술한다. 일관성을 지키면서 예시에 없던 상황에도 적용된다고 판단했다. 대표 대사는 사람 검토용으로만 두고 성격 시트 입력에서 뺐다(`stages/s7_traits/sheet.py`, D-0088) | MD-2.8, MD-2.9 |
| 카메라 관찰 | 기기가 넘기는 관찰 정보를 반응에 쓰는 서비스 방향을 따른다 | MD-1.7 |
| 근거 없는 시비의 첫 반응 | 인물마다 달라야 한다. 공유 프레임(v40 CONFLICT_OWNERSHIP)은 공통 바닥선을 두고, 첫 반응의 종류와 세기는 모든 인물의 선택 칸에 쓴다 | MD-3.3, MD-6.14 |
| 매 턴 블록 순서 | 서비스 코드 순서를 따른다. 서비스에서 문제가 관측되지 않았다 | MD-5.9 |
| 챕터 시작 설정 | 서비스는 고정 시작 대사 없이 장면 사실·경계·관계 설정으로 첫 턴을 생성한다. 이 시작 설정 묶음을 공장이 인물별로 만들어야 한다(K-0077과 같은 과제, 계획) | MD-5.5 |

### 8.2 검증 대기 규칙 소량 대조

공통 조건: 백태하(`cf-20261105-api-cost-argon-v2` pv1) 프롬프트에서 한 규칙만 바꾼 A·B, Gemini 3.8 Flash(low, 0.8), 조건마다 2회. T2는 같은 기획 초안 요청을 Flash(high)로 조건마다 2회. 결과 `runs/experiments/20261105-directive-rules/`, 스크립트 `work/api-cost-20261104/rule_probe.py`·`t2_probe.py`. 184호출, 원장 추정 $0.60, 실패·잘림 0. 인물 1명·모델 1개·소표본이다.

| 규칙 | 시험 | 결과 | 판정 | 바뀐 본문 |
|---|---|---|---|---|
| MD-1.7 관찰 | T1: 공장식(가끔 보조) 대 서비스식(어긋나면 반영), 관찰 블록 8턴 | 말·관찰 어긋남 반응 5/8 대 6/8. 블록에 없는 목소리 단서 3 대 2, 서비스식 외모 언급 1 | 서비스 방향 채택, 블록 밖 단서 금지 추가(그 문장은 검증 대기) | MD-1.7 |
| MD-2.2 핵심 긴장 | T2: 기획 초안 지시문에 구조 추가 여부 | 후보별 동기·방어 유형은 갈림. 지각 상황 선택 틀은 그대로. 구조 구절이 세 후보에 같은 문장으로 반복, 한 판은 브리프 대사를 따옴표째 선택 칸에 복사 | 부분 확인. 구조 이름을 그대로 쓰지 않게 하고 브리프 인용 복사 금지 추가 | MD-2.2, MD-2.8 |
| MD-3.14 끝 덧붙임 | T3: 끝 덧붙임 제한 한 줄 추가 | 질문 끝맺음 3/20 대 5/20, 개선 없음 | 효과 없음. 발췌하지 않고 MD-6.8·6.7로 다룸 | MD-3.14 |
| MD-4.7 종결 | T4: 해요체 대표 형태 표기 대 기능만 | 하십시오체 섞인 응답 1/20 대 6/20 | 반대로 확인. 등급과 맞는 형태 표기를 적는다 | MD-4.7, MD-4.2, MD-1.2 |
| MD-4.12 운율 | T5: 반 박자 쉼 대 구조 기술 | 말줄임표 시작 11/20 대 7/20 | 부분 확인 | MD-4.12 |
| MD-6.11 기록 없는 과거 | T6: 거절 규칙 유무, 이력 있는 대조 2문항 포함 | 수용 8/10 대 0/10, 이력 사실 유지 4/4 대 4/4. 같은 되물음 틀 5/10 | 확인. 되물음 틀 반복 금지 추가 | MD-6.11 |

남은 검증 대기: MD-1.7의 블록 밖 단서 금지 문장(재시험 필요), MD-3.2의 검토용 칸 필수 여부(형성 경로 실행 필요).

### 8.3 이 검증으로 생긴 충돌과 해결

| 부딪힌 것 | 해결 |
|---|---|
| 이전 MD-4.2(등급은 이름으로만, 어미 형태 나열 금지)·MD-4.7(형태를 적지 않음) 대 S-23 실측 | 등급과 맞는 대표 종결 형태 표기는 문법 표지로 허용하고 적는다. 금지는 다른 등급의 형태(S-3)에만 남긴다 |
| MD-1.2 예시 금지 대 형태 표기 | 형태 표기는 예시 대사·어구가 아니라 문법 표지로 본다 |
| 이전 MD-1.7(관찰은 가끔) 대 사용자 결정 | 서비스 방향을 따르고, 실측에서 보인 블록 밖 단서 생성을 바깥 선으로 막는다 |

이 절의 판정은 2.1 규칙별 근거 표의 같은 규칙 행보다 앞선다.
