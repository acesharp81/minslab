# 주택파동 지도 API 정의서 (v1)

> **이 문서는 `schemas/api/openapi.json`(OpenAPI 3.1)에서 `node scripts/gen-api-docs.js` 로 만들어집니다. 직접 고치지 마세요.** 서버·화면 사이의 계약이며, `tests/js/contract.test.cjs`가 운영에서 받은 실제 응답(`tests/fixtures/api/`)이 이 계약을 지키는지, 핸들러가 문서에 적은 오류를 같은 모양으로 내는지, 문서의 매개변수가 코드와 같은지 매번 확인합니다.

## 1. 개요

번들이 없는 지역도 지도가 열리도록 하는 요청 시 조회 API. 열리는 방식은 3등급: A 번들(regions/<slug>) · B 번들 없는 법정동·필지(경계·건물·인허가·기반시설 요청 시 조회) · C 번들 없는 시군구(경계만). 이 문서가 서버·화면 사이의 계약이며 tests/js/contract.test.cjs 가 실제 응답이 이 스키마를 지키는지 확인한다.

### 1.1 세 가지 열기 방식(`tier`)

| 등급 | `tier` | 조건 | 지도에 나오는 것 |
|---|---|---|---|
| A | `bundle` | `regions/<slug>` 번들이 있는 시군구 | 번들의 단지·동 윤곽·점검·버스(사람이 만든 정밀 자료) |
| B | `req` | 번들 없는 **법정동·필지** | 경계 + 건물(칸 단위 요청) + 인허가 사업(건물대장 보강) + 기반시설(학교·정류장) |
| C | `edge` | 번들 없는 **시군구** | 경계 + 건물(요청 시). 사업·기반시설은 법정동을 골라야 나옴 |

### 1.2 공통 규칙

| 항목 | 규칙 |
|---|---|
| 서버 | 운영: `https://housing-board.vercel.app` · 로컬 개발 서버(node scripts/dev.js 8000): `http://localhost:8000` |
| 메서드 | `GET`(`HEAD` 허용). 그 밖은 405 + `Allow` |
| 쿼리 | **문서에 있는 이름만**. 모르는 이름·중복은 400 `invalid-query`(값을 바꿔 가며 CDN 캐시를 비켜 가는 호출 차단) |
| 오류 | `application/problem+json`(RFC 7807): `type`=`/problems/<code>`, `title`, `status`, `code`, `detail` (+ `reason`·`retryAfterSec`·`suggestions`). `/api/bus` 만 옛 `{ "error" }` |
| 보안 | 오류 문구·응답에 인증키·원천 URL·원천 오류 문구를 싣지 않는다. 서버는 임의 좌표·임의 주소를 받아 대신 부르지 않는다(열린 중계 금지) |
| 캐시 | 서버 로컬 캐시 24시간(상한) + CDN. 일시 오류·일부 실패는 짧게만(`s-maxage=60`), 429·5xx 는 `no-store` |
| 한도 | 인증키 한도(`keys-exhausted` 429, `Retry-After`)와 이 서버의 시간당 호출 상한(`budget-exhausted` 429). **초당 호출 한도는 하루 소진이 아니다**: 쉬었다 다시 부르고 키를 하루 쉬게 하지 않는다 |

### 1.3 오류 코드

| `code` | HTTP | 쓰이는 곳 |
|---|---|---|
| `invalid-query` | 400 | 쿼리 이름·개수·길이·형식 |
| `invalid-code` | 400 | 코드 형식·종류 불일치 |
| `invalid-cell` | 400 | 건물 칸 번호가 한국 범위 밖 |
| `unsupported-level` | 422 | 시도 단위(resolve) |
| `unknown-code` | 404 | 표준코드 표에 없음(resolve, suggestions) |
| `unknown-project` | 404 | 발급되지 않은 사업 id(resolve, project) |
| `method` | 405 | GET·HEAD 외 |
| `keys-exhausted` | 429 | 인증키 한도(Retry-After) |
| `budget-exhausted` | 429 | 이 서버의 시간당 호출 상한(Retry-After) |
| `not-configured` | 503 | 인증키 없음 |
| `upstream` | 502 | 원천 서비스 오류 |
| `out-of-range` | 400 | 지형 타일이 한국 범위 밖이거나 z 15 이상(terrain) |
| `not-found` | 404 | 원천에 지형 타일이 없음(terrain) |

## 2. `GET /api/v1/resolve` — 표준코드 해석

시군구 5·법정동 8/10·PNU 19자리·사업 id(PRJ-{시군구5}-{일련4}) 코드(`code` 또는 `sgg`·`bjd`·`pnu`·`project` 중 정확히 하나)를 이름·경계·중심·번들 유무(coverage)로 바꾼다. 사업 id 는 사업 레지스트리에서 사업의 위치(필지 → 법정동 → 시군구)를 찾아 그 위치로 연다. 화면의 `?project=` `?pnu=` `?bjd=` `?sgg=` `?code=` 진입이 부른다.

