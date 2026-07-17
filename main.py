import asyncio
import importlib.util
import json
import socket
import sys
import threading
import time
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from admin_auth import ADMIN_AUTH, SESSION_COOKIE
from admin_page import ADMIN_HTML
from analytics_store import analytics_status, get_analytics_summary, get_system_metric_history, increment_local_llm_calls, list_analytics_visits, purge_old_analytics_events, record_system_metrics, record_visit
from chunking_compare import DEFAULT_CHAT_MODEL, chunk_document, compare_legacy_tables, compare_tables, embed_plan, extract_hwpx_payload
from env_utils import env_first, load_project_env
from portfolio_loader import poc_projects_as_json, projects_as_json
from runtime_monitor import drain_http_window, observe_http_request
from supabase_store import is_configured as supabase_configured
from supabase_store import list_history, save_history
from system_metrics import read_system_usage


load_project_env()

APP_STARTED_AT = time.time()
APP_STARTED_MONOTONIC = time.monotonic()
SYSTEM_METRICS_INTERVAL_SECONDS = 60

STATIC_DIR = Path(__file__).parent / "static"
AI_SAFE_AGENT_PATH = Path(__file__).parent / "PoC" / "01-AISafeAgent" / "RiskInspection_v1.py"
AI_SAFE_IMPORT_PATH = Path(__file__).parent / "PoC" / "01-AISafeAgent" / "import.py"
REPORT_DRAFT_SERVICE_PATH = Path(__file__).parent / "projects" / "04-report-draft" / "portfolio_service.py"
MULTIAGENT_HARNESS_BASE_PATH = "/portfolio/multiagent-harness"
MULTIAGENT_HARNESS_API_BASE = "/api/portfolio/multiagent-harness"
MULTIAGENT_HARNESS_APP = Path(__file__).parent / "projects" / "03-multiagent-harness" / "app"
MULTIAGENT_HARNESS_SERVICE_PATH = Path(__file__).parent / "projects" / "03-multiagent-harness" / "service.py"
FIELD_INSPECTION_BASE_PATH = "/poc/field-inspection-platform"
FIELD_INSPECTION_DIST = Path(__file__).parent / "PoC" / "02-field-inspection-platform" / "dist"
MOIS_KMS_BASE_PATH = "/poc/mois-kms"
MOIS_KMS_API_BASE = "/api/poc/mois-kms"
MOIS_KMS_DIST = Path(__file__).parent / "PoC" / "03-mois-kms" / "dist"
MOIS_KMS_SERVICE_PATH = Path(__file__).parent / "PoC" / "03-mois-kms" / "backend.py"
MOIS_KMS_MODULE = None
MOIS_KMS_MTIME = None
REPORT_DRAFT_MODULE = None
REVERSE_GEOCODE_CACHE = {}
MASTER_PRESS_BASE_PATH = "/poc/master-press"
MASTER_PRESS_API_BASE = "/api/poc/master-press"
MASTER_PRESS_WEB = Path(__file__).parent / "PoC" / "04-master-press" / "web"
MASTER_PRESS_SERVICE_PATH = Path(__file__).parent / "PoC" / "04-master-press" / "backend.py"
MASTER_PRESS_MODULE = None
MASTER_PRESS_MTIME = None

NOMINATIM_LOCK = threading.Lock()
NOMINATIM_LAST_REQUEST = 0.0
REPORT_DRAFT_MTIME = None
MULTIAGENT_HARNESS_MODULE = None
MULTIAGENT_HARNESS_MTIME = None

