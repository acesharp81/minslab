"""Verified application links. Planned connectors never report as connected."""
import os

GUIDES = [
    dict(id="building_register", name="건축HUB 건축물대장정보", priority="우선 신청", mode="API", key_env="POC10_BUILDING_REGISTER_SERVICE_KEY",
         existing_key_env="POC10_BUILDING_HUB_SERVICE_KEY", url="https://www.data.go.kr/data/15134735/openapi.do",
         purpose="주소·대장 PK·사용승인일 교차 검증으로 준공 근거 확대",
         gap="주택인허가 API와 별도 서비스입니다. 기존 재고를 포함하며 사용승인은 주택법 사용검사·실입주와 구분합니다.",
         steps=["공공데이터포털 로그인 → 위 서비스의 활용신청", "활용 목적: HOME 서울·경기 주택사업 진행 검증, 서비스 URL: https://www.minslab.kr/poc/home/", "승인 후 마이페이지의 해당 API 인증키(Decoding) 확인", "기존 인증키와 동일하면 재발급하지 않고 서비스 승인 확인. 별도 키는 HOME 서버 설정에 저장"],
         readiness="CONNECTOR_PENDING"),
    dict(id="lh_notice", name="LH 분양임대공고문", priority="공공임대 보완", mode="API", key_env="POC10_LH_NOTICE_SERVICE_KEY",
         existing_key_env="POC10_CHEONGYAK_SERVICE_KEY", url="https://www.data.go.kr/data/15058530/openapi.do",
         purpose="청약홈에서 빠지는 LH 분양·임대 공고와 원문 확보",
         gap="공고문 조회는 실제 입주량 증명이 아닙니다. 공급 상세·블록 연결 및 기존 공고 중복 제거 필요.",
         steps=["공공데이터포털 로그인 → 해당 서비스 활용신청", "분양주택·임대주택 조회 목적과 HOME 서비스 URL 입력", "승인 후 일반 인증키(Decoding) 확인 → 기존 포털 키와 비교", "HOME 서버 설정에 저장 후 응답·기간·공급 상세 스키마 검증"], readiness="CONNECTOR_PENDING"),
    dict(id="molit_statistics", name="국토교통 통계누리", priority="지역 통계 대조", mode="API", key_env="POC10_MOLIT_STAT_API_KEY", existing_key_env=None,
         url="https://stat.molit.go.kr/portal/api/info.do", purpose="서울·경기 월별 분양승인·착공·준공 및 연간 인허가 공식 총계와 수집 범위 대조",
         gap="지역 전체 통계에는 민간 사업도 포함됩니다. 개별 정책 달성량에 직접 합산하지 않습니다.",
         steps=["통계누리 공유서비스 로그인 → 서비스신청 및 내역", "인증키신청 및 이용내역에서 키 신청", "OPEN API 신청 및 신청현황에서 필요한 주택건설 통계표·양식 선택", "시도·단위·기간·통계표 변경을 검증한 뒤 서버 설정에 저장"], readiness="CONNECTOR_PENDING"),
    dict(id="sh_supply_plan", name="SH 주택분양 공급계획", priority="서울 계획·과거 이력", mode="API", key_env="POC10_SH_SERVICE_KEY", existing_key_env=None,
         url="https://www.data.go.kr/data/15008820/fileData.do", purpose="사업·주택형별 계획 물량·공급 예정월과 과거 공개본 조회",
         gap="공개본 간 동일 사업이 반복됩니다. 계획과 실제 공급을 구분하며 사전·본청약 물량은 합계에 다시 더하지 않습니다.",
         steps=["공공데이터포털 로그인 → 데이터셋의 Open API 탭 → 활용신청", "승인된 공공데이터포털 인증키를 HOME SH 전용 설정에 저장", "자료 연도별 공개본과 수집 결과 확인"], readiness="CONNECTOR_READY"),
    dict(id="sh_redevelopment", name="SH 공공재개발·재건축 사업현황", priority="서울 사업·위치·정책 연결", mode="API", key_env="POC10_SH_SERVICE_KEY", existing_key_env=None,
         url="https://www.data.go.kr/data/15124798/fileData.do", purpose="사업 위치·전체 계획 세대수·임대 세대수·원천 추진현황 조회",
         gap="최신 공개본의 원천 기준일은 2023-11-02입니다. 현재 진행 상태를 확정하지 않으며 임대 세대수는 전체 세대수의 일부입니다.",
         steps=["공공데이터포털의 해당 데이터셋 Open API 탭에서 별도 활용신청", "승인된 포털 키로 SH 전용 수집기를 호출", "과거 현황과 현재 사업 근거를 대조한 뒤 정책 귀속 검토"], readiness="CONNECTOR_READY"),
    dict(id="sh_files", name="SH 주택관리현황 파일", priority="서울 범위 확대", mode="FILE", key_env=None, existing_key_env=None,
         url="https://data.seoul.go.kr/dataList/OA-12027/S/1/datasetView.do", purpose="SH 관리 단지·주소·유형 자료로 서울 사업 범위 대조",
         gap="현재 확인 자료는 XLSX 파일이며 API 키가 필요하지 않습니다. 기존 관리 재고와 신규 공급·연간 실적을 구분해야 합니다.",
         steps=["공식 데이터셋의 파일내려받기에서 최신 XLSX 확인", "사업·주소·기준일·물량의 의미 검증 후 별도 수집기 연결"], readiness="CONNECTOR_PENDING"),
    dict(id="gh_files", name="GH 재건축매입임대 현황 파일", priority="경기 범위 확대", mode="FILE", key_env=None, existing_key_env=None,
         url="https://www.data.go.kr/data/15112600/fileData.do", purpose="GH 매입임대 사업·소재지·물량 자료 확보",
         gap="CSV 공개 파일은 API 키 없이 확보 가능합니다. 매입임대는 신축 공급과 별도 지표이며 GH 전체 진행 사업을 대체하지 않습니다.",
         steps=["공공데이터포털 공식 파일자료의 최신 CSV 확인", "공급 유형과 기준일 검증 → GH 사업계획·공고 원문과 연결"], readiness="CONNECTOR_PENDING"),
    dict(id="seoul_openapi", name="서울 열린데이터광장 API", priority="선택 · API 제공 자료 확정 후", mode="API", key_env="POC10_SEOUL_OPEN_API_KEY", existing_key_env=None,
         url="https://data.seoul.go.kr/together/guide/useGuide.do", purpose="서울시 API 제공 주택·행정 자료 확장",
         gap="SH 파일 수집에 이 키가 필요한 것은 아닙니다. 사용할 주택 데이터셋의 Open API 제공 여부부터 확인하세요.",
         steps=["서울시 회원가입·로그인 → 인증키 신청/관리", "HOME 활용 목적과 서비스 URL 등록 → 인증키 확인", "Open API가 제공되는 대상 데이터셋·서비스명을 확인 후 연결"], readiness="DATASET_SELECTION_REQUIRED"),
    dict(id="gyeonggi_openapi", name="경기데이터드림 API", priority="선택 · API 제공 자료 확정 후", mode="API", key_env="POC10_GG_OPEN_API_KEY", existing_key_env=None,
         url="https://data.gg.go.kr/portal/openapi/usagePage.do", purpose="경기도·GH API 제공 사업·행정 자료 확장",
         gap="현재 확인 GH 파일 자료에는 이 키가 필요하지 않습니다. API 제공 주택사업 데이터셋을 먼저 선택해야 합니다.",
         steps=["경기데이터드림 로그인 → 인증키 발급", "활용용도·사용 URL·설명 입력 → 발급 요청", "선택 데이터셋의 API 명세에서 서비스명·필터 확인 후 연결"], readiness="DATASET_SELECTION_REQUIRED"),
    dict(id="lh_supply_history",name="LH 과거 공공분양 공급현황",priority="과거 공급 이력",mode="FILE",key_env=None,existing_key_env=None,
         url="https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=727605&mid=a10103040000",purpose="2020~2025 공공분양 블록별 공급년도·공고 호수·주소 확보",
         gap="공고 공급량이며 실제 입주량과 구분. 2018~2019 공급현황 미확보.",steps=["공식 게시물 XLSX 첨부를 자동 수집", "시도·주소·공급 호수·공고일 검증 후 연도별 조회"],readiness="CONNECTOR_PENDING"),
    dict(id="lh_movein_history",name="LH 연간 입주계획 공개본",priority="과거 계획 이력",mode="FILE",key_env=None,existing_key_env=None,
         url="https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=654827&mid=a10103010000",purpose="2022~2026 블록·유형·규모별 입주 예정월과 호수",
         gap="실제 입주량과 구분. 2018~2021 파일 미확보, 2026 원천 총계와 상세 합계 불일치.",steps=["공식 HWPX·DOCX 공개 첨부 자동 수집", "본문 전체 행·전국 합계와 실제 소재지 검증"],readiness="CONNECTOR_PENDING"),
    dict(id="lh_stock",name="LH 단지 준공·입주지정 일정",priority="과거 일정 보완",mode="FILE",key_env=None,existing_key_env=None,
         url="https://www.data.go.kr/data/15080989/fileData.do",purpose="현재 단지정보의 과거 준공·입주지정 날짜 확인",
         gap="현재 재고와 예정일 포함. 과거 월별 실제 공정률·실입주량은 별도 근거 필요.",steps=["공개 CSV 로그인 없이 자동 내려받기", "단지코드·실제 위치·과거 일정·재고 지표 검증"],readiness="CONNECTOR_PENDING"),
    dict(id="lh_progress",name="LH 블록별 실제 공정률 이력",priority="실제 공정률",mode="FILE",key_env=None,existing_key_env=None,
         url="https://apply.lh.or.kr/lhapply/land/cwsttList.do?mi=1352",purpose="블록별 공정률·공사 설명·날짜 이력 수집",
         gap="공개 이력이 없는 연도·블록과 SH·GH 공정률은 별도 확보 필요. 공정률은 공급·입주율과 구분합니다.",
         steps=["API 키 없이 전체 목록과 블록별 공개 상세 페이지 수집", "원본 등록일·사진 기준월을 분리하고 기존 사업과 지구·블록으로 대조"],readiness="CONNECTOR_READY"),
]


