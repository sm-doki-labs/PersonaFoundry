# 인계: 2026-10-20(인상) 비교 범위에 인물 인상 칸 추가, S1 계약 v2

이전 인계: [handoff-2026-10-20-image.md](handoff-2026-10-20-image.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- Q-0015를 해결했다(D-0020). 비교 범위에 `appearanceOrigin`(korean·east-asian·unspecified)이 필수이고, 미리보기 프롬프트 주어에 들어간다("fictional Korean woman").
- S1 입력·보고서 계약을 `popularity-ranking-v2`·`reference-report-v2`로 올렸다(D-0021). v1 순위 파일은 안내와 함께 거절한다.
- 실제 구독 호출에서 "Korean" + 피할 것 "celebrity likeness" 조합이 2회 연속 안전 시스템에 막혔다. 피할 것 목록을 "text, watermark, logo"로 줄이자 한국인 인상으로 생성됐다.
- 이미지 생성 실패(차단 포함) 때 S1이 RUNNING으로 남던 문제를 고쳐 `CHECK_FAILED`로 기록한다. 테스트 43 passed.

## 2. 이번 세션에서 한 일

- 코드: `contracts/reference.py`(`AppearanceOrigin`, 계약 v2), `stages/s1_reference/ranking.py`(v1 안내 거절), `preview.py`(주어·피할 것 목록), `page.py`(검토 페이지에 인물 인상 표시), `run.py`(dry run에 비교 범위 표시, 옛 보고서 비교 생략, 이미지 실패 시 CHECK_FAILED), `report.py`·`approve.py`, CLI 도움말.
- 테스트: 합성 순위 목록과 [양식 예시](../../templates/popularity-ranking-example.json)를 v2로 올림. 새 테스트 5개(인물 인상 필수·정해진 값만·주어 반영, v1 안내 거절, 옛 보고서 비교 생략, 피할 것 목록 문구, 이미지 차단 시 CHECK_FAILED).
- 문서: [결정 기록](../decisions.md) D-0020·D-0021, [미결 질문](../open-questions.md) Q-0015 해결, [PRD](../../product/prd.md)·[명세](../../architecture/spec.md)·[LLD](../../architecture/lld.md) v0.3, [양식 모음](../../templates/README.md).
- 실제 구독 호출 3회(아래 검증 기록): 차단 2회, 통과 1회.

## 3. 결정

D-0020(확정), D-0021(제안).

## 4. 확인한 사실과 정정

- 앞 인계의 "피할 것: text, watermark, logo, celebrity likeness"는 바뀌었다. "celebrity"류 단어는 인물 인상과 함께 쓰면 차단을 부른다.
- 이번 통과 호출의 입력 토큰은 약 4만 개였다(앞 세션 관측 약 11.8만 개). 장당 사용량은 호출마다 크게 다르다.

## 5. 미결

Q-0002, Q-0004, Q-0013.

## 6. 다음 할 일

1. 사용자가 실제 순위 목록과 비교 범위(Q-0002, 인물 인상은 korean)를 [양식 예시](../../templates/popularity-ranking-example.json) 형식으로 채운다. `acf ref run x --new-slug <slug> --ranking <file>`로 계획을 보고, 지시 뒤 `--execute`로 S1을 돌린다.
2. 미리보기 12장 중 일부가 차단되면 지금은 S1 전체가 멈춘다. 첫 실제 실행에서 차단이 잦으면 장별 실패를 기록하고 계속하는 방식을 검토한다.
3. G1 선택 뒤 S2(M2).

## 7. 떠 있는 것

없음. 임시 파일: `/tmp/acf-imgprobe-20261020/c1-1-korean.png`(한국인 인상 확인 이미지 사본), `/tmp/acf-doc-edits-20261020.json`(문서 수정 입력).
