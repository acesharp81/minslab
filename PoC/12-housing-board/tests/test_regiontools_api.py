import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import api

FAKE_DG = "fake+data/go==KEY"
FAKE_VW = "FAKE-VWORLD-KEY-0000"
KEYS = api.Keys(data_go_kr=FAKE_DG, vworld=FAKE_VW, vworld_domain="example.test")


def body(obj):
    return json.dumps(obj).encode("utf-8")


def hub_page(items, total):
    return body({"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": items}, "totalCount": total}}})


def vw_page(features, page, pages):
    return body({"response": {"status": "OK", "page": {"total": str(pages), "current": str(page)},
                              "result": {"featureCollection": {"type": "FeatureCollection", "features": features}}}})


class FakeFetch:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []
        self.posts = []

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.urls.append(url)
        self.posts.append((data, headers))
        return self.responses.pop(0)


class Env(unittest.TestCase):
    def test_load_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env.local"
            p.write_text('# 주석\nDATA_GO_KR_KEY="abc+/="\nVWORLD_KEY=xyz\nVWORLD_DOMAIN=\'dom\'\n\n', encoding="utf-8")
            env = api.load_env(p)
            self.assertEqual(env, {"DATA_GO_KR_KEY": "abc+/=", "VWORLD_KEY": "xyz", "VWORLD_DOMAIN": "dom"})
            keys = api.load_keys(p)
            self.assertEqual(keys.vworld_domain, "dom")

    def test_missing_keys_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env.local"
            p.write_text("VWORLD_KEY=xyz\n", encoding="utf-8")
            with self.assertRaises(api.MissingKey):
                api.load_keys(p)
            with self.assertRaises(api.MissingKey):
                api.load_keys(Path(tmp) / "none")


class Helpers(unittest.TestCase):
    def test_cache_key_ignores_secrets_and_order(self):
        a = api.cache_key("hub", {"serviceKey": "k1", "pageNo": 1, "sigunguCd": "12330"})
        b = api.cache_key("hub", {"sigunguCd": "12330", "pageNo": 1, "serviceKey": "k2"})
        self.assertEqual(a, b)
        self.assertNotIn("k1", a)
        self.assertNotEqual(a, api.cache_key("hub", {"sigunguCd": "12330", "pageNo": 2}))

    def test_extract_items_variants(self):
        self.assertEqual(api.extract_items({"response": {"body": {"items": {"item": [{"a": 1}]}}}}), [{"a": 1}])
        self.assertEqual(api.extract_items({"response": {"body": {"items": {"item": {"a": 1}}}}}), [{"a": 1}])
        self.assertEqual(api.extract_items({"response": {"body": {"items": ""}}}), [])
        self.assertEqual(api.extract_items({"response": {"body": {"item": [{"a": 2}]}}}), [{"a": 2}])

    def test_redact(self):
        s = api.redact("x serviceKey=fake%2Bdata%2Fgo%3D%3DKEY and fake+data/go==KEY", [FAKE_DG])
        self.assertNotIn("KEY", s.replace("<KEY>", ""))

    def test_pan_id(self):
        url = "https://apply.lh.or.kr/x/selectWrtancInfo.do?panId=0000061131&ccrCnntSysDsCd=02"
        self.assertEqual(api.pan_id(url), "0000061131")
        self.assertIsNone(api.pan_id("https://example.org/"))