- operationId: `resolveCode`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `code` |  | string `^([0-9\s-]+\|[Pp][Rr][Jj]-\d{5}-\d{4})$` | 자릿수로 종류를 판별(5 sgg · 8·10 bjd · 19 pnu · `PRJ-` 접두는 사업 id). 다른 이름과 함께 쓰지 않는다 |
| `sgg` |  | string `^[0-9\s-]+$` | 시군구 5자리 |
| `bjd` |  | string `^[0-9\s-]+$` | 법정동 8자리(00 보충) 또는 10자리 |
| `pnu` |  | string `^[0-9\s-]+$` | 필지 19자리(대지구분 1·2, 본번 0000 아님) |
| `project` |  | string `^[Pp][Rr][Jj]-\d{5}-\d{4}$` | 사업 id `PRJ-{시군구5}-{일련4}`(발급 시점의 시군구, 일련은 0001 부터). 레지스트리에 있어야 한다(없으면 404 unknown-project). 합병되어 폐기된 id 는 남은 사업으로 열린다 |
| `geometry` |  | 0 · 1 | 1 이면 경계를 포함(기본: sgg 가 아니면 포함). 화면은 항상 1 |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=300, stale-while-revalidate=300` · 스키마 `ResolveResponse`

해석 결과. 경계를 못 받아도(V-World 오류) 이름·coverage 는 주고 warnings 에 알린다

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `sgg` · `bjd` · `pnu` · `project` | ● |  |
| `canonical` | string `^\d{5}$\|^\d{10}$\|^\d{19}$\|…` | ● | 정규화된 코드. 사업 id 로 열었으면 남은 사업의 id(합병된 id 를 열었으면 input 과 다르다) |
| `input` | string | ● |  |
| `sgg` | string `^\d{5}$` | ● |  |
| `bjd` | string `^\d{10}$` |  |  |
| `pnu` | string `^\d{19}$` |  |  |
| `name` | string | ● | 행정표준코드의 전체 주소 이름('경기도 하남시 감일동') |
| `level` | `sgg` · `umd` · `ri` | ● |  |
| `bbox` | Bbox |  | [최소경도, 최소위도, 최대경도, 최대위도] |
| `center` | Position |  | [경도, 위도] WGS84(한국 범위) |
| `geometry` | Geometry \| null |  | geometry=1 이거나 sgg 가 아니면 경계(필지로 열었는데 필지가 없으면 법정동 경계) |
| `parcel` | object |  |  |
| `parcel.jibun` | string | ● |  |
| `parcel.landType` | `일반` · `산` | ● |  |
| `parcel.hub` | object | ● |  |
| `parcel.hub.sigunguCd` | string | ● |  |
| `parcel.hub.bjdongCd` | string | ● |  |
| `parcel.hub.platGbCd` | `0` · `1` | ● |  |
| `parcel.hub.bun` | string | ● |  |
| `parcel.hub.ji` | string | ● |  |
| `parcel.geometry` | Geometry \| null | ● | GeoJSON Polygon 또는 MultiPolygon(경계는 점 수를 줄여 단순화함) |
| `parcel.addr` | string |  |  |
| `coverage` | Coverage | ● | {tier:'A'} 이면 regions/<slug> 번들이 있고, {tier:'none'} 이면 번들이 없어 요청 시 조회로 연다 |
| `warnings` | `padded-8-digit` · `districts-merged` · `parcel-not-found` · `ri-uses-umd-boundary` · `boundary-not-found` · `geometry-unavailable` · `geometry-not-configured` · `project-unlocated` · `project-superseded`[] |  | 열렸지만 요청과 다른 범위로 열린 이유(8자리 보충·구를 합쳐 시 경계로 씀·필지 없음→법정동·리→읍면동·경계 조회 실패·사업의 위치(필지)가 연결되지 않아 법정동 또는 시군구로 엶·합병되어 폐기된 사업 id 를 남은 사업으로 엶) |
| `source` | object | ● |  |
| `source.code` | string | ● |  |
| `source.geometry` | string | ● |  |
| `asOf` | string(date) | ● |  |
| `neighbors` | object[] |  | 같은 시군구의 읍면동(리 제외). 시군구면 전체, 법정동·필지면 자기 자신을 뺀 나머지. 인허가 사업이 없는 지역에서 화면이 이웃 법정동을 고르게 한다 |
| `neighbors[].bjd` | string `^\d{10}$` | ● |  |
| `neighbors[].name` | string | ● |  |
| `project` | object |  | type 이 project 일 때만. 사업 레코드(스펙 9.1)의 일부와 6단계. pnu·bjd·parcel·경계는 사업의 첫 필지(없으면 첫 법정동, 그것도 없으면 시군구)의 것이다 |
| `project.id` | string `^PRJ-\d{5}-\d{4}$` | ● |  |
| `project.name` | string |  |  |
| `project.units` | integer 1~ |  |  |
| `project.stageCode` | `01` · `02` · `03` · `04` · `05` · `06` | ● | 6단계: 01 정책 · 02 사업화 · 03 인허가 · 04 건설 · 05 공급 · 06 입주 |
| `project.stage` | `정책` · `사업화` · `인허가` · `건설` · `공급` · `입주` | ● |  |
| `project.pnus` | string `^\d{19}$`[] | ● | 사업 필지. 비면 위치 미연결 |
| `project.bjdCodes` | string `^\d{10}$`[] | ● |  |
| `project.block` | string |  | 번들 단지의 사업이면 그 단지 id(화면이 번들을 연 뒤 그 단지를 연다) |
| `project.supersededFrom` | string `^PRJ-\d{5}-\d{4}$` |  | 합병되어 폐기된 id 로 열었으면 그 id |

### 동작

- `code` 는 자릿수로 종류를 판별하고(`PRJ-` 접두는 사업 id), `sgg`·`bjd`·`pnu`·`project` 는 종류가 맞아야 한다(`type-mismatch`). 정확히 하나만 쓴다.
- **사업 id**(`PRJ-{시군구5}-{일련4}`)는 사업 레지스트리(`registry/projects.json`)에서 찾아 그 사업의 첫 필지 → 첫 법정동 → 시군구 순으로 열고, 응답의 `type` 은 `project`, `canonical` 은 사업 id, `project` 에 사업 정보가 붙는다. 필지가 없으면 `project-unlocated`, 합병되어 폐기된 id 는 남은 사업으로 열고 `project-superseded`. 레지스트리에 없으면 404 `unknown-project`.
- `geometry` 기본값: 시군구는 생략(커서), 법정동·필지는 포함. 화면은 항상 `geometry=1`.
- **구가 있는 시**(수원·청주·포항·창원·고양·용인·천안·전주·화성 …)는 V-World 시군구 경계에 구만 있어 구 경계를 합쳐 시 경계로 돌려주고 `warnings` 에 `districts-merged` 를 적는다.
- 필지가 연속지적도에 없으면 법정동 경계로 후퇴하고 `parcel-not-found`.

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `invalid-code` | invalid-query(코드를 둘 이상·0개·모르는 이름) · invalid-code(형식·종류 불일치). s-maxage=3600 |
| 404 | `unknown-code` · `unknown-project` | unknown-code: 표준코드 표에 없는 시군구·법정동(개편으로 바뀐 코드일 수 있음). suggestions 로 같은 시군구 법정동 후보 · unknown-project: 사업 레지스트리에 없는 사업 id(project 에 요청한 id) |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 422 | `unsupported-level` | 시도 단위(2자리)는 지도 대상이 아님 |
| 429 | `keys-exhausted` | 인증키 한도(keys-exhausted). Retry-After |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**법정동(번들 없음, 이웃 법정동 목록 포함)** (`tests/fixtures/api/resolve-bjd.json`)

```json
{
  "type": "bjd",
  "canonical": "4145011400",
  "input": "4145011400",
  "sgg": "41450",
  "bjd": "4145011400",
  "name": "경기도 하남시 감일동",
  "level": "umd",
  "neighbors": [
    {
      "bjd": "4145012000",
      "name": "상사창동"
    },
    {
      "bjd": "4145011900",
      "name": "하사창동"
    },
    "…"
  ],
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      "…"
    ]
  },
  "bbox": [
    127.13993,
    37.50323,
    "…"
  ],
  "center": [
    127.15512,
    37.50986
  ],
  "coverage": {
    "tier": "none"
  },
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 법정읍면동 경계(LT_C_ADEMD_INFO)"
  },
  "asOf": "2026-10-06"
}
```

**필지(PNU)** (`tests/fixtures/api/resolve-pnu.json`)

```json
{
  "type": "pnu",
  "canonical": "4145010600105200000",
  "input": "4145010600105200000",
  "sgg": "41450",
  "bjd": "4145010600",
  "pnu": "4145010600105200000",
  "parcel": {
    "jibun": "520",
    "landType": "일반",
    "hub": {
      "sigunguCd": "41450",
      "bjdongCd": "10600",
      "platGbCd": "0",
      "bun": "0520",
      "ji": "0000"
    },
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        "…"
      ]
    },
    "addr": "경기도 하남시 신장동 520"
  },
  "name": "경기도 하남시 신장동",
  "level": "umd",
  "neighbors": [
    {
      "bjd": "4145012000",
      "name": "상사창동"
    },
    {
      "bjd": "4145011900",
      "name": "하사창동"
    },
    "…"
  ],
  "bbox": [
    127.21337,
    37.53801,
    "…"
  ],
  "center": [
    127.21464,
    37.5391
  ],
  "coverage": {
    "tier": "none"
  },
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 연속지적도(LP_PA_CBND_BUBUN)"
  },
  "asOf": "2026-10-06"
}
```

**사업 id(필지로 열림)** (`tests/fixtures/api/resolve-project.json`)

```json
{
  "type": "project",
  "canonical": "PRJ-41450-0001",
  "input": "PRJ-41450-0001",
  "sgg": "41450",
  "project": {
    "id": "PRJ-41450-0001",
    "name": "휴먼시아 꽃뫼마을",
    "units": 748,
    "stageCode": "06",
    "stage": "입주",
    "pnus": [
      "4145010800107750000"
    ],
    "bjdCodes": [
      "4145010800"
    ]
  },
  "bjd": "4145010800",
  "pnu": "4145010800107750000",
  "parcel": {
    "jibun": "775",
    "landType": "일반",
    "hub": {
      "sigunguCd": "41450",
      "bjdongCd": "10800",
      "platGbCd": "0",
      "bun": "0775",
      "ji": "0000"
    },
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        "…"
      ]
    },
    "addr": "경기도 하남시 덕풍동 775"
  },
  "name": "경기도 하남시 덕풍동",
  "level": "umd",
  "neighbors": [
    {
      "bjd": "4145012000",
      "name": "상사창동"
    },
    {
      "bjd": "4145011900",
      "name": "하사창동"
    }
  ],
  "bbox": [
    127.19911,
    37.55148,
    "…"
  ],
  "center": [
    127.20037,
    37.55257
  ],
  "coverage": {
    "tier": "none"
  },
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 연속지적도(LP_PA_CBND_BUBUN)"
  },
  "asOf": "2026-10-06"
}
```

**사업 id(번들 단지: 필지로 열리고 `project.block` 이 번들 단지를 가리킴)** (`tests/fixtures/api/resolve-project-bundle.json`)

```json
{
  "type": "project",
  "canonical": "PRJ-28245-0001",
  "input": "PRJ-28245-0001",
  "sgg": "28245",
  "project": {
    "id": "PRJ-28245-0001",
    "name": "인천계양 테크노밸리 A6 블록",
    "units": 663,
    "stageCode": "05",
    "stage": "공급",
    "pnus": [
      "2824510900101840001"
    ],
    "bjdCodes": [
      "2824510900"
    ],
    "block": "techno-A6"
  },
  "bjd": "2824510900",
  "pnu": "2824510900101840001",
  "parcel": {
    "jibun": "184-1",
    "landType": "일반",
    "hub": {
      "sigunguCd": "28245",
      "bjdongCd": "10900",
      "platGbCd": "0",
      "bun": "0184",
      "ji": "0001"
    },
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        "…"
      ]
    },
    "addr": "인천광역시 계양구 박촌동 184-1"
  },
  "name": "인천광역시 계양구 박촌동",
  "level": "umd",
  "neighbors": [
    {
      "bjd": "2824510100",
      "name": "효성동"
    },
    {
      "bjd": "2824510200",
      "name": "계산동"
    }
  ],
  "bbox": [
    126.75523,
    37.55229,
    "…"
  ],
  "center": [
    126.75564,
    37.55278
  ],
  "coverage": {
    "tier": "A",
    "slug": "incheon-gyeyang",
    "name": "인천 계양구",
    "updatedAt": "2026-10-03",
    "visibility": "public"
  },
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 연속지적도(LP_PA_CBND_BUBUN)"
  },
  "asOf": "2026-10-06"
}
```

**번들이 있는 법정동** (`tests/fixtures/api/resolve-bundle.json`)

```json
{
  "type": "bjd",
  "canonical": "2824510900",
  "input": "2824510900",
  "sgg": "28245",
  "bjd": "2824510900",
  "name": "인천광역시 계양구 박촌동",
  "level": "umd",
  "neighbors": [
    {
      "bjd": "2824510100",
      "name": "효성동"
    },
    {
      "bjd": "2824510200",
      "name": "계산동"
    },
    "…"
  ],
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      "…"
    ]
  },
  "bbox": [
    126.73929,
    37.53902,
    "…"
  ],
  "center": [
    126.75159,
    37.55078
  ],
  "coverage": {
    "tier": "A",
    "slug": "incheon-gyeyang",
    "name": "인천 계양구",
    "updatedAt": "2026-10-03",
    "visibility": "public"
  },
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 법정읍면동 경계(LT_C_ADEMD_INFO)"
  },
  "asOf": "2026-10-06"
}
```

**구만 있는 시(경계를 구에서 합침)** (`tests/fixtures/api/resolve-sgg-districts.json`)

```json
{
  "type": "sgg",
  "canonical": "41590",
  "input": "41590",
  "sgg": "41590",
  "name": "경기도 화성시",
  "level": "sgg",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [
      "…"
    ]
  },
  "bbox": [
    126.52827,
    37.01338,
    "…"
  ],
  "center": [
    126.84479,
    37.15833
  ],
  "coverage": {
    "tier": "none"
  },
  "warnings": [
    "districts-merged"
  ],
  "source": {
    "code": "행정안전부 행정표준코드(법정동코드)",
    "geometry": "V-World 시군구 경계(LT_C_ADSIGG_INFO)"
  },
  "asOf": "2026-10-06"
}
```

## 3. `GET /api/v1/codes/search` — 이동할 곳 검색

글자(장소 이름·법정동·시군구 이름·지번·도로명)나 표준코드를 지도가 열 수 있는 후보로 바꾼다. 주소 이동 입력줄이 부른다. 후보를 고르면 `kind` 에 따라 `?sgg=` `?bjd=` `?pnu=` 로 연다.

- operationId: `searchCodes`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `q` | ● | string 2~60자 | 검색어(공백은 정리됨). 숫자만이면 코드로 본다 |
| `limit` |  | integer 1~20 | 후보 수 |
| `near` |  | string `^\d{2,3}(\.\d+)?,\d{2}(\.\d+)?$` | 지금 보는 지도 가운데 '경도,위도'(한국 안). 장소 이름이 전국에 많을 때 가까운 것을 앞에 둔다 |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=3600, stale-while-revalidate=3600` · 스키마 `SearchResponse`