AI_SAFE_BUILD_LOCK = threading.Lock()
AI_SAFE_AGENT_MODULE = None
AI_SAFE_AGENT_MTIME = None

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>MinsLab — 오늘의 기록으로 내일의 가능성을 실험하는 곳</title>
  <style>
    :root {
      color-scheme: light;
      --bg1: #f5f7ff;
      --bg2: #eaf3ff;
      --accent: #5b7cff;
      --accent-2: #35c5ff;
      --text: #14213d;
      --muted: #51607a;
      --card: rgba(255, 255, 255, 0.72);
      --border: rgba(255, 255, 255, 0.8);
      --shadow: 0 20px 45px rgba(91, 124, 255, 0.16);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, "Segoe UI", Roboto, sans-serif;
      color: var(--text);
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(53, 197, 255, 0.24), transparent 26%),
        radial-gradient(circle at bottom right, rgba(91, 124, 255, 0.2), transparent 20%),
        linear-gradient(135deg, var(--bg1), var(--bg2));
      overflow-x: hidden;
    }

    body::before, body::after {
      content: "";
      position: fixed;
      width: 22rem;
      height: 22rem;
      border-radius: 50%;
      filter: blur(70px);
      opacity: 0.3;
      pointer-events: none;
      animation: drift 12s ease-in-out infinite alternate;
    }

    body::before {
      top: -5rem;
      left: -3rem;
      background: var(--accent);
    }

    body::after {
      bottom: -5rem;
      right: -3rem;
      background: var(--accent-2);
      animation-duration: 10s;
    }

    @keyframes drift {
      from { transform: translate3d(0, 0, 0) scale(1); }
      to { transform: translate3d(1.2rem, 1.2rem, 0) scale(1.06); }
    }

    .shell {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 2rem;
    }

    .card {
      width: min(100%, 1120px);
      border: 1px solid var(--border);
      background: var(--card);
      backdrop-filter: blur(20px);
      box-shadow: var(--shadow);
      border-radius: 28px;
      overflow: hidden;
      padding: 2rem;
    }

    .content {
      display: grid;
      gap: 1.2rem;
    }

    .pill {
      width: fit-content;
      padding: 0.5rem 0.9rem;
      border-radius: 999px;
      font-size: 0.9rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      background: rgba(91, 124, 255, 0.1);
      border: 1px solid rgba(91, 124, 255, 0.16);
      color: #4560b7;
    }

    h1 {
      margin: 0;
      font-size: clamp(2rem, 4.4vw, 3.2rem);
      line-height: 1.1;
      letter-spacing: -0.03em;
    }

    .accent {
      color: var(--accent);
    }

    p {
      margin: 0;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.8;
      max-width: 760px;
    }

    .hero-grid {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 1.2rem;
      margin-top: 0.4rem;
    }

    .panel {
      background: rgba(255, 255, 255, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.8);
      border-radius: 20px;
      padding: 1.1rem;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }

    .panel h2 {
      margin: 0 0 0.6rem;
      font-size: 1.05rem;
      color: var(--text);
    }

    .panel ul {
      margin: 0;
      padding-left: 1rem;
      color: var(--muted);
      line-height: 1.7;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.8rem;
      margin-top: 0.3rem;
    }

    a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.85rem 1.1rem;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 700;
      transition: transform 180ms ease, box-shadow 180ms ease;
    }

    a.button:hover {
      transform: translateY(-2px);
    }

    .primary {
      color: white;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      box-shadow: 0 10px 20px rgba(91, 124, 255, 0.22);
    }

    .secondary {
      color: var(--text);
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid rgba(91, 124, 255, 0.14);
    }

    @media (max-width: 860px) {
      .hero-grid { grid-template-columns: 1fr; }
      .card { padding: 1.3rem; }
      .actions { flex-direction: column; }
      a.button { width: 100%; }
    }

    /* Editorial AI guide */
    body { background: #f3f1e9; color: #171916; }
    body::before, body::after { display: none; }
    .shell { display: block; padding: 0; }
    .card { width: 100%; max-width: none; padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; backdrop-filter: none; }
    .site-nav { position: sticky; top: 0; z-index: 10; height: 68px; padding: 0 max(20px, calc((100% - 1120px)/2)); display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #d6d4ca; background: rgba(243,241,233,.9); backdrop-filter: blur(14px); }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; letter-spacing: -.03em; }
    .brand i{width:32px;height:32px;display:grid;place-items:center;position:relative;border-radius:10px 10px 50% 50%;background:#171916;color:#dfff56;font:800 15px monospace;font-style:normal;transform:rotate(-3deg)}.brand i::after{content:"";position:absolute;width:7px;height:7px;border-radius:50%;right:-3px;top:-3px;background:#ff704d;box-shadow:0 0 0 3px #f3f1e9}
    .health-wrap{position:relative}.health-button{display:flex;align-items:center;gap:9px;padding:9px 12px;border:1px solid #d1cfc5;border-radius:99px;background:#fffdf6;color:#555b52;cursor:default;font-size:12px;font-weight:700}.health-dot{width:9px;height:9px;border-radius:50%;background:#aaa;box-shadow:0 0 0 4px rgba(120,120,120,.12)}.health-wrap.healthy .health-dot,.detail-row.ok i{background:#62be55}.health-wrap.healthy .health-dot{box-shadow:0 0 0 4px rgba(98,190,85,.16)}.health-wrap.unhealthy .health-dot,.detail-row.fail i{background:#ef6048}.health-wrap.unhealthy .health-dot{box-shadow:0 0 0 4px rgba(239,96,72,.16)}.health-popover{visibility:hidden;opacity:0;transform:translateY(-5px);position:absolute;z-index:30;right:0;top:calc(100% + 10px);width:245px;padding:15px;background:#1c1f1b;color:white;border:1px solid #3d413b;border-radius:14px;box-shadow:0 14px 38px rgba(0,0,0,.22);transition:.18s}.health-wrap:hover .health-popover,.health-wrap:focus-within .health-popover{visibility:visible;opacity:1;transform:none}.health-popover h3{font-size:13px;margin:0 0 10px}.detail-row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-top:1px solid #393d37;font-size:12px;color:#c4c9c0}.detail-row span{display:flex;align-items:center;gap:8px}.detail-row i{width:8px;height:8px;border-radius:50%;background:#888}.detail-row b{font-size:11px;color:#aeb4aa}.health-updated{display:block;margin-top:9px;color:#777e74;font:10px monospace}
    .health-popover{width:300px;padding:12px}.health-popover h3{margin-bottom:8px}
    .health-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin-bottom:8px}
    .health-stat{position:relative;overflow:hidden;padding:6px 4px;border:1px solid #393d37;border-radius:8px;background:#252923;text-align:center;min-width:0}
    .health-stat span{display:block;color:#8f978c;font-size:8px;font-weight:800;text-transform:uppercase;white-space:nowrap}
    .health-stat b{display:block;margin-top:3px;color:#f1f4ed;font:700 12px ui-monospace,monospace;overflow:hidden;text-overflow:ellipsis}
    .health-stat>span,.health-stat>b{position:relative;z-index:2;text-shadow:0 1px 3px #1c1f1b}
    .health-spark{position:absolute;z-index:1;inset:auto 0 0;width:100%;height:72%;opacity:.26;pointer-events:none}
    .health-spark polyline{fill:none;stroke:#dfff56;stroke-width:2.2;vector-effect:non-scaling-stroke}
    .health-runtime{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;border:1px solid #393d37;border-radius:8px;background:#252923}
    .health-runtime span{color:#8f978c;font-size:9px;font-weight:800}.health-runtime b{color:#f1f4ed;font:700 11px ui-monospace,monospace;white-space:nowrap}
    .health-popover .detail-row{padding:6px 0;font-size:11px}.health-popover .detail-row b{font-size:10px}.health-updated{margin-top:7px}
    .nav-links { display: flex; gap: 24px; font-size: 13px; }
    .nav-links a { color: #62675e; text-decoration: none; }
    .hero { padding: 82px max(20px, calc((100% - 1120px)/2)); display: grid; grid-template-columns: 1.1fr .9fr; gap: 60px; align-items: center; border-bottom: 1px solid #d6d4ca; }
    .hero h1 { font-size: clamp(48px, 6vw, 82px); line-height: 1.04; letter-spacing: -.065em; }
    .marker { position: relative; z-index: 0; white-space: nowrap; }
    .marker::after { content:""; position:absolute; left:-3px; right:-3px; bottom:3px; height:24%; background:#dfff56; z-index:-1; transform:rotate(-1deg); }
    .kicker { color:#7054ef; font: 500 12px ui-monospace, monospace; letter-spacing:.1em; }
    .hero-art { aspect-ratio:1; display:grid; place-items:center; position:relative; }
    .orbit { position:absolute; inset:7%; border:1px solid #c4c1b7; border-radius:50%; animation:spin 20s linear infinite; }
    .orbit::before { content:""; position:absolute; width:15px; height:15px; border-radius:50%; background:#ff704d; left:8%; top:18%; }
    .brain { width:47%; aspect-ratio:1; display:grid; place-items:center; border-radius:42% 58% 47% 53%; background:#7054ef; color:white; font-size:64px; box-shadow:16px 16px 0 #dfff56; transform:rotate(-7deg); }
    @keyframes spin { to { transform:rotate(360deg); } }
    .section { padding: 90px max(20px, calc((100% - 1120px)/2)); }
    .section.dark { background:#1c1f1b; color:white; }
    .head { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:end; margin-bottom:38px; }
    .head h2 { font-size:clamp(34px,4vw,52px); line-height:1.15; letter-spacing:-.045em; margin:10px 0 0; }
    .head p { justify-self:end; color:#697067; line-height:1.8; }
    .dark .head p { color:#a9afa5; }
    .tabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }
    .tab { border:1px solid #c9c7bd; background:transparent; border-radius:99px; padding:9px 15px; cursor:pointer; }
    .tab.active { background:#171916; color:white; }
    .theory { display:grid; grid-template-columns:1fr 1fr; min-height:330px; background:#fffdf6; border:1px solid #171916; border-radius:20px; overflow:hidden; box-shadow:8px 8px 0 #d6d3c9; }
    .theory-copy { padding:clamp(28px,5vw,58px); display:flex; flex-direction:column; justify-content:center; }
    .theory-copy h2 { font-size:31px; margin:10px 0 14px; }
    .theory-copy p { line-height:1.85; }
    .flow { background:#1c1f1b; display:flex; align-items:center; justify-content:center; gap:10px; padding:30px; color:white; }
    .node { width:88px; height:88px; border:1px solid #555b52; border-radius:16px; display:grid; place-items:center; text-align:center; font-size:12px; }
    .node b { display:block; color:#dfff56; font-size:21px; }
    .steps, .topics { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid #41453f; border-radius:18px; overflow:hidden; }
    .step { padding:28px 23px; min-height:260px; border-right:1px solid #41453f; }
    .step:last-child { border:0; } .step em { color:#dfff56; font:12px ui-monospace,monospace; font-style:normal; }
    .step h3 { margin-top:38px; font-size:20px; } .step p { color:#a9afa5; font-size:14px; line-height:1.75; }
    .topics { grid-template-columns:repeat(3,1fr); border:0; gap:16px; }
    .topic { padding:28px; min-height:275px; background:#fffdf6; border:1px solid #d6d4ca; border-radius:18px; transition:.2s; }
    .topic:hover { transform:translateY(-5px); border-color:#171916; box-shadow:7px 7px 0 #dfff56; }
    .topic span { color:#7054ef; font:12px ui-monospace,monospace; } .topic h3 { font-size:23px; margin-top:42px; } .topic p { font-size:14px; line-height:1.75; }
    .ethics { margin:0 max(20px, calc((100% - 1120px)/2)) 90px; padding:clamp(32px,6vw,68px); border-radius:24px; color:white; background:#7054ef; display:grid; grid-template-columns:1fr 1fr; gap:50px; }
    .ethics h2 { font-size:clamp(34px,4vw,52px); margin:8px 0 18px; } .ethics p { color:#ddd7ff; }
    .checks div { padding:15px 0; border-bottom:1px solid rgba(255,255,255,.22); } .checks b { color:#dfff56; margin-right:8px; }
    footer { border-top:1px solid #d6d4ca; padding:34px max(20px, calc((100% - 1120px)/2)); display:flex; justify-content:space-between; font-size:12px; color:#697067; }
    .main-menu{display:flex;gap:6px;padding:4px;border:1px solid #d6d4ca;border-radius:99px}.main-menu a{padding:8px 17px;border-radius:99px;text-decoration:none;color:#62675e;font-size:13px;font-weight:700}.main-menu a.active{background:#171916;color:white}.portfolio-view{display:none}body.archive-mode .home-view{display:none}body.archive-mode .portfolio-view{display:block}
    .portfolio-hero{padding:64px max(20px,calc((100% - 1120px)/2)) 42px;border-bottom:1px solid #d6d4ca}.portfolio-hero h1{font-size:clamp(40px,5vw,64px);margin:12px 0}.portfolio-layout{max-width:1120px;margin:auto;padding:42px 20px 90px;display:grid;grid-template-columns:260px minmax(0,1fr);gap:36px;align-items:start}.side-menu{position:sticky;top:98px}.project-list{display:grid;gap:7px}.project-button{padding:15px;text-align:left;border:1px solid transparent;border-radius:12px;background:transparent;cursor:pointer}.project-button strong{display:block}.project-button small{color:#858a81}.project-button.active{background:#fffdf6;border-color:#171916;box-shadow:4px 4px 0 #dfff56}
    .project-document{background:#fffdf6;border:1px solid #d6d4ca;border-radius:20px;overflow:hidden;min-width:0}.document-head,.document-body{padding:clamp(28px,5vw,52px);min-width:0}.document-head{border-bottom:1px solid #e0ded5}.project-meta{display:flex;gap:7px;margin-bottom:24px;flex-wrap:wrap}.project-meta span{padding:6px 10px;background:#eeeaff;color:#6246dd;border-radius:99px;font:11px monospace}.document-head h2{font-size:clamp(30px,4vw,45px);margin:0}.document-head p,.document-body p,.document-body li{line-height:1.8;color:#656b62}.feature-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:24px 0}.feature{padding:18px;border:1px solid #e0ded5;border-radius:12px}.feature b{display:block}.feature span{font-size:13px;color:#747970}.project-lab{display:none;margin-top:10px}.project-lab.active{display:block}.project-default.hidden{display:none}.chunking-shell{display:grid;gap:18px}.chunking-controls{display:grid;grid-template-columns:minmax(0,1fr) 220px 120px;gap:12px;align-items:end}.chunking-controls label{display:block;font-size:12px;font-weight:700;color:#666c63}.chunking-controls textarea,.chunking-controls select,.chunking-controls input{width:100%;margin-top:7px;padding:12px 13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff;font:14px/1.6 inherit}.chunking-controls textarea{min-height:112px;resize:vertical}.chunking-controls input[type=checkbox]{width:auto;margin:0}.rerank-option{min-height:48px;display:flex!important;align-items:center;gap:8px;padding:12px 13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff}.rerank-option input{margin:0}.rerank-option span{font-size:12px;font-weight:800;color:#666c63}.chunking-run{height:48px;border:0;border-radius:14px;background:#171916;color:#dfff56;font-weight:800;cursor:pointer}.chunking-run:disabled{opacity:.45;cursor:wait}.chunking-note{padding:14px 16px;border-radius:14px;background:#f4f0ff;color:#5b47c0;font-size:13px;line-height:1.7}.chunking-compare{display:grid;grid-template-columns:1fr 1fr;gap:16px}.compare-panel{border:1px solid #ddd9cf;border-radius:18px;background:#fcfbf7;overflow:hidden}.compare-head{padding:18px 18px 14px;border-bottom:1px solid #e7e3d8;background:linear-gradient(180deg,#fff,#faf8f1)}.compare-head strong{display:block;font-size:17px}.compare-head small{display:block;margin-top:6px;color:#7b8178}.compare-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.compare-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:#efede5;color:#666c63;font:11px ui-monospace,monospace}.compare-badge.ok{background:#edf9eb;color:#2b7c3b}.compare-badge.error{background:#fff0eb;color:#b44f32}.compare-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}.compare-stat{padding:10px 12px;border:1px solid #e6e2d7;border-radius:12px;background:#fff}.compare-stat b{display:block;font-size:18px;line-height:1.1}.compare-stat span{display:block;margin-top:4px;color:#7b8178;font-size:11px}.compare-body{padding:18px}.compare-answer{padding:16px;border-radius:16px;background:#171916;color:#eff3e9}.compare-answer span{display:block;margin-bottom:8px;color:#dfff56;font:11px ui-monospace,monospace}.compare-answer pre{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.75 inherit;color:#eff3e9}.compare-list{display:grid;gap:10px;margin-top:16px}.compare-item{padding:14px;border:1px solid #e6e2d7;border-radius:14px;background:#fff}.compare-item-head{display:flex;justify-content:space-between;gap:10px;align-items:start}.compare-item strong{display:block;font-size:14px}.compare-score{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;background:#f2eeff;color:#6045d4;font:11px ui-monospace,monospace;white-space:nowrap}.compare-item small{display:block;margin-top:6px;color:#7b8178}.compare-empty{padding:18px;border:1px dashed #d8d4ca;border-radius:14px;color:#7a8077;font-size:13px;text-align:center}.compare-loading .compare-answer,.compare-loading .compare-item,.compare-loading .compare-stat{opacity:.55}.compare-loading .compare-answer::after{content:'비교 중...';display:block;margin-top:10px;color:#dfff56;font:11px ui-monospace,monospace}.compare-status{margin-top:12px;font-size:13px;color:#747970}.compare-grid-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}.compare-grid-head h3{margin:0;font-size:18px}.compare-grid-head p{margin:0;color:#7a8077;font-size:13px}.compare-panel.error .compare-answer{background:#4b2b22;color:#fff5f2}.compare-panel.error .compare-answer span{color:#ffd9c9}@media(max-width:900px){.chunking-controls{grid-template-columns:1fr}.chunking-compare{grid-template-columns:1fr}.compare-stats{grid-template-columns:1fr 1fr}}
    .chunking-lab-v2{display:grid;gap:20px}.chunking-doc-grid{display:grid;grid-template-columns:240px minmax(0,1fr);gap:14px}.chunking-file{display:grid;align-content:start;gap:10px;padding:16px;border:1px dashed #bbb8ad;border-radius:14px;background:#f5f2e9;color:#62675e;font-size:12px;font-weight:800}.chunking-file input{width:100%;font:12px inherit}.chunking-file span{font-weight:500;color:#7a8077;line-height:1.5}.document-input label,.rag-console label{display:block;font-size:12px;font-weight:800;color:#666c63}.document-input textarea{width:100%;min-height:190px;margin-top:7px;padding:13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff;font:13px/1.65 inherit;resize:vertical}.strategy-picker{display:grid;gap:12px;padding:16px;border:1px solid #e0ddd2;border-radius:16px;background:#fbfaf5}.strategy-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.strategy-option{display:flex;gap:9px;align-items:flex-start;padding:13px;border:1px solid #d8d4ca;border-radius:12px;background:#fffdf6;cursor:pointer}.strategy-option input{margin-top:3px}.strategy-option strong{display:block;font-size:13px}.strategy-option span{display:block;margin-top:4px;color:#777d73;font-size:11px;line-height:1.45}.plan-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.plan-actions button,.embed-plan,.chunking-run{min-height:44px;padding:0 14px;border:0;border-radius:12px;background:#171916;color:#dfff56;font-weight:800;cursor:pointer}.plan-actions button:disabled,.embed-plan:disabled,.chunking-run:disabled{opacity:.45;cursor:wait}.chunking-plans{display:grid;gap:14px}.plan-card{border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;overflow:hidden}.plan-head{display:flex;justify-content:space-between;gap:12px;align-items:start;padding:16px;border-bottom:1px solid #e5e1d6;background:#fbfaf5}.plan-head strong{font-size:17px}.plan-head small{color:#777d73;font:11px ui-monospace,monospace}.plan-body{padding:16px}.plan-desc{font-size:13px;line-height:1.7;color:#62675e}.pros-cons{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.pros-cons div{padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:white}.pros-cons b{font-size:12px}.pros-cons ul{margin:7px 0 0;padding-left:18px;color:#71776e;font-size:12px;line-height:1.6}.embed-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.embed-status{color:#686e65;font-size:12px}.chunk-list{display:grid;gap:8px;max-height:360px;overflow:auto}.chunk-detail{border:1px solid #e4e0d5;border-radius:12px;background:#fff}.chunk-detail summary{padding:11px 13px;cursor:pointer;font-size:12px;font-weight:800;color:#555b52}.chunk-detail pre{padding:0 13px 13px;margin:0;color:#30342f;background:transparent;white-space:pre-wrap;word-break:break-word;font:12px/1.7 inherit}.rag-console{display:grid;gap:14px;padding-top:10px;border-top:1px solid #e3dfd3;min-width:0;max-width:100%;overflow:hidden}.rag-console .chunking-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;min-width:0;max-width:100%}.rag-console .prompt-control{flex:1 0 100%;min-width:0}.rag-console .prompt-control textarea{min-height:104px}.rag-console .chunking-controls>label:not(.prompt-control){flex:1 1 118px;min-width:0}.rag-console .chunking-controls>label:nth-of-type(2){flex:2 1 220px}.rag-console .rerank-option{flex:1 1 150px}.rag-console .chunking-run{flex:1 1 140px;width:auto;min-width:120px;padding:0 10px;white-space:normal}.rag-console label{min-width:0}.chunking-shell,.chunking-lab-v2,.chunking-note,.chunking-compare{min-width:0;max-width:100%}.chunking-note{overflow-wrap:anywhere}.rag-console h3{margin:0;font-size:18px}.chunking-compare.vertical{grid-template-columns:1fr}.result-snippets{width:100%;height:8.7em;margin-top:12px;padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:#fff;color:#3a3f39;font:12px/1.55 inherit;resize:vertical}.compare-chunk-button{margin-top:12px;min-height:36px;padding:0 12px;border:1px solid #171916;border-radius:10px;background:#fffdf6;color:#171916;font-weight:800;cursor:pointer}.compare-chunk-detail{margin-top:10px;display:grid;gap:8px}.compare-chunk-detail[hidden]{display:none}.compare-chunk{padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:#fff}.compare-chunk strong{display:block;font-size:12px}.compare-chunk pre{padding:8px 0 0;color:#30342f;background:transparent;white-space:pre-wrap;word-break:break-word;font:12px/1.65 inherit}.compare-panel[data-embedded="true"] .compare-head{box-shadow:inset 4px 0 0 #dfff56}.compare-evaluation{border:1px solid #171916;border-radius:16px;background:#fffdf6;box-shadow:5px 5px 0 #dfff56;overflow:hidden}.compare-evaluation .compare-head{background:#171916;color:#fff;border:0}.compare-evaluation .compare-head small{color:#cfd5ca}.evaluation-grid{display:grid;gap:10px;padding:16px}.evaluation-row{display:grid;grid-template-columns:1.1fr .9fr .9fr .8fr;gap:10px;align-items:center;padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:#fff}.evaluation-row b{font-size:13px}.evaluation-row span{font-size:12px;color:#697067}.evaluation-winner{font-weight:800;color:#171916}.evaluation-note{padding:0 16px 16px;color:#697067;font-size:12px;line-height:1.6}@media(max-width:720px){.evaluation-row{grid-template-columns:1fr}.evaluation-row span{display:block}}@media(max-width:900px){.chunking-doc-grid,.strategy-grid,.pros-cons{grid-template-columns:1fr}.rag-console .chunking-controls{display:grid;grid-template-columns:1fr}.rag-console .prompt-control,.rag-console .chunking-controls>label,.rag-console .rerank-option,.rag-console .chunking-run{grid-column:auto;width:100%;min-width:0}}
    .report-draft-lab{display:grid;gap:16px;min-width:0}
    .report-draft-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:18px;border:1px solid #d8d4ca;border-radius:16px;background:#f4f7f2}
    .report-draft-head h3{margin:0;font-size:19px}.report-draft-head p{margin:6px 0 0;color:#687068;font-size:12px;line-height:1.55}
    .report-draft-health{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border-radius:999px;background:#fff;color:#666c63;font:11px ui-monospace,monospace;white-space:nowrap;border:1px solid #d8d4ca}
    .report-draft-health::before{content:"";width:8px;height:8px;border-radius:50%;background:#d99b27}.report-draft-health.ok::before{background:#2f9e55}.report-draft-health.error::before{background:#c74b42}
    .report-draft-grid{display:grid;grid-template-columns:minmax(280px,.9fr) minmax(0,1.1fr);gap:16px;align-items:start}
    .report-draft-panel{padding:18px;border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;min-width:0}
    .report-draft-panel h4{margin:0 0 14px;font-size:16px}.report-draft-panel label{display:grid;gap:7px;color:#62675e;font-size:12px;font-weight:800;min-width:0}
    .report-draft-panel textarea,.report-draft-panel select,.report-draft-dialog input,.report-draft-dialog textarea{width:100%;padding:12px 13px;border:1px solid #d7d4ca;border-radius:11px;background:#fff;color:#30342f;font:13px/1.55 inherit}
    .report-draft-panel textarea{min-height:170px;resize:vertical}.report-draft-presets{display:grid;gap:7px;margin-bottom:13px}.report-draft-presets button{padding:10px 11px;border:1px solid #dedbd1;border-radius:10px;background:#faf9f4;color:#555b52;text-align:left;font-size:12px;line-height:1.45;cursor:pointer}
    .report-draft-presets button:hover{border-color:#1f7a4d;background:#eef7f0}.report-draft-model-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:end;margin-top:12px}
    .report-draft-option-button,.report-draft-secondary{min-height:43px;padding:0 13px;border:1px solid #171916;border-radius:11px;background:#fffdf6;color:#171916;font-weight:800;cursor:pointer;white-space:nowrap}
    .report-draft-option-summary{margin-top:9px;color:#747970;font:11px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}
    .report-draft-actions{display:flex;align-items:center;gap:11px;margin-top:14px;flex-wrap:wrap}.report-draft-generate{min-height:46px;padding:0 18px;border:0;border-radius:12px;background:#1f7a4d;color:#fff;font-weight:900;cursor:pointer}.report-draft-generate:disabled{opacity:.5;cursor:wait}
    .report-draft-status{color:#6e756c;font-size:12px;line-height:1.45}.report-draft-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px}.report-draft-meta div{padding:10px;border:1px solid #e2ded4;border-radius:10px;background:#faf9f4;min-width:0}.report-draft-meta span{display:block;color:#777d73;font-size:10px;font-weight:800}.report-draft-meta b{display:block;margin-top:5px;font-size:12px;overflow-wrap:anywhere}
    .report-draft-answer{min-height:250px;margin:0;padding:16px;border:1px solid #e0ddd3;border-radius:12px;background:#fbfcfb;color:#27312a;white-space:pre-wrap;word-break:break-word;font:14px/1.75 inherit}.report-draft-review{margin-top:12px;padding:12px;border:1px solid #ebcd8b;border-radius:10px;background:#fff3d6;color:#805600;font-size:12px;line-height:1.55}
    .report-draft-dialog{width:min(680px,calc(100% - 28px));padding:0;border:1px solid #cbc7bd;border-radius:16px;background:#fffdf6;color:#30342f;box-shadow:0 24px 80px rgba(23,25,22,.28)}.report-draft-dialog::backdrop{background:rgba(23,25,22,.45);backdrop-filter:blur(3px)}.report-draft-dialog-box{padding:20px}.report-draft-dialog-head{display:flex;justify-content:space-between;gap:12px;align-items:start}.report-draft-dialog-head h4{margin:0;font-size:18px}.report-draft-dialog-head p{margin:5px 0 0;color:#747970;font-size:12px}.report-draft-dialog-close{border:0;background:transparent;font-size:22px;cursor:pointer}.report-draft-option-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}.report-draft-option-grid label{display:grid;gap:7px;color:#62675e;font-size:11px;font-weight:800}.report-draft-dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.report-draft-dialog-actions .save{background:#171916;color:#dfff56}
    .report-draft-system-prompt{grid-column:1/-1}.report-draft-system-prompt textarea{min-height:170px;resize:vertical}.report-draft-system-prompt small{color:#7a8077;font-size:10px;line-height:1.5;font-weight:500}
    @media(max-width:900px){.report-draft-grid{grid-template-columns:1fr}.report-draft-meta{grid-template-columns:1fr 1fr 1fr}}
    @media(max-width:560px){.report-draft-head{display:grid}.report-draft-model-row,.report-draft-option-grid,.report-draft-meta{grid-template-columns:1fr}.report-draft-option-button,.report-draft-generate{width:100%}}

    .field-inspection-lab{display:grid;gap:14px;min-width:0}
    .field-inspection-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:16px 18px;border:1px solid #ddd9cf;border-radius:16px;background:#fcfbf7}
    .field-inspection-toolbar strong{display:block;font-size:15px}
    .field-inspection-toolbar span{display:block;margin-top:4px;color:#747970;font-size:12px;line-height:1.5}
    .field-inspection-open{flex:none;padding:10px 14px;border-radius:12px;background:#171916;color:#dfff56;text-decoration:none;font-size:12px;font-weight:800}
    .field-inspection-frame-wrap{overflow:hidden;border:1px solid #d8d5ca;border-radius:18px;background:#eef0f8;box-shadow:0 16px 40px rgba(24,28,38,.12)}
    .field-inspection-frame{display:block;width:100%;height:clamp(720px,80vh,1080px);border:0;background:#f7f7fb}
    .field-inspection-policy{padding:12px 15px;border-radius:14px;background:#fff7dc;color:#775b00;font-size:12px;line-height:1.65}
    @media(max-width:800px){.field-inspection-toolbar{align-items:flex-start;flex-direction:column}.field-inspection-open{width:100%;text-align:center}.field-inspection-frame{height:780px}}
    .safe-agent-lab{display:grid;gap:18px}
    .safe-agent-console{display:grid;grid-template-columns:1fr;gap:16px}
    .safe-agent-map{width:100%;height:300px;min-height:300px;border:1px solid #d8d4ca;border-radius:16px;background:#dfe8df;position:relative;overflow:hidden;z-index:0}
    .safe-agent-map.leaflet-container{font:inherit;overflow:hidden}
    .safe-agent-map .leaflet-pane,.safe-agent-map .leaflet-map-pane,.safe-agent-map .leaflet-tile,.safe-agent-map .leaflet-marker-icon,.safe-agent-map .leaflet-marker-shadow,.safe-agent-map .leaflet-tile-container,.safe-agent-map .leaflet-pane>svg,.safe-agent-map .leaflet-pane>canvas,.safe-agent-map .leaflet-zoom-box,.safe-agent-map .leaflet-image-layer,.safe-agent-map .leaflet-layer{position:absolute;left:0;top:0}
    .safe-agent-map .leaflet-tile{max-width:none!important;user-select:none}
    .safe-agent-map .leaflet-tile-pane{z-index:200}.safe-agent-map .leaflet-overlay-pane{z-index:400}.safe-agent-map .leaflet-shadow-pane{z-index:500}.safe-agent-map .leaflet-marker-pane{z-index:600}.safe-agent-map .leaflet-tooltip-pane{z-index:650}.safe-agent-map .leaflet-popup-pane{z-index:700}
    .safe-agent-map .leaflet-control{position:relative;z-index:800;pointer-events:auto}.safe-agent-map .leaflet-top,.safe-agent-map .leaflet-bottom{position:absolute;z-index:1000;pointer-events:none}.safe-agent-map .leaflet-top{top:0}.safe-agent-map .leaflet-right{right:0}.safe-agent-map .leaflet-bottom{bottom:0}.safe-agent-map .leaflet-left{left:0}
    .safe-agent-map .leaflet-control-attribution{font-size:10px}
    .safe-agent-map-fallback{position:absolute;inset:0;display:grid;place-items:center;background:linear-gradient(135deg,#f8fbff,#eef7f2);color:#62675e;font-size:13px;z-index:1}
    .safe-agent-gps-popup{position:absolute;left:50%;top:50%;z-index:1200;transform:translate(-50%,-50%);display:flex;align-items:center;gap:10px;max-width:calc(100% - 32px);padding:13px 16px;border:1px solid #d8d4ca;border-radius:8px;background:rgba(255,253,246,.97);color:#30342f;font-size:13px;font-weight:800;box-shadow:0 14px 34px rgba(23,25,22,.2);pointer-events:none}
    .safe-agent-gps-popup[hidden]{display:none}.safe-agent-gps-popup i{width:18px;height:18px;flex:0 0 18px;border:2px solid #d4d1c7;border-top-color:#2563eb;border-radius:50%;animation:safe-agent-spin .8s linear infinite}
    @keyframes safe-agent-spin{to{transform:rotate(360deg)}}
    .safe-agent-run.is-stop{background:#8b2f21;color:#fff}
    .safe-agent-map.is-fallback::before{content:"";position:absolute;inset:22px;border:1px dashed rgba(37,99,235,.28);border-radius:50%;z-index:2}
    .safe-agent-map.is-fallback::after{content:"";position:absolute;inset:48px;border:1px dashed rgba(23,25,22,.18);border-radius:50%;z-index:2}
    .safe-agent-map-label{position:absolute;left:16px;bottom:16px;z-index:800;padding:10px 12px;border:1px solid #d8d4ca;border-radius:12px;background:rgba(255,253,246,.94);color:#555b52;font:12px ui-monospace,monospace;box-shadow:0 8px 20px rgba(23,25,22,.1);pointer-events:none}
    .safe-agent-controls,.safe-agent-result article,.safe-agent-status-card{border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;min-width:0}
    .safe-agent-controls{padding:16px;display:grid;grid-template-columns:1fr;gap:12px;align-items:end;overflow:hidden}
    .safe-agent-title-row{display:flex;align-items:center;gap:10px;min-width:0;flex-wrap:wrap}
    .safe-agent-title-row h3{margin:0;font-size:18px;line-height:1.25;white-space:nowrap}
    .safe-agent-title-row .safe-agent-badges{flex:1 1 auto;min-width:0}
    .safe-agent-fields{display:grid;grid-template-columns:minmax(120px,.55fr) minmax(120px,.55fr) minmax(180px,1fr);gap:10px}
    .safe-agent-fields label,.safe-agent-execute-row label{display:grid;gap:6px;color:#62675e;font-size:12px;font-weight:800;min-width:0}
    .safe-agent-fields input,.safe-agent-execute-row select{width:100%;padding:12px 13px;border:1px solid #d7d4ca;border-radius:12px;background:#fff;font:14px/1.4 inherit;min-width:0}
    .safe-agent-address-field input{color:#30342f;background:#fbfaf5}
    .safe-agent-execute-row{display:grid;grid-template-columns:minmax(230px,1fr) auto minmax(220px,1.15fr);gap:10px;align-items:end;min-width:0}
    .safe-agent-model-field{min-width:0}
    .safe-agent-run{min-height:44px;padding:0 16px;border:0;border-radius:12px;background:#171916;color:#dfff56;font-weight:800;cursor:pointer;white-space:nowrap}
    .safe-agent-run:disabled{opacity:.5;cursor:wait}
    .safe-agent-inline-message{min-height:44px;display:flex;align-items:center;padding:10px 12px;border:1px dashed #d8d4ca;border-radius:12px;color:#6f756c;font-size:12px;line-height:1.45;min-width:0;overflow-wrap:anywhere}
    .safe-agent-toggle{display:flex;align-items:center;gap:8px;color:#62675e;font-size:12px;font-weight:800}
    .safe-agent-samples{display:flex;gap:8px;flex-wrap:wrap}
    .safe-agent-samples button{min-height:34px;padding:0 11px;border:1px solid #d8d4ca;border-radius:10px;background:#fbfaf5;color:#555b52;font-size:12px;font-weight:800;cursor:pointer}
    .safe-agent-status{display:grid;grid-template-columns:minmax(0,1fr) repeat(2,86px);gap:10px;align-items:stretch}
    .safe-agent-status-card{padding:10px;display:grid;align-content:center;justify-items:center;text-align:center;min-height:132px}
    .safe-agent-status-card b{display:block;font-size:28px;line-height:1;overflow-wrap:anywhere}
    .safe-agent-status-card span{display:block;margin-top:7px;color:#747970;font-size:11px;font-weight:800;line-height:1.25}
    .safe-agent-rain-card{grid-column:auto;padding:12px 14px;border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;min-width:0;display:grid;grid-template-columns:116px minmax(0,1fr);gap:12px;align-items:center;min-height:156px}
    .safe-agent-rain-head{display:grid;gap:6px;align-content:center;min-width:0}.safe-agent-rain-head strong{font-size:14px}.safe-agent-rain-head span{color:#747970;font-size:11px;line-height:1.35;overflow-wrap:anywhere}.safe-agent-rain-peak{font:11px ui-monospace,monospace;color:#171916}
    .safe-agent-rain-graph{min-width:0}.safe-agent-rain-svg{display:block;width:100%;height:112px;overflow:visible}.safe-agent-rain-axis{display:grid;grid-template-columns:repeat(13,minmax(0,1fr));gap:2px;margin-top:2px;color:#747970;font:10px ui-monospace,monospace;text-align:center}.safe-agent-rain-axis span{min-width:0;white-space:nowrap}.safe-agent-rain-axis .current{color:#171916;font-weight:900}.safe-agent-rain-line{fill:none;stroke:#2563eb;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.safe-agent-rain-area{fill:rgba(37,99,235,.1)}.safe-agent-rain-dot{fill:#fff;stroke:#2563eb;stroke-width:2}.safe-agent-rain-now{stroke:#171916;stroke-width:1;stroke-dasharray:4 4;opacity:.45}.safe-agent-rain-grid{stroke:#d8d4ca;stroke-width:1;opacity:.7}
    .safe-agent-weather-legend{display:flex;flex-wrap:wrap;gap:8px;color:#555b53;font-size:10px;font-weight:800}.safe-agent-weather-legend span{display:inline-flex;align-items:center;gap:4px;margin:0}.safe-agent-weather-legend i{width:14px;height:3px;border-radius:0;background:#2563eb}.safe-agent-weather-legend i.temp{background:#d9573f}
    .safe-agent-temp-line{fill:none;stroke:#d9573f;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}.safe-agent-temp-dot{fill:#fffdf6;stroke:#d9573f;stroke-width:2}
    .safe-agent-chart-axis{font:9px ui-monospace,monospace;font-weight:800}.safe-agent-chart-axis.rain{fill:#2563eb}.safe-agent-chart-axis.temp{fill:#d9573f}.safe-agent-weather-icon{fill:#555b53;font:15px sans-serif}.safe-agent-weather-icon.current{font-weight:900;fill:#171916}
    .safe-agent-result{display:grid;gap:14px}
    .safe-agent-result article{padding:18px}
    .safe-agent-result h3{margin:0 0 12px;font-size:17px}
    .safe-agent-report pre,.safe-agent-context pre{margin:0;padding:0;background:transparent;color:#30342f;white-space:pre-wrap;word-break:break-word;font:13px/1.75 inherit}
    .safe-agent-report{box-shadow:5px 5px 0 #dfff56}
    .safe-agent-report pre{font-size:14px}
    .safe-agent-empty{padding:18px;border:1px dashed #d8d4ca;border-radius:14px;color:#7a8077;text-align:center;font-size:13px}
    .safe-agent-badges{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .safe-agent-badge{padding:5px 10px;border-radius:999px;background:#efede5;color:#62675e;font:11px ui-monospace,monospace;white-space:nowrap}
    .safe-agent-badge.ok{background:#edf9eb;color:#2b7c3b}
    .safe-agent-badge.warn{background:#fff5da;color:#8b6200}
    .safe-agent-list{display:grid;gap:8px;min-width:0}
    .safe-agent-list div{display:grid;grid-template-columns:minmax(120px,.7fr) minmax(0,1.3fr);gap:12px;padding:10px 0;border-top:1px solid #ebe7dc;color:#62675e;min-width:0}
    .safe-agent-list span,.safe-agent-list b{min-width:0;overflow-wrap:anywhere}
    .safe-agent-list b{color:#171916;text-align:right}
    .safe-agent-detail-sections{display:grid;gap:10px;margin-top:14px}.safe-agent-detail-section{border:1px solid #e3dfd3;border-radius:12px;background:#fbfaf5;overflow:hidden}.safe-agent-detail-section summary{min-height:44px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;font-size:13px;font-weight:900;color:#30342f;list-style:none}.safe-agent-detail-section summary::-webkit-details-marker{display:none}.safe-agent-detail-section summary::after{content:'펼치기';padding:5px 9px;border:1px solid #d8d4ca;border-radius:999px;background:#fffdf6;color:#555b52;font-size:11px}.safe-agent-detail-section[open] summary::after{content:'접기'}.safe-agent-detail-count{margin-left:auto;color:#747970;font:11px ui-monospace,monospace;white-space:nowrap}.safe-agent-detail-list{display:grid;gap:8px;padding:0 12px 12px}.safe-agent-detail-item{padding:11px;border:1px solid #e7e3d8;border-radius:10px;background:#fff;min-width:0}.safe-agent-detail-item strong{display:block;font-size:13px;line-height:1.35}.safe-agent-detail-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}.safe-agent-detail-meta span{padding:4px 7px;border-radius:999px;background:#efede5;color:#60665d;font:10px ui-monospace,monospace}.safe-agent-detail-fields{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:5px 10px;margin:9px 0 0;padding-top:9px;border-top:1px dashed #ddd8cd;font-size:11px;color:#6f756c}.safe-agent-detail-fields dt{font-weight:900;color:#555b52}.safe-agent-detail-fields dd{margin:0;min-width:0;overflow-wrap:anywhere}.safe-agent-detail-empty{padding:12px;border:1px dashed #d8d4ca;border-radius:10px;color:#7a8077;text-align:center;font-size:12px;background:#fff}
    @media(max-width:1100px){.safe-agent-status{grid-template-columns:1fr 1fr}.safe-agent-rain-card{grid-column:1/-1}}
    @media(max-width:900px){.safe-agent-fields{grid-template-columns:1fr 1fr}.safe-agent-address-field{grid-column:1/-1}.safe-agent-execute-row{grid-template-columns:minmax(0,1fr) auto}.safe-agent-inline-message{grid-column:1/-1}.safe-agent-status{grid-template-columns:1fr 1fr}.safe-agent-rain-card{grid-column:1/-1}}
    @media(max-width:560px){.safe-agent-map{height:300px}.safe-agent-fields,.safe-agent-execute-row{grid-template-columns:1fr}.safe-agent-run{width:100%}.safe-agent-title-row h3{white-space:normal}.safe-agent-rain-card{grid-template-columns:1fr}.safe-agent-rain-axis{font-size:9px}.safe-agent-rain-axis span:nth-child(even){visibility:hidden}.safe-agent-status-card{min-height:78px}}
    .safe-agent-map-legend{position:absolute;right:14px;bottom:14px;z-index:800;display:flex;gap:8px;flex-wrap:wrap;padding:8px 10px;border:1px solid #d8d4ca;border-radius:12px;background:rgba(255,253,246,.94);box-shadow:0 8px 20px rgba(23,25,22,.1);font-size:11px;font-weight:800;color:#555b52;pointer-events:none}
    .safe-agent-map-legend span{display:flex;align-items:center;gap:6px}.safe-agent-map-legend i{width:10px;height:10px;border-radius:50%;display:inline-block}.safe-agent-map-legend .risk{background:#dc2626}.safe-agent-map-legend .shelter{background:#16a34a}
    .safe-agent-div-icon{width:18px!important;height:18px!important;margin-left:-9px!important;margin-top:-9px!important;border-radius:50%;border:3px solid #fff;box-shadow:0 7px 18px rgba(23,25,22,.28)}.safe-agent-div-icon.risk{background:#dc2626}.safe-agent-div-icon.shelter{background:#16a34a}.safe-agent-div-icon span{display:block;width:100%;height:100%;border-radius:50%;box-shadow:0 0 0 7px rgba(220,38,38,.18)}.safe-agent-div-icon.shelter span{box-shadow:0 0 0 7px rgba(22,163,74,.18)}
    .safe-agent-preset-panel{grid-column:1/-1;display:grid;gap:10px}.safe-agent-preset-form{display:grid;grid-template-columns:minmax(150px,1fr) auto auto;gap:10px;align-items:end}.safe-agent-preset-form label{display:grid;gap:6px;color:#62675e;font-size:12px;font-weight:800}.safe-agent-preset-form input{width:100%;padding:10px 12px;border:1px solid #d7d4ca;border-radius:10px;background:#fff;font:13px/1.4 inherit}.safe-agent-preset-form button{min-height:40px;padding:0 13px;border:1px solid #171916;border-radius:10px;background:#fffdf6;color:#171916;font-weight:800;cursor:pointer}.safe-agent-preset-item{display:inline-flex;align-items:center;gap:4px;border:1px solid #d8d4ca;border-radius:10px;background:#fbfaf5;overflow:hidden}.safe-agent-preset-item button{border:0;border-radius:0}.safe-agent-preset-delete{min-width:34px;color:#8b2f21!important;background:#fff6f1!important;border-left:1px solid #e8d6cc!important}
    @media(max-width:640px){.safe-agent-preset-form{grid-template-columns:1fr 1fr}.safe-agent-preset-form label{grid-column:1/-1}.safe-agent-map-label{left:12px;right:12px;bottom:54px}.safe-agent-map-legend{left:12px;right:12px;justify-content:center}}
    .safe-agent-data-bar{border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;overflow:hidden}.safe-agent-data-head{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:16px;border-bottom:1px solid #e5e1d6;background:#fbfaf5;cursor:pointer}.safe-agent-data-head strong{display:block;font-size:16px}.safe-agent-data-head small{display:block;margin-top:5px;color:#777d73;font-size:12px}.safe-agent-data-actions{display:flex;gap:8px;flex-wrap:wrap}.safe-agent-data-actions button{min-height:38px;padding:0 12px;border:1px solid #171916;border-radius:10px;background:#fffdf6;color:#171916;font-size:12px;font-weight:800;cursor:pointer}.safe-agent-data-actions button.primary{background:#171916;color:#dfff56}.safe-agent-data-actions button:disabled{opacity:.45;cursor:wait}.safe-agent-log-toggle{background:#efede5!important;color:#555b52!important;border-color:#d8d4ca!important}.safe-agent-data-log{display:block;width:100%;height:118px;border:0;border-radius:0;padding:14px;background:#1c1f1b;color:#e9ece6;font:12px/1.65 ui-monospace,monospace;resize:vertical}.safe-agent-data-bar.is-collapsed .safe-agent-data-head{border-bottom:0}.safe-agent-data-bar.is-collapsed .safe-agent-data-log{display:none}.safe-agent-refresh{min-height:44px;padding:0 14px;border:1px solid #171916;border-radius:12px;background:#fffdf6;color:#171916;font-weight:800;cursor:pointer}.safe-agent-refresh:disabled{opacity:.5;cursor:wait}.safe-agent-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.safe-agent-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.safe-agent-actions .safe-agent-run{flex:0 0 auto}@media(max-width:640px){.safe-agent-data-head{display:grid}.safe-agent-data-actions{display:grid;grid-template-columns:1fr 1fr}.safe-agent-data-actions button{width:100%}}
    .code-wrap{margin:16px 0 30px;border-radius:14px;overflow:hidden;background:#1c1f1b}.code-head{display:flex;justify-content:space-between;padding:12px 16px;color:#aab0a6;border-bottom:1px solid #383c36;font:12px monospace}.copy-code{border:0;background:transparent;color:#dfff56;cursor:pointer}pre{margin:0;padding:22px;overflow:auto;color:#e9ece6;font:13px/1.75 monospace}.next-note{padding:20px;border-left:4px solid #7054ef;background:#f0edff;color:#5540b9}
    .chat-home{height:calc(100vh - 68px);min-height:620px;display:grid;grid-template-columns:260px 1fr}.chat-sidebar{padding:22px 16px;border-right:1px solid #d6d4ca;display:flex;flex-direction:column;gap:18px;background:#ebe9e0}.new-chat{width:100%;padding:13px 15px;border:1px solid #171916;border-radius:12px;background:#171916;color:white;font-weight:700;cursor:pointer;display:flex;justify-content:space-between}.new-chat:hover{box-shadow:4px 4px 0 #dfff56}.chat-history-label{font:11px monospace;color:#777c73;margin:8px}.history-item{padding:12px;border-radius:10px;font-size:13px;background:#fffdf6;border:1px solid #dad8ce}.chat-sidebar-note{margin-top:auto;padding:14px;border-top:1px solid #d1cfc5;color:#747970;font-size:11px;line-height:1.6}.chat-main{min-width:0;display:grid;grid-template-rows:auto 1fr auto;max-height:calc(100vh - 68px)}.chat-toolbar{height:66px;padding:0 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #d6d4ca}.model-select{min-width:210px;padding:10px 13px;border:1px solid #c9c7bd;border-radius:10px;background:#fffdf6;color:#171916;font-weight:700}.ollama-status{display:flex;gap:8px;align-items:center;color:#687066;font-size:12px}.ollama-status i{width:8px;height:8px;border-radius:50%;background:#67c35b;box-shadow:0 0 0 4px #dff0da}
    .messages{overflow-y:auto;padding:38px max(28px,calc((100% - 820px)/2));scroll-behavior:smooth}.empty-chat{text-align:center;min-height:100%;display:grid;place-content:center}.ai-mark{width:64px;height:64px;margin:0 auto 22px;display:grid;place-items:center;border-radius:22px;background:#7054ef;color:white;font-size:28px;box-shadow:8px 8px 0 #dfff56}.empty-chat h1{font-size:clamp(34px,4vw,52px);margin:0 0 12px}.suggestions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:30px;max-width:640px}.suggestion{padding:15px;text-align:left;border:1px solid #d2d0c6;border-radius:12px;background:#fffdf6;cursor:pointer;color:#555b52}.suggestion:hover{border-color:#171916;transform:translateY(-2px)}.message{display:grid;grid-template-columns:38px minmax(0,1fr);gap:14px;margin-bottom:28px}.avatar{width:36px;height:36px;display:grid;place-items:center;border-radius:10px;background:#171916;color:white;font-size:13px}.message.user .avatar{background:#dfff56;color:#171916}.message-body{padding-top:5px;line-height:1.8;white-space:pre-wrap;word-break:break-word}.message-role{font-size:12px;font-weight:800;margin-bottom:6px}.typing{color:#747970}.composer-area{padding:16px max(28px,calc((100% - 820px)/2)) 24px}.composer{display:grid;grid-template-columns:1fr 46px;gap:10px;padding:10px 10px 10px 18px;border:1px solid #aaa99f;border-radius:18px;background:#fffdf6;box-shadow:0 10px 30px rgba(30,32,28,.08)}.composer:focus-within{border-color:#7054ef}.composer textarea{border:0;outline:0;resize:none;background:transparent;min-height:26px;max-height:130px;font:15px/1.65 inherit}.send-button{width:44px;height:44px;border:0;border-radius:13px;background:#171916;color:#dfff56;cursor:pointer;font-size:18px}.send-button:disabled{opacity:.35}.composer-hint{text-align:center;color:#888d84;font-size:10px;margin-top:9px}
    .home-view>.hero,.home-view>.section,.home-view>.ethics{display:none}
    .ollama-status{display:none!important}.process-box{margin-top:13px;border:1px solid #d7d5cb;border-radius:12px;background:#efede5;overflow:hidden;max-width:650px;transition:.18s}.process-box summary{padding:10px 13px;cursor:pointer;font-size:12px;font-weight:700;color:#62675e;list-style:none;display:flex;align-items:center;justify-content:space-between;gap:12px}.process-box summary::-webkit-details-marker{display:none}.process-box summary::before{content:'▸';margin-right:8px;color:#7054ef}.process-box[open] summary::before{content:'▾'}.process-box.live{border-color:#cfc9ff;box-shadow:0 10px 24px rgba(112,84,239,.08)}.process-box.live summary{background:linear-gradient(180deg,rgba(255,255,255,.38),rgba(255,255,255,0))}.process-box.compact{background:#f4f2eb;border-color:#ddd8c9;box-shadow:none}.process-box.compact summary{padding:9px 13px}.process-box.compact .process-inner{display:none}.process-summary{display:inline-flex;align-items:center;gap:8px;min-width:0}.process-toggle{margin-left:auto;padding:4px 8px;border:1px solid #d7d5cb;border-radius:999px;background:#fffdf6;color:#61665e;font:10px ui-monospace,monospace}.process-box.live .process-toggle{background:#f2eeff;border-color:#d4cbff;color:#5f46cf}.process-meta{color:#8a8f86;font:10px ui-monospace,monospace;white-space:nowrap}.process-inner{max-height:190px;overflow:auto;padding:0 14px 12px;border-top:1px solid #d7d5cb}.process-log{display:grid;gap:2px;padding:8px 0}.process-step{display:flex;gap:9px;align-items:flex-start;padding:7px 0;font-size:11px;color:#6f756c;line-height:1.55}.process-step i{width:7px;height:7px;flex:0 0 auto;margin-top:5px;border-radius:50%;background:#aaa}.process-step.done i{background:#62be55}.process-step.active i{background:#7054ef;box-shadow:0 0 0 4px rgba(112,84,239,.12)}.process-step.muted{opacity:.72}.process-step.error i{background:#ef6048}.references{padding-top:8px;border-top:1px dashed #d0cec4;font-size:11px;color:#777d73}.references a{color:#5f46cf;word-break:break-all}.typing .message-body{position:relative;min-height:1.8em}.typing.streaming .message-body::after{content:'';display:inline-block;width:9px;height:1.1em;margin-left:3px;vertical-align:-2px;border-radius:2px;background:#7054ef;animation:blinkCursor .9s steps(1,end) infinite}.typing.streaming.done .message-body::after{display:none}@keyframes blinkCursor{50%{opacity:0}}
    .chat-home{grid-template-columns:260px minmax(0,1fr) 290px}.source-panel{border-left:1px solid #d6d4ca;background:#ebe9e0;padding:22px 16px;overflow-y:auto}.source-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.source-head h2{margin:0;font-size:14px}.source-count{min-width:24px;height:24px;padding:0 7px;display:grid;place-items:center;border-radius:99px;background:#171916;color:#dfff56;font:11px monospace}.source-empty{margin-top:70px;text-align:center;color:#7a7f76;font-size:12px;line-height:1.7}.source-empty i{width:45px;height:45px;margin:0 auto 14px;display:grid;place-items:center;border:1px solid #c8c6bc;border-radius:14px;font-size:19px;font-style:normal}.source-card{display:block;margin-bottom:10px;padding:14px;border:1px solid #d3d1c7;border-radius:12px;background:#fffdf6;text-decoration:none;transition:.18s}.source-card:hover{border-color:#171916;transform:translateY(-2px)}.source-type{display:inline-block;margin-bottom:8px;padding:4px 7px;border-radius:99px;background:#eeeaff;color:#6045d4;font:10px monospace}.source-card strong{display:block;font-size:13px;line-height:1.45}.source-card small{display:block;margin-top:7px;color:#858a81;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.source-note{margin-top:16px;padding:12px;border-top:1px solid #d1cfc5;color:#858a81;font-size:10px;line-height:1.6}
    .model-settings{margin-bottom:14px;border:1px solid #d1cfc5;border-radius:12px;background:#fffdf6;overflow:hidden}.model-settings summary{padding:12px;cursor:pointer;font-size:12px;font-weight:800}.model-settings label{display:block;padding:0 12px 11px;color:#73786f;font-size:11px}.model-settings textarea,.model-settings select{width:100%;margin-top:6px;padding:9px;border:1px solid #d2d0c6;border-radius:8px;background:white;font:12px/1.5 inherit;resize:vertical}.model-settings button,.attachment-box>button{width:calc(100% - 24px);margin:0 12px 12px;padding:9px;border:0;border-radius:8px;background:#171916;color:white;font-size:11px;font-weight:700;cursor:pointer}.attachment-box{margin-bottom:18px;padding:12px 0;border:1px dashed #bbb9ae;border-radius:12px}.attachment-box>button{background:#7054ef}.attachment-box small{display:block;padding:0 12px;color:#858a81;font-size:9px}.file-chip{display:flex;justify-content:space-between;gap:8px;margin:0 12px 7px;padding:7px 9px;border-radius:7px;background:#fffdf6;font-size:10px}.file-chip button{border:0;background:transparent;color:#ef6048;cursor:pointer}
    .composer{grid-template-columns:38px 1fr 46px;padding-left:10px}.composer-attach{width:36px;height:36px;align-self:center;border:0;border-radius:10px;background:#efede5;color:#5f655c;cursor:pointer;font-size:17px}.composer-attach:hover{background:#e4e0ff;color:#6045d4}.composer-files{display:none;margin-bottom:8px;padding:8px 10px;border:1px solid #d6d4ca;border-radius:12px;background:#ebe9e0}.composer-files.active{display:block}.composer-files-head{display:flex;justify-content:space-between;margin:0 3px 7px;color:#696f66;font-size:10px}.composer-files .file-chip{display:inline-flex;margin:3px;padding:6px 8px;border:1px solid #d4d1c8}.attachment-box{display:none}
    .composer{grid-template-columns:38px minmax(0,1fr) 46px!important;padding-left:10px;align-items:end}.composer-attach{width:36px;height:36px;align-self:center;border:0;border-right:1px solid #d8d5cc;border-radius:0;background:transparent;color:#5f655c;cursor:pointer;font-size:26px;font-weight:300;line-height:1}.composer-attach:hover{background:transparent;color:#6045d4}.composer textarea{width:100%;min-width:0}
    .ai-mark{width:172px;height:172px;background:transparent;box-shadow:none;border-radius:34px;overflow:hidden}.ai-mark img{display:block;width:100%;height:100%;object-fit:cover;border-radius:34px}#historyTitle{display:none}.history-list{display:grid;gap:6px;margin-top:8px;max-height:42vh;overflow:auto}.history-list .history-item{width:100%;text-align:left;cursor:pointer}.history-list .history-item.active{border-color:#171916;box-shadow:4px 4px 0 #dfff56;font-weight:700}.history-db-status{padding:8px;color:#858a81;font-size:10px}
    @media(max-width:1100px){.chat-home{grid-template-columns:220px minmax(0,1fr) 250px}}
    @media(max-width:900px){.chat-home{grid-template-columns:220px minmax(0,1fr)}.source-panel{display:none}}
    @media(max-width:800px){.nav-links{display:none}.hero,.head,.theory,.ethics{grid-template-columns:1fr}.hero-art{max-width:430px;width:100%;margin:auto}.steps{grid-template-columns:1fr 1fr}.topics{grid-template-columns:1fr}.head p{justify-self:start}.ethics{gap:15px}}
    @media(max-width:800px){.portfolio-layout{grid-template-columns:1fr}.side-menu{position:static}.project-list{display:flex;overflow:auto}.project-button{min-width:190px}.feature-grid{grid-template-columns:1fr}}
    @media(max-width:800px){.chat-home{grid-template-columns:1fr}.chat-sidebar{display:none}.chat-toolbar{padding:0 15px}.messages,.composer-area{padding-left:16px;padding-right:16px}.suggestions{grid-template-columns:1fr}.ollama-status span{display:none}}
    @media(max-width:520px){.steps{grid-template-columns:1fr}.step{border-right:0;border-bottom:1px solid #41453f;min-height:auto}.flow{padding:20px 6px}.node{width:74px;height:74px}.hero h1{font-size:43px}}
    /* Responsive layout hardening */
    img,svg,canvas,video{max-width:100%}
    .site-nav,.chat-home,.chat-main,.messages,.composer-area,.portfolio-layout,.project-document,.document-body,.project-lab,.compare-panel,.plan-card{min-width:0}
    .site-nav{gap:14px}
    .brand,.main-menu,.health-wrap{min-width:0}
    .brand{white-space:nowrap}
    .main-menu{flex:0 0 auto}
    .health-button{white-space:nowrap}
    .chat-home{height:calc(100dvh - 68px);min-height:0}
    .chat-main{min-height:0;max-height:calc(100dvh - 68px)}
    .messages{min-height:0}
    .empty-chat{padding:24px 0}
    .empty-chat h1,.portfolio-hero h1,.document-head h2{letter-spacing:0}
    .ai-mark{width:clamp(112px,14vw,172px);height:clamp(112px,14vw,172px)}
    .suggestion,.message-body,.process-step,.source-card strong,.source-card small,.project-button,.feature,.compare-item,.compare-answer pre,.chunk-detail pre,.compare-chunk pre{overflow-wrap:anywhere}
    .process-box{max-width:100%}
    .composer-area{padding-bottom:max(20px,env(safe-area-inset-bottom))}
    .portfolio-layout{width:min(1120px,100%)}
    .project-list{min-width:0}
    .project-button{width:100%}
    .code-wrap pre,.compare-body,.plan-body{min-width:0}
    .compare-grid-head,.plan-head,.compare-item-head{flex-wrap:wrap}
    .compare-grid-head{gap:8px}
    .compare-grid-head p{max-width:100%;line-height:1.6}
    .chunking-controls{grid-template-columns:minmax(220px,1fr) minmax(170px,220px) minmax(118px,150px)}
    .chunking-controls select,.chunking-controls input,.chunking-controls textarea,.document-input textarea,.result-snippets{min-width:0}
    .chunking-doc-grid{grid-template-columns:minmax(190px,240px) minmax(0,1fr)}
    .strategy-grid{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
    .compare-stats{grid-template-columns:repeat(auto-fit,minmax(110px,1fr))}
    .compare-score{white-space:normal;text-align:center}
    footer{gap:14px}
    @media(max-width:1100px){
      .site-nav{padding-inline:18px}
      .portfolio-layout{gap:24px}
      .document-head,.document-body{padding:32px}
    }
    @media(max-width:900px){
      .chat-home{height:calc(100dvh - 68px)}
      .chat-main{max-height:calc(100dvh - 68px)}
      .empty-chat h1{font-size:32px}
      .source-panel{display:none}
      .portfolio-hero{padding:46px 20px 32px}
      .portfolio-layout{padding:28px 20px 72px}
      .side-menu{position:static}
      .project-list{display:flex;gap:10px;overflow-x:auto;padding:2px 0 10px;scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
      .project-button{flex:0 0 min(240px,78vw);scroll-snap-align:start}
      .chunking-doc-grid,.chunking-controls,.pros-cons{grid-template-columns:1fr}
      .plan-head{display:grid;grid-template-columns:1fr}
    }
    @media(max-width:800px){
      .chat-home{height:auto;min-height:calc(100dvh - 68px)}
      .chat-main{min-height:calc(100dvh - 68px);max-height:none}
      .chat-toolbar{height:auto;min-height:58px;padding:10px 16px}
      .model-wrap,.model-select{width:100%;min-width:0}
      .messages{padding-top:24px;padding-bottom:18px}
      .empty-chat{place-content:start center}
      .ai-mark{width:108px;height:108px;margin-bottom:18px;border-radius:24px}
      .ai-mark img{border-radius:24px}
      .suggestions{margin-top:22px}
      .composer{grid-template-columns:36px minmax(0,1fr) 42px!important;gap:8px;border-radius:16px}
      .send-button{width:40px;height:40px}
      .composer-files-head{display:grid;gap:3px}
      .portfolio-hero h1{font-size:36px;line-height:1.15}
      .project-document{border-radius:16px}
      .document-head,.document-body{padding:22px}
      .document-head h2{font-size:28px;line-height:1.22}
      .compare-body,.compare-head,.plan-body,.plan-head{padding:14px}
      .chunk-list{max-height:48vh}
      footer{flex-direction:column;padding:24px 20px}
    }
    @media(max-width:640px){
      .site-nav{height:auto;min-height:68px;padding:10px 14px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"brand health" "menu menu";align-items:center}
      .brand{grid-area:brand;overflow:hidden;text-overflow:ellipsis}
      .main-menu{grid-area:menu;width:100%;justify-content:center}
      .main-menu a{flex:1;text-align:center;padding:9px 10px}
      .health-wrap{grid-area:health}
      .health-button{padding:9px 10px}
      .health-button #healthLabel{display:none}
      .health-popover{position:fixed;top:74px;left:14px;right:14px;width:auto}
      .chat-home{min-height:calc(100dvh - 116px)}
      .chat-main{min-height:calc(100dvh - 116px)}
      .empty-chat h1{font-size:29px;line-height:1.18}
      .empty-chat p{font-size:14px;line-height:1.65}
      .message{grid-template-columns:32px minmax(0,1fr);gap:10px;margin-bottom:22px}
      .avatar{width:32px;height:32px}
      .process-box summary{align-items:flex-start;flex-wrap:wrap}
      .process-meta{width:100%}
      .portfolio-layout{padding-inline:14px}
      .portfolio-hero{padding-inline:14px}
      .document-head,.document-body{padding:18px}
      .feature{padding:14px}
      pre{padding:16px;font-size:12px}
      .plan-actions{display:grid;grid-template-columns:1fr}
      .plan-actions button,.chunking-run{width:100%}
      .compare-badge{max-width:100%;white-space:normal}
      .result-snippets{height:10em}
    }
    @media(max-width:420px){
      .site-nav{padding-inline:10px}
      .brand{font-size:14px}
      .brand i{width:28px;height:28px;font-size:13px}
      .main-menu a{font-size:12px}
      .chat-toolbar,.messages,.composer-area{padding-left:12px;padding-right:12px}
      .empty-chat h1{font-size:26px}
      .suggestion{padding:13px}
      .composer{padding:8px}
      .portfolio-hero h1{font-size:32px}
      .project-button{flex-basis:82vw}
      .document-head h2{font-size:25px}
      .compare-stats{grid-template-columns:1fr 1fr}
    }
    /* Mobile drawer navigation */
    .mobile-panel-toggle,.drawer-backdrop{display:none}
    .mobile-panel-toggle{align-items:center;gap:8px;min-height:40px;padding:0 13px;border:1px solid #171916;border-radius:12px;background:#171916;color:#dfff56;font-size:12px;font-weight:800;box-shadow:4px 4px 0 #dfff56;cursor:pointer}
    .mobile-panel-toggle::before{content:"☰";font-size:15px;line-height:1}
    .drawer-backdrop{position:fixed;inset:0;z-index:35;border:0;background:rgba(23,25,22,.38);backdrop-filter:blur(2px)}
    body.chat-drawer-open .drawer-backdrop,body.project-drawer-open .drawer-backdrop{display:block}
    @media(max-width:960px){
      .chat-home{position:relative;grid-template-columns:1fr!important}
      .chat-drawer-toggle{display:inline-flex;position:fixed;left:14px;bottom:max(88px,calc(env(safe-area-inset-bottom) + 84px));z-index:32}
      .chat-sidebar{display:flex!important;position:fixed;z-index:45;left:0;top:0;bottom:0;width:min(320px,86vw);padding:24px 16px max(24px,env(safe-area-inset-bottom));border-right:1px solid #d6d4ca;box-shadow:20px 0 45px rgba(23,25,22,.18);transform:translateX(-104%);transition:transform .22s ease;overflow-y:auto}
      body.chat-drawer-open .chat-sidebar{transform:translateX(0)}
      .source-panel{display:none!important}
      .history-list{max-height:none;overflow:visible}
    }
    @media(max-width:960px) and (orientation:landscape){
      .chat-drawer-toggle{bottom:max(18px,env(safe-area-inset-bottom));left:14px}
      .chat-sidebar{width:min(300px,45vw)}
    }
    @media(max-width:960px){
      .portfolio-layout{display:block;max-width:none;width:100%;padding:20px clamp(12px,4vw,24px) 72px}
      .project-drawer-toggle{display:inline-flex;position:sticky;top:82px;z-index:8;margin:0 0 14px}
      .side-menu{display:flex!important;position:fixed!important;z-index:45;left:0;top:0;bottom:0;width:min(330px,88vw);padding:24px 16px max(24px,env(safe-area-inset-bottom));border-right:1px solid #d6d4ca;background:#ebe9e0;box-shadow:20px 0 45px rgba(23,25,22,.18);transform:translateX(-104%);transition:transform .22s ease;overflow-y:auto;flex-direction:column;gap:12px}
      body.project-drawer-open .side-menu{transform:translateX(0)}
      .side-menu .kicker{margin:0 0 4px}
      .project-list{display:grid!important;grid-template-columns:1fr;gap:8px;overflow:visible!important;padding:0!important;scroll-snap-type:none!important}
      .project-button{flex:none!important;min-width:0!important;width:100%;padding:13px 14px}
      .project-button.active{box-shadow:3px 3px 0 #dfff56}
      .project-document{width:100%;border-radius:16px}
      .document-head,.document-body{padding:clamp(18px,5vw,28px)}
    }
    @media(max-width:960px) and (orientation:landscape){
      .portfolio-hero{padding-top:28px;padding-bottom:22px}
      .project-drawer-toggle{top:76px}
      .side-menu{width:min(310px,44vw)}
    }
    @media(min-width:961px){
      body.project-drawer-open .drawer-backdrop{display:none}
    }
    @media(min-width:961px){
      body.chat-drawer-open .drawer-backdrop{display:none}
    }
    .chunking-stream-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.chunking-stop-all,.compare-stop,.compare-retry{min-height:34px;padding:0 11px;border:1px solid #d5d1c5;border-radius:10px;background:#fffdf6;color:#343832;font-weight:800;cursor:pointer}.chunking-stop-all{border-color:#b9543e;color:#a4402c}.chunking-stop-all:disabled{opacity:.4;cursor:not-allowed}
    .stream-panel{position:relative}.stream-panel.is-streaming{border-color:#c9c0ff;box-shadow:0 12px 28px rgba(95,70,207,.1)}.stream-panel.is-done .stream-process{max-height:42px;overflow:hidden;background:#f4f2eb}.stream-panel.is-done .stream-process-log{display:none}.stream-process{margin-top:12px;padding:10px 12px;border:1px solid #e2ded1;border-radius:12px;background:#fff;transition:.2s}.stream-process-head{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;font-weight:800}.stream-process-log{display:grid;gap:5px;margin-top:9px}.stream-step{display:flex;gap:7px;color:#737970;font-size:11px}.stream-step::before{content:'○';color:#aaa}.stream-step.done::before{content:'●';color:#64b854}.stream-step.active::before{content:'●';color:#7054ef}.stream-step.error::before{content:'●';color:#df6048}
    .stream-answer{position:relative;min-height:110px;max-height:430px;overflow:auto;overscroll-behavior:contain}.stream-answer.is-following{scroll-behavior:smooth}.stream-answer-output{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.75 inherit;color:#eff3e9}.stream-answer.is-streaming .stream-answer-output::after{content:'▋';margin-left:3px;color:#dfff56;animation:blinkCursor .9s steps(1,end) infinite}.stream-answer-paused{display:none;position:sticky;bottom:4px;margin:8px auto 0;width:max-content;padding:4px 9px;border-radius:99px;background:#fff;color:#5d46cc;font-size:10px}.stream-answer.user-paused .stream-answer-paused{display:block}.stream-markdown h1,.stream-markdown h2,.stream-markdown h3{margin:1em 0 .45em;color:#fff}.stream-markdown p{margin:.65em 0}.stream-markdown ul,.stream-markdown ol{padding-left:22px}.stream-markdown code{padding:2px 5px;border-radius:5px;background:#30342f}.stream-markdown pre{padding:12px;border-radius:10px;background:#0d0f0d;overflow:auto}.stream-markdown blockquote{margin:10px 0;padding-left:12px;border-left:3px solid #dfff56;color:#d5d9d1}
    .stream-actions{display:flex;gap:7px;margin-top:10px}.stream-live-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.stream-sources{margin-top:12px}.stream-sources summary{cursor:pointer;color:#686e65;font-size:12px;font-weight:800}.stream-sources-list{display:grid;gap:8px;margin-top:9px}.stream-source{padding:10px;border:1px solid #e1ddd1;border-radius:10px;background:#fff;font-size:11px;color:#5f655c}.stream-source b{display:block;margin-bottom:4px}.stream-source p{margin:0;line-height:1.5}.stream-error-note{margin-top:10px;color:#bd4c35;font-size:12px}.stream-panel.is-stopped .compare-answer{background:#4b4536}
    @media(max-width:900px){.stream-answer{max-height:360px}}
    .send-button.is-stop{background:#b84e38;color:#fff}.chat-retry{margin-top:10px;padding:7px 11px;border:1px solid #cfcac0;border-radius:9px;background:#fffdf6;color:#6045d4;font-weight:800;cursor:pointer}.message-markdown{white-space:normal}.message-markdown p{margin:.6em 0}.message-markdown h1,.message-markdown h2,.message-markdown h3{margin:1em 0 .4em;line-height:1.35}.message-markdown ul,.message-markdown ol{padding-left:22px}.message-markdown code{padding:2px 5px;border-radius:5px;background:#e9e6dc}.message-markdown pre{padding:12px;border-radius:10px;background:#171916;color:#f0f3ed;overflow:auto;white-space:pre-wrap}.message-markdown blockquote{margin:10px 0;padding-left:12px;border-left:3px solid #7054ef;color:#666c63}.chat-follow-paused{position:sticky;bottom:8px;width:max-content;margin:0 auto;padding:5px 10px;border:1px solid #d6d0ff;border-radius:99px;background:#fff;color:#6045d4;font-size:10px;font-weight:800;cursor:pointer;z-index:2}
    .message.typing.streaming .message-body{min-height:12.6em;max-height:14.4em;overflow-y:auto;overscroll-behavior:contain;padding-right:8px;scrollbar-width:thin}.process-box.live.stream-compact{margin-top:8px;box-shadow:none;background:#f4f2eb}.process-box.live.stream-compact summary{padding:8px 11px}.process-box.live.stream-compact[open] .process-inner{max-height:112px;padding-bottom:8px}.process-box.live.stream-compact .process-step{padding:4px 0}.process-box.live.stream-compact .process-log{padding:5px 0}@media(max-width:640px){.message.typing.streaming .message-body{min-height:10.8em;max-height:12.6em}.process-box.live.stream-compact[open] .process-inner{max-height:88px}}
    .composer-area>.process-box.composer-docked{width:100%;max-width:none;margin:0 0 9px;border-color:#cfc9ff;background:#f6f3ff;box-shadow:0 6px 18px rgba(112,84,239,.08)}.composer-area>.process-box.composer-docked summary{padding:7px 11px;cursor:default}.composer-area>.process-box.composer-docked summary::before{content:'●';font-size:8px}.composer-area>.process-box.composer-docked .process-toggle{display:none}.composer-area>.process-box.composer-docked .process-inner{display:block;max-height:92px;padding:0 10px 7px;overflow:auto}.composer-area>.process-box.composer-docked .process-log{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 14px;padding:4px 0}.composer-area>.process-box.composer-docked .process-step{padding:3px 0;font-size:10px;line-height:1.4}.composer-area>.process-box.composer-docked .references{padding-top:4px;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}@media(max-width:640px){.composer-area>.process-box.composer-docked .process-inner{max-height:82px}.composer-area>.process-box.composer-docked .process-log{grid-template-columns:1fr}.composer-area>.process-box.composer-docked .process-step:nth-child(n+4){display:none}}
    .composer-area{width:100%;min-width:0}.composer{display:flex!important;width:100%;min-width:0;align-items:flex-end}.composer>.composer-attach{flex:0 0 36px}.composer>textarea{flex:1 1 0;width:0!important;min-width:72px!important}.composer>.send-button{flex:0 0 44px}@media(max-width:640px){.composer>textarea{min-width:56px!important}.composer>.send-button{flex-basis:40px}}
  </style>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
</head>
<body>
  <main class="shell"><section class="card">
    <nav class="site-nav"><div class="brand"><i>M</i> MinsLab</div><div class="main-menu"><a href="/" data-page="home">홈</a><a href="/portfolio" data-page="portfolio">포트폴리오</a><a href="/poc" data-page="poc">PoC</a></div><div class="health-wrap" id="healthWrap"><div class="health-button" tabindex="0"><span class="health-dot"></span><span id="healthLabel">서버 확인 중</span></div><div class="health-popover"><h3>서비스 세부 상태</h3><div class="health-stats" id="healthStats"></div><div id="healthDetails"></div><small class="health-updated" id="healthUpdated">확인 중...</small></div></div></nav>
    <div class="home-view">
    <section class="chat-home">
      <button class="mobile-panel-toggle chat-drawer-toggle" id="chatDrawerToggle" type="button" aria-controls="chatSidebar" aria-expanded="false"><span>대화 이력</span></button>
      <aside class="chat-sidebar" id="chatSidebar"><button class="new-chat" id="newChat"><span>＋ 새 대화</span><span>⌘ K</span></button><div><div class="chat-history-label">TODAY</div><div class="history-item" id="historyTitle">새로운 대화</div></div><div class="chat-sidebar-note">MinsLab<br>오늘의 기록으로 내일의 가능성을 실험하는 곳</div></aside>
      <div class="chat-main"><header class="chat-toolbar"><div class="model-wrap"><select class="model-select" id="modelSelect" aria-label="AI 모델 선택"><option>모델 불러오는 중...</option></select></div><div class="ollama-status" id="ollamaStatus"><i></i><span>OLLAMA CONNECTED</span></div></header><div class="messages" id="messages"><div class="empty-chat" id="emptyChat"><div><div class="ai-mark">✦</div><h1>MinsLab</h1><p>오늘의 기록으로 내일의 가능성을 실험하는 곳</p><div class="suggestions"><button class="suggestion">Python 함수와 클래스의 차이를 설명해줘</button><button class="suggestion">오늘 배울 AI 개념 하나를 추천해줘</button><button class="suggestion">REST API 예제 코드를 만들어줘</button><button class="suggestion">내 코드의 오류를 같이 찾아줘</button></div></div></div></div><div class="composer-area"><form class="composer" id="chatForm"><textarea id="chatInput" rows="1" placeholder="메시지를 입력하세요..." aria-label="메시지"></textarea><button class="send-button" id="sendButton" type="submit" aria-label="보내기">↑</button></form><div class="composer-hint">AI는 실수할 수 있습니다. 중요한 정보는 한 번 더 확인하세요.</div></div></div>
      <aside class="source-panel" id="sourcePanel"><details class="model-settings"><summary>⚙ 모델별 설정</summary><label>시스템 프롬프트<textarea id="systemPrompt" rows="5"></textarea></label><label>최대 출력 토큰<select id="maxTokens"><option value="128">128 · 빠름</option><option value="256" selected>256 · 권장</option><option value="512">512 · 상세</option><option value="1024">1024 · 느림</option></select></label><button id="saveSettings" type="button">이 모델 설정 저장</button></details><div class="attachment-box"><input type="file" id="fileInput" multiple accept=".txt,.md,.csv,.json,.py,.js,.html,.css,.yaml,.yml,.log" hidden><button id="attachButton" type="button">＋ 분석 자료 첨부</button><div id="attachedFiles"></div><small>텍스트·코드 파일, 파일당 최대 5MB · 총 15MB</small></div><div class="source-head"><h2>사용한 자료</h2><span class="source-count" id="sourceCount">0</span></div><div id="sourceList"><div class="source-empty"><i>⌕</i><strong>아직 사용한 자료가 없어요</strong><br>웹 검색 또는 RAG 문서가 사용되면<br>이곳에 출처가 표시됩니다.</div></div><div class="source-note">출처는 응답에 실제로 연결된 웹 URL과 RAG 메타데이터만 표시합니다.</div></aside>
    </section>
    <header class="hero"><div><div class="kicker">MinsLab / LEARNING ARCHIVE</div><h1>오늘의 기록으로<br><span class="marker">내일의 가능성을 실험합니다.</span></h1><p>배운 것, 만든 것, 실패하며 고친 것을 차곡차곡 남기는 개인 AI 실험실입니다. 로컬 AI, RAG, Python 실습을 실제로 만져볼 수 있는 기록으로 정리합니다.</p><div class="actions"><a class="button primary" href="/portfolio" data-page="portfolio">실험 기록 보기 ↓</a><a class="button secondary" href="#concept">AI 개념 살펴보기</a></div></div><div class="hero-art"><div class="orbit"></div><div class="brain">M</div></div></header>
    <section class="section" id="concept"><div class="head"><div><span class="kicker">01 / THE BIG IDEA</span><h2>AI를 움직이는<br>네 가지 재료</h2></div><p>AI는 데이터에서 반복되는 관계를 찾아 내부의 숫자들을 조절합니다. 버튼을 눌러 각 요소의 역할을 확인해 보세요.</p></div><div class="tabs"><button class="tab active" data-key="data">데이터</button><button class="tab" data-key="model">모델</button><button class="tab" data-key="learn">학습</button><button class="tab" data-key="infer">추론</button></div><article class="theory"><div class="theory-copy"><span class="kicker" id="tag">INGREDIENT 01</span><h2 id="title">경험을 숫자로 바꾼 데이터</h2><p id="desc">사진, 문장, 소리처럼 세상에서 수집한 사례를 컴퓨터가 읽을 수 있는 숫자로 표현합니다. 데이터의 다양성과 품질은 AI가 바라보는 세계의 경계를 결정합니다.</p></div><div class="flow"><div class="node"><div><b>01</b>현실 세계</div></div>→<div class="node"><div><b>0·1</b>숫자 표현</div></div>→<div class="node"><div><b>∞</b>패턴</div></div></div></article></section>
    <section class="section dark" id="learn"><div class="head"><div><span class="kicker">02 / HOW IT LEARNS</span><h2>정답에 가까워지는<br>반복의 기술</h2></div><p>예측하고, 틀린 정도를 계산하고, 아주 조금 수정하는 일을 수백만 번 반복합니다.</p></div><div class="steps"><article class="step"><em>STEP 01</em><h3>입력과 예측</h3><p>데이터가 여러 층을 통과하며 예측값으로 변환됩니다. 처음의 예측은 무작위에 가깝습니다.</p></article><article class="step"><em>STEP 02</em><h3>오차 측정</h3><p>예측과 정답의 차이를 손실 함수로 계산합니다. 숫자가 작을수록 더 좋은 예측입니다.</p></article><article class="step"><em>STEP 03</em><h3>역전파</h3><p>오차의 책임을 각 연결에 나눠 전달합니다. 미분은 수정 방향을 알려주는 나침반입니다.</p></article><article class="step"><em>STEP 04</em><h3>가중치 갱신</h3><p>연결의 세기를 조금 바꿔 다시 예측합니다. 반복 속에서 모델만의 규칙이 생깁니다.</p></article></div></section>
    <section class="section" id="topics"><div class="head"><div><span class="kicker">03 / THE TOOLKIT</span><h2>오늘의 AI를 만든<br>세 가지 전환점</h2></div><p>아이디어가 쌓이며 AI는 보는 기계에서 언어를 이해하고 새로운 것을 만드는 시스템으로 확장됐습니다.</p></div><div class="topics"><article class="topic"><span>NEURAL NETWORK</span><h3>신경망</h3><p>작은 계산 단위를 여러 층으로 연결해 단순한 특징에서 복잡한 개념까지 단계적으로 추출합니다.</p></article><article class="topic"><span>ATTENTION</span><h3>트랜스포머</h3><p>모든 단어의 관계를 동시에 살피는 어텐션으로 긴 맥락과 의미를 효과적으로 이해합니다.</p></article><article class="topic"><span>GENERATION</span><h3>생성형 AI</h3><p>학습한 확률 분포에서 다음 토큰이나 픽셀을 예측해 전에 없던 문장과 이미지를 만듭니다.</p></article></div></section>
    <section class="ethics" id="ethics"><div><span class="kicker" style="color:#dfff56">04 / HUMAN IN THE LOOP</span><h2>똑똑함보다<br>중요한 질문</h2><p>AI의 결과는 데이터와 설계자의 선택을 반영합니다. 성능뿐 아니라 누구에게 어떤 영향을 주는지도 함께 살펴야 합니다.</p></div><div class="checks"><div><b>✓</b> 편향: 데이터에서 누가 빠져 있는가?</div><div><b>✓</b> 검증: 그럴듯한 답은 사실인가?</div><div><b>✓</b> 책임: 최종 결정을 사람이 책임지는가?</div></div></section>
    </div>
    <div class="portfolio-view">
      <header class="portfolio-hero"><span class="kicker" id="archiveKicker">MinsLab / LEARNING ARCHIVE</span><h1 id="archiveTitle">오늘의 기록으로<br>내일의 가능성을 실험합니다.</h1><p id="archiveDescription">교육과 실습에서 만든 Python, Local AI, RAG 프로젝트를 실행 방법과 배운 점까지 함께 정리하는 성장형 포트폴리오입니다.</p></header>
      <div class="portfolio-layout">
        <button class="mobile-panel-toggle project-drawer-toggle" id="projectDrawerToggle" type="button" aria-controls="projectSideMenu" aria-expanded="false"><span id="projectDrawerLabel">프로젝트</span></button>
        <aside class="side-menu" id="projectSideMenu"><h2 class="kicker" id="projectIndexTitle">PROJECT INDEX</h2><div class="project-list" id="projectList"></div></aside>
        <article class="project-document"><header class="document-head"><div class="project-meta" id="projectMeta"></div><h2 id="projectTitle"></h2><p id="projectSummary"></p></header><div class="document-body"><div class="project-default" id="projectDefaultView"><h3>프로젝트 설명</h3><p id="projectDescription"></p><div class="feature-grid" id="projectFeatures"></div><h3>핵심 코드</h3><div class="code-wrap"><div class="code-head"><span id="codeFile">main.py</span><button class="copy-code" id="copyCode">코드 복사</button></div><pre><code id="projectCode"></code></pre></div><h3>실행 방법</h3><ol id="projectUsage"></ol><div class="next-note" id="projectNote"></div></div><section class="project-lab" id="projectLab"></section></div></article>
      </div>
    </div>
    <footer><span>MinsLab · 오늘의 기록으로 내일의 가능성을 실험하는 곳</span><a href="/admin">ADMIN ↗</a></footer>
    <button class="drawer-backdrop" id="drawerBackdrop" type="button" aria-label="메뉴 닫기"></button>
  </section></main>
  <script>
    const info={data:['INGREDIENT 01','경험을 숫자로 바꾼 데이터','사진, 문장, 소리처럼 세상에서 수집한 사례를 컴퓨터가 읽을 수 있는 숫자로 표현합니다. 데이터의 다양성과 품질은 AI가 바라보는 세계의 경계를 결정합니다.'],model:['INGREDIENT 02','패턴을 담는 계산 구조','모델은 입력을 출력으로 바꾸는 거대한 수학 함수입니다. 수많은 가중치가 어떤 특징에 주목하고 어떻게 조합할지 기억합니다.'],learn:['INGREDIENT 03','실수에서 규칙을 찾는 학습','예측과 정답 사이의 오차를 구하고, 오차가 줄어드는 방향으로 가중치를 조금씩 수정합니다. 이 반복이 기계가 경험을 쌓는 방식입니다.'],infer:['INGREDIENT 04','배운 것을 적용하는 추론','새로운 입력이 들어오면 저장된 패턴으로 가장 가능성 높은 결과를 계산합니다. 챗봇의 답변도 다음 단어를 연속해서 추론한 결과입니다.']};
    document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelector('.tab.active').classList.remove('active');b.classList.add('active');const x=info[b.dataset.key];tag.textContent=x[0];title.textContent=x[1];desc.textContent=x[2]});

    // 파일 기반 */project.json 로딩이 실패하면 빈 상태를 유지합니다.
    const fallbackProjects=[];
    const fallbackPocProjects=[];

    const loadedProjects=__PROJECTS_JSON__;
    const loadedPocProjects=__POC_PROJECTS_JSON__;
    const catalogs={
      portfolio:{path:'/portfolio',kicker:'MinsLab / LEARNING ARCHIVE',title:'오늘의 기록으로<br>내일의 가능성을 실험합니다.',description:'교육과 실습에서 만든 Python, Local AI, RAG 프로젝트를 실행 방법과 배운 점까지 함께 정리하는 성장형 포트폴리오입니다.',indexLabel:'PROJECT INDEX',drawerLabel:'프로젝트',projects:loadedProjects.length?loadedProjects:fallbackProjects},
      poc:{path:'/poc',kicker:'MinsLab / PROOF OF CONCEPT',title:'개인 PoC로<br>아이디어를 검증합니다.',description:'개인적으로 만든 프로그램과 실험형 도구를 같은 형식으로 정리합니다. 문제의식, 핵심 코드, 실행 방법을 함께 남겨 다음 실험으로 이어갑니다.',indexLabel:'POC INDEX',drawerLabel:'PoC',projects:loadedPocProjects.length?loadedPocProjects:fallbackPocProjects}
    };

    async function readJsonResponse(response){
      const text=await response.text();
      try{return JSON.parse(text)}catch(e){throw new Error(text.trim().slice(0,220)||`HTTP ${response.status} 응답을 해석하지 못했습니다.`)}
    }

    let chunkingModelRefreshTimer=null;
    function escapeModelHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
    function fallbackChunkingModels(){return {models:[{value:'openrouter:openai/gpt-4o-mini',label:'OpenRouter · openai/gpt-4o-mini',details:{}}],default:'openrouter:openai/gpt-4o-mini'}}
    function setChunkingModelOptions(selectEl,data,previousValue=''){const fallback=fallbackChunkingModels();const models=(data.models||[]).length?data.models:fallback.models;const defaultValue=data.default||fallback.default;selectEl.innerHTML=models.map(item=>`<option value="${escapeModelHtml(item.value)}">${escapeModelHtml(item.label)}${item.details?.parameter_size?' · '+escapeModelHtml(item.details.parameter_size):''}</option>`).join('');const values=[...selectEl.options].map(option=>option.value);const preferred=values.includes(previousValue)?previousValue:(values.includes(defaultValue)?defaultValue:values[0]);if(preferred)selectEl.value=preferred}
    async function loadChunkingModels(selectEl){if(!selectEl)return;const previousValue=selectEl.value;try{const r=await fetch('/api/chunking-models',{cache:'no-store'});const data=await readJsonResponse(r);if(!r.ok)throw new Error(data.error||'모델 목록을 불러오지 못했습니다.');setChunkingModelOptions(selectEl,data,previousValue);selectEl.title=''}catch(e){setChunkingModelOptions(selectEl,fallbackChunkingModels(),previousValue);selectEl.title=`모델 목록 조회 실패: ${e.message}`}}
    function startChunkingModelAutoRefresh(selectEl){if(chunkingModelRefreshTimer)clearInterval(chunkingModelRefreshTimer);loadChunkingModels(selectEl);chunkingModelRefreshTimer=setInterval(()=>{if(!document.body.contains(selectEl)){clearInterval(chunkingModelRefreshTimer);chunkingModelRefreshTimer=null;return;}loadChunkingModels(selectEl)},15000)}

    function renderLegacyChunkingLab(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="chunking-shell"><div class="compare-grid-head"><h3>청킹 비교 시뮬레이션</h3><p>같은 프롬프트를 두 테이블에 각각 적용해 검색 결과를 나란히 비교합니다.</p></div><div class="chunking-controls"><label>프롬프트 입력<textarea id="legacyChunkingPromptInput" placeholder="질문이나 비교할 요청을 입력하세요.">민원 처리 법에 대해 알려줘</textarea></label><label>모델 선택<select id="legacyChunkingModelSelect"><option value="openai/gpt-4o-mini" selected>openai/gpt-4o-mini</option><option value="llama3.2:1b">llama3.2:1b · local Ollama</option></select></label><button class="chunking-run" id="legacyChunkingRunButton" type="button">비교 실행</button></div><div class="chunking-note">RAG Supabase 비교 대상 · 왼쪽은 <b>documents</b>, 오른쪽은 <b>documents_test</b> 테이블을 사용합니다. 모델은 OpenRouter의 openai/gpt-4o-mini 또는 로컬 Ollama의 llama3.2:1b 중에서 선택할 수 있으며, 검색된 문맥을 바탕으로 실제 답변을 호출합니다.</div><div class="chunking-compare" id="legacyChunkingCompare"><article class="compare-panel" data-panel="documents"><div class="compare-head"><strong>일반 청킹</strong><small>documents</small><div class="compare-meta"><span class="compare-badge">대기 중</span></div></div><div class="compare-body"><div class="compare-empty">프롬프트를 입력하고 비교 실행을 눌러주세요.</div></div></article><article class="compare-panel" data-panel="documents_test"><div class="compare-head"><strong>전처리 청킹</strong><small>documents_test</small><div class="compare-meta"><span class="compare-badge">대기 중</span></div></div><div class="compare-body"><div class="compare-empty">프롬프트를 입력하고 비교 실행을 눌러주세요.</div></div></article></div></section>`;
      projectLab.querySelector('.chunking-note').innerHTML='RAG Supabase 비교 대상 · 왼쪽은 <b>documents</b>, 오른쪽은 <b>documents_test</b> 테이블을 사용합니다. 로컬 Ollama 모델 목록은 자동 갱신되며, OpenRouter의 openai/gpt-4o-mini 옵션은 계속 사용할 수 있습니다.';
      const compareEl=document.getElementById('legacyChunkingCompare');
      const promptEl=document.getElementById('legacyChunkingPromptInput');
      const modelEl=document.getElementById('legacyChunkingModelSelect');
      const runButton=document.getElementById('legacyChunkingRunButton');
      function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
      function renderPanel(panel){
        const card=compareEl.querySelector(`[data-panel="${panel.table}"]`);
        if(!card)return;
        card.classList.toggle('error',panel.status==='error');
        card.classList.remove('compare-loading');
        const badgeClass=panel.status==='ok'?'ok':panel.status==='error'?'error':'';
        const meta=panel.meta||{};
        card.querySelector('.compare-meta').innerHTML=`<span class="compare-badge ${badgeClass}">${panel.status==='ok'?'조회 완료':'오류'}</span><span class="compare-badge">테이블 ${escapeHtml(panel.table)}</span><span class="compare-badge">모델 ${escapeHtml(panel.model)}</span>`;
        const stats=panel.status==='ok'?`<div class="compare-stats"><div class="compare-stat"><b>${meta.total_rows??0}</b><span>총 문서</span></div><div class="compare-stat"><b>${meta.top_count??0}</b><span>비교 조각</span></div><div class="compare-stat"><b>${meta.top_score??0}</b><span>최고 점수</span></div><div class="compare-stat"><b>${meta.avg_score??0}</b><span>평균 점수</span></div></div>`:'';
        const items=panel.results?.length?`<div class="compare-list">${panel.results.map(item=>`<article class="compare-item"><div class="compare-item-head"><strong>${item.rank}. ${escapeHtml(item.title)}</strong><span class="compare-score">score ${item.score}</span></div><p>${escapeHtml(item.preview||'미리보기 없음')}</p></article>`).join('')}</div>`:'<div class="compare-empty">표시할 검색 결과가 없습니다.</div>';
        card.querySelector('.compare-body').innerHTML=`<div class="compare-status">${escapeHtml(panel.summary||'')}</div>${stats}<div class="compare-answer"><span>OUTPUT</span><pre>${escapeHtml(panel.answer||'')}</pre></div>${items}`;
      }
      function setLoading(){
        compareEl.querySelectorAll('.compare-panel').forEach(card=>{card.classList.remove('error');card.classList.add('compare-loading');card.querySelector('.compare-meta').innerHTML='<span class="compare-badge">조회 중</span>';card.querySelector('.compare-body').innerHTML='<div class="compare-stats"><div class="compare-stat"><b>...</b><span>총 문서</span></div><div class="compare-stat"><b>...</b><span>비교 조각</span></div><div class="compare-stat"><b>...</b><span>최고 점수</span></div><div class="compare-stat"><b>...</b><span>평균 점수</span></div></div><div class="compare-answer"><span>OUTPUT</span><pre>질문에 맞는 문서를 검색하고 있습니다...</pre></div><div class="compare-list"><article class="compare-item">검색 결과를 준비하는 중입니다.</article></div>'})
      }
      async function runCompare(){
        const prompt=promptEl.value.trim();
        if(!prompt){alert('질문을 입력하세요.');return;}
        runButton.disabled=true;setLoading();
        try{
          const r=await fetch('/api/chunking-legacy-compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,model:modelEl.value})});
          const data=await readJsonResponse(r);
          if(!r.ok)throw new Error(data.error||'비교 결과를 가져오지 못했습니다.');
          data.panels.forEach(renderPanel);
        }catch(e){
          compareEl.querySelectorAll('.compare-panel').forEach(card=>{card.classList.remove('compare-loading');card.classList.add('error');card.querySelector('.compare-meta').innerHTML='<span class="compare-badge error">오류</span>';card.querySelector('.compare-body').innerHTML=`<div class="compare-answer"><span>ERROR</span><pre>${escapeHtml(e.message)}</pre></div>`})
        }finally{runButton.disabled=false}
      }
      runButton.onclick=runCompare;
      startChunkingModelAutoRefresh(modelEl);
    }

    function renderChunkingRagLab(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="chunking-shell chunking-lab-v2"><div class="compare-grid-head"><h3>02. 청킹실습(과제)</h3><p>선택한 청킹 방식만 청킹, 임베딩, 질문 비교 대상으로 사용합니다.</p></div><div class="chunking-doc-grid"><label class="chunking-file">첨부 문서<input id="chunkingFileInput" type="file" accept=".hwpx,.txt,.md,.csv,.json,.html,.xml,.py,.js,.css,.log"><span id="chunkingFileName">텍스트 기반 문서 또는 .hwpx를 선택하세요.</span></label><div class="document-input"><label>문서 내용<textarea id="chunkingDocumentInput" placeholder="문서를 붙여넣거나 왼쪽에서 파일을 첨부하세요."></textarea></label></div></div><div class="strategy-picker"><div class="compare-grid-head"><h3>청킹 알고리즘 선택</h3><p>최대 3개까지 선택할 수 있습니다.</p></div><div class="strategy-grid"><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="fixed" checked><span><strong>고정 길이 청킹</strong><span>균일한 크기와 overlap으로 빠르게 분할</span></span></label><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="recursive" checked><span><strong>문단 우선 재귀 청킹</strong><span>문단과 문장 경계를 우선 보존</span></span></label><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="semantic" checked><span><strong>문장 윈도우 의미 청킹</strong><span>겹치는 문장 묶음으로 주변 의미 보존</span></span></label></div><div class="plan-actions"><button id="chunkingBuildButton" type="button">1. 청킹 실행</button><button id="chunkingEmbedButton" type="button" disabled>2. 임베딩 실행</button><span class="embed-status" id="chunkingEmbedProgress">(0/0 완료)</span><span class="embed-status" id="chunkingPlanStatus">문서를 준비하세요.</span></div></div><div class="chunking-plans" id="chunkingPlans"><div class="compare-empty">청킹 실행 후 방식별 설명, 장단점, 실제 청크가 표시됩니다.</div></div><div class="rag-console"><h3>질문 비교</h3><div class="chunking-controls"><label class="prompt-control">질문 입력<textarea id="chunkingPromptInput" placeholder="임베딩된 문서에 질문하세요.">이 문서의 핵심 내용을 요약해줘</textarea></label><label>모델 선택<select id="chunkingModelSelect"><option value="openai/gpt-4o-mini" selected>OpenRouter · gpt-4o-mini</option><option value="llama3.2:1b">Ollama · llama3.2:1b</option></select></label><label>RAG 방식<select id="chunkingRagMode"><option value="both" selected>Naive + Advanced</option><option value="naive">Naive RAG</option><option value="advanced">Advanced RAG</option></select></label><label>Temperature<input id="chunkingTemperature" type="number" min="0" max="1.5" step="0.1" value="0.2"></label><label>Top-K<input id="chunkingTopK" type="number" min="1" max="10" step="1" value="5"></label><label class="rerank-option"><input id="chunkingRerankToggle" type="checkbox"><span>Reranking</span></label><button class="chunking-run" id="chunkingRunButton" type="button" disabled>3. 질문 실행</button></div><div class="chunking-note">진행 순서 · <b>1. 청킹 실행</b> 후 <b>2. 임베딩 실행</b>이 활성화되고, 임베딩 완료 후 <b>3. 질문 실행</b>이 활성화됩니다. 선택한 청킹 방식이 1개 또는 2개이면 해당 방식만 임베딩하고 검색합니다.</div><div class="chunking-compare vertical" id="chunkingCompare"><div class="compare-empty">청킹 실행 후 임베딩을 완료하면 질문을 실행할 수 있습니다.</div></div></div></section>`;
      const sampleDoc=['인공지능 문서 검색 실습은 문서를 작은 조각으로 나누는 청킹 단계에서 시작합니다. 청킹 방식은 검색 정확도와 답변 품질에 직접적인 영향을 줍니다.','고정 길이 청킹은 구현이 쉽고 속도가 빠르지만 문장 경계를 끊을 수 있습니다. 문단 우선 재귀 청킹은 원문 구조를 더 잘 보존합니다. 문장 윈도우 의미 청킹은 주변 맥락을 겹쳐 담아 검색 누락을 줄이는 데 유리합니다.','각 청크는 임베딩 벡터로 변환되어 Supabase pgvector 테이블에 저장됩니다. 질문이 들어오면 질문도 벡터화한 뒤 유사도가 높은 청크를 검색하고, 선택한 LLM이 검색 문맥을 바탕으로 답변을 생성합니다.'].join('\n\n');
      const fileInput=document.getElementById('chunkingFileInput');
      const fileName=document.getElementById('chunkingFileName');
      const documentEl=document.getElementById('chunkingDocumentInput');
      const buildButton=document.getElementById('chunkingBuildButton');
      const embedButton=document.getElementById('chunkingEmbedButton');
      const embedProgress=document.getElementById('chunkingEmbedProgress');
      const planStatus=document.getElementById('chunkingPlanStatus');
      const plansEl=document.getElementById('chunkingPlans');
      const compareEl=document.getElementById('chunkingCompare');
      const promptEl=document.getElementById('chunkingPromptInput');
      const modelEl=document.getElementById('chunkingModelSelect');
      const ragModeEl=document.getElementById('chunkingRagMode');
      const temperatureEl=document.getElementById('chunkingTemperature');
      const topKEl=document.getElementById('chunkingTopK');
      const rerankEl=document.getElementById('chunkingRerankToggle');
      const runButton=document.getElementById('chunkingRunButton');
      const stopAllButton=document.createElement('button');
      stopAllButton.type='button';stopAllButton.className='chunking-stop-all';stopAllButton.textContent='전체 생성 중지';stopAllButton.disabled=true;
      runButton.insertAdjacentElement('afterend',stopAllButton);
      const compareControllers=new Map();
      let lastCompareConfig=null;
      const strategyInputs=[...document.querySelectorAll('input[name="chunkStrategy"]')];
      let currentPlans=[],embeddedTables=[];
      documentEl.value=sampleDoc;
      function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
      function selectedStrategies(){return strategyInputs.filter(input=>input.checked).map(input=>input.value)}
      function resetExecution(message='청킹 실행 전입니다.'){embeddedTables=[];embedButton.disabled=true;runButton.disabled=true;embedProgress.textContent='(0/0 완료)';planStatus.textContent=message;compareEl.innerHTML='<div class="compare-empty">청킹 실행 후 임베딩을 완료하면 질문을 실행할 수 있습니다.</div>'}
      function invalidatePlans(message='문서 또는 알고리즘이 바뀌었습니다. 청킹을 다시 실행하세요.'){currentPlans=[];plansEl.innerHTML='<div class="compare-empty">청킹 실행 후 방식별 설명, 장단점, 실제 청크가 표시됩니다.</div>';resetExecution(message)}
      strategyInputs.forEach(input=>input.onchange=()=>{const checked=strategyInputs.filter(item=>item.checked);if(checked.length>3){input.checked=false;alert('청킹 알고리즘은 최대 3개까지 선택할 수 있습니다.');return;}if(!checked.length){input.checked=true;alert('하나 이상의 청킹 알고리즘을 선택하세요.');return;}invalidatePlans('청킹 알고리즘 선택이 바뀌었습니다. 청킹을 다시 실행하세요.')});
      documentEl.oninput=()=>invalidatePlans('문서 내용이 바뀌었습니다. 청킹을 다시 실행하세요.');
      function bytesToBase64(bytes){let binary='';const size=0x8000;for(let i=0;i<bytes.length;i+=size){binary+=String.fromCharCode(...bytes.subarray(i,i+size))}return btoa(binary)}
      fileInput.onchange=async()=>{const file=fileInput.files?.[0];if(!file)return;if(file.size>30*1024*1024){alert('30MB 이하의 문서를 선택하세요.');fileInput.value='';return;}fileName.textContent=`${file.name} 읽는 중...`;try{if(file.name.toLowerCase().endsWith('.hwpx')){const bytes=new Uint8Array(await file.arrayBuffer());const r=await fetch('/api/hwpx-extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,data_base64:bytesToBase64(bytes)})});const data=await r.json();if(!r.ok)throw new Error(data.error||'hwpx 본문 추출에 실패했습니다.');documentEl.oninput=null;documentEl.value=data.text;documentEl.oninput=()=>invalidatePlans('문서 내용이 바뀌었습니다. 청킹을 다시 실행하세요.');fileName.textContent=`${file.name} · 본문 ${data.char_count}자 · 문단 ${data.paragraph_count}개`}else{documentEl.oninput=null;documentEl.value=await file.text();documentEl.oninput=()=>invalidatePlans('문서 내용이 바뀌었습니다. 청킹을 다시 실행하세요.');fileName.textContent=file.name}invalidatePlans('파일을 읽었습니다. 청킹을 실행하세요.')}catch(e){fileName.textContent='파일 읽기 실패';alert(e.message)}};
      function strategySettings(plan){const settings={fixed:'size 900 · overlap 120',recursive:'max 1100자 · 문단/문장 경계',semantic:'window 5문장 · stride 3'};return settings[plan.strategy]||'기본 설정'}
      function renderPlans(data){
        currentPlans=data.plans||[];embeddedTables=[];
        if(!currentPlans.length){plansEl.innerHTML='<div class="compare-empty">생성된 청크가 없습니다.</div>';resetExecution('생성된 청크가 없습니다.');return;}
        embedProgress.textContent=`(0/${currentPlans.length} 완료)`;
        planStatus.textContent=`문서 ${data.document.char_count}자 · ${currentPlans.length}개 방식 생성 · 임베딩 실행 가능`;
        embedButton.disabled=false;runButton.disabled=true;
        compareEl.innerHTML='<div class="compare-empty">임베딩 실행 후 질문을 실행할 수 있습니다.</div>';
        plansEl.innerHTML=currentPlans.map(plan=>`<article class="plan-card" data-slot="${plan.slot}"><div class="plan-head"><div><strong>청킹 방식 ${plan.slot}: ${escapeHtml(plan.label)}</strong><small>${escapeHtml(plan.summary)}</small></div><small>${escapeHtml(plan.table)}</small></div><div class="plan-body"><p class="plan-desc">${escapeHtml(plan.description)}</p><div class="compare-meta"><span class="compare-badge">설정 ${escapeHtml(strategySettings(plan))}</span><span class="compare-badge">${plan.chunks.length} chunks</span><span class="compare-badge">${escapeHtml(plan.table)}</span></div><div class="pros-cons"><div><b>장점</b><ul>${plan.pros.map(item=>`<li>${escapeHtml(item)}</li>`).join('')}</ul></div><div><b>단점</b><ul>${plan.cons.map(item=>`<li>${escapeHtml(item)}</li>`).join('')}</ul></div></div><div class="embed-row"><span class="embed-status" data-embed-status="${plan.slot}">임베딩 대기 중</span></div><div class="chunk-list">${plan.chunks.map(chunk=>`<details class="chunk-detail" ${chunk.rank===1?'open':''}><summary>Chunk ${chunk.rank} · ${chunk.char_count}자 · token ${chunk.token_count}</summary><pre>${escapeHtml(chunk.content)}</pre></details>`).join('')}</div></div></article>`).join('')
      }
      async function buildChunks(){const text=documentEl.value.trim();if(!text){alert('문서를 입력하거나 첨부하세요.');return;}buildButton.disabled=true;embedButton.disabled=true;runButton.disabled=true;embeddedTables=[];embedProgress.textContent='(0/0 완료)';planStatus.textContent='청킹 중...';plansEl.innerHTML='<div class="compare-empty">문서를 청킹하고 있습니다.</div>';compareEl.innerHTML='<div class="compare-empty">청킹 결과를 기다리고 있습니다.</div>';try{const r=await fetch('/api/chunking-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,strategies:selectedStrategies()})});const data=await r.json();if(!r.ok)throw new Error(data.error||'청킹에 실패했습니다.');renderPlans(data)}catch(e){currentPlans=[];planStatus.textContent='청킹 실패';plansEl.innerHTML=`<div class="compare-empty">${escapeHtml(e.message)}</div>`;embedButton.disabled=true;runButton.disabled=true}finally{buildButton.disabled=false}}
      async function embedAllPlans(){
        if(!currentPlans.length){alert('먼저 청킹을 실행하세요.');return;}
        embedButton.disabled=true;runButton.disabled=true;embeddedTables=[];
        let completed=0;
        embedProgress.textContent=`(${completed}/${currentPlans.length} 완료)`;
        planStatus.textContent=`${currentPlans.length}개 청킹 방식 임베딩 중...`;
        currentPlans.forEach(plan=>{const status=plansEl.querySelector(`[data-embed-status="${plan.slot}"]`);const card=plansEl.querySelector(`[data-slot="${plan.slot}"]`);if(card)delete card.dataset.embedded;if(status)status.textContent='임베딩 대기 중'});
        try{
          for(const plan of currentPlans){
            const status=plansEl.querySelector(`[data-embed-status="${plan.slot}"]`);
            if(status)status.textContent='임베딩 중...';
            const r=await fetch('/api/chunking-embed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan})});
            const item=await r.json();
            if(!r.ok)throw new Error(item.error||'임베딩에 실패했습니다.');
            completed+=1;embedProgress.textContent=`(${completed}/${currentPlans.length} 완료)`;
            if(item.table)embeddedTables.push(item.table);
            const card=plansEl.querySelector(`[data-slot="${item.slot}"]`),doneStatus=plansEl.querySelector(`[data-embed-status="${item.slot}"]`);
            if(card)card.dataset.embedded='true';
            if(doneStatus){const actual=item.actual_table&&item.actual_table!==item.table?` · 실제 ${item.actual_table}`:'';doneStatus.textContent=`${item.embedded_count}개 저장 · ${item.embedding_provider}${actual}${item.warning?' · fallback':''}`}
          }
          if(!embeddedTables.length)throw new Error('임베딩된 청킹 방식이 없습니다.');
          planStatus.textContent=`${embeddedTables.length}개 청킹 방식 임베딩 완료 · 질문 실행 가능`;
          runButton.disabled=false;
        }catch(e){
          planStatus.textContent=`임베딩 실패: ${e.message}`;embeddedTables=[];runButton.disabled=true;
        }finally{
          embedButton.disabled=!currentPlans.length;
        }
      }
      function snippetsFor(panel){return (panel.results||[]).map(item=>{const rerank=item.rerank_score!=null?` · rerank ${item.rerank_score}`:'';const queries=item.matched_queries?.length?` · query ${item.matched_queries.length}`:'';const citation=item.citation?`${item.citation} · `:'';return `${item.rank}. ${citation}score ${item.score}${rerank}${queries} · ${item.preview||''}`}).join('\n')||'검색 결과가 없습니다.'}
      function renderComparePanel(panel){
        const meta=panel.meta||{},badgeClass=panel.status==='ok'?'ok':'error';
        const detailId=`chunk-detail-${panel.table}-${panel.rag_mode||'naive'}`;
        const elapsed=meta.elapsed_ms!=null?`${(meta.elapsed_ms/1000).toFixed(1)}s`:'';
        const optionBadges=`<span class="compare-badge">RAG ${escapeHtml(panel.rag_label||panel.rag_mode||'Naive')}</span><span class="compare-badge">T ${panel.temperature??0.2}</span><span class="compare-badge">Top-K ${panel.top_k??5}</span>${meta.query_count?`<span class="compare-badge">Query ${meta.query_count}</span>`:''}${meta.context_compression?'<span class="compare-badge">Context 압축</span>':''}${meta.answer_chars?`<span class="compare-badge">답변 ${meta.answer_chars}자</span>`:''}${elapsed?`<span class="compare-badge">${elapsed}</span>`:''}${meta.citation_count!=null?`<span class="compare-badge">근거 ${meta.citation_count}개</span>`:''}${panel.reranking?`<span class="compare-badge">Cohere ${escapeHtml(panel.rerank_model||'rerank')}</span>`:''}`;
        const queryInfo=panel.query_variants?.length?`<div class="compare-status">질의 변형 · ${escapeHtml(panel.query_variants.join(' / '))}</div>`:'';
        const citationInfo=panel.citations?.length?`<div class="compare-status">답변 인용 · ${escapeHtml(panel.citations.join(', '))}</div>`:'';
        return `<article class="compare-panel ${panel.status==='error'?'error':''}" data-panel="${escapeHtml(panel.table)}-${escapeHtml(panel.rag_mode||'naive')}"><div class="compare-head"><strong>청킹 방식 ${panel.slot}: ${escapeHtml(panel.label)}</strong><small>${escapeHtml(panel.table)} · ${escapeHtml(panel.rag_label||panel.rag_mode||'Naive RAG')}</small><div class="compare-meta"><span class="compare-badge ${badgeClass}">${panel.status==='ok'?'조회 완료':'오류'}</span><span class="compare-badge">${escapeHtml(panel.model)}</span>${optionBadges}${panel.embedding_provider?`<span class="compare-badge">${escapeHtml(panel.embedding_provider)}</span>`:''}${panel.actual_table&&panel.actual_table!==panel.table?`<span class="compare-badge">실제 ${escapeHtml(panel.actual_table)}</span>`:''}</div><div class="compare-stats"><div class="compare-stat"><b>${meta.total_rows??0}</b><span>총문서</span></div><div class="compare-stat"><b>${meta.top_count??0}</b><span>비교조각</span></div><div class="compare-stat"><b>${meta.top_score??0}</b><span>최고점수</span></div><div class="compare-stat"><b>${meta.avg_score??0}</b><span>평균점수</span></div></div></div><div class="compare-body"><div class="compare-status">${escapeHtml(panel.summary||'')}${panel.warning?' · '+escapeHtml(panel.warning):''}</div>${queryInfo}${citationInfo}<label class="compare-status">검색 결과<textarea class="result-snippets" rows="5" readonly>${escapeHtml(snippetsFor(panel))}</textarea></label><div class="compare-answer"><span>LLM ANSWER</span><pre>${escapeHtml(panel.answer||'')}</pre></div><button class="compare-chunk-button" data-detail-panel="${detailId}" type="button">비교 청크 내용 보기</button><div class="compare-chunk-detail" id="${detailId}" hidden>${(panel.results||[]).map(item=>`<article class="compare-chunk"><strong>${item.rank}. ${escapeHtml(item.citation||'검색 조각 '+item.rank)} · ${escapeHtml(item.title)} · score ${item.score}${item.rerank_score!=null?` · rerank ${item.rerank_score}`:''}</strong>${item.matched_queries?.length?`<small>matched · ${escapeHtml(item.matched_queries.join(' / '))}</small>`:''}<pre>${escapeHtml(item.content||item.preview||'')}</pre></article>`).join('')||'<div class="compare-empty">표시할 청크가 없습니다.</div>'}</div></div></article>`
      }
      function ragScore(panel){
        if(panel.status!=='ok')return -999;
        const meta=panel.meta||{};
        const top=Number(meta.top_score||0),avg=Number(meta.avg_score||0),citations=Number(meta.citation_count||0),chars=Number(meta.answer_chars||0),elapsed=Number(meta.elapsed_ms||0);
        const citationBonus=Math.min(citations,Number(meta.top_count||0)||citations)*0.18;
        const answerBonus=Math.min(chars/1200,1)*0.16;
        const advancedBonus=panel.rag_mode==='advanced'?0.12:0;
        const rerankBonus=panel.reranking?0.05:0;
        const speedPenalty=Math.min(elapsed/60000,1)*0.12;
        return top+avg+citationBonus+answerBonus+advancedBonus+rerankBonus-speedPenalty;
      }
      function renderEvaluationSummary(panels){
        const okPanels=panels.filter(panel=>panel.status==='ok');
        if(!okPanels.length)return '';
        const groups=new Map();
        okPanels.forEach(panel=>{const key=panel.table||`slot-${panel.slot}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(panel)});
        const rows=[];
        groups.forEach(items=>{
          const naive=items.find(panel=>panel.rag_mode==='naive');
          const advanced=items.find(panel=>panel.rag_mode==='advanced');
          const base=advanced||naive||items[0];
          const naiveScore=naive?ragScore(naive):null,advancedScore=advanced?ragScore(advanced):null;
          let winner='비교 대상 부족', reason='선택한 RAG 방식만 실행됨';
          if(naive&&advanced){
            const diff=Math.abs(advancedScore-naiveScore);
            if(diff<0.08){winner='비슷함';reason='검색 점수와 근거 수 차이가 작음'}
            else if(advancedScore>naiveScore){winner='Advanced RAG';reason='다중 질의, rerank, 근거 활용 점수가 높음'}
            else{winner='Naive RAG';reason='단일 검색이 더 높은 유사도/속도를 보임'}
          }
          const metric=panel=>panel?`score ${ragScore(panel).toFixed(2)} · ${((panel.meta?.elapsed_ms||0)/1000).toFixed(1)}s · 근거 ${panel.meta?.citation_count??0}개`:'실행 안 됨';
          rows.push(`<div class="evaluation-row"><b>청킹 방식 ${base.slot}: ${escapeHtml(base.label)}</b><span>Naive · ${escapeHtml(metric(naive))}</span><span>Advanced · ${escapeHtml(metric(advanced))}</span><span class="evaluation-winner">${escapeHtml(winner)}<br><small>${escapeHtml(reason)}</small></span></div>`);
        });
        return `<article class="compare-evaluation"><div class="compare-head"><strong>Naive vs Advanced 평가 카드</strong><small>검색 점수, 인용 근거, 답변 길이, 처리 시간을 종합한 휴리스틱 추천입니다.</small></div><div class="evaluation-grid">${rows.join('')}</div><div class="evaluation-note">평가 점수는 실험용 지표입니다. 최종 품질 판단은 답변 내용과 실제 근거 청크를 함께 확인하세요.</div></article>`;
      }
      function renderProgressPanel(plan,state='pending',message='이전 청킹 방식 답변이 끝나면 시작합니다.'){
        const badge=state==='active'?'생성 중':state==='done'?'완료':'대기 중';
        const body=state==='active'?'임시 출력':'진행 상태';
        return `<article class="compare-panel compare-loading" data-panel="${escapeHtml(plan.table)}-${escapeHtml(plan.ragMode||'naive')}"><div class="compare-head"><strong>청킹 방식 ${plan.slot}: ${escapeHtml(plan.label)}</strong><small>${escapeHtml(plan.table)} · ${escapeHtml(plan.ragLabel||plan.ragMode||'Naive RAG')}</small><div class="compare-meta"><span class="compare-badge">${badge}</span><span class="compare-badge">${escapeHtml(plan.ragLabel||plan.ragMode||'Naive RAG')}</span><span class="compare-badge">순차 실행</span></div></div><div class="compare-body"><div class="compare-answer"><span>${body}</span><pre>${escapeHtml(message)}</pre></div></div></article>`
      }
      function renderCompareErrorPanel(plan,message){
        return `<article class="compare-panel error" data-panel="${escapeHtml(plan.table)}-${escapeHtml(plan.ragMode||'naive')}"><div class="compare-head"><strong>청킹 방식 ${plan.slot}: ${escapeHtml(plan.label)}</strong><small>${escapeHtml(plan.table)} · ${escapeHtml(plan.ragLabel||plan.ragMode||'Naive RAG')}</small><div class="compare-meta"><span class="compare-badge error">오류</span></div></div><div class="compare-body"><div class="compare-answer"><span>ERROR</span><pre>${escapeHtml(message)}</pre></div></div></article>`
      }
      function compareKey(plan){return `${plan.table}-${plan.ragMode||'naive'}`}
      function selectedRagModes(){return ragModeEl.value==='both'?['naive','advanced']:[ragModeEl.value]}
      function compareJobs(){return currentPlans.filter(plan=>embeddedTables.includes(plan.table)).flatMap(plan=>selectedRagModes().map(mode=>({...plan,ragMode:mode,ragLabel:mode==='advanced'?'Advanced RAG':'Naive RAG'})))}
      function replaceComparePanel(key,html){
        const current=compareEl.querySelector(`[data-panel="${key}"]`);
        if(current)current.outerHTML=html;else compareEl.insertAdjacentHTML('beforeend',html);
      }
      function setCompareLoading(){const panels=compareJobs();compareEl.innerHTML=panels.map((plan,index)=>renderProgressPanel(plan,index===0?'active':'pending',index===0?'Supabase에서 유사 청크를 검색하고 LLM 답변 생성을 시작합니다.':'앞선 비교 답변이 완료되면 자동으로 시작합니다.')).join('')}
      async function runCompare(){
        const prompt=promptEl.value.trim();
        if(!prompt){alert('질문을 입력하세요.');return;}
        if(!embeddedTables.length){alert('먼저 임베딩을 실행하세요.');return;}
        const panels=compareJobs();
        if(!panels.length){alert('질문을 실행할 청킹 방식이 없습니다.');return;}
        const rawTemperature=Number(temperatureEl.value||0.2);
        const rawTopK=parseInt(topKEl.value||'5',10);
        const temperature=Number.isFinite(rawTemperature)?Math.max(0,Math.min(1.5,rawTemperature)):0.2;
        const topK=Number.isFinite(rawTopK)?Math.max(1,Math.min(10,rawTopK)):5;
        temperatureEl.value=String(temperature);topKEl.value=String(topK);
        runButton.disabled=true;setCompareLoading();
        let completed=0;
        const completedPanels=[];
        try{
          for(const plan of panels){
            planStatus.textContent=`질문 실행 중... ${completed+1}/${panels.length} · ${plan.label} · ${plan.ragLabel}`;
            const progressMessages=['Supabase에서 유사 청크를 검색하는 중입니다.','검색된 청크를 질문 문맥으로 정리하고 있습니다.','LLM 답변을 생성하는 중입니다.','응답이 길어질 수 있어 조금만 더 기다려주세요.'];
            let progressIndex=0;
            replaceComparePanel(compareKey(plan),renderProgressPanel(plan,'active',progressMessages[progressIndex]));
            const progressTimer=setInterval(()=>{
              progressIndex=Math.min(progressIndex+1,progressMessages.length-1);
              replaceComparePanel(compareKey(plan),renderProgressPanel(plan,'active',progressMessages[progressIndex]));
            },2500);
            try{
              const r=await fetch('/api/chunking-compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,model:modelEl.value,tables:[plan.table],rag_mode:plan.ragMode,temperature,top_k:topK,reranking:rerankEl.checked,rerank_model:'rerank-v4.0-fast'})});
              const data=await readJsonResponse(r);
              if(!r.ok)throw new Error(data.error||'비교 결과를 가져오지 못했습니다.');
              const panel=data.panels?.[0];
              if(!panel)throw new Error('응답 패널이 비어 있습니다.');
              replaceComparePanel(compareKey(plan),renderComparePanel(panel));
              completedPanels.push(panel);
            }catch(e){
              replaceComparePanel(compareKey(plan),renderCompareErrorPanel(plan,e.message));
            }finally{
              clearInterval(progressTimer);
              completed+=1;
            }
          }
          compareEl.querySelector('.compare-evaluation')?.remove();
          const evaluationHtml=renderEvaluationSummary(completedPanels);
          if(evaluationHtml)compareEl.insertAdjacentHTML('afterbegin',evaluationHtml);
          planStatus.textContent=`질문 실행 완료 · ${completed}/${panels.length}`;
        }finally{runButton.disabled=false}
      }
      const comparePlanMap=new Map();
      function renderStreamMarkdown(text){const lines=escapeHtml(text).split('\n');let html=[],inCode=false,list='';const closeList=()=>{if(list){html.push(`</${list}>`);list=''}};for(const raw of lines){if(raw.startsWith('```')){closeList();if(inCode){html.push('</code></pre>');inCode=false}else{html.push('<pre><code>');inCode=true}continue}if(inCode){html.push(raw+'\n');continue}let line=raw.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');const heading=line.match(/^(#{1,3})\s+(.+)/);if(heading){closeList();const level=heading[1].length;html.push(`<h${level}>${heading[2]}</h${level}>`);continue}const bullet=line.match(/^[-*]\s+(.+)/);const numbered=line.match(/^\d+\.\s+(.+)/);if(bullet||numbered){const wanted=bullet?'ul':'ol';if(list!==wanted){closeList();list=wanted;html.push(`<${list}>`)}html.push(`<li>${(bullet||numbered)[1]}</li>`);continue}closeList();if(line.startsWith('&gt; '))html.push(`<blockquote>${line.slice(5)}</blockquote>`);else if(line.trim())html.push(`<p>${line}</p>`);else html.push('<br>')}closeList();if(inCode)html.push('</code></pre>');return html.join('')}
      function renderStreamShell(plan){const key=compareKey(plan);return `<article class="compare-panel stream-panel is-streaming" data-panel="${escapeHtml(key)}"><div class="compare-head"><strong>청킹 방식 ${plan.slot}: ${escapeHtml(plan.label)}</strong><small>${escapeHtml(plan.table)} · ${escapeHtml(plan.ragLabel)}</small><div class="compare-meta"><span class="compare-badge ok" data-stream-badge>연결 중</span><span class="compare-badge">${escapeHtml(modelEl.value)}</span><span class="compare-badge">병렬 스트리밍</span></div></div><div class="compare-body"><div class="compare-answer stream-answer is-streaming is-following"><span>LLM ANSWER · LIVE</span><div class="stream-answer-output"></div><button class="stream-answer-paused" type="button">↓ 실시간 출력으로 이동</button></div><div class="stream-live-meta"><span class="compare-badge" data-first-token>첫 응답 대기</span><span class="compare-badge" data-live-chars>0자</span><span class="compare-badge" data-live-time>0.0s</span></div><div class="stream-process"><div class="stream-process-head"><span data-process-title>생성 준비 중</span><span>상세 진행</span></div><div class="stream-process-log"><div class="stream-step active">요청을 준비하고 있습니다.</div></div></div><details class="stream-sources"><summary>검색 근거 · 준비 중</summary><div class="stream-sources-list"><div class="stream-source">검색 결과가 도착하면 답변보다 먼저 표시됩니다.</div></div></details><div class="stream-error-note" hidden></div><div class="stream-actions"><button class="compare-stop" type="button">이 패널 중지</button><button class="compare-retry" type="button" hidden>이 패널 다시 생성</button></div></div></article>`}
      function streamPanelNodes(key){const panel=compareEl.querySelector(`[data-panel="${key}"]`);return panel&&{panel,answer:panel.querySelector('.stream-answer'),output:panel.querySelector('.stream-answer-output'),badge:panel.querySelector('[data-stream-badge]'),title:panel.querySelector('[data-process-title]'),log:panel.querySelector('.stream-process-log'),sources:panel.querySelector('.stream-sources'),sourceList:panel.querySelector('.stream-sources-list'),first:panel.querySelector('[data-first-token]'),chars:panel.querySelector('[data-live-chars]'),clock:panel.querySelector('[data-live-time]'),error:panel.querySelector('.stream-error-note'),stop:panel.querySelector('.compare-stop'),retry:panel.querySelector('.compare-retry'),paused:panel.querySelector('.stream-answer-paused')}}
      function setStreamStage(nodes,stage,message,state='active'){nodes.log.querySelectorAll('.stream-step.active').forEach(item=>item.classList.replace('active','done'));const row=document.createElement('div');row.className=`stream-step ${state}`;row.dataset.stage=stage;row.textContent=message;nodes.log.append(row);nodes.title.textContent=message;nodes.badge.textContent=state==='error'?'오류':stage==='done'?'완료':stage==='stopped'?'중지됨':'생성 중'}
      function renderStreamSources(nodes,results){const items=results||[];nodes.sources.open=true;nodes.sources.querySelector('summary').textContent=`검색 근거 · ${items.length}개`;nodes.sourceList.innerHTML=items.length?items.map(item=>`<article class="stream-source"><b>${escapeHtml(item.citation||'검색 조각')} · score ${item.score}${item.rerank_score!=null?` · rerank ${item.rerank_score}`:''}</b><p>${escapeHtml(item.preview||item.content||'')}</p></article>`).join(''):'<div class="stream-source">검색된 근거가 없습니다.</div>'}
      function setupStreamScroll(nodes){let userPaused=false;const follow=()=>{if(!userPaused)nodes.answer.scrollTop=nodes.answer.scrollHeight};nodes.answer.addEventListener('wheel',e=>{if(e.deltaY<0){userPaused=true;nodes.answer.classList.add('user-paused')}});nodes.answer.addEventListener('scroll',()=>{const away=nodes.answer.scrollHeight-nodes.answer.scrollTop-nodes.answer.clientHeight>55;if(away){userPaused=true;nodes.answer.classList.add('user-paused')}else{userPaused=false;nodes.answer.classList.remove('user-paused')}});nodes.paused.onclick=()=>{userPaused=false;nodes.answer.classList.remove('user-paused');follow()};return follow}
      function updateLiveMetrics(nodes,start,firstAt,text){nodes.clock.textContent=`${((performance.now()-start)/1000).toFixed(1)}s`;nodes.chars.textContent=`${text.length}자`;if(firstAt)nodes.first.textContent=`첫 응답 ${((firstAt-start)/1000).toFixed(1)}s`}
      function stopCompareJob(key){const controller=compareControllers.get(key);if(controller)controller.abort()}
      async function runCompareJob(plan,config){const key=compareKey(plan);comparePlanMap.set(key,plan);replaceComparePanel(key,renderStreamShell(plan));const nodes=streamPanelNodes(key),controller=new AbortController();compareControllers.set(key,controller);nodes.stop.onclick=()=>stopCompareJob(key);nodes.retry.onclick=()=>runCompareJob(plan,config);const follow=setupStreamScroll(nodes),started=performance.now();let firstAt=0,received='',visible='',queueChars=[],finalPanel=null;const timer=setInterval(()=>{if(queueChars.length){const take=Math.max(1,Math.ceil(queueChars.length/16));visible+=queueChars.splice(0,take).join('');nodes.output.textContent=visible;updateLiveMetrics(nodes,started,firstAt,visible);follow()}else updateLiveMetrics(nodes,started,firstAt,visible)},18);try{const r=await fetch('/api/chunking-compare-stream',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({...config,tables:[plan.table],rag_mode:plan.ragMode})});if(!r.ok||!r.body){const data=await readJsonResponse(r);throw new Error(data.error||'스트리밍 연결에 실패했습니다.')}const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines){if(!line.trim())continue;const event=JSON.parse(line);if(event.type==='stage')setStreamStage(nodes,event.stage,event.message);else if(event.type==='context'){setStreamStage(nodes,'context',event.message);renderStreamSources(nodes,event.results)}else if(event.type==='token'){if(!firstAt){firstAt=performance.now();setStreamStage(nodes,'stream','첫 응답이 도착해 실시간으로 표시하고 있습니다.')}received+=event.content||'';queueChars.push(...Array.from(event.content||''))}else if(event.type==='done')finalPanel=event.result?.panels?.[0];else if(event.type==='error')throw new Error(event.error||'답변 생성에 실패했습니다.')}}if(!finalPanel)throw new Error('완료된 응답 패널이 없습니다.');clearInterval(timer);visible=received||finalPanel.answer||'';nodes.output.textContent=visible;const elapsed=(performance.now()-started)/1000,approxTokens=Math.max(1,Math.ceil(visible.length/3)),tps=(approxTokens/Math.max(elapsed,0.1)).toFixed(1);finalPanel.meta={...(finalPanel.meta||{}),first_token_ms:firstAt?Math.round(firstAt-started):null,approx_output_tokens:approxTokens,tokens_per_second:Number(tps)};replaceComparePanel(key,renderComparePanel(finalPanel));const done=compareEl.querySelector(`[data-panel="${key}"]`);done.classList.add('stream-panel','is-done');const answerPre=done.querySelector('.compare-answer pre');answerPre.classList.add('stream-markdown');answerPre.style.whiteSpace='normal';answerPre.innerHTML=renderStreamMarkdown(finalPanel.answer||'');done.querySelector('.compare-meta').insertAdjacentHTML('beforeend',`<span class="compare-badge">첫 응답 ${firstAt?((firstAt-started)/1000).toFixed(1):'-'}s</span><span class="compare-badge">약 ${approxTokens} tok</span><span class="compare-badge">${tps} tok/s</span>`);done.querySelector('.compare-body').insertAdjacentHTML('afterbegin',`<div class="stream-process"><div class="stream-process-head"><span>생성 완료 · ${elapsed.toFixed(1)}초</span><span>진행 과정 접힘</span></div></div>`);return finalPanel}catch(e){clearInterval(timer);nodes.answer.classList.remove('is-streaming');nodes.stop.hidden=true;nodes.retry.hidden=false;if(e.name==='AbortError'){nodes.panel.classList.remove('is-streaming');nodes.panel.classList.add('is-stopped');setStreamStage(nodes,'stopped','사용자 요청으로 생성을 중지했습니다.','done');nodes.error.hidden=false;nodes.error.textContent='중지 전까지 생성된 답변은 유지됩니다.'}else{nodes.panel.classList.remove('is-streaming');nodes.panel.classList.add('error');setStreamStage(nodes,'error',e.message,'error');nodes.error.hidden=false;nodes.error.textContent=`오류: ${e.message} · 이 패널만 다시 생성할 수 있습니다.`}return null}finally{clearInterval(timer);compareControllers.delete(key)}}
      async function runCompareStreaming(){const prompt=promptEl.value.trim();if(!prompt){alert('질문을 입력하세요.');return}if(!embeddedTables.length){alert('먼저 임베딩을 실행하세요.');return}const panels=compareJobs();if(!panels.length){alert('질문을 실행할 청킹 방식이 없습니다.');return}const temperature=Math.max(0,Math.min(1.5,Number(temperatureEl.value)||0.2)),topK=Math.max(1,Math.min(10,parseInt(topKEl.value||'5',10)));lastCompareConfig={prompt,model:modelEl.value,temperature,top_k:topK,reranking:rerankEl.checked,rerank_model:'rerank-v4.0-fast'};compareEl.innerHTML=panels.map(renderStreamShell).join('');runButton.disabled=true;stopAllButton.disabled=false;planStatus.textContent=`${panels.length}개 패널 병렬 스트리밍 중...`;const results=(await Promise.all(panels.map(plan=>runCompareJob(plan,lastCompareConfig)))).filter(Boolean);compareEl.querySelector('.compare-evaluation')?.remove();const evaluationHtml=renderEvaluationSummary(results);if(evaluationHtml)compareEl.insertAdjacentHTML('afterbegin',evaluationHtml);planStatus.textContent=`질문 실행 완료 · ${results.length}/${panels.length}`;runButton.disabled=false;stopAllButton.disabled=true}
      stopAllButton.onclick=()=>{[...compareControllers.keys()].forEach(stopCompareJob);stopAllButton.disabled=true;planStatus.textContent='실행 중인 모든 패널의 생성을 중지했습니다.'};
      compareEl.addEventListener('click',e=>{const button=e.target.closest('[data-detail-panel]');if(!button)return;const detail=document.getElementById(button.dataset.detailPanel);if(!detail)return;detail.hidden=!detail.hidden;button.textContent=detail.hidden?'비교 청크 내용 보기':'비교 청크 내용 닫기'});
      buildButton.onclick=buildChunks;embedButton.onclick=embedAllPlans;runButton.onclick=runCompareStreaming;resetExecution('청킹 실행 전입니다.');startChunkingModelAutoRefresh(modelEl);
    }

    function renderAISafeAgent(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="safe-agent-lab"><div class="safe-agent-data-bar is-collapsed"><div class="safe-agent-data-head" id="safeAgentDataHead" tabindex="0"><div><strong id="safeAgentKbStatus">기초 데이터 확인 중</strong><small id="safeAgentKbDetail">PKL 상태를 불러오고 있습니다.</small></div><div class="safe-agent-data-actions"><button class="primary" id="safeAgentBuildData" type="button">기초 데이터 만들기</button><button id="safeAgentRefreshKb" type="button">새로고침</button><button class="safe-agent-log-toggle" id="safeAgentLogToggle" type="button" aria-expanded="false" aria-controls="safeAgentDataLog">로그 보기</button></div></div><textarea class="safe-agent-data-log" id="safeAgentDataLog" readonly>기초 데이터 로그가 이곳에 표시됩니다.</textarea></div><div class="safe-agent-console"><div class="safe-agent-map" id="safeAgentMap" aria-label="분석 지점 지도"><div class="safe-agent-map-label" id="safeAgentMapLabel">37.5665, 126.9780 · 500m</div><div class="safe-agent-map-legend"><span><i class="risk"></i>위험 요소</span><span><i class="shelter"></i>대피소</span></div></div><div class="safe-agent-controls"><div class="safe-agent-title-row"><h3>위험 요소 중심 복합 재해 분석</h3><div class="safe-agent-badges"><span class="safe-agent-badge">KMA LIVE</span><span class="safe-agent-badge">500M RADIUS</span><span class="safe-agent-badge">LLM REPORT</span></div></div><div class="safe-agent-fields"><label>위도<input id="safeAgentLat" type="number" step="0.000001" value="37.5665"></label><label>경도<input id="safeAgentLng" type="number" step="0.000001" value="126.9780"></label><label class="safe-agent-address-field">법정동<input id="safeAgentAddress" type="text" value="확인 중" readonly></label></div><div class="safe-agent-execute-row"><label class="safe-agent-model-field">AI 모델<select id="safeAgentModel"><option value="">모델 불러오는 중...</option></select></label><button class="safe-agent-run" id="safeAgentRun" type="button">분석 실행</button><div class="safe-agent-inline-message" id="safeAgentMessage">좌표를 입력하거나 지도를 클릭하면 Python PoC가 서버에서 실행됩니다.</div></div><div class="safe-agent-preset-panel"><div class="safe-agent-preset-form"><label>장소명<input id="safeAgentPlaceName" type="text" placeholder="예: 우리집, 현장 A"></label><button id="safeAgentSavePreset" type="button">현재 좌표 저장</button><button id="safeAgentGps" type="button">GPS 위치</button></div><div class="safe-agent-samples" id="safeAgentPresets"></div></div></div></div><div class="safe-agent-status" id="safeAgentStatus"><article class="safe-agent-rain-card"><div class="safe-agent-rain-head"><strong>강수·기온 추계</strong><span>분석 실행 후 갱신</span></div><div class="safe-agent-rain-bars"><div class="safe-agent-rain-item"><span class="safe-agent-rain-value">-</span><i class="safe-agent-rain-bar" style="height:6px"></i><span class="safe-agent-rain-label">6H</span></div><div class="safe-agent-rain-item"><span class="safe-agent-rain-value">-</span><i class="safe-agent-rain-bar" style="height:6px"></i><span class="safe-agent-rain-label">현재</span></div><div class="safe-agent-rain-item"><span class="safe-agent-rain-value">-</span><i class="safe-agent-rain-bar" style="height:6px"></i><span class="safe-agent-rain-label">+1H</span></div><div class="safe-agent-rain-item"><span class="safe-agent-rain-value">-</span><i class="safe-agent-rain-bar" style="height:6px"></i><span class="safe-agent-rain-label">+2H</span></div><div class="safe-agent-rain-item"><span class="safe-agent-rain-value">-</span><i class="safe-agent-rain-bar" style="height:6px"></i><span class="safe-agent-rain-label">+3H</span></div></div></article><article class="safe-agent-status-card"><b>-</b><span>위험 이력</span></article><article class="safe-agent-status-card"><b>-</b><span>대피소</span></article></div><div class="safe-agent-result" id="safeAgentResult"><div class="safe-agent-empty">실행 결과가 이곳에 표시됩니다.</div></div></section>`;
      const latEl=document.getElementById('safeAgentLat'),lngEl=document.getElementById('safeAgentLng'),addressEl=document.getElementById('safeAgentAddress'),modelEl=document.getElementById('safeAgentModel'),runButton=document.getElementById('safeAgentRun'),messageEl=document.getElementById('safeAgentMessage'),statusEl=document.getElementById('safeAgentStatus'),resultEl=document.getElementById('safeAgentResult'),mapEl=document.getElementById('safeAgentMap'),mapLabelEl=document.getElementById('safeAgentMapLabel'),kbStatusEl=document.getElementById('safeAgentKbStatus'),kbDetailEl=document.getElementById('safeAgentKbDetail'),buildDataButton=document.getElementById('safeAgentBuildData'),refreshKbButton=document.getElementById('safeAgentRefreshKb'),dataBarEl=document.querySelector('.safe-agent-data-bar'),dataHeadEl=document.getElementById('safeAgentDataHead'),dataLogEl=document.getElementById('safeAgentDataLog'),dataLogToggle=document.getElementById('safeAgentLogToggle'),gpsButton=document.getElementById('safeAgentGps'),placeNameEl=document.getElementById('safeAgentPlaceName'),savePresetButton=document.getElementById('safeAgentSavePreset'),presetsEl=document.getElementById('safeAgentPresets');
      const gpsPopupEl=document.createElement('div');gpsPopupEl.className='safe-agent-gps-popup';gpsPopupEl.setAttribute('role','status');gpsPopupEl.setAttribute('aria-live','polite');gpsPopupEl.innerHTML='<i aria-hidden="true"></i><span>GPS 기반 장소로 이동 중입니다.</span>';gpsPopupEl.hidden=true;mapEl.append(gpsPopupEl);
      function setGpsPopup(open){gpsPopupEl.hidden=!open}
      const presetKey='minzday.aiSafeAgent.presets';
      const defaultPresets=[{name:'서울시청',lat:37.5665,lng:126.978},{name:'부산시청',lat:35.1796,lng:129.0756}];
      let lastAnalysisRequest=null,lastSpatialSummary=null,lastSpatialCoords=null,lastRainInfo=null,lastRainCoords=null,safeMap=null,safeMarker=null,safeCircle=null,safeFeatureLayer=null,analysisRunning=false,analysisController=null,spatialRequestSeq=0,rainRequestSeq=0,geocodeRequestSeq=0,reverseGeocodeEnabled=true,hasCenteredMapOnFirstClick=false;
      function scheduleMapResize(){if(!safeMap)return;requestAnimationFrame(()=>{safeMap.invalidateSize({animate:false});setTimeout(()=>safeMap&&safeMap.invalidateSize({animate:false}),120);setTimeout(()=>safeMap&&safeMap.invalidateSize({animate:false}),360)})}
      function scrollMapToCenterOnce(){if(hasCenteredMapOnFirstClick)return;hasCenteredMapOnFirstClick=true;requestAnimationFrame(()=>{mapEl.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'});setTimeout(scheduleMapResize,320)})}
      function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
      function appendDataLog(message,reset=false){const line=`[${new Date().toLocaleTimeString()}] ${message}`;dataLogEl.value=reset?line:`${dataLogEl.value}\n${line}`;dataLogEl.scrollTop=dataLogEl.scrollHeight}
      function setDataLogOpen(open){dataBarEl.classList.toggle('is-collapsed',!open);dataLogToggle.textContent=open?'로그 닫기':'로그 보기';dataLogToggle.setAttribute('aria-expanded',String(open))}
      function toggleDataLog(){setDataLogOpen(dataBarEl.classList.contains('is-collapsed'))}
      function validPresetItems(items){return items.filter(item=>item&&Number.isFinite(Number(item.lat))&&Number.isFinite(Number(item.lng))&&String(item.name||'').trim()).map(item=>({name:String(item.name).trim(),lat:Number(item.lat),lng:Number(item.lng)}))}
      function loadPresets(){try{const saved=localStorage.getItem(presetKey);if(saved!==null){const parsed=JSON.parse(saved);return Array.isArray(parsed)?validPresetItems(parsed):[]}}catch(e){}return defaultPresets}
      function savePresets(presets){localStorage.setItem(presetKey,JSON.stringify(presets.map(item=>({name:item.name,lat:Number(item.lat),lng:Number(item.lng)}))))}
      function renderPresets(){const presets=loadPresets();presetsEl.innerHTML=presets.map((item,index)=>`<span class="safe-agent-preset-item"><button type="button" data-preset-index="${index}">${escapeHtml(item.name)}</button><button class="safe-agent-preset-delete" type="button" data-delete-preset-index="${index}" aria-label="${escapeHtml(item.name)} 삭제">삭제</button></span>`).join('')||'<span class="safe-agent-empty">저장된 좌표가 없습니다.</span>'}
      function setKbStatus(status){if(status?.exists){kbStatusEl.textContent=status.message||`PKL 파일 생성완료(${status.display_date||status.filename})`;kbDetailEl.textContent=`${status.filename||''}${status.size?` · ${Math.round(status.size/1024).toLocaleString()}KB`:''}`}else{kbStatusEl.textContent='PKL 파일 없음';kbDetailEl.textContent='기초 데이터 만들기를 실행하면 날짜가 붙은 PKL이 생성됩니다.'}}
      async function loadKbStatus(log=false){const r=await fetch('/api/poc/ai-safe-agent/kb/status');const data=await readJsonResponse(r);if(!r.ok)throw new Error(data.error||'PKL 상태를 불러오지 못했습니다.');setKbStatus(data);if(log)appendDataLog(data.message||'PKL 상태 확인 완료');return data}
      function initMap(){const lat=Number(latEl.value),lng=Number(lngEl.value);if(!Number.isFinite(lat)||!Number.isFinite(lng))return;if(!window.L){mapEl.classList.add('is-fallback');if(!mapEl.querySelector('.safe-agent-map-fallback'))mapEl.insertAdjacentHTML('afterbegin','<div class="safe-agent-map-fallback">OpenStreetMap을 불러오지 못했습니다.</div>');return;}safeMap=L.map(mapEl,{zoomControl:true,scrollWheelZoom:true}).setView([lat,lng],15);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(safeMap);L.control.scale({metric:true,imperial:false}).addTo(safeMap);safeMarker=L.marker([lat,lng]).addTo(safeMap);safeCircle=L.circle([lat,lng],{radius:500,color:'#2563eb',weight:2,fillColor:'#2563eb',fillOpacity:.12}).addTo(safeMap);safeFeatureLayer=L.layerGroup().addTo(safeMap);safeMap.on('click',event=>{scrollMapToCenterOnce();setCoordinates(event.latlng.lat,event.latlng.lng,{message:'지도에서 선택한 좌표의 공간 데이터를 조회합니다.',preview:true})});scheduleMapResize()}
      function updateMap(){const lat=Number(latEl.value),lng=Number(lngEl.value);if(!Number.isFinite(lat)||!Number.isFinite(lng))return;mapLabelEl.textContent=`${lat.toFixed(4)}, ${lng.toFixed(4)} · 500m`;if(safeMap&&safeMarker&&safeCircle){const point=[lat,lng];safeMarker.setLatLng(point);safeCircle.setLatLng(point);safeCircle.setRadius(500);safeMap.setView(point,safeMap.getZoom()||15,{animate:true});scheduleMapResize();}}
      function setCoordinates(lat,lng,options={}){if(!Number.isFinite(lat)||!Number.isFinite(lng))return;latEl.value=Number(lat).toFixed(6);lngEl.value=Number(lng).toFixed(6);updateMap();loadLegalDong(lat,lng);if(options.message)messageEl.textContent=options.message;if(options.preview)loadSpatialPreview();if(options.analyze)runAnalysis()}
      function markerIcon(category){return L.divIcon({className:`safe-agent-div-icon ${category==='shelter'?'shelter':'risk'}`,html:'<span></span>',iconSize:[18,18],iconAnchor:[9,9]})}
      function renderMapFeatures(data){if(!safeFeatureLayer||!window.L)return;safeFeatureLayer.clearLayers();const features=(data.spatial_summary?.map_features||[]).filter(item=>Number.isFinite(Number(item.lat))&&Number.isFinite(Number(item.lng)));for(const feature of features){const popup=`<strong>${escapeHtml(feature.kind||feature.category)}</strong><br>${escapeHtml(feature.label||'항목')}<br>${feature.distance_m!=null?`${escapeHtml(feature.distance_m)}m`:''}`;L.marker([Number(feature.lat),Number(feature.lng)],{icon:markerIcon(feature.category)}).bindPopup(popup).addTo(safeFeatureLayer)}}
      function rainNumber(value){const n=Number(String(value??'0').replace(/[^0-9.]/g,''));return Number.isFinite(n)?n:0}
      function optionalNumber(value){if(value===null||value===undefined||value==='')return null;const n=Number(value);return Number.isFinite(n)?n:null}
      function rainSeries(rain){
        const fallback=[-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6].map(offset=>{const known=offset>=0&&offset<=3;return{offset,label:offset===0?'현재':`${offset>0?'+':''}${offset}H`,value:known?(offset===0?rain.rain_current:(offset===1?rain.rain_1h_after:(offset===2?rain.rain_2h_after:rain.rain_3h_after))):'-',value_mm:null,time:'',source:known?'legacy':'none'}});
        const source=Array.isArray(rain.rain_hourly)&&rain.rain_hourly.length?rain.rain_hourly:fallback;
        return source.map((item,index)=>{
          const offset=Number.isFinite(Number(item.offset))?Number(item.offset):index-6,missing=item.source==='none'||item.source==='spatial_only'||item.value==='-'||((item.value===null||item.value===undefined||item.value==='')&&item.value_mm===null);
          const value=missing?'-':(item.value??item.value_mm??'0mm'),valueMm=missing?null:(item.value_mm!==undefined&&Number.isFinite(Number(item.value_mm))?Number(item.value_mm):rainNumber(value));
          return{offset,label:item.label||(offset===0?'현재':`${offset>0?'+':''}${offset}H`),time:item.time||'',value,valueMm,temperatureC:optionalNumber(item.temperature_c),humidityPct:optionalNumber(item.humidity_pct),windSpeedMs:optionalNumber(item.wind_speed_ms),windDirectionDeg:optionalNumber(item.wind_direction_deg),precipitationTypeLabel:item.precipitation_type_label||'',precipitationProbabilityPct:optionalNumber(item.precipitation_probability_pct),lightningCode:optionalNumber(item.lightning_code),skyLabel:item.sky_label||''}
        })
      }
      function weatherAxisTime(item){const raw=String(item.time||'').trim(),clock=(raw.split(' ').pop()||'').slice(0,5);return /^\d{2}:\d{2}$/.test(clock)?`${clock.slice(0,2)}시`:item.label}
      function weatherIcon(item){if(item.lightningCode)return '⚡';const type=item.precipitationTypeLabel||'';if(type.includes('눈'))return '❄';if(type.includes('비')||type.includes('빗')||(item.valueMm!==null&&item.valueMm>0))return '☂';if(item.skyLabel==='맑음')return '☀';if(item.skyLabel==='구름많음')return '⛅';if(item.skyLabel==='흐림')return '☁';if(type==='없음')return '○';return '·'}
      function weatherTooltip(item){const parts=[item.time||item.label,item.valueMm===null?'강수 자료 없음':`강수 ${item.value}`];if(item.temperatureC!==null)parts.push(`기온 ${item.temperatureC}°C`);if(item.humidityPct!==null)parts.push(`습도 ${item.humidityPct}%`);if(item.windSpeedMs!==null)parts.push(`풍속 ${item.windSpeedMs}m/s${item.windDirectionDeg!==null?` · ${item.windDirectionDeg}°`:''}`);if(item.precipitationTypeLabel)parts.push(`강수형태 ${item.precipitationTypeLabel}`);if(item.precipitationProbabilityPct!==null)parts.push(`강수확률 ${item.precipitationProbabilityPct}%`);if(item.lightningCode)parts.push(`낙뢰 ${item.lightningCode}`);return parts.join(' · ')}
      function weatherSegments(points,key){const segments=[];let current=[];for(const point of points){if(point[key]===null){if(current.length)segments.push(current);current=[]}else current.push(point)}if(current.length)segments.push(current);return segments}
      function chartAxisValue(value,unit){if(value===null||value===undefined)return '-';const text=Number.isInteger(value)?value.toFixed(0):value.toFixed(1);return `${text}${unit}`}
      function renderRainChart(rain){
        const items=rainSeries(rain||{}),rainValues=items.map(item=>item.valueMm).filter(value=>value!==null),rainDataMax=rainValues.length?Math.max(...rainValues):null,rainScaleMax=Math.max(1,rainDataMax??0),temperatures=items.map(item=>item.temperatureC).filter(value=>value!==null);
        const tempDataMin=temperatures.length?Math.min(...temperatures):null,tempDataMax=temperatures.length?Math.max(...temperatures):null,tempPadding=temperatures.length?(tempDataMax===tempDataMin?1:Math.max(.5,(tempDataMax-tempDataMin)*.15)):0,tempAxisMin=temperatures.length?Math.floor((tempDataMin-tempPadding)*10)/10:0,tempAxisMax=temperatures.length?Math.ceil((tempDataMax+tempPadding)*10)/10:1,tempRange=Math.max(1,tempAxisMax-tempAxisMin);
        const width=560,height=124,left=42,right=42,iconY=16,top=34,bottom=98,mid=(top+bottom)/2,usableWidth=width-left-right;
        const points=items.map((item,index)=>{const x=left+(usableWidth*(items.length===1?0:index/(items.length-1))),rainY=item.valueMm===null?null:bottom-((item.valueMm/rainScaleMax)*(bottom-top)),tempY=item.temperatureC===null?null:bottom-(((item.temperatureC-tempAxisMin)/tempRange)*(bottom-top));return{x,rainY,tempY,item}});
        const rainSegments=weatherSegments(points,'rainY'),tempSegments=weatherSegments(points,'tempY'),coords=(segment,key)=>segment.map(point=>`${point.x.toFixed(1)},${point[key].toFixed(1)}`).join(' ');
        const rainAreas=rainSegments.map(segment=>`<polygon class="safe-agent-rain-area" points="${segment[0].x.toFixed(1)},${bottom} ${coords(segment,'rainY')} ${segment[segment.length-1].x.toFixed(1)},${bottom}"></polygon>`).join(''),rainLines=rainSegments.filter(segment=>segment.length>1).map(segment=>`<polyline class="safe-agent-rain-line" points="${coords(segment,'rainY')}"></polyline>`).join(''),tempLines=tempSegments.filter(segment=>segment.length>1).map(segment=>`<polyline class="safe-agent-temp-line" points="${coords(segment,'tempY')}"></polyline>`).join('');
        const currentPoint=points.find(point=>point.item.offset===0)||points[Math.floor(points.length/2)]||{x:width/2,item:{}};
        const icons=points.map(point=>`<text class="safe-agent-weather-icon ${point.item.offset===0?'current':''}" x="${point.x.toFixed(1)}" y="${iconY}" text-anchor="middle"><title>${escapeHtml(weatherTooltip(point.item))}</title>${escapeHtml(weatherIcon(point.item))}</text>`).join('');
        const rainDots=points.filter(point=>point.rainY!==null).map(point=>`<circle class="safe-agent-rain-dot" cx="${point.x.toFixed(1)}" cy="${point.rainY.toFixed(1)}" r="3"><title>${escapeHtml(weatherTooltip(point.item))}</title></circle>`).join(''),tempDots=points.filter(point=>point.tempY!==null).map(point=>`<circle class="safe-agent-temp-dot" cx="${point.x.toFixed(1)}" cy="${point.tempY.toFixed(1)}" r="3"><title>${escapeHtml(weatherTooltip(point.item))}</title></circle>`).join('');
        const axis=items.map(item=>`<span class="${item.offset===0?'current':''}" title="${escapeHtml(item.time)}">${escapeHtml(weatherAxisTime(item))}</span>`).join(''),rainAxis=[rainScaleMax,rainScaleMax/2,0],tempAxis=temperatures.length?[tempAxisMax,(tempAxisMax+tempAxisMin)/2,tempAxisMin]:[null,null,null],axisY=[top,mid,bottom];
        const axisLabels=axisY.map((y,index)=>`<text class="safe-agent-chart-axis rain" x="${left-7}" y="${y+3}" text-anchor="end">${chartAxisValue(rainAxis[index],'mm')}</text><text class="safe-agent-chart-axis temp" x="${width-right+7}" y="${y+3}" text-anchor="start">${chartAxisValue(tempAxis[index],'°C')}</text>`).join('');
        const rainPeak=rainDataMax===null?'강수 자료 없음':`${chartAxisValue(rainDataMax,'mm')} max`,tempRangeText=temperatures.length?`${tempDataMin.toFixed(1)}~${tempDataMax.toFixed(1)}°C`:'기온 없음',currentWeather=[currentPoint.item.temperatureC!==null&&currentPoint.item.temperatureC!==undefined?`${currentPoint.item.temperatureC}°C`:'',currentPoint.item.humidityPct!==null&&currentPoint.item.humidityPct!==undefined?`습도 ${currentPoint.item.humidityPct}%`:'',currentPoint.item.windSpeedMs!==null&&currentPoint.item.windSpeedMs!==undefined?`풍속 ${currentPoint.item.windSpeedMs}m/s`:''].filter(Boolean).join(' · ');
        return `<article class="safe-agent-rain-card"><div class="safe-agent-rain-head"><strong>강수·기온 추계</strong><div class="safe-agent-weather-legend"><span><i class="rain"></i>강수</span><span><i class="temp"></i>기온</span></div><span>${escapeHtml(currentWeather||rain.status||'spatial')}</span><b class="safe-agent-rain-peak">${rainPeak} · ${tempRangeText}</b></div><div class="safe-agent-rain-graph"><svg class="safe-agent-rain-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="실제 시각별 강수량과 기온, 날씨 아이콘과 좌우 수치축">${icons}<line class="safe-agent-rain-grid" x1="${left}" y1="${bottom}" x2="${width-right}" y2="${bottom}"></line><line class="safe-agent-rain-grid" x1="${left}" y1="${mid}" x2="${width-right}" y2="${mid}"></line><line class="safe-agent-rain-grid" x1="${left}" y1="${top}" x2="${width-right}" y2="${top}"></line><line class="safe-agent-rain-now" x1="${currentPoint.x.toFixed(1)}" y1="${top-8}" x2="${currentPoint.x.toFixed(1)}" y2="${bottom}"></line>${axisLabels}${rainAreas}${rainLines}${rainDots}${tempLines}${tempDots}</svg><div class="safe-agent-rain-axis">${axis}</div></div></article>`
      }
      function coordsOf(data){const lat=Number(data?.lat),lng=Number(data?.lng);return {lat:Number.isFinite(lat)?lat:Number(latEl.value),lng:Number.isFinite(lng)?lng:Number(lngEl.value)}}
      function sameCoords(a,b){return !!(a&&b)&&Math.abs(Number(a.lat)-Number(b.lat))<0.000001&&Math.abs(Number(a.lng)-Number(b.lng))<0.000001}
      function renderStatus(data){const coords=coordsOf(data),incomingRain=data.rain_info||null;let spatial=data.spatial_summary||null;if(spatial){lastSpatialSummary=spatial;lastSpatialCoords=coords}else if(sameCoords(lastSpatialCoords,coords)){spatial=lastSpatialSummary}spatial=spatial||{};if(incomingRain&&incomingRain.status!=='spatial_only'){lastRainInfo=incomingRain;lastRainCoords=coords}let rain=incomingRain||{};if((!incomingRain||incomingRain.status==='spatial_only')&&sameCoords(lastRainCoords,coords))rain=lastRainInfo||rain;const riskTotal=(spatial.floods_count||0)+(spatial.landslides_count||0)+(spatial.vulnerable_count||0);statusEl.innerHTML=`${renderRainChart(rain)}<article class="safe-agent-status-card"><b>${riskTotal}</b><span>위험이력</span></article><article class="safe-agent-status-card"><b>${spatial.shelters_count||0}</b><span>대피소</span></article>`}
      function detailFieldsHtml(fields){const entries=Object.entries(fields||{}).filter(([,value])=>value!==null&&value!==undefined&&String(value).trim()!=='');return entries.length?`<dl class="safe-agent-detail-fields">${entries.map(([key,value])=>`<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl>`:''}
      function renderDetailList(items=[],type='risk'){if(!items.length)return '<div class="safe-agent-detail-empty">표시할 실제 데이터가 없습니다.</div>';return `<div class="safe-agent-detail-list">${items.map(item=>{const meta=[];if(type==='risk'&&item.date)meta.push(`<span>날짜 ${escapeHtml(item.date)}</span>`);if(item.distance_m!==null&&item.distance_m!==undefined)meta.push(`<span>직선 ${escapeHtml(item.distance_m)}m</span>`);if(item.address)meta.push(`<span>${escapeHtml(item.address)}</span>`);if(item.lat&&item.lng)meta.push(`<span>${Number(item.lat).toFixed(5)}, ${Number(item.lng).toFixed(5)}</span>`);return `<article class="safe-agent-detail-item"><strong>${escapeHtml(item.label||item.kind||'항목')}</strong>${meta.length?`<div class="safe-agent-detail-meta">${meta.join('')}</div>`:''}${detailFieldsHtml(item.fields)}</article>`}).join('')}</div>`}
      function renderDetailSection(title,count,items,type='risk'){return `<details class="safe-agent-detail-section"><summary><span>${escapeHtml(title)}</span><b class="safe-agent-detail-count">${Number(count||0).toLocaleString()}건</b></summary>${renderDetailList(items||[],type)}</details>`}
      function resultDataHtml(data){const spatial=data.spatial_summary||{},nearest=spatial.nearest_shelter,details=spatial.details||{};const riskMapCount=(spatial.map_features||[]).filter(x=>x.category==='risk').length,shelterMapCount=(spatial.map_features||[]).filter(x=>x.category==='shelter').length;const sections=[renderDetailSection('침수 흔적',spatial.floods_count,details.floods,'risk'),renderDetailSection('산사태 발생/우려',spatial.landslides_count,details.landslides,'risk'),renderDetailSection('인명피해 우려구역',spatial.vulnerable_count,details.vulnerable,'risk'),renderDetailSection('대피소',spatial.shelters_count,details.shelters,'shelter')].join('');return `<article><h3>분석 데이터</h3><div class="safe-agent-list"><div><span>사용 PKL</span><b>${escapeHtml(data.kb_filename||data.kb_status?.filename||'없음')}</b></div><div><span>분석 좌표</span><b>${Number(data.lat).toFixed(6)}, ${Number(data.lng).toFixed(6)}</b></div><div><span>지도 표기</span><b>위험 ${riskMapCount}건 · 대피소 ${shelterMapCount}건</b></div><div><span>가장 가까운 대피소</span><b>${nearest?escapeHtml((nearest.REARE_NM||nearest.VT_ACM_PLC_NM||'대피소')+' · 직선 '+nearest.distance_m+'m'):'없음'}</b></div></div><div class="safe-agent-detail-sections">${sections}</div></article>`}
      function renderSpatialResult(data){resultEl.innerHTML=`<article class="safe-agent-report"><h3>공간 데이터 빠른 조회</h3><div class="safe-agent-badges"><span class="safe-agent-badge">PKL MEMORY</span><span class="safe-agent-badge">500M RADIUS</span></div><pre>지도 클릭 좌표의 위험 요소와 대피소를 표시했습니다. 기상 정보와 보고서는 분석 실행 버튼을 눌러 생성하세요.</pre></article>${resultDataHtml(data)}`}
      function renderResult(data){const rain=data.rain_info||{},config=data.config_status||{};const model=data.model||modelEl.options[modelEl.selectedIndex]?.textContent||'AI 모델';const keyBadges=`<div class="safe-agent-badges"><span class="safe-agent-badge ${config.kma_key?'ok':'warn'}">KMA ${config.kma_key?'KEY OK':'KEY EMPTY'}</span><span class="safe-agent-badge ${config.hf_key?'ok':'warn'}">HF ${config.hf_key?'KEY OK':'KEY EMPTY'}</span><span class="safe-agent-badge ${config.openrouter_key?'ok':'warn'}">OR ${config.openrouter_key?'KEY OK':'KEY EMPTY'}</span><span class="safe-agent-badge">${escapeHtml(model)}</span><span class="safe-agent-badge">${escapeHtml(rain.status||'status unknown')}</span></div>`;resultEl.innerHTML=`<article class="safe-agent-report"><h3>AI 안전비서</h3>${keyBadges}<pre>${escapeHtml(data.report||'보고서가 비어 있습니다.')}</pre></article>${resultDataHtml(data)}`}
      function currentCoordsMatch(data){return Math.abs(Number(data.lat)-Number(latEl.value))<0.000001&&Math.abs(Number(data.lng)-Number(lngEl.value))<0.000001}
      async function loadRainPreview(){const lat=Number(latEl.value),lng=Number(lngEl.value);if(!Number.isFinite(lat)||!Number.isFinite(lng))return null;const requestId=++rainRequestSeq;messageEl.textContent='기상청 강수·기온 추계를 먼저 가져오는 중...';const r=await fetch('/api/poc/ai-safe-agent/rain',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat,lng})});const data=await readJsonResponse(r);if(requestId!==rainRequestSeq)return null;if(!r.ok)throw new Error(data.error||'기상청 기상 정보 조회에 실패했습니다.');if(!currentCoordsMatch(data))return null;renderStatus(data);messageEl.textContent='기상청 강수·기온 추계 표기 완료 · AI 보고서 생성 중...';return data}
      async function loadSpatialPreview(){const lat=Number(latEl.value),lng=Number(lngEl.value);if(!Number.isFinite(lat)||!Number.isFinite(lng))return;const requestId=++spatialRequestSeq;messageEl.textContent='공간 데이터 조회 중...';try{const r=await fetch('/api/poc/ai-safe-agent/spatial',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat,lng})});const data=await readJsonResponse(r);if(requestId!==spatialRequestSeq)return;if(!r.ok)throw new Error(data.error||'공간 데이터 조회에 실패했습니다.');if(data.kb_status)setKbStatus(data.kb_status);renderStatus(data);renderMapFeatures(data);renderSpatialResult(data);messageEl.textContent='공간 데이터 표시 완료';}catch(e){if(requestId!==spatialRequestSeq)return;messageEl.textContent='공간 데이터 조회 실패';resultEl.innerHTML=`<div class="safe-agent-empty">${escapeHtml(e.message)}</div>`}}
      async function loadAiSafeModels(){try{const r=await fetch('/api/poc/ai-safe-agent/models');const data=await readJsonResponse(r);if(!r.ok)throw new Error(data.error||'모델 목록을 불러오지 못했습니다.');modelEl.innerHTML=(data.models||[]).map(item=>`<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}${item.details?.parameter_size?' · '+escapeHtml(item.details.parameter_size):''}</option>`).join('')||'<option value="">모델 없음</option>';if(data.default)modelEl.value=data.default;}catch(e){modelEl.innerHTML='<option value="huggingface:Qwen/Qwen2.5-72B-Instruct">Hugging Face · Qwen/Qwen2.5-72B-Instruct</option><option value="openrouter:openai/gpt-4o-mini">OpenRouter · openai/gpt-4o-mini</option>';appendDataLog(`AI 모델 목록 조회 실패: ${e.message}`)}}
      async function loadLegalDong(lat=Number(latEl.value),lng=Number(lngEl.value)){if(!reverseGeocodeEnabled||!Number.isFinite(lat)||!Number.isFinite(lng))return;const requestId=++geocodeRequestSeq;addressEl.value='법정동 확인 중';try{const r=await fetch('/api/poc/ai-safe-agent/reverse-geocode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat,lng})});const data=await readJsonResponse(r);if(requestId!==geocodeRequestSeq)return;if(!r.ok||data.status==='error'){addressEl.value='법정동 확인 실패';appendDataLog(`법정동 확인 실패: ${data.message||data.error||r.status}`);return;}addressEl.value=data.legal_dong||data.address||'확인 불가';if(data.provider==='openstreetmap')appendDataLog(`법정동 대체 조회 완료: ${addressEl.value}`);}catch(e){if(requestId!==geocodeRequestSeq)return;addressEl.value='법정동 확인 실패';appendDataLog(`법정동 확인 실패: ${e.message}`)}}
      function loadDefaultLocation(message='기본 좌표로 공간 데이터를 조회합니다.'){updateMap();loadLegalDong();loadSpatialPreview();messageEl.textContent=message}
      function useGpsLocation(options={}){const auto=!!options.auto;setGpsPopup(true);if(!navigator.geolocation){setGpsPopup(false);if(auto){loadDefaultLocation('GPS를 사용할 수 없어 기본 좌표로 시작합니다.');return;}alert('이 브라우저에서는 위치 정보를 사용할 수 없습니다.');return;}gpsButton.disabled=true;messageEl.textContent='GPS 기반 장소로 이동 중입니다.';navigator.geolocation.getCurrentPosition(position=>{gpsButton.disabled=false;setGpsPopup(false);const lat=position.coords.latitude,lng=position.coords.longitude,accuracy=Math.round(position.coords.accuracy||0);const message=auto?`현재 GPS 위치로 시작합니다${accuracy?` · 정확도 약 ${accuracy}m`:''}.`:`GPS 위치로 이동했습니다${accuracy?` · 정확도 약 ${accuracy}m`:''}.`;setCoordinates(lat,lng,{message,preview:true});},error=>{gpsButton.disabled=false;setGpsPopup(false);const messages={1:'위치 권한이 거부되었습니다.',2:'현재 위치를 확인할 수 없습니다.',3:'위치 확인 시간이 초과되었습니다.'};const message=messages[error.code]||'GPS 위치 확인에 실패했습니다.';if(auto){loadDefaultLocation(`${message} 기본 좌표로 시작합니다.`);return;}messageEl.textContent=message;alert(messageEl.textContent);},{enableHighAccuracy:true,timeout:12000,maximumAge:30000})}
      async function runAnalysis(){if(analysisRunning){analysisController?.abort();messageEl.textContent='AI 보고서 생성을 중지하는 중...';return;}const lat=Number(latEl.value),lng=Number(lngEl.value),use_ai=true,ai_model=modelEl.value;if(!Number.isFinite(lat)||!Number.isFinite(lng)||lat<-90||lat>90||lng<-180||lng>180){alert('올바른 위도와 경도를 입력하세요.');return;}analysisRunning=true;analysisController=new AbortController();updateMap();runButton.disabled=false;runButton.classList.add('is-stop');runButton.textContent='생성 중지';resultEl.innerHTML='<div class="safe-agent-empty">기상청 강수·기온 추계를 먼저 업데이트한 뒤 공간 데이터와 AI 답변을 실시간으로 생성합니다.</div>';let rainData=null,answer='',reportPre=null,finalEvent=null;try{try{rainData=await loadRainPreview()}catch(rainError){appendDataLog(`기상청 기상 정보 조회 실패: ${rainError.message}`);messageEl.textContent='기상청 기상 정보 조회 실패 · 공간/AI 분석을 계속합니다.'}lastAnalysisRequest={lat,lng,use_ai,ai_model,rain_info:rainData?.rain_info||null};messageEl.textContent='공간 데이터를 정리하고 AI 답변을 생성하는 중...';const r=await fetch('/api/poc/ai-safe-agent/analyze-stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lastAnalysisRequest),signal:analysisController.signal});if(!r.ok){const data=await readJsonResponse(r);throw new Error(data.error||'분석 실행에 실패했습니다.')}if(!r.body)throw new Error('실시간 AI 응답을 받을 수 없습니다.');const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';const handleEvent=event=>{if(event.type==='context'){const data={...(event.data||{}),model:event.model,report:'AI 답변 생성 중...'};if(!currentCoordsMatch(data))throw new Error('분석 중 좌표가 변경되었습니다.');if(data.kb_status)setKbStatus(data.kb_status);renderStatus(data);renderMapFeatures(data);renderResult(data);reportPre=resultEl.querySelector('.safe-agent-report pre');messageEl.textContent='AI 답변을 실시간으로 표시하는 중...';}else if(event.type==='token'){answer+=event.content||'';if(reportPre)reportPre.textContent=answer;}else if(event.type==='done'){finalEvent=event;}else if(event.type==='error'){throw new Error(event.error||'AI 보고서 생성 실패')}};while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines){if(line.trim())handleEvent(JSON.parse(line))}}buffer+=decoder.decode();if(buffer.trim())handleEvent(JSON.parse(buffer));if(!answer)throw new Error('AI 보고서 내용이 비어 있습니다.');const seconds=finalEvent?.metrics?.total_duration?finalEvent.metrics.total_duration/1e9:null;messageEl.textContent=seconds?`분석 완료 · AI 생성 ${seconds.toFixed(1)}초`:'분석 완료';}catch(e){if(e.name==='AbortError'){messageEl.textContent='AI 보고서 생성을 중지했습니다.';if(reportPre&&!answer)reportPre.textContent='생성이 중지되었습니다.';}else{messageEl.textContent='분석 실패';if(reportPre)reportPre.textContent=answer||`오류: ${e.message}`;else resultEl.innerHTML=`<div class="safe-agent-empty">${escapeHtml(e.message)}</div>`}}finally{analysisRunning=false;analysisController=null;runButton.classList.remove('is-stop');runButton.textContent='분석 실행';runButton.disabled=false}}
      async function buildKnowledgeBase(){buildDataButton.disabled=true;refreshKbButton.disabled=true;runButton.disabled=true;gpsButton.disabled=true;savePresetButton.disabled=true;appendDataLog('기초 데이터 만들기 시작',true);try{const r=await fetch('/api/poc/ai-safe-agent/kb/build',{method:'POST'});if(!r.ok&&!r.body){const data=await readJsonResponse(r);throw new Error(data.error||'기초 데이터 생성 실패')}if(!r.body){const data=await readJsonResponse(r);setKbStatus(data);appendDataLog(data.message||'기초 데이터 생성 완료');return;}const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines){if(!line.trim())continue;const event=JSON.parse(line);if(event.type==='log')appendDataLog(event.message);else if(event.type==='done'){setKbStatus(event.status);appendDataLog(event.status?.message||'기초 데이터 생성 완료')}else if(event.type==='error')throw new Error(event.error||'기초 데이터 생성 실패')}}if(buffer.trim()){const event=JSON.parse(buffer);if(event.type==='done'){setKbStatus(event.status);appendDataLog(event.status?.message||'기초 데이터 생성 완료')}}}catch(e){appendDataLog(`오류: ${e.message}`);alert(e.message)}finally{buildDataButton.disabled=false;refreshKbButton.disabled=false;runButton.disabled=false;gpsButton.disabled=false;savePresetButton.disabled=false}}
      async function refreshKnowledgeBase(){refreshKbButton.disabled=true;try{appendDataLog('PKL 상태 새로고침');await loadKbStatus(true);if(lastAnalysisRequest){await runAnalysis()}else{await loadSpatialPreview();messageEl.textContent='PKL 상태를 다시 읽고 지도 데이터를 갱신했습니다.'}}catch(e){appendDataLog(`오류: ${e.message}`);alert(e.message)}finally{refreshKbButton.disabled=false}}
      presetsEl.onclick=event=>{const deleteButton=event.target.closest('[data-delete-preset-index]');if(deleteButton){const presets=loadPresets();presets.splice(Number(deleteButton.dataset.deletePresetIndex),1);savePresets(presets);renderPresets();return;}const button=event.target.closest('[data-preset-index]');if(!button)return;const item=loadPresets()[Number(button.dataset.presetIndex)];if(item)setCoordinates(item.lat,item.lng,{message:`${item.name} 좌표를 불러왔습니다.`})};
      savePresetButton.onclick=()=>{const name=placeNameEl.value.trim();const lat=Number(latEl.value),lng=Number(lngEl.value);if(!name){alert('저장할 장소명을 입력하세요.');placeNameEl.focus();return;}if(!Number.isFinite(lat)||!Number.isFinite(lng)){alert('저장할 좌표가 올바르지 않습니다.');return;}const presets=loadPresets();const existing=presets.findIndex(item=>item.name===name);const saved={name,lat,lng};if(existing>=0)presets[existing]=saved;else presets.push(saved);savePresets(presets);renderPresets();placeNameEl.value='';messageEl.textContent=`${name} 좌표를 저장했습니다.`};
      dataHeadEl.addEventListener('click',event=>{if(event.target.closest('button'))return;toggleDataLog()});dataHeadEl.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&!event.target.closest('button')){event.preventDefault();toggleDataLog()}});dataLogToggle.onclick=event=>{event.stopPropagation();toggleDataLog()};latEl.oninput=updateMap;lngEl.oninput=updateMap;runButton.onclick=runAnalysis;gpsButton.onclick=useGpsLocation;buildDataButton.onclick=buildKnowledgeBase;refreshKbButton.onclick=refreshKnowledgeBase;initMap();renderPresets();updateMap();addEventListener('resize',scheduleMapResize);loadAiSafeModels();loadKbStatus().catch(e=>appendDataLog(`PKL 상태 확인 실패: ${e.message}`,true));useGpsLocation({auto:true});
    }

    function renderMoisKmsLab(p){
      projectDefaultView.classList.add("hidden");
      projectLab.classList.add("active");
      projectLab.innerHTML=`<section class="field-inspection-lab"><div class="field-inspection-toolbar"><div><strong>MoIS KMS · 통합 업무관리시스템</strong><span id="moisKmsStatus">Supabase 인증과 업무 데이터를 연결하는 중입니다.</span></div><a class="field-inspection-open" href="/poc/mois-kms/" target="_blank" rel="noopener">새 창에서 크게 보기 ↗</a></div><div class="field-inspection-policy">사용자 로그인·조직별 RLS·결재 흐름 적용 · AI 보고서는 Local LLM, Hugging Face, OpenRouter 중 선택할 수 있습니다.</div><div class="field-inspection-frame-wrap"><iframe class="field-inspection-frame" id="moisKmsFrame" src="/poc/mois-kms/" title="통합 업무관리시스템" loading="eager"></iframe></div></section>`;
      const frame=document.getElementById("moisKmsFrame"),status=document.getElementById("moisKmsStatus");
      frame.addEventListener("load",()=>{status.textContent="통합 업무관리시스템 연결 완료 · 로그인 후 업무와 AI 보고서를 이용하세요."},{once:true});
    }

    function renderMasterPressLab(p){
      projectDefaultView.classList.add("hidden");
      projectLab.classList.add("active");
      projectLab.innerHTML=`<section class="field-inspection-lab"><div class="field-inspection-toolbar"><div><strong>04 · 마스터언론</strong><span id="masterPressStatus">뉴스 모니터링 대시보드를 연결하는 중입니다.</span></div><a class="field-inspection-open" href="/poc/master-press/" target="_blank" rel="noopener">새 창에서 크게 보기 ↗</a></div><div class="field-inspection-policy">공식 검색 API·RSS 우선 · 키워드/임베딩/LLM 복합 관련도 · 개인별 카카오 나에게 보내기</div><div class="field-inspection-frame-wrap"><iframe class="field-inspection-frame" id="masterPressFrame" src="/poc/master-press/" title="마스터언론" loading="eager"></iframe></div></section>`;
      const frame=document.getElementById("masterPressFrame"),status=document.getElementById("masterPressStatus");
      frame.addEventListener("load",()=>{status.textContent="마스터언론 연결 완료 · 공개 대시보드와 관리자 설정을 이용할 수 있습니다."},{once:true});
    }

    function renderMultiAgentHarnessLab(p){
      projectDefaultView.classList.add("hidden");
      projectLab.classList.add("active");
      projectLab.innerHTML=`<section class="field-inspection-lab"><div class="field-inspection-toolbar"><div><strong>03 · 계층형 멀티에이전트 상황실</strong><span id="multiagentHarnessStatus">하네스 이벤트와 픽셀 오피스를 연결하는 중입니다.</span></div><a class="field-inspection-open" href="/portfolio/multiagent-harness/" target="_blank" rel="noopener">새 창에서 크게 보기 ↗</a></div><div class="field-inspection-policy">계층형 Coordinator · 공용 Agent Pool · Local LLM/Hugging Face/OpenRouter 슬롯 제어 · 대면 문서 전달 시각화</div><div class="field-inspection-frame-wrap"><iframe class="field-inspection-frame" id="multiagentHarnessFrame" src="/portfolio/multiagent-harness/" title="계층형 멀티에이전트 하네스" loading="eager"></iframe></div></section>`;
      const frame=document.getElementById("multiagentHarnessFrame"),status=document.getElementById("multiagentHarnessStatus");
      frame.addEventListener("load",()=>{status.textContent="픽셀 오피스 연결 완료 · 계층형 데모를 실행할 수 있습니다."},{once:true});
    }

    function renderFieldInspectionLab(p){
      projectDefaultView.classList.add("hidden");
      projectLab.classList.add("active");
      projectLab.innerHTML=`<section class="field-inspection-lab"><div class="field-inspection-toolbar"><div><strong>재난안전정보시스템 · 현장점검 지원플랫폼</strong><span id="fieldInspectionStatus">기존 서비스 경로에서 Supabase 연결 화면을 불러오는 중입니다.</span></div><a class="field-inspection-open" href="/poc/field-inspection-platform/" target="_blank" rel="noopener">새 창에서 크게 보기 ↗</a></div><div class="field-inspection-policy">공개 PoC 운영 중 · 현재 관리자 메뉴와 데이터 등록·수정·삭제 기능이 공개되어 있습니다. 운영 전 사용자 로그인과 역할별 권한을 적용할 예정입니다.</div><div class="field-inspection-frame-wrap"><iframe class="field-inspection-frame" id="fieldInspectionFrame" src="/poc/field-inspection-platform/" title="현장점검 지원플랫폼" loading="eager"></iframe></div></section>`;
      const frame=document.getElementById("fieldInspectionFrame"),status=document.getElementById("fieldInspectionStatus");
      frame.addEventListener("load",()=>{status.textContent="현장점검 플랫폼 연결 완료 · Supabase 기존 데이터를 사용합니다."},{once:true});
    }

    function renderReportDraftLab(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="report-draft-lab"><div class="report-draft-head"><div><h3>민원 회신 초안 생성</h3><p>XML 민원자료를 선택한 뒤 서버의 로컬 Ollama 모델로 검토 전 초안을 만듭니다.</p></div><span class="report-draft-health" id="reportDraftHealth">모델 확인 중</span></div><div class="report-draft-grid"><article class="report-draft-panel"><h4>요청</h4><div class="report-draft-presets"><button type="button" data-report-preset="공원 야간 소음 민원에 대해 순찰 강화와 안내문 부착 계획을 포함한 민원 회신 초안을 작성해 주세요.">공원 야간 소음 민원</button><button type="button" data-report-preset="7월 18일 10시부터 15시까지 상수도 공사로 일부 지역 단수가 예정된다는 주민 안내문 초안을 작성해 주세요.">상수도 공사 단수 안내</button></div><label>요청 내용<textarea id="reportDraftRequest" maxlength="8000">공원 야간 소음 민원에 대해 순찰 강화와 안내문 부착 계획을 포함한 민원 회신 초안을 작성해 주세요.</textarea></label><div class="report-draft-model-row"><label>로컬 LLM<select id="reportDraftModel"><option value="">설치 모델 불러오는 중...</option></select></label><button class="report-draft-option-button" id="reportDraftOpenOptions" type="button">모델 옵션</button></div><div class="report-draft-option-summary" id="reportDraftOptionSummary">옵션 확인 중...</div><div class="report-draft-actions"><button class="report-draft-generate" id="reportDraftGenerate" type="button" disabled>초안 생성</button><span class="report-draft-status" id="reportDraftStatus">Ollama 모델을 확인하고 있습니다.</span></div></article><article class="report-draft-panel"><h4>응답 결과</h4><div class="report-draft-meta"><div><span>선택 자료</span><b id="reportDraftCase">-</b></div><div><span>담당부서</span><b id="reportDraftDepartment">-</b></div><div><span>문의처</span><b id="reportDraftContact">-</b></div></div><pre class="report-draft-answer" id="reportDraftAnswer">생성된 초안이 이곳에 표시됩니다.</pre><div class="report-draft-review" id="reportDraftReview">담당자 검토 필요: 생성 결과의 사실관계와 법령 근거를 확인하세요.</div></article></div><dialog class="report-draft-dialog" id="reportDraftOptions"><div class="report-draft-dialog-box"><div class="report-draft-dialog-head"><div><h4>모델 생성 옵션</h4><p>현재 브라우저에 저장되며 보고서 생성 요청에만 적용됩니다.</p></div><button class="report-draft-dialog-close" id="reportDraftCloseOptions" type="button" aria-label="닫기">×</button></div><div class="report-draft-option-grid"><label>Temperature<input id="reportDraftTemperature" type="number" min="0" max="2" step="0.1"></label><label>최대 생성 토큰<input id="reportDraftNumPredict" type="number" min="500" max="4096" step="100"></label><label>Context 크기<input id="reportDraftNumCtx" type="number" min="512" max="32768" step="256"></label><label class="report-draft-system-prompt">시스템 프롬프트<textarea id="reportDraftSystemPrompt" maxlength="4000" spellcheck="false"></textarea><small>최대 4,000자 · 출력 JSON 규칙을 변경하면 초안 형식이 달라질 수 있습니다.</small></label></div><div class="report-draft-dialog-actions"><button class="report-draft-secondary" id="reportDraftResetOptions" type="button">기본값</button><button class="report-draft-secondary save" id="reportDraftSaveOptions" type="button">적용</button></div></div></dialog></section>`;
      const requestEl=document.getElementById('reportDraftRequest'),modelEl=document.getElementById('reportDraftModel'),generateButton=document.getElementById('reportDraftGenerate'),statusEl=document.getElementById('reportDraftStatus'),healthEl=document.getElementById('reportDraftHealth'),answerEl=document.getElementById('reportDraftAnswer'),caseEl=document.getElementById('reportDraftCase'),departmentEl=document.getElementById('reportDraftDepartment'),contactEl=document.getElementById('reportDraftContact'),reviewEl=document.getElementById('reportDraftReview'),dialogEl=document.getElementById('reportDraftOptions'),temperatureEl=document.getElementById('reportDraftTemperature'),numPredictEl=document.getElementById('reportDraftNumPredict'),numCtxEl=document.getElementById('reportDraftNumCtx'),systemPromptEl=document.getElementById('reportDraftSystemPrompt'),summaryEl=document.getElementById('reportDraftOptionSummary');
      const optionStorageKey='minslab.reportDraft.options';
      let defaultOptions={temperature:0.3,num_predict:500,num_ctx:2048,system_prompt:''};
      function currentOptions(){return {temperature:Number(temperatureEl.value),num_predict:Number(numPredictEl.value),num_ctx:Number(numCtxEl.value),system_prompt:systemPromptEl.value}}
      function setOptions(options){temperatureEl.value=Number(options.temperature??defaultOptions.temperature);numPredictEl.value=Math.max(Number(numPredictEl.min||500),Number(options.num_predict??defaultOptions.num_predict));numCtxEl.value=Math.max(Number(numCtxEl.min||512),Number(options.num_ctx??defaultOptions.num_ctx));systemPromptEl.value=String(options.system_prompt||defaultOptions.system_prompt);updateOptionSummary()}
      function updateOptionSummary(){const values=currentOptions(),prompt=values.system_prompt.trim(),isDefault=!prompt||prompt===defaultOptions.system_prompt.trim();summaryEl.textContent=`temperature ${values.temperature} · max tokens ${values.num_predict} · context ${values.num_ctx} · system prompt ${isDefault?'기본값':'수정됨'} (${prompt.length.toLocaleString()}자)`}
      function savedOptions(){try{return JSON.parse(localStorage.getItem(optionStorageKey)||'null')}catch(e){return null}}
      function openOptions(){if(typeof dialogEl.showModal==='function')dialogEl.showModal();else dialogEl.setAttribute('open','')}
      function closeOptions(){if(typeof dialogEl.close==='function')dialogEl.close();else dialogEl.removeAttribute('open')}
      function applyLimits(settings){const limits=settings?.limits||{};for(const [input,key] of [[temperatureEl,'temperature'],[numPredictEl,'num_predict'],[numCtxEl,'num_ctx']]){const rule=limits[key]||{};if(rule.min!=null)input.min=rule.min;if(rule.max!=null)input.max=rule.max;if(rule.step!=null)input.step=rule.step}}
      async function loadModels(){generateButton.disabled=true;healthEl.className='report-draft-health';healthEl.textContent='모델 확인 중';try{const response=await fetch('/api/portfolio/report-draft/models',{cache:'no-store'});const data=await readJsonResponse(response);if(!response.ok)throw new Error(data.error||'모델 목록을 불러오지 못했습니다.');modelEl.innerHTML='';for(const item of data.models||[]){const option=document.createElement('option');option.value=item.value||item.name;const size=item.details?.parameter_size?` · ${item.details.parameter_size}`:'';option.textContent=`${item.label||item.name}${size}`;modelEl.appendChild(option)}if(data.default&&[...modelEl.options].some(option=>option.value===data.default))modelEl.value=data.default;defaultOptions={temperature:Number(data.settings?.temperature??0.3),num_predict:Number(data.settings?.num_predict??500),num_ctx:Number(data.settings?.num_ctx??2048),system_prompt:String(data.settings?.system_prompt||'')};applyLimits(data.settings);setOptions({...defaultOptions,...(savedOptions()||{})});generateButton.disabled=!modelEl.value;healthEl.classList.add(data.warning?'error':'ok');healthEl.textContent=data.warning?'Ollama 연결 확인 필요':`로컬 모델 ${data.models?.filter(item=>item.installed!==false).length||0}개`;statusEl.textContent=data.warning||`${modelEl.value} 모델을 사용할 수 있습니다.`}catch(error){modelEl.innerHTML='<option value="">모델 조회 실패</option>';healthEl.classList.add('error');healthEl.textContent='모델 조회 실패';statusEl.textContent=error.message}}
      async function generateDraft(){const request=requestEl.value.trim();if(!request){statusEl.textContent='요청 내용을 입력하세요.';requestEl.focus();return}if(!modelEl.value){statusEl.textContent='사용할 로컬 모델을 선택하세요.';return}generateButton.disabled=true;answerEl.textContent='선택 민원자료를 찾고 로컬 LLM이 초안을 생성하고 있습니다...';statusEl.textContent=`${modelEl.value} 생성 중`;try{const response=await fetch('/api/portfolio/report-draft/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request,model:modelEl.value,options:currentOptions()})});const data=await readJsonResponse(response);if(!response.ok)throw new Error(data.error||'초안 생성에 실패했습니다.');answerEl.textContent=data.answer||'응답이 비어 있습니다.';caseEl.textContent=`${data.case?.id||'-'} · ${data.case?.title||'-'}`;departmentEl.textContent=data.case?.department||'-';contactEl.textContent=data.case?.contact||'-';reviewEl.textContent=`담당자 검토 필요: ${data.review_notice||''} ${data.case?.review_note||''}`.trim();statusEl.textContent=`생성 완료 · ${data.model} · system prompt ${data.system_prompt_customized?'수정됨':'기본값'} · ${Number(data.elapsed_seconds||0).toFixed(1)}초`}catch(error){answerEl.textContent=`오류: ${error.message}`;statusEl.textContent='초안 생성 실패'}finally{generateButton.disabled=!modelEl.value}}
      projectLab.querySelectorAll('[data-report-preset]').forEach(button=>button.onclick=()=>{requestEl.value=button.dataset.reportPreset;requestEl.focus()});
      document.getElementById('reportDraftOpenOptions').onclick=openOptions;document.getElementById('reportDraftCloseOptions').onclick=closeOptions;document.getElementById('reportDraftResetOptions').onclick=()=>setOptions(defaultOptions);document.getElementById('reportDraftSaveOptions').onclick=()=>{localStorage.setItem(optionStorageKey,JSON.stringify(currentOptions()));updateOptionSummary();closeOptions()};generateButton.onclick=generateDraft;modelEl.onchange=()=>{statusEl.textContent=`${modelEl.value} 모델을 선택했습니다.`};systemPromptEl.oninput=updateOptionSummary;dialogEl.addEventListener('click',event=>{if(event.target===dialogEl)closeOptions()});loadModels();
    }


    const archiveKickerEl=document.getElementById('archiveKicker'),archiveTitleEl=document.getElementById('archiveTitle'),archiveDescriptionEl=document.getElementById('archiveDescription'),projectIndexTitleEl=document.getElementById('projectIndexTitle'),projectDrawerLabelEl=document.getElementById('projectDrawerLabel');
    function escapeProjectHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
    function archivePageFromLocation(){if(location.pathname.startsWith('/poc'))return 'poc';if(location.pathname.startsWith('/portfolio'))return 'portfolio';return 'home'}
    function catalog(page){return catalogs[page]||catalogs.portfolio}
    function lastProjectId(page=currentArchivePage){const list=catalog(page).projects;return list.at(-1)?.id||list[0]?.id||''}
    let currentArchivePage=archivePageFromLocation()==='home'?'portfolio':archivePageFromLocation();
    const currentProjectIds={portfolio:lastProjectId('portfolio'),poc:lastProjectId('poc')};
    function setArchiveChrome(page){
      const c=catalog(page);
      archiveKickerEl.textContent=c.kicker;archiveTitleEl.innerHTML=c.title;archiveDescriptionEl.textContent=c.description;projectIndexTitleEl.textContent=c.indexLabel;projectDrawerLabelEl.textContent=c.drawerLabel;
      projectList.innerHTML=c.projects.map(p=>`<button class="project-button" data-id="${escapeProjectHtml(p.id)}"><strong>${escapeProjectHtml(p.no)}. ${escapeProjectHtml(p.title)}</strong><small>${escapeProjectHtml(p.date)}</small></button>`).join('');
    }
    function renderProject(id,page=currentArchivePage){
      const list=catalog(page).projects;
      if(!list.length){
        currentProjectIds[page]='';projectMeta.innerHTML='';projectTitle.textContent='아직 등록된 프로젝트가 없습니다.';projectSummary.textContent='이 컬렉션 폴더에 project.json을 추가하면 같은 형식으로 표시됩니다.';
        projectLab.classList.remove('active');projectLab.innerHTML='';projectDefaultView.classList.remove('hidden');projectDescription.textContent=`${catalog(page).path.replace('/','')} 컬렉션의 첫 프로젝트를 기다리고 있습니다.`;projectFeatures.innerHTML='';codeFile.textContent='project.json';projectCode.textContent='# project.json과 entry_file을 추가하면 이곳에 코드가 표시됩니다.';projectUsage.innerHTML='';projectNote.textContent='';
        return null;
      }
      const p=list.find(x=>x.id===id)||list[0];
      currentProjectIds[page]=p.id;
      document.querySelectorAll('.project-button').forEach(b=>b.classList.toggle('active',b.dataset.id===p.id));
      projectMeta.innerHTML=(p.tags||[]).map(x=>`<span>${escapeProjectHtml(x)}</span>`).join(''); projectTitle.textContent=p.title; projectSummary.textContent=p.summary;
      if(p.id==='chunking-lab'){
        renderLegacyChunkingLab(p);
      }else if(p.id==='chunking-rag-lab'){
        renderChunkingRagLab(p);
      }else if(p.id==='multiagent-harness'||p.id==='api-multi-agent'){
        renderMultiAgentHarnessLab(p);
      }else if(p.id==='report-draft'){
        renderReportDraftLab(p);
      }else if(p.id==='field-inspection-platform'){
        renderFieldInspectionLab(p);
      }else if(p.id==='master-press'){
        renderMasterPressLab(p);
      }else if(p.id==='mois-kms'){
        renderMoisKmsLab(p);
      }else if(p.id==='ai-safe-agent'){
        renderAISafeAgent(p);
      }else{
        projectLab.classList.remove('active'); projectLab.innerHTML=''; projectDefaultView.classList.remove('hidden');
        projectDescription.textContent=p.description;
        projectFeatures.innerHTML=(p.features||[]).map(x=>`<div class="feature"><b>${escapeProjectHtml(x[0])}</b><span>${escapeProjectHtml(x[1])}</span></div>`).join(''); codeFile.textContent=p.file; projectCode.textContent=p.code;
        projectUsage.innerHTML=(p.usage||[]).map(x=>`<li>${escapeProjectHtml(x)}</li>`).join(''); projectNote.textContent=p.note;
      }
      return p;
    }
    function projectIdFromLocation(page=currentArchivePage){
      const c=catalog(page),pathMatch=location.pathname.match(new RegExp(`^${c.path}/([^/?#]+)`));
      return pathMatch ? decodeURIComponent(pathMatch[1]) : new URLSearchParams(location.search).get('project');
    }
    function projectUrl(id,page=currentArchivePage){const c=catalog(page);return id?`${c.path}?project=${encodeURIComponent(id)}`:c.path}
    function scrollAISafeMapIntoView(){const map=document.getElementById('safeAgentMap');if(!map)return;requestAnimationFrame(()=>map.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'}))}
    setArchiveChrome(currentArchivePage);renderProject(projectIdFromLocation(currentArchivePage)||lastProjectId(currentArchivePage),currentArchivePage);
    projectList.addEventListener('click',e=>{const b=e.target.closest('.project-button');if(b){const p=renderProject(b.dataset.id,currentArchivePage);if(p&&document.body.classList.contains('archive-mode')){history.pushState({},'',projectUrl(p.id,currentArchivePage));trackCurrentPage()}closeMobileDrawers();if(p?.id==='ai-safe-agent')scrollAISafeMapIntoView()}});
    const drawerBackdrop=document.getElementById('drawerBackdrop'),chatDrawerToggle=document.getElementById('chatDrawerToggle'),projectDrawerToggle=document.getElementById('projectDrawerToggle'),chatSidebarEl=document.getElementById('chatSidebar'),projectSideMenuEl=document.getElementById('projectSideMenu');
    function setDrawerState(type,open){
      const className=type==='chat'?'chat-drawer-open':'project-drawer-open';
      document.body.classList.toggle(className,open);
      if(type==='chat')chatDrawerToggle?.setAttribute('aria-expanded',String(open));
      if(type==='project')projectDrawerToggle?.setAttribute('aria-expanded',String(open));
      if(open){
        const other=type==='chat'?'project-drawer-open':'chat-drawer-open';
        document.body.classList.remove(other);
        if(type==='chat')projectDrawerToggle?.setAttribute('aria-expanded','false');
        if(type==='project')chatDrawerToggle?.setAttribute('aria-expanded','false');
      }
    }
    function closeMobileDrawers(){setDrawerState('chat',false);setDrawerState('project',false)}
    chatDrawerToggle?.addEventListener('click',()=>setDrawerState('chat',!document.body.classList.contains('chat-drawer-open')));
    projectDrawerToggle?.addEventListener('click',()=>setDrawerState('project',!document.body.classList.contains('project-drawer-open')));
    drawerBackdrop?.addEventListener('click',closeMobileDrawers);
    chatSidebarEl?.addEventListener('click',e=>{if(e.target.closest('.history-item'))closeMobileDrawers()});
    addEventListener('keydown',e=>{if(e.key==='Escape')closeMobileDrawers()});
    copyCode.onclick=async()=>{await navigator.clipboard.writeText(projectCode.textContent);copyCode.textContent='복사 완료 ✓';setTimeout(()=>copyCode.textContent='코드 복사',1400)};
    const modelSelectEl=document.getElementById('modelSelect'),messagesEl=document.getElementById('messages'),inputEl=document.getElementById('chatInput'),sendEl=document.getElementById('sendButton');
    document.querySelector('.ai-mark').innerHTML='<img src="/static/images/logo.png" alt="MinsLab 로고">';
    let conversation=[],generating=false,currentChatId=crypto.randomUUID(),activeChatController=null,chatAutoFollow=true;const legacyClientId=localStorage.getItem('minzday.clientId');const deviceId=localStorage.getItem('minslab.deviceId')||legacyClientId||crypto.randomUUID();localStorage.setItem('minslab.deviceId',deviceId);localStorage.setItem('minzday.clientId',deviceId);const accountId=localStorage.getItem('minslab.accountId')||'';const historyScope=accountId?'account':'device';const historyList=document.createElement('div');historyList.className='history-list';document.getElementById('historyTitle').parentElement.append(historyList);
    messagesEl.addEventListener('scroll',()=>{chatAutoFollow=messagesEl.scrollHeight-messagesEl.scrollTop-messagesEl.clientHeight<70});messagesEl.addEventListener('wheel',e=>{if(e.deltaY<0)chatAutoFollow=false});
    let lastTrackedLocation='';
    const processCompactObserver=new MutationObserver(records=>{for(const record of records){const item=record.target;if(!(item instanceof HTMLElement)||!item.matches('.message.typing.streaming'))continue;const box=item.querySelector('.process-box');if(!box||box.classList.contains('stream-compact'))continue;box.classList.add('stream-compact');box.open=false;const toggle=box.querySelector('.process-toggle');if(toggle)toggle.textContent='상태 펼치기'}});
    processCompactObserver.observe(messagesEl,{subtree:true,attributes:true,attributeFilter:['class']});
    const answerScrollObserver=new MutationObserver(()=>{if(!chatAutoFollow)return;messagesEl.querySelectorAll('.message.typing.streaming .message-body').forEach(body=>{body.scrollTop=body.scrollHeight})});
    answerScrollObserver.observe(messagesEl,{subtree:true,childList:true,characterData:true});
    function trackCurrentPage(){const target=`${location.pathname}${location.search}`;if(target===lastTrackedLocation||target.startsWith('/admin'))return;lastTrackedLocation=target;fetch('/api/analytics/visit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({visitor_id:deviceId,path:target,page_title:document.title,referrer:document.referrer}),keepalive:true}).catch(error=>console.warn('Visit tracking failed',error))}
    function historyQuery(){const params=new URLSearchParams({client_id:deviceId});if(accountId)params.set('account_id',accountId);return params.toString()}
    async function loadHistory(){
      try{
        const r=await fetch(`/api/history?${historyQuery()}`),data=await r.json();if(!r.ok)throw new Error(data.error||'대화 이력을 불러오지 못했습니다.');
        const storageLabel=data.storage==='local'?'단말기 저장':'Supabase 저장';
        const warning=data.warning?'<div class="history-db-status">Supabase 테이블이 없어 서버 로컬 저장소를 사용 중입니다.</div>':'';
        historyList.innerHTML=(data.items?.length?data.items.map(item=>`<button class="history-item ${item.id===currentChatId?'active':''}" data-history="${item.id}">${item.title}<small>${storageLabel}</small></button>`).join(''):`<div class="history-db-status">아직 저장된 대화가 없습니다. 저장 단위: ${historyScope==='account'?'계정':'단말기'}</div>`)+warning;
        historyList.querySelectorAll('button').forEach(b=>b.onclick=()=>{
          const item=data.items.find(entry=>entry.id===b.dataset.history);if(!item)return;
          currentChatId=item.id;conversation=item.messages;messagesEl.innerHTML='';conversation.forEach(m=>addMessage(m.role,m.content));document.getElementById('historyTitle').textContent=item.title;
          if([...modelSelectEl.options].some(o=>o.value===item.model)){modelSelectEl.value=item.model;loadModelSettings()}
          historyList.querySelectorAll('.history-item').forEach(button=>button.classList.toggle('active',button.dataset.history===currentChatId));
        });
      }catch(e){historyList.innerHTML=`<div class="history-db-status">대화 이력 연결 실패: ${e.message}</div>`}
    }
    async function persistHistory(){if(!conversation.length)return;const title=conversation.find(m=>m.role==='user')?.content.slice(0,40)||'새로운 대화';try{const r=await fetch('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:currentChatId,client_id:deviceId,account_id:accountId||null,scope_type:historyScope,title,model:modelSelectEl.value,messages:conversation})});const data=await r.json();if(!r.ok||!data.saved)throw new Error(data.error||'대화 이력을 저장하지 못했습니다.');loadHistory()}catch(e){console.warn('History save failed',e);historyList.insertAdjacentHTML('afterbegin',`<div class="history-db-status">저장 실패: ${e.message}</div>`)}}
    async function loadModels(){try{const r=await fetch('/api/models'),data=await r.json();if(!r.ok)throw new Error(data.error);modelSelectEl.innerHTML=data.models.map(m=>`<option value="${m.name}">${m.name}${m.details.parameter_size?' · '+m.details.parameter_size:''}</option>`).join('');if(!data.models.length)throw new Error('설치된 모델이 없습니다.')}catch(e){modelSelectEl.innerHTML='<option>모델 연결 실패</option>';document.getElementById('ollamaStatus').innerHTML='<i style="background:#ff704d"></i><span>OLLAMA OFFLINE</span>';}}
    function healthUptime(seconds){seconds=Math.max(0,Number(seconds||0));const days=Math.floor(seconds/86400),hours=Math.floor(seconds%86400/3600),minutes=Math.floor(seconds%3600/60);return days?`${days}d ${hours}h`:hours?`${hours}h ${minutes}m`:minutes?`${minutes}m`:`${Math.floor(seconds)}s`}
    function healthSparkline(values){const nums=(Array.isArray(values)?values:[]).slice(-7).map(value=>Math.max(0,Number(value)||0));if(nums.length<2)return'';const max=Math.max(...nums),min=Math.min(...nums),range=Math.max(1,max-min),step=100/(nums.length-1),points=nums.map((value,index)=>`${(index*step).toFixed(1)},${(29-((value-min)/range)*23).toFixed(1)}`).join(' ');return`<svg class="health-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polyline points="${points}"/></svg>`}
    async function loadHealth(){const wrap=document.getElementById('healthWrap');try{const r=await fetch('/api/health',{cache:'no-store'}),data=await r.json(),stats=data.stats||{},webTime=healthUptime(stats.web_uptime_seconds??stats.uptime_seconds),serverTime=stats.host_uptime_seconds==null?'-':healthUptime(stats.host_uptime_seconds),totalSpark=healthSparkline(stats.trend?.cumulative_views),todaySpark=healthSparkline(stats.trend?.page_views),visitorSpark=healthSparkline(stats.trend?.visitors);wrap.classList.toggle('healthy',data.ok);wrap.classList.toggle('unhealthy',!data.ok);healthLabel.textContent=data.ok?'서버 정상':'서버 이상';document.getElementById('healthStats').innerHTML=`<div class="health-stat">${totalSpark}<span>Total</span><b>${Number(stats.total_views||0).toLocaleString('ko-KR')}</b></div><div class="health-stat">${todaySpark}<span>Today</span><b>${Number(stats.today_views||0).toLocaleString('ko-KR')}</b></div><div class="health-stat">${visitorSpark}<span>Visitors</span><b>${Number(stats.today_visitors||0).toLocaleString('ko-KR')}</b></div><div class="health-stat"><span>LLM Calls</span><b>${Number(stats.local_llm_calls||0).toLocaleString('ko-KR')}</b></div><div class="health-runtime"><span>가동 시간</span><b>WEB ${webTime} · SERVER ${serverTime}</b></div>`;healthDetails.innerHTML=Object.values(data.services).map(s=>`<div class="detail-row ${s.ok?'ok':'fail'}"><span><i></i>${s.label}</span><b>${s.detail}</b></div>`).join('');healthUpdated.textContent=`마지막 확인 ${new Date(data.checked_at*1000).toLocaleTimeString()}`}catch(e){wrap.className='health-wrap unhealthy';healthLabel.textContent='상태 확인 실패';document.getElementById('healthStats').innerHTML='';healthDetails.innerHTML='<div class="detail-row fail"><span><i></i>헬스 API</span><b>연결 실패</b></div>'}}
    function processPanel(item,start){const box=document.createElement('details');box.className='process-box live';box.open=true;const requestCount=conversation.length;const attachmentCount=attachedData.length;box.innerHTML='<summary><span class="process-summary">생성 중 · 준비 단계</span><span class="process-toggle">자세히 보는 중</span><span class="process-meta">0.0s</span></summary><div class="process-inner"><div class="process-log"></div><div class="references">참고 자료 확인 중...</div></div>';const log=box.querySelector('.process-log');const summaryEl=box.querySelector('.process-summary');const toggleEl=box.querySelector('.process-toggle');const metaEl=box.querySelector('.process-meta');const refs=box.querySelector('.references');const timers=[];let finished=false,firstChunkSeen=false,expansionNoted=false;box.addEventListener('toggle',()=>{if(finished)return;toggleEl.textContent=box.open?'자세히 보는 중':'간단히 보는 중'});function addStep(text,state='done'){const row=document.createElement('div');row.className=`process-step ${state}`.trim();row.innerHTML=`<i></i><span>${text}</span>`;log.append(row);log.parentElement.scrollTop=log.parentElement.scrollHeight;messagesEl.scrollTop=messagesEl.scrollHeight;return row}const intro='요청 수신 · '+requestCount+'개 메시지 맥락 정리 완료'+(attachmentCount?` · 첨부 ${attachmentCount}개 포함`:'');addStep(intro,'done');const stages=[['프롬프트와 모델 설정을 적용하고 있어요.','done','생성 중 · 입력 구성'],['로컬 모델에 요청을 전달했어요.','done','생성 중 · 모델 호출'],['응답 초안을 계산하고 있어요.','active','생성 중 · 초안 생성'],['문장 흐름과 길이를 정리하고 있어요.','active','생성 중 · 답변 다듬기']];stages.forEach(([text,state,summary],index)=>{timers.push(setTimeout(()=>{if(finished)return;addStep(text,state);summaryEl.textContent=summary},450+(index*900)))});const tick=setInterval(()=>{if(finished)return;metaEl.textContent=`${((performance.now()-start)/1000).toFixed(1)}s`},120);item.children[1].append(box);return{stream(answer){if(finished)return;if(!firstChunkSeen&&answer.trim()){firstChunkSeen=true;summaryEl.textContent='생성 중 · 실시간 출력';addStep('첫 응답 조각이 도착해 화면에 바로 표시하고 있어요.','active')}if(!expansionNoted&&answer.length>180){expansionNoted=true;addStep('답변 분량이 늘어나고 있어요. 문단 단위로 이어 붙이는 중입니다.','muted')}},finish(answer,metrics,ok=true){finished=true;timers.forEach(clearTimeout);clearInterval(tick);const seconds=metrics?.total_duration?metrics.total_duration/1e9:(performance.now()-start)/1000;const evalCount=metrics?.eval_count;const urls=[...new Set(answer.match(/https?:\/\/[^\s)\]]+/g)||[])];const statusText=ok?`${modelSelectEl.value} 응답 생성 완료`:'응답 생성 중 오류 발생';addStep(statusText+(evalCount?` · ${evalCount} tokens`:''),ok?'done':'error');refs.textContent=urls.length?'참고 자료 · ':'참고 자료 · 외부 자료를 사용하지 않은 로컬 모델 응답';urls.forEach((url,i)=>{const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noreferrer';a.textContent=`[${i+1}] ${url}`;refs.append(document.createElement('br'),a)});summaryEl.textContent=ok?`생성 완료 · ${seconds.toFixed(1)}초`:`오류로 종료 · ${seconds.toFixed(1)}초`;toggleEl.textContent='요약만 표시';metaEl.textContent=ok?(evalCount?`${evalCount} tok · ${urls.length} refs`:`${urls.length} refs`):'retry needed';box.classList.remove('live');box.classList.add('compact');box.open=false}}}
    function addMessage(role,text,extra=''){document.getElementById('emptyChat')?.remove();const item=document.createElement('article');item.className=`message ${role} ${extra}`;const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent=role==='user'?'YOU':'✦';const wrap=document.createElement('div');const label=document.createElement('div');label.className='message-role';label.textContent=role==='user'?'나':modelSelectEl.value;const body=document.createElement('div');body.className='message-body';body.textContent=text;wrap.append(label,body);item.append(avatar,wrap);messagesEl.append(item);messagesEl.scrollTop=messagesEl.scrollHeight;return item;}
    function renderChatMarkdown(text){const lines=escapeChatHtml(text).split('\n');let html=[],inCode=false,list='';const closeList=()=>{if(list){html.push(`</${list}>`);list=''}};for(const raw of lines){if(raw.startsWith('```')){closeList();html.push(inCode?'</code></pre>':'<pre><code>');inCode=!inCode;continue}if(inCode){html.push(raw+'\n');continue}let line=raw.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');const h=line.match(/^(#{1,3})\s+(.+)/),bullet=line.match(/^[-*]\s+(.+)/),numbered=line.match(/^\d+\.\s+(.+)/);if(h){closeList();html.push(`<h${h[1].length}>${h[2]}</h${h[1].length}>`)}else if(bullet||numbered){const wanted=bullet?'ul':'ol';if(list!==wanted){closeList();list=wanted;html.push(`<${list}>`)}html.push(`<li>${(bullet||numbered)[1]}</li>`)}else{closeList();if(line.startsWith('&gt; '))html.push(`<blockquote>${line.slice(5)}</blockquote>`);else html.push(line.trim()?`<p>${line}</p>`:'<br>')}}closeList();if(inCode)html.push('</code></pre>');return html.join('')}
    function escapeChatHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
    function finishChatMarkdown(item,answer){const body=item.querySelector('.message-body');body.classList.add('message-markdown');body.innerHTML=renderChatMarkdown(answer)}
    function renderSources(answer,sources=[]){const urls=[...new Set(answer.match(/https?:\/\/[^\s)\]]+/g)||[])];const merged=[...sources,...urls.map(url=>({type:'WEB',title:new URL(url).hostname,url,excerpt:'응답에 포함된 웹 링크'}))];sourceCount.textContent=merged.length;if(!merged.length){sourceList.innerHTML='<div class="source-empty"><i>⌕</i><strong>외부 자료 없음</strong><br>이 답변은 로컬 모델의 학습 지식으로<br>생성되었습니다.</div>';return}sourceList.textContent='';merged.forEach((s,i)=>{const card=document.createElement(s.url?'a':'div');card.className='source-card';if(s.url){card.href=s.url;card.target='_blank';card.rel='noreferrer'};const type=document.createElement('span');type.className='source-type';type.textContent=s.type||'RAG';const title=document.createElement('strong');title.textContent=`${i+1}. ${s.title||s.document||'참고 문서'}`;const detail=document.createElement('small');detail.textContent=s.excerpt||s.url||s.source||'';card.append(type,title,detail);sourceList.append(card)})}
    const defaultPrompt='항상 자연스러운 한국어로만 답변하세요. 다른 언어 문자를 섞지 마세요. 핵심부터 간결하고 정확하게 설명하고, 모르는 내용은 추측하지 말고 모른다고 말하세요.';const ATTACHMENT_MAX_FILE_BYTES=5*1024*1024,ATTACHMENT_MAX_FILES=3,ATTACHMENT_MAX_TOTAL_BYTES=ATTACHMENT_MAX_FILE_BYTES*ATTACHMENT_MAX_FILES,CHAT_REQUEST_MAX_BYTES=18*1024*1024;let attachedData=[];
    function attachmentBytes(){return attachedData.reduce((sum,file)=>sum+(file.size||0),0)}
    function formatBytes(bytes){const mb=bytes/(1024*1024);return mb>=1?`${mb.toFixed(mb>=10?0:1).replace(/\.0$/,'')}MB`:`${Math.ceil(bytes/1024)}KB`}
    const composerEl=document.querySelector('.composer'),composerArea=document.querySelector('.composer-area'),attachmentBoxEl=document.querySelector('.attachment-box'),attachButtonEl=document.getElementById('attachButton'),fileInputEl=document.getElementById('fileInput'),attachedFilesEl=document.getElementById('attachedFiles'),fileShelf=document.createElement('div');fileShelf.className='composer-files';fileShelf.innerHTML='<div class="composer-files-head"><b>첨부 자료</b><span>최대 3개 · 파일당 5MB · 총 15MB</span></div>';attachButtonEl.className='composer-attach';attachButtonEl.textContent='＋';attachButtonEl.title='분석 자료 첨부';composerEl.insertBefore(attachButtonEl,inputEl);fileShelf.append(attachedFilesEl);composerArea.insertBefore(fileShelf,composerEl);composerArea.append(fileInputEl);attachmentBoxEl.remove();
    const processDockObserver=new MutationObserver(()=>{messagesEl.querySelectorAll('.message.typing .process-box.live:not(.composer-docked)').forEach(box=>{box._messageOwner=box.parentElement;box.classList.add('composer-docked');box.open=true;const toggle=box.querySelector('.process-toggle');if(toggle)toggle.textContent='진행 과정 표시 중';const summary=box.querySelector('summary');if(summary&&!summary.dataset.dockGuard){summary.dataset.dockGuard='true';summary.addEventListener('click',event=>{if(box.classList.contains('composer-docked'))event.preventDefault()})}composerArea.insertBefore(box,composerEl)});composerArea.querySelectorAll('.process-box.composer-docked.compact').forEach(box=>{const owner=box._messageOwner;if(owner?.isConnected){box.classList.remove('composer-docked');owner.append(box)}})});
    processDockObserver.observe(messagesEl,{subtree:true,childList:true});
    processDockObserver.observe(composerArea,{subtree:true,attributes:true,attributeFilter:['class']});
    processDockObserver.takeRecords();
    function settingsKey(){return`minzday.settings.${modelSelectEl.value}`}
    function loadModelSettings(){const saved=JSON.parse(localStorage.getItem(settingsKey())||'{}');systemPrompt.value=saved.prompt||defaultPrompt;maxTokens.value=String(saved.maxTokens||256)}
    saveSettings.onclick=()=>{localStorage.setItem(settingsKey(),JSON.stringify({prompt:systemPrompt.value.trim(),maxTokens:Number(maxTokens.value)}));saveSettings.textContent='저장 완료 ✓';setTimeout(()=>saveSettings.textContent='이 모델 설정 저장',1200)};
    attachButtonEl.onclick=()=>fileInputEl.click();fileInputEl.onchange=async()=>{for(const file of fileInputEl.files){if(file.size>ATTACHMENT_MAX_FILE_BYTES){alert(`${file.name}: ${formatBytes(ATTACHMENT_MAX_FILE_BYTES)}를 초과합니다.`);continue}if(attachedData.length>=ATTACHMENT_MAX_FILES){alert(`파일은 최대 ${ATTACHMENT_MAX_FILES}개까지 첨부할 수 있습니다.`);break}if(attachmentBytes()+file.size>ATTACHMENT_MAX_TOTAL_BYTES){alert(`첨부 파일 총 용량은 ${formatBytes(ATTACHMENT_MAX_TOTAL_BYTES)} 이하로 제한됩니다.`);break}attachedData.push({name:file.name,size:file.size,content:await file.text()})}renderAttachments();fileInputEl.value=''};
    function renderAttachments(){fileShelf.classList.toggle('active',attachedData.length>0);attachedFilesEl.textContent='';attachedData.forEach((f,i)=>{const chip=document.createElement('div');chip.className='file-chip';const label=document.createElement('span');label.textContent=`📄 ${f.name} · ${formatBytes(f.size||0)}`;const remove=document.createElement('button');remove.type='button';remove.dataset.file=String(i);remove.title='첨부 해제';remove.textContent='×';remove.onclick=()=>{attachedData.splice(i,1);renderAttachments()};chip.append(label,remove);attachedFilesEl.append(chip)})}
    async function sendMessage(text){
      text=text.trim();if(!text||generating)return;generating=true;sendEl.disabled=true;
      conversation.push({role:'user',content:text});addMessage('user',text);
      if(conversation.length===1)document.getElementById('historyTitle').textContent=text.slice(0,28);
      inputEl.value='';inputEl.style.height='auto';
      const started=performance.now(),pending=addMessage('assistant','응답을 생각하고 있습니다…','typing'),process=processPanel(pending,started);
      const requestMessages=[];if(systemPrompt.value.trim())requestMessages.push({role:'system',content:systemPrompt.value.trim()});if(attachedData.length)requestMessages.push({role:'system',content:'다음 첨부 자료를 바탕으로 질문에 답하세요. 자료에 없는 내용은 구분해서 설명하세요.\n\n'+attachedData.map(f=>`[파일: ${f.name}]\n${f.content}`).join('\n\n')});requestMessages.push(...conversation);
      try{
        const requestBody=JSON.stringify({model:modelSelectEl.value,messages:requestMessages,max_tokens:Number(maxTokens.value),attachments:attachedData.map(f=>f.name)});if(new Blob([requestBody]).size>CHAT_REQUEST_MAX_BYTES)throw new Error(`첨부와 대화 내용을 합친 요청 크기가 ${formatBytes(CHAT_REQUEST_MAX_BYTES)}를 초과합니다. 파일을 줄이거나 일부만 첨부하세요.`);
        const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:requestBody});
        if(!r.ok){const data=await r.json();throw new Error(data.error||'응답을 받지 못했습니다.')}
        if(!r.body)throw new Error('스트리밍 응답을 받을 수 없습니다.');
        const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='',answer='',finalEvent=null;pending.classList.add('streaming');pending.querySelector('.message-body').textContent='';
        while(true){
          const {value,done}=await reader.read();
          if(done)break;
          buffer+=decoder.decode(value,{stream:true});
          const lines=buffer.split('\n');
          buffer=lines.pop()||'';
          for(const line of lines){
            if(!line.trim())continue;
            const event=JSON.parse(line);
            if(event.type==='token'){answer+=event.content||'';pending.querySelector('.message-body').textContent=answer;process.stream(answer)}
            else if(event.type==='done'){finalEvent=event}
            else if(event.type==='error'){throw new Error(event.error||'응답 생성 실패')}
          }
        }
        buffer+=decoder.decode();
        if(buffer.trim()){const event=JSON.parse(buffer);if(event.type==='done')finalEvent=event;else if(event.type==='error')throw new Error(event.error||'응답 생성 실패')}
        if(!answer&&finalEvent?.message?.content)answer=finalEvent.message.content;
        if(!answer)answer='응답 내용이 없습니다.';
        conversation.push({role:'assistant',content:answer});pending.querySelector('.message-body').textContent=answer;pending.classList.add('done');pending.classList.remove('streaming','typing');process.finish(answer,finalEvent?.metrics,true);renderSources(answer,finalEvent?.sources||[]);persistHistory();
      }catch(e){const answer=`오류: ${e.message}`;if(conversation.at(-1)?.role==='user')conversation.pop();pending.querySelector('.message-body').textContent=answer;pending.classList.add('done');pending.classList.remove('streaming','typing');process.finish(answer,null,false);renderSources(answer,[])}
      finally{generating=false;sendEl.disabled=false;inputEl.focus();messagesEl.scrollTop=messagesEl.scrollHeight}
    }
    async function sendMessageLive(text){if(generating){activeChatController?.abort();return}text=text.trim();if(!text)return;generating=true;const controller=new AbortController();activeChatController=controller;sendEl.disabled=false;sendEl.classList.add('is-stop');sendEl.textContent='■';sendEl.title='생성 중지';conversation.push({role:'user',content:text});addMessage('user',text);if(conversation.length===1)document.getElementById('historyTitle').textContent=text.slice(0,28);inputEl.value='';inputEl.style.height='auto';chatAutoFollow=true;const started=performance.now(),pending=addMessage('assistant','응답을 생각하고 있습니다…','typing'),process=processPanel(pending,started),bodyEl=pending.querySelector('.message-body');const requestMessages=[];if(systemPrompt.value.trim())requestMessages.push({role:'system',content:systemPrompt.value.trim()});if(attachedData.length)requestMessages.push({role:'system',content:'다음 첨부 자료를 바탕으로 질문에 답하세요. 자료에 없는 내용은 구분해서 설명하세요.\n\n'+attachedData.map(f=>`[파일: ${f.name}]\n${f.content}`).join('\n\n')});requestMessages.push(...conversation);let answer='',displayed='',tokenQueue=[],finalEvent=null,followButton=null;const follow=()=>{if(chatAutoFollow){messagesEl.scrollTop=messagesEl.scrollHeight;followButton?.remove();followButton=null}else if(!followButton){followButton=document.createElement('button');followButton.className='chat-follow-paused';followButton.type='button';followButton.textContent='↓ 실시간 답변으로 이동';followButton.onclick=()=>{chatAutoFollow=true;follow()};messagesEl.append(followButton)}};const draw=force=>{if(force){displayed=answer;tokenQueue=[]}else if(tokenQueue.length){const take=Math.max(1,Math.ceil(tokenQueue.length/12));displayed+=tokenQueue.splice(0,take).join('')}bodyEl.textContent=displayed;follow()};const flushTimer=setInterval(()=>draw(false),18);try{const requestBody=JSON.stringify({model:modelSelectEl.value,messages:requestMessages,max_tokens:Number(maxTokens.value),attachments:attachedData.map(f=>f.name)});if(new Blob([requestBody]).size>CHAT_REQUEST_MAX_BYTES)throw new Error(`첨부와 대화 내용을 합친 요청 크기가 ${formatBytes(CHAT_REQUEST_MAX_BYTES)}를 초과합니다.`);const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:requestBody,signal:controller.signal});if(!r.ok){const data=await r.json();throw new Error(data.error||'응답을 받지 못했습니다.')}if(!r.body)throw new Error('스트리밍 응답을 받을 수 없습니다.');const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';pending.classList.add('streaming');bodyEl.textContent='';while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines){if(!line.trim())continue;const event=JSON.parse(line);if(event.type==='token'){answer+=event.content||'';tokenQueue.push(...Array.from(event.content||''));process.stream(answer)}else if(event.type==='done')finalEvent=event;else if(event.type==='error')throw new Error(event.error||'응답 생성 실패')}}buffer+=decoder.decode();if(buffer.trim()){const event=JSON.parse(buffer);if(event.type==='done')finalEvent=event;else if(event.type==='error')throw new Error(event.error||'응답 생성 실패')}if(!answer&&finalEvent?.message?.content)answer=finalEvent.message.content;if(!answer)answer='응답 내용이 없습니다.';clearInterval(flushTimer);draw(true);conversation.push({role:'assistant',content:answer});pending.classList.add('done');pending.classList.remove('streaming','typing');finishChatMarkdown(pending,answer);process.finish(answer,finalEvent?.metrics,true);renderSources(answer,finalEvent?.sources||[]);persistHistory()}catch(e){clearInterval(flushTimer);draw(true);pending.classList.add('done');pending.classList.remove('streaming','typing');if(e.name==='AbortError'){answer=answer||'생성이 중지되었습니다.';bodyEl.textContent=answer;conversation.push({role:'assistant',content:answer});process.finish(answer,null,false);persistHistory()}else{answer=`오류: ${e.message}`;if(conversation.at(-1)?.role==='user')conversation.pop();bodyEl.textContent=answer;process.finish(answer,null,false);const retry=document.createElement('button');retry.type='button';retry.className='chat-retry';retry.textContent='다시 생성';retry.onclick=()=>sendMessageLive(text);pending.children[1].append(retry)}renderSources(answer,[])}finally{clearInterval(flushTimer);followButton?.remove();if(activeChatController===controller)activeChatController=null;generating=false;sendEl.classList.remove('is-stop');sendEl.textContent='↑';sendEl.title='보내기';sendEl.disabled=false;inputEl.focus();if(chatAutoFollow)messagesEl.scrollTop=messagesEl.scrollHeight}}
    document.getElementById('chatForm').onsubmit=e=>{e.preventDefault();sendMessageLive(inputEl.value)};inputEl.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessageLive(inputEl.value)}};inputEl.oninput=()=>{inputEl.style.height='auto';inputEl.style.height=Math.min(inputEl.scrollHeight,130)+'px'};document.querySelectorAll('.suggestion').forEach(b=>b.onclick=()=>sendMessageLive(b.textContent));document.getElementById('newChat').onclick=()=>{conversation=[];location.reload()};modelSelectEl.onchange=()=>{localStorage.setItem('minzday.selectedModel',modelSelectEl.value);conversation=[];currentChatId=crypto.randomUUID();document.getElementById('historyTitle').textContent='새로운 대화';loadModelSettings()};loadModels().then(()=>{const saved=localStorage.getItem('minzday.selectedModel');if(saved&&[...modelSelectEl.options].some(o=>o.value===saved))modelSelectEl.value=saved;loadModelSettings();loadHistory()});loadHealth();setInterval(loadHealth,15000);
    function showPage(page,push=false,projectId=null){const archive=page==='portfolio'||page==='poc';const requestedProject=archive?(projectId||projectIdFromLocation(page)||(push?lastProjectId(page):currentProjectIds[page]||lastProjectId(page))):null;closeMobileDrawers();document.body.classList.toggle('archive-mode',archive);document.querySelectorAll('[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===page));if(archive){currentArchivePage=page;setArchiveChrome(page);renderProject(requestedProject,page)}if(push)history.pushState({},'',archive?projectUrl(requestedProject,page):'/');trackCurrentPage();scrollTo(0,0)}
    document.querySelectorAll('[data-page]').forEach(a=>a.onclick=e=>{e.preventDefault();showPage(a.dataset.page,true)});addEventListener('popstate',()=>showPage(archivePageFromLocation()));showPage(archivePageFromLocation());
  </script>
</body>
</html>
"""


def build_html():
    """projects와 PoC 폴더의 최신 목록을 페이지에 삽입한다."""
    return (
        HTML_PAGE.replace("__PROJECTS_JSON__", projects_as_json())
        .replace("__POC_PROJECTS_JSON__", poc_projects_as_json())
    )


def load_module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{path.name} 파일을 불러오지 못했습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ai_safe_agent_module():
    global AI_SAFE_AGENT_MODULE, AI_SAFE_AGENT_MTIME
    mtime = AI_SAFE_AGENT_PATH.stat().st_mtime_ns
    if AI_SAFE_AGENT_MODULE is None or AI_SAFE_AGENT_MTIME != mtime:
        AI_SAFE_AGENT_MODULE = load_module_from_path("ai_safe_agent_poc", AI_SAFE_AGENT_PATH)
        AI_SAFE_AGENT_MTIME = mtime
    return AI_SAFE_AGENT_MODULE


def clear_ai_safe_agent_runtime_cache():
    module = load_ai_safe_agent_module()
    if hasattr(module, "clear_knowledge_base_cache"):
        module.clear_knowledge_base_cache()


def load_ai_safe_import_module():
    return load_module_from_path("ai_safe_agent_import", AI_SAFE_IMPORT_PATH)


def ai_safe_kb_status():
    """AI Safe Agent 기초 데이터 PKL 상태를 반환한다."""
    module = load_ai_safe_import_module()
    return module.get_pkl_status()


def build_ai_safe_kb(progress):
    """공공데이터 수집부터 날짜 PKL 생성까지 실행한다."""
    if not AI_SAFE_BUILD_LOCK.acquire(blocking=False):
        raise RuntimeError("기초 데이터 생성이 이미 진행 중입니다.")
    try:
        module = load_ai_safe_import_module()
        result = module.build_knowledge_base(progress=progress, force=True)
        clear_ai_safe_agent_runtime_cache()
        return result
    finally:
        AI_SAFE_BUILD_LOCK.release()


def parse_ai_safe_coordinates(payload):
    try:
        lat = float(payload.get("lat"))
        lng = float(payload.get("lng"))
    except (TypeError, ValueError):
        raise ValueError("위도와 경도를 숫자로 입력하세요.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("위도 또는 경도 범위가 올바르지 않습니다.")
    return lat, lng


def ai_safe_config_status(kb_status):
    return {
        "kma_key": bool(env_first("KMA_AUTH_KEY")),
        "hf_key": bool(env_first("HF_API_KEY")),
        "openrouter_key": bool(env_first("OPENROUTER_API_KEY")),
        "kb_path": kb_status.get("filename") or env_first("DISASTER_KB_PATH", default="integrated_disaster_kb.pkl"),
    }


def run_ai_safe_agent_spatial(payload):
    """지도 클릭용 빠른 공간 조회. KMA/LLM 호출 없이 PKL만 사용한다."""
    lat, lng = parse_ai_safe_coordinates(payload)
    module = load_ai_safe_agent_module()
    result = module.analyze_spatial_location(lat, lng)
    kb_status = ai_safe_kb_status()
    result["kb_status"] = kb_status
    result["config_status"] = ai_safe_config_status(kb_status)
    return result


def run_ai_safe_agent_rain(payload):
    """분석 버튼에서 먼저 보여줄 KMA 강수·기온 추계만 가져온다."""
    lat, lng = parse_ai_safe_coordinates(payload)
    module = load_ai_safe_agent_module()
    rain = module.get_kma_precipitation_live(lat, lng)
    kb_status = ai_safe_kb_status()
    return {
        "lat": lat,
        "lng": lng,
        "rain_info": rain,
        "config_status": ai_safe_config_status(kb_status),
    }


def run_ai_safe_agent_analysis(payload):
    """AI Safe Agent PoC 스크립트를 서버에서 실행한다."""
    lat, lng = parse_ai_safe_coordinates(payload)
    module = load_ai_safe_agent_module()
    use_ai = bool(payload.get("use_ai", True))
    result = module.analyze_location(lat, lng, use_ai=use_ai, model_choice=payload.get("ai_model"), rain_info=payload.get("rain_info"))
    kb_status = ai_safe_kb_status()
    result["kb_status"] = kb_status
    result["config_status"] = ai_safe_config_status(kb_status)
    return result


def prepare_ai_safe_agent_analysis(payload):
    """이미 조회한 강수 데이터를 재사용해 스트리밍용 분석 문맥을 준비한다."""
    lat, lng = parse_ai_safe_coordinates(payload)
    module = load_ai_safe_agent_module()
    result = module.prepare_analysis(lat, lng, rain_info=payload.get("rain_info"))
    kb_status = ai_safe_kb_status()
    result["kb_status"] = kb_status
    result["config_status"] = ai_safe_config_status(kb_status)
    return result



def _is_ollama_chat_model(model):
    name = str(model.get("name") or "").lower()
    details = model.get("details") if isinstance(model.get("details"), dict) else {}
    family = str(details.get("family") or "").lower()
    families = [str(item).lower() for item in details.get("families", []) if item]
    if "embed" in name or "embedding" in name:
        return False
    if "bert" in family or any("bert" in item for item in families):
        return False
    return True


def ollama_model_options():
    try:
        base_url = env_first("OLLAMA_BASE_URL", default="http://127.0.0.1:11434")
        parsed = url_parse.urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not _tcp_port_is_open(host, port):
            return []
        result = call_ollama("/api/tags")
        return [
            {
                "value": f"ollama:{model['name']}",
                "label": f"Ollama · {model['name']}",
                "provider": "ollama",
                "name": model["name"],
                "details": model.get("details", {}),
            }
            for model in result.get("models", [])
            if model.get("name") and _is_ollama_chat_model(model)
        ]
    except Exception:
        return []


def ai_safe_model_options():
    local_models = ollama_model_options()
    hf_model = env_first("AI_SAFE_HF_QWEN25_MODEL", default="Qwen/Qwen2.5-72B-Instruct")
    openrouter_model = env_first("AI_SAFE_OPENROUTER_MODEL", default="openai/gpt-4o-mini")
    remote_models = [
        {"value": f"huggingface:{hf_model}", "label": f"Hugging Face · {hf_model}", "provider": "huggingface", "name": hf_model},
        {"value": f"openrouter:{openrouter_model}", "label": f"OpenRouter · {openrouter_model}", "provider": "openrouter", "name": openrouter_model},
    ]
    models = local_models + remote_models
    return {"models": models, "default": models[0]["value"] if models else ""}


def chunking_model_options():
    openrouter_model = env_first("CHUNKING_OPENROUTER_MODEL", "OPENROUTER_CHAT_MODEL", default=DEFAULT_CHAT_MODEL)
    openrouter_option = {
        "value": f"openrouter:{openrouter_model}",
        "label": f"OpenRouter · {openrouter_model}",
        "provider": "openrouter",
        "name": openrouter_model,
        "details": {},
    }
    models = ollama_model_options() + [openrouter_option]
    return {"models": models, "default": openrouter_option["value"]}


def _join_region(*parts):
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _nominatim_reverse_geocode(lat, lng):
    """Kakao/VWorld가 실패할 때 사용하는 저빈도 OSM 역지오코딩 대체 경로."""
    global NOMINATIM_LAST_REQUEST
    cache_key = (round(lat, 4), round(lng, 4))
    cached = REVERSE_GEOCODE_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    with NOMINATIM_LOCK:
        cached = REVERSE_GEOCODE_CACHE.get(cache_key)
        if cached:
            return dict(cached)
        wait_seconds = 1.0 - (time.monotonic() - NOMINATIM_LAST_REQUEST)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lng,
            "zoom": 18,
            "addressdetails": 1,
            "accept-language": "ko",
        }
        request = url_request.Request(
            f"https://nominatim.openstreetmap.org/reverse?{url_parse.urlencode(params)}",
            headers={
                "User-Agent": "MinsLab-AISafeAgent/1.0 (https://github.com/acesharp81/minslab)",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with url_request.urlopen(request, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
        finally:
            NOMINATIM_LAST_REQUEST = time.monotonic()

    address_parts = data.get("address", {}) if isinstance(data, dict) else {}
    region1 = address_parts.get("province") or address_parts.get("state") or address_parts.get("city")
    region2 = (
        address_parts.get("city_district")
        or address_parts.get("borough")
        or address_parts.get("county")
        or address_parts.get("municipality")
    )
    region3 = (
        address_parts.get("quarter")
        or address_parts.get("suburb")
        or address_parts.get("neighbourhood")
        or address_parts.get("village")
        or address_parts.get("town")
    )
    legal = _join_region(region1, region2, region3)
    result = {
        "status": "ok" if legal else "error",
        "provider": "openstreetmap",
        "legal_dong": legal,
        "address": data.get("display_name", "") if isinstance(data, dict) else "",
        "lat": lat,
        "lng": lng,
    }
    REVERSE_GEOCODE_CACHE[cache_key] = result
    return dict(result)


def reverse_geocode_location(payload):
    lat, lng = parse_ai_safe_coordinates(payload)
    errors = []
    kakao_key = env_first("KAKAO_REST_API_KEY", "KAKAO_API_KEY")
    if kakao_key:
        try:
            query = url_parse.urlencode({"x": lng, "y": lat})
            request = url_request.Request(
                f"https://dapi.kakao.com/v2/local/geo/coord2regioncode.json?{query}",
                headers={"Authorization": f"KakaoAK {kakao_key}"},
                method="GET",
            )
            with url_request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            documents = data.get("documents", [])
            legal = next((item for item in documents if item.get("region_type") == "B"), documents[0] if documents else {})
            address = legal.get("address_name") or _join_region(
                legal.get("region_1depth_name"),
                legal.get("region_2depth_name"),
                legal.get("region_3depth_name"),
            )
            return {"status": "ok", "provider": "kakao", "legal_dong": address, "address": address, "lat": lat, "lng": lng}
        except Exception as error:  # noqa: BLE001 - optional enrichment must not break the PoC screen
            errors.append(f"kakao: {error}")

    vworld_key = env_first("VWORLD_API_KEY", "VWORLD_KEY")
    if vworld_key:
        try:
            params = {
                "service": "address",
                "request": "getAddress",
                "format": "json",
                "type": "parcel",
                "crs": "epsg:4326",
                "point": f"{lng},{lat}",
                "key": vworld_key,
            }
            request = url_request.Request(f"https://api.vworld.kr/req/address?{url_parse.urlencode(params)}", method="GET")
            with url_request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("response", {}).get("result", []) or []
            first = results[0] if results else {}
            structure = first.get("structure", {}) if isinstance(first, dict) else {}
            address = first.get("text") if isinstance(first, dict) else ""
            legal = _join_region(structure.get("level1"), structure.get("level2"), structure.get("level4L") or structure.get("level4LC")) or address
            return {"status": "ok", "provider": "vworld", "legal_dong": legal, "address": address or legal, "lat": lat, "lng": lng}
        except Exception as error:  # noqa: BLE001 - optional enrichment must not break the PoC screen
            errors.append(f"vworld: {error}")

    try:
        result = _nominatim_reverse_geocode(lat, lng)
        if result.get("status") == "ok":
            result["fallback_errors"] = errors
            return result
        errors.append("openstreetmap: 법정동 수준 주소를 찾지 못했습니다.")
    except Exception as error:  # noqa: BLE001 - final fallback error is returned to the UI
        errors.append(f"openstreetmap: {error}")
    if errors:
        return {
            "status": "error",
            "provider": None,
            "legal_dong": "",
            "address": "",
            "message": "; ".join(errors),
            "lat": lat,
            "lng": lng,
        }
    return {
        "status": "unavailable",
        "provider": None,
        "legal_dong": "",
        "address": "",
        "message": "KAKAO_REST_API_KEY 또는 VWORLD_API_KEY가 설정되지 않았습니다.",
        "lat": lat,
        "lng": lng,
    }


def _build_ollama_request(path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    base_url = env_first("OLLAMA_BASE_URL", default="http://127.0.0.1:11434").rstrip("/")
    return url_request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )


def call_ollama(path, payload=None):
    """브라우저에 Ollama 포트를 노출하지 않고 로컬 API를 호출한다."""
    request = _build_ollama_request(path, payload)
    with url_request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def iter_ollama_stream(path, payload=None):
    """Ollama의 NDJSON 스트림을 순서대로 읽는다."""
    if path == "/api/chat" and payload is not None:
        try:
            increment_local_llm_calls()
        except Exception:
            pass
    request = _build_ollama_request(path, payload)
    with url_request.urlopen(request, timeout=120) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            yield json.loads(line)


def _tcp_port_is_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def host_uptime_seconds():
    """Linux 운영체제가 부팅된 뒤 경과한 시간을 초 단위로 반환한다."""
    try:
        return max(0, int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])))
    except (OSError, ValueError, IndexError):
        return None


def capture_system_metrics():
    usage = read_system_usage()
    usage.update(drain_http_window())
    record_system_metrics(**usage)
    return usage


async def collect_system_metrics():
    while True:
        await asyncio.sleep(SYSTEM_METRICS_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(capture_system_metrics)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"System metrics collection failed: {error}", file=sys.stderr)


def check_services():
    """웹 서비스 운영에 필요한 구성요소의 실제 연결 상태를 확인한다."""
    services = {"server": {"label": "서버", "ok": True, "detail": "ASGI 응답 정상"}}
    nginx_port = next((port for port in (443, 80) if _tcp_port_is_open("127.0.0.1", port)), None)
    services["nginx"] = {
        "label": "Nginx", "ok": nginx_port is not None,
        "detail": f"포트 {nginx_port} 응답 정상" if nginx_port else "포트 연결 실패",
    }
    try:
        models = call_ollama("/api/tags").get("models", [])
        services["ollama"] = {
            "label": "Ollama", "ok": True,
            "detail": f"실행 중 · 모델 {len(models)}개",
        }
    except (OSError, url_error.URLError, json.JSONDecodeError):
        services["ollama"] = {"label": "Ollama", "ok": False, "detail": "API 연결 실패"}
    try:
        stats = get_analytics_summary()
        analytics_status()
        services["analytics"] = {"label": "방문 통계", "ok": True, "detail": "SQLite 기록 정상"}
    except (OSError, ValueError, RuntimeError) as error:
        stats = {
            "total_views": 0,
            "today_views": 0,
            "today_visitors": 0,
            "total_visitors": 0,
        }
        services["analytics"] = {
            "label": "방문 통계", "ok": False, "detail": f"저장소 오류: {error}"
        }
    web_uptime = max(0, int(time.monotonic() - APP_STARTED_MONOTONIC))
    stats["uptime_seconds"] = web_uptime
    stats["web_uptime_seconds"] = web_uptime
    stats["host_uptime_seconds"] = host_uptime_seconds()
    stats["started_at"] = int(APP_STARTED_AT)
    return {
        "ok": all(item["ok"] for item in services.values()),
        "services": services,
        "stats": stats,
        "checked_at": int(time.time()),
    }


async def read_request_body(receive):
    chunks = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)



def scope_headers(scope):
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }


def request_ip(scope):
    client = scope.get("client") or ("unknown", 0)
    return str(client[0] or "unknown")


def admin_session(scope):
    raw_cookie = scope_headers(scope).get("cookie", "")
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except Exception:
        return None
    token = cookie.get(SESSION_COOKIE)
    return ADMIN_AUTH.verify_session(token.value if token else "")


def valid_analytics_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from error


def load_mois_kms_module():
    """PoC 03 백엔드를 변경 시 자동으로 다시 읽는다."""
    global MOIS_KMS_MODULE, MOIS_KMS_MTIME
    mtime = MOIS_KMS_SERVICE_PATH.stat().st_mtime_ns
    if MOIS_KMS_MODULE is None or MOIS_KMS_MTIME != mtime:
        MOIS_KMS_MODULE = load_module_from_path("mois_kms_poc_backend", MOIS_KMS_SERVICE_PATH)
        MOIS_KMS_MTIME = mtime
    return MOIS_KMS_MODULE


def load_master_press_module():
    """PoC 04 뉴스 모듈과 하위 Python 소스를 변경 시 다시 읽는다."""
    global MASTER_PRESS_MODULE, MASTER_PRESS_MTIME
    source_paths = [MASTER_PRESS_SERVICE_PATH, *MASTER_PRESS_SERVICE_PATH.parent.glob("master_press/*.py")]
    mtime = max(path.stat().st_mtime_ns for path in source_paths if path.is_file())
    if MASTER_PRESS_MODULE is None or MASTER_PRESS_MTIME != mtime:
        if MASTER_PRESS_MODULE is not None:
            for module_name in [name for name in sys.modules if name == "master_press" or name.startswith("master_press.")]:
                sys.modules.pop(module_name, None)
        MASTER_PRESS_MODULE = load_module_from_path("master_press_poc_backend", MASTER_PRESS_SERVICE_PATH)
        MASTER_PRESS_MTIME = mtime
    return MASTER_PRESS_MODULE


async def collect_master_press():
    """기존 홈페이지 프로세스 안에서 30초마다 예정된 수집·발송을 확인한다."""
    while True:
        try:
            module = load_master_press_module()
            await asyncio.to_thread(module.worker_tick)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"Master Press background worker failed: {error}", file=sys.stderr)
        await asyncio.sleep(30)


def load_report_draft_module():
    """04 보고서 초안 서비스를 변경 시 자동으로 다시 읽는다."""
    global REPORT_DRAFT_MODULE, REPORT_DRAFT_MTIME
    mtime = REPORT_DRAFT_SERVICE_PATH.stat().st_mtime_ns
    if REPORT_DRAFT_MODULE is None or REPORT_DRAFT_MTIME != mtime:
        REPORT_DRAFT_MODULE = load_module_from_path(
            "report_draft_portfolio_service", REPORT_DRAFT_SERVICE_PATH
        )
        REPORT_DRAFT_MTIME = mtime
    return REPORT_DRAFT_MODULE


def load_multiagent_harness_module():
    """03 계층형 멀티에이전트 하네스 서비스를 변경 시 다시 읽는다."""
    global MULTIAGENT_HARNESS_MODULE, MULTIAGENT_HARNESS_MTIME
    mtime = MULTIAGENT_HARNESS_SERVICE_PATH.stat().st_mtime_ns
    if MULTIAGENT_HARNESS_MODULE is None or MULTIAGENT_HARNESS_MTIME != mtime:
        MULTIAGENT_HARNESS_MODULE = load_module_from_path(
            "multiagent_harness_portfolio_service", MULTIAGENT_HARNESS_SERVICE_PATH
        )
        MULTIAGENT_HARNESS_MTIME = mtime
    return MULTIAGENT_HARNESS_MODULE


def report_draft_model_options():
    """04 프로젝트에서 선택할 로컬 Ollama 모델과 기본 옵션을 반환한다."""
    return load_report_draft_module().model_options()


def run_report_draft(payload):
    """04 프로젝트의 XML 검색과 로컬 LLM 초안 생성을 실행한다."""
    return load_report_draft_module().generate(payload)


async def app(scope, receive, send):
    """Uvicorn에서 사용하는 최소 ASGI 애플리케이션."""
    if scope["type"] == "lifespan":
        metrics_task = None
        master_press_task = None
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await asyncio.to_thread(analytics_status)
                await asyncio.to_thread(purge_old_analytics_events)
                try:
                    await asyncio.to_thread(capture_system_metrics)
                except (OSError, ValueError, RuntimeError) as error:
                    print(f"Initial system metrics collection failed: {error}", file=sys.stderr)
                metrics_task = asyncio.create_task(collect_system_metrics())
                master_press_task = asyncio.create_task(collect_master_press())
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if metrics_task is not None:
                    metrics_task.cancel()
                    try:
                        await metrics_task
                    except asyncio.CancelledError:
                        pass
                if master_press_task is not None:
                    master_press_task.cancel()
                    try:
                        await master_press_task
                    except asyncio.CancelledError:
                        pass
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] != "http":
        return

    path = scope.get("path", "/")
    method = scope.get("method", "GET").upper()
    request_started = time.perf_counter()
    response_status = 500
    response_observed = False
    original_send = send

    async def monitored_send(message):
        nonlocal response_status, response_observed
        if message["type"] == "http.response.start":
            response_status = int(message.get("status", 500))
        await original_send(message)
        if (
            message["type"] == "http.response.body"
            and not message.get("more_body", False)
            and not response_observed
        ):
            response_observed = True
            observe_http_request(
                path,
                response_status,
                (time.perf_counter() - request_started) * 1000.0,
            )

    send = monitored_send
    status = 200
    extra_headers = []

    if path == "/api/analytics/visit" and method == "POST":
        try:
            raw_body = await read_request_body(receive)
            if len(raw_body) > 32_000:
                raise ValueError("방문 기록 요청이 너무 큽니다.")
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON 객체 형식이 필요합니다.")
            headers_in = scope_headers(scope)
            user_agent = headers_in.get("user-agent", "")
            visitor_id = str(payload.get("visitor_id") or "")
            if not visitor_id or len(visitor_id) > 160:
                raise ValueError("방문자 식별자가 필요합니다.")
            tracked = await asyncio.to_thread(
                record_visit,
                visitor_id=visitor_id,
                ip_address=request_ip(scope),
                path=str(payload.get("path") or ""),
                page_title=str(payload.get("page_title") or ""),
                referrer=str(payload.get("referrer") or headers_in.get("referer", "")),
                user_agent=user_agent,
            )
            status = 201 if tracked else 200
            body = json.dumps({"tracked": tracked}, ensure_ascii=False).encode("utf-8")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            status = 400
            body = json.dumps({"tracked": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
        except (OSError, RuntimeError) as error:
            status = 503
            body = json.dumps({"tracked": False, "error": f"통계 저장 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == "/api/admin/login" and method == "POST":
        try:
            raw_body = await read_request_body(receive)
            if len(raw_body) > 4_096:
                raise ValueError("로그인 요청이 너무 큽니다.")
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON 객체 형식이 필요합니다.")
            token = ADMIN_AUTH.authenticate(str(payload.get("password") or ""), request_ip(scope))
            body = json.dumps({"authenticated": True}, ensure_ascii=False).encode("utf-8")
            extra_headers.append((b"set-cookie", ADMIN_AUTH.cookie_header(token).encode("latin-1")))
        except PermissionError as error:
            status = 429
            body = json.dumps({"authenticated": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
            extra_headers.append((b"retry-after", str(ADMIN_AUTH.retry_after(request_ip(scope))).encode("ascii")))
        except RuntimeError as error:
            status = 503
            body = json.dumps({"authenticated": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            status = 401
            body = json.dumps({"authenticated": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == "/api/admin/logout" and method == "POST":
        body = json.dumps({"authenticated": False}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.extend([
            (b"set-cookie", ADMIN_AUTH.clear_cookie_header().encode("latin-1")),
            (b"cache-control", b"no-store"),
        ])
    elif path == "/api/admin/session" and method == "GET":
        session = admin_session(scope)
        if session:
            body = json.dumps(
                {"authenticated": True, "expires_at": session.get("exp")},
                ensure_ascii=False,
            ).encode("utf-8")
        else:
            status = 401
            body = json.dumps(
                {"authenticated": False, "error": "관리자 로그인이 필요합니다."},
                ensure_ascii=False,
            ).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == "/api/admin/analytics" and method == "GET":
        if not admin_session(scope):
            status = 401
            body = json.dumps(
                {"error": "관리자 로그인이 필요합니다."}, ensure_ascii=False
            ).encode("utf-8")
        else:
            try:
                query = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
                target_date = valid_analytics_date(query.get("date", [""])[0])
                page_number = int(query.get("page", ["1"])[0])
                page_size = int(query.get("page_size", ["50"])[0])
                visits = await asyncio.to_thread(
                    list_analytics_visits,
                    local_date=target_date,
                    page=page_number,
                    page_size=page_size,
                    ip_filter=query.get("ip", [""])[0],
                    path_filter=query.get("path", [""])[0],
                )
                summary = await asyncio.to_thread(get_analytics_summary)
                system_metrics = await asyncio.to_thread(get_system_metric_history, 48)
                web_uptime = max(0, int(time.monotonic() - APP_STARTED_MONOTONIC))
                body = json.dumps(
                    {
                        "summary": summary,
                        "system_metrics": system_metrics,
                        "system_metrics_interval_seconds": SYSTEM_METRICS_INTERVAL_SECONDS,
                        "visits": visits,
                        "uptime_seconds": web_uptime,
                        "web_uptime_seconds": web_uptime,
                        "host_uptime_seconds": host_uptime_seconds(),
                        "started_at": int(APP_STARTED_AT),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                status = 400
                body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
            except (OSError, RuntimeError) as error:
                status = 503
                body = json.dumps({"error": f"통계 조회 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == "/api/history" and method == "GET":
        try:
            query = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
            client_id = query.get("client_id", [""])[0]
            account_id = query.get("account_id", [""])[0] or None
            if not client_id:
                raise ValueError("client_id가 필요합니다.")
            result, storage, warning = await asyncio.to_thread(list_history, client_id, account_id)
            body = json.dumps({"configured": supabase_configured(), "storage": storage, "warning": warning, "items": result}, ensure_ascii=False).encode("utf-8")
        except ValueError as error:
            status = 400
            body = json.dumps({"configured": supabase_configured(), "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/history" and method == "POST":
        try:
            record = json.loads((await read_request_body(receive)).decode("utf-8"))
            required = {"id", "client_id", "title", "model", "messages"}
            if not required.issubset(record) or not isinstance(record["messages"], list):
                raise ValueError("잘못된 대화 이력 형식입니다.")
            payload = {key: record[key] for key in required}
            payload["account_id"] = record.get("account_id") or None
            payload["scope_type"] = record.get("scope_type") or ("account" if payload["account_id"] else "device")
            result, storage, warning = await asyncio.to_thread(save_history, payload)
            body = json.dumps({"saved": True, "storage": storage, "warning": warning, "item": result}, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 503
            body = json.dumps({"saved": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif (path == MASTER_PRESS_API_BASE or path.startswith(f"{MASTER_PRESS_API_BASE}/")) and method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        try:
            payload = {}
            if method in {"POST", "PUT", "PATCH"}:
                raw_body = await read_request_body(receive)
                if len(raw_body) > 1_000_000:
                    raise ValueError("요청 본문은 1MB를 넘을 수 없습니다.")
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON 객체 형식이 필요합니다.")
            query_values = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
            query = {key: values[-1] if values else "" for key, values in query_values.items()}
            request_headers = scope_headers(scope)
            scheme = request_headers.get("x-forwarded-proto", scope.get("scheme", "https")).split(",")[0].strip()
            host = request_headers.get("x-forwarded-host", request_headers.get("host", "")).split(",")[0].strip()
            request_base = f"{scheme}://{host}" if host else ""
            module = load_master_press_module()
            subpath = path[len(MASTER_PRESS_API_BASE):] or "/"
            result = await asyncio.to_thread(
                module.dispatch,
                subpath,
                method,
                payload,
                query,
                bool(admin_session(scope)),
                request_base,
            )
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = int(getattr(error, "status", 500))
            message = str(error) if status < 500 or str(error) else "마스터언론 요청을 처리하지 못했습니다."
            body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path.startswith(f"{MASTER_PRESS_BASE_PATH}/article/") and method == "GET":
        try:
            article_id = path[len(f"{MASTER_PRESS_BASE_PATH}/article/"):]
            location = await asyncio.to_thread(load_master_press_module().article_redirect_url, article_id)
            status = 302
            body = b""
            extra_headers.append((b"location", location.encode("latin-1")))
        except Exception as error:
            status = int(getattr(error, "status", 404))
            body = f"원문 연결 실패\n{str(error)}".encode("utf-8")
        content_type = "text/plain; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == f"{MASTER_PRESS_BASE_PATH}/connect" and method == "GET":
        try:
            query = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
            invite = query.get("invite", [""])[0]
            location = await asyncio.to_thread(load_master_press_module().kakao_authorization_url, invite)
            status = 302
            body = b""
            extra_headers.append((b"location", location.encode("latin-1")))
        except Exception as error:
            status = int(getattr(error, "status", 400))
            body = f"수신자 등록 실패\n{str(error)}".encode("utf-8")
        content_type = "text/plain; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif path == f"{MASTER_PRESS_BASE_PATH}/oauth/kakao/callback" and method == "GET":
        try:
            query = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
            if query.get("error"):
                raise ValueError(query.get("error_description", query["error"])[0])
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0]
            await asyncio.to_thread(load_master_press_module().complete_kakao_authorization, code, state)
            status = 302
            body = b""
            extra_headers.append((b"location", f"{MASTER_PRESS_BASE_PATH}/?connected=1".encode("latin-1")))
        except Exception as error:
            status = int(getattr(error, "status", 400))
            body = f"카카오 연결 실패\n{str(error)}".encode("utf-8")
        content_type = "text/plain; charset=utf-8"
        extra_headers.append((b"cache-control", b"no-store"))
    elif (path == MASTER_PRESS_BASE_PATH or path.startswith(f"{MASTER_PRESS_BASE_PATH}/")) and method in {"GET", "HEAD"}:
        relative_path = path[len(MASTER_PRESS_BASE_PATH):].lstrip("/")
        requested = (MASTER_PRESS_WEB / relative_path).resolve() if relative_path else MASTER_PRESS_WEB / "index.html"
        try:
            requested.relative_to(MASTER_PRESS_WEB.resolve())
            if requested.is_file():
                target = requested
            elif not Path(relative_path).suffix:
                target = MASTER_PRESS_WEB / "index.html"
            else:
                raise FileNotFoundError
            body = await asyncio.to_thread(target.read_bytes)
            content_type = {
                ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
            }.get(target.suffix.lower(), "application/octet-stream")
        except (ValueError, OSError, FileNotFoundError):
            status = 404
            body = b"Master Press application is not available."
            content_type = "text/plain; charset=utf-8"

    elif (path == MULTIAGENT_HARNESS_API_BASE or path.startswith(f"{MULTIAGENT_HARNESS_API_BASE}/")) and method in {"GET", "POST"}:
        try:
            payload = {}
            if method == "POST":
                raw_body = await read_request_body(receive)
                if len(raw_body) > 1_000_000:
                    raise ValueError("요청 본문은 1MB를 넘을 수 없습니다.")
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON 객체 형식이 필요합니다.")
            module = load_multiagent_harness_module()
            subpath = path[len(MULTIAGENT_HARNESS_API_BASE):] or "/"
            result = await asyncio.to_thread(module.dispatch, subpath, method, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, json.JSONDecodeError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = int(getattr(error, "status", 500))
            body = json.dumps({"error": str(error) or "하네스 요청을 처리하지 못했습니다."}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif (path == MULTIAGENT_HARNESS_BASE_PATH or path.startswith(f"{MULTIAGENT_HARNESS_BASE_PATH}/")) and method in {"GET", "HEAD"}:
        relative_path = path[len(MULTIAGENT_HARNESS_BASE_PATH):].lstrip("/")
        requested = (MULTIAGENT_HARNESS_APP / relative_path).resolve() if relative_path else MULTIAGENT_HARNESS_APP / "index.html"
        try:
            requested.relative_to(MULTIAGENT_HARNESS_APP.resolve())
            if requested.is_file():
                target = requested
            elif not Path(relative_path).suffix:
                target = MULTIAGENT_HARNESS_APP / "index.html"
            else:
                raise FileNotFoundError
            if not target.is_file():
                raise FileNotFoundError
            body = await asyncio.to_thread(target.read_bytes)
            content_type = {
                ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
                ".woff": "font/woff", ".woff2": "font/woff2",
            }.get(target.suffix.lower(), "application/octet-stream")
        except (ValueError, OSError, FileNotFoundError):
            status = 404
            body = b"Multi-agent harness application is not available."
            content_type = "text/plain; charset=utf-8"
    elif (path == MOIS_KMS_API_BASE or path.startswith(f"{MOIS_KMS_API_BASE}/")) and method in {"GET", "POST"}:
        try:
            payload = {}
            if method == "POST":
                raw_body = await read_request_body(receive)
                if len(raw_body) > 1_000_000:
                    raise ValueError("요청 본문은 1MB를 넘을 수 없습니다.")
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON 객체 형식이 필요합니다.")
            request_headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            authorization = request_headers.get("authorization", "")
            token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
            module = load_mois_kms_module()
            subpath = path[len(MOIS_KMS_API_BASE):] or "/"
            result = await asyncio.to_thread(module.dispatch, subpath, method, token, payload)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, json.JSONDecodeError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = int(getattr(error, "status", 500))
            message = str(error) if status < 500 or str(error) else "PoC 03 서버 요청을 처리하지 못했습니다."
            body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif (path == MOIS_KMS_BASE_PATH or path.startswith(f"{MOIS_KMS_BASE_PATH}/")) and method in {"GET", "HEAD"}:
        relative_path = path[len(MOIS_KMS_BASE_PATH):].lstrip("/")
        requested = (MOIS_KMS_DIST / relative_path).resolve() if relative_path else MOIS_KMS_DIST / "index.html"
        try:
            requested.relative_to(MOIS_KMS_DIST.resolve())
            if requested.is_file():
                target = requested
            elif not Path(relative_path).suffix:
                target = MOIS_KMS_DIST / "index.html"
            else:
                raise FileNotFoundError
            if not target.is_file():
                raise FileNotFoundError
            body = await asyncio.to_thread(target.read_bytes)
            content_type = {
                ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon",
                ".woff": "font/woff", ".woff2": "font/woff2",
            }.get(target.suffix.lower(), "application/octet-stream")
        except (ValueError, OSError, FileNotFoundError):
            status = 404
            body = b"MoIS KMS application is not built."
            content_type = "text/plain; charset=utf-8"
    elif (path == FIELD_INSPECTION_BASE_PATH or path.startswith(f"{FIELD_INSPECTION_BASE_PATH}/")) and method in {"GET", "HEAD"}:
        relative_path = path[len(FIELD_INSPECTION_BASE_PATH):].lstrip("/")
        requested = (FIELD_INSPECTION_DIST / relative_path).resolve() if relative_path else FIELD_INSPECTION_DIST / "index.html"
        try:
            requested.relative_to(FIELD_INSPECTION_DIST.resolve())
            if requested.is_file():
                target = requested
            elif not Path(relative_path).suffix:
                target = FIELD_INSPECTION_DIST / "index.html"
            else:
                raise FileNotFoundError
            if not target.is_file():
                raise FileNotFoundError
            body = await asyncio.to_thread(target.read_bytes)
            content_type = {
                ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon",
                ".woff": "font/woff", ".woff2": "font/woff2",
            }.get(target.suffix.lower(), "application/octet-stream")
        except (ValueError, OSError, FileNotFoundError):
            status = 404
            body = b"Field inspection application is not built."
            content_type = "text/plain; charset=utf-8"
    elif path.startswith("/static/") and method in {"GET", "HEAD"}:
        relative_path = path.removeprefix("/static/")
        target = (STATIC_DIR / relative_path).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
            if not target.is_file():
                raise FileNotFoundError
            body = await asyncio.to_thread(target.read_bytes)
            content_type = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }.get(target.suffix.lower(), "application/octet-stream")
        except (ValueError, OSError, FileNotFoundError):
            status = 404
            body = b"Not Found"
            content_type = "text/plain; charset=utf-8"
    elif path == "/api/health" and method == "GET":
        result = await asyncio.to_thread(check_services)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/models" and method == "GET":
        try:
            result = await asyncio.to_thread(call_ollama, "/api/tags")
            models = [
                {"name": model["name"], "size": model.get("size", 0), "details": model.get("details", {})}
                for model in result.get("models", [])
            ]
            body = json.dumps({"models": models}, ensure_ascii=False).encode("utf-8")
        except (OSError, url_error.URLError, json.JSONDecodeError, TimeoutError) as error:
            status = 503
            body = json.dumps({"error": f"Ollama 연결 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/hwpx-extract" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(extract_hwpx_payload, payload.get("filename", ""), payload.get("data_base64", ""))
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/kb/status" and method == "GET":
        try:
            result = await asyncio.to_thread(ai_safe_kb_status)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, RuntimeError, TimeoutError) as error:
            status = 500
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/models" and method == "GET":
        try:
            result = await asyncio.to_thread(ai_safe_model_options)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except Exception as error:
            status = 502
            body = json.dumps({"error": f"AI 모델 목록 조회 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/reverse-geocode" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(reverse_geocode_location, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError, url_error.URLError) as error:
            status = 400
            body = json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/kb/build" and method == "POST":
        headers = [
            (b"content-type", b"application/x-ndjson; charset=utf-8"),
            (b"cache-control", b"no-cache"),
        ]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def progress(message):
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "log", "message": str(message)})

        def worker():
            try:
                result = build_ai_safe_kb(progress)
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "status": result})
            except Exception as error:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "error": str(error)})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "eof"})

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                event = await queue.get()
                if event.get("type") == "eof":
                    break
                line = json.dumps(event, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
                await send({"type": "http.response.body", "body": line, "more_body": True})
        finally:
            await worker_task
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return
    elif path == "/api/poc/ai-safe-agent/rain" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(run_ai_safe_agent_rain, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = 502
            body = json.dumps({"error": f"AI Safe Agent 강수조회 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/spatial" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(run_ai_safe_agent_spatial, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = 502
            body = json.dumps({"error": f"AI Safe Agent 공간조회 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/poc/ai-safe-agent/analyze-stream" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            prepared = await asyncio.to_thread(prepare_ai_safe_agent_analysis, payload)
            prompt_context = prepared.pop("prompt_context")
            module = load_ai_safe_agent_module()
            provider, model, model_label = module.normalize_model_choice(payload.get("ai_model"))
        except Exception as error:
            status = 400
            body = json.dumps({"error": f"AI Safe Agent 준비 실패: {error}"}, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            headers = [
                (b"content-type", b"application/x-ndjson; charset=utf-8"),
                (b"cache-control", b"no-cache"),
                (b"x-accel-buffering", b"no"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            context_line = json.dumps(
                {"type": "context", "data": prepared, "model": model_label},
                ensure_ascii=False,
                default=str,
            ).encode("utf-8") + b"\n"
            await send({"type": "http.response.body", "body": context_line, "more_body": True})

            if provider == "ollama":
                queue = asyncio.Queue()
                loop = asyncio.get_running_loop()
                stream_payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": module.system_instruction()},
                        {"role": "user", "content": prompt_context},
                    ],
                    "stream": True,
                    "think": False,
                    "keep_alive": "5m",
                    "options": {
                        "num_predict": 160,
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "repeat_penalty": 1.1,
                        "num_ctx": 2048,
                    },
                }

                def ai_safe_stream_worker():
                    try:
                        for chunk in iter_ollama_stream("/api/chat", stream_payload):
                            loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                    except Exception as error:
                        loop.call_soon_threadsafe(queue.put_nowait, ("error", str(error)))
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, ("eof", None))

                worker_task = asyncio.create_task(asyncio.to_thread(ai_safe_stream_worker))
                raw_report = []
                metrics = {}
                stream_failed = False
                try:
                    while True:
                        kind, data = await queue.get()
                        if kind == "chunk":
                            content = data.get("message", {}).get("content", "")
                            if content:
                                raw_report.append(content)
                            if data.get("done"):
                                metrics = {
                                    "total_duration": data.get("total_duration", 0),
                                    "eval_count": data.get("eval_count", 0),
                                }
                        elif kind == "error":
                            stream_failed = True
                            line = json.dumps({"type": "error", "error": f"AI 보고서 생성 실패: {data}"}, ensure_ascii=False).encode("utf-8") + b"\n"
                            await send({"type": "http.response.body", "body": line, "more_body": True})
                        elif kind == "eof":
                            break
                finally:
                    await worker_task
                if not stream_failed:
                    report = module.normalize_report_output(prompt_context, "".join(raw_report))
                    token_line = json.dumps({"type": "token", "content": report}, ensure_ascii=False).encode("utf-8") + b"\n"
                    done_line = json.dumps({"type": "done", "model": model_label, "metrics": metrics}, ensure_ascii=False).encode("utf-8") + b"\n"
                    await send({"type": "http.response.body", "body": token_line, "more_body": True})
                    await send({"type": "http.response.body", "body": done_line, "more_body": True})

            else:
                report, model_label = await asyncio.to_thread(module.generate_report, prompt_context, payload.get("ai_model"))
                token_line = json.dumps({"type": "token", "content": report}, ensure_ascii=False).encode("utf-8") + b"\n"
                done_line = json.dumps({"type": "done", "model": model_label, "metrics": {}}, ensure_ascii=False).encode("utf-8") + b"\n"
                await send({"type": "http.response.body", "body": token_line, "more_body": True})
                await send({"type": "http.response.body", "body": done_line, "more_body": True})

            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
    elif path == "/api/poc/ai-safe-agent/analyze" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(run_ai_safe_agent_analysis, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = 502
            body = json.dumps({"error": f"AI Safe Agent 실행 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/portfolio/report-draft/models" and method == "GET":
        try:
            result = await asyncio.to_thread(report_draft_model_options)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except Exception as error:
            status = 503
            body = json.dumps(
                {"error": f"보고서 모델 목록 조회 실패: {error}"}, ensure_ascii=False
            ).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/portfolio/report-draft/generate" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(run_report_draft, payload)
            body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        except (ValueError, json.JSONDecodeError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = 502
            body = json.dumps(
                {"error": f"보고서 초안 생성 실패: {error}"}, ensure_ascii=False
            ).encode("utf-8")
        content_type = "application/json; charset=utf-8"

    elif path == "/api/chunking-models" and method == "GET":
        try:
            result = await asyncio.to_thread(chunking_model_options)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except Exception as error:
            status = 503
            body = json.dumps({"error": f"청킹 모델 목록 조회 실패: {error}"}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/chunking-legacy-compare" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(compare_legacy_tables, payload.get("prompt", ""), payload.get("model", "openai/gpt-4o-mini"))
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 502
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/chunking-plan" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(chunk_document, payload.get("text", ""), payload.get("strategies", []))
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/chunking-embed" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            plans = payload.get("plans")
            if isinstance(plans, list):
                result = await asyncio.to_thread(lambda: [embed_plan(plan) for plan in plans])
                body = json.dumps({"ok": True, "results": result}, ensure_ascii=False).encode("utf-8")
            else:
                result = await asyncio.to_thread(embed_plan, payload.get("plan", {}))
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 502
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/chunking-compare-stream" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as error:
            status = 400
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            headers = [
                (b"content-type", b"application/x-ndjson; charset=utf-8"),
                (b"cache-control", b"no-cache, no-transform"),
                (b"x-accel-buffering", b"no"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            def emit_compare_event(event):
                loop.call_soon_threadsafe(queue.put_nowait, event)
            def compare_worker():
                try:
                    result = compare_tables(
                        payload.get("prompt", ""),
                        payload.get("model", "openai/gpt-4o-mini"),
                        tables=payload.get("tables"),
                        temperature=payload.get("temperature", 0.2),
                        top_k=payload.get("top_k", 5),
                        reranking=payload.get("reranking", False),
                        rerank_model=payload.get("rerank_model"),
                        rag_mode=payload.get("rag_mode", "naive"),
                        event_callback=emit_compare_event,
                    )
                    emit_compare_event({"type": "done", "result": result})
                except Exception as error:
                    emit_compare_event({"type": "error", "error": str(error)})
                finally:
                    emit_compare_event({"type": "eof"})
            worker_task = asyncio.create_task(asyncio.to_thread(compare_worker))
            try:
                while True:
                    event = await queue.get()
                    if event.get("type") == "eof":
                        break
                    line = json.dumps(event, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
                    await send({"type": "http.response.body", "body": line, "more_body": True})
            finally:
                await worker_task
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
    elif path == "/api/chunking-compare" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            result = await asyncio.to_thread(lambda: compare_tables(
                payload.get("prompt", ""),
                payload.get("model", "openai/gpt-4o-mini"),
                tables=payload.get("tables"),
                temperature=payload.get("temperature", 0.2),
                top_k=payload.get("top_k", 5),
                reranking=payload.get("reranking", False),
                rerank_model=payload.get("rerank_model"),
                rag_mode=payload.get("rag_mode", "naive"),
            ))
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 502
            body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/chat" and method == "POST":
        try:
            payload = json.loads((await read_request_body(receive)).decode("utf-8"))
            if not payload.get("model") or not payload.get("messages"):
                raise ValueError("모델과 메시지가 필요합니다.")
            max_tokens = max(64, min(int(payload.get("max_tokens", 256)), 1024))
        except (ValueError, OSError, url_error.URLError, json.JSONDecodeError, TimeoutError) as error:
            status = 502
            body = json.dumps({"error": f"응답 생성 실패: {error}"}, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            attachment_sources = [
                {"type": "FILE", "title": name, "excerpt": "첨부 분석 자료"}
                for name in payload.get("attachments", [])
            ]
            headers = [
                (b"content-type", b"application/x-ndjson; charset=utf-8"),
                (b"cache-control", b"no-cache"),
                (b"x-accel-buffering", b"no"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            stream_payload = {
                "model": payload["model"],
                "messages": payload["messages"],
                "stream": True,
                "keep_alive": "5m",
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": 8192,
                },
            }

            def worker():
                try:
                    for chunk in iter_ollama_stream("/api/chat", stream_payload):
                        loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                except (OSError, url_error.URLError, json.JSONDecodeError, TimeoutError) as error:
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", f"응답 생성 실패: {error}"))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, ("eof", None))

            worker_task = asyncio.create_task(asyncio.to_thread(worker))
            try:
                while True:
                    kind, data = await queue.get()
                    if kind == "chunk":
                        content = data.get("message", {}).get("content", "")
                        if content:
                            token_line = json.dumps({"type": "token", "content": content}, ensure_ascii=False).encode("utf-8") + b"\n"
                            await send({"type": "http.response.body", "body": token_line, "more_body": True})
                        if data.get("done"):
                            done_line = json.dumps({
                                "type": "done",
                                "message": data.get("message", {}),
                                "sources": data.get("sources", []) + attachment_sources,
                                "metrics": {
                                    "total_duration": data.get("total_duration", 0),
                                    "eval_count": data.get("eval_count", 0),
                                },
                            }, ensure_ascii=False).encode("utf-8") + b"\n"
                            await send({"type": "http.response.body", "body": done_line, "more_body": True})
                    elif kind == "error":
                        error_line = json.dumps({"type": "error", "error": data}, ensure_ascii=False).encode("utf-8") + b"\n"
                        await send({"type": "http.response.body", "body": error_line, "more_body": True})
                    elif kind == "eof":
                        break
            finally:
                await worker_task

            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
    elif path == "/admin" and method in {"GET", "HEAD"}:
        body = ADMIN_HTML.encode("utf-8")
        content_type = "text/html; charset=utf-8"
        extra_headers.extend([
            (b"cache-control", b"no-store"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"same-origin"),
        ])
    elif path == "/health":
        body = json.dumps(
            {"status": "healthy", "message": "Main page is running"}
        ).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    else:
        body = build_html().encode("utf-8")
        content_type = "text/html; charset=utf-8"

    headers = [
        (b"content-type", content_type.encode("latin-1")),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({
        "type": "http.response.body",
        "body": b"" if method == "HEAD" else body,
    })
