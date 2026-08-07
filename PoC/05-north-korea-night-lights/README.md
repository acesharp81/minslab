# 05. 북한 야간조명 3D 지도

Google Earth Engine Python API에서 북한 경계 안의 VIIRS 월별 야간조명 자료를 내려받고, cloud-free 관측이 존재하는 약 463.83m 격자를 pydeck GridCellLayer의 3D 막대로 표현하는 실행형 PoC입니다.

운영 결과물은 북한 격자만 담은 월별 compact JSON.gz와 하나의 공통 deck.gl 플레이어입니다. 마우스로 지도를 회전·확대할 수 있고 각 격자의 원본 방사휘도와 관측 횟수를 확인할 수 있습니다. 기존 단일 월 HTML 생성 기능도 재현용으로 유지합니다.

## 현재 검증된 결과

2026-08-07에 다음 조건으로 실제 생성까지 검증했습니다.

| 항목 | 검증값 |
| --- | --- |
| 단일 월 검증 기준 | 2024-01 |
| Earth Engine 프로젝트 | minslab-504801 |
| VIIRS 컬렉션 | NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG |
| 경계 컬렉션 | USDOS/LSIB_SIMPLE/2017 |
| 북한 선택 조건 | country_co = KN |
| 요청 및 표시 격자 | 463.83m |
| 유효 조건 | cf_cvg > 0 |
| 생성 격자 수 | 740,776개 |
| 결과 파일 | output/north_korea_viirs_2024-01.html |
| 결과 크기 | 156,055,271바이트, 약 148.8MiB |
| 동일 월 압축 데이터 | 5,256,249바이트, 약 5.0MiB |
| 핵심 라이브러리 | earthengine-api 1.7.38, pydeck 0.9.3, rasterio 1.5.0 |

전체 시계열은 2026-08-07 Earth Engine 조회 기준 2012-04부터 2026-04까지 169개월입니다. 이 중 북한 경계 안에 `cf_cvg > 0` 격자가 하나 이상 존재하는 147개월을 수집했으며, 관측 격자가 0개인 22개월은 목록에서 제외했습니다. 월별 compact JSON.gz 전체 크기는 801,940,220바이트, 약 764.8MiB입니다.

### 부분 관측 월 검증

147개월의 유효 격자 수를 전수 집계한 결과, 기준 최대치는 749,224개이고 중앙값은 749,220개입니다.

| 관측 상태 | 기준 | 월 수 |
| --- | --- | ---: |
| full | 최대 격자의 90% 이상 | 127 |
| partial | 50% 이상 90% 미만 | 5 |
| sparse | 50% 미만 | 15 |
| no coverage | 북한 내 cf_cvg > 0 격자 0개 | 22, 목록 제외 |

화면에서 일부 지역만 보이는 월은 저장 또는 전송 누락이 아닙니다. 대표적으로 2017-07은 저장 파일 1,166개에 대해 Earth Engine 원본 재집계 1,074개, 2020-05는 저장 1,404개에 대해 원본 1,243개로 같은 희소 패턴이 확인됐습니다. 차이는 Earth Engine `reduceRegion`과 다운로드 GeoTIFF의 격자 정렬·경계 래스터화 차이입니다.

공식 데이터 설명도 월 합성 영상은 구름과 고위도 여름철 태양광 때문에 양질의 관측 범위가 부족할 수 있고, stray light·번개·달빛·구름 영향을 받은 관측을 평균 전에 제외한다고 명시합니다. 따라서 플레이어는 없는 영역을 0 조명으로 채우지 않고 원본 `cf_cvg > 0` 영역만 표시합니다. 월 목록의 `◐`와 주황·적색 테두리는 각각 부분·희소 관측 월을 뜻합니다.

월 전환 시에는 좌표 키로 이전 월과 새 월의 격자를 한 번 정렬한 뒤, 하나의 `GridCellLayer`에서 `getElevation`과 `getColor`를 1.5초 동안 GPU 보간합니다. 따라서 화면 전체 투명도를 바꾸지 않고 각 막대의 `log1p(avg_rad)` 높이와 조명도 색상이 이전 값에서 새 값으로 직접 변합니다. 새로 관측된 격자는 높이 0·투명 색상에서 자라고, 관측이 사라진 격자는 0으로 줄어듭니다. Top 3 `TextLayer`는 `characterSet: 'auto'`와 한글 폰트 스택을 사용하며 `도시 이름 표시` 체크박스를 켰을 때만 순위와 도시명을 표시합니다.

### 월별 Top 3 도시 표기

`build_top3.py`는 각 월의 `avg_rad`가 큰 격자 3개를 원값 기준으로 선택하고, GeoNames 북한 국가 추출본의 도시 중 가장 가까운 곳을 연결합니다. 도시 후보는 인구 1만 이상 또는 행정 중심지이며 한글 대체명이 있으면 한글을 우선 사용합니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/python build_top3.py --workers 3
~~~

결과는 `output/top3_locations.json`에 147개월분이 기록됩니다. 지도에는 실제 상위 격자 좌표에 순위별 색상 점과 `순위. 최근접 도시` 라벨만 표시하고 `avg_rad`는 툴팁에서 확인합니다. 같은 도시 주변의 여러 격자가 Top 3이면 가장 높은 순위 하나만 지도에 남기며, 다음 서로 다른 도시의 원래 순위는 다시 매기지 않고 그대로 유지합니다.

