# 01. AI Safe Agent

선택한 위치의 기상청 강수 관측·예보와 반경 500m 공간 방재 데이터를 결합하고, 선택한 LLM으로 재난안전 판단 보고서를 생성하는 실행형 PoC입니다.

## 현재 상태

- 홈페이지 통합: 완료
- 공개 화면: https://www.minslab.kr/poc?project=ai-safe-agent
- 실행 백엔드: 기존 main.py ASGI 서비스
- 별도 프로젝트 웹서버 또는 전용 포트: 없음
- 위치 입력: GPS, 지도 클릭, 좌표 직접 입력, 브라우저 저장 장소
- LLM: 로컬 Ollama, Hugging Face Router, OpenRouter
- 공간 지식베이스: 날짜가 포함된 최신 integrated_disaster_kb_*.pkl

## 분석 데이터

선택 좌표를 기준으로 다음 정보를 구성합니다.

- 기상청 초단기실황: 현재부터 과거 6시간의 강수량, 기온, 습도, 풍향·풍속, 강수형태
- 기상청 초단기예보: 현재부터 향후 6시간의 강수량·확률, 기온, 습도, 풍향·풍속, 강수형태, 낙뢰, 하늘상태
- 침수흔적도
- 산사태 발생 이력
- 인명피해 우려 지역
- 통합대피소
- 반경 500m 내 위험 요소와 대피소 위치·거리

지도에는 위험 요소와 대피소 마커를 표시하고, 보고서에는 확인된 데이터만 근거로 사용합니다.

## 홈페이지 실행 흐름

1. PoC 메뉴에서 01. AI Safe Agent를 선택합니다.
2. 브라우저 위치 권한을 허용하거나 지도·좌표 입력으로 분석 지점을 선택합니다.
3. 법정동, 반경 500m 위험 요소와 대피소를 확인합니다.
4. 필요한 경우 기초 데이터 만들기로 안전데이터를 다시 수집합니다.
5. 설치된 로컬 모델 또는 원격 모델을 선택합니다.
6. 분석 실행으로 강수 추계, 공간 요약과 AI 안전 보고서를 생성합니다.

지도 선택 시 빠른 공간 조회를 먼저 수행합니다. 분석 실행은 기상청 강수를 한 번 조회해 그래프에 표시한 뒤 같은 payload를 공간·LLM 준비 단계에서 재사용하고, 보고서 토큰을 실시간으로 표시합니다.

## 기초 데이터 생성

기초 데이터 만들기는 다음 안전데이터 API를 수집합니다.

| 데이터 | 환경변수 |
| --- | --- |
| 통합대피소 | SAFETYDATA_SHELTER_KEY |
| 산사태발생이력 | SAFETYDATA_LANDSLIDE_KEY |
| 인명피해우려지역 | SAFETYDATA_VULNERABLE_KEY |
| 침수흔적도 | SAFETYDATA_FLOOD_KEY |

수집 결과를 CSV로 기록하고 좌표를 WGS84로 정규화한 뒤 하나의 PKL 지식베이스를 만듭니다.

중요: 홈페이지의 기초 데이터 만들기는 기존 integrated_disaster_kb PKL을 삭제하고 현재 시각이 포함된 새 PKL로 교체합니다. 생성 중에는 동일 작업을 중복 실행할 수 없습니다.

CSV와 PKL은 생성 데이터이므로 Git 추적 대상이 아닙니다.

## 공용 환경변수

모든 설정은 저장소 루트의 공용 .env에서 읽습니다.

기상청:

~~~dotenv
KMA_AUTH_KEY=YOUR_KMA_API_HUB_AUTH_KEY
KMA_ULTRA_SHORT_URL=https://apihub-pub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtFcst
KMA_ULTRA_NCST_URL=https://apihub-pub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst
~~~

LLM 공급자:

~~~dotenv
HF_API_KEY=YOUR_HUGGINGFACE_ROUTER_API_KEY
HF_BASE_URL=https://router.huggingface.co/v1
AI_SAFE_AGENT_MODEL=Qwen/Qwen3.6-35B-A3B
AI_SAFE_HF_QWEN25_MODEL=Qwen/Qwen2.5-72B-Instruct

OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_SAFE_OPENROUTER_MODEL=openai/gpt-4o-mini

OLLAMA_BASE_URL=http://127.0.0.1:11434
~~~

법정동 역지오코딩:

~~~dotenv
KAKAO_REST_API_KEY=YOUR_KAKAO_REST_API_KEY
VWORLD_API_KEY=YOUR_VWORLD_API_KEY
~~~

지식베이스 경로를 고정하려면 다음 값을 사용합니다.

~~~dotenv
DISASTER_KB_PATH=/safe/path/integrated_disaster_kb_YYYYMMDD_HHMMSS.pkl
~~~

DISASTER_KB_PATH가 없으면 PoC 폴더의 날짜 PKL 중 수정 시각이 가장 최신인 파일을 자동 선택합니다.

## 홈페이지 API

- GET /api/poc/ai-safe-agent/kb/status
- POST /api/poc/ai-safe-agent/kb/build
- GET /api/poc/ai-safe-agent/models
- POST /api/poc/ai-safe-agent/reverse-geocode
- POST /api/poc/ai-safe-agent/rain
- POST /api/poc/ai-safe-agent/spatial
- POST /api/poc/ai-safe-agent/analyze
- POST /api/poc/ai-safe-agent/analyze-stream

Ollama와 원격 LLM 키는 브라우저에 전달하지 않으며 백엔드에서만 사용합니다.

## 터미널 실행

지식베이스 다시 만들기:

~~~bash
cd /home/ubuntu/apps/myservice
python3 PoC/01-AISafeAgent/import.py
~~~

LLM 없이 공간·강수 컨텍스트 확인:

~~~bash
python3 PoC/01-AISafeAgent/RiskInspection_v1.py   --lat 37.5665   --lng 126.9780   --no-ai
~~~

기본 Hugging Face 모델로 전체 분석:

~~~bash
python3 PoC/01-AISafeAgent/RiskInspection_v1.py   --lat 37.5665   --lng 126.9780
~~~

특정 PKL 사용:

~~~bash
python3 PoC/01-AISafeAgent/RiskInspection_v1.py   --lat 37.5665   --lng 126.9780   --kb /safe/path/integrated_disaster_kb.pkl
~~~

터미널 기본 모델은 AI_SAFE_AGENT_MODEL의 Hugging Face 모델입니다. 홈페이지에서는 모델 콤보상자에서 공급자를 명시적으로 선택합니다.

## 파일 구성

~~~text
PoC/01-AISafeAgent/
├── README.md
├── project.json
├── RiskInspection_v1.py  # 공간 분석, 기상청, LLM 보고서
└── import.py             # 안전데이터 수집과 PKL 생성

main.py                   # 홈페이지 UI와 PoC API
~~~

## 제한과 검토 원칙

- 지식베이스가 없으면 공간 목록은 비어 있고 실시간 강수 중심으로만 실행됩니다.
- KMA 키가 없거나 API가 실패하면 강수 상태에 오류가 표시되지만 공간 분석은 계속할 수 있습니다.
- Kakao/VWorld가 없거나 실패하면 호출 제한과 캐시가 적용된 OpenStreetMap Nominatim을 마지막 대체 경로로 사용합니다. OSM 주소 데이터에 따라 법정동 수준 이름이 없을 수 있습니다.
- 직선거리는 현장 접근 거리와 다를 수 있습니다.
- AI 보고서는 참고용이며 재난 대응 기관의 공식 판단을 대체하지 않습니다.
- 실제 대응 전 최신 기상 특보, 현장 상황과 관계기관 안내를 확인합니다.


## 현재 화면 동작 상세

### 초기 위치

1. 화면 진입 직후 브라우저 Geolocation을 high accuracy, 12초 timeout, 30초 cache 조건으로 호출합니다.
2. 위치를 기다리는 동안 지도 중앙에 `GPS 기반 장소로 이동 중입니다.` 팝업을 표시합니다.
3. 성공하면 좌표, 정확도 안내, 지도 중심과 500m 원을 갱신합니다.
4. 실패하면 원인을 안내하고 서울시청 기본 좌표로 공간 조회를 계속합니다.
5. 사용자의 첫 지도 클릭은 지도 영역이 화면 중앙에 오도록 한 번만 부드럽게 스크롤합니다.

