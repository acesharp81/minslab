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

class GHPaginationTests(unittest.TestCase):
    def pages(self,page,duplicate=False):
        ids=list(range(10)) if page==1 else ([0,11] if duplicate else [10,11])
        row=lambda i: f'<tr><td>{i}</td><td>평택시</td><td>임대</td><td><a data-sn="{i}">입주 안내</a></td><td>GH</td><td></td><td>2026-11-04</td><td>1</td></tr>'
        return ('<div>총게시물 : 12 페이지 : '+str(page)+'/2</div><table>'+''.join(row(i) for i in ids)+'</table>').encode()

    def test_two_pages_are_read_and_counted_before_evidence_filter(self):
        from unittest.mock import patch
        owner=self
        class Fetch:
            def get(self,url,suffix='html',params=None):return owner.pages((params or {}).get('pageIndex',1))
        # No matching evidence is an error, but only after both pages are validated.
        with patch('backend.gh_completion.parse_list', wraps=parse_list) as parser:
            with self.assertRaisesRegex(ValueError,'자료 미확인'):collect_gh_completion(SOURCE,Fetch())
            self.assertEqual(parser.call_count,2)
            self.assertEqual(parser.call_args.kwargs['page'],2)

    def test_repeated_page_or_cross_page_duplicate_never_succeeds(self):
        owner=self
        class Fetch:
            def get(self,url,suffix='html',params=None):return owner.pages((params or {}).get('pageIndex',1),duplicate=True)
        with self.assertRaisesRegex(ValueError,'중복'):collect_gh_completion(SOURCE,Fetch())
        with self.assertRaisesRegex(ValueError,'페이지'):
            parse_list(self.pages(1),SOURCE,page=2,total=12,pages=2)
        with self.assertRaisesRegex(ValueError,'총건수'):
            parse_list(self.pages(2),SOURCE,page=2,total=13,pages=2)
