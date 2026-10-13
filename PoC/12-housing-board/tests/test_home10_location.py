"""Guard the block names used when PoC 10 candidates are placed on the PoC 12 map."""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'import-home10.py'
spec = importlib.util.spec_from_file_location('import_home10', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Home10LocationTests(unittest.TestCase):
    def test_block_spelling_and_district_suffix(self):
        expected = ('경기도', '고양창릉', 's1')
        self.assertEqual(module.location_key('경기도', '고양창릉', 'S-01'), expected)
        self.assertEqual(module.location_key('경기도', '고양창릉 공공주택지구', 'S1'), expected)
        self.assertEqual(module.location_key('경기도', '평택고덕국제화계획', 'Ab-037'),
                         ('경기도', '평택고덕', 'ab37'))
        self.assertNotEqual(module.location_key('경기도', '구리갈매', 'A1'),
                            module.location_key('경기도', '구리갈매역세권', 'A1'))

    def test_multiblock_plan_is_not_assigned_to_one_point(self):
        single = {'source_id': 'lh_sale', 'name': '고양창릉 S-01'}
        self.assertEqual(module.project_site(single), ('고양창릉', 'S-01', 'LH_PLAN_NAME_SINGLE_BLOCK'))
        combined = {'source_id': 'lh_sale', 'name': '안산신길2 A1,A3'}
        self.assertEqual(module.project_site(combined), (None, None, None))
        self.assertIsNone(module.location_key('경기도', '안산신길2', 'A1,A3'))


if __name__ == '__main__':
    unittest.main()
