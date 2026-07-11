# 계층형 하네스 아키텍처

```text
Pixel Office Canvas UI
        │ Harness Events
        ▼
Harness Service
├── Hierarchical Scheduler
├── Capability Router
├── Shared Agent Pools
├── Artifact / Handoff Contract
└── Model Gateway
    ├── Ollama Lane       1 slot
    ├── Hugging Face Lane 1 slot
    └── OpenRouter Lane   2 slots
```

## 설계 원칙

- 에이전트 수와 실제 모델 실행 수를 분리한다.
- Manager와 Coordinator는 계층형으로 통제한다.
- Collector와 Summarizer는 특정 팀에 고정하지 않고 공용 capability pool로 제공한다.
- 업무 의존성은 순환이 없는 DAG로 검증한다.
- 중요한 산출물 전달은 `handoff.requested` 이벤트로 추적한다.
- 시각화는 실행 이벤트를 소비하며 존재하지 않는 모델 실행을 연출하지 않는다.
- 공개 데모는 비용 없는 결정적 이벤트를 사용한다.
- 사이트 오너 키는 암호 인증 후 10분 유효 토큰으로 접근한다.
- 개인 키는 요청별 Model Gateway에만 주입하고 환경변수·실행 기록에 저장하지 않는다.
- 외부 API 용량 점검과 실제 호출은 관리자 CLI에서만 명시적으로 실행한다.
