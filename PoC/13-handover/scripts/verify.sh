#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest tests -q
.venv/bin/python -m compileall -q app
if command -v node >/dev/null; then node --check app/web/app.js; node --check app/web/reader.js; node --check app/web/stream.js; node --check app/web/guide.js; node --check app/web/grouping.js; node --check app/web/tour.js; node --check app/web/walkthrough.js; fi
