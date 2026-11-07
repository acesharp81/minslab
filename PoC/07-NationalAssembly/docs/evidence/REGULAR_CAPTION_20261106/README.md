# 국회 일반 자막 복구 — 2026-11-06

## 확인된 원인

국회 공식 player.asp는 일반 smi/smi-dw/smi-hy 서버에 Socket.IO namespace로 연결하며 AI 자막에만 /hls + echo-protocol을 쓴다. 기존 수집기는 모두 후자로 처리해 일반 자막 수신을 놓쳤다. 실제 공개 /socket.io/?EIO=3&transport=websocket 연결 및 40/10, 42/10 receive message 이벤트 수신을 확인했다. 원본 플레이어/자막 스크립트 보존 파일 참조.

자정 이전 방송도 2026-11-05 15:14 KST에 OFFICIAL_CAPTION_TIMEOUT으로 STT로 전환돼 있었다. 자정 이후 00:01은 새 방송 ID의 전환 시각이며 최초 장애 발생 시각이 아니다. 두 방송 ID는 사용자 지시대로 계속 별도 회의로 보존한다.

## 수정·배포

검증된 일반 호스트만 Socket.IO/EIO3 어댑터로 분기하고 기존 AI 자막은 유지한다. Engine heartbeat, namespace 이벤트 필터, 연결 종료/무응답 처리를 구현했다. 원본 프레임을 먼저 저장한 뒤 파싱한다. 원본에 없는 화자는 생성하지 않는다. 새 xsami는 /hls 없이 저장하며 기존 잘못된 URL도 호환 처리한다.

caption-worker 및 live-monitor를 poc07-regular-caption:20261106으로 교체했다. Mistral 워커는 기존 복구90초/STOP_REQUESTED 처리로 스스로 종료했다. 데이터 삭제, 강제 종료 상태 지정, 모델 추가 호출은 하지 않았다.

## 검증

관련 테스트 27건 및 11 subtests 통과. 기존 AI 자막, 일반 자막 이벤트, 하트비트/연결 종료, 원본 보존, 동일 문구의 별개 발언 보존 검증 포함.

운영 상태는 DEGRADED → RECOVERING → ACTIVE, active_transcript_source=OFFICIAL_CAPTION, stt_fallback_status=IDLE로 전환됐다. 자막 원문 저장은 계속 증가했다. Mistral 로그 executive.audio.completed, retry=false 확인. after.json 및 stt-stop.log 참조.