### 법정동 조회 순서

```text
Kakao coord2regioncode (B 법정동)
  → 실패/미설정 시 VWorld parcel address
  → 실패/미설정 시 OpenStreetMap Nominatim
```

OSM fallback은 좌표를 소수점 4자리로 캐시하고 서버 전체에서 초당 1회 이하로 호출합니다. `province/state/city`, `city_district/borough/county`, `quarter/suburb/neighbourhood/village` 순서로 법정동에 가까운 지역명을 구성합니다. 공급자 오류는 데이터 로그에 남기되 지도·위험 분석은 중단하지 않습니다.

## 강수와 공간 분석 원리

기상청 좌표 변환은 위경도를 초단기예보 격자 `nx/ny`로 바꿉니다. 현재 시각을 기준으로 초단기실황을 과거 6시간, 초단기예보를 향후 6시간에 배치해 총 13개 시점을 만듭니다. 각 시점에는 `RN1` 강수량과 함께 `T1H` 기온, `REH` 습도, `WSD/VEC` 풍속·풍향, `PTY` 강수형태를 저장하고 예보에는 `POP` 강수확률, `LGT` 낙뢰, `SKY` 하늘상태도 저장합니다. 현재 시점에 관측과 예보가 함께 있으면 관측값을 우선하고 관측에 없는 예보 항목만 보완합니다. 화면은 강수량과 기온을 독립 범위의 두 선으로 그리고 X축에는 `현재/+1H` 대신 실제 시각을 표시합니다. 왼쪽 축은 강수량(mm), 오른쪽 축은 기온(°C)의 최저·중간·최고값을 표시하며 기온축에는 여백을 두어 최저기온이 강수 0선과 같은 값처럼 보이지 않게 합니다. 각 시간 상단에는 `SKY`, `PTY`, `LGT`를 조합한 맑음·구름·비·눈·낙뢰 아이콘을 표시합니다. RN1 항목이 없거나 시점 자체가 미수신이면 `0mm`로 바꾸지 않고 null로 유지해 점과 선을 끊으며, 기상청이 명시적으로 `강수없음`을 반환한 경우만 실제 `0mm`로 그립니다. 현재 시점은 점선으로 구분하고 각 점과 아이콘의 툴팁에서 나머지 기상 요소를 확인할 수 있습니다.

공간 지식베이스는 데이터 유형별 위경도 필드가 달라 별도 후보 키를 사용합니다. 위도 경도 차이를 미터로 근사해 500m 이내 항목만 선택하고 거리순으로 정렬합니다.

| 출력 | 최대 표시 |
| --- | --- |
| 지도 위험·대피소 feature | 120개 |
| 유형별 상세 데이터 | 80개 |
| LLM에 전달하는 유형별 대표 상세 | 가까운 3개 |

화면에는 실제 상세 데이터를 유지하면서 LLM에는 건수, 최근/가까운 대표 항목과 13개 시점의 강수·기온·습도·바람·강수형태·강수확률·낙뢰 흐름만 전달해 입력 길이를 제한합니다. API에 없는 값은 추정하지 않습니다.

## AI 안전비서 프롬프트와 성능 설정

LLM은 내부적으로 과거 위험 이력, 현재 기상과 향후 흐름을 모두 비교하지만 분석 과정과 시간대별 수치를 그대로 출력하지 않습니다.

- 즉시 알릴 특이사항이 없으면 제목·번호·위험등급·행동요령 없이 한 문장, 한 줄로 끝냅니다.
- 특이사항이 있으면 최대 4줄 안에서 `특이사항:`과 `지금 할 일:`만 출력합니다.
- 수치는 위험 판단을 이해하는 데 꼭 필요한 경우에만 한 번 사용합니다.
- 행동요령은 현재 위치에서 바로 실행할 수 있는 행동 1~2개로 제한하고 `주의하세요`, `대비하세요` 같은 막연한 문구는 사용하지 않습니다.

