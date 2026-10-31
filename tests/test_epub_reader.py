"""PoC 12 public routes and catalog integration."""
import unittest
from test_site_api import call_app
import portfolio_loader


class EpubReaderRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_reader_shortcut_and_canonical_redirects(self):
        for path in ['/epub', '/epub/', '/poc/epub-reader']:
            start, body = await call_app(path)
            self.assertEqual(start['status'], 307)
            self.assertEqual(dict(start['headers'])[b'location'], b'/poc/epub-reader/')
            self.assertEqual(body, b'')

    async def test_reader_and_assets_get_head(self):
        for path, mime in [('/poc/epub-reader/', b'text/html'),
                           ('/poc/epub-reader/app.js', b'text/javascript'),
                           ('/poc/epub-reader/epub.js', b'text/javascript'),
                           ('/poc/epub-reader/storage.js', b'text/javascript'),
                           ('/poc/epub-reader/pagination.js', b'text/javascript'),
                           ('/poc/epub-reader/pdf.js', b'text/javascript'),
                           ('/poc/epub-reader/vendor/pdfjs/legacy/build/pdf.min.mjs', b'text/javascript'),
                           ('/poc/epub-reader/vendor/pdfjs/legacy/build/pdf.worker.min.mjs', b'text/javascript'),
                           ('/poc/epub-reader/styles.css', b'text/css'),
                           ('/poc/epub-reader/vendor/jszip.min.js', b'text/javascript'),
                           ('/poc/epub-reader/vendor/purify.min.js', b'text/javascript')]:
            with self.subTest(path=path):
                start, body = await call_app(path)
                self.assertEqual(start['status'], 200)
                headers = dict(start['headers'])
                self.assertTrue(headers[b'content-type'].startswith(mime))
                self.assertEqual(int(headers[b'content-length']), len(body))
                self.assertEqual(headers[b'x-content-type-options'], b'nosniff')
                head, empty = await call_app(path, 'HEAD')
                self.assertEqual(head['status'], 200)
                self.assertEqual(dict(head['headers'])[b'content-length'], headers[b'content-length'])
                self.assertEqual(empty, b'')

    async def test_reader_rejects_traversal_missing_files_and_writes(self):
        for path in ['/poc/epub-reader/../project.json', '/poc/epub-reader/../../../.env', '/poc/epub-reader/missing.js']:
            start, _ = await call_app(path)
            self.assertEqual(start['status'], 404)
        for method in ['POST', 'PUT', 'DELETE']:
            start, _ = await call_app('/poc/epub-reader/', method)
            self.assertEqual(start['status'], 405)

    async def test_reader_catalog_registration(self):
        item = next(p for p in portfolio_loader.load_projects() if p['id'] == 'epub-reader')
        self.assertEqual(item['no'], '12')
        self.assertEqual(item['app_path'], '/poc/epub-reader/')
        self.assertEqual(item['menu_group'], 'portfolio')
        self.assertFalse(any(p['id'] == 'epub-reader' for p in portfolio_loader.load_poc_projects()))
