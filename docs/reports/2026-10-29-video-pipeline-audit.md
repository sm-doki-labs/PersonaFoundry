# 영상 파이프라인 구현 감사 — 2026-10-29

## 범위와 결론

최근 도구·워크숍·승인 후 자동 재개를 구현한 `character-factory-poc`를 기준으로 검사했다. 이전 `agentic-character-factory`의 실제 이미지 산출물은 별도 근거로만 확인했다. 제품 코드 수정과 외부 생성 호출은 없었다.

현재는 이미지 제작 및 영상 작업 관리 골격이 구현되어 있다. 실제 영상 세트의 일관성·연결성을 보장하는 운영 파이프라인으로 판정할 수 없다. 실제 factory.toml에는 providers.video가 없어 fake가 선택되며, image_qa.enabled=false다.

## 1. 키 비주얼 선택

S1은 순위 인물의 공통 외모 특징으로 외모군을 만들고, 군마다 얼굴 이미지를 생성한다. 기본 cluster_k=4, previews_per_cluster=1이며 실제 후보 수는 유효 외모군에 따른다. 사람이 G1에서 얼굴 한 장을 선택한다. 현재 S2는 picked로 그 파일을 그대로 기준 사진으로 고정한다. G2는 새 경로에서 쓰지 않는다. generate 모드는 실행 전 거절한다.

이미지 어댑터는 codex_image다. ChatGPT 웹 화면을 조작하지 않고 Codex CLI의 내장 이미지 생성 도구를 호출한다. 설정의 gpt-6.1-sol은 CLI를 구동하는 모델명이므로 이미지 생성 엔진의 정확한 버전이 확인됐다는 뜻은 아니다.

S1 프롬프트: `Character reference portrait of a fictional {subject} in their {ageRange}, {artStyle} style.` 뒤에 Appearance/Styling/Mood 공통 특징을 넣고 `Upper body, neutral background, soft natural light. An original person, not based on any real individual.`을 붙인다. 금지 항목은 text, watermark, logo다.

근거: src/character_factory_poc/stages/s1_reference/{run,preview}.py, stages/s2_hero/run.py, providers/codex_image.py.

## 2. 레퍼런스 주입

S1 얼굴 후보 생성은 텍스트 입력이며 실존 인물 사진을 첨부하지 않는다. 최신 S2 picked는 생성 호출 자체가 없고 선택한 얼굴을 복사한다. heroPrompt는 저장되지만 현재 경로에서 모델에 호출되는 프롬프트가 아니다. 동일인 검사는 SKIPPED, attempts=0이다.

이전 서비스 S2는 선택한 얼굴을 reference_images로 넣어 대표 사진 후보를 만들었으며 실제 ar2/inputs.json에도 referencePreviews가 있다. 최신과 이전 동작을 혼동하면 안 된다. 이후 S4는 기준 얼굴과 배경 이미지를 실제 참조 입력으로 사용한다.

## 3. 배경 후보

scene_scout가 승인 기획의 생활 동선·취향·관계 단계를 읽고 챕터당 3개, 총9개 후보를 쓴다. ch1 첫 만남, ch2 첫 데이트, ch3 고백이다. 각 후보에 장소·시간·분위기·캐릭터가 있을 이유·관찰 사실·경계·영문 plateBrief를 작성한다.

이미지 프롬프트는 `Photorealistic empty background plate of a realistic modern Korean place.`에 Place/Time/Light and color와 plateBrief를 붙인다. `Vertical 9:16 composition, preserve room for a foreground subject to be added later.` 및 사람·실루엣·사람 반사·글자·브랜드 금지를 포함한다. G4a에서 챕터마다 한 장을 선택하거나 직접 정의한다.

근거: prompts/scene_scout.md, stages/s4a_backgrounds/{run,prompt}.py.

## 4. 배경에 캐릭터 배치

S4b가 장면 사실과 자세·손·소품·시선·표정·의상·구도·motionHint를 작성하고 G4b에서 고른다. S4는 참조1=얼굴, 참조2=배경을 이미지 모델에 함께 보내 새 완성 이미지를 생성한다. 단순 잘라 붙이기나 배경 픽셀 보존 합성이 아니다.

프롬프트는 `Reference image 1 is the identity reference: use its face for identity only.`와 `Reference image 2 is the empty background plate: keep the same place, light and layout.`을 사용한다. 얼굴만 참조해 원본 자세·옷이 새 장면으로 복사되지 않도록 지시한다. 얼굴 크롭 배율은1.4이며 검출 실패 시 전체 사진으로 대체한다. 챕터별 완성 이미지1장, 총3장을 G4에서 승인한다.

이전 서비스의 cf-20261021-s2real/s4-frames/fr1에는 실제3장이 있다. 직접 열어 확인했으며 같은 캐릭터로 읽히는 인상은 유지되지만 구도·거리·손에 든 소품은 다르다. 이는 정량 동일인 합격이나 영상 연결 합격이 아니다.

## 5. 움직임 생성

