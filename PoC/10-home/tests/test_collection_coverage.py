import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from backend.additional_apis import collect_register
from backend.agency_data import collect_sh_inventory, parse_gh_plan, collect_gh_notices
from backend.coverage_audit import coverage_audit
from backend.sources import SOURCES
from backend.collectors import parse_policy

BY_ID={s['id']:s for s in SOURCES}


def register_data(page, total=101, duplicate=False, empty=False):
    indices=range((page-1)*100,min(page*100,total)) if not empty else []
    rows=[dict(mgmBldrgstPk=str(0 if duplicate else i),sigunguCd='11680',bjdongCd='10300',
               platPlc='서울특별시 강남구 개포동 1',mainPurpsCdNm='공동주택' if i==100 else '판매시설',hhldCnt=2)
          for i in indices]
    return dict(response=dict(header=dict(resultCode='00'),body=dict(totalCount=total,pageNo=page,items=dict(item=rows))))


class CollectionCoverageTests(unittest.TestCase):
    def collect_register(self, response):
        calls=[]
        class Fetch:
            def get(self,url,suffix,params):
                calls.append(params['pageNo']);return json.dumps(response(params['pageNo'])).encode()
        with patch('backend.additional_apis.DISTRICTS',[('서울특별시','11680','10300','개포동')]), patch('backend.additional_apis.key_for',return_value='fixture'):
            records,stats=collect_register(BY_ID['building_register'],Fetch())
        return records,stats,calls

    def test_register_collects_residential_row_after_first_page(self):
        rows,stats,calls=self.collect_register(register_data)
        self.assertEqual(calls,[1,2]);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][1],'100')
        self.assertEqual(stats['district_counts']['개포동']['fetched'],101)
        self.assertTrue(stats['complete_query']);self.assertFalse(stats['complete_population'])

    def test_register_rejects_duplicate_nonresidential_rows_across_pages(self):
        with self.assertRaisesRegex(ValueError,'중복'):
            self.collect_register(lambda p:register_data(p,duplicate=p==2))

    def test_register_rejects_missing_second_page(self):
        with self.assertRaisesRegex(ValueError,'누락'):
            self.collect_register(lambda p:register_data(p,empty=p==2))

    def test_register_rejects_total_change_without_partial_commit(self):
        with self.assertRaisesRegex(ValueError,'건수 변경'):
            self.collect_register(lambda p:register_data(p,total=101 if p==1 else 102))

    def test_sh_latest_housing_types_merge_without_history_or_pre_subscription_actuals(self):
        rows=[dict(id=str(i),source_id='sh_supply_plan',name='마곡지구 17단지',business_type='토지임대부',
                   is_latest_dataset=True,units=355 if i==0 else 26,main_subscription_units=180 if i==0 else 26,
                   pre_subscription_units=175 if i==0 else 0,dataset_version='2026-06-22',schedule_month='2026-02',
                   evidence_url='https://www.data.go.kr/data/15008820/fileData.do') for i in range(2)]
        rows.append(dict(rows[0],id='past',is_latest_dataset=False,units=99999))
        service=SimpleNamespace(rows=lambda kind:rows if kind=='sh_plan' else [])
        collected,stats=collect_sh_inventory(BY_ID['sh_inventory'],None,service)
        self.assertEqual(len(collected),1);row=collected[0][2]
        self.assertEqual(row['planned_units'],381);self.assertEqual(row['main_subscription_units'],206)
        self.assertEqual(row['proposed_policy'],'UNASSIGNED');self.assertIsNone(row['progress_pct'])
        self.assertEqual(sum(r['units'] for r in row['rows']),206)
        self.assertEqual(stats['linked_sample_rows'],2)

    def test_gh_plan_preserves_ranges_and_does_not_parse_commented_old_rows(self):
        html='''<div id="cms-content">(‘26년 4월 기준)<table><thead><tr><th>사업지구</th><th>분양/임대</th><th>전용면적(㎡)</th><th>공급세대</th><th>입주자모집</th><th>입주일</th><th>문의처</th></tr></thead><tbody><!--<tr><td>과거사업</td></tr>--><tr></tr><tr><td>다산지금A3</td><td rowspan="2">통합공공임대</td><td>60㎡미만</td><td>518세대</td><td>2026년 5~6월 중(최초)</td><td>2027년 하반기 예정</td><td>공급센터</td></tr><tr><td>광주역세권</td><td>60㎡미만</td><td>316세대</td><td>2026년 5월</td><td>2026년 하반기 예정</td><td>공급센터</td></tr></tbody></table></div>'''
        rows,stats=parse_gh_plan(BY_ID['gh_supply_plan'],html)
        self.assertEqual(len(rows),2);self.assertEqual(rows[1][2]['tenure'],'통합공공임대')
        self.assertIsNone(rows[0][2]['schedule_month']);self.assertEqual(rows[1][2]['schedule_month'],'2026-05')
        self.assertEqual(rows[0][2]['source_move_in_label'],'2027년 하반기 예정')
        self.assertIsNone(rows[0][2]['supply_units']);self.assertFalse(stats['complete_population'])

    def test_gh_notices_all_pages_keep_result_notices_without_units(self):
        calls=[]
        def html(offset):
            rows=''.join(f'<tr><td class="number">{i}</td><td class="title"><a href="?mode=view&amp;articleNo={i}">당첨자 발표 {i}</a></td><td class="date">26.01.02</td></tr>' for i in range(11-offset,max(0,1-offset),-1))
            return '<div id="cms-content"><table><tbody>'+rows+'</tbody></table></div>'
        class Fetch:
            def get(self,url,params):calls.append(params['article.offset']);return html(calls[-1])
        rows,stats=collect_gh_notices(BY_ID['gh_notice'],Fetch())
        self.assertEqual(calls,[0,10]);self.assertEqual(len(rows),11)
        self.assertTrue(stats['complete_query']);self.assertEqual(stats['fetched'],11)
        self.assertTrue(all(r[2]['units'] is None and r[2]['notice_class']=='RESULT' for r in rows))

    def test_coverage_cannot_infer_population_from_success(self):
        source=dict(BY_ID['building_register'],status='SUCCESS',last_success='2026-10-03',record_count=1,
            stats=dict(district_counts={'동':dict(matching_records=101,fetched=101,complete_query=True)}))
        result=coverage_audit([source]);row=result['items'][0]
        self.assertFalse(result['complete_population']);self.assertFalse(row['complete_population'])
        self.assertEqual(row['query_status'],'VERIFIED');self.assertEqual(row['provided_records'],101)
        self.assertIn('6개 법정동',row['scope'])

    def test_policy_article_does_not_invent_remaining_candidate_names_or_group_units(self):
        text='후보지 11곳 선정. 효창공원앞역 북측 후보지는 약 4000호. 망원체육공원 인근. 이수역 동측. 고은산 서측과 목4동 강서고 6786호. 송중동 주민센터·녹번동근린공원·신길4 5032호. '+('개별 검토 필요 '*20)
        records,stats=parse_policy('urban_930','<div class="view_cont">'+text+'</div>')
        self.assertEqual(stats['missing_candidate_names'],8);self.assertEqual(stats['additional_designated_projects'],5)
        projects=[p for kind,_,p in records if kind=='project']
        self.assertEqual(len(projects),8);self.assertEqual(sum(p['planned_units'] or 0 for p in projects),4000)
        self.assertFalse(stats['complete_query'])

    def test_geocoding_continues_after_cached_parents(self):
        from backend.api_samples import collect_locations
        old=dict(id='first',name='기존주소',region='서울특별시',sample_kind='notice',source_object_id='1',address='서울특별시 강남구 1')
        new=dict(old,id='second',name='추가주소',source_object_id='2',address='서울특별시 강남구 2')
        cached=dict(parent_sample_id='first',address=old['address'])
        service=SimpleNamespace(rows=lambda kind:[cached] if kind=='location' else [old,new] if kind=='notice' else [])
        calls=[]
        class Fetch:
            def get(self,url,suffix,params,headers):
                calls.append(params['address']);return json.dumps({'response':{'status':'NOT_FOUND'}})
        with patch('backend.api_samples.key_for',return_value='fixture'):
            rows,stats=collect_locations(BY_ID['vworld'],Fetch(),service)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0][1],'second');self.assertEqual(calls,[new['address']])
        self.assertEqual(stats['remaining_parents'],0);self.assertTrue(stats['complete_query'])

    def test_policy_appendix_row_count_sum_and_outside_region_filter(self):
        from backend.policy_attachments import parse_policy129_table
        lines=['사업 리스트(34개소, 9,894호)']
        for i in range(1,35):
            region='인천' if i>32 else '서울' if i<=20 else '경기'
            city='서구' if i>32 else '강남' if i<=20 else '수원'
            units=9861 if i==1 else 1
            lines.append(f'{i} {region} {city} 사업{i} {units} 국유지 ‘27.06 SH')
        rows=parse_policy129_table('\n'.join(lines));self.assertEqual(len(rows),32)
        self.assertTrue(all(r[2]['region']!='인천' for r in rows))
        self.assertEqual(rows[0][2]['start_plan_month'],'2027-06');self.assertNotIn('completion_plan_date',rows[0][2])
        with self.assertRaises(ValueError):parse_policy129_table('\n'.join(lines[:-1]))
        with self.assertRaises(ValueError):parse_policy129_table('\n'.join(lines).replace('9861','1'))

    def test_policy_start_is_separate_from_supply_and_completion(self):
        from backend.roadmap import source_events
        from datetime import date
        row=dict(source_id='policy_129',planned_units=712,start_plan_month='2027-06',evidence_url='https://example.com')
        events=source_events(row,date(2026,10,3))
        self.assertEqual(len(events),1);self.assertEqual(events[0]['stage'],'CONSTRUCTION')
        self.assertEqual(events[0]['units'],712)
