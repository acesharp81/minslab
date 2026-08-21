# Changelog

## 2026-08-13 · 국정 흐름 워크스페이스 전면 재구성

- 첫 화면을 상시 기록·맥락 복원·공식 근거 연결의 세 가지 사용 원칙 중심으로 재설계
- LIVE·예정·종료 방송과 방송에서 남은 후속 과제를 한 작업 영역에서 바로 비교하도록 재배치
- 방송 확장 화면을 16:9 영상, 주제별 질문·답변, 미해결 과제, 담당 부서, 시간순 전체 자막 구조로 정리
- 종료 방송은 LIVE 저장본과 공식 회의록을 덮어쓰지 않고 처음부터 끝까지 대조하도록 안내 강화
- 생방송이 없을 때 정부·국회 최근 공식 정보를 5초 순환하는 별도 브리핑 영역 유지
- 정부 자료는 주제·담당 부처, 국회 자료는 위원회 회차·정책 신호·의안 표결 중심으로 재명명·재배치
- 밝은 중립 배경, 절제된 인디고 강조색, 16px 기본 본문, 더 큰 행·필터·상세 텍스트를 적용한 실용형 UI 도입
- 데스크톱·태블릿·모바일 반응형과 키보드 focus, reduced-motion 접근성 보정
- 기존 네이비 요약판·사각 표·라운드 카드를 혼용하던 표현을 제거하고, 영상 영역을 제외한 전 화면을 동일한 밝은 surface·인디고 선택 상태·12px 내부 반경으로 통일
- 첫 화면을 `LIVE`·`국무회의`·`국회` 작업 탭으로 분리하고 상단 메뉴·주소 해시·방향키·관심 위원회 선택과 탭 상태를 연동
- 한 줄 제목·대형 탭 카드·LIVE 소개·3단계 안내까지 모두 제거하고 우측 상단 메뉴를 직접 탭으로 사용하며, 실제 방송 감지 시에만 LIVE 메뉴에 붉은 상태 마크 표시

## 2026-08-13 · LIVE 질의응답·과제 보드

- 발언 단위 자막 나열을 주제별 질문·답변·도출 과제·담당 부서 카드로 개편
- 원문 자막은 접을 수 있는 근거 기록으로 유지하고 2초 cursor 갱신 시 카드도 함께 재구성
- 국회 공식 `xhls`의 검증된 HTTPS HLS stream을 native video와 자막 overlay로 동시 표시
- 추론 구조는 `AUTO GROUP · DRAFT`, 데모 구조와 영상 placeholder는 `SIMULATION`으로 구분
- E2E 데모 발언을 3개 주제의 질문·답변 쌍과 명시적 실행 과제로 재구성
- 국무회의 요약 채널과 국회 영상·질의응답 채널을 데스크톱 같은 행에 배치하고 LIVE 중 중복 fallback을 숨기는 컴팩트 레이아웃 적용
- 방송 종료 후에도 최근 세션의 질의응답·과제 보드를 유지하고 다음 LIVE가 시작되면 같은 영역을 실시간 모드로 전환
- 영상 영역을 일반 방송 규격인 16:9로 고정하고 주제 카드의 배지·박스·원형 Q/A 장식을 제거한 정보 중심 목록으로 단순화
- 일반 현황 답변은 과제로 만들지 않고 미해결 확인·검토·조치 약속과 의무 표현만 `OPEN` 후속 과제로 유지
- 같은 주제에서 완료·조치·처리·해소가 확인되면 자동 과제 후보를 제거하고 담당 부서는 열린 과제에만 연결
- LIVE·방송 예정·최근 종료 회의를 한 줄 상태 목록으로 분리하고 LIVE 행 선택 시 전체 폭 영상·분석 패널 확장
- 국무회의·국회 공식 확정 자료 패널은 LIVE 상태와 독립적으로 1:1 배치해 5초마다 계속 순환
- 종료 방송도 LIVE와 동일한 전체 폭 16:9 영상·인사이트·원문 자막 패널로 확장되도록 통합
- 최근 종료 방송 N건 목록과 방송 ID별 저장 기록 조회 API를 연결하고 관심 위원회 필터를 적용

