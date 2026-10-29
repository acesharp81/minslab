# Solar API 설정 및 모델 확인 — 2026-10-29 (한국시간)

분석 모델 선택란의 GPT-5.4 mini 뒤 `일 1,000만 토큰` 문구를 삭제했습니다. 모델 값·기본 선택 및 잔량 집계는 유지합니다.

현재 키로 공식 `GET https://api.upstage.ai/v1/models` 요청이 HTTP 200을 반환했습니다. 현재 설정은 `UPSTAGE_MODEL=solar-pro4`, `UPSTAGE_BASE_URL=https://api.upstage.ai/v1`입니다. 목록에 solar-pro4 및 solar-pro4-260806, solar-mini4 및 solar-mini4-260922, 이전 Pro 2/3, 구 Mini, Syn-Pro, 구조화 의사결정용 모델들이 포함되었습니다. 목록 노출만으로 모든 모델의 실제 생성 권한을 보장하지 않습니다.

공식 문서에서 Solar Pro 4는 현재 대표 범용 모델이며, 더 상위 범용 Solar 모델은 확인되지 않았습니다. Solar Mini 4는 비용·속도 중심의 소형 대안입니다. Solar Decide는 베타 의사결정 API이며 설명문을 생성하지 않아 현재 검수 의견 생성 모델을 그대로 대체하지 못합니다. Pro 2/3과 구 Mini는 공식 문서상 2026-10-30 KST 종료 예정이므로 대안으로 채택하지 않았습니다.

현재 서비스의 `/v1/responses`·Bearer 인증·텍스트 입력·JSON Schema 출력은 공식 규격과 일치합니다. 실제 사용자 이미지를 보내지 않고 합성 손 관찰 두 건으로 표준(none)과 추론(low)을 각 두 차례, 총 네 번 호출했습니다. 모두 HTTP 성공 및 서비스의 객체별 배열 스키마 검증에 통과했고 실제 모델은 `solar-pro4-260806`이었습니다. 총 16,916 토큰, 표준 요금 환산 $0.0073392를 기존 공용 사용량 경로에 기록했습니다.

첫 간소화 규칙 시험에서 오류 조건을 발견한 것을 PASS로 해석하는 응답이 나왔습니다. 상태 필드 설명과 공통 프롬프트에 '품질 정상=PASS, 결함 발견=FAIL, 가림·미확정=REVIEW'를 명시하고 운영 규칙 원문·공통 지침으로 다시 확인했습니다. 후속 두 호출 모두 명확한 여섯 손가락은 FAIL로 반환했습니다. 표준은 다른 손을 누락했고 low는 가려진 손을 PASS로 반환했으므로, 이 작은 시험은 정확도 검증 완료나 다른 모델보다 우수하다는 근거가 아닙니다. 기존 서버의 가림 품질 제한은 PASS를 REVIEW로 내립니다.

추론 강도는 `UPSTAGE_REASONING_EFFORT`로 선택할 수 있게 연결했습니다. 사용자가 무료 키이며 성능을 우선한다고 확인하여 운영 `.env`는 `high`로 설정했습니다. 설정이 없는 독립 설치의 기본값은 `none`이며 `low` 이상은 추론 토큰·지연이 늘 수 있습니다. 공개 화면의 기본값은 계속 GPT-5.4 그림 읽기 + GPT-5.4 mini 분석입니다. Solar보다 상위인 모델로 자동 전환하거나 검증되지 않은 모델을 선택란에 추가하지 않았습니다.

참고:
- https://console.upstage.ai/docs/models/solar-pro-4
- https://console.upstage.ai/docs/models/solar-mini-4
- https://console.upstage.ai/api/responses
- https://console.upstage.ai/docs/capabilities/generate/reasoning
- https://console.upstage.ai/docs/models/solar-decide

최종 high 실호출은 8.01초, 입력 5,305 + 출력 737 토큰으로 완료됐습니다. 두 객체 응답을 모두 받았고 서버 검증 후 명백한 여섯 손가락은 FAIL, 가려진 손은 REVIEW로 처리됐습니다. 총 검증 5회는 22,958 토큰이며 실제 사용자 이미지 없이 합성 관찰만 사용했습니다. 이 표본으로 광범위한 검수 정확도를 입증하지는 않았습니다. 사용자가 무료 키임을 확인했으며 기록의 USD는 표준 요금 환산값이지 실제 청구액이 아닙니다. 선택란의 Solar 표기는 `Solar Pro 4 · 고강도 추론`입니다.
