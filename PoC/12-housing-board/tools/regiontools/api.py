"""외부 API 호출(얇은 층): V-World 데이터 API, 마이홈 공고, 건축HUB 주택인허가, 국토교통부 TAGO 버스정보, Overpass.

비밀 취급: 키는 .env.local에서 읽어 요청에만 쓴다. 요청 URL·키를 출력·로그·파일에 남기지 않는다.
캐시 파일 이름은 키를 뺀 매개변수의 해시이고, 내용은 응답 본문만이다. 캐시 폴더는 호출하는 쪽이 저장소 밖으로 정한다.
건축HUB는 간헐적으로 503·빈 본문을 주므로 최대 5회까지 점점 길게 기다리며 다시 시도한다.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

VWORLD_URL = "https://api.vworld.kr/req/data"
MYHOME_URL = "https://apis.data.go.kr/1613000/HWSPR02/"
HUB_URL = "https://apis.data.go.kr/1613000/HsPmsHubService/"
HUB_ARCH_URL = "https://apis.data.go.kr/1613000/ArchPmsHubService/"
TAGO_URL = "https://apis.data.go.kr/1613000/"          # 국토교통부 TAGO 버스정류소·노선·위치정보(서비스별 활용신청이 따로 필요)
EDUINFO_URL = "https://eduinfo.go.kr/portal/theme/newSchInfoDetail.do"
EDUINFO_REFERER = "https://eduinfo.go.kr/portal/theme/newSchMapPage.do"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SECRET_PARAMS = ("serviceKey", "key", "domain")
MAX_ATTEMPTS = 5
WAIT_STEP_S = 2.0
USER_AGENT = "housing-board-regiontools/1.0"


class ApiError(RuntimeError):
    pass


class MissingKey(RuntimeError):
    pass


class QuotaExceeded(ApiError):
    """공공데이터포털 일일 호출 한도(resultCode 22 · LIMITED_NUMBER…) 초과. 다른 키가 있으면 그 키로 이어서 부른다."""


@dataclass(frozen=True)
class Keys:
    data_go_kr: str
    vworld: str
    vworld_domain: str
    data_go_kr_pool: tuple = ()      # DATA_GO_KR_KEY_BUILD_<N> 여러 개(번호 순). 비어 있으면 data_go_kr 하나만 쓴다
    vworld_other: tuple = ()         # 쓰지 않는 다른 V-World 키(운영키 등). 오류 문구에서 가리기 위해서만 갖고 있는다

    def pool(self) -> tuple:
        return self.data_go_kr_pool or ((self.data_go_kr,) if self.data_go_kr else ())

    def secrets(self) -> list[str]:
        return [s for s in (*self.pool(), self.data_go_kr, self.vworld, *self.vworld_other) if s]


def load_env(path) -> dict:
    """KEY=VALUE 줄을 읽는다. 주석(#)·빈 줄은 건너뛰고 값의 따옴표를 벗긴다."""
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("\"'")
    return env


_BUILD_KEY = re.compile(r"^DATA_GO_KR_KEY_BUILD_(\d+)$")


def _decode_key(v: str) -> str:
    return urllib.parse.unquote(v) if "%" in v else v      # 인코딩된 채 적어 둔 키도 디코딩된 값으로 맞춘다(요청에서 한 번만 인코딩)


def load_keys(path) -> Keys:
    """공공데이터포털 키: DATA_GO_KR_KEY_BUILD_<N>(여러 개, 한도에 닿으면 다음 키)가 있으면 그것을, 없으면 DATA_GO_KR_KEY 하나를 쓴다."""
    p = Path(path)
    if not p.exists():
        raise MissingKey(f"키 파일이 없음: {p.name}")
    env = load_env(p)
    numbered = []
    for k, v in env.items():
        m = _BUILD_KEY.match(k)
        if m and v:
            numbered.append((int(m.group(1)), v))
    pool = tuple(_decode_key(v) for _, v in sorted(numbered))
    # 수집·빌드 도구는 로컬에서만 돈다: 개발키(VWORLD_DEV_KEY, 도메인 localhost)가 있으면 그것을, 없으면 VWORLD_KEY 를 쓴다
    vworld = env.get("VWORLD_DEV_KEY") or env.get("VWORLD_KEY")
    missing = [k for k in ("VWORLD_DOMAIN",) if not env.get(k)]
    if not vworld:
        missing.insert(0, "VWORLD_KEY(또는 VWORLD_DEV_KEY)")
    if not pool and not env.get("DATA_GO_KR_KEY"):
        missing.insert(0, "DATA_GO_KR_KEY(또는 DATA_GO_KR_KEY_BUILD_<N>)")
    if missing:
        raise MissingKey(f"키가 없음: {', '.join(missing)}")
    first = pool[0] if pool else env["DATA_GO_KR_KEY"]
    other = tuple(k for k in (env.get("VWORLD_DEV_KEY"), env.get("VWORLD_KEY")) if k and k != vworld)
    return Keys(first, vworld, env["VWORLD_DOMAIN"], pool, other)


def redact(text: str, secrets) -> str:
    for s in secrets:
        if not s:
            continue
        for form in {s, urllib.parse.quote(s, safe=""), urllib.parse.quote_plus(s)}:
            text = text.replace(form, "<KEY>")
    return text


def cache_key(name: str, params: dict) -> str:
    clean = {k: str(v) for k, v in params.items() if k not in SECRET_PARAMS}
    raw = name + "|" + json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def extract_items(payload) -> list:
    """data.go.kr JSON 응답에서 항목 목록을 꺼낸다(items.item이 list·dict·빈 문자열인 경우 모두)."""
    body = (payload or {}).get("response", {}).get("body", {}) if isinstance(payload, dict) else {}
    items = body.get("items", body.get("item"))
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return list(items) if isinstance(items, list) else []


def total_count(payload) -> int:
    try:
        return int(payload["response"]["body"].get("totalCount") or 0)
    except (KeyError, TypeError, ValueError, AttributeError):
        return 0


def pan_id(url) -> str | None:
    m = re.search(r"[?&]panId=([^&]+)", str(url or ""))
    return m.group(1) if m else None


def _default_fetch(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except Exception as e:  # 네트워크 오류는 재시도 대상
        return -1, type(e).__name__.encode()


_AUTH_ERR = re.compile(rb"<returnAuthMsg>([^<]+)</returnAuthMsg>|<returnReasonCode>(\d+)</returnReasonCode>")
# data.go.kr XML 오류 중 잠시 뒤 다시 시도할 만한 것. 키 미등록·한도 초과 등은 바로 멈춘다.
_RETRYABLE_AUTH = ("APPLICATION_ERROR", "TIMEOUT", "HTTP_ERROR", "UNKNOWN_ERROR")


class Client:
    def __init__(self, keys: Keys, cache_dir=None, refresh: bool = False, fetch=None, sleep=time.sleep):
        self.keys = keys
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.refresh = refresh
        self.fetch = fetch or _default_fetch
        self.sleep = sleep
        self.calls = collections.Counter()
        self._key_i = 0              # 지금 쓰는 data.go.kr 키(풀 안 번호)
        self._quota_dead: set = set()  # 이번 실행에서 한도에 닿은 키 번호

    # ---- 공통 ----
    def _err(self, msg: str) -> ApiError:
        return ApiError(redact(msg, self.keys.secrets()))

    def _cache_path(self, name: str, params: dict) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{name}-{cache_key(name, params)}.json"

    def _get_json(self, name: str, url: str, params: dict, check, timeout: int = 60):
        """GET + JSON. check(payload)는 정상이면 None, 재시도할 오류면 'retry:…', 멈출 오류면 'fatal:…'."""
        cp = self._cache_path(name, params)
        if cp and cp.exists() and not self.refresh:
            self.calls["cache"] += 1
            return json.loads(cp.read_text(encoding="utf-8"))
        full = url + "?" + urllib.parse.urlencode(params)
        last = "응답 없음"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.calls["net"] += 1
            self.calls[name] += 1
            status, raw = self.fetch(full, None, {"User-Agent": USER_AGENT}, timeout)
            m = _AUTH_ERR.search(raw or b"")
            if m:
                code = (m.group(1) or m.group(2) or b"").decode("utf-8", "replace").strip()
                if "LIMITED_NUMBER" in code or code == "22":
                    raise QuotaExceeded(f"{name}: 일일 호출 한도 초과")
                if not any(t in code for t in _RETRYABLE_AUTH):
                    raise self._err(f"{name}: 인증·서비스 오류 {code}")
                last = f"서비스 오류 {code}"
            elif status == 429:
                raise QuotaExceeded(f"{name}: 일일 호출 한도 초과(HTTP 429)")
            elif status != 200:
                last = f"HTTP {status}"
            elif not (raw or b"").strip():
                last = "빈 본문"
            else:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    last = "JSON 아님"
                else:
                    verdict = check(payload)
                    if verdict is None:
                        if cp:
                            cp.parent.mkdir(parents=True, exist_ok=True)
                            cp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                        return payload
                    if verdict.startswith("quota:"):
                        raise QuotaExceeded(f"{name}: {verdict[6:]}")
                    if verdict.startswith("fatal:"):
                        raise self._err(f"{name}: {verdict[6:]}")
                    last = verdict[6:]
            if attempt < MAX_ATTEMPTS:
                self.sleep(WAIT_STEP_S * attempt)
        raise self._err(f"{name}: {MAX_ATTEMPTS}회 시도 실패({last})")

    # ---- data.go.kr ----
    @staticmethod
    def _check_data_go_kr(payload):
        if not isinstance(payload, dict) or "response" not in payload:
            return "retry:응답 형식이 다름"
        code = str(payload["response"].get("header", {}).get("resultCode", "00"))
        if code not in ("00", "0", "000"):
            msg = payload["response"].get("header", {}).get("resultMsg", "")
            if code == "22":      # 일일 호출 한도 초과: 같은 키로는 다시 부르지 않고 다음 키로 넘어간다
                return f"quota:결과 코드 {code} {msg}"
            if code == "99":      # TAGO 가 동시 접속이 가득 찼을 때 주는 일시 오류("가용한 세션이 존재하지 않습니다")
                return f"retry:결과 코드 {code} {msg}"
            return f"fatal:결과 코드 {code} {msg}"
        return None

    def _current_key(self) -> str:
        pool = self.keys.pool()
        if not pool:
            raise MissingKey("data.go.kr 키가 없음")
        return pool[self._key_i % len(pool)]

    def _next_key(self, err: QuotaExceeded) -> None:
        """한도에 닿은 키를 이번 실행에서 빼고 다음 키로. 모두 닿았으면 그 오류를 그대로 올린다."""
        pool = self.keys.pool()
        self._quota_dead.add(self._key_i % len(pool))
        left = [i for i in range(len(pool)) if i not in self._quota_dead]
        if not left:
            raise QuotaExceeded(f"{err} (키 {len(pool)}개 모두 한도 초과 — 한국시간 자정 이후 다시)") from None
        self._key_i = left[0]
        self.calls["key-switch"] += 1

    def _data_go_kr_all(self, name: str, url: str, params: dict, rows: int = 100) -> list:
        out: list = []
        page = 1
        while True:
            while True:
                p = {"serviceKey": self._current_key(), **params, "numOfRows": rows, "pageNo": page, "_type": "json"}
                try:
                    payload = self._get_json(name, url, p, self._check_data_go_kr)
                    break
                except QuotaExceeded as e:
                    self._next_key(e)
            items = extract_items(payload)
            out += items
            total = total_count(payload)
            if not items or page * rows >= total:
                return out
            page += 1

    def myhome_notices(self) -> dict:
        """마이홈 공고 전체: rental(임대)·sale(분양)."""
        return {"rental": self._data_go_kr_all("myhome-rental", MYHOME_URL + "rsdtRcritNtcList", {}),
                "sale": self._data_go_kr_all("myhome-sale", MYHOME_URL + "ltRsdtRcritNtcList", {})}

    def hub_basis(self, sigungu: str, bjdong: str) -> list:
        return self._data_go_kr_all("hub-basis", HUB_URL + "getHpBasisOulnInfo",
                                    {"sigunguCd": sigungu, "bjdongCd": bjdong})

    def hub_dong(self, sigungu: str, bjdong: str) -> list:
        return self._data_go_kr_all("hub-dong", HUB_URL + "getHpDongOulnInfo",
                                    {"sigunguCd": sigungu, "bjdongCd": bjdong})

    def hub_arch_dong(self, sigungu: str, bjdong: str) -> list:
        """건축인허가 기본개요(주택 아닌 건축물 포함) 법정동 전체."""
        return self._data_go_kr_all("hub-arch", HUB_ARCH_URL + "getApBasisOulnInfo", {"sigunguCd": sigungu, "bjdongCd": bjdong})

    # ---- 국토교통부 TAGO 버스정보 ----
    def tago_stops_near(self, lat: float, lon: float) -> list:
        """좌표에서 반경 약 500 m 안의 정류소(좌표기반근접정류소): nodeid·nodenm·nodeno·gpslati·gpslong. 없으면 빈 목록."""
        return self._data_go_kr_all("tago-near", TAGO_URL + "BusSttnInfoInqireService/getCrdntPrxmtSttnList",
                                    {"gpsLati": f"{lat:.6f}", "gpsLong": f"{lon:.6f}"})

    def tago_stop_routes(self, city, node_id: str) -> list:
        """정류소를 지나는 노선(정류소별경유노선): routeid·routeno·routetp·startnodenm·endnodenm."""
        return self._data_go_kr_all("tago-stop-routes", TAGO_URL + "BusSttnInfoInqireService/getSttnThrghRouteList",
                                    {"cityCode": city, "nodeid": node_id})

    def tago_route_stops(self, city, route_id: str) -> list:
        """노선이 지나는 정류소를 정류소순서(nodeord)대로(왕복 전체, 기점(미정차) 같은 가상 정류소 포함). 좌표가 문자열인 행도 있다."""
        return self._data_go_kr_all("tago-route-stops", TAGO_URL + "BusRouteInfoInqireService/getRouteAcctoThrghSttnList",
                                    {"cityCode": city, "routeId": route_id}, rows=300)

    # ---- 교육재정알리미 (키 없음) ----
    def eduinfo_new_schools(self, attempts: int = 3) -> list:
        """신설예정학교 전국 목록. 검색 조건을 비우고 POST 하면 전체(약 220교)가 한 번에 온다. 시군구 거르기는 호출한 쪽이 한다."""
        name, form = "eduinfo-newschool", {"schlSeq": "", "yymmdd": "", "searchRg": "", "searchOffc": "", "searchWd": ""}
        cp = self._cache_path(name, form)
        if cp and cp.exists() and not self.refresh:
            self.calls["cache"] += 1
            return json.loads(cp.read_text(encoding="utf-8"))
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest", "Referer": EDUINFO_REFERER}
        last = "응답 없음"
        for attempt in range(1, attempts + 1):
            self.calls["net"] += 1
            self.calls[name] += 1
            status, raw = self.fetch(EDUINFO_URL, data, headers, 60)
            if status == 200:
                try:
                    rows = json.loads(raw.decode("utf-8")).get("result")
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    rows = None
                if isinstance(rows, list):
                    if cp:
                        cp.parent.mkdir(parents=True, exist_ok=True)
                        cp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                    return rows
                last = "result 목록이 없음"
            else:
                last = f"HTTP {status}"
            if attempt < attempts:
                self.sleep(WAIT_STEP_S * attempt)
        raise self._err(f"{name}: {attempts}회 시도 실패({last})")

    # ---- V-World ----
    @staticmethod
    def _check_vworld(payload):
        r = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(r, dict):
            return "retry:응답 형식이 다름"
        st = r.get("status")
        if st in ("OK", "NOT_FOUND"):
            return None
        err = r.get("error") or {}
        code = err.get("code", st)
        if code in ("SYSTEM_ERROR", "UNKNOWN_ERROR"):
            return f"retry:{code}"
        return f"fatal:{code} {err.get('text', '')}"

    def vworld_features(self, layer: str, bbox=None, attr_filter: str | None = None, size: int = 1000) -> list:
        out: list = []
        page = 1
        while True:
            p = {"service": "data", "request": "GetFeature", "data": layer, "key": self.keys.vworld,
                 "domain": self.keys.vworld_domain, "format": "json", "size": size, "page": page, "crs": "EPSG:4326"}
            if bbox is not None:
                p["geomFilter"] = "BOX({},{},{},{})".format(*bbox)
            if attr_filter:
                p["attrFilter"] = attr_filter
            payload = self._get_json(f"vworld-{layer}", VWORLD_URL, p, self._check_vworld)
            r = payload["response"]
            if r.get("status") == "NOT_FOUND":
                return out
            out += r.get("result", {}).get("featureCollection", {}).get("features", [])
            pages = int((r.get("page") or {}).get("total") or 1)
            if page >= pages:
                return out
            page += 1

    def parcel(self, pnu: str) -> dict | None:
        fs = self.vworld_features("LP_PA_CBND_BUBUN", attr_filter=f"pnu:=:{pnu}")
        return fs[0] if fs else None

    # ---- Overpass (키 없음) ----
    def overpass(self, query: str, budget_s: float = 120.0, attempts: int = 3) -> dict:
        """Overpass POST. 바쁜 서버(429·504·네트워크 오류)는 짧게 기다려 다시 시도하되 전체 budget_s 안에서만."""
        name = "overpass"
        cp = self._cache_path(name, {"q": query})
        if cp and cp.exists() and not self.refresh:
            self.calls["cache"] += 1
            return json.loads(cp.read_text(encoding="utf-8"))
        data = urllib.parse.urlencode({"data": query}).encode("utf-8")
        start = time.monotonic()
        last = "응답 없음"
        for attempt in range(1, attempts + 1):
            remaining = budget_s - (time.monotonic() - start)
            if remaining < 5:
                break
            self.calls["net"] += 1
            self.calls[name] += 1
            status, raw = self.fetch(OVERPASS_URL, data, {"User-Agent": USER_AGENT}, max(5, min(90, remaining)))
            if status == 200:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    last = "JSON 아님"
                else:
                    if cp:
                        cp.parent.mkdir(parents=True, exist_ok=True)
                        cp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    return payload
            else:
                last = f"HTTP {status}"
                if status not in (429, 502, 503, 504, -1):
                    break
            if attempt < attempts:
                self.sleep(5.0 * attempt)
        raise ApiError(f"overpass: {last}")