후보 목록(없으면 빈 배열, 코드가 틀렸으면 meta.reason). 한쪽 원천만 실패하면 meta.partial 이 있고 s-maxage=60

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `items` | SearchItem[] | ● |  |
| `items[].code` | string `^\d{5}$\|^\d{10}$\|^\d{19}$` | ● |  |
| `items[].kind` | `sgg` · `bjd` · `pnu` | ● | 화면이 여는 코드 매개변수(?sgg= ?bjd= ?pnu=) |
| `items[].name` | string | ● |  |
| `items[].parts` | object | ● |  |
| `items[].parts.sido` | string | ● |  |
| `items[].parts.sgg` | string | ● |  |
| `items[].parts.umd` | string |  |  |
| `items[].parts.ri` | string |  |  |
| `items[].parts.jibun` | string |  |  |
| `items[].parts.road` | string |  |  |
| `items[].parts.place` | string |  |  |
| `items[].tier` | Tier | ● | 열리는 방식. bundle=번들이 있는 시군구(등급 A), req=번들 없는 법정동·필지(등급 B: 경계·건물·인허가·기반시설을 요청 시 조회), edge=번들 없는 시군구(등급 C: 경계만) |
| `items[].point` | Position |  | [경도, 위도] WGS84(한국 범위) |
| `items[].road` | `true` |  | 도로명 주소 후보(법정동 + 좌표로 연다) |
| `items[].place` | `true` |  | 장소(POI) 후보(필지 + 좌표로 연다) |
| `items[].category` | string |  |  |
| `items[].addr` | string |  |  |
| `meta` | object | ● |  |
| `meta.q` | string | ● |  |
| `meta.count` | integer 0~ | ● |  |
| `meta.sources` | `행정표준코드` · `V-World 주소` · `V-World 장소`[] | ● |  |
| `meta.partial` | `stan` · `vworld` · `budget` · `vworld-key`[] |  | 한쪽 원천이 실패해 나머지만 준 경우(이때 응답은 짧게만 캐시) |
| `meta.reason` | string |  | 코드를 쳤는데 후보가 없을 때의 이유 |
| `meta.detail` | string |  |  |
| `meta.asOf` | string(date) | ● |  |

### 동작

- 후보의 `kind` 가 화면이 여는 매개변수이다: `sgg` → `?sgg=`, `bjd` → `?bjd=`, `pnu` → `?pnu=`. `road`·`place` 후보는 `point` 로 `at=경도,위도,17.5` 를 함께 붙인다.
- `tier` 는 열리는 방식이다(`bundle`·`req`·`edge`, 위 3등급).
- `near` 가 있으면 장소 이름 중 가까운 것을 앞에 둔다(화면은 지금 보는 지도 가운데를 5 km 격자로 맞춰 보낸다).
- 행정표준코드와 V-World 중 한쪽만 실패하면 나머지 후보를 주고 `meta.partial` 에 적는다(이때 응답은 `s-maxage=60`).

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` | 쿼리 이름·개수·길이(2~60자)·limit·near 형식 오류. s-maxage=3600 |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `keys-exhausted` | 인증키 한도(keys-exhausted) |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**이름** (`tests/fixtures/api/search-name.json`)

```json
{
  "items": [
    {
      "code": "4145011400",
      "kind": "bjd",
      "name": "경기도 하남시 감일동",
      "parts": {
        "sido": "경기도",
        "sgg": "하남시",
        "umd": "감일동"
      },
      "tier": "req"
    },
    "…"
  ],
  "meta": {
    "q": "감일",
    "sources": [
      "행정표준코드",
      "V-World 장소"
    ],
    "asOf": "2026-10-06",
    "count": 6
  }
}
```

**지번 주소(PNU)** (`tests/fixtures/api/search-jibun.json`)

```json
{
  "items": [
    {
      "code": "1129013800100680037",
      "kind": "pnu",
      "name": "서울특별시 성북구 장위동 68-37",
      "parts": {
        "sido": "서울특별시",
        "sgg": "성북구",
        "umd": "장위동",
        "jibun": "68-37"
      },
      "tier": "req",
      "point": [
        127.05302,
        37.612292
      ]
    },
    "…"
  ],
  "meta": {
    "q": "장위동 68-37",
    "sources": [
      "V-World 주소",
      "행정표준코드",
      "…"
    ],
    "asOf": "2026-10-06",
    "count": 2
  }
}
```

**장소 이름(near)** (`tests/fixtures/api/search-place.json`)

```json
{
  "items": [
    {
      "code": "4145010600105200000",
      "kind": "pnu",
      "name": "경기도하남시청",
      "parts": {
        "sido": "경기도",
        "sgg": "하남시",
        "umd": "신장동",
        "jibun": "520",
        "place": "경기도하남시청"
      },
      "tier": "req",
      "point": [
        127.21468,
        37.539113
      ],
      "place": true,
      "category": "지방행정기관 > 시청",
      "addr": "경기도 하남시 대청로 10"
    },
    "…"
  ],
  "meta": {
    "q": "시청",
    "sources": [
      "행정표준코드",
      "V-World 장소"
    ],
    "asOf": "2026-10-06",
    "count": 5
  }
}
```

**틀린 코드** (`tests/fixtures/api/search-code-bad.json`)

```json
{
  "items": [],
  "meta": {
    "q": "12345",
    "sources": [
      "행정표준코드"
    ],
    "asOf": "2026-10-06",
    "reason": "unknown-code",
    "detail": "행정표준코드 표에 없는 코드입니다",
    "count": 0
  }
}
```

## 4. `GET /api/v1/notices` — 공공 모집 공고(마이홈·LH)

시군구 하나의 공공주택 모집공고(임대·분양)를 돌려준다: 마이홈포털(HWSPR02)과 LH 분양임대공고문(15058530)을 합친다. 번들이 없는 지역에도 지금 모집 중인 공공주택을 보이려는 것이며 화면은 사이드바에 비동기로 채운다. 마이홈 원천은 시군구 필터가 없는 전국 목록(100건씩, 1시간 캐시)이라 행정표준코드의 시군구 이름으로 거른다. LH 공고문은 시도만 있어 제목에 시군구·법정동 이름이 있는 것만 싣고(제목 기준 추정, 마이홈과 제목이 같으면 마이홈만), 공급정보(15056765)로 단지명·세대수를 채운다. 한쪽이 실패하면 나머지를 주고 meta.partial 에 알린다.

- operationId: `getNotices`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `sgg` | ● | string `^[0-9\s-]+$` | 시군구 5자리(구가 있는 시는 구 코드나 시 코드 모두 가능) |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=3600, stale-while-revalidate=3600` · 스키마 `NoticesResponse`

