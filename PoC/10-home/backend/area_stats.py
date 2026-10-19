"""Official Seoul/Gyeonggi area context. These are background indicators, not housing completions."""
import json
import os
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from .db import Revision
from .api_samples import today

SGIS = "https://sgisapi.mods.go.kr/OpenAPI3/"
KOSIS = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SGIS_DOC = "https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html"
KOSIS_DOC = "https://kosis.kr/openapi/devGuide/devGuide_0201List.do"
EXPECTED = {"서울특별시": 25, "경기도": 44}
EXPECTED_CITIES = {"서울특별시": 25, "경기도": 31}
GYEONGGI = set("수원시 성남시 의정부시 안양시 부천시 광명시 평택시 동두천시 안산시 고양시 과천시 구리시 남양주시 오산시 시흥시 군포시 의왕시 하남시 용인시 파주시 이천시 안성시 김포시 화성시 광주시 양주시 포천시 여주시 연천군 가평군 양평군".split())


def number(value):
    if value is None or str(value).strip() in {"", "-", "N/A", "...", "x", "X"}:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def count(value):
    n = number(value)
    return int(n) if n is not None and n >= 0 and n == n.to_integral_value() else None


def sgis_geography(region, name):
    if region in ("서울특별시", "인천광역시"):
        return name if re.fullmatch(r"[가-힣]+[구군]", name or "") else None
    city = (name or "").split()[0]
    return city if city in GYEONGGI else None


def sgis_data(fetcher, path, token, **params):
    body = json.loads(fetcher.get(SGIS + path, "json", params={"accessToken": token, **params}))
    if not isinstance(body, dict):
        raise ValueError("SGIS 응답 형식 확인 필요")
    code = body.get("errCd")
    if code == -100:
        return None
    if code != 0 or not isinstance(body.get("result"), list):
        raise ValueError("SGIS 응답 코드·목록 확인 필요")
    return body["result"]


def sgis_token(fetcher):
    key = os.environ.get("POC10_SGIS_CONSUMER_KEY", "").strip()
    secret = os.environ.get("POC10_SGIS_CONSUMER_SECRET", "").strip()
    if not key or not secret:
        raise ValueError("SGIS 인증 설정 미확보")
    # Authentication responses contain a short-lived access token. Never persist them as raw evidence.
    try:
        response = fetcher.client.get(SGIS + "auth/authentication.json",
                                      params={"consumer_key": key, "consumer_secret": secret})
        response.raise_for_status()
        body = response.json()
        token = body.get("result", {}).get("accessToken")
    except Exception:
        raise RuntimeError("SGIS 인증 연결 실패") from None
    if body.get("errCd") != 0 or not isinstance(token, str) or not token:
        raise ValueError("SGIS 인증 상태 확인 필요")
    return token


