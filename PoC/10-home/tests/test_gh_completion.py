import io
import unittest

from pypdf import PdfWriter

from backend.gh_completion import collect_gh_completion, evidence_type, parse_list
from backend.sources import SOURCES

SOURCE = next(s for s in SOURCES if s['id'] == 'gh_completion_evidence')


def listing(page='1/1', count=2):
    return f'''<div>총게시물 : {count} 페이지 : {page}</div><table><tbody>
    <tr><td>1</td><td>남양주시</td><td>공공임대</td><td><a data-sn="88">다산역자연앤푸르지오 사용검사 확인증</a></td><td>GH</td><td>pdf</td><td>2024-02-23</td><td>1</td></tr>
    <tr><td>2</td><td>평택시</td><td>행복주택</td><td><a data-sn="50">평택BIX 임시사용승인서</a></td><td>GH</td><td>pdf</td><td>2021-05-03</td><td>1</td></tr>
    </tbody></table>'''.encode()


class GHCompletionTests(unittest.TestCase):
    def test_evidence_classification_does_not_treat_provisional_as_completion(self):
        self.assertEqual(evidence_type('사용검사 확인증'), 'USE_APPROVAL_CANDIDATE')
        self.assertEqual(evidence_type('준공인가전 사용허가(연장)'), 'PROVISIONAL_EXTENSION')
        self.assertEqual(evidence_type('임시사용승인서'), 'PROVISIONAL')
        self.assertIsNone(evidence_type('입주자 사전방문 안내'))

    def test_collection_preserves_pdf_but_no_units_or_project_actuals(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buffer = io.BytesIO()
        writer.write(buffer)
        pdf = buffer.getvalue()
        class Fetch:
            def get(self, url, suffix='html'):
                if suffix == 'pdf': return pdf
                if 'DetailView' in url:
                    return b'<a href="/cs/sr/sr7900/selectFileDown.do?atchFileSn=1">x</a>'
                return listing()
        rows, stats = collect_gh_completion(SOURCE, Fetch())
        self.assertEqual(stats['collected'], 2)
        self.assertEqual(stats['provisional_count'], 1)
        self.assertEqual(rows[0][2]['project_link_status'], 'REVIEW')
        self.assertIsNone(rows[0][2]['actual_occupied_units'])
        self.assertIsNone(rows[0][2]['approval_date'])
        self.assertIsNone(rows[1][2]['units'])
        self.assertIn('PROVISIONAL_NOT_FINAL_COMPLETION', rows[1][2]['warnings'])

    def test_changed_list_population_fails_instead_of_silent_partial_collection(self):
        with self.assertRaisesRegex(ValueError, '건수'):
            parse_list(listing(count=3), SOURCE)
        with self.assertRaisesRegex(ValueError, '페이지'):
            parse_list(listing(page='1/2'), SOURCE)
