"""Annual Seoul/Gyeonggi housing construction flows from official MOLIT observations.

A monthly total is compared as a full year only when January–December are all
present. Housing inventory, policy targets, and announcement counts stay separate.
"""
import csv
import io
from collections import defaultdict

from sqlalchemy import select, or_

from .db import Revision

from .national_statistics import REGION_NAMES
REGIONS = tuple(REGION_NAMES.values())
METRICS = ("분양승인", "인허가", "착공", "준공", "멸실")
SOURCES = {
    "분양승인": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=488",
    "인허가": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=31",
    "착공": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=471",
    "준공": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=468",
    "멸실": "https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2839",
}


def annual_supply(service, region=None, through_year=None):
    if region is not None and region not in REGIONS:
        raise ValueError("전국 시도 조회할 수 있습니다")
    with service.sessions() as session:
        query = select(Revision.payload).where(Revision.source_id.in_(("molit_statistics", "molit_demolition", "incheon_statistics", "national_statistics", "molit_monthly_release")),
                                               Revision.kind.in_(("statistic", "statistic_reference")))
        cutoff=getattr(service,'known_at',None)
        if cutoff is not None:
            query=query.where(Revision.recorded_at<cutoff,or_(Revision.superseded_at.is_(None),Revision.superseded_at>=cutoff))
        else:query=query.where(Revision.superseded_at.is_(None))
        if region:
            query = query.where(Revision.sample_region == region)
        source_rows = session.scalars(query).all()
    observed = defaultdict(dict)
    cumulative = {}
    first_year = None
    last_year = None
    for row in source_rows:
        metric = row.get("statistic_metric")
        place = row.get("region")
        period = str(row.get("statistic_period", ""))
        units = row.get("units")
        if metric not in METRICS or place not in REGIONS or not period[:4].isdigit() or not isinstance(units, int) or units < 0:
            continue
        year = int(period[:4])
        if through_year is not None and year > through_year:
            continue
        if row.get('sample_kind') == 'statistic_reference':
            if metric=='인허가' and row.get('statistic_frequency')=='YTD' and len(period)==6 and 1<=int(period[4:])<=12:
                key=(place,year,metric)
                if period>str(cumulative.get(key,{}).get('statistic_period','')):cumulative[key]=row
                first_year=year if first_year is None else min(first_year,year)
                last_year=year if last_year is None else max(last_year,year)
            continue
        month = int(period[4:]) if row.get("statistic_frequency") == "MONTH" and len(period) == 6 else None
        if metric not in ("인허가", "멸실") and (month is None or not 1 <= month <= 12):
            continue
        if metric in ("인허가", "멸실") and (month is not None or len(period) != 4):
            continue
        key = (place, year, metric)
        period_key = month or 0
        if period_key in observed[key]:
            raise ValueError("국토부 공급 통계 기간 중복")
        observed[key][period_key] = row
        first_year = year if first_year is None else min(first_year, year)
        last_year = year if last_year is None else max(last_year, year)
    if first_year is None:
        return {"regions": list(REGIONS) if region is None else [region], "first_year": None,
                "last_year": None, "rows": [], "metrics": list(METRICS),
                "sources": SOURCES}
    places = (region,) if region else REGIONS
    latest_demolition_year = max((y for (place, y, metric) in observed if metric == "멸실"), default=None)
    records = []
    for place in places:
        for year in range(first_year, last_year + 1):
            record = {"region": place, "year": year, "metrics": {}}
            for metric in METRICS:
                periods = observed.get((place, year, metric), {})
                if metric in ("인허가", "멸실"):
                    item = periods.get(0)
                    cell = {"units": item["units"] if item else None, "periods": 1 if item else 0,
                            "expected_periods": 1, "complete": bool(item), "through_period": str(year) if item else None}
                    fallback=cumulative.get((place,year,metric))
                    if item is None and fallback:
                        period=fallback['statistic_period'];months=int(period[4:])
                        cell=dict(units=fallback['units'],periods=months,expected_periods=12,complete=months==12,
                            through_period=period,aggregation='OFFICIAL_YTD',source_url=fallback['evidence_url'],
                            period_basis='공식 원문 누계 · 개별 월별 관측을 전부 확보했다는 뜻이 아님')
                else:
                    months = sorted(periods)
                    cell = {"units": sum(row["units"] for row in periods.values()) if months else None,
                            "periods": len(months), "expected_periods": 12,
                            "complete": months == list(range(1, 13)),
                            "through_period": f"{year}{max(months):02d}" if months else None}
                    if metric == "분양승인" and months:
                        cell["breakdown"] = {component: sum(row["supply_approval_breakdown"][component] for row in periods.values())
                                             for component in ("분양", "임대", "조합")}
                prior = observed.get((place, year - 1, metric), {})
                prior_complete = bool(prior.get(0)) if metric in ("인허가", "멸실") else sorted(prior) == list(range(1, 13))
                if cell["complete"] and prior_complete:
                    previous = prior[0]["units"] if metric in ("인허가", "멸실") else sum(row["units"] for row in prior.values())
                    cell["change_yoy_units"] = cell["units"] - previous
                    cell["change_yoy_pct"] = round(100 * (cell["units"] - previous) / previous, 1) if previous else None
                else:
                    cell["change_yoy_units"] = None
                    cell["change_yoy_pct"] = None
                cell["availability_status"] = ("ACQUIRED" if cell["units"] is not None and cell["complete"] else
                    "PARTIAL" if cell["units"] is not None else
                    "SOURCE_NOT_PUBLISHED" if metric == "멸실" and latest_demolition_year is not None and year > latest_demolition_year else
                    "NOT_ACQUIRED")
                record["metrics"][metric] = cell
            completion, demolition = record["metrics"]["준공"], record["metrics"]["멸실"]
            record["net_change_reference"] = (completion["units"] - demolition["units"]
                if completion["complete"] and demolition["complete"] else None)
            records.append(record)
    return {"regions": list(places), "first_year": first_year, "last_year": last_year,
            "rows": records, "metrics": list(METRICS),
            "sources": SOURCES, "demolition_latest_year": latest_demolition_year,
            "note": "전국 시도 전체(공공·민간 포함). 분양승인은 공동주택 승인 순계, 인허가·착공·준공은 주택건설 단계별 실적. 멸실은 기존 주택 재고 감소로 신규 공급과 구분. 준공−멸실은 통계 보정 전 산술 참고값이며 공식 재고 변동이 아님. 정책·블록별 실적으로 배분하지 않음. 12개월 미만 연도는 부분 집계."}


def annual_supply_csv(data):
    fields = ["region", "year", "metric", "units", "periods", "expected_periods",
              "complete", "through_period", "change_yoy_units", "change_yoy_pct",
              "sale_units", "rental_units", "cooperative_units", "net_change_reference", "source_url"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for item in data["rows"]:
        for metric in data["metrics"]:
            cell = item["metrics"][metric]
            breakdown = cell.get("breakdown", {})
            writer.writerow({"region": item["region"], "year": item["year"], "metric": metric,
                             "units": cell["units"], "periods": cell["periods"],
                             "expected_periods": cell["expected_periods"], "complete": cell["complete"],
                             "through_period": cell["through_period"], "change_yoy_units": cell["change_yoy_units"],
                             "change_yoy_pct": cell["change_yoy_pct"], "sale_units": breakdown.get("분양"),
                             "rental_units": breakdown.get("임대"), "cooperative_units": breakdown.get("조합"),
                             "net_change_reference": item.get("net_change_reference"),
                             "source_url": cell.get('source_url') or data["sources"][metric]})
    return "\ufeff" + buffer.getvalue()