def collect_sgis_area(source, fetcher, service):
    token = sgis_token(fetcher)
    latest = None
    for year in range(date.today().year, 2017, -1):
        probe = sgis_data(fetcher, "stats/population.json", token, year=year, adm_cd="11", low_search=1)
        if probe:
            latest = year
            break
    if latest is None:
        raise ValueError("SGIS 제공 연도 확인 필요")
    prior = service.latest_collection_stats(source["id"])
    completed = {int(y) for y in prior.get("years_complete", []) if str(y).isdigit()}
    region_completed=set(prior.get('region_years_complete',[]))
    if not region_completed:
        # Legacy checkpoints covered Seoul/Gyeonggi only; Incheon must backfill.
        region_completed={f'{y}:{r}' for y in completed for r in ('서울특별시','경기도')}
    years=[y for y in range(2018,latest+1) if y==latest or any(f'{y}:{r}' not in region_completed for r in ('서울특별시','경기도','인천광역시'))]
    sectors = sgis_data(fetcher, "stats/industrycode.json", token, class_deg=11)
    if not sectors or not all(re.fullmatch(r"[A-Z]", str(x.get("class_code", ""))) for x in sectors):
        raise ValueError("SGIS 산업분류표 확인 필요")
    classes = {x["class_code"]: x["class_nm"] for x in sectors}
    records = []
    coverage = {}
    for year in years:
        for region, adm_cd in (("서울특별시", "11"), ("경기도", "31"), ("인천광역시", "23")):
            if year!=latest and f'{year}:{region}' in region_completed:continue
            data = {}
            for endpoint in ("population", "household", "company"):
                rows = sgis_data(fetcher, f"stats/{endpoint}.json", token, year=year, adm_cd=adm_cd, low_search=1)
                if rows is None or len(rows) not in ((10,11) if region=="인천광역시" and year>=2026 else (10,) if region=="인천광역시" else (EXPECTED[region],)):
                    raise ValueError(f"SGIS {year}년 {region} {endpoint} 행 수 확인 필요")
                keyed = {str(row.get("adm_cd")): row for row in rows}
                if len(keyed) != len(rows):
                    raise ValueError("SGIS 행정코드 중복 확인 필요")
                data[endpoint] = keyed
            if not (set(data["population"]) == set(data["household"]) == set(data["company"])):
                raise ValueError("SGIS 인구·가구·사업체 지역 범위 불일치")
            industry = defaultdict(dict)
            for class_code in classes:
                rows = sgis_data(fetcher, "stats/company.json", token, year=year, adm_cd=adm_cd,
                                 low_search=1, class_code=class_code)
                for row in rows or []:
                    code = str(row.get("adm_cd"))
                    if code not in data["population"]:
                        raise ValueError("SGIS 산업별 행정코드 확인 필요")
                    industry[code][class_code] = count(row.get("tot_worker"))
            coverage[f"{year}:{region}"] = len(data["population"])
            region_completed.add(f"{year}:{region}")
            for code, person in data["population"].items():
                municipality = sgis_geography(region, person.get("adm_nm"))
                if municipality is None:
                    raise ValueError("SGIS 시군구 명칭 연결 확인 필요")
                household = data["household"][code]
                company = data["company"][code]
                payload = {"name": municipality, "region": region, "municipality": municipality,
                           "source_admin_code": code, "source_admin_name": person["adm_nm"],
                           "metric_group": "sgis_census", "year": year, "base_date": f"{year}-12-31",
                           "date_precision": "YEAR", "population": count(person.get("tot_ppltn")),
                           "households": count(household.get("household_cnt")),
                           "workplace_workers": count(company.get("tot_worker")),
                           "businesses": count(company.get("corp_cnt")),
                           "industry_workers": industry[code], "industry_labels": classes,
                           "industry_coverage": len(industry[code]),
                           "evidence_url": SGIS_DOC,
                           "definition": "SGIS 총인구·일반가구·사업체 소재지 종사자. 공급 실적 아님"}
                records.append(("area_stat", f"{year}|{code}", payload))
    if not records:
        raise ValueError("SGIS 통계 행 미확보")
    return records, {"years_complete": sorted(completed | set(years)), "latest_available_year": latest,
                     "queried_years": years, "region_year_rows": coverage,"region_years_complete":sorted(region_completed),
                     "regions":["서울특별시","경기도","인천광역시"],
                     "industry_count": len(classes), "complete_query": True, "incremental": True}


def kosis_rows(fetcher, key, table, period, item, start, end, allow_missing=False, **extra):
    params = {"method": "getList", "apiKey": key, "orgId": "101", "tblId": table,
              "objL1": "ALL", "itmId": item, "prdSe": period, "startPrdDe": start,
              "endPrdDe": end, "format": "json", "jsonVD": "Y", **extra}
    data = json.loads(fetcher.get(KOSIS, "json", params=params))
    if not isinstance(data, list):
        if allow_missing and isinstance(data, dict) and str(data.get("err")) == "30":
            return []
        raise ValueError("KOSIS 데이터 응답 확인 필요")
    return data


def kosis_key():
    key = os.environ.get("POC10_KOSIS_API_KEY", "").strip()
    if not key:
        raise ValueError("KOSIS API 키 미확보")
    return key