- 종료 방송 목록에 자동 리뷰와 공식본 게시 상태를 표시
- 좁은 확장 패널에서 영상·인사이트를 세로 배치하고 한국어 발언의 글자 단위 줄바꿈과 다중 발언 grid 배치를 수정
- LIVE·종료 리뷰에 주제·미해결 과제 수와 `전체/미해결 과제/담당 부서` 필터를 추가하고 자막 갱신 중 선택 상태 유지
- 최근 30일 LIVE·종료 final 자막의 명시적 OPEN 과제를 통합하는 `/api/live/tasks` 추가
- 방송 목록 아래 담당 부서별 후속 과제 보드를 추가하고 선택 시 해당 방송의 미해결 과제 화면으로 이동
- 종료 방송의 질문·답변과 원문 자막에 문장별 공식본 exact 일치·미확인 배지와 대조된 공식 발언 근거를 추가
- 확장 패널에 LIVE 저장본과 잠정·정본 권위, exact 문장 대조 수, 공식 회의록 원문 링크를 나란히 표시
## 2026-08-13 · LIVE E2E 운영 데모

- 공식 monitor와 분리된 `poc07.demo` source system으로 국회형 방송 세션 생성
- partial/final 자막을 실제 source version·segment revision·event cursor 테이블에 저장
- `/api/live/status`와 snapshot/delta 화면에 `DEMO LIVE · SIMULATION`으로 명시
- 데모 종료 후 기존 review worker가 동일 기록을 PROVISIONAL 매거진으로 변환

## 2026-08-13 · 국무회의-국회 공통 정책 흐름

- 국무회의 공식 안건과 국회 공식 발언을 공통 정책 taxonomy로 대조하는 공개 API 추가
- 법무·사법과 재난·안전의 일반 단어 오연결을 막는 강한 근거 단어 규칙 적용
- 양쪽 OFFICIAL 근거와 기관 간 `PROVISIONAL · DRAFT` 관계를 분리한 국정 연결 카드 추가
- 관심 분야 선택에 따른 위원회 범위 재집계와 연결 의안·표결·공식 원문 이동 제공
- 양쪽 공식 근거의 공통 핵심 단어가 없는 관계와 광범위 단일 단어 관계를 전체·위원회 필터에서 일관되게 제외
- 자료 날짜 순서, 공통 근거 단어, 직접 인과·동일 안건이 아니라는 범위 표시
- 최근 공식 국무회의의 명시 소관 부처 facet, 안건명·공식 내용 검색 API와 화면 필터 추가
- 연결 의안의 공식 PDF 원본·hash·page span 보존과 제안설명/검토 요지 원문 발췌 표시
- FileGate 재생성 PDF의 추출 본문 fingerprint 중복 방지와 기존 중복 canonical 정리

## 2026-08-12 · 공식 국무회의 화면 연결

- 대한민국 정책브리핑 국무회의 목록·상세 HTML contract 검증
- 최신 제35~26회 공식본 10건과 명시 소관 안건 49건 raw-first 수집
- content hash, parser version, source URL, 안건 source span 보존
- 청와대 자료 시각화에 주제·공식 내용·소관 부처·국회 RULE LINK 행 표시
- 생방송 부재 시 최신 제35회 공식본을 국무회의 카드에 대체 표시
- 공식 자료 worker의 1시간 주기 갱신과 공개 API 추가
- 회차·날짜·안건 수 선택 목록과 회의별 안건 전환 UI 추가
- 날짜·회차가 모두 일치하는 청와대 공식 브리핑 6건과 대통령 메시지 35개 연결
- 선택 회의별 OFFICIAL MESSAGE 카드, 원문 링크, source span 표시

중요한 변경사항은 이 문서에 기록합니다.

## [Unreleased]

### Added

