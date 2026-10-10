import hashlib
import io
import json
import re
import time
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from .sources import POLICIES

PARSER_VERSION = "home-collection-1.5"
ALLOWED_HOSTS = {"bizmap.lh.or.kr", "apply.lh.or.kr", "www.lh.or.kr", "lh.or.kr", "www.korea.kr", "m.korea.kr", "d.nts.go.kr", "api.odcloud.kr", "infuser.odcloud.kr", "apis.data.go.kr", "api.vworld.kr", "stat.molit.go.kr", "www.gh.or.kr", "gh.or.kr", "data.seoul.go.kr", "datafile.seoul.go.kr", "www.data.go.kr", "www.code.go.kr", "sgisapi.mods.go.kr", "kosis.kr"}
SECRET_PARAMS = {"key", "servicekey", "apikey", "authkey", "access_token", "accesstoken", "consumer_key", "consumer_secret", "authorization"}
GYEONGGI_CITIES = "수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 군포 의왕 하남 용인 파주 이천 안성 김포 화성 광주 양주 포천 여주 연천 가평 양평".split()


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def integer(value):
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "미정"}:
        return None
    text=re.sub(r'\.0+$','',text)
    if not re.fullmatch(r"\d+", text):
        raise ValueError("호수 컬럼 형식 변경")
    return int(text)


def date_iso(value):
    match = re.fullmatch(r"(\d{2}|\d{4})[-./](\d{2})[-./](\d{2})", clean(value))
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return date(year + 2000 if year < 100 else year, month, day).isoformat()


def month_iso(value):
    match = re.search(r"(20\d{2})\D*(\d{1,2})\s*월", clean(value))
    if match:
        return f"{match[1]}-{int(match[2]):02d}"
    return None


class Fetcher:
    def __init__(self, source_id, raw_dir):
        self.source_id = source_id
        self.raw_dir = Path(raw_dir)
        self.manifest = []
        self.client = httpx.Client(timeout=35, follow_redirects=False, headers={"User-Agent": "HOME-PoC/1.0 official-data-validation"})

    def close(self):
        self.client.close()

    def get(self, url, suffix="html", params=None, headers=None):
        if urlparse(url).hostname not in ALLOWED_HOSTS:
            raise ValueError("허용된 공식 원천 호스트가 아님")
        # httpx params replaces the existing query; preserve the source type.
        request_url = httpx.URL(url).copy_merge_params(params or {})
        secrets = [value for key, value in request_url.params.multi_items() if key.lower() in SECRET_PARAMS and value]
        if secrets and request_url.scheme != "https":
            raise ValueError("API 인증 요청은 HTTPS만 허용")
        response = None
        for attempt in range(3):
            try:
                response = self.client.get(request_url, headers=headers)
                for _ in range(5):
                    if not response.is_redirect:
                        break
                    target = urljoin(str(response.url), response.headers.get("location", ""))
                    if urlparse(target).hostname not in ALLOWED_HOSTS:
                        raise ValueError("원천 redirect 호스트 변경")
                    if secrets and (urlparse(target).scheme != "https" or urlparse(target).hostname != request_url.host):
                        raise ValueError("인증 요청 redirect는 같은 HTTPS 호스트만 허용")
                    response = self.client.get(target, headers=headers)
                response.raise_for_status()
                if len(response.content) < (2 if suffix == 'json' else 100):
                    raise ValueError("원천 응답이 비었거나 차단됨")
                break
            except (httpx.RequestError, httpx.HTTPStatusError):
                if attempt == 2:
                    raise RuntimeError("공식 원천 연결 실패 (timeout/HTTP 오류)") from None
                time.sleep(attempt + 1)
        data = response.content
        # Preserve API data after removing credentials, including echoed errors.
        for secret in secrets:
            encoded = quote(secret, safe="")
            variants = {secret, encoded, re.sub(r"%[0-9A-F]{2}", lambda m: m[0].lower(), encoded), json.dumps(secret)[1:-1]}
            for value in sorted(variants, key=len, reverse=True):
                data = data.replace(value.encode(), b"[REDACTED]")
        digest = hashlib.sha256(data).hexdigest()
        path = self.raw_dir / self.source_id / f"{digest}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        parts = urlsplit(str(response.url))
        safe_query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                      if key.lower() not in SECRET_PARAMS and not any(secret in value for secret in secrets)]
        safe_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), "")) if secrets else str(response.url)
        entry = {"url": safe_url, "sha256": digest, "bytes": len(data), "file": f"{self.source_id}/{path.name}", "parser_version": PARSER_VERSION}
        if secrets:
            entry["credentials_removed"] = True
        self.manifest.append(entry)
        return data


