#!/usr/bin/env python3
"""입력 규격 검증기. 사용법: docs/data-interface/정의서.md 11절.

  python3 tools/validate_input.py <폴더 또는 ZIP> [--out 리포트폴더] [--today YYYY-MM-DD] [--strict]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datacheck.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
