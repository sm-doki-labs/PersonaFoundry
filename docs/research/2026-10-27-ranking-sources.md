# 화제성 순위 출처 조사 (B 갈래, P-14·P-21, Q-0013)

- 작성일: 2026-10-27
- 범위: 한국 연예인·인물 화제성(브랜드평판) 순위를 정기적으로 공개하는 출처 가운데 자동 수집
  어댑터로 쓸 수 있는 곳을 고른다. S1 `popularity-ranking-v2`의 `lists`로 옮길 수 있는지
  (발표 주기·분류·성별 구분·형식)와 이용 조건(robots.txt·약관·공지)을 함께 본다.
- 확인 방법: 2026-10-27에 공개 페이지만 읽었다. `curl`로 `robots.txt`와 본문을 받아 눈으로
  확인했고, 순위 목록은 저장소에 저장하지 않았다. 화면 구조는 HTML 원문의 class·JSON-LD로 확인했다.
- 관련 결정: P-14(이용 조건 확인 뒤 자동 수집 어댑터), P-21(허용하지 않으면 다른 출처),
  D-0017(순위 목록 이름은 내부 기록에만), D-0044 (4).

## 1. 후보 요약

| 출처 | 공개 주기 | 분류·성별 구분 | 발표 형식 | robots.txt | 약관·공지 | 판정 |
|---|---|---|---|---|---|---|
| 한국기업평판연구소(브랜드평판지수, brandpedia.net·kbri.co.kr) | 월간(공지·보도 기준) | 배우·가수·아이돌 개인. 화면 분류는 확인하지 못함 | 확인하지 못함(회원가입·로그인 메뉴가 있는 사이트) | `User-agent: Yeti / Allow:/` | 전 페이지 공지 "허가 없는 사용시 민형사의 처벌" | 사용하지 않음 |
| 랭키파이(rankify.site) | 월간 | 여자 아이돌·남자 아이돌(성별 분리), 배우(혼성) | HTML 목록 + `schema.org ItemList` JSON-LD | `User-agent: * / Allow: /` + sitemap | 이용약관 페이지 없음. 개인정보처리방침만 | 채택(원자료 조건은 사람 확인 필요) |
| FUNdex(gooddata.co.kr·fundex.co.kr) | 주간 | 드라마·예능 출연자(성별 분리 없음) | JavaScript로 그리는 화면, PDF 리포트 | `User-agent: Yeti / Allow:/` | 확인한 이용약관 페이지 없음 | 보류(사람 확인 필요) |
| 한국갤럽(gallup.co.kr) | 연간 | '올해를 빛낸 인물' 분야별 | 갤럽리포트 HTML(목록은 스크립트로 불러옴) | robots.txt 없음(404) | 확인 못 함 | 사용하지 않음(월간 요건 아님) |

## 2. 출처별 확인 내용

### 2.1 한국기업평판연구소 — 사용하지 않음

- URL: `https://brandpedia.net/`, `https://kbri.co.kr/`, `https://brandpedia.net/robots.txt`
- robots.txt 원문: `User-agent: Yeti` / `Allow:/`. 우리 수집기 User-Agent에는 해당 규칙이 없어
  표준 해석으로는 허용이지만, 이 사이트의 제한은 robots가 아니라 본문 공지에 있다.
- 본문 공지(모든 페이지 하단, 2026-10-27 확인): "한국기업평판연구소에서 생성된 빅데이터 분석자료는
  빅데이터 분석시스템 ALLSNS를 통한 자료로, 허가 없는 사용시 민형사의 처벌을 받게 됩니다."
  또 "브랜드평판지수는 대한민국 특허청 상표등록(출원번호 40-2018-0040251)되어 법적 보호를 받고
  있습니다"라고 밝힌다.
- 이용약관(`https://brandpedia.net/bbs/content.php?co_id=provision`)은 쇼핑몰 표준 약관이라
  크롤링을 직접 다루지 않는다. 그러나 위 공지가 재사용에 허가를 요구하므로 자동 수집 대상에서 뺀다.