공고 목록(없으면 빈 배열). 임대·분양 한쪽만 실패하면 meta.partial 과 s-maxage=60

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"Notices"` | ● |  |
| `sgg` | string `^\d{5}$` | ● |  |
| `name` | string | ● | 행정표준코드 시군구 이름('경기도 하남시') |
| `asOf` | string(date) | ● |  |
| `items` | Notice[] | ● | 공고일 최신 순(마이홈·LH 합침). 구가 있는 시는 시 전체가 구 공고를 모두 포함 |
| `items[].id` | string | ● | 'rental-<공고번호>[-<세대번호>]' · 'sale-…'(마이홈) · 'lh-<PAN_ID>'(LH 공고문) |
| `items[].kind` | `rental` · `sale` | ● |  |
| `items[].title` | string | ● |  |
| `items[].agency` | string \| null |  |  |
| `items[].status` | string \| null |  |  |
| `items[].housingType` | string \| null |  |  |
| `items[].supplyType` | string \| null |  |  |
| `items[].complex` | string \| null |  | 단지명(LH 공고는 공급정보의 단지명, 둘을 넘으면 '… 외 N') |
| `items[].units` | integer 1~ \| null |  | 세대수(LH 공고는 공급정보의 금회공급 세대수 합) |
| `items[].address` | string \| null |  |  |
| `items[].pnu` | string `^\d{19}$` \| null |  | 있으면 화면이 그 필지로 이동할 수 있다 |
| `items[].announcedAt` | string(date) \| null |  |  |
| `items[].applyFrom` | string(date) \| null |  |  |
| `items[].applyTo` | string(date) \| null |  |  |
| `items[].url` | string `^https://(www\.myhome\.go\…` \| null |  | 마이홈·LH 주소만(원천 링크를 그대로 믿지 않는다) |
| `items[].source` | `myhome` · `lh` |  | 출처: myhome(마이홈포털 HWSPR02) · lh(한국토지주택공사 분양임대공고문). lh 공고는 주소·필지가 없고(pnu null) 제목에 시군구·법정동 이름이 있을 때만 그 시군구에 실리며(제목 기준 추정), 단지명·세대수는 공급정보(15056765)에서 채운다. 마이홈과 제목이 같은 LH 공고는 마이홈 쪽만 싣는다 |
| `meta` | object | ● |  |
| `meta.source` | string | ● |  |
| `meta.rental` | integer 0~ | ● | 전국 마이홈 임대 공고 수 |
| `meta.sale` | integer 0~ | ● | 전국 마이홈 분양 공고 수 |
| `meta.matched` | integer 0~ | ● | 이 시군구에 실린 공고 수(마이홈 + LH) |
| `meta.partial` | `rental` · `sale` · `lh` · `lh-supply`[] |  | 일부가 실패해 나머지만 준 경우(이때 응답은 짧게만 캐시): rental·sale(마이홈 목록) · lh(LH 공고문 목록) · lh-supply(LH 공급정보, 단지명·세대수 없음) |
| `meta.lh` | integer 0~ | ● | 전국 LH 진행 중 공고 수(공고중·접수중·정정공고중, 토지·상가 포함 — 주택 공고만 거르기 전) |
| `meta.lhMatched` | integer 0~ | ● | 그 가운데 LH 공고 수 |

### 동작

- 공고는 대부분 매입임대·일반매각(개별 주택)이다. 건설 중인 단지(`permits`)와 합치지 않고 화면의 별도 목록으로 보인다. `pnu` 가 있으면 화면이 그 필지로 이동할 수 있다.
- 구가 있는 시는 시 코드로 물으면 구 공고를 모두 돌려주고, 구 코드로 물으면 그 구만.
- 링크(`url`)는 마이홈·LH 주소만 싣는다.

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `invalid-code` | invalid-query(쿼리) · invalid-code(시군구가 아님). s-maxage=3600 |
| 404 | `unknown-code` | 표준코드 표에 없는 시군구 |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `keys-exhausted` | 인증키 한도(keys-exhausted). Retry-After |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**하남시(임대·분양 공고)** (`tests/fixtures/api/notices-hanam.json`)

```json
{
  "type": "Notices",
  "sgg": "41450",
  "name": "경기도 하남시",
  "asOf": "2026-10-06",
  "items": [
    {
      "id": "rental-21372-1",
      "kind": "rental",
      "title": "하남시 신혼희망타운 행복주택 예비입주자 모집공고(2026.10.01)",
      "agency": "LH",
      "status": "일반공고",
      "housingType": "아파트",
      "supplyType": "행복주택",
      "complex": "하남감일A7BL",
      "units": 20,
      "address": "경기도 하남시 감일순환로 40",
      "pnu": "4145011500104680000",
      "announcedAt": "2026-10-01",
      "applyFrom": "2026-10-12",
      "applyTo": "2026-10-14",
      "url": "https://www.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcDetailView.do?pblancId=21372&houseSn=1",
      "source": "myhome"
    },
    "…"
  ],
  "meta": {
    "source": "마이홈포털 공공주택 모집공고(HWSPR02) + 한국토지주택공사 분양임대공고문(15058530)·공급정보(15056765)",
    "rental": 244,
    "sale": 80,
    "lh": 158,
    "matched": 2,
    "lhMatched": 0
  }
}
```

**LH 공고가 더해지는 시군구(아산시, `source: "lh"`)** (`tests/fixtures/api/notices-asan.json`)

```json
{
  "type": "Notices",
  "sgg": "44200",
  "name": "충청남도 아산시",
  "asOf": "2026-10-06",
  "items": [
    {
      "id": "lh-2015122300020726",
      "kind": "rental",
      "title": "아산지역 국민임대주택 예비입주자 모집공고(2026.09.15)",
      "agency": "한국토지주택공사",
      "status": "접수중",
      "housingType": "국민임대",
      "supplyType": "임대주택",
      "complex": "아산탕정2-A7BL 국민임대, 아산탕정 2-A15BL 국민임대 외 2",
      "units": 1530,
      "address": null,
      "pnu": null,
      "announcedAt": "2026-09-15",
      "applyFrom": null,
      "applyTo": "2026-10-14",
      "url": "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=2015122300020726&ccrCnntSysDsCd=03&uppAisTpCd=06&aisTpCd=07&mi=1026",
      "source": "lh"
    },
    "…"
  ],
  "meta": {
    "source": "마이홈포털 공공주택 모집공고(HWSPR02) + 한국토지주택공사 분양임대공고문(15058530)·공급정보(15056765)",
    "rental": 244,
    "sale": 80,
    "lh": 158,
    "matched": 7,
    "lhMatched": 1
  }
}
```

**공고가 없는 시군구(종로구)** (`tests/fixtures/api/notices-none.json`)

```json
{
  "type": "Notices",
  "sgg": "11110",
  "name": "서울특별시 종로구",
  "asOf": "2026-10-06",
  "items": [],
  "meta": {
    "source": "마이홈포털 공공주택 모집공고(HWSPR02) + 한국토지주택공사 분양임대공고문(15058530)·공급정보(15056765)",
    "rental": 244,
    "sale": 80,
    "lh": 158,
    "matched": 0,
    "lhMatched": 0
  }
}
```

## 5. `GET /api/v1/buildings` — 건물 요청 시 조회(0.01° 칸)

번들이 없는 곳(또는 번들 밖)의 기존 건물 3D 를 칸 단위로 받는다. 화면이 지도에 보이는 칸마다 부른다. 건물은 중심점이 있는 칸에만 속한다.

- operationId: `getBuildings`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `cell` | ● | string `^\d{5},\d{4}$` | `<ix>,<iy>` = floor(경도×100),floor(위도×100). 예 128.00,37.55 근처 → 12800,3755 |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=86400, stale-while-revalidate=86400` · 스키마 `BuildingsResponse`

칸 안의 건물(최대 5쪽×1,000동, 넘으면 meta.truncated)

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"FeatureCollection"` | ● |  |
| `cell` | integer[] | ● | [ix, iy] = [floor(경도×100), floor(위도×100)] |
| `bbox` | Bbox | ● | [최소경도, 최소위도, 최대경도, 최대위도] |
| `features` | object[] | ● |  |
| `features[].type` | `"Feature"` |  |  |
| `features[].properties` | BuildingProperties | ● | 번들 buildings.json 과 같은 속성(짧은 이름) |
| `features[].properties.eh` | number | ● | 그리는 높이 m(층수환산 높이 포함) |
| `features[].properties.src` | string | ● | 높이 출처('공식높이'·'층수환산'·'정보없음'). '정보없음'은 높이·층수가 모두 없는 도형이며 대장과 이어지지 않았을 수 있어 화면은 평면으로만 그림(eh는 3) |
| `features[].properties.h` | number |  | 공식 높이 m |
| `features[].properties.f` | integer |  | 지상층수 |
| `features[].properties.b` | integer |  | 지하층수 |
| `features[].properties.u` | string |  | 용도 |
| `features[].properties.n` | string |  | 건물 이름 |
| `features[].properties.a` | integer |  | 사용승인 연도 |
| `features[].properties.x` | 값 |  | 기타 |
| `features[].geometry` | Geometry | ● | GeoJSON Polygon 또는 MultiPolygon(경계는 점 수를 줄여 단순화함) |
| `meta` | object | ● |  |
| `meta.source` | string | ● |  |
| `meta.fetchedAt` | string(date) | ● |  |
| `meta.count` | integer 0~ | ● |  |
| `meta.rawCount` | integer |  |  |
| `meta.tinyDropped` | integer |  |  |
| `meta.outsideCell` | integer |  |  |
| `meta.pages` | integer 1~5 | ● |  |
| `meta.truncated` | boolean | ● | 칸에 건물이 5,000동을 넘어 일부만 담음 |
| `meta.heights` | string |  |  |

