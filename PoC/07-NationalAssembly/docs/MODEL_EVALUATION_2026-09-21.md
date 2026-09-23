# 회의 보고서 모델 점검 (2026-09-21)

## 운영 표본

- 현재 회의 보고서 모델 `dots-studio/dots-3-note-preview:free`의 최근 저장본 9건은 빈 요약·빈 주제 없이 구조 검증을 통과했다.
- 다만 최신 43개 발언 보고서에서 `서영교장`, `증인 혼의`, `미연다` 같은 오탈자와 의미 중복 주제가 확인됐다.
- Dots 저장본은 회의당 평균 56.8개 세부 주제였고, 긴 회의는 86~140개까지 증가했다. 일부는 최종 합성 뒤 미연결 LIVE cluster를 모두 독립 주제로 승격한 로컬 정책의 영향이다.
- 현재 모델의 남은 실패 2건은 `ConnectionError`이며 구조화 JSON 실패가 아니다. 과거 Mistral Small 2603에서는 `JSONDecodeError`, `ValueError`, HTTP 오류가 저장돼 있다.

## 후보 판단

### OpenAI GPT-5.4 mini

- 공식 모델 ID는 `gpt-5.4-mini`이며 Chat Completions와 Structured Outputs를 지원한다.
- 400k context, 최대 128k output으로 긴 회의의 최종 합성과 엄격한 JSON 계약에 여유가 있다.
- 공식 가격은 입력 $0.75/백만 토큰, 출력 $4.50/백만 토큰이며 API Free tier는 지원하지 않는다.
- 따라서 무료 대체재가 아니라, OpenAI 프로젝트 예산과 PoC 7 전용 secret을 승인한 뒤 **최종 합성 1회**에 한정하는 품질 보강 후보가 적합하다. 청크 분석까지 전환하면 비용과 외부 전송량이 불필요하게 커진다.

출처: <https://developers.openai.com/api/docs/models/gpt-5.4-mini>

### NVIDIA NIM Nemotron 3 Super

- 공식 모델 ID는 `nvidia/nemotron-3-super-120b-a12b`이며 OpenAI 호환 Chat Completions, 최대 1M context, reasoning `none/low/high`를 지원한다.
- NVIDIA 문서는 권장 temperature 1.0/top_p 0.95와 영어·프랑스어·독일어·이탈리아어·일본어·스페인어·중국어를 명시하지만 한국어는 지원 언어에 포함하지 않는다.
- 공용 OpenRouter를 통한 같은 계열 무료 모델은 과거 10건을 생성했으나 주제 수 편차가 1~94개로 컸다. 당시 계약 버전 차이도 있어 모델 단독 비교로 보기는 어렵다.
- 따라서 NVIDIA API trial 잔여량은 원본을 덮어쓰지 않는 shadow canary와 긴 문맥 누락 검사에 사용할 수 있지만, 한국어 최종 보고서의 단독 기본 모델로 승격하지 않는다. 사용 시 PoC 4의 파일이나 환경을 runtime으로 참조하지 않고 PoC 7 전용 secret으로 복제·관리해야 한다.

출처: <https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b>

## 적용 결정

1. 즉시 적용은 모델 변경보다 `assembly-meeting-brief/1.9` 품질 계약을 우선한다. 최종·승격 주제 합계를 24개로 제한하고 남는 cluster는 근거를 보존한 미연결 검토 대상으로 두며, 운영 표본에서 확인된 명백한 표시 오인식은 결정적으로 교정한다.
2. 기존 `assembly-meeting-brief/1.2` 청크 캐시를 재사용해 최종 합성만 다시 실행한다. 공용 OpenRouter gateway의 950회 안전선은 유지하되 PoC 4 중단으로 생긴 잔여량을 PoC 7 재합성에 사용할 수 있다.
3. GPT-5.4 mini는 동일 입력의 최종 합성 A/B 평가에서 사실 오류, 오탈자, 중복 주제, 근거 ID 보존을 통과하고 별도 예산·secret이 준비된 뒤 선택적으로 도입한다.
4. Nemotron 3 Super direct NIM은 한국어 품질 때문에 shadow 후보로만 평가한다. 저장 결과를 현재 보고서에 자동 승격하지 않는다.