도시명 자료는 GeoNames `KP.zip` 국가 추출본을 사용하며 CC BY 4.0 조건을 따릅니다. GeoNames 위치는 최근접 도시 안내용이며 북한 행정구역의 공식 판정이나 해당 격자가 도시 내부에 있다는 의미는 아닙니다.

정상 실행 로그는 다음 형태입니다.

~~~text
[1/4] 2024-01 VIIRS 영상과 북한 경계를 준비합니다.
[2/4] 약 463.83m GeoTIFF를 내려받습니다.
[3/4] cf_cvg > 0 격자와 log1p 높이·색상을 계산합니다.
[4/4] 740,776개 북한 격자를 결과로 기록합니다.
압축 데이터: .../output/data/north_korea_viirs_2024-01.json.gz (5.0 MiB)
~~~

## 홈페이지에서 바로 확인

저장소의 메인 ASGI 애플리케이션에 PoC 05 전용 화면이 연결되어 있습니다. 홈페이지와 큰 창은 동일한 공통 플레이어를 사용하고, 선택한 북한 월별 gzip만 스트리밍해 표시합니다.

현재 메인 화면이 서비스로 실행 중이라면 저장소 루트에서 재시작합니다.

~~~bash
cd /home/ubuntu/apps/myservice
sudo systemctl restart myservice
~~~

브라우저 접근 주소:

~~~text
# 홈페이지에서 PoC 05가 선택된 화면
https://www.minslab.kr/poc?project=north-korea-night-lights

# 지도만 크게 보는 전용 화면
https://www.minslab.kr/poc/north-korea-night-lights/map
~~~

로컬 서버 기준으로 확인하려면 도메인을 `http://127.0.0.1:8000`으로 바꿉니다.

~~~bash
curl -I http://127.0.0.1:8000/poc/north-korea-night-lights/map
~~~

정상이면 `HTTP/1.1 200 OK`와 `content-type: text/html; charset=utf-8`가 표시됩니다. 이 응답은 약 12KiB의 공통 `player.html`이며, 149MiB 안팎의 기존 단일 월 HTML과 크기가 다릅니다. 플레이어가 없으면 지도 경로가 404를 반환하고, 월별 gzip이 없으면 플레이어 안에 `생성된 북한 월별 데이터가 없습니다.`가 표시됩니다.

### 시계열 목록과 자동 재생

홈페이지와 큰 창 플레이어는 `output/data/north_korea_viirs_YYYY-MM.json.gz` 형식의 북한 한정 압축 파일을 자동 검색해 월별 목록으로 표시합니다. 월 버튼을 누르면 해당 지도로 이동하며, **재생** 버튼을 누르면 1.5초마다 다음 월을 선택합니다. 마지막 월 다음에는 첫 월로 돌아가며 정지 버튼을 누를 때까지 무한 반복합니다. `도시 이름 표시`는 기본 해제이며 체크한 경우에만 중복 도시를 제거한 `순위. 도시명` 라벨을 표시합니다.

월별 목록 API와 지도 주소는 다음 형식입니다.

~~~text
GET /api/poc/north-korea-night-lights/maps
GET /api/poc/north-korea-night-lights/data/YYYY-MM
GET /poc/north-korea-night-lights/map
~~~

큰 창 주소에도 동일한 월 목록과 재생·정지 버튼이 포함됩니다. 플레이어는 현재 월과 다음 월을 미리 캐시하며, 여러 월을 생성하면 서비스 재시작 없이 다음 목록 조회부터 자동 반영됩니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/python collect_all.py --workers 3
~~~

개별 월만 추가하려면 `generate_map.py --month YYYY-MM --data-output output/data/north_korea_viirs_YYYY-MM.json.gz --no-html`을 실행합니다. 재생 선택과 막대 보간은 1.5초 간격이며 실제 표시 시점은 최초 데이터 다운로드와 브라우저 GPU 처리 속도의 영향을 받습니다.

## 최소 재현 절차: 월 1개를 홈페이지에서 확인

아래 절차는 새 환경에서 `2024-01` 한 달의 compact JSON.gz, Top 3 도시 정보, 공통 플레이어와 홈페이지 연결까지 재현하는 기준 경로입니다. `/home/ubuntu/apps/myservice`는 자신의 저장소 절대경로로 바꿉니다.

### 1. 수집 환경 설치

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
~~~

저장소 루트 `.env`에 자신의 Earth Engine 실행 프로젝트 ID를 기록합니다. API 키나 JSON 개인키는 필요하지 않습니다.

~~~dotenv
GEE_PROJECT=YOUR_GOOGLE_CLOUD_PROJECT_ID
~~~

### 2. OAuth 인증 및 권한 확인

원격 서버라면 notebook 인증을 사용합니다. 브라우저와 명령 실행 환경이 같으면 `--auth_mode=notebook`을 생략할 수 있습니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/earthengine authenticate --force --auth_mode=notebook
.venv/bin/earthengine set_project YOUR_GOOGLE_CLOUD_PROJECT_ID
.venv/bin/python -c "import ee; ee.Initialize(project='YOUR_GOOGLE_CLOUD_PROJECT_ID'); print(ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG').filterDate('2024-01-01','2024-02-01').size().getInfo())"
~~~

인증 명령에서는 `Successfully saved authorization token.`, 프로젝트 저장에서는 `Successfully saved project id`가 각각 출력되어야 합니다. 마지막 명령은 0보다 큰 정수를 출력해야 합니다.

