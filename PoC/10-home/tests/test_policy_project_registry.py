import unittest
from datetime import date
from sqlalchemy import create_engine, select, func
from backend.db import Base, Revision, Mapping, ProgramMapping, upsert_revision
from backend.service import HomeService
from backend.policy_project_registry import registry_records, supplement_records, register_reviewed_sites, POLICY_ID
from tests.test_policy_delivery import FakeService
from backend.policy_delivery import build_delivery

class RegistryTests(unittest.TestCase):
    def test_named_sites_do_not_create_actuals_or_raise_policy_target(self):
        service=FakeService()
        before=build_delivery(service,date(2026,10,13))
        for sid in ('policy_907','policy_129'):
            for _,key,p in registry_records(sid):
                service.project_rows.append(dict(p,id=sid+key,source_id=sid,mapping={'status':'REVIEW','policy_id':POLICY_ID}))
        after=build_delivery(service,date(2026,10,13))
        self.assertEqual(len(service.project_rows)-2,16)
        self.assertEqual(sum(p['planned_units'] is None for p in service.project_rows[2:]),3)
        suseo=next(p for p in service.project_rows if p['name']=='수서 노후 임대 재건축')
        self.assertEqual((suseo['existing_stock_units'],suseo['planned_units'],suseo['net_additional_units']),(2565,3899,1334))
        self.assertEqual(suseo['address'],'서울특별시 강남구 수서동 707')
        self.assertEqual(suseo['quantity_status'],'OFFICIAL_ESTIMATE')
        self.assertTrue(all(s['total_units']==1350000 for s in after['snapshots']))
        for stage in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'):
            self.assertEqual(before['current']['totals'][stage],after['current']['totals'][stage])

    def test_recollection_preserves_a_newer_parsed_source_record(self):
        base=registry_records('policy_907')
        newer=dict(base[0][2],planned_units=18000,base_date='2026-10-13')
        merged=supplement_records('policy_907',[(base[0][0],base[0][1],newer)])
        self.assertEqual(len(merged),13)
        self.assertEqual(merged[0][2]['planned_units'],18000)
        self.assertEqual(supplement_records('policy_907',merged),merged)

    def test_registration_is_atomic_idempotent_and_preserves_staff_review(self):
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        service=HomeService(engine,'/tmp/policy-registry-test')
        service.mapping_policies=lambda: [dict(policy_id=POLICY_ID,monitor_kind='POLICY',evidence_url='https://www.molit.go.kr/')]
        dry=register_reviewed_sites(service)
        self.assertEqual(len(dry['added']),16)
        with service.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),0)
        applied=register_reviewed_sites(service,True)
        with service.sessions.begin() as db:
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==applied['added'][0]['id']))
            mapping.status='RELEASED';mapping.basis='담당자 제외';mapping.revision_no=2
        again=register_reviewed_sites(service,True)
        self.assertEqual(len(again['added']),0)
        self.assertEqual(len(again['existing']),16)
        with service.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),16)
            m=db.scalar(select(Mapping).where(Mapping.project_id==applied['added'][0]['id']))
            self.assertEqual((m.status,m.basis,m.revision_no),('RELEASED','담당자 제외',2))
            self.assertTrue(all(p.policy_id==POLICY_ID for p in db.scalars(select(ProgramMapping))))

    def test_existing_same_name_aborts_without_partial_inserts(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        service=HomeService(engine,'/tmp/policy-registry-test')
        service.mapping_policies=lambda: [dict(policy_id=POLICY_ID,monitor_kind='POLICY')]
        p=registry_records('policy_907')[-1][2]
        with service.sessions.begin() as db:upsert_revision(db,'project','other-source',p['name'],p,'fixture')
        with self.assertRaisesRegex(ValueError,'중복'):register_reviewed_sites(service,True)
        with service.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Revision)),1)