- 데이터 문의 창구는 `data@brikorea.com`으로 안내되어 있다. 허가를 받는 경로는 이 창구다.
- 판정: **자동 수집하지 않는다.** 이 지수를 인용한 2차 사이트를 쓰는 경우에도 원자료 조건이
  따라붙으므로 2.2의 "사람 확인 필요" 항목과 같이 본다.

### 2.2 랭키파이 rankify.site — 채택

- URL: `https://rankify.site/`, `https://rankify.site/idolFemale`, `https://rankify.site/idolMale`,
  `https://rankify.site/actor`, `https://rankify.site/robots.txt`, `https://rankify.site/sitemap.xml`
- robots.txt 원문(2026-10-27):

  ```
  User-agent: *
  Allow: /

  Sitemap: https://rankify.site/sitemap.xml
  ```

- 이용약관: `/terms`는 404이고 사이트 어디에도 이용약관 페이지가 없다. 공개된 것은
  `https://rankify.site/privacy`(개인정보처리방침, 시행 2026-08-01)뿐이고, 그 문서는 방문 기록·
  쿠키·광고 식별자 수집만 다루며 자동 접근을 제한하는 문구가 없다. 회원가입·로그인 절차도 없다.
- 발표 형식: 서버가 그린 HTML이다. 목록은 `ol.rank-list > li.rank-item`이고 항목마다
  `span.rank-pos`(순위), `span.rank-name`(이름), `span.rank-cat`(소속·분류), `div.mau-num`(지수)이
  있다. 같은 문서의 `<script type="application/ld+json">`에 `ItemList`(position·name)도 들어 있어
  화면 구조가 바뀌었을 때의 대비책으로 쓸 수 있다.
- 주기: 페이지 제목·본문에 "2026년 9월"처럼 발표 월이 적혀 있고 "매월 갱신"이라고 밝힌다.
- 성별 구분: 아이돌만 성별이 나뉜다(`idolFemale`, `idolMale`). 배우(`actor`)는 혼성이다.
- 한계(사이트가 직접 밝힘): "지수는 상위 5위(개인 순위 기준 공표분)만 실측이고 나머지는 공표된
  순위에 맞춘 추정치입니다." 지수 원자료는 한국기업평판연구소 브랜드평판지수 인용이다.
- 판정: **robots 기준 자동 수집 허용.** 다만 (1) 원자료(브랜드평판지수)를 2차 사이트가 다시
  공개한 것이고 (2) 6위 이하가 추정치이므로, **사람 확인 필요**로 남긴다. 어댑터의
  `TermsCheck.human_review=True`와 `notes`에 이 두 가지를 적었다.

### 2.3 FUNdex(굿데이터코퍼레이션) — 보류

- URL: `http://www.gooddata.co.kr/`, `http://www.fundex.co.kr/fxmain.do`,
  `http://www.fundex.co.kr/spcreport.do`, `http://www.gooddata.co.kr/robots.txt`
- robots.txt 원문: `User-agent: Yeti` / `Allow:/` (한국기업평판연구소와 같은 형태).
- 발표 형식: 주간 화제성 순위. `spcreport.do` 본문 HTML에는 표가 없고(0개 `<table>`), 스크립트가
  데이터를 그린다. 공개 리포트는 S3 PDF로도 배포된다.
- 성별 구분: 드라마·예능 "출연자(Player)" 단위라 성별 분류가 없다.
- 약관: 사이트 메뉴에 이용약관 항목이 없고, 확인한 페이지에 크롤링 규정이 없다.
- 판정: **보류(사람 확인 필요).** 주기가 주간이고 성별 분류가 없어 S1의 월간·성별 요건에도
  맞지 않는다. 대안 출처로 쓰려면 약관 확인과 별도 파서가 필요하다.

### 2.4 한국갤럽 — 사용하지 않음