def kosis_geography(row):
    code = str(row.get("C1", ""))
    name = str(row.get("C1_NM", ""))
    if code.startswith("11") and re.fullmatch(r"서울 [가-힣]+구", name):
        return "서울특별시", name.split(" ", 1)[1]
    if code.startswith("23") and re.fullmatch(r"인천 [가-힣]+[구군]", name):
        return "인천광역시", name.split(" ", 1)[1]
    if code.startswith("31") and name in GYEONGGI:
        return "경기도", name
    return None


def collect_kosis_employment(source, fetcher):
    key = kosis_key()
    cells = defaultdict(dict)
    first, last = "201801", f"{date.today().year}02"
    metrics = {"T3": "resident_employed", "T7": "employment_rate", "T2": "labor_force"}
    for item, metric in metrics.items():
        rows = kosis_rows(fetcher, key, "DT_1ES3A01S", "S", item, first, last)
        if not rows:
            raise ValueError("KOSIS 고용 시계열 비어 있음")
        for row in rows:
            place = kosis_geography(row)
            if not place:
                continue
            period = str(row.get("PRD_DE", ""))
            if not re.fullmatch(r"20\d{4}", period) or period[-2:] not in {"01", "02"}:
                raise ValueError("KOSIS 반기 코드 확인 필요")
            value = number(row.get("DT"))
            # T2/T3 are published in thousands with one decimal; keep that precision explicit.
            value = int(value * 1000) if value is not None and item in {"T2", "T3"} else float(value) if value is not None else None
            cells[(place[0], place[1], str(row["C1"]), period)][metric] = value
    if not cells:
        raise ValueError("서울·경기 고용 통계 미확보")
    records = []
    for (region, municipality, code, period), values in cells.items():
        year, half = int(period[:4]), int(period[-2:])
        payload = {"name": municipality, "region": region, "municipality": municipality,
                   "source_admin_code": code, "metric_group": "kosis_employment", "period": period,
                   "year": year, "half": half, "base_date": f"{year}-{'06-30' if half == 1 else '12-31'}",
                   "date_precision": "HALF_YEAR", "resident_employed": values.get("resident_employed"),
                   "employment_rate": values.get("employment_rate"), "labor_force": values.get("labor_force"),
                   "unit_basis": "취업자·경제활동인구는 원천의 천명 단위를 명으로 환산(100명 정밀도)",
                   "evidence_url": KOSIS_DOC, "table_id": "DT_1ES3A01S",
                   "definition": "거주지 기준 취업자·고용률. 사업체 소재지 종사자와 별개"}
        records.append(("area_stat", f"{code}|{period}", payload))
    return records, {"periods": sorted({key[-1] for key in cells}), "region_city_count": len({key[:2] for key in cells}),
                     "table_id": "DT_1ES3A01S", "complete_query": True}


def collect_kosis_household_forecast(source, fetcher):
    key = kosis_key()
    current = date.today().year
    rows = kosis_rows(fetcher, key, "DT_1BZ0505", "A", "T01", str(current), str(current + 10), objL2="000")
    data = {}
    for row in rows:
        region = {"11": "서울특별시", "31": "경기도", "23": "인천광역시"}.get(str(row.get("C1")))
        if not region or row.get("C2") != "000":
            continue
        year = int(row["PRD_DE"])
        value = count(row.get("DT"))
        if value is None:
            continue
        source_date = str(row.get("LST_CHN_DE") or "")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", source_date):
            raise ValueError("KOSIS 장래가구 기준일 확인 필요")
        data[(region, year)] = {"name": region, "region": region, "municipality": None,
                                "metric_group": "kosis_household_forecast", "year": year,
                                "base_date": source_date, "source_date": source_date,
                                "date_precision": "YEAR", "forecast_households": value,
                                "evidence_url": KOSIS_DOC, "table_id": "DT_1BZ0505",
                                "definition": "시도 장래가구추계. 관측 가구 수 아님"}
    if not data:
        raise ValueError("서울·경기 장래가구추계 미확보")
    records = [("area_stat", f"{region}|{year}", payload) for (region, year), payload in sorted(data.items())]
    return records, {"years": sorted({year for _, year in data}), "regions": sorted({region for region, _ in data}),
                     "table_id": "DT_1BZ0505", "complete_query": True}


