import unittest
from backend.supply_type import assess, source_fields


class SupplyTypeTests(unittest.TestCase):
    def project(self, **values):
        return dict(name='검증 사업', evidence_url='https://www.lh.or.kr/example', **values)

    def test_general_permit_and_agency_name_do_not_prove_private_or_public_type(self):
        p=self.project(source_id='building_general_permit', developer='LH')
        self.assertEqual(assess(p)['code'],'UNKNOWN')
        self.assertEqual(assess(p)['candidate_code'],'OTHER_PRIVATE')
        self.assertEqual(assess(self.project(developer='LH',program='공공주택 후보'))['status'],'UNRESOLVED')

    def test_subtenure_unknown_still_identifies_broad_public_type(self):
        self.assertEqual(assess(self.project(tenure='공공주택 · 세부유형 확인 필요'))['code'],'PUBLIC')

    def test_renewal_allocation_needs_proof_but_separate_public_cohort_is_known(self):
        p=self.project(source_id='sh_inventory',program='공공재개발')
        self.assertEqual(assess(p)['code'],'UNKNOWN')
        self.assertEqual(assess(p)['candidate_code'],'PRIVATE_RENEWAL')
        p.update(tenure='통합공공임대')
        self.assertEqual(assess(p)['code'],'PUBLIC')
        p.update(program='건설형 공공임대',name='강서염창(가로주택) 01')
        self.assertEqual(assess(p)['code'],'PUBLIC')

    def test_explicit_types_are_distinguished_from_existing_purchase_and_generic_rental(self):
        self.assertEqual(assess(self.project(tenure='공공지원 민간임대'))['code'],'PUBLIC_SUPPORTED_RENT')
        self.assertEqual(assess(self.project(tenure='신축매입임대'))['code'],'PURCHASE_NEW')
        self.assertEqual(assess(self.project(tenure='기존주택 매입임대'))['code'],'UNKNOWN')
        self.assertEqual(assess(self.project(tenure='민간임대'))['code'],'UNKNOWN')
        self.assertEqual(assess(self.project(tenure='공공분양·민영주택 혼합'))['code'],'MIXED')

    def test_manual_type_requires_basis_url_and_can_explicitly_hold(self):
        p=self.project(source_id='lh_construction',developer='LH',supply_type='OTHER_PRIVATE',
                       supply_type_basis='담당자가 공급방식 확인',supply_type_evidence_url='https://example.org/notice',
                       manual_fields={'supply_type':{'value':'OTHER_PRIVATE','reason':'확인'}})
        self.assertEqual(assess(p)['code'],'OTHER_PRIVATE')
        self.assertEqual(source_fields(p)['supply_type'],'PUBLIC')
        p['supply_type_evidence_url']='javascript:alert(1)'
        self.assertEqual(assess(p)['code'],'UNKNOWN')
        p.update(supply_type='UNKNOWN')
        self.assertEqual(assess(p)['status'],'UNRESOLVED')

    def test_missing_source_url_never_confirms(self):
        p=self.project(tenure='공공분양');p['evidence_url']=''
        self.assertEqual(assess(p)['status'],'UNRESOLVED')