- URL: `https://www.gallup.co.kr/`, `https://www.gallup.co.kr/gallupdb/report.asp`
- robots.txt: `https://www.gallup.co.kr/robots.txt`가 오류 페이지를 200으로 돌려준다(파일 없음).
- 발표: 연말 '올해를 빛낸 인물' 성격의 연간 조사가 중심이다. 2026-10-27에 확인한 갤럽리포트
  목록에서 "매달 연예인 화제성 순위"를 공개하는 화면은 찾지 못했다. 목록 페이지는 스크립트로
  게시물을 불러와 월간 연예인 순위의 존재를 확정하지 못했다.
- 판정: **사용하지 않음.** S1이 요구하는 월간 주기와 성별 분류를 만족한다는 근거가 없다.

## 3. 채택안과 구현 연결

- 어댑터: `src/character_factory_poc/collectors/rankify.py`의 `RankifySource`. 분류는 `idolFemale`(여성),
  `idolMale`(남성), `actor`(혼성, `gender="any"`) 셋이다.
- 성별 처리: 수집 결과의 각 목록에 `gender`를 달고, `collect.select_lists`가 캐릭터
  성별(`scope.characterGender`)과 같은 목록만 남긴다. 혼성 목록은 `any` 범위에서만 쓴다.
- 메타데이터: 계약 `popularity-ranking-v2`에는 항목별 출처 칸이 없으므로, 목록의 `url`·
  `retrievedAt`과 수집 기록(`ranking-collection-v0`)의 `listId`·`termsCheckedOn`으로 항목마다
  근거를 되짚는다. 기록에는 `robots`·약관 요지·사람 확인 항목을 그대로 담는다.
- 확인 날짜는 어댑터의 `TermsCheck.checked_on`(2026-10-27)에 고정되어 있고, dry run과 수집
  기록에 함께 출력된다.

### 3.1 남은 제약

1. 한 분류가 10명이다. 여성 범위에서 쓸 수 있는 목록은 여자 아이돌 하나(10명)뿐이므로
   S1의 `cluster_k=4`, `min_members_per_cluster=3`(12명 필요)을 그대로 쓸 수 없다. 통합 시
   `cluster_k`를 2~3으로 낮추거나 여러 달치를 누적하는 방식을 정해야 한다.
2. 6위 이하 지수는 추정치다. 순위 자체는 공표값이므로 목록 순서는 쓰되, `score`를 근거로
   정규화하지 않는 편이 안전하다(현재 계약의 정규화는 순위 기반 백분위다).
3. 배우 분류는 혼성이라 성별 범위가 있는 캐릭터에 쓰면 다른 성별 얼굴이 섞인다. 그래서
   `any`로 두고 `select_lists`에서 걸러 낸다.

## 4. 사람 확인이 필요한 것

1. 랭키파이가 인용한 한국기업평판연구소 지수를 자동 수집·재사용해도 되는지(원자료 창구
   `data@brikorea.com`). robots와 사이트 문서만으로는 판단할 수 없다.
2. 랭키파이에 이용약관이 없다는 점이 "금지하지 않음"인지 "규정 밖"인지. 필요하면 운영자에게
   문의해 회신을 기록한다.
3. FUNdex를 대안으로 쓸 경우의 약관·주간 주기·성별 분류 부재 문제.
4. 순위 목록을 실제로 한 번 수집해 S1까지 통과시키는 실행은 사용자 지시 뒤 통합 단계에서 한다
   (P-24). 이번 작업은 dry run과 합성 응답까지만 했다.

## 5. 확인하지 못한 것

- 랭키파이 화면이 월중에 바뀌는지(과거 월 페이지 보존 여부). 2026-10-27 시점 화면은 "2026년 9월"
  발표다.
- `robots.txt`가 실제 수집 시점에도 같은 내용인지. 어댑터는 실행 전 dry run에서 확인 날짜를
  같이 보여 주지만, robots 재확인은 자동화하지 않았다.
- 각 사이트의 저작권 정책 원문(푸터 고지만 확인).