def complete_sum(values, required):
    return sum(values) if len(values) == required and all(isinstance(value, (int, float)) for value in values) else None


def area_context(service, region, municipality, year):
    if region not in (*EXPECTED, "인천광역시"):
        raise ValueError("서울·경기 지역만 조회할 수 있습니다")
    if municipality is not None:
        if region == "경기도" and municipality not in GYEONGGI:
            raise ValueError("경기도 시군구 이름 확인 필요")
        if region == "서울특별시" and not re.fullmatch(r"[가-힣]+구", municipality):
            raise ValueError("서울 시군구 이름 확인 필요")
    with service.sessions() as session:
        query = select(Revision.payload).where(Revision.kind == "area_stat", Revision.sample_region == region,
                                               Revision.superseded_at.is_(None))
        if municipality:
            query = query.where(Revision.sample_name == municipality)
        rows = session.scalars(query).all()
    census = defaultdict(list)
    employment = defaultdict(list)
    forecast = []
    housing = []
    household_size = []
    for row in rows:
        group = row.get("metric_group")
        if group == "sgis_census" and row["year"] <= year:
            census[row["year"]].append(row)
        elif group == "kosis_employment" and row["year"] <= year:
            employment[row["period"]].append(row)
        elif group == "kosis_housing" and row["year"] <= year and row.get("municipality") == municipality:
            stock, households = row.get("housing_units"), row.get("households")
            gap = stock - households if stock is not None and households is not None else None
            housing.append({"year": row["year"], "housing_units": stock, "households": households,
                            "census_housing_units": row.get("census_housing_units"),
                            "census_housing_source_table": row.get("census_housing_source_table"),
                            "census_housing_published_at": row.get("census_housing_published_at"),
                            "gap_units": gap, "stock_to_household_pct": round(100 * stock / households, 1) if gap is not None and households else None,
                            "official_ratio": row.get("official_ratio"), "source_date": row.get("source_date"),
                            "housing_source_table": row.get("housing_source_table"),
                            "population": row.get("population")})
        elif group == "kosis_household_size" and row["year"] <= year and row.get("municipality") == municipality:
            household_size.append({"year": row["year"], "total": row["household_total"], "sizes": row["sizes"]})
        elif group == "kosis_household_forecast" and not municipality and year <= row["year"] <= year + 10:
            forecast.append({"year": row["year"], "households": row["forecast_households"],
                             "published_at": row["source_date"]})
    census_series = []
    for observed_year, group in sorted(census.items()):
        required = len(group) if municipality else EXPECTED.get(region,10 if observed_year<2026 else 11)
        industry_labels = group[0].get("industry_labels", {})
        industries = {}
        for code, label in industry_labels.items():
            values = [row.get("industry_workers", {}).get(code) for row in group]
            total = complete_sum(values, required)
            if total is not None:
                industries[code] = {"name": label, "workers": total}
        census_series.append({"year": observed_year, "population": complete_sum([r.get("population") for r in group], required),
                              "households": complete_sum([r.get("households") for r in group], required),
                              "workplace_workers": complete_sum([r.get("workplace_workers") for r in group], required),
                              "businesses": complete_sum([r.get("businesses") for r in group], required),
                              "industry_workers": industries, "covered_units": len(group),
                              "expected_units": required})
    employment_series = []
    for period, group in sorted(employment.items()):
        required = EXPECTED_CITIES.get(region, 10) if not municipality else 1
        # Employment rates are not additive; omit regional rate without a published regional denominator.
        employed = complete_sum([r.get("resident_employed") for r in group], required)
        labor = complete_sum([r.get("labor_force") for r in group], required)
        rate = group[0].get("employment_rate") if municipality and len(group) == 1 else None
        employment_series.append({"period": period, "resident_employed": employed,
                                  "labor_force": labor, "employment_rate": rate,
                                  "covered_municipalities": len(group), "expected_municipalities": required})
    population_history = [{"year": row["year"], "population": row["population"], "source": "SGIS"}
                          for row in census_series if row["population"] is not None]
    seen_years = {row["year"] for row in population_history}
    population_history.extend({"year": row["year"], "population": row["population"], "source": "KOSIS"}
                              for row in housing if row.get("population") is not None and row["year"] not in seen_years)
    from .unsold import context as unsold_context
    from .age_distribution import context as age_context
    from .area_benchmarks import context as benchmark_context
    from .area_living import context as living_context
    age=age_context(service,region,municipality,year)
    national=benchmark_context(service,age,sorted(household_size,key=lambda r:r['year']),census_series)
    reference=date(year,12,31) if year and year<today().year else today()
    return {"region": region, "municipality": municipality, "analysis_year": year,
            "unsold":unsold_context(service,region,municipality,reference),
            "age_distribution":age,"national_benchmarks":national,"living":living_context(service,region,municipality,year),
            "census": census_series, "population_history": sorted(population_history, key=lambda row: row["year"]),
            "employment": employment_series,
            "housing_balance": sorted(housing, key=lambda row: row["year"]),
            "household_size": sorted(household_size, key=lambda row: row["year"]),
            "household_forecast": sorted(forecast, key=lambda row: row["year"]),
            "sources": {"sgis": SGIS_DOC, "kosis": KOSIS_DOC},
            "notes": {"workplace_workers": "사업체 소재지 기준", "resident_employed": "거주지 기준",
                      "employment_precision": "천명 통계를 명으로 환산, 100명 정밀도",
                      "forecast": "장래가구추계는 관측치와 별도",
                      "geography": "통계 원천의 당시 시군구 판본 유지. 인천 2026년 행정구역 개편 전 통계를 새 경계에 임의 배분하지 않음",
                      "housing_balance": "주택 재고−일반가구의 단순 차이. 실제 공가·가용 물량·정책 공급 실적이 아님"}}


