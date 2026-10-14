import json
import unittest

from backend.building_context import parse_buildings


def document(features, total=None):
    return json.dumps({'response':{'status':'OK','record':{'total':len(features) if total is None else total},
                                   'result':{'featureCollection':{'features':features}}}}).encode()


def feature(fid, height, floors):
    return {'id':fid,'geometry':{'type':'Polygon','coordinates':[[[127,37],[127.001,37],[127,37.001],[127,37]]]},
            'properties':{'height':height,'grnd_flr':floors,'bld_nm':'공식 건물'}}


class BuildingContextTests(unittest.TestCase):
    def test_only_official_positive_height_extrudes_and_no_block_link_is_inferred(self):
        features,total=parse_buildings(document([feature('A','25.5','8'),feature('B','0','12'),feature('C','-1',None)]))
        self.assertEqual(total,3)
        self.assertEqual([row['properties']['height_m'] for row in features],[25.5,None,None])
        self.assertEqual(features[0]['properties']['floors'],8)
        self.assertEqual([row['properties']['render_height_m'] for row in features],[25.5,36.0,7.5])
        self.assertEqual([row['properties']['height_basis'] for row in features],['OFFICIAL_HEIGHT','FLOOR_ESTIMATE','VISUAL_ONLY'])
        self.assertTrue(all(row['properties']['block_link_status']=='UNLINKED' for row in features))

    def test_pagination_or_duplicate_source_ids_fail_closed(self):
        with self.assertRaises(ValueError):parse_buildings(document([feature('A',10,3)],2))
        with self.assertRaises(ValueError):parse_buildings(document([feature('A',10,3),feature('A',11,4)]))

    def test_pages_preserve_total_and_last_page_length(self):
        from unittest.mock import patch
        with patch('backend.building_context.PAGE_SIZE',2):
            page1,total=parse_buildings(document([feature('A',10,3),feature('B',None,4)],3),1)
            page2,last_total=parse_buildings(document([feature('C',None,None)],3),2)
            self.assertEqual((len(page1),len(page2),total,last_total),(2,1,3,3))
            with self.assertRaises(ValueError):parse_buildings(document([feature('C',None,None)],3),1)

    def test_representative_anchor_loads_buildings_and_cache_tracks_coordinates(self):
        from unittest.mock import patch, Mock
        from pathlib import Path
        from backend.building_context import BuildingContext
        service=Mock(data_dir=Path('/tmp'))
        service.rows.return_value=[]
        anchor=dict(latitude=37.48, longitude=127.1, coordinate_basis='APPROXIMATE_ADDRESS', label='대표 지번 근사 위치')
        with patch('backend.building_context.Fetcher') as factory, patch('backend.building_context.key_for', return_value='test'):
            fetcher=factory.return_value
            fetcher.get.return_value=document([feature('A',25,8)])
            fetcher.manifest=[]
            context=BuildingContext()
            result=context.get('PROJECT', service, anchor)
            self.assertEqual(result['feature_count'],1)
            self.assertEqual(result['location_basis'],'APPROXIMATE_ADDRESS')
            self.assertEqual(result['origin']['longitude'],127.1)
            self.assertEqual(result['search_radius_metres'],1000)
            self.assertEqual(context.get('PROJECT', service, anchor),result)
            self.assertEqual(fetcher.get.call_count,1)
            moved=context.get('PROJECT', service, dict(anchor, longitude=127.2))
            self.assertEqual(moved['longitude'],127.2)
            self.assertEqual(fetcher.get.call_count,2)

    def test_zero_building_response(self):
        self.assertEqual(parse_buildings(json.dumps({'response':{'status':'NOT_FOUND'}}).encode()),([],0))