### 3. 공통 플레이어용 월 데이터 생성

`--no-html`만 단독으로 쓰면 오류가 나므로 반드시 `--data-output`을 함께 지정합니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/python generate_map.py \
  --month 2024-01 \
  --data-output output/data/north_korea_viirs_2024-01.json.gz \
  --no-html
~~~

Top 3 격자에 최근접 도시를 연결합니다. 첫 실행은 GeoNames `KP.zip`을 자동 다운로드합니다.

~~~bash
.venv/bin/python build_top3.py --workers 1
~~~

### 4. 메인 ASGI 애플리케이션 실행

메인 홈페이지용 Python 환경이 아직 없다면 저장소 루트에서 설치합니다.

~~~bash
cd /home/ubuntu/apps/myservice
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
~~~

이미 `myservice.service`로 운영 중인 서버에서는 새 프로세스를 띄우지 않고 다음 명령만 실행합니다.

~~~bash
cd /home/ubuntu/apps/myservice
sudo systemctl restart myservice
systemctl status myservice --no-pager
~~~

### 5. 브라우저와 API 확인

~~~text
http://127.0.0.1:8000/poc?project=north-korea-night-lights
http://127.0.0.1:8000/poc/north-korea-night-lights/map
~~~

~~~bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/poc/north-korea-night-lights/maps
curl -I http://127.0.0.1:8000/api/poc/north-korea-night-lights/data/2024-01
~~~

정상 기준은 health의 `status=healthy`, 월 목록의 `2024-01`, 데이터 응답의 `200 OK`와 `content-encoding: gzip`입니다.

원격 서버라면 로컬 PC에서 포트를 전달한 뒤 같은 주소를 엽니다.

~~~bash
ssh -L 8000:127.0.0.1:8000 USER@SERVER
~~~

### 6. 여러 월 또는 전체 시계열 생성

먼저 3개월만 직렬 수집해 할당량과 다운로드를 확인하는 것을 권장합니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/python collect_all.py --start 2024-01 --end 2024-03 --workers 1
.venv/bin/python build_top3.py --workers 1
~~~

문제가 없으면 기존 정상 파일을 자동으로 건너뛰는 전체 수집을 실행합니다. `--workers 3`은 이 서버에서 검증한 값이며 Earth Engine 할당량 오류가 나면 1로 낮춥니다.

~~~bash
.venv/bin/python collect_all.py --workers 3
.venv/bin/python build_top3.py --workers 3
~~~

월별 gzip과 `top3_locations.json`은 API 요청 때 다시 검색되므로 실행 중인 서비스의 재시작 없이도 새 목록이 반영됩니다. 브라우저가 이미 열려 있으면 페이지를 새로고침합니다.

## 처리 흐름

~~~text
USDOS/LSIB_SIMPLE/2017
  └─ country_co = KN으로 북한 경계 선택

NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG
  └─ YYYY-MM 시작일 이상, 다음 달 시작일 미만으로 한 장 선택

두 자료 결합
  └─ avg_rad, cf_cvg 밴드 선택
  └─ cf_cvg > 0 마스크
  └─ 북한 경계 clip
  └─ 약 463.83m, EPSG:4326, 2밴드 GeoTIFF 다운로드

로컬 변환
  └─ rasterio로 avg_rad와 cf_cvg 읽기
  └─ 결측값 및 cf_cvg <= 0 제거
  └─ 각 래스터 셀의 좌하단 위경도 계산
  └─ log1p 높이와 방사휘도 색상 계산

시계열 출력
  └─ 월별 compact JSON.gz, 북한 유효 격자만 기록
  └─ 공통 deck.gl GridCellLayer 플레이어
  └─ 북한 경계 GeoJsonLayer
  └─ Carto Dark Matter TileLayer 배경지도
  └─ 범례, 툴팁, 회전·확대 컨트롤
  └─ 월 목록, 1.5초 간격 무한 반복 재생 및 GPU 막대 보간
~~~

## 데이터 출처

### VIIRS 월별 야간조명

- 컬렉션: NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG
- 공식 문서: [VIIRS Nighttime Day/Night Band Monthly V1](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMCFG)
- 공칭 픽셀 크기: 463.83m

사용 밴드:

| 밴드 | 의미 | 사용 방법 |
| --- | --- | --- |
| avg_rad | 월평균 DNB 방사휘도, nW/sr/cm² | 막대 높이, 색상, 툴팁 |
| cf_cvg | 해당 합성 픽셀에 포함된 cloud-free 관측 횟수 | 0보다 큰 셀만 선택 |

VIIRS V1에는 오로라, 화재, 선박 등 일부 일시적 광원과 배경 잡음이 남을 수 있습니다. 따라서 밝기 하나만으로 전력 공급이나 경제활동을 단정하면 안 됩니다.

### 북한 경계

