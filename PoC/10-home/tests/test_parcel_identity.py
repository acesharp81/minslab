import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base, upsert_revision
from backend.service import HomeService
from backend.parcel_identity import compose, enrich_source, reconcile, selected_permits

class ParcelTests(unittest.TestCase):
    def test_structure_land_conversion_and_invalid_inputs(self):
        row=dict(sigungu_code='41610',bjdong_code='11200',plat_gb_cd='0',bun='417',ji='2')
        self.assertEqual(compose(row),('4161011200104170002','CANDIDATE'))
        self.assertEqual(compose(dict(row,plat_gb_cd=1,ji=0))[0],'4161011200204170000')
        for patch_,reason in [({'plat_gb_cd':'2'},'BLOCK_ADDRESS'),({'plat_gb_cd':None},'LAND_TYPE_MISSING'),
                              ({'bun':'0000'},'LOT_INVALID'),({'ji':None},'LOT_MISSING'),({'bun':'10000'},'LOT_INVALID'),
                              ({'bun':'1.0'},'LOT_INVALID'),({'bjdong_code':'12'},'LEGAL_CODE_INVALID')]:
            self.assertEqual(compose(dict(row,**patch_)),(None,reason))
        enrich_source(row,{'platGbCd':0});self.assertEqual(row['pnu'],'4161011200104170002')

    def test_persistent_multiple_parcels_and_released_permit(self):
        engine=create_engine('sqlite://',poolclass=StaticPool);Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose);s=HomeService(engine)
        project=dict(id='p1',name='검증 사업',region='경기도',base_date='2026-10-13')
        with s.sessions.begin() as db:
            permit,_=upsert_revision(db,'permit','building_hub','pk',dict(source_object_id='pk',sigungu_code='41610',bjdong_code='11200',plat_gb_cd='2',bun='0000',ji='0000'),'test')
            eid=permit.entity_id
            upsert_revision(db,'stage_evidence','auto','s',dict(base_date='2026-10-13',project_id='p1',status='REVIEW',selected=dict(source_entity_id=eid,source_revision_no=1)),'test')
            upsert_revision(db,'legal_dong','legal_dongs','4161011200',dict(base_date='2026-10-13',source_object_id='4161011200'),'test')
            for num in [1,2]:
                upsert_revision(db,'permit_parcel','building_hub_details',str(num),dict(parent_permit_native_id='pk',sigungu_code='41610',bjdong_code='11200',plat_gb_cd='0',bun=str(num),ji='0000'),'test')
        with patch.object(s,'projects',return_value=[project]):
            first=reconcile(s);self.assertEqual(first['states'],{'CANDIDATE':1})
            self.assertEqual(len(s.rows('project_parcel')[0]['pnus']),2)
            self.assertEqual(reconcile(s)['revisions'],{'unchanged':1})
            with s.sessions.begin() as db:
                upsert_revision(db,'stage_evidence','auto','s',dict(base_date='2026-10-13',project_id='p1',status='RELEASED',selected=dict(source_entity_id=eid,source_revision_no=1)),'test')
            self.assertFalse(selected_permits(s));reconcile(s)
            self.assertEqual(s.rows('project_parcel')[0]['pnus'],[])
            self.assertIn('PERMIT_LINK_MISSING',s.rows('project_parcel')[0]['missing_reasons'])

    def test_detail_priority_uses_selected_permit_dong_including_incheon(self):
        from backend.building_details import next_detail_dongs
        class Service:
            sessions=True
            def rows(self,kind):
                return ([dict(source_object_id='1111010100',address='서울특별시 종로구 청운동')]
                        if kind=='legal_dong' else [dict(source_object_id='2824510100',address='인천광역시 계양구 효성동')])
            def latest_collection_stats(self,_):return {}
            def projects(self):return [dict(address='서울특별시 종로구 청운동')]
        with patch('backend.parcel_identity.target_dongs',return_value={'2824510100'}):
            selected,_,_=next_detail_dongs(Service())
        self.assertEqual(selected,('2824510100','1111010100'))
