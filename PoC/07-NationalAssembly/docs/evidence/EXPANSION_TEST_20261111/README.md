# 확장성 테스트 증빙 안내

이 디렉터리는 **사전 구현·검증 및 설정 등록 증빙**이다. 2026-11-11 10:00 예정 문체위 방송의 실제 수집·최종 보고서 완료 결과는 아직 포함하지 않는다.

## 최종 증빙

- `registration-comparison.json`: 최종 등록 전 0건 → 등록 후 1건, 6개 서비스 및 화면·등록 도구 파일 불변 대조 결과.
- `20261110T152321Z-before-registration.json` / `20261110T152323Z-after-registration.json`: 최종 대조 원본. 파일명은 UTC이며 한국 시각은 11월 11일 00:23이다.
- `build-manifest.json`: 서비스별 이미지 ID와 변경 모듈 SHA-256. 각 서비스의 기존 이미지를 기반으로 필요한 모듈만 배포했으며, 수집 임대 보완은 이를 사용하는 자막·음성 워커에 추가 적용했다.
- `preflight-tests.txt`: 131개 테스트·하위 검증 11개 통과. 실제 SQL은 격리 임시 테이블에서 시험했고 모델을 호출하지 않았다.
- `browser-checks.json`: PC·모바일 목록 분리, 테스트 표식, 인쇄/PDF·MD 표식, JavaScript 오류 검증.
- `live-scheduled-1440.png`, `live-scheduled-390.png`: 실제 서비스의 문체위 수집 예정 영역.
- `fixture-separated-1440.png`, `fixture-separated-390.png`: **브라우저 안에서만 생성한 화면 검증용 모의 카드**. 실수집·실제 생성 보고서 증빙으로 사용하지 않는다. 운영 DB에 저장하지 않았다.
- `registration-audit.jsonl`: 최초 준비 과정과 최종 등록을 포함한 설정 변경 이력. 수집 시작 전 마운트·잠금 보완 후 다시 기준을 잡은 내역을 보존한다.

더 이른 `before/after-registration` 파일은 준비 중 진단 이력이다. 최종 성과 판정에는 `registration-comparison.json`이 지정한 파일 쌍을 사용한다.

## 방송 후 보완

```bash
python scripts/collect_assembly_expansion_evidence.py --phase after-broadcast
```

실제 발언 수·첫 수신 시각·오류·보고서 완료 상태·비활성화 후 조회를 확인해 [적용 보고서](../../EXPANSION_TEST_20261111.md)의 결과 작성란에 추가한다. 향후 증빙에도 동일 이미지·코드 해시 여부를 확인한다.
