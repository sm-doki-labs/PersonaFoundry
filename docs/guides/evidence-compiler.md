# 승인 카드로 8개 섹션의 프롬프트 만들기

S8의 `evidence_compiler.py`는 승인된 JSON 한 건을 읽어 UTF-8 프롬프트 한 건을 쓴다. Python 표준 라이브러리만 사용하며, 모델을 호출하거나 공장 설정을 바꾸지 않는다.

## 실행

Character Factory에서는 oneclick 저장소 루트에서 같은 컴파일러를 실행한다.

```sh
PYTHONPATH=src .venv/bin/python -m character_factory_poc.stages.s8_prompts.evidence_compiler examples/evidence/synthetic.json /tmp/cfp-evidence-demo.md
```

이 버전의 패키지를 설치하면 `cfp-compile-evidence INPUT.json OUTPUT.md`로도 실행할 수 있다. Python에서 문자열이 필요하면 다음 함수를 호출한다.

```python
from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt

prompt = compile_prompt(packet)  # dict -> str; 잘못된 입력은 ValueError
```

## 검토 단계와의 연결

oneclick의 사전 분석·검토 도구 위치는 `scripts/evidence_workflow/`이다. [전체 공정](../../scripts/evidence_workflow/README.md)의 prepare.py와 form.py는 대화 분리, 화행 표집, 승인 카드 검증부터 이 컴파일러 호출까지 연결한다. 검토자는 원문과 근거를 대조하고 채택한 카드만 최종 JSON의 `sections`에 넣는다. 이후 이 문서의 CLI에 그 JSON을 전달한다. 컴파일러가 검토 도구를 호출하거나 카드의 승인을 대신하지는 않는다. 현재 공장의 새 모티브 기본 경로는 같은 컴파일 함수를 직접 호출한다. 실제 S8·G6·시연·내보내기 연결은 [공장 실행 안내](evidence-pipeline.md)를 따른다. 아래 독립 CLI는 별도로 유지한다.

## 입력 계약

[`examples/evidence/synthetic.json`](../../examples/evidence/synthetic.json)에 완전한 입력 예가 있다. 다음 여섯 키를 모두 사용하며 그 밖의 키는 허용하지 않는다.

| 키 | 값과 용도 |
| --- | --- |
| `role`, `scene` | 역할과 장면을 각각 비어 있지 않은 문자열로 넣는다. 두 값은 섹션 앞에 입력 그대로 들어간다. |
| `facts` | 승인된 사실을 문자열 하나로 넣는다. 앞뒤 공백, 줄바꿈, 탭을 포함해 그대로 `[FACTS]`에 들어간다. |
| `trainIds`, `holdoutIds` | 자료 식별자를 문자열 배열로 넣는다. 각 배열 안에 중복이 없어야 하며 두 배열은 서로 겹칠 수 없다. |
| `sections` | 승인된 카드의 배열이다. 승인한 카드가 없으면 빈 배열을 쓴다. |

각 카드에는 `section, trigger, first, shift, stop, limit, evidence, rule`이 모두 있어야 한다. `evidence`는 중복 없는 `trainIds` 참조를 하나 이상 담고, 나머지 값은 비어 있지 않은 문자열이다. `section`에는 아래 순서에서 `FACTS`를 제외한 이름만 쓴다. `FACTS`는 오직 최상위 `facts`에서 가져온다.

출력 순서는 `FACTS → LIFE_AND_TASTES → DISPOSITION → WANTS_AND_FEARS → READING_AND_TENSION → CHOICES → VOICE → KNOWS_AND_LIMITS`로 고정한다. 같은 섹션 안에서는 카드 입력 순서대로 `rule`만 옮긴다. 조건이나 한계가 실제 응답에 적용되어야 한다면 검토 단계에서 그 내용을 `rule` 자체에 반영한다. 근거 ID와 작업 메모는 출력하지 않는다. 카드가 없는 섹션에는 “자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다.”라고 표시한다.

## 거부하는 입력과 검사의 한계

필수 키가 빠지거나 다른 키가 추가된 경우, 섹션 이름이 틀린 경우, 카드가 미등록 ID 또는 평가용 ID를 인용한 경우에는 출력을 만들지 않는다. CLI는 JSON의 중복 키도 거부한다. 검증 오류 시 종료 코드는 2이며 기존 출력 파일을 보존한다.

예시 전용 필드, 명시적인 화자 표기(`USER:`, `MODEL:` 등), 예시 표시, 규칙에 큰따옴표로 묶은 인용문, 본문 안에 다시 넣은 섹션 제목도 거부한다. 승인 사실표의 따옴표 고유명사는 그대로 보존한다. ID 목록만으로는 평문이 실제 원문에서 복사됐는지, 참조 자료가 규칙을 뒷받침하는지 판단할 수 없다. 두 가지 모두 검토자의 확인이 필요하다. 원문이나 평가용 대화는 컴파일러 입력에 포함하지 않는다.

저장소에서는 `.venv/bin/python -m pytest -q tests/test_evidence_compiler.py tests/test_persona_compiler.py`로 새 입력 계약과 기존 페르소나 컴파일 동작을 함께 확인한다.
