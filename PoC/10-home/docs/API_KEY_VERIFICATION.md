# HOME API 키 최초 실제 응답 검증 — 2026-10-02 KST

이 문서는 최초 소량 인증 검증 기록입니다. 이후 요청으로 52개 API 표본을 실제 수집·저장하고 홈페이지 조회를 추가했습니다. 현재 결과는 [TEST_COLLECTION.md](TEST_COLLECTION.md)를 확인하세요.

설정된 HOME 전용 키로 공식 API에 소량의 읽기 요청을 보냈으며 세 키 모두 인증 및 데이터 응답을 확인했습니다. 키 원문·키 포함 URL·원본 오류문은 출력하거나 보관하지 않았습니다.

| 서비스 | 검증 endpoint (키 제외) | 실제 결과 |
| --- | --- | --- |
| 청약홈 | `https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail` | HTTP 200, JSON, `page=1 / perPage=1` 요청에 공고 1건 반환 |
| 건축HUB 주택인허가 | `https://apis.data.go.kr/1613000/HsPmsHubService/getHpBasisOulnInfo` | HTTP 200, JSON, 결과코드 `00`, 서울 강남구·개포동 기본개요 1건 반환 |
| VWorld 주소 좌표 | `https://api.vworld.kr/req/address` | HTTP 200, `response.status=OK`, 서울·경기 공공시설 주소 2건 좌표 변환 성공 |

## 표본과 해석

- 청약홈은 공고와 일정 정보 schema를 반환했습니다. 응답 `totalCount=2,885`는 전역 원천 공고 수이며 지역·기간 필터 집계에는 `matchCount`를 사용해야 합니다. 현재 서울·경기 진행사업 수가 아닙니다.
- 건축HUB는 `sigunguCd=11680`, `bjdongCd=10300`, `numOfRows=1`, `_type=json`으로 조회했습니다. 총건수 1,157은 해당 지역의 원천 개요 수이며 정책 실적이나 현재 진행사업 수가 아닙니다.
- VWorld는 실제 운영 출처 `https://www.minslab.kr`를 domain/Referer로 사용해 `getcoord`, `ROAD`, `EPSG:4326`을 검증했습니다.

| VWorld 표본 | 경도 | 위도 |
| --- | ---: | ---: |
| 서울시청: 서울특별시 중구 세종대로 110 | 126.97834678 | 37.56670101 |
| 경기도청: 경기도 수원시 영통구 도청로 30 | 127.05382022 | 37.28879473 |

키는 `PoC/10-home/.env`에 저장하며 실행 컨테이너에도 세 항목을 반영했습니다. 공개 API는 설정 여부만 제공하고 키 원문은 제공하지 않습니다.

## 검증 범위

이번 검증은 인증·해당 endpoint 이용 권한·표본 응답 확인입니다. 대량 페이지 수집, 서울·경기 최신 기간 전체 조회, 원천 PK 연결, 정책·사업·공급묶음 매핑, VWorld 배경지도·WFS/경계 API의 개별 응답은 아직 검증하지 않았습니다.

최초 인증 검증 당시에는 세 connector가 미활성 상태였습니다. 현재는 수동 `TEST_SAMPLE` 수집으로 활성화됐습니다. 기존 7개 웹·파일 원천과 검토 후보 데이터를 유지하고 API 표본을 공식 정책 실적에 합산하지 않습니다.

공식 명세: [청약홈](https://www.data.go.kr/data/15098547/openapi.do), [건축HUB](https://www.data.go.kr/data/15136560/openapi.do), [VWorld 공식 2026 교육 예제](https://github.com/V-world/V-world_API_sample/tree/master/%EB%B8%8C%EC%9D%B4%EC%9B%94%EB%93%9C_%EA%B5%90%EC%9C%A1/2026%EB%85%84_%EB%B8%8C%EC%9D%B4%EC%9B%94%EB%93%9C_%EA%B5%90%EC%9C%A1).
