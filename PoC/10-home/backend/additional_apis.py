"""Additional verified APIs. Stock, notices and regional totals are not policy actuals."""
import calendar
import json
from collections import Counter

from .api_samples import DISTRICTS, SAMPLE_LIMIT, base, day, key_for, response_json, today
from .collection_period import collection_start
from .collectors import clean, integer

REGISTER_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
LH_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
STAT_URL = "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
STAT_PERIOD_URL = "https://stat.molit.go.kr/portal/api/period.do"
LH_REGIONS = {"11": "서울특별시", "41": "경기도", "28": "인천광역시"}
LH_CATEGORIES = {"05":"분양", "06":"임대", "39":"신혼희망타운"}
STAT_REGIONS = {"서울": "서울특별시", "경기": "경기도"}
STAT_SERIES = [("5372", "1", "MONTH", "준공", "사용검사실적"),
               ("5386", "1", "MONTH", "착공", "착공실적"),
               ("626", "125", "YEAR", "인허가", "인허가실적"),
               ("5557", "1", "MONTH", "분양승인", "순계>합계")]


def parse_register(data, source, region, sigungu, bjdong):
    kind = source.get('register_kind', 'register')
    response = data.get("response", {})
    if str(response.get("header", {}).get("resultCode")) != "00":
        raise ValueError("건축물대장 인증/응답 오류: 서비스 활용승인 확인 필요")
    body = response.get("body", {})
    total = integer(body.get("totalCount"))
    items = body.get("items") or {}
    rows = items.get("item", []) if isinstance(items, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or total is None or len(rows) > min(total, SAMPLE_LIMIT):
        raise ValueError("건축물대장 페이지 schema 변경")
    records, seen = [], set()
    for row in rows:
        address = clean(row.get("platPlc"))
        identifier = clean(row.get("mgmBldrgstPk"))
        if str(row.get("sigunguCd")) != sigungu or str(row.get("bjdongCd")) != bjdong or not address.startswith(region):
            raise ValueError("건축물대장 지역·법정동 불일치")
        if not identifier or identifier in seen:
            raise ValueError("건축물대장 식별자 누락·중복")
        seen.add(identifier)
        purpose = clean(row.get("mainPurpsCdNm"))
        if purpose not in {"공동주택", "단독주택"}:
            continue
        payload = base(source, kind, clean(row.get("bldNm")) or address, region, address, day(row.get("crtnDay")))
        payload.update(source_object_id=identifier, sigungu_code=sigungu, bjdong_code=bjdong,
                       units=integer(row.get("hhldCnt")), unit_basis="건축물 표제부 세대수 · 기존 재고 포함, 신규 공급량 아님",
                       source_date_label="대장 레코드 생성일", main_purpose=purpose, building_dong=clean(row.get("dongNm")),
                       household_count=integer(row.get("hhldCnt")), family_count=integer(row.get("fmlyCnt")),
                       unit_count=integer(row.get("hoCnt")), warnings=["REGISTER_STOCK_NOT_SUPPLY", "USE_APPROVAL_NOT_MOVE_IN"],
                       dates={"건축허가일": day(row.get("pmsDay")), "착공일": day(row.get("stcnsDay")),
                              "건축물 사용승인일": day(row.get("useAprDay"))})
        if payload["units"] == 0:
            payload["warnings"].append("ZERO_UNITS_REVIEW")
        payload.update(block=clean(row.get('block')) or None,lot=clean(row.get('lot')) or None,
            bun=clean(row.get('bun')) or None,ji=clean(row.get('ji')) or None,
            related_lot_count=integer(row.get('bylotCnt')),register_endpoint=source.get('register_endpoint','getBrTitleInfo'))
        from .parcel_identity import enrich_source
        enrich_source(payload, row)
        records.append((kind, identifier, payload))
    return records, total, len(rows)


def collect_register(source, fetcher, service=None):
    records, counts, seen = [], {}, set()
    districts=DISTRICTS;scope_total=None
    if service is not None:
        from .building_scope import next_districts
        districts,counts,scope_total=next_districts(service,source['id'])
    for region, sigungu, bjdong, label in districts:
        expected, fetched, page, residential = None, 0, 1, 0
        while True:
            params = dict(serviceKey=key_for(source), sigunguCd=sigungu, bjdongCd=bjdong,
                          numOfRows=SAMPLE_LIMIT, pageNo=page, _type="json")
            url=REGISTER_URL.replace('getBrTitleInfo', source.get('register_endpoint','getBrTitleInfo'))
            data = response_json(fetcher.get(url, "json", params=params))
            current, total, count = parse_register(data, source, region, sigungu, bjdong)
            if expected is None:
                expected = total
            if total != expected or count != min(SAMPLE_LIMIT, max(0, total - fetched)):
                raise ValueError("건축물대장 페이지 누락·수집 중 건수 변경")
            body = data["response"]["body"]
            if "pageNo" in body and str(body["pageNo"]) != str(page):
                raise ValueError("건축물대장 요청 페이지 불일치")
            items = body.get("items") or {}
            raw = items.get("item", [])
            raw = [raw] if isinstance(raw, dict) else raw
            for row in raw:
                identifier = clean(row.get("mgmBldrgstPk"))
                if identifier in seen:
                    raise ValueError("건축물대장 페이지·법정동 간 중복")
                seen.add(identifier)
            records.extend(current)
            residential += len(current)
            fetched += count
            if fetched == total:
                break
            if page >= 10000:
                raise ValueError("건축물대장 페이지 상한 초과: 기존 데이터 유지")
            page += 1
        counts[sigungu+bjdong if service is not None else label] = dict(matching_records=total, fetched=fetched, residential_records=residential,
                             pages=page, complete_query=True,legal_dong_code=sigungu+bjdong,label=label)
        if service is not None:
            from .db import now
            counts[sigungu+bjdong]['checked_at']=now().isoformat()
    if service is not None:
        from .building_scope import expansion_stats
        return records,dict(expansion_stats(counts,scope_total,len(records)),collection_mode='TEST_SAMPLE',complete_population=False,page_size=SAMPLE_LIMIT)
    if not records:
        raise ValueError("주거용 건축물대장 표본 없음: 기존 데이터 유지")
    return records, dict(collection_mode="TEST_SAMPLE", complete_population=False, complete_query=True,
                         district_counts=counts, page_size=SAMPLE_LIMIT,
                         scope_note="6개 법정동 전체 조회 페이지 중 주거용 표제부. 과거 사용승인·기존 재고 포함. 서울·경기 전체 범위 아님. 호수(hoCnt)를 세대수로 대체하지 않음")


def parse_lh_notices(data, source, region_code, category, start, end):
    if not isinstance(data, list):
        raise ValueError("LH 공고 인증/응답 schema 확인 필요")
    result = next((x for x in data if isinstance(x, dict) and "resHeader" in x), {})
    headers = result.get("resHeader") or []
    if not headers or headers[0].get("SS_CODE") != "Y":
        raise ValueError("LH 공고 인증/응답 오류: 활용승인 확인 필요")
    rows = result.get("dsList", [])
    if not isinstance(rows, list) or len(rows) > SAMPLE_LIMIT:
        raise ValueError("LH 공고 페이지 schema 변경")
    total = integer(rows[0].get("ALL_CNT")) if rows else 0
    if total is None or total < len(rows):
        raise ValueError("LH 공고 총건수 미확인")
    records, seen = [], set()
    excluded = {"nonhousing": 0, "multi_region": 0}
    for row in rows:
        region = clean(row.get("CNP_CD_NM"))
        announced = day(row.get("PAN_NT_ST_DT"))
        if str(row.get("UPP_AIS_TP_CD")) != category or not announced or not start <= announced <= end:
            raise ValueError("LH 공고 지역·유형·공고 기간 불일치")
        if integer(row.get("ALL_CNT")) != total:
            raise ValueError("LH 공고 총건수 불일치")
        pan_id, subtype = clean(row.get("PAN_ID")), clean(row.get("AIS_TP_CD"))
        identifier = ":".join([pan_id, category, subtype, region_code, clean(row.get("CCR_CNNT_SYS_DS_CD"))])
        if not pan_id or not subtype or identifier in seen or not clean(row.get("PAN_NM")):
            raise ValueError("LH 공고 식별자 누락·중복")
        seen.add(identifier)
        # Regional queries also return multi-region notices (e.g. Incheon + Gimpo).
        # Preserve the raw response but do not assign the whole notice to Gyeonggi.
        if region != LH_REGIONS[region_code]:
            if region.endswith(" 외") or region == "전국":
                excluded["multi_region"] += 1
                continue
            raise ValueError("LH 공고 시도 필터 불일치")
        # The rental endpoint also returns childcare facility tenders.
        if subtype == "40" or "어린이집" in clean(row.get("AIS_TP_CD_NM")):
            excluded["nonhousing"] += 1
            continue
        payload = base(source, "lh_notice", clean(row.get("PAN_NM")), region, "시도 공고 · 상세 주소 미제공", announced)
        payload.update(source_object_id=identifier, notice_no=pan_id, source_date_label="LH 공고게시일 PAN_NT_ST_DT",
                       unit_basis="공고 목록에는 공급 세대수 미제공 · 정정·재공고와 공급 상세 확인 필요",
                       notice_category=clean(row.get("UPP_AIS_TP_NM")), notice_type=clean(row.get("AIS_TP_CD_NM")),
                       notice_status=clean(row.get("PAN_SS")), evidence_url=clean(row.get("DTL_URL")) or source["url"],
                       warnings=["NOTICE_DETAIL_UNITS_REQUIRED"],
                       dates={"원천 공고일 PAN_DT": day(row.get("PAN_DT")), "공고게시일 PAN_NT_ST_DT": announced, "공고 마감일": day(row.get("CLSG_DT"))})
        records.append(("lh_notice", identifier, payload))
    return records, total, len(rows), excluded, seen


def collect_lh_notices(source, fetcher):
    start, end = collection_start().isoformat(), today().isoformat()
    records, counts, seen = [], {}, set()
    for region_code, region in LH_REGIONS.items():
        for category in LH_CATEGORIES:
            page, fetched, expected = 1, 0, None
            excluded = Counter()
            while True:
                params = dict(serviceKey=key_for(source), PG_SZ=SAMPLE_LIMIT, PAGE=page, _type="json",
                              UPP_AIS_TP_CD=category, CNP_CD=region_code,
                              PAN_ST_DT=start.replace("-", ""), PAN_ED_DT=end.replace("-", ""))
                try:
                    data = json.loads(fetcher.get(LH_URL, "json", params=params))
                except (ValueError, UnicodeDecodeError):
                    raise ValueError("LH 공고 JSON 응답 미확인") from None
                current, total, size, skipped, ids = parse_lh_notices(data, source, region_code, category, start, end)
                if expected is None:
                    expected = total
                if total != expected or total > 10000 or size != min(SAMPLE_LIMIT, total - fetched) or seen.intersection(ids):
                    raise ValueError("LH 공고 페이지 누락·중복·수집 중 건수 변경")
                seen.update(ids)
                records.extend(current)
                fetched += size
                excluded.update(skipped)
                if fetched == total:
                    break
                page += 1
            counts[region + " " + LH_CATEGORIES[category]] = dict(
                matching_records=expected, fetched=fetched, excluded_nonhousing=excluded["nonhousing"],
                excluded_multi_region=excluded["multi_region"],
                collected=fetched-sum(excluded.values()), pages=page, complete_query=True,
                status="COLLECTED" if expected else "NO_RESULTS_UNVERIFIED")
    if not records:
        raise ValueError("수도권 LH 공고 없음: 기존 데이터 유지")
    annual = Counter((r[2]["source_date"][:4], r[2]["region"]) for r in records)
    return records, dict(collection_mode="TEST_SAMPLE", complete_population=False, period_start=start, period_end=end,
                         region_counts=counts, annual_counts=[dict(year=int(y), region=r, records=n) for (y,r),n in sorted(annual.items())],
                         scope_note="2018년 정책 기원부터 서울·경기·인천 분양·임대·신혼희망타운 전체 조회 페이지. 어린이집과 시도별 배분 미확인 복수지역 공고는 표시 제외하고 원문 보존. 공고 건수는 공급량·입주량 아님")


def parse_statistics(data, source, series, start, end):
    regions = source.get('stat_regions', STAT_REGIONS)
    form, style, frequency, label, metric = series
    status = data.get("result_status", {}).get("status_code")
    if status == "INFO-200":
        return []  # No result is unknown, never a synthetic zero.
    if status != "INFO-000":
        raise ValueError("통계누리 인증·통계표 응답 오류: " + (status if status in {"INFO-100", "INFO-300", "ERROR-301", "ERROR-334", "ERROR-335"} else "상태 미확인"))
    result = data.get("result_data", {})
    rows = result.get("formList")
    if result.get("unitName") != "호" or not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("통계누리 단위·행 schema 변경")
    records, seen = [], set()
    for row in rows:
        if label == "분양승인":
            if (not source.get("all_regions") and row.get("구분1") != "수도권") or row.get("구분2") not in regions:
                continue
            region_name = row["구분2"]
            components = {name: integer(row.get("순계>" + name)) for name in ("분양", "임대", "조합")}
            if any(value is None for value in components.values()) or sum(components.values()) != integer(row.get(metric)):
                raise ValueError("통계누리 분양승인 순계·구성항목 불일치")
        else:
            if row.get("시도별") not in regions:
                continue
            if row.get("부문명") != "총계" or row.get("구  분", row.get("구분명")) != "총계":
                continue
            region_name = row["시도별"]
        period = str(row.get("date", ""))
        if len(period) != (6 if frequency == "MONTH" else 4) or not period.isdigit() or not start <= period <= end:
            raise ValueError("통계누리 조회 기간 불일치")
        region = regions[region_name]
        identifier = f"{form}:{style}:{period}:{region_name}"
        units = integer(row.get(metric))
        if identifier in seen or units is None:
            raise ValueError("통계누리 총계 중복·실적 미확인")
        seen.add(identifier)
        year, month = int(period[:4]), int(period[4:]) if frequency == "MONTH" else 12
        if not 1 <= month <= 12:
            raise ValueError("통계누리 월 형식 변경")
        period_end = f"{year:04d}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}"
        payload = base(source, "statistic", f"{region} {period[:4]}년 " + (f"{month}월 " if frequency == "MONTH" else "") + label,
                       region, "시도 전체 공식 통계", period_end)
        payload.update(source_object_id=identifier, units=units, unit_basis="시도 전체 총계 · 민간 포함 · 정책 실적 직접 합산 제외",
                       source_date_label="통계 대상 기간 말일 (공표일 아님)", statistic_metric=label, statistic_field=metric,
                       statistic_period=period, statistic_frequency=frequency, form_id=form, style_num=style,
                       statistic_unit="호", warnings=["REGIONAL_TOTAL_NOT_POLICY_ACTUAL"],
                       dates={"통계 대상 시작일": f"{year:04d}-{month if frequency == 'MONTH' else 1:02d}-01", "통계 대상 종료일": period_end})
        if label == "분양승인":
            payload["supply_approval_breakdown"] = components
            payload["unit_basis"] = "공동주택 분양승인 순계 · 분양·임대·조합 포함 · 청약공고·입주실적 아님"
        # Whitelist public fields; cert_id in the API response must never reach a payload.
        records.append(("statistic", identifier, payload))
    return records


def collect_statistics(source, fetcher):
    records, coverage, seen = [], [], set()
    begin_year = collection_start().year
    for series in STAT_SERIES:
        form, style, frequency, label, metric = series
        metadata = response_json(fetcher.get(STAT_PERIOD_URL, "json", params=dict(form_id=form, style_num=style)))
        periods = [str(p.get("MNG_DIV_VL", "")) for p in metadata.get("periodList", [])]
        width = 6 if frequency == "MONTH" else 4
        valid = [p for p in periods if len(p) == width and p.isdigit() and p <= today().strftime("%Y%m" if width == 6 else "%Y")]
        if not valid:
            raise ValueError("통계누리 최신 공개 기간 미확인")
        latest = max(valid)
        if frequency == "MONTH":
            queries = [f"{y:04d}{m:02d}" for y in range(begin_year, int(latest[:4])+1) for m in range(1,13) if f"{y:04d}{m:02d}" <= latest]
        else:
            queries = [str(y) for y in range(begin_year, int(latest)+1)]
        missing = []
        # Full response includes all regions; two months stay below the 1,000-row cap.
        step = 2 if frequency == "MONTH" else 1
        series_count = 0
        for offset in range(0,len(queries),step):
            chunk = queries[offset:offset+step]
            data = response_json(fetcher.get(STAT_URL, "json", params=dict(key=key_for(source), form_id=form,
                                         style_num=style, start_dt=chunk[0], end_dt=chunk[-1])))
            current = parse_statistics(data, source, series, chunk[0], chunk[-1])
            present = {(r[2]["statistic_period"], r[2]["region"]) for r in current}
            missing.extend(dict(period=p, region=r) for p in chunk for r in source.get('stat_regions', STAT_REGIONS).values() if (p,r) not in present)
            for record in current:
                if record[1] in seen:
                    raise ValueError("통계누리 조회 묶음 간 중복")
                seen.add(record[1])
            records.extend(current)
            series_count += len(current)
        coverage.append(dict(metric=label, form_id=form, style_num=style, frequency=frequency,
                             period_start=queries[0], period_end=latest, records=series_count,
                             complete_query=not missing, missing_period_regions=missing))
    if not records:
        raise ValueError("통계누리 지역 총계 없음: 기존 데이터 유지")
    return records, dict(collection_mode="TEST_SAMPLE", complete_population=False,
                         period_start=str(begin_year), series=coverage,
                         unavailable_series=[dict(metric="인허가", frequency="MONTH", reason="5375 API 개방 취소(INFO-300), 정상 제공 연간 626/125 사용")],
                         scope_note="정책 기원 2018년부터 "+"·".join(source.get('stat_regions',STAT_REGIONS).values())+" 월별 분양승인·착공·준공 및 연간 인허가. 시도 총계만 수록하여 소계 중복 제외. 최신 공개 기간까지 수집")