- 컬렉션: USDOS/LSIB_SIMPLE/2017
- 선택 필드: country_co
- 선택 값: KN
- 공식 문서: [LSIB 2017 Simplified](https://developers.google.com/earth-engine/datasets/catalog/USDOS_LSIB_SIMPLE_2017)

LSIB 경계는 미국 공공영역 자료이지만 해안선과 경계 위치에 데이터셋 고유 오차가 있습니다.

### 3D 레이어

- 레이어: GridCellLayer
- 공식 문서: [deck.gl GridCellLayer](https://deck.gl/docs/api-reference/layers/grid-cell-layer)
- getPosition: 각 격자의 좌하단 위경도
- cellSize: 기본 463.83m
- getElevation: 로그 보정값
- getColor: 로그 방사휘도를 고정 팔레트에 보간한 RGB

GridCellLayer는 입력 행마다 한 개의 사각 기둥을 생성합니다. GridLayer처럼 점을 다시 집계하지 않으므로 VIIRS 픽셀 하나와 화면 기둥 하나가 대응합니다.

## 사전 준비

필수 조건:

- Python 3.10 이상
- Google 계정
- Google Cloud 프로젝트
- 해당 프로젝트의 Earth Engine API 활성화
- Earth Engine 상업용 또는 비상업용 프로젝트 등록
- 데이터 수집 시 인터넷 연결
- 결과 배경지도 로드 시 인터넷 연결
- WebGL을 지원하는 최신 브라우저
- 실제 생성 시 여유 메모리와 디스크 공간

이 환경에서 사용한 Python은 3.12이며 다음 버전 조합으로 실행했습니다.

| 패키지 | 검증 버전 |
| --- | --- |
| earthengine-api | 1.7.38 |
| numpy | 2.5.1 |
| pandas | 2.3.3 |
| pydeck | 0.9.3 |
| python-dotenv | 1.2.2 |
| rasterio | 1.5.0 |

requirements.txt는 호환 범위를 지정하므로 새 환경에서도 같은 메이저 버전 안에서 설치됩니다.

## 1. Google Cloud와 Earth Engine 프로젝트 준비

Google Cloud Console에서 실행 프로젝트를 만들거나 기존 프로젝트를 선택합니다.

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 선택합니다.
2. 프로젝트 대시보드의 프로젝트 ID를 확인합니다.
3. Earth Engine API를 활성화합니다.
4. [Earth Engine 액세스 안내](https://developers.google.com/earth-engine/guides/access)에 따라 프로젝트를 등록합니다.
5. 비상업 사용이면 비상업 프로젝트 등록 상태를 확인합니다.

주의:

- 프로젝트 이름이 아니라 프로젝트 ID를 사용합니다.
- 프로젝트 번호도 아닙니다.
- 이 저장소에서 검증한 실행 프로젝트 ID는 minslab-504801입니다.
- GGE_API_KEY, GOOGLE_CLOUD_API_KEY 같은 일반 API 키는 Earth Engine Python 연산 인증을 대신하지 않습니다.

## 2. 환경변수 설정

저장소 루트 파일에 실행 프로젝트 ID만 넣습니다.

파일:

~~~text
/home/ubuntu/apps/myservice/.env
~~~

내용:

~~~dotenv
GEE_PROJECT=minslab-504801
~~~

다른 환경에서는 자신의 프로젝트 ID로 바꿉니다.

~~~dotenv
GEE_PROJECT=YOUR_GOOGLE_CLOUD_PROJECT_ID
~~~

generate_map.py는 다음 두 파일을 순서대로 읽습니다.

1. 저장소 루트 .env
2. PoC/05-north-korea-night-lights/.env

이미 셸에 설정된 값은 .env로 덮어쓰지 않습니다.

프로젝트 결정 우선순위:

~~~text
--project 실행 인자
→ GEE_PROJECT
→ GOOGLE_CLOUD_PROJECT
→ Earth Engine 또는 ADC의 기본 프로젝트
~~~

OAuth 승인 코드와 refresh token은 .env에 넣지 않습니다. Earth Engine CLI가 사용자 홈 아래에 저장합니다.

~~~text
~/.config/earthengine/credentials
~~~

## 3. Python 환경 설치

PoC 폴더로 이동해 전용 가상환경을 만듭니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
~~~

설치 확인:

~~~bash
.venv/bin/python generate_map.py --help
.venv/bin/earthengine --help
~~~

가상환경을 activate하지 않아도 위와 같이 .venv/bin 경로를 직접 사용하면 항상 동일한 인터프리터가 실행됩니다.

## 4. 사용자 OAuth 인증

서비스 계정 JSON보다 사용자 OAuth 인증을 권장합니다. JSON 개인키는 저장소, 채팅, 업로드 화면에 올리지 않습니다.

### 로컬 PC에서 인증

브라우저와 Python이 같은 PC에서 실행된다면:

~~~bash
.venv/bin/earthengine authenticate --force
~~~

### 원격 서버에서 notebook 방식 인증

브라우저는 로컬 PC에 있고 코드는 원격 서버에서 실행된다면:

~~~bash
.venv/bin/earthengine authenticate --force --auth_mode=notebook
~~~

진행 순서:

1. 터미널에 출력된 최신 인증 링크를 엽니다.
2. 올바른 Google 계정을 선택합니다.
3. Notebook Authenticator의 인증 프로젝트를 선택합니다.
4. Generate Token을 누릅니다.
5. 권한 요청을 승인합니다.
6. 마지막 화면의 일회용 승인 코드를 복사합니다.
7. 동일한 터미널 명령이 기다리는 Enter verification code 입력란에 즉시 붙여넣습니다.
8. 아래 성공 문구를 확인합니다.

~~~text
Successfully saved authorization token.
~~~

승인 코드는 채팅, README, .env에 기록하지 않습니다. 승인 코드는 한 번만 사용할 수 있고 인증 명령의 PKCE 검증값과 짝을 이루므로, 링크를 만든 명령과 코드를 붙여넣는 명령이 같아야 합니다.

### 실행 프로젝트 저장

OAuth 인증 후 실제 VIIRS 연산에 사용할 프로젝트를 저장합니다.

~~~bash
.venv/bin/earthengine set_project minslab-504801
~~~

정상 결과:

~~~text
Successfully saved project id
~~~

프로젝트 저장 성공은 OAuth 토큰 저장 성공과 다릅니다. 두 성공 문구를 모두 확인해야 합니다.

### 인증 확인

공개 VIIRS 컬렉션을 한 번 읽어 인증과 프로젝트 권한을 동시에 확인합니다.

~~~bash
.venv/bin/python -c "import ee; ee.Initialize(project='minslab-504801'); print(ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG').filterDate('2024-01-01','2024-02-01').size().getInfo())"
~~~

정상이라면 0보다 큰 이미지 수가 출력됩니다.

## 5. 실제 HTML 생성

PoC 폴더에서 실행합니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/05-north-korea-night-lights
.venv/bin/python generate_map.py --month 2024-01
~~~

.env를 사용하지 않고 프로젝트를 직접 지정할 수도 있습니다.

~~~bash
.venv/bin/python generate_map.py \
  --project minslab-504801 \
  --month 2024-01 \
  --output output/north_korea_viirs_2024-01.html
~~~

실행은 다음 네 단계로 진행됩니다.

1. Earth Engine에서 대상 월과 북한 경계를 확인합니다.
2. avg_rad와 cf_cvg가 포함된 GeoTIFF를 임시 폴더에 내려받습니다.
3. cf_cvg > 0 필터, 로그 높이, 색상을 계산합니다.
4. 모든 유효 격자를 단일 HTML로 직렬화합니다.

중간 GeoTIFF는 기본적으로 임시 폴더에서 삭제됩니다. 원본을 남기려면:

~~~bash
.venv/bin/python generate_map.py \
  --month 2024-01 \
  --save-raster output/north_korea_viirs_2024-01.tif
~~~

## 6. 결과 화면 열기

결과 파일:

~~~text
output/north_korea_viirs_2024-01.html
~~~

파일을 직접 더블클릭해도 되지만 HTTP 서버로 여는 것이 안정적입니다.

~~~bash
.venv/bin/python -m http.server 8080 --bind 127.0.0.1 --directory output
~~~

브라우저:

~~~text
http://127.0.0.1:8080/north_korea_viirs_2024-01.html
~~~

화면 조작:

- 왼쪽 드래그: 지도 이동
- 오른쪽 드래그 또는 환경별 회전 제스처: 3D 회전
- 휠 또는 트랙패드: 확대·축소
- 격자 hover: avg_rad, cf_cvg, log1p 값, 좌하단 좌표 확인

기본 HTML에는 deck.gl 실행 번들이 포함됩니다. Carto 배경지도 타일은 인터넷에서 불러오므로 배경지도까지 완전한 오프라인은 아닙니다.

메인 홈페이지 서비스에서 확인하려면 별도 HTTP 서버 대신 아래 경로를 사용할 수 있습니다.

~~~text
/poc?project=north-korea-night-lights
/poc/north-korea-night-lights/map
~~~

## 7. 다른 월 재생성

YYYY-MM 형식으로 월만 바꿉니다.

~~~bash
.venv/bin/python generate_map.py --month 2023-12
.venv/bin/python generate_map.py --month 2024-02
~~~

결과:

~~~text
output/north_korea_viirs_2023-12.html
output/north_korea_viirs_2024-02.html
~~~

월간 비교에는 모든 실행에서 동일한 값을 사용합니다.

~~~bash
.venv/bin/python generate_map.py \
  --month 2024-02 \
  --scale 463.83 \
  --color-max 60 \
  --elevation-scale 5000
~~~

월마다 자동 색상 범위를 사용하지 않고 고정 상한을 쓰는 이유는 같은 방사휘도가 모든 월에서 같은 색과 높이를 갖게 하기 위해서입니다.

## 높이 계산

원본 avg_rad는 툴팁에 그대로 보존합니다.

화면 계산:

~~~text
visual_radiance = log1p(max(avg_rad, 0))
display_height_m = visual_radiance × elevation_scale
~~~

기본 elevation-scale은 5000입니다.

VIIRS V1에는 음수 배경 잡음이 있고 자료 카탈로그상 -1보다 작은 값도 가능합니다. 이 값에 log1p를 그대로 적용하면 정의되지 않는 결과가 생기므로 높이와 색상 계산에만 0 하한을 둡니다.

예:

| avg_rad | 시각 계산 입력 | log1p 값 |
| ---: | ---: | ---: |
| -1.2 | 0 | 0 |
| 0 | 0 | 0 |
| 1 | 1 | 약 0.693 |
| 10 | 10 | 약 2.398 |
| 60 | 60 | 약 4.111 |

## 색상 계산

높이와 동일한 로그 방사휘도를 0부터 log1p(color-max)까지 정규화한 뒤 다음 팔레트 사이를 선형 보간합니다.

~~~text
어두운 남색
→ 청색
→ 청록
→ 녹색
→ 황색
→ 주황
→ 밝은 백색
~~~

기본 color-max는 avg_rad 60입니다. 60보다 큰 값은 가장 밝은 색으로 포화되지만 원본 수치는 툴팁에 유지됩니다.

## CLI 옵션

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| --month | 2024-01 | 대상 월, YYYY-MM |
| --project | 환경설정 | Earth Engine 실행 프로젝트 ID |
| --output | output/north_korea_viirs_YYYY-MM.html | 결과 HTML 경로 |
| --data-output | 없음 | 공통 플레이어용 북한 compact JSON.gz 경로 |
| --no-html | 꺼짐 | 월별 HTML을 생략하고 압축 데이터만 생성 |
| --scale | 463.83 | Earth Engine 요청 및 GridCell 크기, 미터 |
| --color-max | 60 | 색상 포화 상한 avg_rad |
| --elevation-scale | 5000 | 로그 높이에 곱하는 시각 배율 |
| --save-raster | 없음 | 중간 2밴드 GeoTIFF 보존 경로 |
| --cdn | 꺼짐 | deck.gl을 내장하지 않고 CDN에서 로드 |

도움말:

~~~bash
.venv/bin/python generate_map.py --help
~~~

고해상도 결과가 브라우저에서 너무 무거우면 시험용으로 scale을 늘립니다.

~~~bash
.venv/bin/python generate_map.py \
  --month 2024-01 \
  --scale 750 \
  --cdn \
  --output output/north_korea_viirs_2024-01-preview.html
~~~

이 명령은 빠른 미리보기용이며 원래 약 463.83m 결과와 해상도가 다릅니다.

## 구현 함수

| 함수 | 역할 |
| --- | --- |
| load_runtime_environment | 루트 및 PoC .env 로딩 |
| parse_month | YYYY-MM을 월 시작일과 다음 달 시작일로 변환 |
| initialize_earth_engine | OAuth 또는 ADC로 ee.Initialize 실행 |
| prepare_month_image | 북한 경계, 월 영상, cf_cvg 마스크 구성 |
| download_geotiff | Earth Engine getDownloadURL로 2밴드 GeoTIFF 다운로드 |
| raster_to_frame | 래스터 유효 셀을 pydeck 입력 DataFrame으로 변환 |
| _interpolate_colors | 로그값을 고정 RGB 팔레트에 보간 |
| build_map_html | GridCellLayer, 경계, 툴팁, 범례를 단일 HTML로 기록 |
| build_map_data | 북한 유효 격자를 공통 플레이어용 compact JSON.gz로 기록 |

`collect_all.py`는 Earth Engine 컬렉션의 전체 월 목록을 조회하고, 기존의 정상 gzip은 건너뛰면서 여러 월을 병렬 수집합니다. 출력은 프로세스별 임시 파일에 먼저 기록한 뒤 원자적으로 교체하므로 중단 후에도 안전하게 재실행할 수 있습니다.

Earth Engine 다운로드 응답이 GeoTIFF 또는 ZIP 중 어느 형식이든 처리합니다. ZIP이면 내부 첫 GeoTIFF만 안전하게 복사합니다.

국외 또는 무관측 영역은 -9999로 명시해 GeoTIFF 마스크 메타데이터가 손실되어도 로컬 필터에서 제외되게 합니다.

## 결과 검증

### Python 문법

~~~bash
python3 -m py_compile generate_map.py collect_all.py build_top3.py
~~~

### compact JSON.gz 내용

다음 검사는 파일이 정상 gzip인지, 북한 범위와 `cf_cvg > 0` 조건이 기록됐는지, 행 개수와 메타데이터가 일치하는지 확인합니다.

~~~bash
.venv/bin/python -c "import gzip,json; p='output/data/north_korea_viirs_2024-01.json.gz'; d=json.load(gzip.open(p,'rt',encoding='utf-8')); assert d['month']=='2024-01'; assert d['filter']=='cf_cvg > 0'; assert d['columns']==['lon','lat','rad','cvg','log','r','g','b']; assert d['count']==len(d['data'])>0; assert all(row[3]>0 for row in d['data']); print({'month':d['month'],'count':d['count'],'scale_m':d['scale_m'],'first_row':d['data'][0]})"
~~~

2024-01 기본 설정의 예상 `count`는 740,776입니다. Earth Engine 자료 개정이나 경계 래스터화 환경에 따라 숫자가 달라질 수 있으므로, 핵심 불변조건은 0보다 큰 개수와 모든 행의 `cvg > 0`입니다.

### Top 3 도시 인덱스

~~~bash
.venv/bin/python -c "import json; d=json.load(open('output/top3_locations.json',encoding='utf-8')); rows=d['months']['2024-01']; assert len(rows)==3; print([(x['rank'],x['city'],x['avg_rad']) for x in rows])"
~~~

실제 지도에서는 같은 도시가 여러 순위에 있으면 가장 높은 순위 라벨 하나만 남습니다. manifest에는 원본 Top 3를 보존하므로 위 검사는 항상 3개를 기대합니다.

### 플레이어 전환 설정

~~~bash
rg -n "alignPayload|duration:1500|showCityLabels=false|setInterval.*1500" player.html
~~~

네 문자열이 모두 확인되면 월별 좌표 정렬, 높이·색상의 1.5초 GPU 보간, 도시명 기본 숨김, 1.5초 간격 재생이 포함된 것입니다.

### 홈페이지 API

메인 ASGI 애플리케이션을 실행한 상태에서 확인합니다.

~~~bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/poc/north-korea-night-lights/maps | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); assert d['interval_ms']==1500; assert d['maps']; print({'months':len(d['maps']),'default_month':d['default_month'],'interval_ms':d['interval_ms']})"
curl -I http://127.0.0.1:8000/poc/north-korea-night-lights/map
~~~

### 프로젝트 메타데이터

~~~bash
python3 -c "import json; print(json.load(open('project.json', encoding='utf-8'))['id'])"
~~~

예상값:

~~~text
north-korea-night-lights
~~~

### 생성 파일

~~~bash
ls -lh output/north_korea_viirs_2024-01.html
~~~

실제 검증 결과:

~~~text
약 149M
~~~

HTML 핵심 문자열 확인:

~~~bash
.venv/bin/python -c "from pathlib import Path; p=Path('output/north_korea_viirs_2024-01.html'); s=p.read_text(encoding='utf-8'); print({x:x in s for x in ['GridCellLayer','viirs-grid-cells','map-info','cf_cvg']})"
~~~

모든 값이 True여야 합니다. 이 검사는 150MiB 안팎의 HTML 전체를 메모리에 읽으므로 메모리가 부족한 장비에서는 생략합니다.

## 인증 문제 해결

### Please authorize access to your Earth Engine account

OAuth 토큰이 없거나 저장에 실패한 상태입니다.

~~~bash
.venv/bin/earthengine authenticate --force --auth_mode=notebook
~~~

Successfully saved project id만으로는 인증 성공이 아닙니다. Successfully saved authorization token 문구가 반드시 있어야 합니다.

### Cannot authenticate: Invalid request

승인 코드가 만료됐거나 다른 인증 명령의 PKCE 검증값과 짝이 맞지 않는 경우입니다.

1. 인증 명령을 --force로 새로 실행합니다.
2. 새 명령이 출력한 최신 링크만 엽니다.
3. 새 승인 코드를 발급합니다.
4. 동일한 명령의 입력란에 즉시 붙여넣습니다.
5. 인증 명령을 코드 발급과 입력 사이에 다시 실행하지 않습니다.

### Project has an incompatible OAuth2 Client configuration

Notebook Authenticator에서 선택한 인증 프로젝트에 이미 호환되지 않는 OAuth 클라이언트 구성이 있습니다.

해결:

1. OAuth Client ID가 없는 빈 Google Cloud 프로젝트를 인증 전용으로 만듭니다.
2. Notebook Authenticator에서 그 프로젝트를 선택합니다.
3. 인증용 프로젝트에는 Owner, Editor 또는 OAuth Config Editor 권한이 필요합니다.
4. 실제 Earth Engine 연산은 기존 minslab-504801 프로젝트를 계속 사용합니다.

인증 프로젝트와 실행 프로젝트는 달라도 됩니다. 자세한 내용은 [Earth Engine 인증 프로젝트 문서](https://developers.google.com/earth-engine/guides/auth#authentication-projects)를 확인합니다.

### Caller does not have required permission to use project

서비스 계정 방식을 사용하는 경우 실행 주체에 최소한 다음 권한이 필요할 수 있습니다.

- Service Usage Consumer
- Earth Engine Resource Viewer

이 PoC의 현재 재현 절차는 서비스 계정 JSON이 아니라 사용자 OAuth를 사용합니다.

### Earth Engine API has not been used or is disabled

Google Cloud Console에서 실행 프로젝트의 Earth Engine API를 활성화하고 Earth Engine 프로젝트 등록 상태를 확인합니다.

### 대상 월 영상이 없습니다

VIIRS 컬렉션 제공 범위를 벗어난 월이거나 아직 해당 월 합성이 게시되지 않은 경우입니다. 공식 데이터 카탈로그에서 제공 범위를 확인합니다.

### 다운로드 크기 또는 10,000픽셀 제한 오류

Earth Engine 동기 다운로드 API는 요청 크기와 격자 차원 제한이 있습니다. 북한 범위의 463.83m 결과는 검증됐지만 설정이나 경계가 바뀌면 제한을 넘을 수 있습니다.

우선 scale을 500, 750 또는 1000으로 늘립니다.

~~~bash
.venv/bin/python generate_map.py --month 2024-01 --scale 750
~~~

원본 해상도를 유지해야 하면 Earth Engine Batch Export와 Cloud Storage 방식으로 전환합니다.

### 지도가 느리거나 브라우저가 멈춥니다

기존 단일 월 HTML은 2024-01 기준 약 149MiB이므로 재현 확인 외에는 공통 플레이어 사용을 권장합니다. 시계열 플레이어의 gzip은 월별 약 0.5~8.6MiB지만 압축 해제 후에는 최대 약 75만 개 JavaScript 행과 GPU 버퍼가 필요합니다.

- 하드웨어 가속을 켠 최신 데스크톱 브라우저를 사용합니다.
- 다른 대형 지도·영상 탭을 닫고 다시 확인합니다.
- 플레이어는 현재·다음 월을 포함해 최대 2개월만 캐시하므로 전체 시계열을 한 번에 메모리에 올리지 않습니다.
- 1.5초 보간은 GPU에서 실행되지만 좌표 정렬은 월 전환마다 CPU에서 한 번 수행되어 저사양 장비에서는 짧은 멈춤이 생길 수 있습니다.
- 시험용 데이터는 `--scale 750` 또는 `--scale 1000`으로 다시 생성합니다. 서로 다른 scale로 만든 월을 한 목록에서 비교하지 않습니다.
- 기존 단일 HTML이 필요하면 `--cdn`으로 deck.gl 번들 내장을 생략해 파일 크기를 줄일 수 있습니다.

## 보안

- GGE_API_KEY 또는 일반 Google API 키는 Earth Engine OAuth 인증을 대신하지 않습니다.
- 서비스 계정 JSON에는 개인키가 있으므로 저장소, 채팅, 티켓, 공유 드라이브에 올리지 않습니다.
- 이 PoC 폴더의 .gitignore는 project.json을 제외한 루트 JSON, PEM, P12 파일을 차단합니다.
- OAuth 승인 코드는 일회용이지만 채팅에 공유하지 않습니다.
- refresh token이 담긴 ~/.config/earthengine/credentials를 커밋하거나 복사하지 않습니다.
- 저장소 루트 .env는 Git 제외 상태를 유지합니다.
- 키가 한 번이라도 외부에 업로드됐다면 Git에서 지우는 것만으로 충분하지 않으며 Google Cloud에서 해당 키를 폐기합니다.

## 시계열 보간 구현과 성능

월별 원본 배열은 `cf_cvg > 0`인 셀만 포함하므로 관측이 빠진 위치 이후의 배열 인덱스가 서로 달라집니다. 대표 월의 같은 인덱스 좌표 일치율은 2.6%까지 낮아 단순 인덱스 보간을 쓰면 서로 다른 지역의 밝기가 연결됩니다.

플레이어는 다음 순서로 이를 처리합니다.

1. `cellKey`가 6자리 위경도를 안전한 정수 키로 변환합니다.
2. 월 전환 때 `alignPayload`가 새 월을 `Map`으로 한 번 인덱싱합니다.
3. 공통 좌표는 이전 배열과 같은 순서에 배치하고, 새 좌표는 배열 끝에 추가합니다.
4. 새 월에 없는 이전 좌표에는 전환 전용 높이 0·알파 0 셀을 둡니다.
5. ID가 고정된 하나의 `GridCellLayer`에 새 데이터를 전달합니다.
6. deck.gl `transitions`가 `getElevation`과 `getColor`를 smoothstep 곡선으로 1.5초 동안 GPU 보간합니다.

전환용 0 셀은 원본 관측으로 저장되거나 API의 유효 격자 수에 포함되지 않습니다. 월별 gzip에는 계속 `cf_cvg > 0` 자료만 존재합니다. 새로 관측된 셀은 0에서 자라고, 관측이 사라진 셀은 0으로 줄어든 뒤 투명해집니다.

최대 약 749,224개 셀을 JavaScript에서 매 프레임 새 배열로 계산하면 부담이 크므로 사용하지 않습니다. CPU 좌표 정렬은 월 전환당 한 번만 수행하고 1.5초 애니메이션은 GPU 속성 전환에 맡깁니다. 메모리 사용을 제한하기 위해 월 데이터 캐시는 최대 2개만 유지합니다.

2026-03→2026-04 검증에서는 이전 749,002개, 현재 749,193개 중 748,983개가 같은 좌표로 연결됐고 키 충돌은 없었습니다. 신규 210개는 0에서 성장하고 누락 19개는 0으로 축소됐으며, 정렬 후 합집합은 749,212개였습니다.

`cf_cvg > 0`은 최소 유효 조건일 뿐 모든 월의 품질이 같다는 뜻은 아닙니다. 엄격한 시계열 분석에서는 최소 관측 횟수 필터와 월별 관측 횟수 차이를 함께 검토해야 합니다.

## 파일 구성

~~~text
PoC/05-north-korea-night-lights/
├── .gitignore
├── README.md
├── generate_map.py
├── collect_all.py
├── build_top3.py
├── player.html
├── project.json
├── requirements.txt
├── .venv/                              # 로컬 실행환경, Git 제외
└── output/                             # 생성 산출물, Git 제외
    ├── north_korea_viirs_YYYY-MM.html  # 기존 단일 월 HTML
    ├── top3_locations.json             # 월별 Top 3와 최근접 도시 manifest
    ├── geonames/
    │   └── KP.zip                      # GeoNames 북한 국가 추출본
    └── data/
        └── north_korea_viirs_YYYY-MM.json.gz  # 북한 한정 시계열
~~~

저장소 루트:

~~~text
/home/ubuntu/apps/myservice/.env         # GEE_PROJECT, Git 제외
~/.config/earthengine/credentials       # OAuth 토큰, 저장소 밖
~~~

## 제한사항

- VIIRS Monthly V1은 모든 일시적 광원이나 배경 잡음을 제거한 확정 통계가 아닙니다.
- cf_cvg가 1 이상이어도 관측 횟수가 적으면 불확실성이 큽니다.
- LSIB 경계는 제공 기관의 정치적·지리적 표현과 위치 오차를 따릅니다.
- EPSG:4326의 공칭 463.83m 격자와 Web Mercator 화면의 사각 셀은 위도에 따른 표현 차이가 있을 수 있습니다.
- 기존 단일 HTML 방식은 재현용으로 유지하지만, 전체 시계열 서비스는 월별 gzip과 공통 플레이어를 사용합니다.
- Carto 배경지도와 deck.gl 번들은 인터넷 연결이 필요합니다. 북한 월별 격자 데이터는 서버에 저장됩니다.
- 이 결과는 탐색용 PoC이며 공식 통계, 정보 판단 또는 정책 결정 자료를 대체하지 않습니다.
