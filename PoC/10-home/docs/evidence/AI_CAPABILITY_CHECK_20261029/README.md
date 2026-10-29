# HOME AI 자동화 API 연결 검증 · 2026-10-29

실제 등록된 키로 Solar Pro 4와 GPT-5.2의 API 기본 기능을 확인했다. 이는 자동화 구현의 연결 가능성 검증이며, 운영 자동화나 코드 자동 배포를 구현·활성화한 결과가 아니다.

## 범위와 결과

- HOME 전용 `.env`의 `UPSTAGE_SECRET_KEY`로 Solar Pro 4 검증. 루트의 Upstage 키들과 값이 다르므로 암묵적 대체를 사용하지 않았다.
- 루트 `.env`의 `OpenAI_API_KEY`로 GPT-5.2 검증.
- Responses API에서 모델별 구조화 출력, 읽기 전용 합성 도구 호출, 도구 결과를 반영한 중복 처리 판단, 날짜 추출 규칙 제안을 각각 1회 확인했다.
- 합성 추출 사례에는 기대 수치를 지시했다. 복잡한 공고 해석 정확도를 측정하는 성능평가가 아니다.
- 중복 조회는 합성 결과를 반환하는 도구이며 실제 운영 DB에 접근하지 않았다. 중복 발견 시 `SKIP_DUPLICATE`, `approved=false` 반환을 확인했다.
- 모델이 제안한 정규식은 사전에 고정하고 모델에 제공하지 않은 8개 사례에서 각각 모두 통과했다. 임의 생성 Python 코드의 실행·수정·배포는 하지 않았다.
- 추가 1회 GPT-5.2 소규모 호출로 처리 한도 헤더 제공 여부를 확인했다. 계정 무료 제공량이나 잔액을 조회하는 호출은 아니다.
- 모든 호출은 `reasoning.effort=none`, `store=false`; 입력은 합성 자료만 사용했다. `store=false`를 데이터 공유 혜택 설정으로 해석하지 않는다.

| 모델 | 결과 | 입력 토큰 | 출력 토큰 | 공개 단가 기준 추정 |
| --- | --- | ---: | ---: | ---: |
| solar-pro4 | passed | 934 | 121 | $0.000425 |
| gpt-5.2 | passed | 548 | 134 | $0.002835 |

총 API 요청 9회. 추정 합계 $0.003260. [세부 결과](results.json), [고정 검증사례](fixed_cases.json).

공개 표시 단가를 사용한 계산이며 실제 청구액이 아니다. OpenAI 무료 토큰·계정 크레딧이나 Upstage 할인·세금은 반영하지 않았다. 사용자 안내의 Upstage $110은 한도로 취급하며 현재 남은 잔액이나 공급자 측 차단 설정은 확인하지 않았다.

## 플랜에 적용할 결론

1. 모델 연결·구조화 결과·함수 호출을 사용한 실행 루프는 두 제공사로 구현 가능하다.
2. 실제 검색·원문 취득·정답 데이터셋 기반 복합 회귀검사·코드 격리 실행·승인·배포는 별도 구현 및 검증 대상이다. 이번 8개 날짜 표본으로 운영 안정성을 입증했다고 주장하지 않는다.
3. 신규 자료는 후보로 등록하고, 신규 정책·사업 연결 및 실적 확정은 담당자 판단으로 남긴다.
4. 코드 변경은 격리환경에서 수정·시험하고 운영 반영은 승인한다. 모델이 고정 정답 자료와 검사 기준을 수정할 수 없게 분리한다.
5. HOME worker에 사용할 키를 명시적으로 지정한다. 새로운 HOME 키를 루트의 기존 Upstage 키로 자동 대체하지 않는다.
6. 비용은 제공사·키별로 구분해 누적하며, 호출 전 최대 예상비용 예약과 완료 후 실제 토큰 정산을 적용한다. 예산 확인 불가 시 무제한 대체 호출을 하지 않는다. 아직 이 예산 제어가 구현된 상태는 아니다.
7. 운영 데이터·기존 승인·배포·자동 수집 예약·키·계정 결제 및 데이터 공유 설정은 이번 검사에서 변경하지 않았다.

## 비용 및 계정 확인

OpenAI 무료 토큰 혜택 가입 여부, 구독자 API 크레딧, 사용자 설명의 65만 토큰의 의미는 이번 API 성공 결과만으로 확인되지 않는다. 계정의 공유 설정·Limits·Usage·Billing 화면을 대조해야 한다.

- [Upstage Responses API](https://console.upstage.ai/api/responses)
- [Upstage 공개 요금](https://www.upstage.ai/pricing/api)
- [GPT-5.2 모델·요금](https://developers.openai.com/api/docs/models/gpt-5.2)
- [OpenAI 무료 토큰 조건](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai)
- [OpenAI API 티어](https://developers.openai.com/api/docs/guides/rate-limits)
- [ChatGPT 구독자 API 크레딧](https://developers.openai.com/api/docs/guides/chatgpt-api-credits)
