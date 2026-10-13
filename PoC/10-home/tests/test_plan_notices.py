"""Official plan events require the page and PDF to agree with the fixed pilot."""
import unittest

from backend.plan_notices import collect_plan_notice
from backend.sources import SOURCES

SOURCE = next(s for s in SOURCES if s['id'] == 'seoul_plan_notice_pilot')


class FakeFetcher:
    def __init__(self, page):
        self.page = page
    def get(self, url, suffix='html'):
        if suffix == 'pdf':
            return b'%PDF-' + b'x' * 50000
        return self.page.encode()


class PlanNoticeTests(unittest.TestCase):
    def test_verified_page_and_pdf_make_no_supply_units(self):
        records, stats = collect_plan_notice(SOURCE, FakeFetcher(
            '<html><body>공덕1 제2020-418호 2020.10.22</body></html>'))
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0][2]['units'])
        self.assertEqual(records[0][2]['verification_status'], 'SOURCE_FILE_CAPTURED')
        self.assertEqual(len(records[0][2]['original_sha256']), 64)
        self.assertFalse(stats['complete_population'])

    def test_changed_page_blocks_capture(self):
        with self.assertRaisesRegex(ValueError, '게시 페이지'):
            collect_plan_notice(SOURCE, FakeFetcher('<html>공덕1</html>'))


if __name__ == '__main__':
    unittest.main()

