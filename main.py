from http.server import BaseHTTPRequestHandler, HTTPServer
import asyncio
import json
import socket
import time
from pathlib import Path
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from chunking_compare import chunk_document, compare_legacy_tables, compare_tables, embed_plan, extract_hwpx_payload
from env_utils import env_first, load_project_env
from portfolio_loader import projects_as_json
from supabase_store import is_configured as supabase_configured
from supabase_store import list_history, save_history


load_project_env()

STATIC_DIR = Path(__file__).parent / "static"

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>민즈데이 — Local AI & Portfolio</title>
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
    .main-menu{display:flex;gap:6px;padding:4px;border:1px solid #d6d4ca;border-radius:99px}.main-menu a{padding:8px 17px;border-radius:99px;text-decoration:none;color:#62675e;font-size:13px;font-weight:700}.main-menu a.active{background:#171916;color:white}.portfolio-view{display:none}body.portfolio-mode .home-view{display:none}body.portfolio-mode .portfolio-view{display:block}
    .portfolio-hero{padding:64px max(20px,calc((100% - 1120px)/2)) 42px;border-bottom:1px solid #d6d4ca}.portfolio-hero h1{font-size:clamp(40px,5vw,64px);margin:12px 0}.portfolio-layout{max-width:1120px;margin:auto;padding:42px 20px 90px;display:grid;grid-template-columns:260px minmax(0,1fr);gap:36px;align-items:start}.side-menu{position:sticky;top:98px}.project-list{display:grid;gap:7px}.project-button{padding:15px;text-align:left;border:1px solid transparent;border-radius:12px;background:transparent;cursor:pointer}.project-button strong{display:block}.project-button small{color:#858a81}.project-button.active{background:#fffdf6;border-color:#171916;box-shadow:4px 4px 0 #dfff56}
    .project-document{background:#fffdf6;border:1px solid #d6d4ca;border-radius:20px;overflow:hidden;min-width:0}.document-head,.document-body{padding:clamp(28px,5vw,52px);min-width:0}.document-head{border-bottom:1px solid #e0ded5}.project-meta{display:flex;gap:7px;margin-bottom:24px;flex-wrap:wrap}.project-meta span{padding:6px 10px;background:#eeeaff;color:#6246dd;border-radius:99px;font:11px monospace}.document-head h2{font-size:clamp(30px,4vw,45px);margin:0}.document-head p,.document-body p,.document-body li{line-height:1.8;color:#656b62}.feature-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:24px 0}.feature{padding:18px;border:1px solid #e0ded5;border-radius:12px}.feature b{display:block}.feature span{font-size:13px;color:#747970}.project-lab{display:none;margin-top:10px}.project-lab.active{display:block}.project-default.hidden{display:none}.chunking-shell{display:grid;gap:18px}.chunking-controls{display:grid;grid-template-columns:minmax(0,1fr) 220px 120px;gap:12px;align-items:end}.chunking-controls label{display:block;font-size:12px;font-weight:700;color:#666c63}.chunking-controls textarea,.chunking-controls select,.chunking-controls input{width:100%;margin-top:7px;padding:12px 13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff;font:14px/1.6 inherit}.chunking-controls textarea{min-height:112px;resize:vertical}.chunking-controls input[type=checkbox]{width:auto;margin:0}.rerank-option{min-height:48px;display:flex!important;align-items:center;gap:8px;padding:12px 13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff}.rerank-option input{margin:0}.rerank-option span{font-size:12px;font-weight:800;color:#666c63}.chunking-run{height:48px;border:0;border-radius:14px;background:#171916;color:#dfff56;font-weight:800;cursor:pointer}.chunking-run:disabled{opacity:.45;cursor:wait}.chunking-note{padding:14px 16px;border-radius:14px;background:#f4f0ff;color:#5b47c0;font-size:13px;line-height:1.7}.chunking-compare{display:grid;grid-template-columns:1fr 1fr;gap:16px}.compare-panel{border:1px solid #ddd9cf;border-radius:18px;background:#fcfbf7;overflow:hidden}.compare-head{padding:18px 18px 14px;border-bottom:1px solid #e7e3d8;background:linear-gradient(180deg,#fff,#faf8f1)}.compare-head strong{display:block;font-size:17px}.compare-head small{display:block;margin-top:6px;color:#7b8178}.compare-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.compare-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:#efede5;color:#666c63;font:11px ui-monospace,monospace}.compare-badge.ok{background:#edf9eb;color:#2b7c3b}.compare-badge.error{background:#fff0eb;color:#b44f32}.compare-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}.compare-stat{padding:10px 12px;border:1px solid #e6e2d7;border-radius:12px;background:#fff}.compare-stat b{display:block;font-size:18px;line-height:1.1}.compare-stat span{display:block;margin-top:4px;color:#7b8178;font-size:11px}.compare-body{padding:18px}.compare-answer{padding:16px;border-radius:16px;background:#171916;color:#eff3e9}.compare-answer span{display:block;margin-bottom:8px;color:#dfff56;font:11px ui-monospace,monospace}.compare-answer pre{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.75 inherit;color:#eff3e9}.compare-list{display:grid;gap:10px;margin-top:16px}.compare-item{padding:14px;border:1px solid #e6e2d7;border-radius:14px;background:#fff}.compare-item-head{display:flex;justify-content:space-between;gap:10px;align-items:start}.compare-item strong{display:block;font-size:14px}.compare-score{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;background:#f2eeff;color:#6045d4;font:11px ui-monospace,monospace;white-space:nowrap}.compare-item small{display:block;margin-top:6px;color:#7b8178}.compare-empty{padding:18px;border:1px dashed #d8d4ca;border-radius:14px;color:#7a8077;font-size:13px;text-align:center}.compare-loading .compare-answer,.compare-loading .compare-item,.compare-loading .compare-stat{opacity:.55}.compare-loading .compare-answer::after{content:'비교 중...';display:block;margin-top:10px;color:#dfff56;font:11px ui-monospace,monospace}.compare-status{margin-top:12px;font-size:13px;color:#747970}.compare-grid-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}.compare-grid-head h3{margin:0;font-size:18px}.compare-grid-head p{margin:0;color:#7a8077;font-size:13px}.compare-panel.error .compare-answer{background:#4b2b22;color:#fff5f2}.compare-panel.error .compare-answer span{color:#ffd9c9}@media(max-width:900px){.chunking-controls{grid-template-columns:1fr}.chunking-compare{grid-template-columns:1fr}.compare-stats{grid-template-columns:1fr 1fr}}
    .chunking-lab-v2{display:grid;gap:20px}.chunking-doc-grid{display:grid;grid-template-columns:240px minmax(0,1fr);gap:14px}.chunking-file{display:grid;align-content:start;gap:10px;padding:16px;border:1px dashed #bbb8ad;border-radius:14px;background:#f5f2e9;color:#62675e;font-size:12px;font-weight:800}.chunking-file input{width:100%;font:12px inherit}.chunking-file span{font-weight:500;color:#7a8077;line-height:1.5}.document-input label,.rag-console label{display:block;font-size:12px;font-weight:800;color:#666c63}.document-input textarea{width:100%;min-height:190px;margin-top:7px;padding:13px;border:1px solid #d7d4ca;border-radius:14px;background:#fff;font:13px/1.65 inherit;resize:vertical}.strategy-picker{display:grid;gap:12px;padding:16px;border:1px solid #e0ddd2;border-radius:16px;background:#fbfaf5}.strategy-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.strategy-option{display:flex;gap:9px;align-items:flex-start;padding:13px;border:1px solid #d8d4ca;border-radius:12px;background:#fffdf6;cursor:pointer}.strategy-option input{margin-top:3px}.strategy-option strong{display:block;font-size:13px}.strategy-option span{display:block;margin-top:4px;color:#777d73;font-size:11px;line-height:1.45}.plan-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.plan-actions button,.embed-plan,.chunking-run{min-height:44px;padding:0 14px;border:0;border-radius:12px;background:#171916;color:#dfff56;font-weight:800;cursor:pointer}.plan-actions button:disabled,.embed-plan:disabled,.chunking-run:disabled{opacity:.45;cursor:wait}.chunking-plans{display:grid;gap:14px}.plan-card{border:1px solid #d8d4ca;border-radius:16px;background:#fffdf6;overflow:hidden}.plan-head{display:flex;justify-content:space-between;gap:12px;align-items:start;padding:16px;border-bottom:1px solid #e5e1d6;background:#fbfaf5}.plan-head strong{font-size:17px}.plan-head small{color:#777d73;font:11px ui-monospace,monospace}.plan-body{padding:16px}.plan-desc{font-size:13px;line-height:1.7;color:#62675e}.pros-cons{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.pros-cons div{padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:white}.pros-cons b{font-size:12px}.pros-cons ul{margin:7px 0 0;padding-left:18px;color:#71776e;font-size:12px;line-height:1.6}.embed-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.embed-status{color:#686e65;font-size:12px}.chunk-list{display:grid;gap:8px;max-height:360px;overflow:auto}.chunk-detail{border:1px solid #e4e0d5;border-radius:12px;background:#fff}.chunk-detail summary{padding:11px 13px;cursor:pointer;font-size:12px;font-weight:800;color:#555b52}.chunk-detail pre{padding:0 13px 13px;margin:0;color:#30342f;background:transparent;white-space:pre-wrap;word-break:break-word;font:12px/1.7 inherit}.rag-console{display:grid;gap:14px;padding-top:10px;border-top:1px solid #e3dfd3;min-width:0;max-width:100%;overflow:hidden}.rag-console .chunking-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;min-width:0;max-width:100%}.rag-console .prompt-control{flex:1 0 100%;min-width:0}.rag-console .prompt-control textarea{min-height:104px}.rag-console .chunking-controls>label:not(.prompt-control){flex:1 1 118px;min-width:0}.rag-console .chunking-controls>label:nth-of-type(2){flex:2 1 220px}.rag-console .rerank-option{flex:1 1 150px}.rag-console .chunking-run{flex:1 1 140px;width:auto;min-width:120px;padding:0 10px;white-space:normal}.rag-console label{min-width:0}.chunking-shell,.chunking-lab-v2,.chunking-note,.chunking-compare{min-width:0;max-width:100%}.chunking-note{overflow-wrap:anywhere}.rag-console h3{margin:0;font-size:18px}.chunking-compare.vertical{grid-template-columns:1fr}.result-snippets{width:100%;height:8.7em;margin-top:12px;padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:#fff;color:#3a3f39;font:12px/1.55 inherit;resize:vertical}.compare-chunk-button{margin-top:12px;min-height:36px;padding:0 12px;border:1px solid #171916;border-radius:10px;background:#fffdf6;color:#171916;font-weight:800;cursor:pointer}.compare-chunk-detail{margin-top:10px;display:grid;gap:8px}.compare-chunk-detail[hidden]{display:none}.compare-chunk{padding:12px;border:1px solid #e3dfd3;border-radius:12px;background:#fff}.compare-chunk strong{display:block;font-size:12px}.compare-chunk pre{padding:8px 0 0;color:#30342f;background:transparent;white-space:pre-wrap;word-break:break-word;font:12px/1.65 inherit}.compare-panel[data-embedded="true"] .compare-head{box-shadow:inset 4px 0 0 #dfff56}@media(max-width:900px){.chunking-doc-grid,.strategy-grid,.pros-cons{grid-template-columns:1fr}.rag-console .chunking-controls{display:grid;grid-template-columns:1fr}.rag-console .prompt-control,.rag-console .chunking-controls>label,.rag-console .rerank-option,.rag-console .chunking-run{grid-column:auto;width:100%;min-width:0}}
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
  </style>
</head>
<body>
  <main class="shell"><section class="card">
    <nav class="site-nav"><div class="brand"><i>M</i> 민즈데이</div><div class="main-menu"><a href="/" data-page="home">홈</a><a href="/portfolio" data-page="portfolio">포트폴리오</a></div><div class="health-wrap" id="healthWrap"><div class="health-button" tabindex="0"><span class="health-dot"></span><span id="healthLabel">서버 확인 중</span></div><div class="health-popover"><h3>서비스 세부 상태</h3><div id="healthDetails"></div><small class="health-updated" id="healthUpdated">확인 중...</small></div></div></nav>
    <div class="home-view">
    <section class="chat-home">
      <button class="mobile-panel-toggle chat-drawer-toggle" id="chatDrawerToggle" type="button" aria-controls="chatSidebar" aria-expanded="false"><span>대화 이력</span></button>
      <aside class="chat-sidebar" id="chatSidebar"><button class="new-chat" id="newChat"><span>＋ 새 대화</span><span>⌘ K</span></button><div><div class="chat-history-label">TODAY</div><div class="history-item" id="historyTitle">새로운 대화</div></div><div class="chat-sidebar-note">LOCAL AI<br>대화는 이 브라우저에서만 유지되며 Ollama 로컬 모델로 처리됩니다.</div></aside>
      <div class="chat-main"><header class="chat-toolbar"><div class="model-wrap"><select class="model-select" id="modelSelect" aria-label="AI 모델 선택"><option>모델 불러오는 중...</option></select></div><div class="ollama-status" id="ollamaStatus"><i></i><span>OLLAMA CONNECTED</span></div></header><div class="messages" id="messages"><div class="empty-chat" id="emptyChat"><div><div class="ai-mark">✦</div><h1>무엇이든 물어보세요.</h1><p>로컬에서 실행되는 나만의 AI 어시스턴트입니다.</p><div class="suggestions"><button class="suggestion">Python 함수와 클래스의 차이를 설명해줘</button><button class="suggestion">오늘 배울 AI 개념 하나를 추천해줘</button><button class="suggestion">REST API 예제 코드를 만들어줘</button><button class="suggestion">내 코드의 오류를 같이 찾아줘</button></div></div></div></div><div class="composer-area"><form class="composer" id="chatForm"><textarea id="chatInput" rows="1" placeholder="메시지를 입력하세요..." aria-label="메시지"></textarea><button class="send-button" id="sendButton" type="submit" aria-label="보내기">↑</button></form><div class="composer-hint">AI는 실수할 수 있습니다. 중요한 정보는 한 번 더 확인하세요.</div></div></div>
      <aside class="source-panel" id="sourcePanel"><details class="model-settings"><summary>⚙ 모델별 설정</summary><label>시스템 프롬프트<textarea id="systemPrompt" rows="5"></textarea></label><label>최대 출력 토큰<select id="maxTokens"><option value="128">128 · 빠름</option><option value="256" selected>256 · 권장</option><option value="512">512 · 상세</option><option value="1024">1024 · 느림</option></select></label><button id="saveSettings" type="button">이 모델 설정 저장</button></details><div class="attachment-box"><input type="file" id="fileInput" multiple accept=".txt,.md,.csv,.json,.py,.js,.html,.css,.yaml,.yml,.log" hidden><button id="attachButton" type="button">＋ 분석 자료 첨부</button><div id="attachedFiles"></div><small>텍스트·코드 파일, 파일당 최대 200KB</small></div><div class="source-head"><h2>사용한 자료</h2><span class="source-count" id="sourceCount">0</span></div><div id="sourceList"><div class="source-empty"><i>⌕</i><strong>아직 사용한 자료가 없어요</strong><br>웹 검색 또는 RAG 문서가 사용되면<br>이곳에 출처가 표시됩니다.</div></div><div class="source-note">출처는 응답에 실제로 연결된 웹 URL과 RAG 메타데이터만 표시합니다.</div></aside>
    </section>
    <header class="hero"><div><div class="kicker">A FIELD GUIDE TO INTELLIGENCE</div><h1>기계는 어떻게<br><span class="marker">생각을 배울까?</span></h1><p>인공지능은 마법이 아닙니다. 데이터를 관찰하고 패턴을 압축해 다음을 예측하는 수학적 시스템이죠. 복잡한 AI의 원리를 직관적인 이야기로 탐험해 보세요.</p><div class="actions"><a class="button primary" href="#concept">탐험 시작하기 ↓</a><a class="button secondary" href="#topics">5분 핵심 요약</a></div></div><div class="hero-art"><div class="orbit"></div><div class="brain">⌁</div></div></header>
    <section class="section" id="concept"><div class="head"><div><span class="kicker">01 / THE BIG IDEA</span><h2>AI를 움직이는<br>네 가지 재료</h2></div><p>AI는 데이터에서 반복되는 관계를 찾아 내부의 숫자들을 조절합니다. 버튼을 눌러 각 요소의 역할을 확인해 보세요.</p></div><div class="tabs"><button class="tab active" data-key="data">데이터</button><button class="tab" data-key="model">모델</button><button class="tab" data-key="learn">학습</button><button class="tab" data-key="infer">추론</button></div><article class="theory"><div class="theory-copy"><span class="kicker" id="tag">INGREDIENT 01</span><h2 id="title">경험을 숫자로 바꾼 데이터</h2><p id="desc">사진, 문장, 소리처럼 세상에서 수집한 사례를 컴퓨터가 읽을 수 있는 숫자로 표현합니다. 데이터의 다양성과 품질은 AI가 바라보는 세계의 경계를 결정합니다.</p></div><div class="flow"><div class="node"><div><b>01</b>현실 세계</div></div>→<div class="node"><div><b>0·1</b>숫자 표현</div></div>→<div class="node"><div><b>∞</b>패턴</div></div></div></article></section>
    <section class="section dark" id="learn"><div class="head"><div><span class="kicker">02 / HOW IT LEARNS</span><h2>정답에 가까워지는<br>반복의 기술</h2></div><p>예측하고, 틀린 정도를 계산하고, 아주 조금 수정하는 일을 수백만 번 반복합니다.</p></div><div class="steps"><article class="step"><em>STEP 01</em><h3>입력과 예측</h3><p>데이터가 여러 층을 통과하며 예측값으로 변환됩니다. 처음의 예측은 무작위에 가깝습니다.</p></article><article class="step"><em>STEP 02</em><h3>오차 측정</h3><p>예측과 정답의 차이를 손실 함수로 계산합니다. 숫자가 작을수록 더 좋은 예측입니다.</p></article><article class="step"><em>STEP 03</em><h3>역전파</h3><p>오차의 책임을 각 연결에 나눠 전달합니다. 미분은 수정 방향을 알려주는 나침반입니다.</p></article><article class="step"><em>STEP 04</em><h3>가중치 갱신</h3><p>연결의 세기를 조금 바꿔 다시 예측합니다. 반복 속에서 모델만의 규칙이 생깁니다.</p></article></div></section>
    <section class="section" id="topics"><div class="head"><div><span class="kicker">03 / THE TOOLKIT</span><h2>오늘의 AI를 만든<br>세 가지 전환점</h2></div><p>아이디어가 쌓이며 AI는 보는 기계에서 언어를 이해하고 새로운 것을 만드는 시스템으로 확장됐습니다.</p></div><div class="topics"><article class="topic"><span>NEURAL NETWORK</span><h3>신경망</h3><p>작은 계산 단위를 여러 층으로 연결해 단순한 특징에서 복잡한 개념까지 단계적으로 추출합니다.</p></article><article class="topic"><span>ATTENTION</span><h3>트랜스포머</h3><p>모든 단어의 관계를 동시에 살피는 어텐션으로 긴 맥락과 의미를 효과적으로 이해합니다.</p></article><article class="topic"><span>GENERATION</span><h3>생성형 AI</h3><p>학습한 확률 분포에서 다음 토큰이나 픽셀을 예측해 전에 없던 문장과 이미지를 만듭니다.</p></article></div></section>
    <section class="ethics" id="ethics"><div><span class="kicker" style="color:#dfff56">04 / HUMAN IN THE LOOP</span><h2>똑똑함보다<br>중요한 질문</h2><p>AI의 결과는 데이터와 설계자의 선택을 반영합니다. 성능뿐 아니라 누구에게 어떤 영향을 주는지도 함께 살펴야 합니다.</p></div><div class="checks"><div><b>✓</b> 편향: 데이터에서 누가 빠져 있는가?</div><div><b>✓</b> 검증: 그럴듯한 답은 사실인가?</div><div><b>✓</b> 책임: 최종 결정을 사람이 책임지는가?</div></div></section>
    </div>
    <div class="portfolio-view">
      <header class="portfolio-hero"><span class="kicker">LEARNING ARCHIVE / 2026</span><h1>배우고, 만들고,<br>기록한 것들.</h1><p>교육과 실습에서 만든 Python 프로젝트를 실행 방법과 배운 점까지 함께 정리하는 성장형 포트폴리오입니다.</p></header>
      <div class="portfolio-layout">
        <button class="mobile-panel-toggle project-drawer-toggle" id="projectDrawerToggle" type="button" aria-controls="projectSideMenu" aria-expanded="false"><span>프로젝트</span></button>
        <aside class="side-menu" id="projectSideMenu"><h2 class="kicker">PROJECT INDEX</h2><div class="project-list" id="projectList"></div></aside>
        <article class="project-document"><header class="document-head"><div class="project-meta" id="projectMeta"></div><h2 id="projectTitle"></h2><p id="projectSummary"></p></header><div class="document-body"><div class="project-default" id="projectDefaultView"><h3>프로젝트 설명</h3><p id="projectDescription"></p><div class="feature-grid" id="projectFeatures"></div><h3>핵심 코드</h3><div class="code-wrap"><div class="code-head"><span id="codeFile">main.py</span><button class="copy-code" id="copyCode">코드 복사</button></div><pre><code id="projectCode"></code></pre></div><h3>실행 방법</h3><ol id="projectUsage"></ol><div class="next-note" id="projectNote"></div></div><section class="project-lab" id="projectLab"></section></div></article>
      </div>
    </div>
    <footer><span>민즈데이 · 배우고 만드는 개발 기록</span><a href="/health">SERVICE HEALTH ↗</a></footer>
    <button class="drawer-backdrop" id="drawerBackdrop" type="button" aria-label="메뉴 닫기"></button>
  </section></main>
  <script>
    const info={data:['INGREDIENT 01','경험을 숫자로 바꾼 데이터','사진, 문장, 소리처럼 세상에서 수집한 사례를 컴퓨터가 읽을 수 있는 숫자로 표현합니다. 데이터의 다양성과 품질은 AI가 바라보는 세계의 경계를 결정합니다.'],model:['INGREDIENT 02','패턴을 담는 계산 구조','모델은 입력을 출력으로 바꾸는 거대한 수학 함수입니다. 수많은 가중치가 어떤 특징에 주목하고 어떻게 조합할지 기억합니다.'],learn:['INGREDIENT 03','실수에서 규칙을 찾는 학습','예측과 정답 사이의 오차를 구하고, 오차가 줄어드는 방향으로 가중치를 조금씩 수정합니다. 이 반복이 기계가 경험을 쌓는 방식입니다.'],infer:['INGREDIENT 04','배운 것을 적용하는 추론','새로운 입력이 들어오면 저장된 패턴으로 가장 가능성 높은 결과를 계산합니다. 챗봇의 답변도 다음 단어를 연속해서 추론한 결과입니다.']};
    document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelector('.tab.active').classList.remove('active');b.classList.add('active');const x=info[b.dataset.key];tag.textContent=x[0];title.textContent=x[1];desc.textContent=x[2]});

    // 새 실습은 아래 배열에 항목 하나만 추가하면 좌측 메뉴와 본문에 자동 반영됩니다.
    const fallbackProjects=[
      {id:'calculator',no:'01',date:'Python Basics',title:'함수로 만든 미니 계산기',summary:'조건문과 함수를 이용해 사칙연산을 처리하는 첫 번째 Python 실습입니다.',description:'입력값과 연산자를 함수에 전달하고, 잘못된 연산이나 0으로 나누는 상황을 안전하게 처리했습니다. 작은 예제지만 함수의 책임 분리와 예외 처리의 기초를 담았습니다.',tags:['Python','함수','예외 처리'],features:[['함수 분리','연산 로직을 calculate 함수 하나로 분리했습니다.'],['안전한 입력','지원하지 않는 연산과 0 나누기를 검사합니다.']],file:'calculator.py',code:`def calculate(a, operator, b):
    if operator == "+":
        return a + b
    if operator == "-":
        return a - b
    if operator == "*":
        return a * b
    if operator == "/" and b != 0:
        return a / b
    raise ValueError("올바른 연산을 입력하세요")

print(calculate(12, "*", 3))`,usage:['calculator.py 파일로 저장합니다.','터미널에서 python calculator.py를 실행합니다.','calculate 함수의 숫자와 연산자를 바꿔 결과를 확인합니다.'],note:'배운 점 · 반복되는 계산을 함수로 묶으면 코드의 의도가 선명해지고 테스트도 쉬워집니다.'},
      {id:'data',no:'02',date:'Data Analysis',title:'CSV 데이터 요약 리포트',summary:'Pandas로 CSV 파일을 읽고 핵심 통계와 결측치를 빠르게 확인하는 실습입니다.',description:'데이터 분석을 시작할 때 가장 먼저 수행하는 구조 확인, 기초 통계, 결측치 집계를 하나의 함수로 정리했습니다. 다양한 CSV 파일에 재사용할 수 있습니다.',tags:['Python','Pandas','CSV'],features:[['빠른 탐색','행·열 크기와 통계 요약을 한 번에 출력합니다.'],['품질 점검','열별 결측치 개수를 자동으로 집계합니다.']],file:'report.py',code:`import pandas as pd

def create_report(file_path):
    data = pd.read_csv(file_path)
    print(f"데이터 크기: {data.shape}")
    print(data.describe(include="all"))
    print("\\n결측치")
    print(data.isna().sum())

create_report("sample.csv")`,usage:['pip install pandas로 라이브러리를 설치합니다.','분석할 파일을 sample.csv 이름으로 준비합니다.','python report.py를 실행해 요약 결과를 확인합니다.'],note:'확장 아이디어 · Matplotlib 그래프와 HTML 리포트 저장 기능을 다음 단계로 추가할 수 있습니다.'},
      {id:'api',no:'03',date:'Web API',title:'Uvicorn 헬스체크 API',summary:'ASGI 규격을 이해하고 서비스 상태를 JSON으로 응답하는 간단한 웹 API입니다.',description:'웹 서버와 애플리케이션이 통신하는 ASGI 구조를 직접 구현했습니다. 운영 환경에서 프록시가 서비스 생존 여부를 확인하는 /health 경로도 제공합니다.',tags:['Python','ASGI','Uvicorn'],features:[['표준 인터페이스','프레임워크 없이 ASGI 요청·응답 흐름을 익혔습니다.'],['상태 확인','/health에서 일관된 JSON 응답을 반환합니다.']],file:'main.py',code:`import json

async def app(scope, receive, send):
    body = json.dumps({"status": "healthy"}).encode()
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({"type": "http.response.body", "body": body})`,usage:['pip install uvicorn으로 서버를 설치합니다.','uvicorn main:app --reload 명령을 실행합니다.','브라우저에서 http://127.0.0.1:8000/health를 엽니다.'],note:'현재 이 포트폴리오 사이트 자체가 같은 방식으로 서비스되고 있습니다.'}
    ];

    const loadedProjects=__PROJECTS_JSON__;
    const projects=loadedProjects.length ? loadedProjects : fallbackProjects;

    async function readJsonResponse(response){
      const text=await response.text();
      try{return JSON.parse(text)}catch(e){throw new Error(text.trim().slice(0,220)||`HTTP ${response.status} 응답을 해석하지 못했습니다.`)}
    }

    function renderLegacyChunkingLab(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="chunking-shell"><div class="compare-grid-head"><h3>청킹 비교 시뮬레이션</h3><p>같은 프롬프트를 두 테이블에 각각 적용해 검색 결과를 나란히 비교합니다.</p></div><div class="chunking-controls"><label>프롬프트 입력<textarea id="legacyChunkingPromptInput" placeholder="질문이나 비교할 요청을 입력하세요.">민원 처리 법에 대해 알려줘</textarea></label><label>모델 선택<select id="legacyChunkingModelSelect"><option value="openai/gpt-4o-mini" selected>openai/gpt-4o-mini</option><option value="llama3.2:1b">llama3.2:1b · local Ollama</option></select></label><button class="chunking-run" id="legacyChunkingRunButton" type="button">비교 실행</button></div><div class="chunking-note">RAG Supabase 비교 대상 · 왼쪽은 <b>documents</b>, 오른쪽은 <b>documents_test</b> 테이블을 사용합니다. 모델은 OpenRouter의 openai/gpt-4o-mini 또는 로컬 Ollama의 llama3.2:1b 중에서 선택할 수 있으며, 검색된 문맥을 바탕으로 실제 답변을 호출합니다.</div><div class="chunking-compare" id="legacyChunkingCompare"><article class="compare-panel" data-panel="documents"><div class="compare-head"><strong>일반 청킹</strong><small>documents</small><div class="compare-meta"><span class="compare-badge">대기 중</span></div></div><div class="compare-body"><div class="compare-empty">프롬프트를 입력하고 비교 실행을 눌러주세요.</div></div></article><article class="compare-panel" data-panel="documents_test"><div class="compare-head"><strong>전처리 청킹</strong><small>documents_test</small><div class="compare-meta"><span class="compare-badge">대기 중</span></div></div><div class="compare-body"><div class="compare-empty">프롬프트를 입력하고 비교 실행을 눌러주세요.</div></div></article></div></section>`;
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
    }

    function renderChunkingRagLab(p){
      projectDefaultView.classList.add('hidden');
      projectLab.classList.add('active');
      projectLab.innerHTML=`<section class="chunking-shell chunking-lab-v2"><div class="compare-grid-head"><h3>05. 청킹실습(과제)</h3><p>선택한 청킹 방식만 청킹, 임베딩, 질문 비교 대상으로 사용합니다.</p></div><div class="chunking-doc-grid"><label class="chunking-file">첨부 문서<input id="chunkingFileInput" type="file" accept=".hwpx,.txt,.md,.csv,.json,.html,.xml,.py,.js,.css,.log"><span id="chunkingFileName">텍스트 기반 문서 또는 .hwpx를 선택하세요.</span></label><div class="document-input"><label>문서 내용<textarea id="chunkingDocumentInput" placeholder="문서를 붙여넣거나 왼쪽에서 파일을 첨부하세요."></textarea></label></div></div><div class="strategy-picker"><div class="compare-grid-head"><h3>청킹 알고리즘 선택</h3><p>최대 3개까지 선택할 수 있습니다.</p></div><div class="strategy-grid"><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="fixed" checked><span><strong>고정 길이 청킹</strong><span>균일한 크기와 overlap으로 빠르게 분할</span></span></label><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="recursive" checked><span><strong>문단 우선 재귀 청킹</strong><span>문단과 문장 경계를 우선 보존</span></span></label><label class="strategy-option"><input type="checkbox" name="chunkStrategy" value="semantic" checked><span><strong>문장 윈도우 의미 청킹</strong><span>겹치는 문장 묶음으로 주변 의미 보존</span></span></label></div><div class="plan-actions"><button id="chunkingBuildButton" type="button">1. 청킹 실행</button><button id="chunkingEmbedButton" type="button" disabled>2. 임베딩 실행</button><span class="embed-status" id="chunkingEmbedProgress">(0/0 완료)</span><span class="embed-status" id="chunkingPlanStatus">문서를 준비하세요.</span></div></div><div class="chunking-plans" id="chunkingPlans"><div class="compare-empty">청킹 실행 후 방식별 설명, 장단점, 실제 청크가 표시됩니다.</div></div><div class="rag-console"><h3>질문 비교</h3><div class="chunking-controls"><label class="prompt-control">질문 입력<textarea id="chunkingPromptInput" placeholder="임베딩된 문서에 질문하세요.">이 문서의 핵심 내용을 요약해줘</textarea></label><label>모델 선택<select id="chunkingModelSelect"><option value="openai/gpt-4o-mini" selected>OpenRouter · gpt-4o-mini</option><option value="llama3.2:1b">Ollama · llama3.2:1b</option></select></label><label>RAG 방식<select id="chunkingRagMode"><option value="both" selected>Naive + Advanced</option><option value="naive">Naive RAG</option><option value="advanced">Advanced RAG</option></select></label><label>Temperature<input id="chunkingTemperature" type="number" min="0" max="1.5" step="0.1" value="0.2"></label><label>Top-K<input id="chunkingTopK" type="number" min="1" max="10" step="1" value="5"></label><label class="rerank-option"><input id="chunkingRerankToggle" type="checkbox"><span>Reranking</span></label><button class="chunking-run" id="chunkingRunButton" type="button" disabled>3. 질문 실행</button></div><div class="chunking-note">진행 순서 · <b>1. 청킹 실행</b> 후 <b>2. 임베딩 실행</b>이 활성화되고, 임베딩 완료 후 <b>3. 질문 실행</b>이 활성화됩니다. 선택한 청킹 방식이 1개 또는 2개이면 해당 방식만 임베딩하고 검색합니다.</div><div class="chunking-compare vertical" id="chunkingCompare"><div class="compare-empty">청킹 실행 후 임베딩을 완료하면 질문을 실행할 수 있습니다.</div></div></div></section>`;
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
            }catch(e){
              replaceComparePanel(compareKey(plan),renderCompareErrorPanel(plan,e.message));
            }finally{
              clearInterval(progressTimer);
              completed+=1;
            }
          }
          planStatus.textContent=`질문 실행 완료 · ${completed}/${panels.length}`;
        }finally{runButton.disabled=false}
      }
      compareEl.addEventListener('click',e=>{const button=e.target.closest('[data-detail-panel]');if(!button)return;const detail=document.getElementById(`chunk-detail-${button.dataset.detailPanel}`);if(!detail)return;detail.hidden=!detail.hidden;button.textContent=detail.hidden?'비교 청크 내용 보기':'비교 청크 내용 닫기'});
      buildButton.onclick=buildChunks;embedButton.onclick=embedAllPlans;runButton.onclick=runCompare;resetExecution('청킹 실행 전입니다.');
    }

    function lastProjectId(){return projects.at(-1)?.id||projects[0]?.id||''}
    let currentProjectId=lastProjectId();
    function renderProject(id){
      const p=projects.find(x=>x.id===id)||projects[0];
      currentProjectId=p.id;
      document.querySelectorAll('.project-button').forEach(b=>b.classList.toggle('active',b.dataset.id===p.id));
      projectMeta.innerHTML=p.tags.map(x=>`<span>${x}</span>`).join(''); projectTitle.textContent=p.title; projectSummary.textContent=p.summary;
      if(p.id==='chunking-lab'){
        renderLegacyChunkingLab(p);
      }else if(p.id==='chunking-rag-lab'){
        renderChunkingRagLab(p);
      }else{
        projectLab.classList.remove('active'); projectLab.innerHTML=''; projectDefaultView.classList.remove('hidden');
        projectDescription.textContent=p.description;
        projectFeatures.innerHTML=p.features.map(x=>`<div class="feature"><b>${x[0]}</b><span>${x[1]}</span></div>`).join(''); codeFile.textContent=p.file; projectCode.textContent=p.code;
        projectUsage.innerHTML=p.usage.map(x=>`<li>${x}</li>`).join(''); projectNote.textContent=p.note;
      }
      return p;
    }
    function projectIdFromLocation(){
      const pathMatch=location.pathname.match(/^\/portfolio\/([^/?#]+)/);
      return pathMatch ? decodeURIComponent(pathMatch[1]) : new URLSearchParams(location.search).get('project');
    }
    function projectUrl(id){return `/portfolio?project=${encodeURIComponent(id)}`}
    projectList.innerHTML=projects.map(p=>`<button class="project-button" data-id="${p.id}"><strong>${p.no}. ${p.title}</strong><small>${p.date}</small></button>`).join('');
    projectList.addEventListener('click',e=>{const b=e.target.closest('.project-button');if(b){const p=renderProject(b.dataset.id);if(document.body.classList.contains('portfolio-mode'))history.pushState({},'',projectUrl(p.id));closeMobileDrawers()}}); renderProject(projectIdFromLocation()||lastProjectId());
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
    document.querySelector('.ai-mark').innerHTML='<img src="/static/images/logo.png" alt="민즈데이 로고">';
    let conversation=[],generating=false,currentChatId=crypto.randomUUID();const clientId=localStorage.getItem('minzday.clientId')||crypto.randomUUID();localStorage.setItem('minzday.clientId',clientId);const historyList=document.createElement('div');historyList.className='history-list';document.getElementById('historyTitle').parentElement.append(historyList);
    async function loadHistory(){
      try{
        const r=await fetch(`/api/history?client_id=${encodeURIComponent(clientId)}`),data=await r.json();if(!r.ok)throw new Error(data.error);
        historyList.innerHTML=data.items.map(item=>`<button class="history-item ${item.id===currentChatId?'active':''}" data-history="${item.id}">${item.title}</button>`).join('');
        historyList.querySelectorAll('button').forEach(b=>b.onclick=()=>{
          const item=data.items.find(entry=>entry.id===b.dataset.history);if(!item)return;
          currentChatId=item.id;conversation=item.messages;messagesEl.innerHTML='';conversation.forEach(m=>addMessage(m.role,m.content));document.getElementById('historyTitle').textContent=item.title;
          if([...modelSelectEl.options].some(o=>o.value===item.model)){modelSelectEl.value=item.model;loadModelSettings()}
          historyList.querySelectorAll('.history-item').forEach(button=>button.classList.toggle('active',button.dataset.history===currentChatId));
        });
      }catch(e){historyList.innerHTML='<div class="history-db-status">Supabase 연결 후 대화 이력이 표시됩니다.</div>'}
    }
    async function persistHistory(){if(!conversation.length)return;const title=conversation.find(m=>m.role==='user')?.content.slice(0,40)||'새로운 대화';try{await fetch('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:currentChatId,client_id:clientId,title,model:modelSelectEl.value,messages:conversation})});loadHistory()}catch(e){console.warn('History save failed',e)}}
    async function loadModels(){try{const r=await fetch('/api/models'),data=await r.json();if(!r.ok)throw new Error(data.error);modelSelectEl.innerHTML=data.models.map(m=>`<option value="${m.name}">${m.name}${m.details.parameter_size?' · '+m.details.parameter_size:''}</option>`).join('');if(!data.models.length)throw new Error('설치된 모델이 없습니다.')}catch(e){modelSelectEl.innerHTML='<option>모델 연결 실패</option>';document.getElementById('ollamaStatus').innerHTML='<i style="background:#ff704d"></i><span>OLLAMA OFFLINE</span>';}}
    async function loadHealth(){const wrap=document.getElementById('healthWrap');try{const r=await fetch('/api/health'),data=await r.json();wrap.classList.toggle('healthy',data.ok);wrap.classList.toggle('unhealthy',!data.ok);healthLabel.textContent=data.ok?'서버 정상':'서버 이상';healthDetails.innerHTML=Object.values(data.services).map(s=>`<div class="detail-row ${s.ok?'ok':'fail'}"><span><i></i>${s.label}</span><b>${s.detail}</b></div>`).join('');healthUpdated.textContent=`마지막 확인 ${new Date(data.checked_at*1000).toLocaleTimeString()}`}catch(e){wrap.className='health-wrap unhealthy';healthLabel.textContent='상태 확인 실패';healthDetails.innerHTML='<div class="detail-row fail"><span><i></i>헬스 API</span><b>연결 실패</b></div>'}}
    function processPanel(item,start){const box=document.createElement('details');box.className='process-box live';box.open=true;const requestCount=conversation.length;const attachmentCount=attachedData.length;box.innerHTML='<summary><span class="process-summary">생성 중 · 준비 단계</span><span class="process-toggle">자세히 보는 중</span><span class="process-meta">0.0s</span></summary><div class="process-inner"><div class="process-log"></div><div class="references">참고 자료 확인 중...</div></div>';const log=box.querySelector('.process-log');const summaryEl=box.querySelector('.process-summary');const toggleEl=box.querySelector('.process-toggle');const metaEl=box.querySelector('.process-meta');const refs=box.querySelector('.references');const timers=[];let finished=false,firstChunkSeen=false,expansionNoted=false;box.addEventListener('toggle',()=>{if(finished)return;toggleEl.textContent=box.open?'자세히 보는 중':'간단히 보는 중'});function addStep(text,state='done'){const row=document.createElement('div');row.className=`process-step ${state}`.trim();row.innerHTML=`<i></i><span>${text}</span>`;log.append(row);log.parentElement.scrollTop=log.parentElement.scrollHeight;messagesEl.scrollTop=messagesEl.scrollHeight;return row}const intro='요청 수신 · '+requestCount+'개 메시지 맥락 정리 완료'+(attachmentCount?` · 첨부 ${attachmentCount}개 포함`:'');addStep(intro,'done');const stages=[['프롬프트와 모델 설정을 적용하고 있어요.','done','생성 중 · 입력 구성'],['로컬 모델에 요청을 전달했어요.','done','생성 중 · 모델 호출'],['응답 초안을 계산하고 있어요.','active','생성 중 · 초안 생성'],['문장 흐름과 길이를 정리하고 있어요.','active','생성 중 · 답변 다듬기']];stages.forEach(([text,state,summary],index)=>{timers.push(setTimeout(()=>{if(finished)return;addStep(text,state);summaryEl.textContent=summary},450+(index*900)))});const tick=setInterval(()=>{if(finished)return;metaEl.textContent=`${((performance.now()-start)/1000).toFixed(1)}s`},120);item.children[1].append(box);return{stream(answer){if(finished)return;if(!firstChunkSeen&&answer.trim()){firstChunkSeen=true;summaryEl.textContent='생성 중 · 실시간 출력';addStep('첫 응답 조각이 도착해 화면에 바로 표시하고 있어요.','active')}if(!expansionNoted&&answer.length>180){expansionNoted=true;addStep('답변 분량이 늘어나고 있어요. 문단 단위로 이어 붙이는 중입니다.','muted')}},finish(answer,metrics,ok=true){finished=true;timers.forEach(clearTimeout);clearInterval(tick);const seconds=metrics?.total_duration?metrics.total_duration/1e9:(performance.now()-start)/1000;const evalCount=metrics?.eval_count;const urls=[...new Set(answer.match(/https?:\/\/[^\s)\]]+/g)||[])];const statusText=ok?`${modelSelectEl.value} 응답 생성 완료`:'응답 생성 중 오류 발생';addStep(statusText+(evalCount?` · ${evalCount} tokens`:''),ok?'done':'error');refs.textContent=urls.length?'참고 자료 · ':'참고 자료 · 외부 자료를 사용하지 않은 로컬 모델 응답';urls.forEach((url,i)=>{const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noreferrer';a.textContent=`[${i+1}] ${url}`;refs.append(document.createElement('br'),a)});summaryEl.textContent=ok?`생성 완료 · ${seconds.toFixed(1)}초`:`오류로 종료 · ${seconds.toFixed(1)}초`;toggleEl.textContent='요약만 표시';metaEl.textContent=ok?(evalCount?`${evalCount} tok · ${urls.length} refs`:`${urls.length} refs`):'retry needed';box.classList.remove('live');box.classList.add('compact');box.open=false}}}
    function addMessage(role,text,extra=''){document.getElementById('emptyChat')?.remove();const item=document.createElement('article');item.className=`message ${role} ${extra}`;const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent=role==='user'?'YOU':'✦';const wrap=document.createElement('div');const label=document.createElement('div');label.className='message-role';label.textContent=role==='user'?'나':modelSelectEl.value;const body=document.createElement('div');body.className='message-body';body.textContent=text;wrap.append(label,body);item.append(avatar,wrap);messagesEl.append(item);messagesEl.scrollTop=messagesEl.scrollHeight;return item;}
    function renderSources(answer,sources=[]){const urls=[...new Set(answer.match(/https?:\/\/[^\s)\]]+/g)||[])];const merged=[...sources,...urls.map(url=>({type:'WEB',title:new URL(url).hostname,url,excerpt:'응답에 포함된 웹 링크'}))];sourceCount.textContent=merged.length;if(!merged.length){sourceList.innerHTML='<div class="source-empty"><i>⌕</i><strong>외부 자료 없음</strong><br>이 답변은 로컬 모델의 학습 지식으로<br>생성되었습니다.</div>';return}sourceList.textContent='';merged.forEach((s,i)=>{const card=document.createElement(s.url?'a':'div');card.className='source-card';if(s.url){card.href=s.url;card.target='_blank';card.rel='noreferrer'};const type=document.createElement('span');type.className='source-type';type.textContent=s.type||'RAG';const title=document.createElement('strong');title.textContent=`${i+1}. ${s.title||s.document||'참고 문서'}`;const detail=document.createElement('small');detail.textContent=s.excerpt||s.url||s.source||'';card.append(type,title,detail);sourceList.append(card)})}
    const defaultPrompt='항상 자연스러운 한국어로만 답변하세요. 다른 언어 문자를 섞지 마세요. 핵심부터 간결하고 정확하게 설명하고, 모르는 내용은 추측하지 말고 모른다고 말하세요.';let attachedData=[];
    const composerEl=document.querySelector('.composer'),composerArea=document.querySelector('.composer-area'),attachmentBoxEl=document.querySelector('.attachment-box'),attachButtonEl=document.getElementById('attachButton'),fileInputEl=document.getElementById('fileInput'),attachedFilesEl=document.getElementById('attachedFiles'),fileShelf=document.createElement('div');fileShelf.className='composer-files';fileShelf.innerHTML='<div class="composer-files-head"><b>첨부 자료</b><span>이 대화의 이후 질문에도 계속 사용</span></div>';attachButtonEl.className='composer-attach';attachButtonEl.textContent='＋';attachButtonEl.title='분석 자료 첨부';composerEl.insertBefore(attachButtonEl,inputEl);fileShelf.append(attachedFilesEl);composerArea.insertBefore(fileShelf,composerEl);composerArea.append(fileInputEl);attachmentBoxEl.remove();
    function settingsKey(){return`minzday.settings.${modelSelectEl.value}`}
    function loadModelSettings(){const saved=JSON.parse(localStorage.getItem(settingsKey())||'{}');systemPrompt.value=saved.prompt||defaultPrompt;maxTokens.value=String(saved.maxTokens||256)}
    saveSettings.onclick=()=>{localStorage.setItem(settingsKey(),JSON.stringify({prompt:systemPrompt.value.trim(),maxTokens:Number(maxTokens.value)}));saveSettings.textContent='저장 완료 ✓';setTimeout(()=>saveSettings.textContent='이 모델 설정 저장',1200)};
    attachButtonEl.onclick=()=>fileInputEl.click();fileInputEl.onchange=async()=>{for(const file of fileInputEl.files){if(file.size>200*1024){alert(`${file.name}: 200KB를 초과합니다.`);continue}if(attachedData.length>=3){alert('파일은 최대 3개까지 첨부할 수 있습니다.');break}attachedData.push({name:file.name,content:await file.text()})}renderAttachments();fileInputEl.value=''};
    function renderAttachments(){fileShelf.classList.toggle('active',attachedData.length>0);attachedFilesEl.innerHTML=attachedData.map((f,i)=>`<div class="file-chip"><span>📄 ${f.name}</span><button data-file="${i}" title="첨부 해제">×</button></div>`).join('');attachedFilesEl.querySelectorAll('button').forEach(b=>b.onclick=()=>{attachedData.splice(Number(b.dataset.file),1);renderAttachments()})}
    async function sendMessage(text){
      text=text.trim();if(!text||generating)return;generating=true;sendEl.disabled=true;
      conversation.push({role:'user',content:text});addMessage('user',text);
      if(conversation.length===1)document.getElementById('historyTitle').textContent=text.slice(0,28);
      inputEl.value='';inputEl.style.height='auto';
      const started=performance.now(),pending=addMessage('assistant','응답을 생각하고 있습니다…','typing'),process=processPanel(pending,started);
      const requestMessages=[];if(systemPrompt.value.trim())requestMessages.push({role:'system',content:systemPrompt.value.trim()});if(attachedData.length)requestMessages.push({role:'system',content:'다음 첨부 자료를 바탕으로 질문에 답하세요. 자료에 없는 내용은 구분해서 설명하세요.\n\n'+attachedData.map(f=>`[파일: ${f.name}]\n${f.content}`).join('\n\n')});requestMessages.push(...conversation);
      try{
        const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:modelSelectEl.value,messages:requestMessages,max_tokens:Number(maxTokens.value),attachments:attachedData.map(f=>f.name)})});
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
    document.getElementById('chatForm').onsubmit=e=>{e.preventDefault();sendMessage(inputEl.value)};inputEl.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage(inputEl.value)}};inputEl.oninput=()=>{inputEl.style.height='auto';inputEl.style.height=Math.min(inputEl.scrollHeight,130)+'px'};
    document.querySelectorAll('.suggestion').forEach(b=>b.onclick=()=>sendMessage(b.textContent));document.getElementById('newChat').onclick=()=>{conversation=[];location.reload()};modelSelectEl.onchange=()=>{localStorage.setItem('minzday.selectedModel',modelSelectEl.value);conversation=[];currentChatId=crypto.randomUUID();document.getElementById('historyTitle').textContent='새로운 대화';loadModelSettings()};loadModels().then(()=>{const saved=localStorage.getItem('minzday.selectedModel');if(saved&&[...modelSelectEl.options].some(o=>o.value===saved))modelSelectEl.value=saved;loadModelSettings();loadHistory()});loadHealth();setInterval(loadHealth,15000);
    function showPage(page,push=false,projectId=null){const portfolio=page==='portfolio';const requestedProject=portfolio?(projectId||projectIdFromLocation()||(push?lastProjectId():currentProjectId||lastProjectId())):null;closeMobileDrawers();document.body.classList.toggle('portfolio-mode',portfolio);document.querySelectorAll('[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===page));if(portfolio)renderProject(requestedProject);if(push)history.pushState({},'',portfolio?(requestedProject?projectUrl(requestedProject):'/portfolio'):'/');scrollTo(0,0)}
    document.querySelectorAll('[data-page]').forEach(a=>a.onclick=e=>{e.preventDefault();showPage(a.dataset.page,true)});addEventListener('popstate',()=>showPage(location.pathname.startsWith('/portfolio')?'portfolio':'home'));showPage(location.pathname.startsWith('/portfolio')?'portfolio':'home');
  </script>
</body>
</html>
"""


def build_html():
    """projects 폴더의 최신 실습 목록을 페이지에 삽입한다."""
    return HTML_PAGE.replace("__PROJECTS_JSON__", projects_as_json())


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
    return {"ok": all(item["ok"] for item in services.values()), "services": services, "checked_at": int(time.time())}


async def read_request_body(receive):
    chunks = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


async def app(scope, receive, send):
    """Uvicorn에서 사용하는 최소 ASGI 애플리케이션."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] != "http":
        return

    path = scope.get("path", "/")
    method = scope.get("method", "GET").upper()
    status = 200

    if path == "/api/history" and method == "GET":
        try:
            query = url_parse.parse_qs(scope.get("query_string", b"").decode("utf-8"))
            client_id = query.get("client_id", [""])[0]
            if not client_id:
                raise ValueError("client_id가 필요합니다.")
            result = await asyncio.to_thread(list_history, client_id)
            body = json.dumps({"configured": True, "items": result}, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError) as error:
            status = 503
            body = json.dumps({"configured": supabase_configured(), "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
    elif path == "/api/history" and method == "POST":
        try:
            record = json.loads((await read_request_body(receive)).decode("utf-8"))
            required = {"id", "client_id", "title", "model", "messages"}
            if not required.issubset(record) or not isinstance(record["messages"], list):
                raise ValueError("잘못된 대화 이력 형식입니다.")
            result = await asyncio.to_thread(save_history, {key: record[key] for key in required})
            body = json.dumps({"saved": True, "item": result}, ensure_ascii=False).encode("utf-8")
        except (ValueError, RuntimeError, json.JSONDecodeError, TimeoutError) as error:
            status = 503
            body = json.dumps({"saved": False, "error": str(error)}, ensure_ascii=False).encode("utf-8")
        content_type = "application/json; charset=utf-8"
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
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({
        "type": "http.response.body",
        "body": b"" if method == "HEAD" else body,
    })


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send_response(self._build_payload())

    def do_HEAD(self):
        self._send_response(self._build_payload(), include_body=False)

    def _build_payload(self):
        if self.path.startswith("/static/"):
            target = (STATIC_DIR / self.path.removeprefix("/static/")).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
                if target.is_file():
                    content_type = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
                    return target.read_bytes(), content_type
            except (ValueError, OSError):
                pass

        if self.path == "/health":
            body = json.dumps({"status": "healthy", "message": "Main page is running"}).encode("utf-8")
            return body, "application/json; charset=utf-8"

        body = build_html().encode("utf-8")
        return body, "text/html; charset=utf-8"

    def _send_response(self, payload, include_body=True):
        body, content_type = payload
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run_server(host="0.0.0.0", port=8000):
    server = HTTPServer((host, port), Handler)
    print(f"Serving temporary landing page at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
