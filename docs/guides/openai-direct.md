# 공식 OpenAI API 연결

2026-11-12 D-0193. 기존 OpenAI 판정·비전과 기준 사진 생성에 공식 API를 사용한다. Gemini 원문·프롬프트 생성과 Grok 영상은 별도 공급자로 유지한다.

```toml
[providers.judge]
adapter = "openai_compat"
base_url = "https://api.openai.com/v1"
model = "gpt-6.1-sol"
api_key_env = "OPENAI_API_KEY"
reasoning_effort = "low"
max_retries = 0

[providers.vision]
adapter = "openai_compat"
base_url = "https://api.openai.com/v1"
model = "gpt-6.1-sol"
api_key_env = "OPENAI_API_KEY"
max_retries = 0

[providers.image]
adapter = "openai_images"
base_url = "https://api.openai.com/v1"
model = "gpt-image-2.6-sunburst"
api_key_env = "OPENAI_API_KEY"
quality = "high"
complexity = "medium"
estimated_cost_usd = 1.0
max_retries = 0
timeout_s = 600
```

키는 실행 루트의 Git 제외 `.env` 또는 서버 환경변수에 둔다. 키 값을 TOML·명령 인자·로그·보고서에 넣지 않는다. 생성용 text도 OpenAI를 쓸 때는 judge와 같은 공식 주소를 설정하되 생성/판정 모델 계열 분리 규칙을 확인한다.

참조 파일이 있으면 모든 파일을 multipart `/images/edits`에 보내고, 없으면 `/images/generations`를 호출한다. size·quality·complexity와 PNG 한 장을 명시한다. 모델 접근 또는 요청 실패 시 구독이나 중계로 폴백하지 않는다. `codex_image`는 명시적인 별도 선택으로 남는다.

`estimated_cost_usd`는 장당 계획용 추정값이다. 1달러는 이번 설정의 보수적 가정이며 고정 요금 또는 공급자 청구 상한이 아니다. 사전 확인은 추정값이 없으면 실행을 막는다. 사용량에 따른 정확한 이미지 비용 계산은 아직 연결하지 않았으므로 완료 원장의 미확인 금액은 null로 남긴다. PNG 서명과 실제 디코딩이 모두 성공해야 이미지 생성 성공으로 기록한다.

2026-11-12 실제 연결 검사: 공식 모델 목록 조회200, 텍스트4.50초, 사진 분석5.95초, 합성 참조 이미지 편집18.46초(720×1280). 이는 작은 합성 입력 1회씩의 연결 검사이며 실제 인물 동일성·전체 공정 지연 개선·영상 품질 검증이 아니다.

근거: [OpenAI 이미지 생성 안내](https://developers.openai.com/api/docs/guides/image-generation), [GPT Image 2.6 Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.6-sunburst), [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol). 모델 접근 권한은 이번 계정의 실제 API 조회로 별도 확인했다.