def parse_lh_plan(html, rent=False):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".bbs_apply table")
    if not table or "공급호수" not in table.get_text():
        raise ValueError("LH 공급계획 표 schema 변경")
    year_match = re.search(r"(20\d{2})년 공급계획", soup.get_text(" ", strip=True))
    if not year_match:
        raise ValueError("LH 공급계획 기준연도 미확인")
    rows = []
    for tr in table.select("tbody tr"):
        values = [clean(td.get_text(" ", strip=True)) for td in tr.find_all("td", recursive=False)]
        if len(values) != 9:
            if values and "없" not in "".join(values):
                raise ValueError("LH 공급계획 컬럼 수 변경")
            continue
        if rent:
            region, tenure, name, area, units, supply, move, org, note = values
            total = None
        else:
            tenure, region, name, total, area, units, supply, org, note = values
            move = None
            total = integer(total)
        rows.append({"region": region, "tenure": tenure, "name": name, "area": area,
                     "total_units": total, "units": integer(units), "supply_month": month_iso(supply),
                     "move_in_month": month_iso(move), "org": org, "note": note})
    if not rows:
        raise ValueError("LH 공급계획 행이 없음: 기존 정상 snapshot 유지")
    total_box = soup.select_one(".bbs_total")
    match = re.search(r"전체\s*([\d,]+)\s*건", total_box.get_text(" ", strip=True) if total_box else "")
    if not match:
        raise ValueError("LH pagination 총건수 미확인")
    return int(year_match[1]), int(match[1].replace(",", "")), rows


def collect_lh_plan(source, fetcher):
    rent = source["id"] == "lh_rent"
    all_rows = []
    total, year = None, None
    for page in range(1, 31):
        # LH resets currPage when listCo and prevListCo differ.
        content = fetcher.get(source["url"], params={"listCo": 100, "prevListCo": 100, "currPage": page})
        current_year, expected, rows = parse_lh_plan(content, rent)
        if total is not None and (total != expected or year != current_year):
            raise ValueError("수집 중 공급계획 모집단 변경: 다음 배치 재시도")
        total, year = expected, current_year
        all_rows.extend(rows)
        if len(all_rows) >= total:
            break
    if len(all_rows) != total:
        raise ValueError("LH pagination 누락/중복 감지")
    groups = defaultdict(list)
    excluded = 0
    for row in all_rows:
        if row["region"] not in {"서울특별시", "경기도"}:
            excluded += 1
            continue
        if any(term in row["tenure"] for term in ("매입", "전세")):
            excluded += 1
            continue
        groups[(row["region"], row["tenure"], row["name"])].append(row)
    records = []
    for key, rows in groups.items():
        areas = set()
        for row in rows:
            dimension = (row["area"], row["supply_month"])
            if dimension in areas:
                raise ValueError("동일 면적·공급월 행 중복: 합산 중단")
            areas.add(dimension)
        totals = {r["total_units"] for r in rows if r["total_units"] is not None}
        supply_units = sum(r["units"] for r in rows) if all(r["units"] is not None for r in rows) else None
        warnings = []
        if len(totals) > 1:
            warnings.append("TOTAL_CONFLICT")
        planned = next(iter(totals)) if len(totals) == 1 else supply_units if rent else None
        if planned is not None and supply_units is not None and supply_units > planned:
            warnings.append("SUPPLY_EXCEEDS_TOTAL")
        program = "건설형 공공임대" if rent else "3기 신도시" if any(x in key[2] for x in ("왕숙", "창릉", "교산", "대장")) else "공공택지·공공분양"
        payload = {"name": key[2], "region": key[0], "municipality": "지역 상세 확인 필요", "program": program,
                   "tenure": key[1], "planned_units": planned, "supply_units": supply_units, "rows": rows,
                   "stage": "PLANNED_SUPPLY", "stage_label": "공급계획", "base_date": f"{year}-01-01", "date_precision": "YEAR",
                   "schedule_month": min((r["supply_month"] for r in rows if r["supply_month"]), default=None),
                   "schedule_basis": "모집/공급 예정월", "progress_pct": None, "developer": "LH", "warnings": warnings,
                   "proposed_policy": "POL_2025_0907", "mapping_basis": "LH 공급계획에서 발견한 정책 후보. 개별 정책 귀속은 담당자 확인 필요",
                   "evidence_url": source["url"], "availability": "PUBLIC", "unit_basis": "공급계획 총세대수" if totals else "임대 공급계획 호수"}
        records.append(("project", "|".join(key), payload))
    return records, {"raw_rows": total, "excluded_rows": excluded, "included_rows": total - excluded, "provided":total, "fetched":len(all_rows), "pages":page, "complete_query":True, "complete_population":False, "source_base_date":str(year)}


