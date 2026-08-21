from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.connection import psycopg_dsn


class ConnectionTests(unittest.TestCase):
    def test_sqlalchemy_style_psycopg_url_is_accepted(self):
        self.assertEqual(
            psycopg_dsn("postgresql+psycopg://user:pass@db/name"),
            "postgresql://user:pass@db/name",
        )

    def test_standard_url_is_unchanged(self):
        url = "postgresql://user:pass@db/name"
        self.assertEqual(psycopg_dsn(url), url)


if __name__ == "__main__":
    unittest.main()