### 동작

- 건물은 중심점이 있는 칸에만 속한다(이웃 칸과 겹치지 않음). 속성 이름은 번들 `buildings.json` 과 같다.
- 칸당 V-World 를 최대 5쪽(1,000동씩) 부르고 넘으면 `meta.truncated`.

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `invalid-cell` | invalid-query(쿼리) · invalid-cell(한국 범위 밖·형식 오류) |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `keys-exhausted` | 이 서버의 시간당 V-World 호출 상한(BUILDINGS_UPSTREAM_PER_HOUR). Retry-After |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**칸 하나(건물은 앞 몇 개만)** (`tests/fixtures/api/buildings-cell.json`)

```json
{
  "type": "FeatureCollection",
  "cell": [
    12721,
    3753
  ],
  "bbox": [
    127.21,
    37.53,
    "…"
  ],
  "features": [
    {
      "type": "Feature",
      "properties": {
        "eh": 5.7,
        "src": "공식높이",
        "h": 5.7,
        "f": 1,
        "u": "동.식물 관련시설",
        "a": 2000
      },
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
          "…"
        ]
      }
    },
    "…"
  ],
  "meta": {
    "source": "V-World GIS건물통합정보(LT_C_BLDGINFO)",
    "fetchedAt": "2026-10-06",
    "count": 1702,
    "heights": "층수환산 높이는 계양 측정 층고 기반 근사",
    "rawCount": 1852,
    "tinyDropped": 89,
    "outsideCell": 61,
    "pages": 2,
    "truncated": false
  }
}
```

## 6. `GET /api/v1/permits` — 인허가 사업 요청 시 조회

법정동 하나의 건축HUB 주택인허가를 번지(PNU) 단위 사업 + 필지 경계로 돌려준다. 공공주택지구 블록 단위 허가의 위치·합필 지번·준공은 건축물대장 총괄표제부로 보강한다.

- operationId: `getPermits`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `bjd` | ● | string `^\d{8}(\d{2})?$` | 법정동 8자리(00 보충) 또는 10자리 |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=86400, stale-while-revalidate=86400` · 스키마 `PermitsResponse`

사업 목록(한 법정동 최대 120곳). 필지를 일부 못 받았거나 건물대장 보강이 완전하지 않으면 s-maxage=60

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"FeatureCollection"` | ● |  |
| `bjd` | string `^\d{10}$` | ● |  |
| `features` | object[] | ● |  |
| `features[].type` | `"Feature"` |  |  |
| `features[].properties` | PermitProject | ● | 번지(PNU) 단위로 모은 인허가 사업 하나(화면은 단지 하나로 그린다) |
| `features[].properties.pnu` | string `^\d{19}$` | ● |  |
| `features[].properties.jibun` | string | ● |  |
| `features[].properties.name` | string | ● |  |
| `features[].properties.label` | string | ● | 짧은 이름(8자 이내) |
| `features[].properties.units` | integer 0~ \| null | ● | 가장 최근 허가의 총세대수 |
| `features[].properties.status` | `계획` · `건설 단계` · `입주 단계` | ● | 인허가로 아는 3가지뿐('계획'은 착공·사용검사 기록이 원천에 없다는 뜻) |
| `features[].properties.mainBldCnt` | integer \| null |  |  |
| `features[].properties.approvedAt` | string(date) \| null |  |  |
| `features[].properties.startedAt` | string(date) \| null |  |  |
| `features[].properties.completedAt` | string(date) \| null |  |  |
| `features[].properties.plannedStart` | PartialDate \| null |  | 원천이 연·월까지만 적은 날짜는 YYYY-MM · YYYY 로 온다(예정일) |
| `features[].properties.plannedCompletion` | PartialDate \| null |  | 사용검사 예정일(입주 단계가 아닐 때) |
| `features[].properties.overdue` | object \| null |  | 예정일이 지났는데 착공·사용검사 기록이 없다는 사실(지연 판정이 아님) |
| `features[].properties.address` | string \| null |  |  |
| `features[].properties.refs` | string[] |  | 그 번지에 모인 허가 관리번호(mgmHsrgstPk). 22자리까지 있어 문자열이고 숫자로 바꾸면 안 된다(건축HUB 는 JSON 숫자로 주므로 서버가 파싱 전에 문자열로 지킨다) |
| `features[].properties.records` | integer 1~ | ● |  |
| `features[].properties.latestRef` | string \| null |  | 가장 최근 허가의 관리번호(문자열) |
| `features[].properties.via` | `"ledger"` |  | 위치를 건축물대장이 정함(블록 단위 허가 또는 합필·분할) |
| `features[].properties.block` | string |  | 허가가 블록 단위일 때 블록 이름 |
| `features[].properties.hubJibun` | string |  | 합필·분할 전 허가 지번 |
| `features[].properties.statusBy` | `"ledger"` |  | 준공을 대장 사용승인일로 올림 |
| `features[].properties.ledger` | object |  |  |
| `features[].properties.projectId` | string `^PRJ-\d{5}-\d{4}$` |  | 사업 레지스트리에 발급된 사업이면 그 id(허가 관리번호나 PNU 가 같은 사업). 없으면 발급 전. 화면은 이 id 로 `?project=` 링크를 만든다 |
| `features[].geometry` | Geometry | ● | GeoJSON Polygon 또는 MultiPolygon(경계는 점 수를 줄여 단순화함) |
| `meta` | object | ● |  |
| `meta.source` | string | ● |  |
| `meta.fetchedAt` | string(date) | ● |  |
| `meta.records` | integer 0~ | ● |  |
| `meta.pages` | integer 0~ | ● |  |
| `meta.candidates` | integer 0~ | ● | 공동주택 + 총세대수>0 인 번지·블록 수 |
| `meta.projects` | integer 0~ | ● |  |
| `meta.located` | integer 0~ | ● | 지도에 올린 수(features 길이) |
| `meta.unlocated` | integer 0~ | ● |  |
| `meta.unlocatedNames` | string[] |  |  |
| `meta.unlocatedList` | object[] |  |  |
| `meta.unlocatedList[].name` | string | ● |  |
| `meta.unlocatedList[].jibun` | string | ● |  |
| `meta.unlocatedList[].status` | string | ● |  |
| `meta.unlocatedList[].units` | integer \| null |  |  |
| `meta.unlocatedList[].approvedAt` | string(date) \| null |  |  |
| `meta.unlocatedList[].reason` | string | ● |  |
| `meta.blockProjects` | integer 0~ | ● | 공공주택지구 블록 단위 허가 중 대장으로도 위치를 못 정한 수 |
| `meta.blockList` | object[] |  |  |
| `meta.blockList[].name` | string | ● |  |
| `meta.blockList[].block` | string \| null |  |  |
| `meta.blockList[].units` | integer \| null |  |  |
| `meta.blockList[].status` | string |  |  |
| `meta.blockList[].approvedAt` | string(date) \| null |  |  |
| `meta.blockList[].records` | integer |  |  |
| `meta.ledger` | object |  |  |
| `meta.ledger.used` | boolean | ● |  |
| `meta.ledger.bjds` | integer |  |  |
| `meta.ledger.rows` | integer |  |  |
| `meta.ledger.blocksMatched` | integer |  |  |
| `meta.ledger.blocksAmbiguous` | integer |  |  |
| `meta.ledger.parcelsRecovered` | integer |  |  |
| `meta.ledger.completions` | integer |  |  |
| `meta.ledger.error` | string |  | 건물대장 보강이 완전하지 않은 이유(이때 응답은 짧게만 캐시) |
| `meta.parcelErrors` | integer 0~ | ● | 필지 경계를 일시 오류로 못 받은 수(0이 아니면 응답은 짧게만 캐시) |
| `meta.truncated` | boolean | ● | 사업이 120곳을 넘어 세대수 큰 순으로 남김 |
| `meta.skipped` | object | ● |  |
| `meta.skipped.notCandidate` | integer | ● |  |
| `meta.skipped.noPnu` | integer | ● |  |

### 동작

