import unittest

from backend.policy_geo import geometry_view, metrics_view, schematic_view


def quantity(**overrides):
    row = dict(target_units=100, project_count=1, project_ids=['P'], target_missing_projects=0,
               current_notice_units=40, current_notice_status='REVIEW',
               progress=dict(actual_delivery_units=None, cumulative_goal_units=50, late_count=0,
                             verification_count=1),
               future=[dict(end_year=2027, source_units=60, manual_units=None, units_missing_events=0)],
               chart_schedule_ids=['P'])
    return dict(row, **overrides)


def dashboard():
    polygon={'type':'Polygon','coordinates':[[[127,37],[127.1,37],[127.1,37.1],[127,37]]]}
    group=dict(id='POL',name='정책',**quantity())
    regional=dict(id='서울특별시',name='서울특별시',group_quantities={'policy':{'POL':quantity()}},**quantity())
    municipal=dict(id='M1',name='중구',region='서울특별시',geometry={'type':'GeometryCollection',
        'geometries':[{'type':'LineString','coordinates':[[127,37],[127.1,37]]},polygon]},
        longitude=127.05,latitude=37.05,group_quantities={'policy':{'POL':quantity()}},**quantity())
    district=dict(id='D1',name='용지',regions=['서울특별시'],geometry=polygon,source_layer='LT_C_LHBLPN',
        longitude=127.05,latitude=37.05,project_ids=['P'],group_quantities={'policy':{'POL':quantity()}},
        quantities=quantity())
    block=dict(id='B1',name='A1',block='A1',district_name='용지',region='서울특별시',
        coordinate_basis='LH_PUBLIC_BLOCK_LABEL_POINT',longitude=127.05,latitude=37.05,
        group_quantities={'policy':{'POL':quantity()}},**quantity())
    project=dict(id='P',name='사업',region='서울특별시',program='프로그램',planned_units=100,
        stage_label='계획',mapping={'status':'REVIEW','policy_id':'POL'},
        annual=[dict(year=2027,events=[dict(origin='SOURCE',stage='SUPPLY',units=60)])],
        notice_evidence=dict(id='N1',units=40,source_date='2026-06-01'))
    return dict(knowledge_date='2026-10-10',analysis_year=2026,reference_date='2026-10-10',
        start_year=2018,measure='SUPPLY',measure_label='모집·공급',notice='실입주 미확보',
        groups={'policy':[group],'program':[dict(group,id='프로그램',name='프로그램')],
                'region':[regional]},municipalities=[municipal],districts=[district],blocks=[block],items=[project])


class PolicyGeoReadModelTests(unittest.TestCase):
    def test_geometry_keeps_official_admin_and_land_roles_separate(self):
        data=geometry_view(dashboard())
        self.assertEqual(len(data['municipalities']['features']),1)
        self.assertEqual(data['municipalities']['features'][0]['geometry']['type'],'MultiPolygon')
        self.assertEqual(data['housing_lands']['features'][0]['properties']['geometry_role'],'OFFICIAL_HOUSING_LAND')
        self.assertEqual(data['block_anchors'][0]['geometry_role'],'LH_PUBLIC_BLOCK_LABEL_POINT')
        self.assertEqual(data['out_of_scope'],[])
        self.assertIn('인천광역시',data['scope'])

    def test_schematic_uses_only_official_municipal_outline(self):
        data=schematic_view(dashboard())
        self.assertEqual(data['type'],'PolicySchematic')
        self.assertEqual(len(data['shapes']),1)
        self.assertEqual(data['shapes'][0]['id'],'M1')
        self.assertEqual(data['shapes'][0]['rings'][0][0],[127,37])
        self.assertNotIn('housing_lands',data)
        self.assertNotIn('block_anchors',data)

    def test_series_separates_review_notice_from_plan_and_actual_delivery(self):
        data=metrics_view(dashboard())
        policy=data['groups']['policy'][0]
        self.assertEqual(policy['annual_series'],[{'year':2026,'notice_units':40},
                                                  {'year':2027,'SUPPLY':60}])
        self.assertIsNone(policy['actual_delivery_units'])
        self.assertIn('chart_target_ids',policy)
        self.assertEqual(data['municipalities'][0]['by_scope']['policy']['POL']['target_units'],100)
        self.assertEqual(data['items'][0]['current_notice_units'],40)

    def test_metrics_exposes_source_months_including_earlier_schedule(self):
        data = dashboard()
        data['items'][0]['earlier_events'] = [dict(origin='SOURCE', stage='SUPPLY',
            month='2025-12', year=2025, units=20, basis='원천 공급 예정')]
        data['items'][0]['annual'][0]['events'][0]['month'] = '2027-08'
        result = metrics_view(data)
        events = result['items'][0]['schedule_events']
        self.assertEqual([(row['month'], row['units']) for row in events],
                         [('2025-12', 20), ('2027-08', 60)])
        self.assertEqual(result['groups']['policy'][0]['annual_series'][0],
                         {'year': 2025, 'SUPPLY': 20})

    def test_same_name_programmes_keep_distinct_policy_links(self):
        data=dashboard()
        first=data['items'][0]
        first['mapping'].update(program_id='PRG_ONE',program_name='공공주택 건설')
        second={**first,'id':'P2','planned_units':250,
                'mapping':{**first['mapping'],'program_id':'PRG_TWO','policy_id':'POL_2'},
                'notice_evidence':{'id':'N2','units':80,'source_date':'2026-08-01'}}
        data['items'].append(second)
        data['groups']['region'][0]['project_ids']=['P','P2']
        data['groups']['region'][0]['chart_target_ids']=['P','P2']
        data['groups']['region'][0]['chart_schedule_ids']=['P','P2']
        links=metrics_view(data)['groups']['program_link']
        self.assertEqual({row['id'] for row in links},{'PRG_ONE','PRG_TWO'})
        self.assertEqual({row['id']:row['target_units'] for row in links},{'PRG_ONE':100,'PRG_TWO':250})
        self.assertEqual({row['id']:row['current_notice_units'] for row in links},{'PRG_ONE':40,'PRG_TWO':80})
        self.assertTrue(all(row['actual_delivery_units'] is None for row in links))


if __name__ == '__main__':
    unittest.main()
