import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.additional_apis import parse_register, parse_lh_notices, parse_statistics, collect_lh_notices, collect_statistics, STAT_SERIES
from backend.collectors import Fetcher
from backend.connection_audit import connection_audit
from backend.sources import SOURCES

SOURCES_BY_ID = {s["id"]: s for s in SOURCES}


class AdditionalApiTests(unittest.TestCase):
    def register(self, purpose="공동주택", **extra):
        row = dict(mgmBldrgstPk=1000000000000000190077, sigunguCd="11680", bjdongCd="10300",
                   platPlc="서울특별시 강남구 개포동 1", mainPurpsCdNm=purpose, hhldCnt=0, hoCnt=50,
                   fmlyCnt=0, crtnDay="20220813", useAprDay="19921011")
        row.update(extra)
        return dict(response=dict(header=dict(resultCode="00"), body=dict(totalCount=1,items=dict(item=row))))

    def parse_register(self, data):
        return parse_register(data,SOURCES_BY_ID["building_register"],"서울특별시","11680","10300")

    def test_stock_households_never_use_shop_unit_count_as_supply(self):
        records,total,fetched=self.parse_register(self.register())
        self.assertEqual((total,fetched),(1,1))
        self.assertEqual(records[0][1],"1000000000000000190077")
        payload=records[0][2]
        self.assertEqual(payload["units"],0)
        self.assertEqual(payload["unit_count"],50)
        self.assertEqual(payload["dates"]["건축물 사용승인일"],"1992-10-11")
        self.assertIn("REGISTER_STOCK_NOT_SUPPLY",payload["warnings"])
        self.assertNotIn("move_in_actual_date",payload)
        self.assertEqual(self.parse_register(self.register("판매시설"))[0],[])

    def test_register_requires_auth_and_region(self):
        data=self.register();data["response"]["header"]["resultCode"]="30"
        with self.assertRaises(ValueError):self.parse_register(data)
        with self.assertRaises(ValueError):self.parse_register(self.register(bldNm="건물", **{"bjdongCd":"99999"}))

    def notice(self, pan="000001", subtype="07"):
        return dict(PAN_ID=pan, ALL_CNT="1", CNP_CD_NM="경기도", UPP_AIS_TP_CD="06", PAN_DT="20180102", PAN_NT_ST_DT="2018.01.02",
                    AIS_TP_CD=subtype, AIS_TP_CD_NM="국민임대" if subtype=="07" else "가정어린이집",
                    CCR_CNNT_SYS_DS_CD="02", PAN_NM="과거 공고", DTL_URL="https://apply.lh.or.kr/view")

    def parse_lh(self, rows):
        return parse_lh_notices([dict(resHeader=[dict(SS_CODE="Y")],dsList=rows)],SOURCES_BY_ID["lh_notice"],"41","06","2018-01-01","2026-10-03")

    def test_lh_honeymoon_category_and_incheon_are_included(self):
        row=dict(self.notice(),UPP_AIS_TP_CD='39',AIS_TP_CD='39',AIS_TP_CD_NM='공공분양(신혼희망)',CNP_CD_NM='인천광역시')
        result=parse_lh_notices([dict(resHeader=[dict(SS_CODE='Y')],dsList=[row])],SOURCES_BY_ID['lh_notice'],'28','39','2018-01-01','2026-10-12')
        self.assertEqual(result[0][0][2]['region'],'인천광역시')
        self.assertEqual(result[0][0][2]['notice_type'],'공공분양(신혼희망)')

    def test_lh_keeps_old_notice_identifier_and_unknown_units(self):
        records,total,fetched,excluded,_=self.parse_lh([self.notice()])
        self.assertEqual((total,fetched,excluded),(1,1,{"nonhousing":0,"multi_region":0}))
        self.assertTrue(records[0][1].startswith("000001:"))
        self.assertEqual(records[0][2]["source_date"],"2018-01-02")
        self.assertIsNone(records[0][2]["units"])
        self.assertEqual(self.parse_lh([self.notice(subtype="40")])[3]["nonhousing"],1)

    def test_lh_multi_region_notice_is_preserved_raw_without_invented_regional_assignment(self):
        row=self.notice();row["CNP_CD_NM"]="인천광역시 외"
        records,total,fetched,excluded,_=self.parse_lh([row])
        self.assertEqual(records,[])
        self.assertEqual((total,fetched),(1,1))
        self.assertEqual(excluded["multi_region"],1)

    def test_lh_reposted_old_notice_uses_posted_date_for_query_window(self):
        row=self.notice();row.update(PAN_DT="20171205",PAN_NT_ST_DT="2018.05.30")
        payload=self.parse_lh([row])[0][0][2]
        self.assertEqual(payload["source_date"],"2018-05-30")
        self.assertEqual(payload["dates"]["원천 공고일 PAN_DT"],"2017-12-05")

    def test_lh_rejects_wrong_region_period_and_duplicate(self):
        for field,value in [("CNP_CD_NM","인천광역시"),("PAN_NT_ST_DT","20171231"),("UPP_AIS_TP_CD","05")]:
            row=self.notice();row[field]=value
            with self.assertRaises(ValueError):self.parse_lh([row])
        row=self.notice();row["ALL_CNT"]="2"
        with self.assertRaises(ValueError):self.parse_lh([row,row])

    def test_lh_collector_rejects_repeated_page_instead_of_double_counting(self):
        class Fetch:
            def get(inner,url,suffix,params):
                rows=[dict(self.notice(str(i)),ALL_CNT="101",CNP_CD_NM="서울특별시",UPP_AIS_TP_CD="05") for i in range(100)]
                return json.dumps([dict(resHeader=[dict(SS_CODE="Y")],dsList=rows)])
        with patch.dict(os.environ,{"POC10_LH_NOTICE_SERVICE_KEY":"test"}):
            with self.assertRaises(ValueError):collect_lh_notices(SOURCES_BY_ID["lh_notice"],Fetch())

    def stat(self, rows, **extra):
        return dict(result_status=dict(status_code="INFO-000"),result_data=dict(unitName="호",cert_id="never-persist",formList=rows,**extra))

    def test_stat_totals_exclude_subtotals_and_credential_echo(self):
        total=dict(date="201801",부문명="총계",시도별="서울",사용검사실적=4337,**{"구  분":"총계"})
        records=parse_statistics(self.stat([total,dict(total,부문명="소계",사용검사실적=123)]),SOURCES_BY_ID["molit_statistics"],STAT_SERIES[0],"201801","201802")
        self.assertEqual(len(records),1)
        self.assertEqual(records[0][2]["units"],4337)
        self.assertEqual(records[0][2]["source_date"],"2018-01-31")
        self.assertNotIn("never-persist",str(records))
        self.assertIn("REGIONAL_TOTAL_NOT_POLICY_ACTUAL",records[0][2]["warnings"])
        with self.assertRaises(ValueError):parse_statistics(self.stat([total,total]),SOURCES_BY_ID["molit_statistics"],STAT_SERIES[0],"201801","201802")

    def test_stat_no_result_is_unknown_and_auth_error_is_failure(self):
        source=SOURCES_BY_ID["molit_statistics"]
        self.assertEqual(parse_statistics(dict(result_status=dict(status_code="INFO-200")),source,STAT_SERIES[0],"201801","201801"),[])
        with self.assertRaises(ValueError):parse_statistics(dict(result_status=dict(status_code="INFO-100")),source,STAT_SERIES[0],"201801","201801")

    def test_stat_collects_origin_history_only_until_published_period(self):
        calls=[]
        class Fetch:
            def get(inner,url,suffix,params):
                calls.append(params)
                if "period.do" in url:return json.dumps(dict(periodList=[dict(MNG_DIV_VL="201802")]))
                row=dict(date="201801",부문명="총계",시도별="서울")
                row.update({"구  분":"총계","사용검사실적":10})
                return json.dumps(self.stat([row]))
        with patch.dict(os.environ,{"POC10_MOLIT_STAT_API_KEY":"test"}),patch("backend.additional_apis.STAT_SERIES",[STAT_SERIES[0]]),patch("backend.additional_apis.collection_start",return_value=date(2018,1,1)):
            records,stats=collect_statistics(SOURCES_BY_ID["molit_statistics"],Fetch())
        self.assertEqual(calls[1]["start_dt"],"201801")
        self.assertEqual(calls[1]["end_dt"],"201802")
        self.assertEqual(len(records),1)
        self.assertFalse(stats["series"][0]["complete_query"])
        self.assertEqual(len(stats["series"][0]["missing_period_regions"]),3)

    def test_fetcher_removes_statistics_echo_from_saved_response_and_url(self):
        with tempfile.TemporaryDirectory() as root:
            fetcher=Fetcher("molit_statistics",root)
            fetcher.client.close()
            fetcher.client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={"result_data":{"cert_id":"echoed-secret"}})))
            try:
                content=fetcher.get("https://stat.molit.go.kr/portal/openapi/service/rest/getList.do","json",params={"key":"echoed-secret"})
                self.assertNotIn(b"echoed-secret",content)
                self.assertNotIn("echoed-secret",str(fetcher.manifest))
                self.assertNotIn(b"echoed-secret",next(Path(root).rglob("*.json")).read_bytes())
            finally:fetcher.close()

    def test_connection_status_requires_successful_collection(self):
        source=dict(SOURCES_BY_ID["building_register"],status="NOT_COLLECTED",key_configured=True,record_count=0,last_success=None)
        self.assertEqual(connection_audit([source])["planned"][0]["readiness"],"CONNECTOR_READY")
        source.update(status="SUCCESS",record_count=50,last_success="2026-10-03")
        guide=connection_audit([source])["planned"][0]
        self.assertEqual(guide["readiness"],"CONNECTED")
        self.assertEqual(guide["record_count"],50)


if __name__ == "__main__":unittest.main()