- 후보 규칙: 공동주택 + 총세대수 > 0, 번지(PNU) 단위로 모음. 상태는 인허가로 아는 3가지(`계획`·`건설 단계`·`입주 단계`).
- 공공주택지구 블록 단위 허가(필지 번호 없음)는 건축물대장 총괄표제부의 세대수 + 대지면적으로 위치를 정하고 `via: "ledger"` 를 붙인다. 못 정한 것은 `meta.blockList`.
- 예정일은 연·월만 있는 값(`YYYY-MM`)이 올 수 있다(`PartialDate`).

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `invalid-code` | invalid-query · invalid-code(법정동이 아님) |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `keys-exhausted` · `budget-exhausted` | keys-exhausted(키 한도) 또는 budget-exhausted(시간당 필지 호출 상한). Retry-After |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**법정동(덕풍동)** (`tests/fixtures/api/permits-deokpung.json`)

```json
{
  "type": "FeatureCollection",
  "bjd": "4145010800",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "pnu": "4145010800107880000",
        "jibun": "788",
        "name": "하남덕풍행복주택",
        "label": "하남덕풍행복주택",
        "units": 30,
        "status": "계획",
        "mainBldCnt": 1,
        "approvedAt": "2017-12-27",
        "startedAt": null,
        "completedAt": null,
        "plannedStart": "2023-12-28",
        "plannedCompletion": "2019-11-30",
        "overdue": {
          "kind": "착공",
          "plannedAt": "2023-12-28",
          "months": 33
        },
        "address": "경기도 하남시 덕풍동 788번지",
        "refs": [
          "1115100012021",
          "1083100004201"
        ],
        "records": 2,
        "latestRef": "1115100012021"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          "…"
        ]
      }
    },
    "…"
  ],
  "meta": {
    "source": "건축HUB 주택인허가정보(getHpBasisOulnInfo·getHpPlatPlcInfo) + 건축HUB 건축물대장정보(총괄표제부) + V-World 연속지적도(LP_PA_CBND_BUBUN)",
    "fetchedAt": "2026-10-06",
    "records": 453,
    "pages": 5,
    "candidates": 32,
    "projects": 32,
    "located": 30,
    "unlocated": 2,
    "unlocatedNames": [
      "덕풍동 늘푸른2지역 주택조합아파트(474-6)",
      "하남더샵에디피스(285-31)"
    ],
    "unlocatedList": [
      {
        "name": "덕풍동 늘푸른2지역 주택조합아파트",
        "jibun": "474-6",
        "status": "계획",
        "units": 696,
        "approvedAt": "2003-06-30",
        "reason": "15년 넘은 허가라 지번이 바뀌었을 수 있음"
      },
      {
        "name": "하남더샵에디피스",
        "jibun": "285-31",
        "status": "입주 단계",
        "units": 980,
        "approvedAt": "2016-03-31",
        "reason": "준공 뒤 합필·분할로 지번이 없어졌을 수 있음"
      }
    ],
    "blockProjects": 0,
    "blockList": [],
    "ledger": {
      "used": true,
      "bjds": 24,
      "rows": 1226,
      "blocksMatched": 0,
      "blocksAmbiguous": 0,
      "parcelsRecovered": 0,
      "completions": 0
    },
    "parcelErrors": 0,
    "truncated": false,
    "skipped": {
      "notCandidate": 418,
      "noPnu": 0
    }
  }
}
```

**공공주택지구(감일동, 건물대장 보강)** (`tests/fixtures/api/permits-gamil-ledger.json`)

```json
{
  "type": "FeatureCollection",
  "bjd": "4145011400",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "pnu": "4145011500105300000",
        "jibun": "530",
        "name": "하남감일스윗시티",
        "label": "하남감일스윗시티",
        "units": 934,
        "status": "입주 단계",
        "mainBldCnt": null,
        "approvedAt": "2010-12-31",
        "startedAt": null,
        "completedAt": "2019-06-10",
        "plannedStart": null,
        "plannedCompletion": null,
        "overdue": null,
        "address": "경기도 하남시 감이동 530번지",
        "refs": [],
        "records": 1,
        "latestRef": "1115100008101",
        "block": "B7 BL",
        "via": "ledger",
        "ledger": {
          "name": "감일 한라비발디",
          "platPlc": "경기도 하남시 감이동 530번지",
          "useAprDay": "2019-06-10",
          "areaDiff": 0.19
        }
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          "…"
        ]
      }
    },
    "…"
  ],
  "meta": {
    "source": "건축HUB 주택인허가정보(getHpBasisOulnInfo·getHpPlatPlcInfo) + 건축HUB 건축물대장정보(총괄표제부) + V-World 연속지적도(LP_PA_CBND_BUBUN)",
    "fetchedAt": "2026-10-06",
    "records": 32,
    "pages": 1,
    "candidates": 12,
    "projects": 0,
    "located": 10,
    "unlocated": 0,
    "unlocatedNames": [],
    "unlocatedList": [],
    "blockProjects": 2,
    "blockList": [
      {
        "name": "LH아파트",
        "block": "A3블럭",
        "units": 1094,
        "status": "계획",
        "approvedAt": "2018-01-10",
        "records": 1,
        "latestRef": "1115100008801",
        "startedAt": null,
        "completedAt": null
      },
      {
        "name": "하남감일 공공주택지구 B-9BL",
        "block": "B-9블록",
        "units": 866,
        "status": "계획",
        "approvedAt": "2019-02-28",
        "records": 1,
        "latestRef": "1083100004561",
        "startedAt": null,
        "completedAt": null
      }
    ],
    "ledger": {
      "used": true,
      "bjds": 24,
      "rows": 1226,
      "blocksMatched": 10,
      "blocksAmbiguous": 1,
      "parcelsRecovered": 0,
      "completions": 0
    },
    "parcelErrors": 0,
    "truncated": false,
    "skipped": {
      "notCandidate": 19,
      "noPnu": 13
    }
  }
}
```

## 7. `GET /api/v1/infra` — 기반시설(신설예정 학교·버스 정류장) 요청 시 조회

법정동 인허가 단지 가까이의 신설예정 학교(교육재정알리미)와 버스 정류장(TAGO, 없으면 OpenStreetMap)을 번들 infra.json 과 같은 모양으로 돌려준다. 서버는 임의 좌표를 받지 않고 그 법정동 인허가 결과의 필지 중심만 쓴다. 인허가는 이 서버의 permits API 를 공개 주소로 불러 CDN 캐시에서 받는다.

- operationId: `getInfra`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `bjd` | ● | string `^\d{8}(\d{2})?$` | 법정동 8자리(00 보충) 또는 10자리 |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage=86400, stale-while-revalidate=86400` · 스키마 `InfraResponse`

학교·정류장. 한쪽이 실패하면 meta.schoolsError·stopsError 와 s-maxage=60. TAGO 밖 지역: 서울(시도 11)은 서울특별시 정류소정보조회(meta.stopsSource='seoul'), 실패하면 OpenStreetMap(meta.stopsSource='osm', meta.seoulError), 강릉 등 그 밖은 OpenStreetMap, 그것도 못 받으면 meta.noBus

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"Infra"` | ● |  |
| `bjd` | string `^\d{10}$` | ● |  |
| `asOf` | string(date) | ● |  |
| `sources` | InfraSource[] | ● |  |
| `sources[].id` | string | ● | edu-newschool · tago-bus · seoul-bus · osm-bus |
| `sources[].label` | string | ● |  |
| `sources[].publisher` | string |  |  |
| `sources[].url` | string |  |  |
| `sources[].license` | string |  |  |
| `sources[].redistributable` | `Y` · `N` · `unknown` |  | 공개 사이트에 가공 결과를 실어도 되는지(schemas/input.spec.json 의 redistributable 과 같은 값) |
| `sources[].asOf` | string(date) |  |  |
| `schools` | School[] | ● |  |
| `schools[].id` | string | ● |  |
| `schools[].name` | string | ● |  |
| `schools[].level` | `초등학교` · `중학교` · `고등학교` · `특수학교` · `기타` |  |  |
| `schools[].status` | string |  |  |
| `schools[].openYm` | string \| null |  |  |
| `schools[].classes` | integer \| null |  |  |
| `schools[].students` | integer \| null |  |  |
| `schools[].address` | string \| null |  |  |
| `schools[].lon` | number 120~135 | ● |  |
| `schools[].lat` | number 30~45 | ● |  |
| `schools[].sources` | string[] |  |  |
| `stops` | Stop[] | ● |  |
| `stops[].id` | string | ● |  |
| `stops[].name` | string | ● |  |
| `stops[].lon` | number 120~135 | ● |  |
| `stops[].lat` | number 30~45 | ● |  |
| `stops[].no` | string |  | 정류소 번호(있을 때) |
| `meta` | object | ● |  |
| `meta.centers` | integer 0~ | ● | 인허가 단지 필지 중심 수(상한 30) |
| `meta.schoolsNational` | integer |  |  |
| `meta.schools` | integer | ● |  |
| `meta.stopCalls` | integer |  |  |
| `meta.stops` | integer | ● |  |
| `meta.schoolsError` | string |  |  |
| `meta.stopsError` | string |  |  |
| `meta.noBus` | `true` |  | TAGO·서울시·OpenStreetMap 어디에도 정류장 자료가 없다. 교통 점검은 '자료 없음' |
| `meta.stopsSource` | `tago` · `seoul` · `osm` |  | 정류장 출처: tago(국토교통부) 우선, 서울(시도 11)은 seoul(서울특별시 정류소정보조회), 그 밖에 TAGO 에 자료가 없는 지역(강릉 등)과 서울시 조회 실패 때는 osm(OpenStreetMap, ODbL) |
| `meta.seoulError` | string |  | 서울시 정류소 조회가 실패했거나 일부만 받았다(시간당 상한·인증키 한도·연결 오류). 이때 응답은 s-maxage=60 이고 OpenStreetMap 으로 물러났을 수 있다 |

