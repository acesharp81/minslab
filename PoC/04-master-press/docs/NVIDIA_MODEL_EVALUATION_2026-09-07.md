# NVIDIA 케이스 모델 교체 평가 — 2026-09-07

기존 NVIDIA 무료 `openai/gpt-oss-120b`는 2026-09-03 17:00 KST에 종료되어 HTTP 410을 반환한다. 대체 모델은 `nvidia/nemotron-3-super-120b-a12b`다.

## 평가 범위와 결과

운영 기사·케이스를 외부로 재전송하는 평가는 자동 승인 검토에 의해 차단되어 실시하지 않았다. 대신 새로 작성한 합성 한국어 기사 12개와 합성 케이스 5개를 사용했다. 실제 운영 DB를 읽거나 쓰지 않았으며, 평가 호출은 운영 사용량 통계에 기록되지 않는다.

- 12배치 × 5케이스 = 60건
- 배치 결과 완결성: 12/12, 60/60
- 작성 시 미리 지정한 기대 판정과 일치: 60/60 (발송 11, 제외 49)
- 발송 근거 검증 실패: 0
- 평균 요청 시간: 6.608초 (최소 4.056, 최대 15.750초)
- 범위: 디지털 행정, 지방재정, 재난안전, 기관 직접 비판, 공무원 교육; 타 기관, 무관 기사, 배경 언급을 포함

이 수치는 합성 검증 결과이며 실제 기사 정확도나 기존 모델과의 동등성을 입증하는 대조시험 결과가 아니다. 합성 평가는 임베딩 영향을 배제하여 LLM 가중치 1로 실행했다. 운영 가중치와 판정 프롬프트는 변경하지 않는다.

## 적용

- NVIDIA 케이스 모델을 Nemotron 3 Super로 변경하고 5케이스 배치를 유지한다.
- `chat_template_kwargs.enable_thinking=false`를 해당 모델에만 적용하여 3,200~4,096 출력 토큰을 JSON 생성에 사용한다.
- NVIDIA 모델 식별과 관리자 표시를 갱신한다.
- 기존 OpenAI 보조·OpenRouter 단건 경로와 대기 큐는 유지한다.

재현:

```bash
PYTHONPATH=PoC/04-master-press .venv/bin/python -m master_press.nvidia_canary --output /tmp/nemotron-canary.json
```

공식 자료:
- https://build.nvidia.com/openai/gpt-oss-120b
- https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b
- https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Super-Technical-Report.pdf

## 운영 적용 확인

- 07:52:58 KST DB `case_model1` 선택값을 변경했다. 기존 환경파일과 설치된 systemd 유닛은 변경하지 않았다.
- 웹과 워커 9개를 모두 명시하여 재기동했고 10개 서비스 active 및 `/health` 정상 응답을 확인했다.
- Python 회귀 테스트 190개, JS 구문 검사, diff 검사를 통과했다.
- 다음 값은 교체 직후 관측치이며 실제 판정의 정답률을 뜻하지 않는다.

```json
{
  "observed_at": "2026-09-07T07:54:58+09:00",
  "calls": [
    [
      "completed",
      200,
      5,
      13837.0
    ]
  ],
  "completed_judgments": 25,
  "send": 6,
  "unverified_sends": 0,
  "fallbacks": 0
}
```