def kosis_housing_place(row):
    """Use published city totals, never sum Gyeonggi city totals and their wards."""
    code, name = str(row.get("C1", "")), str(row.get("C1_NM", ""))
    if code == "11" and name == "서울특별시":
        return "서울특별시", None
    if code == "23" and name == "인천광역시":
        return "인천광역시", None
    if len(code) == 5 and code.startswith("23") and re.fullmatch(r"[가-힣]+[구군]", name):
        return "인천광역시", name
    if code == "31" and name == "경기도":
        return "경기도", None
    if len(code) == 5 and code.startswith("11") and re.fullmatch(r"[가-힣]+구", name):
        return "서울특별시", name
    if len(code) == 5 and code.startswith("31") and name in GYEONGGI:
        return "경기도", name
    return None


def collect_kosis_housing(source, fetcher):
    """Adjusted housing inventory and general households, with MOLIT province history."""
    key = kosis_key()
    current = date.today().year
    cells = defaultdict(dict)
    definitions = (
        ("DT_1JC1515", "T1010", "2018", "households"),
        ("DT_1IN1502", "T310", "2018", "census_housing_units"),
        ("DT_1MH2090", "T10", "2024", "housing_units"),
    )
    for table, item, first, field in definitions:
        for row in kosis_rows(fetcher, key, table, "A", item, first, str(current)):
            place = kosis_housing_place(row)
            if not place:
                continue
            year = int(row["PRD_DE"])
            value = count(row.get("DT"))
            if value is None:
                continue
            cell = cells[(place[0], place[1], year)]
            cell[field] = value
            cell[field + "_published_at"] = row.get("LST_CHN_DE")
            cell[field + "_table"] = table
    # SGIS census stops at 2024; the 2025 census table extends the observed
    # population series without estimating a later year.
    for row in kosis_rows(fetcher, key, "DT_1IN1502", "A", "T100", "2018", str(current)):
        place = kosis_housing_place(row)
        if place:
            value = count(row.get("DT"))
            if value is not None:
                cells[(place[0], place[1], int(row["PRD_DE"]))]["population"] = value
    # The ministry's series supplies comparable province totals before the
    # municipality adjusted-inventory series begins in 2024 (thousand units).
    molit = defaultdict(dict)
    for item, field in (("13103871096T4", "households"),
                        ("13103871096T5", "housing_units"),
                        ("13103871096T6", "official_ratio")):
        for row in kosis_rows(fetcher, key, "DT_MLTM_2100", "A", item, "2018", str(current), orgId="116"):
            region = {"서울": "서울특별시", "경기": "경기도", "인천": "인천광역시"}.get(row.get("C1_NM"))
            if not region:
                continue
            year = int(row["PRD_DE"])
            value = number(row.get("DT"))
            if value is None:
                continue
            molit[(region, year)][field] = float(value) if field == "official_ratio" else int(value * 1000)
    if not cells or not molit:
        raise ValueError("KOSIS 주택·가구 연속자료 미확보")
    records = []
    for (region, municipality, year), values in sorted(cells.items(), key=lambda x:(x[0][0], x[0][1] or "", x[0][2])):
        history = molit.get((region, year), {}) if municipality is None else {}
        # Exact census values take precedence for overlapping 2024. Verify that
        # the ministry's published rounded totals describe the same population.
        if history and values.get("housing_units") is not None:
            for field in ("housing_units", "households"):
                if field in history and abs(values[field] - history[field]) > 100:
                    raise ValueError("KOSIS·국토부 주택보급률 집계 기준 불일치")
        housing = values.get("housing_units", history.get("housing_units"))
        households = values.get("households", history.get("households"))
        if households is None:
            continue
        published = values.get("housing_units_published_at") or values.get("households_published_at")
        payload = {"name": municipality or region, "region": region, "municipality": municipality,
                   "metric_group": "kosis_housing", "year": year, "base_date": f"{year}-12-31",
                   "date_precision": "YEAR", "housing_units": housing, "households": households,
                   "census_housing_units": values.get("census_housing_units"),
                   "census_housing_source_table": values.get("census_housing_units_table"),
                   "census_housing_published_at": values.get("census_housing_units_published_at"),
                   "population": values.get("population"), "official_ratio": history.get("official_ratio"),
                   "housing_basis": "다가구 구분거처 반영 주택수",
                   "census_housing_basis": "인구주택총조사 주택_계 · 주택보급률의 보정 재고와 다른 기준",
                   "source_date": published,
                   "housing_source_table": values.get("housing_units_table") or ("DT_MLTM_2100" if history.get("housing_units") is not None else None),
                   "household_source_table": values.get("households_table") or ("DT_MLTM_2100" if history.get("households") is not None else None),
                   "evidence_url": KOSIS_DOC,
                   "definition": "주택 재고와 일반가구의 같은 연도·행정구역 비교. 공실·점유·실입주량은 아님"}
        records.append(("area_stat", f"{region}|{municipality or 'ALL'}|{year}", payload))
    census_years = sorted({year for (_, _, year), value in cells.items()
                           if value.get("census_housing_units") is not None})
    if not census_years or census_years != list(range(2018, max(census_years) + 1)):
        raise ValueError("KOSIS 2018년 이후 주택총조사 연도 누락")
    for year in census_years:
        included = [p for _, _, p in records if p["year"] == year and p["census_housing_units"] is not None and p["municipality"]]
        if sum(p["region"] == "서울특별시" for p in included) != 25 or sum(p["region"] == "경기도" for p in included) != 31:
            raise ValueError(f"KOSIS {year}년 시군구 주택총조사 범위 누락")
    latest = max(year for (_, _, year), value in cells.items() if value.get("housing_units") is not None)
    for year in (latest - 1, latest):
        included = [p for _, _, p in records if p["year"] == year and p["housing_units"] is not None and p["municipality"]]
        if sum(p["region"] == "서울특별시" for p in included) != 25 or sum(p["region"] == "경기도" for p in included) != 31:
            raise ValueError("KOSIS 최신 시군구 주택 재고 범위 누락")
    return records, {"latest_housing_year": latest, "census_housing_years": census_years,
                     "first_household_year": min(p["year"] for _, _, p in records),
                     "covered_municipalities": len({(r[2]["region"],r[2]["municipality"]) for r in records if r[2]["municipality"]}), "complete_query": True,
                     "tables": ["DT_1JC1515", "DT_1MH2090", "DT_1IN1502", "DT_MLTM_2100"]}