### 동작

- 서버는 임의 좌표를 받지 않고 그 법정동의 인허가 필지 중심만 쓴다(키를 쓰는 열린 중계가 되지 않게). 인허가가 없으면 비어 있다.
- 정류장은 TAGO 가 우선이고, 서울은 서울특별시 정류소정보조회(`meta.stopsSource: "seoul"`, 하루 1,000건 한도라 단지 중심 300 m 간격 최대 12곳만 부른다), TAGO·서울시에 자료가 없거나 서울시 조회가 실패하면 OpenStreetMap(`meta.stopsSource: "osm"`, ODbL 출처 표시)으로 보조한다.
- `meta.schoolsError`·`meta.stopsError` 가 있으면 일부만 준 것이며 응답은 `s-maxage=60`.

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `invalid-code` | invalid-query · invalid-code |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `keys-exhausted` · `budget-exhausted` | keys-exhausted 또는 budget-exhausted(시간당 TAGO 호출 상한). Retry-After |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |
| 503 | `not-configured` | 인증키가 없음. Cache-Control: no-store |

### 예제

**법정동(TAGO 정류소)** (`tests/fixtures/api/infra-deokpung.json`)

```json
{
  "type": "Infra",
  "bjd": "4145010800",
  "asOf": "2026-10-06",
  "sources": [
    {
      "id": "edu-newschool",
      "label": "지방교육재정알리미 신설예정학교",
      "publisher": "교육부·한국교육학술정보원",
      "url": "https://eduinfo.go.kr/portal/theme/newSchMapPage.do",
      "redistributable": "unknown",
      "asOf": "2026-10-06"
    },
    {
      "id": "tago-bus",
      "label": "국토교통부 TAGO 버스정류소정보",
      "publisher": "국토교통부",
      "url": "https://www.data.go.kr/data/15098534/openapi.do",
      "license": "이용허락범위 제한 없음",
      "redistributable": "Y",
      "asOf": "2026-10-06"
    }
  ],
  "schools": [
    {
      "id": "edu-136",
      "name": "미사4고",
      "level": "고등학교",
      "status": "신설예정",
      "openYm": "2027-03",
      "classes": 37,
      "students": 1015,
      "address": "하남시 풍산동 562",
      "lon": 127.1850913,
      "lat": 37.5490196,
      "sources": [
        "edu-newschool"
      ]
    },
    {
      "id": "edu-202",
      "name": "교산1중",
      "level": "중학교",
      "status": "신설예정",
      "openYm": "2030-03",
      "classes": 32,
      "students": 840,
      "address": "하남시 천현동 63-2 일원",
      "lon": 127.2201952,
      "lat": 37.5331721,
      "sources": [
        "edu-newschool"
      ]
    }
  ],
  "stops": [
    {
      "id": "GGB227000520",
      "name": "꽃뫼마을1단지.덕풍중학교",
      "lon": 127.19925,
      "lat": 37.55245,
      "no": "28325"
    },
    {
      "id": "GGB227000523",
      "name": "꽃뫼마을1단지.덕풍중학교",
      "lon": 127.199033,
      "lat": 37.552533,
      "no": "28328"
    },
    "…"
  ],
  "meta": {
    "centers": 30,
    "schoolsNational": 220,
    "schools": 3,
    "stopCalls": 20,
    "stops": 117,
    "stopsSource": "tago"
  }
}
```

**서울(서울특별시 정류소정보조회)** (`tests/fixtures/api/infra-seoul.json`)

```json
{
  "type": "Infra",
  "bjd": "1129013800",
  "asOf": "2026-10-06",
  "sources": [
    {
      "id": "seoul-bus",
      "label": "서울특별시 버스 정류소정보조회",
      "publisher": "서울특별시",
      "url": "https://www.data.go.kr/data/15000303/openapi.do",
      "redistributable": "unknown",
      "asOf": "2026-10-06"
    }
  ],
  "schools": [],
  "stops": [
    {
      "id": "seoul-107900355",
      "name": "간대어린이공원",
      "lon": 127.051183,
      "lat": 37.618638,
      "no": "08877"
    },
    {
      "id": "seoul-110000234",
      "name": "광운대학교",
      "lon": 127.058146,
      "lat": 37.619843,
      "no": "11335"
    },
    "…"
  ],
  "meta": {
    "centers": 13,
    "schoolsNational": 220,
    "schools": 0,
    "stopCalls": 7,
    "stops": 112,
    "stopsSource": "seoul"
  }
}
```

**서울시 조회가 안 될 때(OpenStreetMap 으로 물러남)** (`tests/fixtures/api/infra-seoul-osm.json`)

```json
{
  "type": "Infra",
  "bjd": "1129013800",
  "asOf": "2026-10-05",
  "sources": [
    {
      "id": "osm-bus",
      "label": "OpenStreetMap 버스 정류장",
      "publisher": "OpenStreetMap contributors",
      "url": "https://www.openstreetmap.org/copyright",
      "license": "ODbL 1.0(출처 표시)",
      "redistributable": "Y",
      "asOf": "2026-10-05"
    }
  ],
  "schools": [],
  "stops": [
    {
      "id": "osm-357857620",
      "name": "광운대학교",
      "lon": 127.058058,
      "lat": 37.619723
    },
    {
      "id": "osm-357831427",
      "name": "광운중.광운인공지능고등학교",
      "lon": 127.056602,
      "lat": 37.61889
    },
    "…"
  ],
  "meta": {
    "centers": 13,
    "schoolsNational": 220,
    "schools": 0,
    "stopCalls": 0,
    "stops": 66,
    "stopsSource": "osm"
  }
}
```

**정류장을 못 받은 경우(OSM 서버도 실패)** (`tests/fixtures/api/infra-seoul-nobus.json`)

```json
{
  "type": "Infra",
  "bjd": "1150010500",
  "asOf": "2026-10-05",
  "sources": [],
  "schools": [],
  "stops": [],
  "meta": {
    "centers": 18,
    "schoolsNational": 220,
    "schools": 0,
    "stopCalls": 0,
    "stops": 0,
    "noBus": true,
    "stopsError": "버스 정류장(OpenStreetMap)을 불러오지 못함"
  }
}
```

## 8. `GET /api/v1/terrain` — 지형 타일 중계(AWS Terrain Tiles)

지도의 지형(terrain·hillshade) 타일. AWS Terrain Tiles(terrarium PNG, 미국 동부 S3)를 이 서버를 거쳐 받아 CDN 에 1년 캐시한다(S3 직접은 장당 응답 시작 약 0.7초라 첫 로딩이 가장 길었다). 한국 범위에 걸치는 z 0~14 타일만 중계한다(열린 중계 금지). 지도는 상황판 안에서만 이 경로를 쓰고, API 가 없는 옛 정적 열기는 S3 를 그대로 쓴다. 출처 표기는 지도 출처(ⓘ)에 있다.

- operationId: `getTerrainTile`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `z` | ● | integer 0~14 | 확대 단계(0~14) |
| `x` | ● | integer 0~16383 | 타일 열(0~2^z-1, z 14 에서 16383) |
| `y` | ● | integer 0~16383 | 타일 행(0~2^z-1, z 14 에서 16383) |

### 응답 `200`

`image/png` · `Cache-Control: public, max-age=86400, s-maxage=31536000, immutable` · 스키마 `PNG(terrarium, 원자료 그대로)`

terrarium 인코딩 PNG(원자료 그대로)

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|

### 동작

- 지도 지형 타일(terrain·hillshade, maxzoom 14)을 미국 동부 S3 대신 이 서버(icn1)와 CDN 에서 받게 한다. 한 번 받은 타일은 CDN 이 1년 보관한다.
- 열린 중계가 되지 않게 한국 범위(경도 124~132°, 위도 33~39.5°)에 걸치는 z 0~14 타일만 받는다. 인증키는 쓰지 않는다(그래서 503 이 없다).
- PNG 응답이라 JSON 예제는 없다. 원천 404 는 404(하루 CDN 캐시)로 돌려준다.

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `invalid-query` · `out-of-range` | invalid-query(쿼리 이름·형식) · out-of-range(한국 범위 밖이거나 z 15 이상) |
| 404 | `not-found` | not-found(원천에 그 타일이 없음). Cache-Control: public, s-maxage=86400 |
| 405 | `method` | GET·HEAD 만 허용(Allow 헤더) |
| 429 | `budget-exhausted` | 이 서버의 시간당 원천 호출 상한(TERRAIN_UPSTREAM_PER_HOUR). budget-exhausted |
| 502 | `upstream` | 원천 서비스 오류(원인 문구는 싣지 않음). Cache-Control: no-store |

