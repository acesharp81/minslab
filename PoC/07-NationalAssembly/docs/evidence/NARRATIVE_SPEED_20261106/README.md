# 세부요약 처리 속도 보완 — 2026-11-06

- 운영 배포: 정리 워커만 poc07-narrative-speed:20261106으로 교체. 기존 환경·예산·네트워크·볼륨 보존. API와 실시간 요약 워커는 재시작하지 않았다.
- Nemo3.5 structured_narrative 요청만 추론 비활성화. 공식 지원 확인: https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free 및 https://openrouter.ai/docs/guides/best-practices/reasoning-tokens .
- 같은 보고서/모델/현재 요청정책의 최근 15분 마지막 두 응답이 length이면 다음 호출에서 해당 모델을 우회한다. 이전 low 설정 실패나 품질 검증 오류와 섞지 않는다.
- 묶음 합계 24 발언 기준 추가. 단일 쟁점에 24개 넘는 발언이 있으면 원문/발언을 자르지 않는다.
- 활성 LIVE 1개면 최대 2배치, 2개 이상/예정 방송 임박이면 1배치. 기존 요청 상한 안에서만 조정한다. 진척 중인 NARRATIVE 뒤에만 주기 대기 최대15초.
- 회귀 테스트 89건 통과. 원문·발언 ID·예산·부분 성공·완료 재사용 검증 포함.
- 배포 전 완료된 157개 쟁점 요약의 해시가 배포 후 모두 동일했다. preserved-before/after.json 참조.
- 최초 운영 두 Nemo 응답은 15.369초/29.718초, reasoning_tokens=0, stop, READY. 다른 입력/공유 게이트웨이 대기 시간을 포함하므로 정확한 모델 성능 배수로 해석하지 않는다. 추가 결과 model-results.json 참조.
- 최종 전체 보고서 완료는 별도 자동 단계이며 after.json은 확인 시점의 진행률이다.