def connection_audit(sources):
    connected = [dict(id=s["id"], name=s["name"], status=s["status"], key_configured=s["key_configured"],
                      record_count=s["record_count"], last_success=s["last_success"], url=s["url"])
                 for s in sources if s["id"] in {"cheongyak", "building_hub", "vworld", "building_register", "lh_notice", "molit_statistics", "sh_supply_plan", "sh_redevelopment"}]
    planned = [dict(g, key_configured=bool(g["key_env"] and os.environ.get(g["key_env"])),
                    existing_key_configured=bool(g["existing_key_env"] and os.environ.get(g["existing_key_env"]))) for g in GUIDES]
    by_id = {s["id"]: s for s in sources}
    for guide in planned:
        source = by_id.get(guide["id"])
        if source and source.get("implemented"):
            guide.update(readiness="CONNECTED" if source["status"] == "SUCCESS" else "CONNECTOR_READY",
                         status=source["status"], record_count=source["record_count"], last_success=source["last_success"],
                         error=source.get("error"), stats=source.get("stats", {}))
    return dict(checked_date="2026-10-03", connected=connected, planned=planned,
                notice="실제 수집 배치의 응답·건수로 연결을 확인합니다. 키 원문은 표시하지 않습니다. 건축물 재고·공고·지역 총계는 정책 공급 실적과 구분합니다.")
