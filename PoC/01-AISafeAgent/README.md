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

- 기상청 초단기실황: 현재부터 과거 6시간 강수
- 기상청 초단기예보: 현재부터 향후 6시간 강수
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

지도 선택 시 빠른 공간 조회를 먼저 수행하고, 분석 실행 시 기상청 강수 조회와 LLM 보고서 생성을 이어서 처리합니다.

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
- 역지오코딩 키가 없으면 법정동 표시는 사용할 수 없습니다.
- 직선거리는 현장 접근 거리와 다를 수 있습니다.
- AI 보고서는 참고용이며 재난 대응 기관의 공식 판단을 대체하지 않습니다.
- 실제 대응 전 최신 기상 특보, 현장 상황과 관계기관 안내를 확인합니다.