def parse_construction(data, base_date):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    records, skipped = [], 0
    for tr in root.findall(".//w:tr", ns):
        values = [clean("".join(t.text or "" for t in cell.findall(".//w:t", ns))) for cell in tr.findall("w:tc", ns)]
        if len(values) != 13 or values[2] != "건축" or values[9] != "호":
            continue
        org, team, trade, block, district, site, contractor, amount, units, unit, start, end, pct = values
        city = next((c for c in GYEONGGI_CITIES if district.startswith(c)), None)
        region = "경기도" if city else "서울특별시" if district.startswith("서울") else None
        if not region:
            # The HQ is not a geographic boundary: 위례 etc must be reviewed separately.
            skipped += 1
            continue
        progress = float(pct.replace(",", "")) if re.fullmatch(r"\d+(\.\d+)?", pct) else None
        if progress is not None and not 0 <= progress <= 100:
            raise ValueError("공정률 범위 오류")
        records.append(("project", f"{district}|{block}|{site}", {
            "name": site, "district": district, "block": block, "region": region, "municipality": city or "서울 (구 확인 필요)",
            "program": "3기 신도시" if any(x in district for x in ("왕숙", "창릉", "교산", "대장")) else "공공주택 건설",
            "tenure": "유형 확인 필요", "planned_units": integer(units), "supply_units": None, "progress_pct": progress,
            "stage": "COMPLETED" if progress == 100 else "CONSTRUCTION", "stage_label": "원천상 공사 완료" if progress == 100 else "원천상 공사 진행",
            "start_actual_date": date_iso(start) if date_iso(start) and date_iso(start) <= base_date else None,
            "start_plan_date": date_iso(start), "completion_plan_date": date_iso(end),
            "schedule_month": date_iso(end)[:7] if date_iso(end) else None, "schedule_basis": "공사 계약 준공예정 (입주일 아님)",
            "base_date": base_date, "date_precision": "DAY", "developer": "LH", "contractor": contractor,
            "warnings": ["MULTI_SITE_CONTRACT"] if "및" in site or ("위례" in site and "위례" not in district) else [],
            "proposed_policy": "POL_2025_0907", "mapping_basis": "LH 건설공사 현황에서 발견. 정책 귀속과 다른 원천의 동일 사업 확인 필요",
            "availability": "PUBLIC", "unit_basis": "건축공사 계약 규모 (호); 복수 현장·지역 배분 확인 필요" if "및" in site or ("위례" in site and "위례" not in district) else "건축공사 규모 (호)"}))
    if not records:
        raise ValueError("서울·경기 주택 건축공사 행을 찾지 못함")
    return records, {"excluded_ambiguous_region": skipped}