- 합성 LIVE 자막의 partial/final revision을 시간순 재생하고 주제·소관을 분류하는 격리 실험
- `PROVISIONAL · SIMULATION` 결과 4건을 사진·주요 발언 매거진으로 5초마다 자동 전환하는 OFF AIR 화면
- 저장된 과거 LIVE 기록을 기관·관심 분야·n개 기준으로 조회하는 `/api/live/magazine`
- 국회 공식 생중계 목록과 KTV 플레이어 계약을 원본 보존하며 검사하는 LIVE source probe
- probe snapshot을 제공하는 `/api/live/status`와 대상 위원회 LIVE 자동 전환 화면
- 30초 주기의 국회 대상 위원회 LIVE monitor와 상세 player·자막 메시지 parser
- 브라우저 비의존형 방송 세션과 자막 segment·revision 영구 저장 schema
- LIVE monitor의 방송 세션 중복 방지 생성과 `LIVE → ENDED` PostgreSQL 생명주기 처리
- 국회 공식 AI 자막 WebSocket을 최대 3개 동시 처리하는 상시 caption worker
- 자막 메시지 raw-first 저장, source version 연결, partial/final content-hash 중복 방지
- PostgreSQL 만료 lease 기반 worker 중복 방지·재접속과 final segment 후퇴 방지
- 중간 입장용 자막 snapshot, 전역 단조 증가 event cursor와 delta API
- 저장 자막을 먼저 표시하고 2초 cursor delta로 현재 자막을 이어 붙이는 국회 LIVE 화면
- 종료 60초 debounce·DB lease·최대 5회 재시도를 갖춘 review worker
- final 자막의 규칙 기반 주제 묶음, 대표 발언 원문과 전체 evidence revision 저장
- 실제 `AUTO REVIEW · PROVISIONAL` 우선 및 기관별 `SIMULATION` fallback 매거진
- 최근 30일 종료 방송의 공식 위원회 회의록 1시간 polling worker
- 위원회+서울 날짜 유일 후보 기반 공식 `CONF_ID`·회의록/PDF 링크 연결
- AUTO REVIEW 카드의 공식 회의록 이동과 `LINK_ONLY · UNRESOLVED` 상태 분리
- 공식 회의록시스템 세션을 거친 `type=view` HTML raw-first 수집
- 발언자·직위·안건과 `spk_sub` 문장 위치를 보존하는 공식 본문 parser
- 임시회의록 `PROVISIONAL`과 정본 `OFFICIAL`을 덮어쓰지 않는 본문 버전 schema
- 20자 이상 단일 exact-normalized 후보만 연결하는 LIVE/공식 문장 reconciliation
- 매거진 원문 링크의 잠정본/정본·추출 문장 수 표시
- LIVE 방송 기록이 없어도 `Meeting`에 공식 본문을 연결하는 migration
- 대상 위원회 최근 회의록 본문의 1시간 주기 자동 수집
- 회의별 공식 발언 페이지 API와 위원회 행의 발언 상세 dialog
- 행안위 164문장·예결위 130문장·법사위 55문장 실제 잠정 회의록 적재
- 공식 원문과 분리된 주제·관련 부처 annotation schema와 원문 hash 근거
- 349개 공식 발언의 결정적 keyword 분류와 `PROVISIONAL · DRAFT` 검토 상태
- 회의별 주제·부처 분포 API와 상세창 chip 필터
- 기관·위원회 명칭 masking과 POLICY/PROCEDURAL/OTHER 분류 v2
- 태그별 일치 keyword, topic link, `RELATED` ministry link 저장·화면 표시
- 절차·기타를 제외한 위원회 행의 핵심 정책 주제·관련 부처 요약
- 실데이터 349문장 재분류와 위원회명 유발 오탐 2건 제거 검증
- 최신 공식 본문 POLICY 57문장의 세 위원회 통합 정책 흐름 API
- 주제별 강도 bar, 위원회 분포, 관련 부처 count와 대표 공식 근거 발언 UI
- 관심 분야 변경 시 위원회 단위 정책 흐름 재집계
- 공식 발언 itemN과 회의 의안 N.의 exact-only provenance 관계 migration
- 법사위 제5안건 발언 50개와 대안 의안 1건의 실제 연결 검증
- 정책 카드의 의안 처리단계·위원회/본회의 결과·찬성/반대/기권 표시
- 방송 시작·종료를 30초마다 반영하고 종료 후 5초 매거진으로 복귀하는 화면 전환
- 실험 재생 결과의 event·segment·분류·source hash 저장과 `--trace` 확인 명령
- 목적 중심 4영역(타이틀·양원 생방송·청와대 자료·위원회 자료) 화면
- 생방송 부재 시 최근 공식 위원회 자료를 대체 표시하는 국회 LIVE 패널
- 관심 분야 선택을 위원회 회의·의안 필터에 연결하는 화면 동작
- POC-07 독립 프로젝트 구조
- FastAPI health/meta API와 데이터 미연결 상태 화면
- PostgreSQL 기반 Docker Compose 개발 구성
- 상태 모델과 프로젝트 문서
- 외부 의존성 없는 상태 모델 단위 테스트
- 신청 대상 공식 API 8개의 source catalog
- endpoint 검증 전 호출을 차단하는 source 상태 모델
- source 필드를 가정하지 않는 XML envelope parser와 합성 fixture 테스트
- 발급 키를 사용한 공식 API 8종 contract 검증
- 일정 API client와 검증 필드 전용 adapter
- SHA-256 기반 raw 원본·manifest 저장
- 일정 수집 CLI와 중복 수집 판정
- 실제 응답의 잘못된 Content-Type을 본문 signature로 보정
- canonical PostgreSQL migration과 idempotent 일정 repository
- SourceDocumentVersion까지 추적 가능한 오늘 일정 API
- 위원회 회의와 일반 국회행사를 구분하는 ScheduleEntry 모델
- 행정안전위원회·예산결산특별위원회·법제사법위원회 대상 scope
- 실제 일정 11건 적재와 재실행 중복 방지 검증
- 공식 일정 목록을 표시하는 초기 화면
- 위원회 회의록과 회의별 의안 adapter 및 합성 fixture
- `CONF_ID` 기반 MeetingExternalId, 회의록 자료, AgendaItem, Bill migration
- 대상 위원회 bundle 수집·정규화 CLI와 공식 회의 목록 API
- 행안위·예결위·법사위 실제 회의 3건, 회의록 자료 9건, 의안 5건 적재 검증
- raw volume 파일 소유권을 보존하는 비-root API 컨테이너
- 의안정보 상세 adapter, BillVersion migration과 대상 의안 동기화 CLI
- 검색어·대상 위원회·처리단계 필터를 제공하는 `/api/bills`
- 실제 의안 5건 상세 적재와 `공포` 1건·`대안반영폐기` 4건 검색 검증
- 회의·회의록·의안 지표와 대상 회의 카드, 의안 필터를 제공하는 실데이터 대시보드
- 오늘 일정을 점·건수로 표시하고 클릭 시 상세 모달을 여는 월간 미니 달력
- 공식 본회의 의원별 표결 284행을 집계한 찬성·반대·기권 그래픽과 위원회별 의안 처리 요약

- 위원회 + 회차 + 날짜 + 자료 건수를 회의별 한 줄로 표시하는 압축 목록
- 의안 제목 + 표결 결과 한 줄과 hover/focus 상세 요약 패널
- 청와대·국무회의 주제·소관 부처와 국회 의안을 연결하는 단계별 실행 플랜
### Planned
- 국무회의 공식 HTML·HWP·PDF source contract와 최근 10건 수집
- 국무회의 발언 segment, 정책 주제, 소관·관련 부처 모델과 필터

- 의원별 표결 상세 검색과 표결 수집 자동화
- Live/Official reconciliation
- 원문 근거 기반 AI enrichment
