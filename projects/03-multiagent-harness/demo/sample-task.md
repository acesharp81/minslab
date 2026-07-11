# 가상 공공서비스 예약시스템 장애 대응

전국 공공서비스 예약시스템이 오전 9시부터 11시까지 접속 장애를 겪었다는 민원이 다수 발생했다.

언론 문의와 국회 질의 가능성에 대비해 현안 대응 패키지를 만들어줘. 보고 대상은 실장급이고, 대외 설명자료와 예상 Q&A도 포함해줘. 실제 기관명이나 실제 개인정보는 사용하지 말고 가상 상황으로 작성해줘.

## 데모 관찰 지점

1. Mission Manager가 Coordinator들을 Whiteboard로 호출한다.
2. Collector Pool의 두 에이전트가 서로 다른 자료를 준비한다.
3. Collector가 Shared Summarizer에게 직접 문서를 전달한다.
4. Model Broker에 Local LLM 1, Hugging Face 1, OpenRouter 2 슬롯이 표시된다.
5. Technical Analyst와 Legal Reviewer 결과가 Document Coordinator로 전달된다.
6. Risk Checker가 빨간 문서를 Briefing Writer에게 반송한다.
7. 수정본 재검증 후 Final Synthesizer가 Filing Cabinet에 최종 패키지를 보관한다.