HOUSEHOLD_SIZE_ITEMS = {"T10": "total", "T21": "1", "T22": "2", "T23": "3", "T24": "4", "T25": "5", "T26": "6", "T27": "7+"}


def parse_household_size_rows(rows, year):
    """Keep only the published geographic total, then verify its size classes."""
    cells = defaultdict(dict)
    for row in rows:
        place = kosis_housing_place(row)
        if not place or row.get("C2") != "00" or row.get("ITM_ID") not in HOUSEHOLD_SIZE_ITEMS:
            continue
        if str(row.get("PRD_DE")) != str(year):
            raise ValueError("KOSIS 가구원수 자료연도 불일치")
        key = (place[0], place[1])
        field = HOUSEHOLD_SIZE_ITEMS[row["ITM_ID"]]
        if field in cells[key]:
            raise ValueError("KOSIS 가구원수 지역·항목 중복")
        cells[key][field] = count(row.get("DT"))
    parsed = {}
    required = set(HOUSEHOLD_SIZE_ITEMS.values())
    for place, values in cells.items():
        if set(values) != required or any(value is None for value in values.values()):
            raise ValueError("KOSIS 가구원수 항목 미확보")
        if sum(values[k] for k in ("1", "2", "3", "4", "5", "6", "7+")) != values["total"]:
            raise ValueError("KOSIS 가구원수 합계 불일치")
        parsed[place] = {"total": values["total"], "sizes": {"1": values["1"], "2": values["2"],
            "3": values["3"], "4": values["4"], "5+": values["5"] + values["6"] + values["7+"]}}
    return parsed