def collect_construction(source, fetcher):
    content = fetcher.get(source["url"])
    soup = BeautifulSoup(content, "html.parser")
    files = []
    for a in soup.select('a[href*="boardDownload.es"]'):
        title = a.get("title", "")
        match = re.search(r"(20\d{6})", title)
        if ".docx" in title.lower() and match:
            files.append((match[1], urljoin(source["url"], a["href"])))
    if not files:
        raise ValueError("LH 공사 현황 DOCX 링크를 찾지 못함")
    latest, url = max(files)
    base = f"{latest[:4]}-{latest[4:6]}-{latest[6:8]}"
    records, stats = parse_construction(fetcher.get(url, "docx"), base)
    for _, _, payload in records:
        payload["evidence_url"] = url
    stats["source_base_date"] = base
    return records, stats


def article_text(html):
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".view_cont") or soup.select_one(".bbs_detail") or soup.select_one(".nttCn")
    text = clean(node.get_text(" ", strip=True) if node else soup.get_text(" ", strip=True))
    if len(text) < 100:
        raise ValueError("정책 원문 내용 미확보")
    return text


def parse_policy(source_id, html):
    text = article_text(html)
    if source_id == "urban_930":
        if "후보지" not in text or "11곳" not in text:
            raise ValueError("9·30 후속조치 문서 불일치")
        records = [("document", "148972807", {"name": "서울 도심복합사업 신규 후보지 후속조치", "base_date": "2026-09-30",
                    "summary": "서울 11곳 신규 후보지 선정. 개별사업 검토와 주민 동의·지정 절차가 필요합니다.", "policy_id": "POL_2026_0813"})]
        for name, borough in [("효창공원앞역 북측", "용산구"), ("망원체육공원 인근", "마포구"), ("이수역 동측", "서초구"),
                               ("아차산역", "광진구"), ("성동초", "광진구"), ("화곡역", "강서구"), ("오류동역", "구로구"),
                               ("성신여대입구역", "성북구"), ("올림픽공원", "송파구"), ("염창역", "양천구"), ("백련산", "은평구")]:
            if name.split()[0] not in text:
                continue
            payload = urban_project(name, borough, "서울특별시", None, "POL_2026_0813", "2026-09-30", "도심 공공주택 복합사업")
            payload.update(stage="CANDIDATE", stage_label="신규 후보지", unit_basis="개별 호수 원문 확인 필요")
            records.append(("project", name, payload))
        candidate_count = len(records)-1
        for name in ('고은산 서측', '목4동 강서고', '송중동 주민센터', '녹번동근린공원', '신길4'):
            if name not in text:
                continue
            payload = urban_project(name, '', '서울특별시', None, 'POL_2026_0813', '2026-09-30', '도심 공공주택 복합사업')
            payload.update(stage='DESIGNATED',stage_label='복합지구 지정 · 사업계획 승인 추진',
                warnings=['MUNICIPALITY_UNVERIFIED'],unit_basis='5곳 합계만 발표 · 개별 물량 미확인')
            records.append(('project', name, payload))
        # Only individually stated quantities are assigned; 18,000 and group totals stay unallocated.
        for kind,name,payload in records:
            if kind == 'project' and name == '효창공원앞역 북측' and '약 4000호' in text:
                payload['planned_units']=4000
                payload['unit_basis']='정책 원문 개별 후보지 약 4,000호 · 추정 계획, 공급실적 아님'
        return records, {"selected_projects": candidate_count, "announced_candidates":11,
            "additional_designated_projects":len(records)-1-candidate_count,
            "complete_query":False,"complete_population":False,
            "missing_candidate_names":11-candidate_count,
            "scope_note":"보도문에 개별 이름이 명시된 후보지·지정지구만 적재. 미명시 8개 후보지는 명단 원문 확보 필요"}
    spec = POLICIES[source_id]
    if spec["assertion"] not in text.replace(" ", ""):
        raise ValueError("정책 제목/목표 근거 불일치")
    payload = dict(spec, lifecycle_status="REVIEW", base_date=spec["announced_at"], evidence_checked=True,
                   note="발표 당시 공식 목표입니다. 후속 변경과 기준일 현재 유효 여부는 검토 대상입니다.")
    records = [("policy", spec["id"], payload)]
    if source_id == "policy_129":
        # Only named quantities in the official briefing; no guessed coordinates or dates.
        specs = [("동대문구 일원", "동대문구", "서울특별시", "공공시설 이전"),
                 ("은평구 불광동 일원", "은평구", "서울특별시", "공공시설 이전"),
                 ("광명경찰서 부지", "광명시", "경기도", "노후청사·공공부지"),
                 ("하남 신장테니스장 부지", "하남시", "경기도", "노후청사·공공부지"),
                 ("강서 군부지", "강서구", "서울특별시", "군 유휴부지"),
                 ("금천 공군부대", "금천구", "서울특별시", "군 유휴부지"),
                 ("남양주 군부지", "남양주시", "경기도", "군 유휴부지"),
                 ("고양시 소재 구 국방대학교", "고양시", "경기도", "군 유휴부지")]
        for name, borough, region, program in specs:
            match = re.search(re.escape(name) + r"\s+([\d,]+)호", text)
            if match:
                item = urban_project(name, borough, region, integer(match[1]), spec["id"], spec["announced_at"], program)
                records.append(("project", name, item))
    return records, {"policies": 1, "named_projects": len(records) - 1}


