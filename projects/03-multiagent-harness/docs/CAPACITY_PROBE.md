# Provider Capacity Probe

`capacity_probe.py`는 OpenRouter·Hugging Face의 단일 API 키 동시 요청 가능량과 Ollama 실행 시간을 관리자 CLI에서 보수적으로 확인합니다.

## 무과금 사전 점검

```bash
python3 capacity_probe.py
```

모델 목록, provider 설정 여부와 기본 동시성만 확인하며 모델 생성 API는 호출하지 않습니다.

## 실제 호출 점검

실제 호출에는 반드시 `--confirm-live`가 필요합니다.

```bash
python3 capacity_probe.py \
  --model openrouter:openai/gpt-4o-mini \
  --concurrency 2 \
  --requests 2 \
  --max-tokens 16 \
  --confirm-live
```

안전 제한:

- 최대 동시성: 4
- 최대 요청 수: 4
- 요청당 최대 출력: 32 tokens
- 자동 재시도: 없음
- 결과를 운영 설정에 자동 반영하지 않음

공개 홈페이지에는 이 기능을 노출하지 않습니다. 실제 호출 결과를 확인한 관리자가 `.env`의 provider별 concurrency를 수동으로 조정합니다.
