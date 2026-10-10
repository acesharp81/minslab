"""Annual Seoul/Gyeonggi housing construction flows from official MOLIT observations.

A monthly total is compared as a full year only when January–December are all
present. Housing inventory, policy targets, and announcement counts stay separate.
"""
import csv
import io
from collections import defaultdict

from sqlalchemy import select

from .db import Revision

REGIONS = ("서울특별시", "경기도")
METRICS = ("분양승인", "인허가", "착공", "준공")
SOURCES = {
    "분양승인": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=488",
    "인허가": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=31",
    "착공": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=471",
    "준공": "https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=468",
}


def annual_supply(service, region=None, through_year=None):
    if region is not None and region not in REGIONS:
        raise ValueError("서울·경기 지역만 조회할 수 있습니다")
    with service.sessions() as session:
        query = select(Revision.payload).where(Revision.source_id == "molit_statistics",
                                               Revision.kind == "statistic",
                                               Revision.superseded_at.is_(None))
        if region:
            query = query.where(Revision.sample_region == region)
        source_rows = session.scalars(query).all()
    observed = defaultdict(dict)
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
        month = int(period[4:]) if row.get("statistic_frequency") == "MONTH" and len(period) == 6 else None
        if metric != "인허가" and (month is None or not 1 <= month <= 12):
            continue
        if metric == "인허가" and (month is not None or len(period) != 4):
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
    records = []
    for place in places:
        for year in range(first_year, last_year + 1):
            record = {"region": place, "year": year, "metrics": {}}
            for metric in METRICS:
                periods = observed.get((place, year, metric), {})
                if metric == "인허가":
                    item = periods.get(0)
                    cell = {"units": item["units"] if item else None, "periods": 1 if item else 0,
                            "expected_periods": 1, "complete": bool(item), "through_period": str(year) if item else None}
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
                prior_complete = bool(prior.get(0)) if metric == "인허가" else sorted(prior) == list(range(1, 13))
                if cell["complete"] and prior_complete:
                    previous = prior[0]["units"] if metric == "인허가" else sum(row["units"] for row in prior.values())
                    cell["change_yoy_units"] = cell["units"] - previous
                    cell["change_yoy_pct"] = round(100 * (cell["units"] - previous) / previous, 1) if previous else None
                else:
                    cell["change_yoy_units"] = None
                    cell["change_yoy_pct"] = None
                record["metrics"][metric] = cell
            records.append(record)
    return {"regions": list(places), "first_year": first_year, "last_year": last_year,
            "rows": records, "metrics": list(METRICS),
            "sources": SOURCES,
            "note": "서울·경기 시도 전체(공공·민간 포함). 분양승인은 공동주택 승인 순계, 인허가·착공·준공은 주택건설 단계별 실적. 서로 합산하거나 정책·블록별 실적으로 배분하지 않음. 12개월 미만 연도는 부분 집계."}


def annual_supply_csv(data):
    fields = ["region", "year", "metric", "units", "periods", "expected_periods",
              "complete", "through_period", "change_yoy_units", "change_yoy_pct",
              "sale_units", "rental_units", "cooperative_units", "source_url"]
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
                             "source_url": data["sources"][metric]})
    return "\ufeff" + buffer.getvalue()
