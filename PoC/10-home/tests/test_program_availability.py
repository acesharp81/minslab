import unittest
from sqlalchemy import create_engine
from backend.db import Base,ProgramMapping,upsert_revision
from backend.service import HomeService
from backend.program_availability import availability
from backend.api_samples import today

class ProgramAvailabilityTests(unittest.TestCase):
    def test_only_programs_without_both_data_types_are_disabled(self):
        self.assertFalse(availability(dict(active_project_count=0))['selection_enabled'])
        self.assertTrue(availability(dict(active_project_count=1))['selection_enabled'])
        for key,value in [('target_units',18000),('annual:전체:2027',500),('region:서울특별시',1000)]:
            self.assertFalse(availability(dict(profile={key:value},active_project_count=0))['selection_enabled'])
        self.assertTrue(availability(dict(active_project_count=0,linked_project_units=12))['selection_enabled'])
        for value in (None,0,True,-1,float('nan')):
            self.assertFalse(availability(dict(profile={'target_units':value},active_project_count=0))['selection_enabled'])

    def test_adding_data_reactivates_without_changing_mapping_or_source(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine)
        with service.sessions.begin() as db:
            db.add(ProgramMapping(id='PRG_EMPTY',name='이름만 있는 프로그램',seed_policy_id='POL_2025_0907',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
        row=service.program_links(projects=[])[0]
        self.assertFalse(row['selection_enabled']);self.assertEqual(row['status'],'REVIEW')
        with service.sessions.begin() as db:
            upsert_revision(db,'program_source','official','test',dict(program_id='PRG_EMPTY',base_date=today().isoformat(),fields=dict(target_units=1000)),'test')
        row=service.program_links(projects=[])[0]
        self.assertFalse(row['selection_enabled']);self.assertEqual(row['revision_no'],1)
        self.assertTrue(row['has_target_quantity'])
        row=service.program_links(projects=[dict(planned_units=None,mapping=dict(program_id='PRG_EMPTY',status='CONFIRMED'))])[0]
        self.assertTrue(row['selection_enabled']);self.assertEqual(row['revision_no'],1)
        self.assertEqual(row['policy_id'],'POL_2025_0907')

    def test_rejected_and_released_project_links_do_not_enable(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine)
        with service.sessions.begin() as db:
            db.add(ProgramMapping(id='PRG_EMPTY',name='이름만',seed_policy_id='POL_2025_0907',policy_id='POL_2025_0907',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
        projects=[dict(mapping=dict(program_id='PRG_EMPTY',status=status)) for status in ('RELEASED','REJECTED')]
        self.assertFalse(service.program_links(projects=projects)[0]['selection_enabled'])
        projects.append(dict(mapping=dict(program_id='PRG_EMPTY',status='REVIEW')))
        self.assertTrue(service.program_links(projects=projects)[0]['selection_enabled'])
