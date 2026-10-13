import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)
import build_docs_pdf

try:
    import markdown  # noqa: F401
    HAVE_MARKDOWN = True
except ImportError:
    HAVE_MARKDOWN = False

PDF_PATH_ARG = 'out = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--print-to-pdf=")][0]\n'


def fake_chrome(tmp, body):
    """인자를 받아 body를 실행하는 가짜 Chrome 실행 파일을 만든다."""
    path = Path(tmp) / "fake-chrome"
    path.write_text(f"#!{sys.executable}\nimport sys, time\n{PDF_PATH_ARG}{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def html_file(tmp):
    p = Path(tmp) / "a.html"
    p.write_text("<p>x</p>", encoding="utf-8")
    return p


class PrintHtmlToPdf(unittest.TestCase):
    def test_returns_once_the_pdf_is_complete_even_if_chrome_never_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, 'open(out, "wb").write(b"%PDF-1.4\\nfake\\n%%EOF\\n")\ntime.sleep(600)\n')
            pdf = Path(tmp) / "out.pdf"
            started = time.monotonic()
            build_docs_pdf.print_html_to_pdf(html_file(tmp), pdf, chrome=chrome, timeout=30)
            self.assertLess(time.monotonic() - started, 15)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

    def test_runtime_error_when_chrome_exits_without_a_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, "sys.exit(3)\n")
            with self.assertRaises(RuntimeError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), Path(tmp) / "out.pdf", chrome=chrome, timeout=30)

    def test_timeout_when_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            chrome = fake_chrome(tmp, "time.sleep(600)\n")
            with self.assertRaises(TimeoutError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), Path(tmp) / "out.pdf", chrome=chrome, timeout=2)

    def test_an_old_pdf_is_not_mistaken_for_the_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "out.pdf"
            pdf.write_bytes(b"%PDF-1.4\nold\n%%EOF\n")
            chrome = fake_chrome(tmp, "sys.exit(0)\n")  # 아무것도 쓰지 않고 정상 종료
            with self.assertRaises(RuntimeError):
                build_docs_pdf.print_html_to_pdf(html_file(tmp), pdf, chrome=chrome, timeout=30)


@unittest.skipUnless(HAVE_MARKDOWN, "markdown 패키지가 필요함 (.venv/bin/python 으로 실행)")
class RenderHtml(unittest.TestCase):
    def test_render_html_keeps_tables_headings_and_language(self):
        html = build_docs_pdf.render_html("# 제목\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", "정의서")
        self.assertIn("<table>", html)
        self.assertIn("<h1", html)
        self.assertIn('lang="ko"', html)
        self.assertIn("<title>정의서</title>", html)

    def test_the_real_definition_renders_all_tables(self):
        html = build_docs_pdf.render_html(build_docs_pdf.MD.read_text(encoding="utf-8"), "정의서")
        self.assertGreaterEqual(html.count("<table>"), 15)


class DocsList(unittest.TestCase):
    def test_both_definition_documents_are_built(self):
        names = {md.name: pdf.name for md, pdf in build_docs_pdf.DOCS}
        self.assertEqual(names, {"정의서.md": "정의서.pdf", "번들-어댑터-정의서.md": "번들-어댑터-정의서.pdf"})
        for md, _ in build_docs_pdf.DOCS:
            self.assertTrue(md.exists(), md)


if __name__ == "__main__":
    unittest.main()
