"""Run existing shared-service tests against the proposed main.py in memory."""
import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
candidate = types.ModuleType("main")
candidate.__file__ = str(ROOT / "main.py")
sys.modules["main"] = candidate
exec(compile(Path(sys.argv[1]).read_bytes(), candidate.__file__, "exec"), candidate.__dict__)

import portfolio_loader

with tempfile.TemporaryDirectory(prefix="poc-menu-check-") as temporary:
    for path in (ROOT / "PoC").iterdir():
        if path.is_dir() and path.name not in {"11-consultation-cases", "12-housing-board"}:
            (Path(temporary) / path.name).symlink_to(path, target_is_directory=True)
    with mock.patch.object(portfolio_loader, "POC_DIR", Path(temporary)):
        projects = portfolio_loader.load_poc_projects()
        assert {item["id"] for item in projects}.isdisjoint({"consultation-cases", "housing-board"})
        assert len(projects) == len(list((ROOT / "PoC").glob("*/project.json"))) - 2
        result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
        if not result.wasSuccessful():
            sys.exit(1)

        from test_site_api import call_app

        async def verify_retired_runtime():
            for path in ("/home2", "/home2/", "/counsel", "/counsel/", "/poc/housing-board",
                         "/poc/housing-board/map", "/poc/consultation-cases/",
                         "/poc/consultation-cases/api/status"):
                with mock.patch.object(candidate, "load_module_from_path", side_effect=AssertionError("Unexpected PoC import")):
                    start, body = await call_app(path)
                assert start["status"] == 200, (path, start["status"])
                assert b"location" not in dict(start["headers"]), path
                assert body == candidate.build_html().encode(), path
            messages = iter(({"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}))
            sent = []

            async def receive():
                return next(messages)

            async def send(message):
                sent.append(message["type"])

            with mock.patch.object(candidate, "analytics_status"), \
                 mock.patch.object(candidate, "purge_old_analytics_events"), \
                 mock.patch.object(candidate, "capture_system_metrics"), \
                 mock.patch.object(candidate, "master_press_is_paused", return_value=True), \
                 mock.patch.object(candidate, "load_module_from_path", side_effect=AssertionError("Unexpected PoC import")):
                await candidate.app({"type": "lifespan"}, receive, send)
            assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"], sent

        asyncio.run(verify_retired_runtime())
print("62 existing tests, retired-route checks, menu isolation and ASGI lifespan passed.")