### 예제

## 9. `GET /api/bus` — 버스 위치(요청 시에만)

배포된 번들(regions/<slug>/infra.json)의 live 노선 차량 위치. 사용자가 '버스 위치 조회'를 누를 때만 부른다. 오류 모양이 RFC 7807 이 아니라 BusError 이다(옛 경로 유지).

- operationId: `getBuses`

### 매개변수

| 이름 | 필수 | 형식 | 설명 |
|---|---|---|---|
| `region` | ● | string `^[a-z0-9-]{1,40}$` | 번들 slug |

### 응답 `200`

`application/json` · `Cache-Control: public, s-maxage={ttl}` · 스키마 `BusResponse`

차량 위치. 응답은 ttl 초 동안 서버 캐시·CDN 이 나눠 쓴다

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `at` | string(date-time) | ● |  |
| `ttl` | integer 60~ | ● |  |
| `buses` | object[] | ● |  |
| `buses[].r` | string | ● |  |
| `buses[].v` | string | ● |  |
| `buses[].lon` | number | ● |  |
| `buses[].lat` | number | ● |  |
| `buses[].ord` | integer \| null |  |  |
| `buses[].stop` | string \| null |  |  |
| `failed` | string[] |  |  |

### 동작

- 어느 노선을 부를지는 요청이 정하지 못한다(번들의 live 노선만). 오류 모양이 RFC 7807 이 아니라 `{ "error": "<코드>" }` 이다(옛 경로 유지).

### 오류

| HTTP | `code` | 설명 |
|---|---|---|
| 400 | `query` | 쿼리 오류 |
| 404 |  | 실시간 노선이 없는 지역 |
| 405 | `method` | GET·HEAD 만 |
| 429 |  | 키 한도(Retry-After) |
| 502 | `upstream` | 원천 오류 |
| 503 | `not-configured` | 키 없음 |

### 예제

**인천 계양구(앞 3대)** (`tests/fixtures/api/bus-gyeyang.json`)

```json
{
  "at": "2026-10-06T00:27:31.420Z",
  "ttl": 60,
  "buses": [
    {
      "r": "ICB365000050",
      "v": "인천70바2745",
      "lon": 126.688533,
      "lat": 37.617053,
      "ord": 12,
      "stop": "불로대곡동행정복지센터"
    },
    {
      "r": "ICB365000050",
      "v": "인천70바2694",
      "lon": 126.707736,
      "lat": 37.59642,
      "ord": 25,
      "stop": "호반써밋1차아파트"
    },
    "…"
  ]
}
```

## 10. 공통 스키마

### `Problem`

RFC 7807 problem+json. type 은 '/problems/<code>' 이고 code 는 아래 목록 중 하나. 오류 문구에는 인증키·원천 URL·원천 오류 문구를 싣지 않는다.

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | string `^/problems/[a-z0-9-]+$` | ● |  |
| `title` | string | ● |  |
| `status` | integer 400~599 | ● |  |
| `code` | `invalid-query` · `invalid-code` · `invalid-cell` · `unsupported-level` · `unknown-code` · `unknown-project` · `method` · `keys-exhausted` · `budget-exhausted` · `not-configured` · `upstream` · `out-of-range` · `not-found` | ● |  |
| `detail` | string | ● |  |
| `reason` | string |  | invalid-code·invalid-query 의 세부 사유(empty·not-digits·bad-length·unknown-sido·bad-pnu·bad-project·type-mismatch·too-short·too-long) |
| `retryAfterSec` | integer 1~ |  | 429 일 때 다시 시도할 때까지 초(Retry-After 헤더와 같음) |
| `sgg` | string `^\d{5}$` |  |  |
| `suggestions` | object[] |  | unknown-code(법정동)일 때 같은 시군구의 법정동 후보 8개 이내 |
| `project` | string `^PRJ-\d{5}-\d{4}$` |  | unknown-project 일 때 요청한 사업 id |

### `Position`

[경도, 위도] WGS84(한국 범위)

`{"type":"array","description":"[경도, 위도] WGS84(한국 범위)","minItems":2,"maxItems":2,"prefixItems":[{"type":"number","minimum":120,"maximum":135},{"type":"number","minimum":30,"maximum":45}]}`

### `Bbox`

[최소경도, 최소위도, 최대경도, 최대위도]

`{"type":"array","description":"[최소경도, 최소위도, 최대경도, 최대위도]","minItems":4,"maxItems":4,"items":{"type":"number"}}`

### `Geometry`

GeoJSON Polygon 또는 MultiPolygon(경계는 점 수를 줄여 단순화함)

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `type` | `Polygon` · `MultiPolygon` | ● |  |
| `coordinates` | any[] | ● |  |

### `Tier`

열리는 방식. bundle=번들이 있는 시군구(등급 A), req=번들 없는 법정동·필지(등급 B: 경계·건물·인허가·기반시설을 요청 시 조회), edge=번들 없는 시군구(등급 C: 경계만)

`{"type":"string","enum":["bundle","req","edge"],"description":"열리는 방식. bundle=번들이 있는 시군구(등급 A), req=번들 없는 법정동·필지(등급 B: 경계·건물·인허가·기반시설을 요청 시 조회), edge=번들 없는 시군구(등급 C: 경계만)"}`

### `Coverage`

{tier:'A'} 이면 regions/<slug> 번들이 있고, {tier:'none'} 이면 번들이 없어 요청 시 조회로 연다

`{"oneOf":[{"type":"object","required":["tier"],"properties":{"tier":{"const":"none"}},"additionalProperties":false},{"type":"object","required":["tier","slug","name","updatedAt","visibility"],"properties":{"tier":{"const":"A"},"slug":{"type":"string","pattern":"^[a-z0-9-]{1,40}$"},"name":{"type":"string"},"updatedAt":{"type":["string","null"]},"visibility":{"type":"string","enum":["public","preview"]}}}],"description":"{tier:'A'} 이면 regions/<slug> 번들이 있고, {tier:'none'} 이면 번들이 없어 요청 시 조회로 연다"}`

### `PartialDate`

원천이 연·월까지만 적은 날짜는 YYYY-MM · YYYY 로 온다(예정일)

`{"type":"string","pattern":"^\\d{4}(-\\d{2}(-\\d{2})?)?$","description":"원천이 연·월까지만 적은 날짜는 YYYY-MM · YYYY 로 온다(예정일)"}`

## 11. 화면(클라이언트) 계약

| 항목 | 규칙 | 구현·시험 |
|---|---|---|
| 주소 매개변수 | `?pnu=` > `?bjd=` > `?sgg=` > `?code=` 중 앞선 하나가 `?region=` 보다 우선. 보던 상태(`mode`·`panel`·`ring` …)는 이동해도 남고 `region`·`block`·`at` 은 지운다 | `assets/js/region.js` `codeQuery`·`codeUrl`, README 표 |
| 열기 순서 | `resolve`(geometry=1) → coverage `A` 면 번들, 아니면 빈 번들 + `permits` → 단지가 있으면 `infra`(15초까지만 기다리고 못 받으면 점검 없이 열며 자료 안내에 이유) | `region.js` `boot`·`emptyBundle` |
| 어댑터 | `permits` → 번들 단지 모양(`permitsToProjects`: 윤곽=필지, `sponsorClass:"unknown"`, 건물대장 근거 메모·출처), `infra` → 번들 `infra.json` 모양(`schools`·`stops`·`sources`) | `region.js`, 번들-어댑터-정의서 |
| 건물 | 지도에 보이는 0.01° 칸마다 `buildings`(최대 12칸 동시 3, 60,000동 상한), 번들이 있으면 번들 밖만 | `app.js` `DYN` |
| 주소 이동 입력줄 | `search` 후보 → 위 매개변수로 이동. 상태 4가지(대기 .62 · 입력 중 .88 · 이동 중 · 비활성 .46 불투명도). 404·405·503·429 는 비활성 | `assets/js/goto.js`, 스펙 2.5 |
| 실패해도 | 인허가·기반시설·검색이 실패해도 경계와 건물은 열린다(자료 안내·banner 에 이유) | `region.js` |

## 12. 바꾸는 규칙

- **하위 호환**: 응답에 항목을 *더하는* 것은 같은 버전에서 가능(화면은 모르는 항목을 무시). 항목을 지우거나 형식·뜻을 바꾸거나 오류 코드를 바꾸면 `/api/v2` 로 올린다.
- **절차**: `schemas/api/openapi.json` 수정 → `node scripts/capture-fixtures.js`(운영 응답 다시 받기, 키 풀 한도 때문에 호출 사이 1.2초) → `node scripts/gen-api-docs.js` → `node --test tests/js/contract.test.cjs`.
- **전국 점검**: `node scripts/smoke.js [주소]` 가 표본 59곳(`tests/smoke/regions.json`)을 검색 → 해석 → 건물 → 인허가 → 기반시설 순으로 불러 열림·경고를 표로 보여 준다(호출 사이 0.9초).
