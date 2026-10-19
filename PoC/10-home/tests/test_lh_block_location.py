import json
import unittest
from datetime import date

from backend.lh_block_location import parse_label_points
from backend.supply_dashboard import build_dashboard
from test_supply_dashboard import project


def page(rows):
    return 'var HOUSEPLAN_LABEL_INFO = ' + repr(json.dumps({'housePlanLabelInfo': rows}, ensure_ascii=False)) + ';'


class LHBlockLocationTests(unittest.TestCase):
    def test_incheon_labels_are_collected_once_across_tenures(self):
        row={'flag':4,'sggCd':'28','bzdtNm':'인천계양','bnm':'A-16',
             'x':178121.98,'y':449231.47,'zonecode':'28245MX2019001'}
        points,stats=parse_label_points(page([row,dict(row,supplyTp='공공분양'),
            dict(row,sggCd='30',bzdtNm='대전'),dict(row,flag=2)]))
        self.assertEqual(list(points),[('인천광역시','인천계양','A16')])
        self.assertEqual(stats['source_label_rows'],2)
        self.assertEqual(stats['unique_blocks'],1)

    def test_exact_block_label_points_exclude_other_flags_and_conflicting_positions(self):
        base={'flag':4,'sggCd':'41','bzdtNm':'고양창릉지구','bnm':'A-01','x':186010.742,'y':435363.571,'zonecode':'Z'}
        changed=dict(base,x=186200,bnm='S1')
        conflict=dict(changed,x=189000)
        points,stats=parse_label_points(page([base,dict(base),changed,conflict,dict(base,flag=2)]))
        self.assertEqual(list(points),[('경기도','고양창릉','A1')])
        self.assertEqual(stats['ambiguous_blocks'],1)
        self.assertEqual(stats['source_label_rows'],4)

    def test_location_changes_coordinates_without_changing_supply_totals(self):
        row=project()
        before=build_dashboard([row],[],[],[],[],[],[],date(2026,10,3),2018)
        location={'region':'경기도','district_key':'고양창릉','block':'A1','latitude':37.42,
                  'longitude':126.84,'coordinate_basis':'LH_PUBLIC_BLOCK_LABEL_POINT',
                  'evidence_url':'https://bizmap.lh.or.kr/lhmap.do'}
        after=build_dashboard([row],[],[],[],[],[],[],date(2026,10,3),2018,block_locations=[location])
        self.assertEqual(after['blocks'][0]['coordinate_basis'],'LH_PUBLIC_BLOCK_LABEL_POINT')
        self.assertEqual(after['blocks'][0]['latitude'],37.42)
        self.assertEqual(after['summary']['target_units'],before['summary']['target_units'])
        self.assertEqual(after['blocks'][0]['target_units'],before['blocks'][0]['target_units'])
        self.assertIsNone(after['summary']['current_units'])

    def test_page_schema_change_raises(self):
        with self.assertRaises(ValueError):
            parse_label_points('no labels')