class ClientCalls(unittest.TestCase):
    def test_retry_then_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            waits = []
            fetch = FakeFetch([(503, b""), (200, b""), (200, hub_page([{"a": 1}, {"a": 2}], 2))])
            c = api.Client(KEYS, cache_dir=tmp, fetch=fetch, sleep=waits.append)
            self.assertEqual(c.hub_basis("12330", "10600"), [{"a": 1}, {"a": 2}])
            self.assertEqual(len(fetch.urls), 3)
            self.assertEqual(waits, sorted(waits))
            self.assertGreater(waits[1], waits[0])
            # 두 번째는 캐시에서 읽는다
            c2 = api.Client(KEYS, cache_dir=tmp, fetch=FakeFetch([]), sleep=waits.append)
            self.assertEqual(c2.hub_basis("12330", "10600"), [{"a": 1}, {"a": 2}])
            self.assertEqual(c2.calls["cache"], 1)
            for f in Path(tmp).rglob("*"):
                self.assertNotIn(FAKE_DG, f.name)
                if f.is_file():
                    text = f.read_text("utf-8")
                    self.assertNotIn(FAKE_DG, text)
                    self.assertNotIn("serviceKey", text)

    def test_gives_up_after_five_attempts(self):
        fetch = FakeFetch([(503, b"")] * 5)
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        with self.assertRaises(api.ApiError) as cm:
            c.hub_basis("12330", "10600")
        self.assertEqual(len(fetch.urls), 5)
        self.assertNotIn(FAKE_DG, str(cm.exception))

    def test_key_rejection_is_not_retried(self):
        xml = b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>"
        fetch = FakeFetch([(200, xml)])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        with self.assertRaises(api.ApiError) as cm:
            c.hub_basis("12330", "10600")
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", str(cm.exception))
        self.assertEqual(len(fetch.urls), 1)

    def test_hub_paging(self):
        fetch = FakeFetch([(200, hub_page([{"n": i} for i in range(100)], 150)),
                           (200, hub_page([{"n": i} for i in range(100, 150)], 150))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(c.hub_basis("12330", "10600")), 150)
        self.assertIn("pageNo=2", fetch.urls[1])

    def test_vworld_paging_and_not_found(self):
        f1 = {"type": "Feature", "properties": {"a": 1}, "geometry": None}
        fetch = FakeFetch([(200, vw_page([f1], 1, 2)), (200, vw_page([f1], 2, 2)),
                           (200, body({"response": {"status": "NOT_FOUND"}}))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(c.vworld_features("LT_C_BLDGINFO", bbox=(126.0, 35.0, 126.1, 35.1))), 2)
        self.assertIn("BOX%28126.0%2C35.0%2C126.1%2C35.1%29", fetch.urls[0])
        self.assertEqual(c.vworld_features("LP_PA_CBND_BUBUN", attr_filter="pnu:=:1233010600105190000"), [])

    def test_overpass_retries_busy_server_then_gives_up(self):
        ok = body({"elements": [{"type": "node", "lat": 35.1, "lon": 126.7, "tags": {"name": "역"}}]})
        waits = []
        fetch = FakeFetch([(504, b"busy"), (429, b""), (200, ok)])
        c = api.Client(KEYS, fetch=fetch, sleep=waits.append)
        self.assertEqual(len(c.overpass("[out:json];node(1);out;")["elements"]), 1)
        self.assertEqual(len(fetch.urls), 3)
        self.assertEqual(len(waits), 2)
        fetch = FakeFetch([(504, b"")] * 3)
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        with self.assertRaises(api.ApiError):
            c.overpass("[out:json];node(1);out;")
        self.assertEqual(len(fetch.urls), 3)

    def test_eduinfo_new_schools_posts_an_empty_search_without_any_key(self):
        rows = [{"schlNm": "(가칭)계양1초", "openSchdYm": "202903"}]
        fetch = FakeFetch([(503, b""), (200, body({"result": rows, "level": 9}))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(c.eduinfo_new_schools(), rows)
        self.assertEqual(len(fetch.urls), 2)
        data, headers = fetch.posts[1]
        self.assertIn(b"searchRg=", data)
        self.assertIn("eduinfo.go.kr", fetch.urls[1])
        self.assertIn("eduinfo.go.kr", headers["Referer"])
        for needle in (FAKE_DG, FAKE_VW):
            self.assertNotIn(needle.encode(), data)
            self.assertNotIn(needle, fetch.urls[1])

    def test_eduinfo_new_schools_gives_up_and_rejects_a_page_without_result(self):
        c = api.Client(KEYS, fetch=FakeFetch([(504, b"")] * 3), sleep=lambda s: None)
        with self.assertRaises(api.ApiError):
            c.eduinfo_new_schools()
        c = api.Client(KEYS, fetch=FakeFetch([(200, body({"level": 9}))] * 3), sleep=lambda s: None)
        with self.assertRaises(api.ApiError):
            c.eduinfo_new_schools()

    def test_eduinfo_new_schools_is_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"schlNm": "a"}]
            api.Client(KEYS, cache_dir=tmp, fetch=FakeFetch([(200, body({"result": rows}))]), sleep=lambda s: None).eduinfo_new_schools()
            c2 = api.Client(KEYS, cache_dir=tmp, fetch=FakeFetch([]), sleep=lambda s: None)
            self.assertEqual(c2.eduinfo_new_schools(), rows)
            self.assertEqual(c2.calls["cache"], 1)

    def test_hub_arch_dong_pages_and_uses_the_permit_service(self):
        fetch = FakeFetch([(200, hub_page([{"n": i} for i in range(100)], 120)), (200, hub_page([{"n": i} for i in range(100, 120)], 120))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(len(c.hub_arch_dong("28245", "10900")), 120)
        self.assertIn("ArchPmsHubService/getApBasisOulnInfo", fetch.urls[0])
        self.assertIn("bjdongCd=10900", fetch.urls[0])

    def test_tago_calls_use_the_right_services_and_params_and_page(self):
        fetch = FakeFetch([(200, hub_page([{"nodeid": "S1"}], 1)), (200, hub_page([{"routeid": "R1"}], 1)),
                           (200, hub_page([{"nodeord": i} for i in range(300)], 350)), (200, hub_page([{"nodeord": i} for i in range(300, 350)], 350)),
                           (200, body({"response": {"header": {"resultCode": "00"}, "body": {"items": "", "totalCount": 0}}}))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        self.assertEqual(c.tago_stops_near(37.5559, 126.7542), [{"nodeid": "S1"}])
        self.assertIn("BusSttnInfoInqireService/getCrdntPrxmtSttnList", fetch.urls[0])
        self.assertIn("gpsLati=37.555900", fetch.urls[0])
        self.assertIn("gpsLong=126.754200", fetch.urls[0])
        self.assertEqual(c.tago_stop_routes(23, "S1"), [{"routeid": "R1"}])
        self.assertIn("BusSttnInfoInqireService/getSttnThrghRouteList", fetch.urls[1])
        self.assertIn("cityCode=23", fetch.urls[1])
        self.assertIn("nodeid=S1", fetch.urls[1])
        self.assertEqual(len(c.tago_route_stops(23, "R1")), 350)
        self.assertIn("BusRouteInfoInqireService/getRouteAcctoThrghSttnList", fetch.urls[2])
        self.assertIn("routeId=R1", fetch.urls[2])
        self.assertIn("numOfRows=300", fetch.urls[2])
        self.assertIn("pageNo=2", fetch.urls[3])
        self.assertEqual(c.tago_stops_near(37.4, 126.3), [])                     # 정류소가 없는 곳은 빈 목록(오류가 아님)
        for u in fetch.urls:
            self.assertNotIn(FAKE_DG, u)                                          # 키는 URL 인코딩되어 나간다(+ / = 가 그대로면 승인된 키도 거절된다)

    def test_tago_busy_server_is_retried_but_other_error_codes_are_not(self):
        busy = body({"response": {"header": {"resultCode": "99", "resultMsg": "가용한 세션이 존재하지 않습니다. (30/30)"}}})
        fetch = FakeFetch([(200, busy), (200, busy), (200, hub_page([{"nodeid": "S1"}], 1))])
        waits = []
        c = api.Client(KEYS, fetch=fetch, sleep=waits.append)
        self.assertEqual(c.tago_stops_near(37.5, 126.7), [{"nodeid": "S1"}])
        self.assertEqual(len(fetch.urls), 3)
        self.assertEqual(len(waits), 2)
        bad = body({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}})
        fetch = FakeFetch([(200, bad)])
        with self.assertRaises(api.ApiError):
            api.Client(KEYS, fetch=fetch, sleep=lambda s: None).tago_stops_near(37.5, 126.7)
        self.assertEqual(len(fetch.urls), 1)

    def test_vworld_error_raises(self):
        fetch = FakeFetch([(200, body({"response": {"status": "ERROR", "error": {"code": "INVALID_KEY", "text": "x"}}}))])
        c = api.Client(KEYS, fetch=fetch, sleep=lambda s: None)
        with self.assertRaises(api.ApiError) as cm:
            c.vworld_features("LT_C_BLDGINFO", bbox=(126.0, 35.0, 126.1, 35.1))
        self.assertIn("INVALID_KEY", str(cm.exception))
        self.assertNotIn(FAKE_VW, str(cm.exception))


if __name__ == "__main__":
    unittest.main()


QUOTA_XML = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
             b"<returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>"
             b"<returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")


def quota_json():
    return body({"response": {"header": {"resultCode": "22", "resultMsg": "LIMITED"}}})


class BuildKeyPool(unittest.TestCase):
    def _env(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / ".env.local"
        p.write_text(text, encoding="utf-8")
        return p

    def test_load_keys_reads_numbered_build_keys_in_order_and_decodes(self):
        p = self._env("VWORLD_KEY=v\nVWORLD_DOMAIN=d\nDATA_GO_KR_KEY_BUILD_2=b%2Bb\nDATA_GO_KR_KEY_BUILD_1=a+a\nDATA_GO_KR_KEY_BUILD_10=c\nDATA_GO_KR_KEY=legacy\n")
        keys = api.load_keys(p)
        self.assertEqual(keys.data_go_kr_pool, ("a+a", "b+b", "c"))      # 번호 순(10 은 2 뒤), 인코딩된 값은 디코딩
        self.assertEqual(keys.data_go_kr, "a+a")
        self.assertEqual(keys.pool(), ("a+a", "b+b", "c"))
        self.assertTrue({"a+a", "b+b", "c", "v"} <= set(keys.secrets()))

    def test_load_keys_without_build_keys_uses_single_legacy_key(self):
        keys = api.load_keys(self._env("DATA_GO_KR_KEY=legacy\nVWORLD_KEY=v\nVWORLD_DOMAIN=d\n"))
        self.assertEqual(keys.pool(), ("legacy",))
        with self.assertRaises(api.MissingKey) as cm:
            api.load_keys(self._env("VWORLD_KEY=v\nVWORLD_DOMAIN=d\n"))
        self.assertIn("DATA_GO_KR_KEY", str(cm.exception))

    def _client(self, responses, pool=("k1", "k2")):
        keys = api.Keys(pool[0], FAKE_VW, "example.test", tuple(pool))
        fetch = FakeFetch(responses)
        return api.Client(keys, fetch=fetch, sleep=lambda s: None), fetch

    def test_quota_switches_to_next_key_and_keeps_going(self):
        for bad in (quota_json(), QUOTA_XML):
            client, fetch = self._client([(200, bad), (200, hub_page([{"a": 1}], 1))])
            self.assertEqual(client.hub_basis("28245", "10700"), [{"a": 1}])
            self.assertIn("serviceKey=k1", fetch.urls[0])
            self.assertIn("serviceKey=k2", fetch.urls[1])
            self.assertEqual(client.calls["key-switch"], 1)

    def test_http_429_also_switches(self):
        client, fetch = self._client([(429, b""), (200, hub_page([{"a": 1}], 1))])
        self.assertEqual(client.hub_basis("28245", "10700"), [{"a": 1}])
        self.assertIn("serviceKey=k2", fetch.urls[1])

    def test_dead_key_is_not_used_again_in_the_same_run(self):
        client, fetch = self._client([(200, quota_json()), (200, hub_page([{"a": 1}], 1)), (200, hub_page([{"b": 2}], 1))])
        client.hub_basis("28245", "10700")
        client.hub_dong("28245", "10700")
        self.assertEqual([("serviceKey=k1" in u) for u in fetch.urls], [True, False, False])

    def test_all_keys_exhausted_raises_quota_exceeded_without_leaking_keys(self):
        client, _ = self._client([(200, quota_json()), (200, quota_json())])
        with self.assertRaises(api.QuotaExceeded) as cm:
            client.hub_basis("28245", "10700")
        msg = str(cm.exception)
        self.assertIn("2개 모두 한도 초과", msg)
        for s in ("k1&", "serviceKey"):
            self.assertNotIn(s, msg)

    def test_paging_continues_with_the_switched_key(self):
        client, fetch = self._client([(200, hub_page([{"i": 1}], 2)), (200, quota_json()), (200, hub_page([{"i": 2}], 2))])
        # 한 쪽에 한 건씩(rows=1) 받다가 둘째 쪽에서 한도 오류가 나는 경우
        out = client._data_go_kr_all("hub-basis", api.HUB_URL + "x", {}, rows=1)
        self.assertEqual([r["i"] for r in out], [1, 2])
        self.assertIn("serviceKey=k1", fetch.urls[0])
        self.assertIn("serviceKey=k2", fetch.urls[2])
        self.assertIn("pageNo=2", fetch.urls[1]); self.assertIn("pageNo=2", fetch.urls[2])   # 같은 쪽을 다음 키로 다시 부른다

    def test_cache_key_ignores_which_key_was_used(self):
        self.assertEqual(api.cache_key("n", {"serviceKey": "k1", "a": 1}), api.cache_key("n", {"serviceKey": "k2", "a": 1}))


class VWorldKeyChoice(unittest.TestCase):
    def _load(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / ".env.local"
        p.write_text(text, encoding="utf-8")
        return api.load_keys(p)

    def test_dev_key_is_preferred_for_local_tools_and_both_are_redacted(self):
        keys = self._load("DATA_GO_KR_KEY=d\nVWORLD_KEY=operating-key\nVWORLD_DEV_KEY=development-key\nVWORLD_DOMAIN=localhost\n")
        self.assertEqual(keys.vworld, "development-key")
        self.assertEqual(keys.vworld_other, ("operating-key",))
        text = api.redact("호출 operating-key / development-key 실패", keys.secrets())
        self.assertNotIn("operating-key", text)
        self.assertNotIn("development-key", text)

    def test_falls_back_to_vworld_key_and_requires_one_of_them(self):
        keys = self._load("DATA_GO_KR_KEY=d\nVWORLD_KEY=operating-key\nVWORLD_DOMAIN=localhost\n")
        self.assertEqual(keys.vworld, "operating-key")
        self.assertEqual(keys.vworld_other, ())
        with self.assertRaises(api.MissingKey) as cm:
            self._load("DATA_GO_KR_KEY=d\nVWORLD_DOMAIN=localhost\n")
        self.assertIn("VWORLD_DEV_KEY", str(cm.exception))