입력에 있는 위험 이력을 없다고 말하거나 누락값을 추정하지 않으며, 위험은 가능성으로 안내합니다. 외부 OpenAI 호환 모델의 `max_tokens`와 로컬 Ollama의 `num_predict`를 모두 160으로 제한해 짧은 형식을 강화합니다. 최종 후처리는 모델 판단 문장을 유지하면서 정상 의미 표현은 한 줄로 통일하고, 위험 답변에서 행동 줄이 빠지거나 막연하면 위험 유형에 맞는 즉시 행동을 보완해 정확히 두 줄로 정리합니다.

LLM 문맥 끝에는 구조화된 `[보고서 출력 제어]`를 붙입니다. 다음 중 하나를 충족하면 `있음`으로 판정합니다: 시간당 강수 최고 3mm 이상, 향후 3시간 합계 10mm 이상, 과거 6시간 누적 20mm 이상, 주변 위험 이력과 현재·예상 강수의 중첩, 눈·낙뢰, 풍속 9m/s 이상, 기온 33°C 이상 또는 -12°C 이하. 이 수치는 공식 특보 기준이 아니라 PoC의 간결한 보고 여부를 정하는 휴리스틱입니다.

기상 위험 신호가 없으면 주변 과거 위험 이력만으로 현재 경보를 만들지 않고 정상 한 줄로 정리합니다. 반대로 구조화된 판정이 `있음`이면 작은 모델이 특이사항이 없다고 답하더라도 판정 핵심과 즉시 행동을 사용해 두 줄로 보정합니다.

로컬 Ollama 설정:

| 항목 | 값 |
| --- | --- |
| stream | true (홈페이지 `analyze-stream`) |
| think | false |
| num_ctx | 2048 |
| num_predict | 160 |
| temperature | 0.2 |
| top_p | 0.9 |
| repeat_penalty | 1.1 |
| keep_alive | 5m |

브라우저는 `context`, `token`, `done`, `error` NDJSON 이벤트를 처리합니다. `context`가 오면 지도·강수·분석 데이터를 먼저 그립니다. 로컬 Ollama의 원시 토큰은 서버에서 짧게 버퍼링한 뒤 후처리된 한두 줄을 하나의 `token` 이벤트로 전송하므로 생성 중 장황한 초안이 화면에 노출되지 않습니다. 분석 버튼은 실행 중 `생성 중지`로 바뀌며 AbortController로 브라우저 요청을 취소합니다.

## API 요청·응답 요약

| API | 입력 | 출력 |
| --- | --- | --- |
| `/kb/status` | 없음 | 최신 PKL 상태 |
| `/kb/build` | 없음 | NDJSON 수집 로그와 완료 상태 |
| `/models` | 없음 | Ollama + HF + OpenRouter 선택지 |
| `/reverse-geocode` | lat, lng | provider, legal_dong, address |
| `/rain` | lat, lng | 13시점 강수와 상태 |
| `/spatial` | lat, lng | 건수, map_features, details |
| `/analyze-stream` | lat, lng, ai_model, 선택적 rain_info | context + AI token stream |
| `/analyze` | 동일 | 호환용 단일 JSON 응답 |

`rain_info`가 유효하면 `prepare_analysis()`가 재조회하지 않습니다. CLI나 기존 호출처럼 전달되지 않으면 서버가 KMA를 직접 조회합니다.

## 지식베이스 생성 구조

`import.py`는 각 공공데이터 API를 페이지당 기본 1,000건으로 반복 조회하고 원본 CSV를 기록합니다. 좌표는 WGS84 여부를 판별하고 필요한 경우 Web Mercator를 변환합니다. 전처리 결과는 다음 키로 PKL에 저장됩니다.

```text
{
  floods: [...],
  shelters: [...],
  vulnerable: [...],
  landslides: [...]
}
```

새 지식베이스를 만들 때 기존 날짜 PKL을 제거하고 `integrated_disaster_kb_YYYYMMDD_HHMMSS.pkl` 하나를 생성합니다. 분석 모듈은 경로와 mtime을 캐시해 같은 PKL을 반복 역직렬화하지 않습니다.