G4 승인 이미지3장을 good 첫 프레임으로 복사하고, 같은 사진에서 표정만 바꾼 neutral/bad 첫 프레임3장을 추가 생성한다. 동작의 mood에 따라 good/bad 첫 프레임을 선택해 VideoRequest에 first_frame, prompt, duration, resolution, aspect_ratio, generate_audio를 보낸다. 각 영상은 해당 정지 이미지에서 독립적으로 생성되며 이전 영상 마지막 프레임을 다음 영상으로 넘기지 않는다.

무표정 편집 지시: 같은 사람·얼굴·머리·자세·손·옷·배경·빛·구도를 유지하고 표정만 calm neutral unsmiling, closed lips, eyes open으로 바꾼다.

영상 어댑터는 fake/xai_video/grok_oauth/grok_web가 있으나 현재 루트 설정은 fake다. 실제 S6 전 과정 검증은 없다.

## 6. idle 수

각 챕터는 idle_good(미소)와 idle_bad(무표정) 2편을 가지므로 3챕터에서6편이다. 현재 기본 후보 수1일 때의 값이며 후보 수N이면 idle 생성 호출은6N이다.

| 프리셋 | 챕터별 | 3챕터 합계 |
|---|---|---|
| l2 기본 | idle2 + 반응4 | idle6 + 반응12 =18편 |
| standard | idle2 + 반응35 | idle6 + 반응105 =111편 |

기본 요청 길이는 idle15초, 감정10초, special6초다. special은 설정 칸만 있고 실제 특별 행동 카탈로그는 없다. 기본 설정에서 l2 총210초, standard 총1140초이며 재생성·소개 영상은 제외한다. 이 수는 구현 카탈로그 기준이며 사용자 체감에 필요한 최적 수를 검증한 결과는 아니다.

주의: G5b는 챕터별 하나 이상의 영상만 요구한다. idle_good/bad 두 편을 반드시 남기도록 강제하지 않아 idle 없는 세트도 승인될 수 있다.

## 7. 행동 세트 작성

현재 S6는 행동을 새로 기획하는 에이전트가 아니라 기존 앱의 고정37클립 카탈로그에서 프리셋으로 선택한다. l2는 idle_good, idle_bad, glad_good, amused_good, shy_good, sorry_good다. 고정 motion에 챕터 관계 메모와 동일 인물·의상·배경 유지 지시, 수정 메모를 붙인다.

예를 들어 glad_good는 반갑게 웃고 몸을 조금 기울이며 손을 흔든 후 원래 미소와 자세로 돌아오도록 한다. G5b에서 동작별 선택·제외·부분 재생성이 가능하다.

장면 소품을 쓰는 특별 행동3~5개를 제안하는 에이전트와 앱 공용 특별 행동27편은 미구현이다. S4b motionHint도 S6 build_prompt에 전달되지 않는다. 카메라를 들고 서 있는 시드에도 고정된 앉기·손 흔들기 문장이 적용될 수 있다.

## 8. 일관성·연결성

현재 실제 적용 수치/방법은 동일 첫 프레임 재사용, 얼굴 크롭1.4, 9:16, 기본720p, 후보1(허용1~4), idle15초/감정10초, 무음, SHA256과 revision 추적이다. 프롬프트로 같은 인물·의상·배경 유지 및 일부 반응의 원래 표정·자세 복귀를 요구한다. 해시는 입력 파일 동일성을 증명하며 시각적 동일성을 측정하지 않는다.

이미지 QA에는 배경4항목·합성6항목의 PASS/FAIL/UNSURE와 수정 최대2회(총3시도)가 있으나 현재 꺼져 있다. 영상은 MP4 표식과 ffprobe 메타데이터를 기록한다. ffprobe 실패 자체가 승인 차단은 아니며 요청 길이/해상도와 실제 값의 일치도 강제하지 않는다.

미구현: 마지막 프레임 강제, 생성 난수 seed/FPS 고정, 얼굴 유사도·포즈 변위·루프 이음새 임계값, idle↔reaction/미소↔무표정 전환 검증, 영상 자동 품질 판정. 영상 HTML의 loop 속성은 이음새 검사 기능이 아니다.

추가 불일치: 배경 기획의 ch3는 고백이나 S6 메모는 dating이다. 고정 영상 프롬프트에 she·대부분의 몸이 보이는 원거리 구도·앉기가 남아 있어 남성/서 있는 시드/근접 구도와 충돌할 수 있다.

## 검증과 우선순위

오프라인142개(reference/hero/frames/image_qa/video/actions) +48개(scene_flow/codex_image), 총190개 통과. 외부 호출0. 통과는 제어 흐름과 어댑터 계약 검증이며 실제 영상 품질 증거가 아니다.

후속 제안은 장면·성별·구도·소품에 맞는 동작 프롬프트와 관계 단계 정합성, idle 필수 유지 조건을 먼저 보완하는 것이다. 그다음 한 장면의 두 idle와 반응을 실제 생성해 마지막 프레임·루프·전환 품질을 확인하고, 실제 관측에 근거해 임계값을 정한 뒤 전체 세트로 확대한다. 이번 감사는 이 개선을 구현하거나 실제 생성하지 않았다.
