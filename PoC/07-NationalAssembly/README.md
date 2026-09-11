# 07 · 국정ON

국회와 국무회의의 **예정 일정 → 생방송 기록 → AI 잠정 정리 → 공식 자료 반영**을 한 화면에서 이어 보는 회의 정보 서비스입니다. 사용자는 회의에서 무엇을 논의했고 어떤 과제가 남았는지를 먼저 확인하고, 필요할 때만 근거 발언과 공식 원문을 펼쳐 볼 수 있습니다.

이 문서는 다음 독자를 위한 통합 안내서입니다.

- **서비스 사용자**: 일정, 생방송, 요약, 도출 과제, 근거 발언과 공식 수정 내용을 확인하는 방법
- **시스템 운영자**: 설치, 설정, 수집 워커, AI 비용, 모니터링, 재처리, 장애 대응과 보안 운영 방법
- **재구축·유지보수 사업자**: 독립 배포 경계, 데이터 모델, 외부 연계 계약, 마이그레이션, 시험·검수와 인수인계 방법

> 현재 단계는 실제 수집 자료를 사용하는 오픈 베타입니다. 데모 회의는 사용자 목록에 노출하지 않습니다. AI 결과는 근거 발언 ID가 있는 잠정 정보이며, 공식 자료가 발표되면 동일 회의 안에서 보완됩니다.

## 문서 사용 방법