def collect_kosis_household_size(source, fetcher):
    """Annual general-household sizes, 2018 through the latest census year."""
    key = kosis_key()
    records = []
    years = []
    for year in range(2018, date.today().year):
        rows = kosis_rows(fetcher, key, "DT_1JC1516", "A", "+".join(HOUSEHOLD_SIZE_ITEMS),
                          str(year), str(year), allow_missing=True, objL2="00")
        if not rows:
            if years and year >= date.today().year - 1:
                break  # Prior-year census not yet published; preserve completed history.
            raise ValueError("KOSIS 가구원수 과거 연도 미확보")
        places = parse_household_size_rows(rows, year)
        if sum(place[0] == "서울특별시" for place in places) != 26 or sum(place[0] == "경기도" for place in places) != 32:
            raise ValueError("KOSIS 서울·경기 가구원수 지역 범위 누락")
        years.append(year)
        for (region, municipality), values in sorted(places.items(), key=lambda x:(x[0][0], x[0][1] or "")):
            payload = {"name": municipality or region, "region": region, "municipality": municipality,
                "metric_group": "kosis_household_size", "year": year, "base_date": f"{year}-12-31",
                "date_precision": "YEAR", "household_total": values["total"], "sizes": values["sizes"],
                "table_id": "DT_1JC1516", "evidence_url": KOSIS_DOC,
                "definition": "일반가구의 가구원수별 분포. 5인 이상은 5·6·7인 이상 합계"}
            records.append(("area_stat", f"{region}|{municipality or 'ALL'}|{year}", payload))
    if not records:
        raise ValueError("KOSIS 가구원수 과거 시계열 미확보")
    return records, {"years": years, "covered_places_per_year": len(places), "table_id": "DT_1JC1516",
                     "complete_query": True}


def area_places(service):
    with service.sessions() as session:
        rows = session.scalars(select(Revision.payload).where(
            Revision.kind == "area_stat", Revision.source_id == "kosis_housing",
            Revision.superseded_at.is_(None))).all()
    regions = {region: set() for region in (*EXPECTED, "인천광역시")}
    years = set()
    for row in rows:
        if row.get("region") not in regions:
            continue
        years.add(row["year"])
        if row.get("municipality"):
            regions[row["region"]].add(row["municipality"])
    return {"regions": {region: sorted(names) for region, names in regions.items()},
            "housing_years": sorted({row["year"] for row in rows if row.get("housing_units") is not None}),
            "household_years": sorted(years)}