def urban_project(name, borough, region, units, policy_id, base_date, program):
    return {"name": name, "region": region, "municipality": borough, "program": program, "tenure": "유형 확인 필요",
            "planned_units": units, "supply_units": None, "stage": "PLANNING", "stage_label": "정책 발표·계획",
            "progress_pct": None, "schedule_month": None, "schedule_basis": "개별 일정 확인 필요",
            "base_date": base_date, "date_precision": "DAY", "developer": "시행기관 확인 필요", "warnings": [],
            "proposed_policy": policy_id, "mapping_basis": "공식 정책 원문에 명시된 개별사업. 담당자 확정 전 검토 후보",
            "availability": "PUBLIC", "unit_basis": "정책 발표 계획호수"}


def collect(source, fetcher):
    if source["id"] in {"lh_sale", "lh_rent"}:
        return collect_lh_plan(source, fetcher)
    if source["id"] == "lh_construction":
        return collect_construction(source, fetcher)
    records, stats = parse_policy(source["id"], fetcher.get(source["url"]))
    for _, _, payload in records:
        payload["evidence_url"] = source["url"]
    if source['id']=='urban_930':
        from .policy_attachments import collect_urban930_attachment
        extra,metadata=collect_urban930_attachment(fetcher)
        replacements={key:payload for _,key,payload in extra}
        records=[(kind,key,replacements.pop(key,payload) if kind=='project' else payload) for kind,key,payload in records]
        records.extend(('project',key,payload) for key,payload in replacements.items())
        stats.update(metadata)
    if source['id']=='policy_129':
        from .policy_attachments import collect_policy129_attachment
        extra,metadata=collect_policy129_attachment(fetcher)
        keys={key for kind,key,_ in records if kind=='project'}
        if keys.intersection(key for _,key,_ in extra):raise ValueError('정책 본문·별첨 사업 중복: 기존 데이터 유지')
        records.extend(extra);stats.update(metadata,named_projects=sum(kind=='project' for kind,_,_ in records))
    return records, stats