| 독자 | 먼저 읽을 곳 | 운영 중 함께 볼 곳 |
|---|---|---|
| 일반 사용자 | [사용자 안내](#사용자-안내) | [상태와 공식 자료의 의미](#상태와-자료-권위-원칙), [알려진 제약](#알려진-제약) |
| 서비스 운영자 | [운영자 빠른 시작](#운영자-빠른-시작) | [일상 운영 런북](#일상-운영-런북), [모니터링과 장애 대응](#모니터링과-장애-대응), [보안과 백업](#보안과-백업) |
| 재구축 사업자 | [시스템 구성](#시스템-구성) | [신규 서버 재구축 절차](#신규-서버-재구축-절차), [환경변수 계약](#환경변수-계약), [배포·업그레이드·롤백](#배포업그레이드롤백) |
| 개발자 | [개발과 테스트](#개발과-테스트) | [데이터 모델과 저장 원칙](#데이터-모델과-저장-원칙), [주요 API](#주요-api), [관련 문서](#관련-문서) |

이 README는 PoC 7 폴더만 전달받아도 서비스 목적과 실행 경계를 파악할 수 있는 기준 문서입니다. 세부 스키마와 설계 결정은 `docs/`에 남기되, 실제 구축·사용에 반드시 필요한 내용은 이 문서에도 요약합니다. 명령은 별도 표시가 없으면 `PoC/07-NationalAssembly` 디렉터리에서 실행합니다.

## 서비스가 답하려는 질문

국정ON은 자막을 길게 읽게 하는 서비스가 아니라 다음 순서로 답을 주는 서비스입니다.

1. 오늘 어떤 회의가 예정되어 있고 지금 무엇이 생방송 중인가?
2. 회의에서 어떤 주제가 논의되었고 어떤 후속 과제가 도출되었는가?
3. 그 판단은 실제 어느 발언과 공식 문서에 근거하는가?
4. 잠정 정리와 공식 발표 사이에 의미 있는 변화가 있었는가?
5. 같은 정책이 정부와 국회에서 언제 반복·증가·제도화되고 있는가?

서비스가 하지 않는 일도 명확합니다.

- AI 결과를 공식 사실로 표시하지 않습니다.
- 이름이 없는 화자 번호를 실제 인물로 추정하지 않습니다.
- 제목이나 일반 단어가 비슷하다는 이유만으로 정부 자료와 국회 자료를 강제 연결하지 않습니다.
- 공식 문서가 아직 없다는 이유로 라이브 원문이나 잠정 결과를 삭제하지 않습니다.
- 화면 조회·새로고침만으로 외부 LLM을 반복 호출하지 않습니다.

## 제공 기능

### 공통

- 국회와 국무회의를 같은 회의 생명주기와 결과 화면으로 처리합니다.
- 오늘의 예정 회의를 상단 전광판에서 5초간 보여 준 뒤 2초 동안 위로 전환합니다. 화살표와 키보드로 직접 이동할 수도 있습니다.
- 회의 목록은 시작 시각 기준 최근 순으로 20건을 먼저 읽고, 끝으로 이동할 때 10건씩 추가합니다.
- 생방송 여부, 기록·정리 상태, 공식 자료 확정 여부, 국회·국무회의 유형을 독립된 태그로 표시합니다.
- 가장 최근에 끝난 회의를 기본 선택하며, 공식 자료가 새로 반영된 과거 회의도 다시 노출합니다.
- PC, 노트북, 태블릿, 휴대전화 폭에 맞춰 재배치됩니다. 작은 화면에서는 근거 발언 영역이 본문 아래로 이동합니다.

### 국회

- 행정안전위원회, 예산결산특별위원회, 법제사법위원회의 공식 일정과 생방송을 집중 감시합니다.
- 국회 공식 생방송 자막을 저장하고, 같은 화자의 연속 자막 조각을 한 발언 묶음으로 합칩니다.
- 화자가 전환되면 완료된 발언 묶음 전체를 한 번 요약해 DB에 저장합니다.
- 실시간으로 파악한 주요 주제와 잠정 과제를 영상 오른쪽에 한 줄씩 누적합니다.
- 방송 종료 후 전체 발언을 다시 분석해 논의 주제, 화자별 요지, 도출 과제와 담당 부처 후보를 구성합니다.
- 공식 회의록이 발표되면 위원회와 서울 기준 일자로 매칭하고 공식 완성형 문장과 화자 정보를 반영합니다.
- 회의별 의안, 처리 결과와 본회의 표결이 명시적 순번으로 연결될 때 함께 표시합니다.

대상 확대는 구동 로직을 복제하지 않고 수집 대상 설정과 업무 분류 규칙을 추가하는 방식으로 처리합니다.

### 국무회의

- KTV 공식 일정과 HLS 생방송을 감지합니다.
- 공개 HLS에 기계 판독 가능한 자막 트랙이 없으면 60초 단위 오디오를 저장하고 Voxtral로 전사합니다.
- 국회와 같은 발언 묶음, 실시간 요약, 종료 후 브리프, 공식 자료 매칭 흐름을 사용합니다.
- 결과의 각 보고 주제는 **부처 보고 내용 → 대통령 지시 → 부처 추가 발표** 순서로 구분하고, 심의안건은 별도 영역에 둡니다.
- 중복 접두어 대신 기관명만 간결하게 표시합니다.
- 부처 보고 내용은 연결된 LIVE 비공식 보고서의 같은 주제 요약을 우선 사용하되 `LIVE 저장본 요약·PROVISIONAL`로 표시합니다. 연결할 수 없으면 공식 결과문에서 확인된 보고 제목과 담당 부처만 표시합니다.
- 대통령 지시는 관련 주제 안에 대상 부처와 함께 별도로 표시하며 부처 보고 내용을 덮어쓰지 않습니다. 두 문구가 과도하게 유사하면 LIVE 요약 재사용을 중단해 같은 문장이 반복되지 않게 합니다.
- 같은 날·동일 부처·동일 주제로 확인된 부처 브리핑은 `부처 추가 발표`로 분리해 제목, 핵심 요약과 원문 링크를 제공합니다.
- 특정 부처보고에 연결되지 않은 대통령 지시는 `그 밖의 대통령 지시`에서 보되 대통령실 브리핑 전체를 별도 결과처럼 반복하지 않습니다.
- 회차와 서울 기준 일자를 우선 사용해 라이브 기록과 공식 자료를 연결합니다.

KTV 화면에 사람이 읽는 자막이 포함될 수는 있지만 현재 공개 플레이어에서는 안정적으로 수집 가능한 별도 텍스트 자막 피드가 확인되지 않았습니다. 국무회의 라이브 자막은 오디오 전사 결과이며 공식 속기록과 동일한 정확도를 보장하지 않습니다.

## 상태와 자료 권위 원칙

화면의 태그와 DB 상태는 다음 세 축을 섞지 않습니다. 운영자와 재구축 사업자는 새 기능을 추가할 때도 이 구분을 유지해야 합니다.

| 축 | 값 | 판정 대상 |
|---|---|---|
| 회의 생명주기 | `SCHEDULED`, `LIVE`, `ENDED`, `CANCELED` | 회의 자체가 예정·진행·종료·취소인지 |
| 자료 권위 | `LIVE`, `PROVISIONAL`, `OFFICIAL` | 자막 원본·AI 잠정 결과·공식 문서 중 무엇인지 |
| 출처 매칭 | `MATCHED`, `UNRESOLVED`, `CONFLICT` | 라이브와 공식 자료가 안전하게 연결됐는지 |

`ENDED + PROVISIONAL + UNRESOLVED`는 오류가 아니라, 회의는 끝났고 잠정 보고서는 있으나 공식 자료가 아직 없거나 연결되지 않았다는 뜻입니다. 공식 자료가 발견돼도 라이브 원본과 잠정본을 덮어쓰지 않고 새 버전과 대조 관계를 저장합니다.

사용자에게 보이는 구조화 항목은 가능한 범위에서 다음 provenance를 유지합니다.

- 출처 종류·외부 ID·공식 URL
- 수집 시각·발행 시각
- 원문 SHA-256 해시와 parser/prompt 버전
- 근거 문서 버전과 원문 위치 또는 발언·revision ID
- 공식값인지, 규칙/AI가 만든 잠정값인지

## 지원 범위와 외부 의존성

| 영역 | 현재 지원 | 외부 의존성 | 장애 시 동작 |
|---|---|---|---|
| 국회 일정 | 전체 공식 일정 수집, 화면은 위원회 달력과 오늘 예정 일정 중심 | 열린국회정보 API | 마지막 저장본 유지 |
| 국회 생방송 | 행안위·예결위·법사위와 본회의 감시, 최대 4개 방송 병렬 자막 수집 | 국회 공식 LIVE 목록·player·WebSocket | 방송별 재연결, 기존 revision 보존 |
| 국회 공식화 | 회의록·안건·의안 연결과 공식 완성형 발언 반영 | 회의록/의안 공식 API와 뷰어 | `NOT_PUBLISHED`·`AMBIGUOUS`로 대기 |
| 국무회의 생방송 | KTV 편성/HLS 감지, 오디오 청크 보존 후 Voxtral 전사 | KTV 공개 HLS, Mistral API, ffmpeg/ffprobe | 청크별 재시도, 실패 청크가 있으면 완료로 오인하지 않음 |
| 국무회의 공식화 | 회차·서울 날짜 기준 부처보고·심의안건·대변인 브리핑 통합 | 정부·정책브리핑 공식 공개 자료 | 라이브 잠정본 유지, 후보가 모호하면 자동 연결하지 않음 |
| AI 요약 | 화자 전환 묶음과 종료 후 회의 브리프 | Mistral 기본, 설정 시 대체 공급자 | 원문/규칙 기반 fallback 유지 |
| 주문형 보고서 | 로컬 자료 검색, 요청 시 OpenRouter 1회 작성 | OpenRouter | 검색·외부도구용 MD 내보내기는 계속 사용 가능 |
| 알림 | 결정론적 문구 감지, in-app, 선택형 Kakao | Kakao는 선택 사항 | Kakao 실패와 관계없이 in-app·근거 저장 유지 |

공식 출처의 상세 endpoint·신청 링크·검증일은 [데이터 출처 문서](docs/DATA_SOURCES.md)를 기준으로 합니다. 외부 API 계약을 추측해서 수정하지 말고 실제 원본 fixture와 adapter contract test를 함께 갱신합니다.

## 사용자 안내

### 1. 상단 정보

- **예정 회의 전광판**: 오늘 예정된 회의 제목, 시각과 장소
- **알람·실시간**: 알람 설정·알림함과 진행 중 방송을 한 화면에서 확인. `생방송 중 / 방송없음`은 현재 공식 방송 유무
- **회의 보고서**: 방송 종료 후 비공식 보고서와 공식자료 통합 결과
- **주제별 보고서**: 저장 자료를 조건 검색해 주문형 정책 보고서 작성
- **인사이트**: 구체 정책 주제의 반복·과제·의결·의안 전환 흐름과 월간 국회 일정
- **AI 사용량**: 플랫폼, 모델, 현재 사용량, 최대 한도와 다음 갱신 시각

예정 회의는 결과 카드에 섞이지 않습니다. 좌우 버튼이나 키보드 방향키로 다른 일정을 볼 수 있습니다. 모션 감소 설정을 사용하는 기기에서는 자동 전환 효과가 줄어듭니다.

### 2. 회의 카드와 태그

각 카드는 태그, 굵은 제목, 일시·장소·상세보기의 세 줄로 구성됩니다.

| 태그 | 의미 |
|---|---|
| 진행중 | 공식 생방송이 현재 진행 중 |
| 완료 | 방송 또는 회의가 종료됨 |
| 기록 중 | 자막이나 오디오를 실시간 저장 중 |
| 정리중 | 종료 후 전체 요약·근거 연결을 생성 중 |
| 비공식 정리 | AI 잠정 결과를 볼 수 있음 |
| 공식정리 | 공식 회의록 또는 브리핑이 반영됨 |
| 국회 / 국무회의 | 회의 출처 |

생명주기와 자료 권위는 별개입니다. 예를 들어 **완료 + 정리중**은 회의는 끝났지만 결과 생성이 진행 중이라는 뜻입니다.

### 3. 생방송 화면

- **알람·실시간** 메뉴에는 진행 중인 방송과 현재 시각 기준 최근 24시간 안에 진행됐거나 종료된 방송만 표시됩니다. 건수 제한은 두지 않으며, 종료 회의는 정리 중에는 저장된 LIVE 초안으로, 정리 완료 후에는 해당 회의 보고서로 이어집니다.
- 비공식 보고서는 근거 추적용 **세부 쟁점**을 빠짐없이 보존한 뒤 이를 정책 **대상 주제**별로 묶어 표시합니다. 두 단계 모두 고정 상한을 두지 않습니다. 요구·비판·찬반은 같은 대상 아래 별도 세부 쟁점으로 남으며 화면에 대상 수, 세부 쟁점 수와 전체 분석 발언 묶음 수를 함께 표시합니다.
- 종료 후에는 실시간 주제명을 유사 표현 단위로 다시 묶고, 각 묶음을 최종 상위 주제에 `근거 직접 연결 / 유사 주제 연결 / 교차 주제 / 미연결` 상태로 저장합니다. 근거·문자열 규칙 뒤에도 남은 항목은 보고서별 OpenRouter 호출 1회로 의미 연결하고, 모델 신뢰도와 고유 정책어 교차가 모두 확인된 연결만 반영합니다. 새 보고서에서 끝까지 연결되지 않은 독립 cluster는 외부 호출 없이 저장된 제목과 근거 ID를 가진 최종 주제로 승격하며, 매핑 버전과 입력 hash로 같은 최신 보고서의 중복 호출을 막습니다.
- 회의 보고서 상단에는 실시간 주제의 전체·연결·교차·미연결 수를 표시합니다. 각 상위 주제의 **실시간 주제 통합 내역**과 **최종 상위 주제에 포함되지 않은 실시간 논의**를 펼치면 해당 발언 원문까지 확인할 수 있습니다.
- 과거 보고서 등에서 미연결 또는 교차 주제가 남아 있으면 포괄 상태를 `PARTIAL`로 기록하며, 새 보고서는 로컬 주제 승격까지 끝난 뒤 `COMPLETE`로 저장합니다.
- 영상은 16:9 비율로 표시됩니다.
- 영상 오른쪽에는 **발언 묶음별 요약 + 원문**이 놓입니다. 현재 발언과 직전 발언을 영상과 같은 높이 안에서 바로 따라볼 수 있습니다.
- 영상 아래 전체 폭의 **실시간 초안 보고서**는 최종 회의 보고서와 같은 `잠정 상태·회의 제목·핵심 주제/도출 과제/근거 발언 지표·주제/과제 2열 표·주요 논의 카드` 순서를 사용합니다. 같은 주제의 새 발언은 별도 주제를 만들지 않고 기존 카드에 반영됩니다.
- 상단 주제나 과제를 누르면 해당 주요 논의 카드로 이동하고, 카드의 발언·과제를 누르면 요약과 원문 근거를 팝업으로 확인합니다.
- 발언 패널은 항상 보이는 세로 스크롤과 **이전 발언 / 최신 고정 중** 조작을 제공합니다. 사용자가 위로 이동하면 최신 고정이 잠시 해제되고 **최신으로**를 누르면 다시 자동 추적합니다.
- 시네마 모드를 켜면 실시간 발언 패널만 숨기고 영상이 넓어집니다. 영상 아래 실시간 초안 보고서는 유지되며 기본 보기로 복귀하면 영상 높이와 최신 발언 위치를 다시 계산합니다.
- 실시간 초안 보고서의 주제·과제 요약표는 한 번에 최대 5개만 보이고 이후 항목은 내부 스크롤로 확인합니다. 키워드 필터는 주제·부처·과제·요약·원문을 함께 검색합니다.
- 영상 오른쪽에는 현재 화자와 바로 전 화자의 발언 묶음을 우선 표시합니다.
- 같은 화자의 새 자막은 현재 묶음 끝에 계속 누적되며 최신 내용으로 자동 이동합니다.
- **원문 전체 보기**를 열어 둔 상태는 새 자막이 들어와도 유지됩니다.
- 진행 중인 발언은 임의로 잘라 요약하지 않습니다. 화자가 바뀐 뒤 완료된 묶음만 요약합니다.
- 방송이 끝났지만 비공식 보고서가 아직 준비되지 않은 회의는 **완료 + 정리중** 카드로 이 메뉴에 남습니다. 클릭하면 저장된 발언 묶음과 LIVE 초안을 다시 볼 수 있습니다.
- 비공식 또는 공식 보고서가 준비되면 같은 종료 카드가 실시간 초안 → 핵심 주제·도출 과제 전환 링크로 바뀝니다. 클릭하면 **회의 보고서** 탭과 해당 회의 결과가 한 번에 열립니다.
- 사용자가 실시간 초안을 열어 둔 사이 보고서가 완료되면 초안을 닫지 않고 상단에 완료 안내와 **회의 보고서 보기** 버튼을 표시합니다. 아래 초안은 계속 조망할 수 있습니다.

원본 자막이 0, 1 같은 채널 번호만 제공하면 실제 인물로 추정하지 않고 **화자 미확인**으로 취급합니다. 운영자가 확인한 이름을 임시 보완할 수 있고, 공식 회의록이 발표되면 공식 화자 기준으로 분리하거나 합칩니다.

### 4. 종료 회의 결과

**회의 보고서** 메뉴의 결과 화면은 원문보다 결론을 먼저 보여 줍니다.

1. 정책 **대상 주제**와 여기에 연결된 **도출 과제**를 먼저 표시합니다.
2. 대상 제목을 누르면 해당 대상의 모든 근거 발언과 **주요 논의 내용**으로 이동합니다.
3. 각 대상 아래에 세부 쟁점과 화자별 주요 내용을 표시합니다.
4. 관련 과제가 있으면 같은 주제 아래에 **과제 + 내용 + 원문보기** 구조로 붙습니다.
5. 대상 주제, 세부 쟁점, 화자 요지 또는 과제를 누르면 근거 발언을 확인할 수 있습니다.

PC에서는 근거 발언 패널이 논의 내용을 스크롤해도 화면 안에 따라옵니다. 이 패널은 요약문을 중복 표시하지 않고 **화자명 + 해당 자막 묶음의 전체 문장**을 보여 줍니다. 핵심은 단어나 문장 전체가 아니라 짧은 핵심 문구로 최대 3곳만 강조합니다.

### 5. 정리 중인 회의

국회 방송은 오전·오후·저녁처럼 한 번 이상 나뉘거나 장시간 정회 뒤 같은 방송 ID로 속개될 수 있습니다. 저장 자막이 30분 이상 끊기면 해당 구간을 `중간 회차`로 체크포인트하고, 다음 자막이 들어오면 새 회차를 자동으로 시작합니다. 회차 수는 고정하지 않으므로 하루 1회·3회·그 이상을 같은 방식으로 처리합니다. 이는 화면과 중간 정리를 위한 잠정 경계이며 공식 종료 판정이 아닙니다.

각 중간 회차의 저장 주제는 실시간 초안에서 계속 확인할 수 있고, 방송 종료 후에는 모든 회차의 발언과 주제를 하나의 비공식 보고서로 통합합니다. 실시간 주제 묶음은 최종 핵심 주제 중 하나에 반드시 귀속되며, 이 계보 보강에는 추가 LLM 호출을 사용하지 않습니다.

비용이 드는 전체 회의 브리프는 `ENDED` 상태가 2시간 연속 유지된 뒤에만 생성합니다. 속개되면 기존 중간 보고서는 완성본으로 표시하지 않고 새 발언 수와 재정리 상태를 보여 줍니다. 이 대기 중에도 실시간 초안과 전체 발언은 계속 확인할 수 있습니다.

방송 직후에는 전체 화면을 막지 않습니다. 요약된 논의 주제와 도출 과제 영역만 흐리게 처리하고 **전체 N개 발언 중 M개 정리 완료**와 같은 진행 현황을 표시합니다. 기본 회의 정보와 저장된 자막은 계속 볼 수 있고, 처리가 끝나면 같은 화면에서 결과가 갱신됩니다.

### 6. 공식 자료와 변경 표시

임시 결과와 공식 결과를 별도 탭으로 중복 제공하지 않습니다. 공식 자료가 들어오면 같은 결과 안에서 의미 있는 변경만 반영합니다.

- 바뀐 문구는 굵기와 색으로 표시합니다.
- 마우스를 올리거나 포커스하면 이전 내용, 변경 내용, 추가 또는 삭제 이유를 확인할 수 있습니다.
- 공백·문장부호는 비교에서 제외하고, 문장이나 절이 이동한 경우에는 삭제와 추가로 두 번 표시하지 않고 이동한 문구끼리 다시 대조합니다.
- 개조식·서술식·독립 문장 순서 변경은 숫자, 부정, 결정·행위, 기관과 행위의 결합 관계까지 같을 때만 문체 변경으로 처리합니다. 담당 기관·수치·결정이나 행위가 달라지면 단어 구성이 비슷해도 실제 변경으로 남깁니다.
- 유사도가 낮은 공식 전체 재작성은 잠정 본문을 통째로 교체하지 않습니다. 잠정 워딩은 유지하고 공식 대안은 전후 비교 카드에서만 확인합니다.
- 공식 완성형 발언이 있으면 파편화된 라이브 자막 대신 공식 문장을 근거 발언에 사용합니다.
- 공식 자료에서 화자가 여러 명으로 확인되면 묶음을 나누고, 같은 화자로 확인되면 합칩니다. 화자 분리·병합 자체는 사용자용 변경 이력으로 표시하지 않습니다.
- 원본 라이브 자막과 공식 원문은 삭제하지 않고 출처가 다른 버전으로 보존합니다.
- 비교 규칙 버전이 올라가도 같은 공식 원문과 기존 검증 변경 목록이 있으면 결정론적으로 다시 계산해 저장합니다. 현재 공식 통합 비교 버전은 1.5이며 이 업그레이드에는 Mistral·OpenRouter를 새로 호출하지 않습니다.
- 공식화 변화 간단 보고서도 입력 해시·모델·프롬프트가 같으면 이전 통합 버전의 저장 결과를 재사용합니다. 새 통합 ID만 생긴 경우 OpenRouter를 반복 호출하지 않습니다.

| 권위 수준 | 뜻 |
|---|---|
| LIVE | 방송 중 수집한 원문 또는 전사 |
| PROVISIONAL | AI 또는 규칙 기반 잠정 정리 |
| OFFICIAL | 공식 회의록·브리핑·안건 원문 |
| RULE LINK | 양쪽 공식 원문에서 주제와 핵심어가 겹친 잠정 연결. 인과관계 확정이 아님 |

### 7. 관심주제 알림과 테스트 방송

상단 **알람·실시간** 메뉴에서 사용자가 직접 주제명, 감지 문구, 국회·정부 범위와 알림 빈도를 등록·수정·삭제할 수 있습니다. 설정·알림함·근거 발언과 방송 화면이 같은 페이지에 유지됩니다.

- 로그인 전에는 무작위 보안 세션으로 설정을 저장하고, Kakao 연결 뒤에는 Kakao 사용자에 연결된 서버 규칙을 계정 원본으로 사용합니다. 다른 PC에서 같은 Kakao 계정을 연결하면 기존 설정·알림·저장 보고서를 그대로 불러옵니다.
- 브라우저 `localStorage`의 규칙은 화면 복구용 캐시일 뿐 계정 원본이 아닙니다. 구형 `X-Watch-Token`은 최초 접속 때 `HttpOnly·Secure·SameSite=Lax` 쿠키로 자동 승격한 뒤 로컬에서 제거합니다.
- 새 PC에서 로그인 전에 만든 규칙은 기존 계정과 동일 문구·기관·위원회 기준으로 중복 없이 병합하며, 다른 기기의 서버 규칙을 자동 삭제하지 않습니다. 새 설정 폼은 기본적으로 접혀 있고 활성 주제만 짧게 표시됩니다.
- 감지 기록은 최신순 12건만 화면에 표시하고 서버에도 사용자별 최근 50건까지만 자동 보존합니다. 개별 기록 삭제와 **읽은 기록 정리**를 제공하며 삭제 시 해당 브라우저 소유의 불필요한 알림·빈 세션·고아 감지 이벤트도 함께 정리합니다.
- 기본값은 **회의당 최초 1회**입니다. 필요하면 화자별 최초 1회, 10·15·30·60분 간격 또는 모든 감지를 선택할 수 있습니다. 국무회의의 화자 코드는 실제 인물 식별자가 아닐 수 있으므로 화자별 정책은 잠정 경계로 이해해야 합니다.
- **회의 종료 시 누적 결과 알림**을 선택하면 관련 발언 묶음·화자 수와 저장된 요약을 사용한 digest를 한 번 제공합니다. 새 LLM 호출은 발생하지 않습니다.
- 규칙은 최대 20개입니다. 테스트 방송은 횟수 제한 대신 운영자 세션 인증을 요구하며 일반 사용자 화면과 API에서는 접근할 수 없습니다. 규칙 수정 시 새 revision과 적용시각을 저장하고 수정 전 자막을 새 조건으로 알림하지 않습니다.
- 알림 감지는 LLM과 무관한 결정론적 matcher가 담당합니다. Unicode, 문장부호, 연속 공백, 한글 띄어쓰기와 짧은 영문 약어 경계를 보정합니다.
- 빠른 알림은 final 자막 revision에서 판단하고, 사용자에게 보이는 근거는 같은 화자의 연속 자막을 한 발언 묶음으로 다시 구성합니다.
- 알림을 누르면 **현재까지 요약 → 화자별 흐름 → 근거 발언 원문** 순서로 봅니다. 기본 누적 요약은 기존 발언 묶음에서 추출하므로 외부 LLM 토큰을 사용하지 않습니다.
- 각 알림 주제의 **지금까지 보고서**는 현재 진행 중인 회의를 우선하고 없으면 가장 최근 감지 회의를 팝업으로 보여 줍니다. 저장본이 있으면 외부 호출 없이 재사용하고, 새 근거가 3개 이상일 때만 비동기 주제 보고서를 예약합니다. Markdown 다운로드와 브라우저 인쇄·PDF를 지원합니다.
- 설정 이전의 과거 자막으로 새 알림을 보내지 않습니다. API 조회나 화면 새로고침도 LLM 호출을 만들지 않습니다.
- 공식 정본 통합 후 관심 발언은 **공식 근거 확인 / 공식본에서 미확인 / 공식 후보 확인 필요**로 구분합니다. 단순 개조식·서술식 차이는 의미 있는 수정으로 과장하지 않습니다.
- Kakao는 사용자가 직접 연결하고 규칙별 **Kakao로도 받기**를 선택한 경우에만 사용합니다. access/refresh token은 Fernet으로 암호화하고 별도 outbox worker가 최대 3회 재시도하므로 Kakao 장애가 감지·근거·in-app 알림을 막지 않습니다.
- 선택형 **지금까지 보고서**는 `WATCH_LLM_ENABLED=true`, `WATCH_LLM_PROVIDER=openrouter`일 때 보고서 클릭으로만 예약합니다. 새 근거 3묶음 이상을 종합 판단과 2~4개 통합 논점의 브리핑으로 구조화하고 근거 ID 집합·provider·model·prompt version으로 저장하므로 같은 자료를 다시 열 때 호출하지 않습니다. 최근 24시간 우선, 세션 최대 12회, UTC 일일 500회 원자 제한을 적용하며 fallback은 항상 남습니다.
- 접힌 **운영 검토·실방송 회귀 점검**은 관리자 인증 후에만 사용합니다. 자동 공식판정은 수정하지 않고 승인·보정·보류 결정을 별도 이력으로 저장하며 cursor·final·2분 이상 수집 공백·공식전환 상태를 회의별로 기록합니다.

화자가 전환되어 발언 묶음이 닫히면 기존 요약 결과의 `live_insight`가 **실시간 초안 보고서**에 주제별로 누적됩니다. 이 화면 갱신 때문에 새 LLM 호출이 생기지 않습니다. 방송 종료 후에는 현재의 전체 회의 분석이 별도로 실행되어 **회의 보고서**의 비공식 결과가 되고, 공식자료 발행 뒤에는 같은 보고서에 의미 있는 변경만 반영됩니다.

**행안위 AI 실전 재현**은 2026년 8월 24일 제438회 제1차 행정안전위원회의 AI 데이터센터 주민 안전 질의답변 중 저장 자막 4145~4180을 사용합니다. 위원의 문제 제기 → 행정안전부 장관 답변 → 위원 재질의로 구성된 7개 발언 묶음과 요약·주제·과제 산출물은 유지하고, 시연 대기시간만 압축해 약 50초 안에 완료합니다. MBC 전체 중계의 해당 구간은 참고 영상이며 자막 재현 시계와 완전 동기화하지 않습니다. 별도 데모 화면이 아니라 실제 국회 LIVE 카드·16:9 영상·실시간 초안 보고서·전체 자막 인터페이스를 사용합니다.

재현이 끝나면 유튜브 iframe을 제거해 영상 재생을 멈추고 영상 자리를 **생방송 없음**으로 전환합니다. 자막에서 만든 임시보고만 종료시각부터 1분간 유지합니다. 같은 관리자 탭에서 새로고침해도 서버 종료시각을 기준으로 남은 시간 동안 종료 화면과 임시보고를 복원하며, 1분이 지나면 테스트 화면을 모두 정리합니다.

- `AI`, `인공지능`, `AI 데이터센터`, `행안부`처럼 이 구간에서 실제 등장하는 문구를 국회 또는 전체 범위 알람으로 먼저 등록합니다.
- 카카오까지 시험하려면 연결된 계정에서 해당 알람의 **카카오로도 받기**를 켜고, 재현 시작 전에 **카카오 나에게 보내기까지 실제 시험**을 명시적으로 선택합니다. 연결·규칙·실제 문구 중 하나라도 맞지 않으면 시작 전에 이유를 안내합니다.
- 체크하지 않은 재현은 in-app 알림만 만듭니다. 체크한 재현만 `poc07.replay.kakao`로 저장되어 기존 outbox와 카카오 나에게 보내기 경로를 통과합니다.
- 재현 데이터는 `poc07.replay.local` 또는 `poc07.replay.kakao` 출처와 사용자 소유권으로 격리됩니다. 공개 LIVE API, 최근 결과, 회의 후처리, 주제별 보고서, 운영 요약 LLM 후보에서는 제외되므로 비용과 공식 결과를 오염시키지 않습니다.
- 같은 알람이 여러 개면 각 규칙의 알림 정책에 따라 카카오 메시지가 둘 이상 갈 수 있습니다. 시험 전 활성 규칙을 확인합니다. 재현 횟수 제한은 없지만 유효한 운영자 세션에서만 시작·조회할 수 있습니다.

### 8. 주제별 보고서

상단 **주제별 보고서**에서 소관 부처, 주제, 기간과 국회·정부 범위를 지정해 현재 저장된 자료로 정책 흐름 보고서를 요청할 수 있습니다. 미리 작성하거나 모든 주제 조합을 배치 생성하지 않습니다.

1. 소관 부처와 주제 중 **하나 이상**만 입력하면 됩니다. 기간과 국회·정부 범위까지 지정한 뒤 **자료 검색**을 누릅니다.
2. 자료 검색은 저장된 회의 브리프와 공식 통합본의 구조화 주제·담당부처·과제를 의미구조와 핵심어로 찾습니다. 외부 LLM 호출은 0회입니다.
3. 검색이 성공하면 **보고서 작성**과 **외부도구 사용**이 활성화됩니다.
4. **보고서 작성**을 누른 경우에만 선별된 공개 근거를 전용 큐에 저장하고 OpenRouter를 1회 호출합니다. Kakao·브라우저 식별정보와 토큰은 보내지 않습니다.
5. **외부도구 사용**은 LLM을 호출하지 않고 검색 근거와 자율적인 보고서 작성 명령을 하나의 Markdown으로 만듭니다. 크기가 허용되면 **프롬프트 복사**, 항상 **MD 파일 다운로드**를 제공하므로 사용자가 ChatGPT·Gemini·Claude 등 원하는 외부 도구에 직접 전달할 수 있습니다.
6. 생성 보고서는 `전체 요약 → 정책적 시사점 → 부처 태그가 붙은 세부 논점 → 후속 과제·근거` 순서로 읽습니다. 각 본문·시사점·과제·연표는 DB에 존재하는 근거 ID가 있어야 저장되며 알 수 없는 근거를 반환하거나 근거 본문이 2개 미만이면 실패 처리합니다.
7. 대표 1번 논점은 모델이 임의로 고정하지 않습니다. 검색 관련성 30점, 공식 근거 20점, 고유 발언 언급량 20점, 정책 영향 15점, 후속조치 10점, 최근성 5점을 합산해 화면에서 정렬합니다. 같은 발언 근거는 한 번만 세며 기존 저장본에 언급량 정보가 없으면 자료 항목당 1건으로 보수 계산합니다.
8. 같은 사용자·검색조건·근거 집합·모델·프롬프트 버전의 완료 결과는 DB에서 재사용하므로 다시 열기, 다운로드, 인쇄로 호출이 늘지 않습니다.
9. PoC7 OpenRouter 전체 500회/일 안에서 주제별 보고서는 최대 100회/일, 사용자별 10회/일로 제한합니다. 검색·캐시 조회와 외부도구용 내보내기는 이 한도를 사용하지 않습니다.
10. 보고서는 화면 열람, Markdown 다운로드와 브라우저 인쇄·PDF를 지원합니다. 작성 전 카카오 계정 연결을 요구해 공개 익명 남용을 막고 다른 PC에서도 저장 결과를 이어 봅니다.

OpenRouter 요청에는 data collection 거부, provider fallback 금지와 strict JSON schema를 강제합니다. 주제별 보고서는 공개 회의 근거만 전송하고 이메일·전화·주민번호 패턴을 먼저 제거합니다. 현재 무료 모델의 유일한 공급자는 OpenRouter ZDR 대상이 아니므로 이 경로에서는 ZDR을 강제하지 않으며, 다른 비공개 데이터는 전송하지 않습니다. 무료 모델의 제공 여부는 바뀔 수 있으므로 TOPIC_REPORT_MODEL은 운영자가 교체할 수 있습니다.

### 9. 인사이트 — 국정 흐름·국회 일정

- 상단 **인사이트**에서 정책 흐름을 먼저 보고, 아래 일정 영역에서 월을 이동하거나 오늘로 돌아올 수 있습니다. 달력과 선택일 세부 일정은 2:1 비율로 나란히 배치하며 달력 표시는 위원회 일정으로 한정합니다. 날짜를 누르면 세부 일정에서 **위원회 일정 → 의원실 일정** 순으로 시각·주최·장소와 공식 출처를 봅니다.
- 달력은 `ScheduleEntry`에 저장된 공식 일정만 최대 42일씩 조회합니다. 아직 수집되지 않은 미래 일정이나 취소 여부를 추정하지 않습니다.
- 인사이트 화면을 열 때 외부 API와 LLM은 호출되지 않습니다. 공식 API 장애 시 기존 저장 일정을 계속 사용합니다.
- 같은 화면의 **정책 흐름 타임라인**은 정부 공식 안건과 국회 회의 보고서의 구체 주제명·핵심 고유어가 함께 일치할 때만 연결합니다. 수사, 예산, 법률 같은 일반 단어 하나만 겹치는 관계는 표시하지 않으며, 일치 항목이 없으면 0건이 정상입니다.
- **지속·급증·소멸 쟁점**은 법무·사법 같은 대분류가 아니라 최신 회의 보고서의 구체 주제명을 사용합니다. 이전 14일이 0회면 최근에 여러 번 나와도 **신규**, 이전 14일 1회 이상·최근 14일 3회 이상이면서 2배 이상 늘어난 경우만 **급증**, 양 기간에 모두 있으면 **지속**, 이전에만 있으면 **최근 미관측**입니다.
- **논의 → 제도화 전환**도 같은 구체 주제를 기준으로 **후속 과제 도출**, **보고서상 법안·제도개편**, **보고서상 의결·시행**, **공식 의안 직접 연결**을 구분합니다. 항목을 선택하면 `논의된 회의 → 상정 의안 → 처리 절차 → 현재 상태`가 순서대로 열립니다. 앞의 세 단계는 발의 확인이 아니며, 공식 발언 근거 ID와 회의별 의안 ID가 연결되고 주제명·의안명 고유어가 다시 일치한 경우에만 의안번호·발의자·위원회/본회의 결과·공식 링크를 제공합니다.
- 세 지표 모두 저장 자료의 결정론적 읽기 모델이므로 화면을 열거나 다시 조회할 때 LLM 호출은 0회입니다. 주제 유사 묶음과 단계 판정은 원인·영향·가결 가능성을 추정하지 않습니다.
- 정책 흐름 타임라인 항목을 선택하면 같은 팝업 안에서 국무회의 공식 안건 요약과 국회 회의 보고서 요약을 좌우로 비교합니다. 지속·급증·소멸 쟁점은 선택한 주제 요약을, 논의→제도화는 회의별 논의 이력과 공식 의안 처리 타임라인을 보여줍니다. 모바일에서는 비교·절차 카드가 위아래로 배치되며 팝업 열람은 LLM을 호출하지 않습니다.

### 10. 공식화 변화 간단 보고

- 공식 회의록이 연결되면 기존 회의 보고서 위에 **공식화 변화 간단 보고**가 나타납니다. 비공식 결과와 공식 결과를 따로 복제하지 않고, 달라진 사실·담당기관·결정·과제만 묶어서 전후 문구와 함께 보여줍니다.
- 본문 비교는 공백과 문장부호를 정렬 기준에서 제외한 문자 단위 대조를 사용합니다. 동일 부분은 비공식 워딩을 그대로 유지하고 공식 근거가 바꾼 최소 구간만 반영합니다. 유사도가 낮아 문장 전체 교체가 필요한 후보는 본문을 덮어쓰지 않고 비교 카드에 공식 표현을 따로 제시합니다.
- OpenRouter는 서버가 이미 검증한 변경 ID를 최대 6개 설명 묶음으로 정리할 뿐 변경 여부를 새로 판단하지 않습니다. 의미 있는 변경이 0건이면 LLM을 호출하지 않습니다.
- 생성 결과는 공식 통합본·입력 해시·모델·프롬프트 버전으로 DB에 저장해 다시 열거나 인쇄할 때 재호출하지 않습니다. 전용 최대 100회/일과 PoC7 공용 OpenRouter 최대 500회/일을 함께 적용합니다.

## 전체 처리 흐름

~~~text
공식 일정 수집
  → 생방송 감지
  → 자막/오디오 원본 보존
  → 같은 화자의 연속 자막을 발언 묶음으로 누적
  → 화자 전환 시 묶음 요약·주제·잠정 과제 저장
  → 방송 종료 후 전체 회의 브리프 생성
  → 공식 회의록/브리핑 탐색 및 안전한 매칭
  → 공식 완성형 문장·화자·안건 반영
  → 의미 있는 변경만 사용자 화면에 표시
~~~

외부 AI는 API 조회 때마다 호출되지 않습니다. 워커가 결과를 한 번 생성해 DB에 저장하며 같은 방송, 같은 본문 해시, 같은 프롬프트 버전은 캐시를 재사용합니다.

## 시스템 구성

~~~text
사용자 브라우저
  └─ 정적 HTML/CSS/JavaScript
       └─ FastAPI REST API (외부 AI 직접 호출 없음)
            ├─ PostgreSQL ─ canonical data, revision, cache, quota, account
            └─ data/
                 ├─ raw/       원본 응답·자막 메시지·오디오·manifest
                 └─ processed/ 정규화된 파일 스냅샷·상태 산출물

공식 국회/KTV/정부 출처
  └─ 수집 worker ─ 원본 선저장 → adapter → normalizer → PostgreSQL
       ├─ 실시간 worker ─ 방송 감지 → 자막/오디오 → 발언 묶음
       ├─ AI worker ─ 저장된 발언 요약 → 전체 브리프 → DB cache
       ├─ 공식화 worker ─ 회의록/브리핑 수집 → 안전한 대조
       └─ 알림/보고서 worker ─ 결정론 감지, 선택형 외부 전송·작성
~~~

### 구성 원칙

- **단일 제품 경로**: 국회와 국무회의는 `일정 → LIVE → 발언 묶음 → 잠정 브리프 → 공식 통합`을 공유합니다. 기관별 차이는 source adapter, taxonomy, 공식 문서 parser에만 둡니다.
- **API와 작업 분리**: FastAPI는 저장된 결과만 읽습니다. 느리거나 비용이 드는 수집·AI·Kakao 전송은 별도 worker가 처리합니다.
- **PostgreSQL 단일 원장**: 브라우저 상태나 JSON 파일을 회의·알림·보고서의 권위 원장으로 사용하지 않습니다.
- **원본 우선**: 모든 구조화 전에 원문과 수집 metadata를 저장합니다. parser 실패도 원본을 잃지 않습니다.
- **멱등성과 버전**: `content_hash`, 외부 ID, prompt/parser version과 근거 집합 hash로 중복 호출·중복 row를 막습니다.
- **독립 배포**: PoC 7은 부모 저장소와 PoC 4·6의 Python 모듈, `.env`, DB, 토큰 저장소를 runtime dependency로 사용하지 않습니다. 부모 홈페이지와는 HTTP reverse proxy 계약으로만 연결합니다.
- **과설계 제한**: 현재 규모에서는 PostgreSQL, 단일 API 이미지와 역할별 worker로 운영합니다. Kafka·Airflow·Kubernetes·별도 vector DB는 측정된 병목과 승인 없이 도입하지 않습니다.

### 주요 기술 스택

| 계층 | 구현 |
|---|---|
| 사용자 화면 | 서버가 제공하는 정적 HTML/CSS/vanilla JavaScript, 반응형·dialog·키보드 조작 |
| API | Python 3.12, FastAPI, Pydantic, Uvicorn |
| DB | PostgreSQL 16, 순차 SQL migration, psycopg 3 |
| 수집 | requests, websockets, BeautifulSoup, 국회·KTV·정부 source adapter |
| 오디오 | ffmpeg/ffprobe, 60초 기본 청크, Voxtral diarization 전사 |
| AI | Mistral 요약·전사, 선택형 OpenRouter 주문 보고서/변화 보고 |
| 인증·보안 | PoC7 세션 쿠키, Kakao OAuth 선택 연계, Fernet 토큰 암호화, Origin/보안 헤더 검사 |
| 실행 | Docker Engine, Docker Compose 또는 제공된 allowlist 배포 스크립트 |

## 데이터 모델과 저장 원칙

핵심 관계는 다음과 같습니다. 전체 컬럼·인덱스·상태 전이는 [데이터 모델 문서](docs/DATA_MODEL.md)와 `backend/migrations/`가 기준입니다.

~~~text
SourceDocument 1 ─ N SourceDocumentVersion
ScheduleEntry N ─ 0..1 Meeting ─ N AgendaItem/Bill/OfficialTranscript
LiveBroadcast 1 ─ N TranscriptSegment 1 ─ N TranscriptSegmentRevision
LiveBroadcast 1 ─ N TranscriptUtteranceSummary / MeetingBrief
MeetingBrief + OfficialTranscriptDocument ─ MeetingOfficialIntegration
WatchSubscriber ─ WatchRule ─ Detection/Match/Notification/Report
TopicReport ─ selected evidence snapshot + generated report cache + quota ledger
~~~

| 저장 위치 | 포함 내용 | 백업 필요 | Git 포함 |
|---|---|---:|---:|
| PostgreSQL named volume | canonical 회의, revision, 요약 cache, 상태, 계정·알림·사용량 | 필수 | 아니오 |
| `data/raw/` | 원본 API 응답, manifest, LIVE 원본, 국무회의 오디오 | 필수 | 아니오 (`.gitkeep`만 포함) |
| `data/processed/` | 일정·방송 상태 등 재생성 가능한 읽기 스냅샷 | 권장 | 아니오 (`.gitkeep`만 포함) |
| `web/` | 공개 정적 화면 | 코드와 함께 | 예 |
| `backend/migrations/` | 순차 DB schema 변경 | 코드와 함께 | 예 |

원본·DB를 함께 백업해야 발언 근거와 공식 변경 추적을 완전히 복구할 수 있습니다. `data/processed/`만 복사하거나 DB만 복원하면 provenance 일부가 사라질 수 있습니다.

## 운영자 빠른 시작

### 요구 사항

- Docker Engine과 Docker Compose 플러그인
- 공식 데이터 수집을 위한 네트워크 연결
- 국회 API를 사용할 경우 NATIONAL_ASSEMBLY_API_KEY
- AI 요약을 사용할 경우 MISTRAL_API_KEY
- 선택적 대체 경로를 사용할 경우 OPENROUTER_API_KEY
- 국무회의 오디오 전사를 사용할 경우 Mistral/Voxtral 사용 권한

### 환경 설정

~~~bash
cd PoC/07-NationalAssembly
cp .env.example .env
~~~

.env에서 DB 비밀번호와 필요한 API 키를 설정합니다. 전체 변수와 기본값은 [.env.example](.env.example)을 기준으로 합니다.

~~~dotenv
AI_ENRICHMENT_ENABLED=1
LLM_PROVIDER=mistral
LLM_MODEL=mistral-small-2603
MISTRAL_MONTHLY_CREDIT_USD=10
EXECUTIVE_TRANSCRIPTION_MODEL=voxtral-mini-latest
EXECUTIVE_AUDIO_CHUNK_SECONDS=60
OPENROUTER_DAILY_LIMIT=500
TOPIC_REPORTS_ENABLED=true
TOPIC_REPORT_MODEL=dots-studio/dots-3-note-preview:free
TOPIC_REPORT_DAILY_LIMIT=100
TOPIC_REPORT_USER_DAILY_LIMIT=10
OFFICIAL_CHANGE_REPORTS_ENABLED=true
OFFICIAL_CHANGE_REPORT_DAILY_LIMIT=100
~~~

- Mistral 한도는 호출 횟수가 아니라 실제 입력·출력 토큰과 오디오 분을 USD로 환산해 월 10 USD 내에서 관리합니다.
- OPENROUTER_DAILY_LIMIT=500은 OpenRouter를 사용할 때만 적용되며 Mistral 호출에는 적용하지 않습니다.
- 공급자 가격이 바뀌면 .env.example의 입력·출력 백만 토큰당 비용과 오디오 분당 비용을 운영자가 갱신해야 합니다.
- AI를 끄려면 AI_ENRICHMENT_ENABLED=0으로 설정합니다. 원본 수집과 공식 자료 기능은 계속 동작하지만 AI 요약은 생성되지 않습니다.

### 환경변수 계약

실제 값은 `.env`에 두고 커밋하지 않습니다. 변수 이름·기본값·용도는 [.env.example](.env.example)이 배포 계약이며, 아래 표는 운영자가 필수 여부를 빠르게 판단하기 위한 요약입니다.

| 범주 | 주요 변수 | 필수 시점 | 설명 |
|---|---|---|---|
| 앱 | `NATIONAL_ASSEMBLY_ENV`, `NATIONAL_ASSEMBLY_PORT`, `NATIONAL_ASSEMBLY_TIMEZONE`, `NATIONAL_ASSEMBLY_LOG_LEVEL` | 항상 | 실행 환경·포트·서울 시간대·로그 수준 |
| DB | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL` | 항상 | 운영에서는 예시 비밀번호를 반드시 교체하고 URL과 일치시킴 |
| 파일 | `RAW_DATA_DIR`, `PROCESSED_DATA_DIR` | 항상 | 컨테이너 기본값은 `/app/data/raw`, `/app/data/processed` |
| 국회 공식 API | `NATIONAL_ASSEMBLY_API_KEY` | 일정·회의록·의안 수집 시 | API 컨테이너가 아니라 해당 수집 worker에만 주입 |
| 공통 AI | `AI_ENRICHMENT_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL` | 발언·회의 요약 사용 시 | `AI_ENRICHMENT_ENABLED=0`이면 원본 수집은 유지하고 생성 요약을 중지 |
| Mistral | `MISTRAL_API_KEY`, `MISTRAL_BASE_URL`, `MISTRAL_MONTHLY_CREDIT_USD`, `MISTRAL_*_USD_PER_MILLION` | Mistral 요약·전사 시 | 성공 응답의 실제 토큰과 오디오 분을 월 USD 장부에 합산 |
| 국무회의 전사 | `EXECUTIVE_TRANSCRIPTION_MODEL`, `EXECUTIVE_AUDIO_CHUNK_SECONDS`, `EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE` | KTV 오디오 전사 시 | 기본 60초 청크. 변경 전 누락·중복·비용 회귀시험 필요 |
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_DAILY_LIMIT` | 선택형 보고서 사용 시 | UTC 일자 공용 최대 500회. 외부 요청 시도 전 원자 예약 |
| 알림 | `WATCH_ALERTS_ENABLED`, `WATCH_TEST_BROADCASTS_ENABLED`, `WATCH_DIGEST_ENABLED` | 알람·실시간 기능 | 감지와 digest는 결정론적이며 기본 LLM 0회 |
| 알림 AI | `WATCH_LLM_ENABLED`, `WATCH_LLM_PROVIDER`, `WATCH_LLM_MODEL`, `WATCH_LLM_*` | 선택형 지금까지 보고서 | 기본 OFF, 최소 새 근거·debounce·세션/월 한도 적용 |
| Kakao | `WATCH_KAKAO_ENABLED`, `WATCH_KAKAO_REST_API_KEY`, `WATCH_KAKAO_CLIENT_SECRET`, `WATCH_KAKAO_TOKEN_ENCRYPTION_KEY`, `WATCH_KAKAO_REDIRECT_URI`, `WATCH_PUBLIC_BASE_URL` | Kakao 연결·발송 시 | PoC 7 전용 앱·암호화 키. 다른 PoC 값에 runtime 의존하지 않음 |
| 사용자 세션 | `WATCH_SESSION_COOKIE_NAME`, `WATCH_SESSION_COOKIE_PATH` | 다중 기기 계정 사용 시 | 공개 reverse proxy 경로와 cookie path가 일치해야 함 |
| 운영자 | `WATCH_ADMIN_TOKEN` | 운영 검토 API 사용 시 | 별도 무작위 값 사용, 브라우저 영구저장 금지 |
| 주제별 보고서 | `TOPIC_REPORTS_ENABLED`, `TOPIC_REPORT_MODEL`, `TOPIC_REPORT_DAILY_LIMIT`, `TOPIC_REPORT_USER_DAILY_LIMIT`, `TOPIC_REPORT_MAX_PERIOD_DAYS` | 주문형 작성 시 | 자료 검색은 무과금, 작성 worker만 OpenRouter 사용 |
| 공식화 변화 | `OFFICIAL_CHANGE_REPORTS_ENABLED`, `OFFICIAL_CHANGE_REPORT_MODEL`, `OFFICIAL_CHANGE_REPORT_DAILY_LIMIT` | 공식 통합 변화 요약 시 | 검증된 변경이 있을 때만 topic-report worker가 처리 |

주의할 점:

- `.env`의 따옴표·공백·URL 인코딩을 임의로 바꾸지 않습니다. 특히 DB 비밀번호에 예약문자가 있으면 `DATABASE_URL`에서 percent-encoding이 필요합니다.
- `.env.example`의 비용 숫자는 내부 차단 계산용 설정값이지 공급자 가격을 자동 조회한 값이 아닙니다. 공급자 콘솔의 현재 가격·무료 크레딧·월 지출 제한과 정기적으로 대조합니다.
- `OPENROUTER_DAILY_LIMIT=500`은 Mistral에 적용되지 않습니다. Mistral은 `MISTRAL_MONTHLY_CREDIT_USD` 기준입니다.
- Compose와 보안 배포 스크립트는 서비스별 허용목록만 주입합니다. 새 비밀변수를 추가하면 `.env.example`, `config.py`, Compose 또는 배포 스크립트 허용목록, 보안 문서를 한 변경으로 갱신합니다.

### 신규 서버 재구축 절차

다음 순서면 PoC 7 폴더만으로 새 Linux 서버에 독립 재구축할 수 있습니다.

#### 1. 준비와 반입

- 64비트 Linux, Docker Engine, Docker Compose 플러그인, Git과 curl을 준비합니다.
- 외부 송신 방화벽에서 검증된 국회·KTV·정부 출처와 선택한 AI/Kakao endpoint만 허용합니다.
- 소스 코드, 운영 `.env`, PostgreSQL dump, `data/raw/`와 `data/processed/` 백업을 서로 분리해 안전하게 반입합니다.
- 코드만 새로 시작하는 경우 `.env.example`을 복사해 새 비밀값을 만들고 기존 운영 데이터 복원 단계는 건너뜁니다.
- 디스크 용량은 회의 수보다 국무회의 오디오 원본 보존 정책의 영향을 크게 받습니다. 운영 전 실제 1주 수집량으로 월 증가량과 보존기간을 산정합니다.

#### 2. 환경과 네트워크

~~~bash
cd PoC/07-NationalAssembly
cp .env.example .env
chmod 600 .env
docker network inspect poc07-national-assembly
docker network create poc07-national-assembly
~~~

네트워크가 이미 있으면 마지막 생성 명령은 실행하지 않습니다. `.env`에서 DB 비밀번호, API 키, 공개 callback URL과 기능 플래그를 설정한 뒤 실제 값을 화면·로그·티켓에 출력하지 않고 설정 여부만 점검합니다.

#### 3. 이미지·DB·전체 서비스 기동

~~~bash
docker compose build
docker compose up -d db
docker compose ps
docker compose up -d
~~~

API 이미지의 시작 명령이 `backend/migrations/`를 파일명 순으로 한 번씩 적용합니다. 운영 DB를 복구한다면 **복구 후 현재 이미지의 migration을 적용**하며, 이전 migration 파일을 수정하거나 적용 이력을 삭제하지 않습니다.

#### 4. 공개 프록시 연결

- Compose는 기본적으로 호스트의 `NATIONAL_ASSEMBLY_PORT=8070`을 publish하므로 로컬에서는 `127.0.0.1:8070`으로 접속합니다. 제공된 운영 배포 스크립트는 명시적으로 `127.0.0.1:18070`에만 바인딩합니다.
- 외부에는 이 포트를 직접 공개하지 말고 `/poc/national-assembly/` reverse proxy를 사용합니다.
- prefix 제거, PoC7 cookie만 전달, `Set-Cookie`, `Origin`, `Referer`, `Content-Disposition`, `X-LLM-Calls` 전달 규칙은 [공개 프록시 계약](docs/PUBLIC_PROXY_CONTRACT.md)을 그대로 적용합니다.
- Kakao callback 공개 URI와 `WATCH_KAKAO_REDIRECT_URI`가 한 글자까지 같아야 합니다.

#### 5. 인수 시험

~~~bash
curl -fsS http://127.0.0.1:8070/api/health
curl -fsS http://127.0.0.1:8070/api/meta
curl -fsS http://127.0.0.1:8070/api/data-sources
curl -fsS http://127.0.0.1:8070/ >/dev/null
curl -fsS http://127.0.0.1:8070/assets/app.js >/dev/null
~~~

이후 일정 1회 수집, 테스트 방송, 알림 1건, 보고서 화면, 모바일 폭, 공식자료 대기/통합 상태를 순서대로 확인합니다. Kakao·Mistral·OpenRouter는 해당 기능을 운영하기로 승인한 경우에만 실제 외부 호출까지 시험합니다.

### 실행

Compose 네트워크가 없으면 한 번만 생성합니다.

~~~bash
docker network inspect poc07-national-assembly
docker network create poc07-national-assembly
~~~

첫 명령이 성공하면 두 번째 명령은 실행하지 않습니다.

~~~bash
docker compose up --build -d
~~~

이미지는 시작할 때 DB migration을 자동 적용합니다. 소스가 교체된 배포에서는 API 컨테이너를 재생성합니다.

~~~bash
docker compose up --build -d --force-recreate api
~~~

### 기동 확인

~~~bash
docker compose ps
curl -fsS http://127.0.0.1:8070/api/health
curl -fsS http://127.0.0.1:8070/api/meta
~~~

- 독립 실행: http://127.0.0.1:8070/
- OpenAPI: http://127.0.0.1:8070/docs
- 통합 홈페이지: /poc/national-assembly/

통합 홈페이지는 부모 서비스의 NATIONAL_ASSEMBLY_UPSTREAM을 통해 이 앱으로 프록시합니다. 배포 환경에서 독립 서비스가 127.0.0.1:18070을 사용하도록 구성할 수 있지만 이 Compose의 기본 포트는 8070입니다.

### 로그와 종료

~~~bash
docker compose logs --tail=200 api
docker compose logs --tail=200 live-monitor caption-worker summary-worker
docker compose down
~~~

docker compose down은 기본적으로 DB 볼륨을 삭제하지 않습니다. 운영 데이터가 있는 환경에서는 down -v를 사용하지 마십시오.

## Compose 서비스

| 서비스 | 기본 주기/병렬도 | 역할 |
|---|---:|---|
| api | 상시 | 화면, 조회 API, 저장된 근거·브리프 제공 |
| db | 상시 | PostgreSQL 영속 저장소 |
| live-monitor | 30초 | 국회와 KTV 공식 생방송 감지 |
| schedule-worker | 국회 10분·KTV 6시간, 7일 범위 | 국회 위원회와 KTV 국무회의 공식 예정 일정 동기화 |
| caption-worker | 3 workers | 국회 공식 자막 WebSocket 수집·정규화 |
| executive-caption-worker | 5초 | KTV HLS 오디오 수집과 Voxtral 전사 |
| summary-worker | 2초 | 완료된 화자 발언 묶음의 요약·주제·과제 생성 |
| review-worker | 10초 | 종료 방송의 규칙 기반 잠정 리뷰 생성·복구 |
| watch-worker | 1초 | 관심문구 감지·중복 방지·in-app 알림과 격리 테스트 자막 송출 |
| notification-worker | 2초 | 선택된 Kakao outbox claim·토큰 갱신·최대 3회 독립 재시도 |
| watch-summary-worker | 10초 | 선택형 관심주제 통합 요약·evidence hash cache·월 USD 1 soft cap |
| topic-report-worker | 2초 | 주문형 주제별 보고서와 검증된 공식화 변화 간단 보고 처리 |
| meeting-brief-worker | 60초 | 전체 발언 기반 회의 주제·과제 브리프 생성 |
| official-minutes-worker | 1시간 | 국회 공식 회의록 수집과 라이브 결과 재조정 |

모든 워커는 같은 PostgreSQL을 사용합니다. 화면 API는 외부 AI를 직접 호출하지 않으므로 사용자가 새로고침해도 토큰이 반복 소비되지 않습니다.

Compose는 이름이 `poc07-national-assembly`인 외부 Docker network를 사용합니다. API만 호스트 포트 `NATIONAL_ASSEMBLY_PORT`에 publish하며 DB와 worker 포트는 외부에 공개하지 않습니다. Compose의 `ports` 기본값은 모든 host interface에 열릴 수 있으므로 운영 방화벽 또는 compose override로 loopback 접근만 허용해야 합니다. `./data`는 bind mount이고 PostgreSQL은 논리 이름 `national_assembly_pgdata`인 named volume을 사용합니다. API 컨테이너가 시작될 때만 migration을 자동 적용하므로 새 migration을 배포할 때 API health가 정상인지 먼저 확인합니다.

### 기능별 운영 프로필

| 프로필 | 권장 설정 | 이용 가능한 기능 |
|---|---|---|
| 무과금·원본 우선 | `AI_ENRICHMENT_ENABLED=0`, `WATCH_LLM_ENABLED=false`, `WATCH_KAKAO_ENABLED=false` | 일정·LIVE 원본·규칙 리뷰·공식자료·로컬 알림·자료 검색·외부도구 MD |
| 기본 오픈 베타 | Mistral 월 USD 한도 설정, OpenRouter/Kakao 선택 OFF | 발언 묶음 요약·회의 브리프·국무회의 음성 전사 포함 |
| 선택 기능 활성 | OpenRouter·Kakao 키와 각 feature flag를 개별 ON | 지금까지 보고서, 주제별 보고서, 공식화 변화 보고, Kakao 발송 |

무료 운영을 우선할 때 기능 전체를 끄지 않고, 외부 호출 부분만 feature flag로 중지하는 것이 원칙입니다. 원본 수집·공식자료 연결·결정론적 인사이트·자료 검색은 계속 운영할 수 있습니다.

## 수동 실행과 재처리

아래 명령은 프로젝트 디렉터리에서 실행합니다. Compose가 정상이라면 일상 운영에 수동 실행은 필요하지 않습니다.

### 일정과 공식 데이터

~~~bash
python3 scripts/fetch_schedule.py --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.schedule_file
PYTHONPATH=backend python3 -m app.ingestion.committee_sync --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.bill_sync --assembly-term 제22대
~~~

### 워커 1회 점검

~~~bash
PYTHONPATH=backend python3 -m app.ingestion.live_monitor --once
PYTHONPATH=backend python3 -m app.ingestion.schedule_worker --once
PYTHONPATH=backend python3 -m app.ingestion.review_worker --once
PYTHONPATH=backend python3 -m app.ingestion.executive_caption_worker --once
PYTHONPATH=backend python3 -m app.ingestion.summary_worker --once
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker --once
PYTHONPATH=backend python3 -m app.ingestion.official_minutes_worker --once
PYTHONPATH=backend python3 -m app.ingestion.watch_worker --once
PYTHONPATH=backend python3 -m app.ingestion.notification_worker --once
PYTHONPATH=backend python3 -m app.ingestion.watch_summary_worker --once
PYTHONPATH=backend python3 -m app.ingestion.topic_report_worker --once
PYTHONPATH=backend python3 -m app.ingestion.live_regression_audit --limit 20
~~~

Docker Compose 플러그인이 없는 현재 운영 호스트에서는 허용목록 기반 배포 스크립트를 사용합니다.

~~~bash
sudo scripts/deploy_api.sh
sudo scripts/deploy_secure_workers.sh watch
sudo scripts/deploy_secure_workers.sh notification
sudo scripts/deploy_secure_workers.sh watch-summary
sudo scripts/deploy_secure_workers.sh topic-report
sudo scripts/deploy_secure_workers.sh review
~~~

API에는 Mistral·국회 API 키를 주입하지 않습니다. Kakao OAuth에 필요한 키·client secret·토큰 암호화 키와 운영자 인증값만 allowlist로 제한해 API에 주입하며, 실제 발송은 별도 notification-worker가 담당합니다. watch-worker에는 DB와 기능 플래그만 전달합니다.

### 공식 자료 재조정

~~~bash
PYTHONPATH=backend python3 -m app.ingestion.official_integration_worker
PYTHONPATH=backend python3 -m app.ingestion.revalidate_official_integration --help
~~~

official_integration_worker는 지정된 대기 건을 한 번 처리하고 종료합니다. 특정 방송만 강제 재처리해야 할 때는 --help에서 broadcast-id와 force 옵션을 확인한 뒤 실행합니다.

운영 원칙은 삭제 후 재생성이 아니라 저장된 원본과 버전을 유지한 채 새 통합 결과를 추가하는 것입니다.

## 일상 운영 런북

### 방송 전

1. `docker compose ps`와 `/api/health`를 확인합니다.
2. `/api/schedule/upcoming`과 공식 사이트를 대조해 오늘·내일 대상 회의가 들어왔는지 확인합니다.
3. `live-monitor`, `caption-worker`, 국무회의가 예정되면 `executive-caption-worker`가 실행 중인지 확인합니다.
4. `/api/ai/usage`에서 월 Mistral 비용과 일 OpenRouter 호출량을 확인합니다.
5. 실제 방송이 없는 날에는 사용자 소유의 **테스트 방송 송출**로 알림·실시간 화면만 검증합니다. 테스트 데이터는 공개 회의 목록과 분리됩니다.

### 방송 중

1. 대상 방송마다 `capture_status=CAPTURING`이고 최신 final revision 시각이 함께 증가하는지 봅니다.
2. 동시 방송은 `caption-worker --workers 4`의 서로 다른 lease owner가 각각 처리해야 합니다. 한 방송의 segment가 다른 `broadcast_id`에 섞이지 않는지 snapshot/delta를 표본 확인합니다.
3. 같은 화자의 발언은 한 묶음에 계속 누적되고 실제 전환 뒤에만 요약되는지 확인합니다.
4. 화면에서 최신 발언 자동 추적, 수동 스크롤 유지, 시네마 모드 복귀와 실시간 초안 주제 통합을 확인합니다.
5. 원문 전체나 API key를 로그에 출력하지 않습니다. 로그에는 방송 ID, cursor, 건수와 상태만 남깁니다.

### 방송 종료 후

1. 국회는 마지막 final 자막 저장을, 국무회의는 마지막 오디오 청크가 전사될 때까지 `POST_PROCESSING` 상태를 정상 처리 구간으로 봅니다.
2. 오전·오후·저녁 또는 정회 구간이 있으면 30분 공백 checkpoint가 생성되고 최종적으로 한 회의 브리프로 합쳐지는지 확인합니다.
3. `ENDED`가 2시간 안정적으로 유지된 뒤 meeting brief가 생성되는지 `/api/live/overview`에서 전체/완료 발언 수로 확인합니다.
4. 비공식 보고서의 모든 주제·과제·화자 요지에 현재 방송의 evidence ID가 있는지 표본 검수합니다.
5. 실시간 주제 계보의 미연결·교차 항목은 보고서별 OpenRouter 의미 연결이 한 번 실행됐는지 확인하고, 이후에도 남은 저신뢰 항목은 처리 완료와 포괄 완료를 구분해 검토합니다.

### 공식 자료 발표 후

1. 국회는 위원회+서울 날짜, 국무회의는 회차+서울 날짜 후보가 유일한지 확인합니다.
2. 공식 완성형 발언과 화자 분리·병합, 주제별 과제 매핑이 반영됐는지 확인합니다.
3. 공백·문체 차이만 변경으로 과장하지 않고 의미 있는 최소 구간만 강조되는지 봅니다.
4. `NOT_PUBLISHED`는 대기, `AMBIGUOUS`/`CONFLICT`는 운영 검토 대상으로 취급합니다. 임의로 강제 연결하지 않습니다.
5. 공식화 변화 간단 보고가 있으면 변경 ID와 전후 근거를 표본 확인합니다.

## 배포·업그레이드·롤백

### 배포 전

- 변경 파일과 `CHANGELOG.md`, 데이터 출처 변경 시 `DATA_SOURCES.md`, 기술 결정 변경 시 `DECISIONS.md`를 검토합니다.
- backend 전체 테스트와 JavaScript 문법 검사를 통과시킵니다.
- schema 변경이 있으면 새 순번 migration을 추가했는지, 운영 DB 백업과 복구 절차가 준비됐는지 확인합니다.
- `.env.example`과 실제 배포 스크립트의 환경변수 허용목록이 일치하는지 확인합니다.

### Compose 배포

~~~bash
docker compose build
docker compose up -d --force-recreate api
curl -fsS http://127.0.0.1:8070/api/health
docker compose up -d
docker compose ps
~~~

### 제공 스크립트를 사용하는 운영 배포

~~~bash
docker build -t poc07-national-assembly-api:local backend
sudo scripts/deploy_api.sh
sudo scripts/deploy_secure_workers.sh all
curl -fsS http://127.0.0.1:18070/api/health
~~~

공식자료 수집은 1시간 주기 `official-minutes-worker`, LIVE 잠정본과 공식본문 대조는 15초 주기 `official-integration-worker`가 담당합니다. 대조 워커는 READY 결과가 없는 입력만 PostgreSQL 상태 큐에서 선점하며 한 회의의 오류가 다른 회의를 막지 않습니다. 공식 본문과 링크가 역순으로 도착해도 `meeting_id + conference_id`가 정확히 일치하면 자동 연결됩니다.

`deploy_api.sh`와 worker 배포 스크립트는 새 컨테이너 기동이 실패하면 직전 컨테이너를 이름 변경해 복구합니다. API 스크립트는 health 확인 뒤 직전 컨테이너를 제거합니다. 배포 후에는 HTML, 핵심 JS/CSS, API, 공개 프록시, 모바일 화면과 실제 worker 로그까지 확인해야 완료입니다.

### 롤백 원칙

- 정적 화면·Python 코드만 문제라면 검증된 이전 코드로 이미지를 다시 만들고 컨테이너를 재배포합니다.
- **이미 적용된 DB migration 파일을 수정하거나 `schema_migrations`에서 삭제하지 않습니다.** 호환 가능한 후속 migration으로 복구합니다.
- 이전 코드가 새 schema를 읽지 못하면 코드만 먼저 내리지 않습니다. 호환 패치 또는 전용 forward migration을 준비합니다.
- 원본·revision·공식 버전을 삭제해 과거 상태로 맞추지 않습니다. 잘못 생성된 파생 결과는 새 버전/상태로 무효화하거나 재생성합니다.
- 장애 배포 전후의 이미지 ID, migration version, 환경 플래그, 발생 시각과 조치 내용을 운영 기록에 남깁니다.

## AI 요약과 비용

### 호출 단위

- 실시간: 자막 한 조각마다 호출하지 않고 화자 전환으로 닫힌 **발언 묶음 전체**를 한 번 호출합니다.
- 문맥: 대상 발언과 함께 앞쪽 최대 4개, 뒤쪽 최대 2개 묶음을 사용할 수 있습니다.
- 진행 중인 마지막 발언: 계속 바뀌므로 닫히기 전에는 요약하지 않습니다.
- 종료 후: 저장된 발언 요약과 근거 원문을 청크로 묶어 전체 회의 브리프를 만듭니다.
- 공식 자료 반영: 잠정 결과와 공식 원문 사이에서 의미가 달라진 부분만 통합합니다.

### 중복 방지

요약은 방송 ID, 본문 해시와 프롬프트 버전을 키로 DB에 저장합니다. 같은 입력은 캐시를 사용하며 API 요청이나 화면 새로고침으로 재호출하지 않습니다. 프롬프트 버전 또는 원문이 바뀐 경우에만 새 결과를 만들 수 있습니다.

### 사용량 확인

~~~bash
curl -fsS http://127.0.0.1:8070/api/ai/usage
~~~

상단 UI와 이 API에서 공급자, 모델, 현재 사용량, 최대 한도와 갱신 시각을 확인합니다. Mistral 월 예산에는 텍스트 요약과 국무회의 오디오 전사 비용이 함께 반영됩니다. 오디오 전사 기본 추정치는 EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE=0.003입니다.

관심주제 감지·알림·종료 digest·지표·Markdown 대응자료는 LLM을 사용하지 않으며 알림 화면에 비용 `$0.00`으로 표시됩니다. `WATCH_LLM_ENABLED=false`, `WATCH_KAKAO_ENABLED=false`가 무료 기본값입니다.

Kakao 운영 활성화 전 Kakao Developers에 `https://www.minslab.kr/poc/national-assembly/api/watch/kakao/callback`을 Redirect URI로 등록합니다. 카카오 동의 화면에서는 **[선택] 카카오 메시지 전송**에 동의해야 `나와의 채팅`으로 알림을 받을 수 있습니다. PoC 7은 PoC 4의 모듈·환경변수·토큰 저장소를 읽지 않으며 아래 전용 설정만 사용합니다.

~~~dotenv
WATCH_KAKAO_ENABLED=true
WATCH_KAKAO_REST_API_KEY=YOUR_POC07_KAKAO_REST_API_KEY
WATCH_KAKAO_CLIENT_SECRET=YOUR_POC07_KAKAO_CLIENT_SECRET
WATCH_KAKAO_TOKEN_ENCRYPTION_KEY=YOUR_FERNET_KEY
WATCH_KAKAO_REDIRECT_URI=https://www.minslab.kr/poc/national-assembly/api/watch/kakao/callback
WATCH_PUBLIC_BASE_URL=https://www.minslab.kr/poc/national-assembly/
~~~

기존 로컬 환경의 Kakao 앱 키를 한 번만 가져와 PoC 7 `.env`에 복제하려면 다음을 실행합니다. 이 명령은 별도의 암호화 키와 운영자 토큰을 생성하며 비밀값을 출력하지 않습니다. 실행 후 API와 모든 워커는 PoC 7 `.env`만 읽습니다.

~~~bash
python3 scripts/bootstrap_poc07_env.py --source /path/to/existing/.env
sudo scripts/deploy_api.sh
sudo scripts/deploy_secure_workers.sh notification
~~~

동일 Kakao 앱 키를 복제한 경우에도 Kakao Developers의 Redirect URI 등록은 별도로 필요합니다. 완전히 별도의 Kakao 애플리케이션을 사용하려면 PoC 7 `.env`의 REST API 키와 Client Secret만 교체하면 됩니다.

한도를 초과하거나 키가 없으면 AI 작업은 실패 상태로 남고 원본은 보존됩니다. 키를 보완하거나 한도가 갱신된 뒤 워커를 다시 실행하면 처리할 수 있습니다.

## 공식 자료 매칭 원칙

- 국회: 같은 위원회와 서울 기준 일자에 공식 회의록 후보가 하나일 때만 자동 매칭합니다.
- 국무회의: 회차와 서울 기준 일자를 우선 사용하고 동일 대표 회의 안에 부처보고·심의안건·브리핑을 묶습니다.
- 후보가 없으면 UNRESOLVED, 여러 개면 CONFLICT, 안전하게 하나로 확정되면 MATCHED로 관리합니다.
- 모호한 후보를 제목 유사도만으로 강제 연결하지 않습니다.
- 수집 API가 실패해도 이미 저장한 공식 데이터는 삭제하지 않습니다.
- 원본 응답, 자막, 오디오와 공식 문서는 provenance와 함께 보존합니다.

공식 문서가 아직 발표되지 않은 상태는 오류가 아닐 수 있습니다. 회의 종료 직후에는 정리중 또는 비공식 정리가 정상이며, 공식 회의록 발표 후 공식정리로 전환됩니다.

## 모니터링과 장애 대응

### 기본 점검 순서

1. /api/health를 확인합니다.
2. docker compose ps에서 API, DB와 워커 상태를 확인합니다.
3. 문제 서비스의 최근 로그를 확인합니다.
4. /api/live/status, /api/live/broadcasts, /api/ai/usage로 저장 상태와 한도를 확인합니다.
5. 원본이 저장됐는지 확인한 뒤 해당 워커를 --once로 재실행합니다.

| 증상 | 우선 확인 | 조치 |
|---|---|---|
| 홈페이지 Internal Server Error | api, db, migration 로그, /api/health | DB 연결과 컨테이너 상태 확인 후 API 재생성 |
| 상단은 보이나 회의 호출 실패 | 브라우저 네트워크, 프록시 upstream | NATIONAL_ASSEMBLY_UPSTREAM과 API 포트 확인 |
| 생방송 감지 실패 | live-monitor와 공식 소스 응답 | live_monitor --once 실행 |
| 국회 영상은 나오나 자막 없음 | caption-worker, WebSocket 준비 상태 | worker 재기동, 공식 자막 제공 여부 확인 |
| 국무회의 자막 없음 | executive-caption-worker, ffmpeg, 키·예산 | HLS 오디오 저장과 Voxtral 응답 확인 |
| 주제가 계속 잘게 생성됨 | 화자 전환, 발언 묶음, summary-worker | 원본을 보존한 채 worker와 프롬프트 버전 확인 |
| 종료 회의가 계속 정리중 | overview, summary/brief 로그 | AI 한도 확인 후 두 worker를 --once 실행 |
| 공식 회의록 미반영 | official worker, 매칭 상태 | 후보 유일성 확인 후 통합 worker 실행 |
| 주제 클릭 시 발언 없음 | brief/evidence와 evidence ID | 품질 게이트 로그 확인 후 브리프 재생성 |
| Kakao 로그인 KOE006 | Kakao Developers Redirect URI와 `.env` | 공개 callback URI를 정확히 등록하고 API·notification-worker 재배포 |
| Kakao 연결됐지만 발송 안 됨 | 선택 동의 scope, notification outbox, token 상태 | 재동의 상태·worker 로그 확인, in-app 알림은 유지 |
| 주제별 보고서 작성 실패 | 자료 검색 건수, Kakao 세션, topic-report-worker, 일일 한도 | 실패 detail과 queue 상태 확인, 검색/외부도구 MD는 계속 제공 |
| 인사이트 연결이 이상함 | 구체 주제 token과 양쪽 근거 제목 | 일반 단어 연결 금지 규칙 확인, 억지로 관계를 추가하지 않음 |
| UI가 이전 모습 | assets/app.js, 캐시, 이미지 | API를 build·force-recreate하고 강력 새로고침 |

로그에는 API 키, Authorization 헤더 또는 .env 내용을 출력하지 마십시오. 장애 조사 시 키 존재 여부와 길이만 확인하고 값을 복사해 공유하지 않습니다.

## 보안과 백업

- .env와 실제 키는 Git에 커밋하지 않습니다.
- 운영에서는 루트 .env 전체를 컨테이너에 전달하지 말고 프로젝트에 필요한 허용 목록만 주입합니다.
- 제공된 보안 배포 스크립트를 사용할 수 있는 환경에서는 다음 명령으로 워커별 최소 비밀값만 전달합니다.

~~~bash
sudo scripts/deploy_secure_workers.sh all
~~~

- Mistral 키는 요약·국무회의 전사 워커에만, 국회 API 키는 공식 데이터 수집 워커에만 제공합니다.
- OpenRouter 키는 watch-summary와 topic-report 워커에만 제공합니다. API·브라우저·정적 자산에는 주입하지 않습니다.
- 사용자 세션은 원문을 저장하지 않고 SHA-256 hash만 DB에 저장하며 HttpOnly·Secure·SameSite=Lax·PoC7 경로 제한 쿠키로 전달합니다. 현재 기기와 전체 기기 세션 폐기 API를 제공합니다.
- 변경 API는 공개 base URL과 다른 Origin을 거부하고, 응답에는 CSP·HSTS·Referrer-Policy·Permissions-Policy·nosniff를 적용합니다.
- 카카오 access/refresh token은 PoC7 전용 Fernet 키로 암호화하며 API 응답과 로그에 노출하지 않습니다.
- 서비스 포트 8070을 인터넷에 직접 공개하지 않습니다. 외부 사용자는 인증·권한 검사를 수행하는 부모 홈페이지나 리버스 프록시로 접속해야 합니다.
- 화자명 수정 API는 운영자 기능입니다. 부모 프록시의 관리자 세션을 거쳐야 하며 공개 클라이언트에 직접 노출하지 않습니다.
- 무료 플랜 키도 유출 위험은 같습니다. 이상 호출이나 공급자 경고가 있으면 키를 폐기하고 다시 발급합니다.
- 원본 파일에는 개인정보가 포함될 수 있으므로 서버와 백업 접근 권한을 제한합니다.

DB 볼륨과 data/raw, data/processed는 역할이 다릅니다. DB와 원본 파일을 함께 백업해야 완전한 복구가 가능합니다. 자동 백업이 별도로 구성되지 않은 환경에서는 운영 전 보존 주기, 암호화, 복구 훈련과 책임자를 정하십시오.

### 비밀값과 사용자 데이터 분류

| 데이터 | 저장 위치 | 보호·삭제 기준 |
|---|---|---|
| 국회/Mistral/OpenRouter API key | PoC7 `.env`, 해당 worker 환경 | Git·브라우저·API 응답·로그 금지, 최소 worker에만 주입, 이상 징후 시 회전 |
| Kakao access/refresh token | PostgreSQL 암호문 | `WATCH_KAKAO_TOKEN_ENCRYPTION_KEY`로 Fernet 암호화, 연결 해제 시 폐기 |
| 브라우저 세션 | 브라우저 Secure HttpOnly cookie, DB에는 SHA-256 hash | 현재 기기/전체 기기 폐기 API 제공, 원문 token 저장 금지 |
| 관심주제·알림 | PostgreSQL 사용자 계정 범위 | 최근 알림 자동 보존 한도와 사용자 삭제 기능 적용 |
| 공개 회의 자막·공식 문서 | DB와 `data/raw` | 공공 회의 원문이지만 개인정보 포함 가능, 서버·백업 접근 통제 |
| AI 파생 결과 | PostgreSQL 별도 PROVISIONAL 버전 | 근거·provider·model·prompt version 보존, 공식 테이블에 덮어쓰기 금지 |

`WATCH_KAKAO_TOKEN_ENCRYPTION_KEY`를 잃으면 기존 Kakao token을 복호화할 수 없습니다. 이 키는 DB 백업과 별도의 비밀관리소에 보관하되 복구 책임자가 접근할 수 있어야 합니다. 키를 교체할 때는 기존 계정 재동의 또는 승인된 재암호화 절차를 마련합니다.

### 백업 예시

운영 정책에 맞는 암호화 저장소를 준비한 뒤 아래처럼 DB dump와 파일 snapshot을 같은 기준 시각으로 만듭니다.

~~~bash
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > backups/poc07-db.dump
tar --create --gzip --file backups/poc07-data.tar.gz data/raw data/processed
sha256sum backups/poc07-db.dump backups/poc07-data.tar.gz > backups/SHA256SUMS
~~~

- 위 파일에는 회의 원문·사용자 설정·암호화 token이 포함될 수 있으므로 전송·보관 암호화와 최소 권한을 적용합니다.
- dump 성공 여부는 파일 크기만으로 판단하지 말고 `pg_restore --list backups/poc07-db.dump`와 checksum으로 확인합니다.
- 코드 commit ID, migration 목록, `.env` 변수 **이름별 설정 여부**, 이미지 ID를 백업 metadata에 기록합니다. 비밀값 자체는 metadata에 넣지 않습니다.
- 실제 주기는 업무 복구목표에 따라 정하되 DB와 raw가 어긋나지 않도록 같은 백업 세트 ID를 사용합니다.

### 복구 훈련

1. 운영 DB가 아닌 격리된 새 서버·빈 DB를 준비합니다.
2. 코드와 `.env`를 배치하고 DB 컨테이너만 시작합니다.
3. `pg_restore --list`와 checksum을 확인한 뒤 빈 DB에 dump를 복원합니다. 기존 운영 DB에 `--clean` 복원을 실행하지 않습니다.
4. `data/raw`, `data/processed`를 원래 상대경로와 권한으로 복원합니다.
5. 현재 API 이미지를 시작해 아직 적용되지 않은 forward migration을 실행합니다.
6. health, 회의 건수, 최근 방송 revision, 근거 발언, 공식 통합, 알림 계정과 사용량 장부를 표본 대조합니다.
7. 외부 전송 worker는 검증이 끝날 때까지 OFF로 유지하고, 복구 완료 뒤 순차 기동합니다.

복구훈련 결과에는 복구 소요시간, 유실 구간, 실패한 원본/관계와 개선조치를 남깁니다. 자동 백업이 있어도 정기적인 실제 restore 검증이 없으면 복구 가능하다고 간주하지 않습니다.

### 보존과 폐기

- 현재 코드가 자동으로 정리하는 것은 사용자별 감지 기록 등 문서화된 일부 항목뿐입니다. 회의 원본·오디오·revision 전체의 운영 보존기간은 배포기관이 별도로 정해야 합니다.
- raw를 폐기할 때 DB의 provenance와 공식 변경 검증 가능성이 훼손되는지 먼저 평가합니다. 파생 JSON만 남기고 원문을 지우지 않습니다.
- 계정·Kakao 연결·세션 삭제와 공개 회의 원본 보존은 서로 다른 정책입니다.
- 삭제 작업은 대상 기간·source·백업 존재를 조회로 확정하고 승인·감사기록·복구 가능 기간을 정한 뒤 수행합니다.

## 주요 API

전체 요청·응답 계약은 실행 중인 /docs에서 확인합니다.

| 구분 | 메서드와 경로 | 용도 |
|---|---|---|
| 시스템 | GET /api/health | 앱·DB 상태 |
| 시스템 | GET /api/meta | 서비스 메타데이터 |
| 시스템 | GET /api/ai/usage | 모델, 사용량, 한도, 갱신 시각 |
| 시스템 | GET /api/data-sources | 데이터 출처 |
| 일정 | GET /api/schedule/upcoming | 예정 회의 전광판 |
| 일정 | GET /api/schedule/today | 오늘 일정 |
| 일정 | GET /api/schedule/calendar | 최대 42일 국회 일정 달력 |
| 회의 | GET /api/committees/meetings | 국회 회의·공식 자료 |
| 회의 | GET /api/executive/briefings | 국무회의·행정부 공식 자료 |
| 회의 | GET /api/committees/meetings/{conference_id}/transcript | 공식 국회 발언 |
| 정책 | GET /api/committees/policy-flow | 위원회 정책 흐름 |
| 정책 | GET /api/policy/cross-institution-flow | 행정부·국회 잠정 공통 신호 |
| 정책 | GET /api/policy/specific-issues | 구체 주제별 신규·급증·지속·미관측과 제도화 단계 |
| 의안 | GET /api/bills | 회의 연결 의안과 표결 |
| 라이브 | GET /api/live/status | 현재 방송 상태 |
| 라이브 | GET /api/live/magazine | 상단 일정·결과 통합 목록 |
| 라이브 | GET /api/live/broadcasts | 방송 목록과 추가 로딩 |
| 라이브 | GET /api/live/overview | 방송 처리 단계와 진행률 |
| 자막 | GET /api/live/transcript/snapshot | 입장 시 저장 자막과 cursor |
| 자막 | GET /api/live/transcript/delta | cursor 이후 변경분 |
| 자막 | GET /api/live/transcript/recent | 최근 발언 |
| 자막 | GET /api/live/broadcasts/{broadcast_id}/transcript | 방송별 전체 발언 묶음 |
| 화자 | GET /api/live/broadcasts/{broadcast_id}/speakers | 화자 보정 조회 |
| 화자 | PUT /api/live/broadcasts/{broadcast_id}/speakers/{source_label} | 운영자 화자명 보정 |
| 화자 | DELETE /api/live/broadcasts/{broadcast_id}/speakers/{source_label} | 운영자 보정 철회 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief | 잠정/통합 회의 브리프 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief/official | 공식 반영 상태 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief/evidence | 선택한 주제·과제의 근거 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief.md | 저장 결과 기반 Markdown 대응자료 |
| 결과 | GET /api/live/tasks | 방송에서 도출된 잠정 과제 |
| 알림 세션 | POST /api/watch/session | 익명 PoC7 사용자 세션 시작 |
| 알림 세션 | POST /api/watch/session/upgrade | 구형 header token을 cookie 세션으로 승격 |
| 알림 세션 | DELETE /api/watch/session/current, /all | 현재 또는 전체 기기 세션 폐기 |
| 알림 규칙 | GET/POST /api/watch/rules | 내 규칙 조회·생성 |
| 알림 규칙 | PUT/DELETE /api/watch/rules/{rule_id} | 규칙 수정·삭제와 revision 보존 |
| 알림 | GET /api/watch/rules/{rule_id}/report | 알림 주제의 현재 또는 최신 저장 근거 보고서 |
| 알림 | GET /api/watch/notifications | 최근 in-app 알림 |
| 알림 | POST /api/watch/notifications/{id}/read | 읽음 처리 |
| 알림 | DELETE /api/watch/notifications/{id}, /api/watch/notifications | 개별 삭제·읽은 기록 정리 |
| 알림 | GET /api/watch/metrics | 감지·알림·억제·지연·공식확인 지표 |
| Kakao | GET /api/watch/kakao/status | 내 연결·재동의 상태 |
| Kakao | POST /api/watch/kakao/authorize | OAuth 시작 URL 생성 |
| Kakao | GET /api/watch/kakao/callback | Kakao callback, OpenAPI에서는 숨김 |
| Kakao | DELETE /api/watch/kakao | 연결·token 폐기 |
| 운영자 테스트 | POST /api/watch/test-broadcasts | 운영자 인증 후 격리된 테스트 방송 시작 |
| 운영자 테스트 | GET /api/watch/test-broadcasts/latest, /{test_id} | 운영자 인증 후 테스트 진행 상태·결과 조회 |
| 운영자 세션 | GET /api/watch/admin/session | 탭 범위 운영자 세션 검증 |
| 운영 검토 | GET/POST /api/watch/admin/reviews... | 자동 공식대조와 별도 운영자 판정 |
| 운영 검토 | POST/GET /api/watch/admin/live-regression... | 최근 실방송 회귀 감사 실행·조회 |
| 주제 보고서 | POST /api/topic-reports/search | 저장 자료 의미구조·키워드 검색, LLM 0회 |
| 주제 보고서 | POST /api/topic-reports | 요청 시 전용 워커 작성 또는 동일 저장본 재사용 |
| 주제 보고서 | GET /api/topic-reports | 내 저장 보고서 목록 |
| 주제 보고서 | GET /api/topic-reports/{id} | 근거 포함 보고서 조회 |
| 주제 보고서 | GET /api/topic-reports/{id}/report.md | 저장 보고서 Markdown 다운로드 |

사용자 범위 API는 경로 제한 Secure HttpOnly cookie를 우선 사용하고 `X-Watch-Token`은 구형 세션 승격 호환에만 사용합니다. 운영 검토 API는 `X-Watch-Admin-Token`과 same-origin 검사를 함께 요구합니다. 변경 요청 body는 공개 프록시에서 최대 64 KiB로 제한합니다.

`GET /api/meetings/today`는 이전 클라이언트 호환용 deprecated 경로입니다. 새 구현은 `/api/schedule/today`를 사용합니다. `GET /api/assembly/reference`는 저장된 국회 reference snapshot 호환 API이지만 현재 추가기능 화면은 의석 정보를 노출하지 않습니다.

## 개발과 테스트

~~~bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8070 --reload
~~~

~~~bash
pytest backend/tests -q
ruff check backend
node --check web/app.js
node --check web/dashboard.js
node --check web/watch-alerts.js
node --check web/topic-reports.js
node --check web/assembly-extras.js
~~~

외부 API 호출은 기본 테스트 suite에 넣지 않습니다. fixture에는 출처, 조회일, 원본/합성 여부와 이용 조건을 기록하고 키와 개인정보를 포함하지 않습니다.

### 테스트 계층과 완료 기준

| 계층 | 확인 내용 | 완료 기준 |
|---|---|---|
| 단위 테스트 | adapter envelope, normalizer, 상태 전이, 주제·과제 매핑, quota, 보안 정규화 | 외부 네트워크 없이 전체 통과 |
| repository/API 테스트 | migration 이후 저장·멱등성·권한·응답 schema·근거 ID | fixture DB에서 전체 통과 |
| 정적 화면 계약 | 필수 DOM ID, 탭·dialog·인쇄·반응형 구조, JS 문법 | 테스트와 `node --check` 통과 |
| source probe | 현재 공식 LIVE endpoint·player/HLS 계약 | 승인된 운영/검증 환경에서만 실행, raw manifest 보존 |
| 실사용 E2E | 테스트 방송 → 발언 누적 → 알림 → 실시간 초안 → 종료 결과 연결 | 실제 화면에서 사용자 시나리오 완료 |
| 실방송 회귀 | cursor 증가, final revision, 2분 이상 공백, 동시 방송 격리, 공식 전환 | audit가 PASS이거나 PENDING 사유가 설명 가능, REVIEW_REQUIRED는 조치 기록 |

새 API는 schema/API 테스트를, migration은 repository 회귀 테스트를, 사용자 화면 변경은 데스크톱·노트북·모바일 수동 확인을 함께 추가합니다. 테스트 숫자 자체보다 **원본 보존, 근거 연결, 중복 호출 방지, 공식/잠정 분리**가 깨지지 않는지가 검수 기준입니다.

### 공식 LIVE source probe

~~~bash
python3 scripts/probe_live_sources.py
~~~

국회 대상 위원회의 공식 생중계 상태와 KTV 플레이어 계약을 확인하고 원본·manifest를 data/raw, 정규화 상태를 data/processed/live_status.json에 저장합니다.

## 디렉터리

~~~text
PoC/07-NationalAssembly/
├── project.json              # 홈페이지 PoC 등록 메타데이터
├── README.md                 # 사용자·운영자 통합 안내서
├── AGENTS.md                 # 구현과 데이터 권위 원칙
├── CHANGELOG.md              # 날짜별 변경 내역
├── .env.example              # 환경변수 예시
├── docker-compose.yml        # API·DB·수집/후처리 워커
├── backend/
│   ├── app/                  # FastAPI, domain, adapter, repository, worker, service
│   ├── migrations/           # PostgreSQL migration
│   └── tests/                # 단위·통합 테스트와 fixtures
├── web/                      # 반응형 사용자 화면과 정적 읽기 스냅샷
├── docs/                     # 설계·개발·운영 문서
├── scripts/                  # 수집·배포·점검 명령
└── data/
    ├── raw/                  # 원본 응답·자막·오디오·manifest
    └── processed/            # 정규화·상태 산출물
~~~

동일 manifest와 본문은 해시로 중복 판정합니다. 원본이 바뀌면 이전 버전을 덮어쓰지 않고 새 버전과 provenance를 저장합니다.

## 사용자 FAQ

**실시간에 보이던 주제 수보다 종료 보고서의 핵심 주제가 적은 이유는 무엇인가요?**

실시간 주제는 발언 묶음이 닫힐 때 생기는 잠정 신호입니다. 종료 후 전체 흐름을 다시 보면서 같은 의미의 표현을 하나의 상위 주제로 합칩니다. 보고서의 실시간 주제 통합 내역에서 어떤 신호가 어느 상위 주제로 들어갔는지, 교차·미연결된 것이 있는지 확인할 수 있습니다.

**완료, 비공식 정리, 공식정리는 어떤 차이인가요?**

완료는 회의가 끝났다는 뜻이고, 비공식 정리는 저장 발언을 AI/규칙으로 잠정 정리했다는 뜻입니다. 공식정리는 공식 회의록이나 브리핑이 연결됐다는 뜻입니다. 회의 생명주기와 자료 권위는 서로 다른 태그입니다.

**화자 미확인 또는 번호로 보이는 이유는 무엇인가요?**

방송 자막 source가 실제 이름을 제공하지 않은 경우입니다. 번호를 인물로 추정하지 않으며 운영자 임시 표시 또는 공식 회의록의 화자로 나중에 보완합니다.

**주제나 과제가 사실인지 어떻게 확인하나요?**

제목이나 주요 논의 카드를 선택해 연결된 발언 묶음·공식 완성형 발언·원문 링크를 확인합니다. 근거가 없는 AI 항목은 품질 게이트를 통과해 저장될 수 없습니다.

**자료 검색과 보고서 작성은 비용이 같은가요?**

아닙니다. 자료 검색, 인사이트 조회, 알림 감지, 외부도구용 MD는 LLM을 호출하지 않습니다. 국정ON 내부의 주문형 보고서 작성 버튼만 조건을 만족할 때 OpenRouter 작업을 예약합니다. 동일 결과를 다시 보는 것은 cache를 사용합니다.

**Kakao를 연결하지 않아도 사용할 수 있나요?**

일정·LIVE·회의 보고서·로컬 알림·자료 검색과 외부도구 내보내기는 사용할 수 있습니다. 여러 PC의 알림 설정 동기화, Kakao 발송과 내부 주문형 보고서 작성은 계정 연결이 필요합니다.

**공식자료가 나오면 비공식 보고서가 사라지나요?**

별도 중복 화면을 만들지 않고 같은 보고서에 공식 확인 내용을 반영하지만, 저장 계층의 LIVE·잠정·공식 원본과 이전 버전은 보존합니다. 의미 있는 수정은 전후 문구로 확인할 수 있습니다.

## 용어

| 용어 | 뜻 |
|---|---|
| Source document/version | 외부에서 받은 한 문서와 내용 hash별 불변 버전 |
| Segment/revision | 자막 source가 보낸 한 조각과 partial→final 수정 이력 |
| 발언 묶음(utterance) | 같은 화자의 연속 segment를 화면·요약용으로 합친 단위 |
| 실시간 초안 | 닫힌 발언 묶음의 저장 요약과 `live_insight`를 주제별로 누적한 잠정 보고서 |
| Meeting brief | 종료 후 전체 발언을 다시 통합한 핵심 주제·화자 요지·과제 읽기 모델 |
| Evidence ID | 주제·과제·요약이 근거로 삼은 실제 발언/공식 문서 식별자 |
| Reconciliation | LIVE와 공식 원문·화자·회의 identity를 대조해 연결 상태를 정하는 과정 |
| Official integration | 잠정 브리프와 특정 공식 문서 버전을 합성한 파생 읽기 모델 |
| Cache key | 방송·본문/evidence hash·provider·model·prompt version으로 같은 외부 호출을 막는 키 |
| Cursor | LIVE revision의 전역 증가 번호. snapshot 이후 delta를 빠짐없이 받는 기준 |

## 알려진 제약

- 라이브 자막의 화자 번호는 신원 정보가 아니므로 공식 문서 전까지 인물명을 확정할 수 없습니다.
- 국무회의 라이브는 오디오 상태, 동시 발화, 고유명사와 방송 음량에 따라 전사 정확도가 달라집니다.
- 실시간 주제와 과제는 잠정 결과이며 종료 후 전체 분석에서 합쳐지거나 수정될 수 있습니다.
- 공식 회의록과 브리핑은 회의 종료 즉시 발표되지 않을 수 있습니다.
- 행정부와 국회의 공통 정책 신호는 동일 안건이나 직접 인과관계를 의미하지 않습니다.
- 공식 후보가 여러 개인 경우 자동 연결하지 않으므로 운영자 확인이 필요합니다.

## 운영 체크리스트

### 매일

- /api/health와 Compose 서비스 상태 확인
- 상단 일정과 실제 공식 일정의 누락 여부 확인
- 생방송 감지, 자막 증가, 최신 발언 자동 이동 확인
- AI 사용량과 다음 갱신 시각 확인
- 종료 회의가 기록 중 또는 정리중에 장시간 머무는지 확인

### 공식 자료 발표 후

- 동일 회의 카드가 공식정리로 전환됐는지 확인
- 주제별 과제와 담당 부처가 잘못 여러 주제에 묶이지 않았는지 확인
- 근거 발언이 공식 완성형 문장과 공식 화자를 반영했는지 확인
- 의미 없는 문체 변경이나 과도한 하이라이트가 없는지 확인
- 국무회의의 부처보고·심의안건·대변인 브리핑과 대통령 지시사항 확인

### 배포 후

- /, /assets/app.js, /api/health 응답 확인
- 모바일 폭과 데스크톱 sticky 근거 패널 확인
- 통합 홈페이지 프록시와 관리자 화자 수정 권한 확인
- 로그와 네트워크 응답에 비밀값이 노출되지 않았는지 확인

## 재구축·인수인계 체크리스트

재구축 또는 유지보수 사업자는 아래 산출물을 운영기관에 인계하고 함께 복구·기능 시험을 수행합니다.

### 코드와 빌드

- [ ] 기준 Git commit/branch와 `CHANGELOG.md`
- [ ] PoC 7 단독 Docker image 재현 절차와 사용한 Python/package lock 범위
- [ ] `docker-compose.yml`, 운영 배포 스크립트, reverse proxy 계약
- [ ] 전체 테스트 결과와 미실행된 외부/E2E 시험 사유
- [ ] 적용된 migration 목록과 schema 호환·rollback 판단서

### 데이터와 복구

- [ ] PostgreSQL dump와 `data/raw`, `data/processed` 동일 세트 백업
- [ ] checksum, 암호화·보관 위치, 접근권한과 보존기간
- [ ] 격리 환경 restore 결과, 복구 소요시간과 유실 가능 구간
- [ ] 원본→정규화→브리프→공식 통합의 표본 provenance 추적 결과
- [ ] Kakao token 암호화 키와 DB 백업의 분리 보관·복구 책임자

### 외부 계정과 비용

- [ ] 국회 API, Mistral, OpenRouter, Kakao 앱의 소유 조직·관리자·갱신 절차
- [ ] 실제 비밀값이 아닌 환경변수 목록과 설정 여부·회전일
- [ ] Mistral 월 USD, OpenRouter 일 요청, 주제 보고서/공식 변화 전용 한도
- [ ] 공급자 가격·무료 credit·model 종료 시 대체 모델 검증 절차
- [ ] Kakao Redirect URI·선택 동의 scope와 운영 도메인 인증

### 운영과 품질

- [ ] 일일 점검 담당자와 장애 연락체계
- [ ] 실제 동시 방송 2~4개 수집·격리 확인 결과
- [ ] 국무회의 HLS 오디오 청크·전사·종료 후 공식 연결 시험 결과
- [ ] 테스트 방송, 알림, Kakao, 주제별 보고서, 인쇄·Markdown, 모바일 검수 결과
- [ ] `UNRESOLVED`, `CONFLICT`, `REVIEW_REQUIRED`, 장기 `정리중` 처리 기준
- [ ] 알려진 제약, 미완료 항목, 데이터 품질 이슈와 재현 방법

인수 완료 기준은 서버가 뜨는 것만이 아닙니다. **공식 일정 1건 → LIVE 원본 저장 → 발언 묶음 → 잠정 결과 → 근거 조회 → 공식자료 통합**의 전체 흐름과, 백업에서 같은 근거를 복구하는 과정이 재현되어야 합니다.

## 관련 문서

- [프로젝트 배경](docs/PROJECT_CONTEXT.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [국무회의 × 국회 실행 플랜](docs/EXECUTION_PLAN.md)
- [관심주제 실시간 알림·완성도 보완 구축 계획](docs/WATCH_ALERTS_BUILD_PLAN.md)
- [계정 동기화·주제별 보고서 구축 기록](docs/TOPIC_REPORT_AND_ACCOUNT_PLAN.md)
- [PoC 7 공개 reverse proxy 계약](docs/PUBLIC_PROXY_CONTRACT.md)
- [데이터 모델](docs/DATA_MODEL.md)
- [데이터 출처와 신청 링크](docs/DATA_SOURCES.md)
- [개발 방법](docs/DEVELOPMENT.md)
- [상세 운영 방법](docs/OPERATIONS.md)
- [PoC 평가](docs/POC_EVALUATION.md)
- [설계 결정](docs/DECISIONS.md)
- [변경 내역](CHANGELOG.md)

새 기능은 별도 구동 경로를 복제하지 않고 **일정 → 방송 → 발언 묶음 → 브리프 → 공식 자료 통합** 공통 파이프라인을 재사용합니다. 업무 차이는 수집 어댑터, 분류 taxonomy, 공식 문서 파서와 화면 그룹 규칙에만 추가하는 것이 이 프로젝트의 운영 원칙입니다.
