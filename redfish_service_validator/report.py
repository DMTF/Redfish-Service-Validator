# Copyright Notice:
# Copyright 2016-2026 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

import html as html_mod
import json
from datetime import datetime

from redfish_service_validator import metadata
from redfish_service_validator import redfish_logo
from redfish_service_validator.system_under_test import SystemUnderTest

html_template = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Redfish Service Validator &mdash; Test Report</title>
    <style>
      /* ── Reset ── */
      *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
      html, body {{ height: 100%; }}
      body {{
        font-family: "Segoe UI", system-ui, Arial, sans-serif;
        font-size: 13px;
        background: #f0f2f5;
        color: #1a1a2e;
        display: flex;
        flex-direction: column;
      }}

      /* ════════════════════════════
         TOP NAVBAR
         ════════════════════════════ */
      .top-nav {{
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 56px;
        background: linear-gradient(90deg, #0d1b2a 0%, #1a3a5c 60%, #1565c0 100%);
        display: flex;
        align-items: center;
        padding: 0 16px;
        gap: 10px;
        z-index: 1000;
        box-shadow: 0 2px 10px rgba(0,0,0,0.35);
      }}
      .top-nav img {{ height: 34px; border-radius: 4px; flex-shrink: 0; }}
      .nav-brand {{ flex-shrink: 0; }}
      .top-nav-title {{
        color: #fff;
        font-size: 15px;
        font-weight: 700;
        letter-spacing: 0.3px;
        white-space: nowrap;
      }}
      .top-nav-sub {{
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        white-space: nowrap;
      }}
      /* Centered search bar in navbar */
      .top-nav-search-wrap {{
        position: absolute;
        left: 50%; transform: translateX(-50%);
        display: flex; flex-direction: column; align-items: center;
        width: 380px;
        pointer-events: auto;
      }}
      .nav-filter-wrap {{ position: relative; width: 100%; }}
      .nav-filter-wrap .fi {{
        position: absolute; left: 10px; top: 50%;
        transform: translateY(-50%);
        color: rgba(255,255,255,0.5); font-size: 14px;
        pointer-events: none;
      }}
      #uriFilter {{
        width: 100%;
        padding: 6px 30px 6px 30px;
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 20px;
        font-size: 12px; outline: none;
        transition: border-color 0.2s, box-shadow 0.2s;
        font-family: "Cascadia Code","Consolas",monospace;
        color: #fff;
        background: rgba(255,255,255,0.12);
      }}
      #uriFilter::placeholder {{ color: rgba(255,255,255,0.45); }}
      #uriFilter:focus {{
        border-color: #90caf9;
        box-shadow: 0 0 0 3px rgba(144,202,249,0.2);
        background: rgba(255,255,255,0.2);
      }}
      #filterClear {{
        position: absolute; right: 9px; top: 50%;
        transform: translateY(-50%);
        background: none; border: none; cursor: pointer;
        color: rgba(255,255,255,0.5); font-size: 13px; line-height: 1;
        display: none;
      }}
      #filterClear:hover {{ color: #ef5350; }}
      .nav-filter-meta {{
        font-size: 10px; color: rgba(255,255,255,0.5);
        margin-top: 2px; text-align: center;
      }}
      .nav-filter-meta b {{ color: #90caf9; }}
      /* Hamburger button (mobile only) */
      .nav-hamburger {{
        display: none;
        align-items: center; justify-content: center;
        width: 36px; height: 36px;
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 6px; color: #fff; font-size: 18px;
        cursor: pointer; flex-shrink: 0;
      }}
      .nav-hamburger:hover {{ background: rgba(255,255,255,0.2); }}
      .top-nav-meta {{
        color: rgba(255,255,255,0.7);
        font-size: 11px;
        text-align: right;
        line-height: 1.5;
        margin-left: auto;
        flex-shrink: 0;
      }}
      .top-nav-meta a {{ color: #90caf9; text-decoration: none; }}
      .top-nav-meta a:hover {{ text-decoration: underline; }}

      /* ════════════════════════════
         APP SHELL  (sidebar + main)
         ════════════════════════════ */
      .app-shell {{
        display: flex;
        margin-top: 56px;
        height: calc(100vh - 56px);
        overflow: hidden;
      }}
      /* Mobile sidebar backdrop */
      .sidebar-overlay {{
        display: none;
        position: fixed;
        inset: 56px 0 0 0;
        background: rgba(0,0,0,0.45);
        z-index: 99;
      }}
      .sidebar-overlay.show {{ display: block; }}

      /* ── LEFT SIDEBAR ── */
      .sidebar {{
        width: 300px;
        min-width: 300px;
        background: #fff;
        border-right: 1px solid #dde3ec;
        height: 100%;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        box-shadow: 2px 0 8px rgba(0,0,0,0.04);
        z-index: 100;
        transition: left 0.3s ease;
      }}
      .sidebar::-webkit-scrollbar {{ width: 5px; }}
      .sidebar::-webkit-scrollbar-thumb {{ background: #c8d3e0; border-radius: 3px; }}

      .sidebar-section {{
        padding: 16px 18px 10px;
        border-bottom: 1px solid #edf0f5;
      }}
      .sidebar-section:last-child {{ border-bottom: none; }}
      .sidebar-label {{
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8a97aa;
        margin-bottom: 10px;
      }}

      /* Scorecards in sidebar */
      .score-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }}
      .score-tile {{
        border-radius: 8px;
        padding: 10px 12px;
        color: #fff;
        text-align: center;
        font-weight: 700;
      }}
      .score-tile .snum {{ font-size: 26px; line-height: 1.1; }}
      .score-tile .slbl {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; margin-top: 2px; opacity: 0.9; }}
      .st-pass {{ background: linear-gradient(135deg,#27ae60,#2ecc71); }}
      .st-warn {{ background: linear-gradient(135deg,#d68910,#f39c12); }}
      .st-fail {{ background: linear-gradient(135deg,#c0392b,#e74c3c); }}
      .st-skip {{ background: linear-gradient(135deg,#5d6d7e,#85929e); }}

      /* System info in sidebar */
      .sys-table {{ width: 100%; border-collapse: collapse; }}
      .sys-table td {{
        padding: 4px 0;
        font-size: 12px;
        border: none;
        background: transparent;
        vertical-align: top;
        color: #333;
        word-break: break-all;
      }}
      .sys-table td:first-child {{
        font-weight: 600;
        color: #6c757d;
        white-space: nowrap;
        padding-right: 10px;
        min-width: 90px;
      }}

      /* Tally tables in sidebar */
      .tally-panel {{
        margin-bottom: 0;
      }}
      .tally-panel h3 {{
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8a97aa;
        margin-bottom: 8px;
      }}
      .tally-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 11px;
      }}
      .tally-table th {{
        background: #f5f7fa;
        color: #2c3e50;
        font-weight: 700;
        padding: 5px 8px;
        text-align: left;
        border-bottom: 1px solid #dde3ec;
      }}
      .tally-table td {{
        padding: 4px 8px;
        border: none;
        border-bottom: 1px solid #f0f2f5;
        background: #fff;
        color: #444;
      }}
      .tally-table tr:last-child td {{ border-bottom: none; }}
      .tally-table tr:hover td {{ background: #f8fafc; }}
      .tally-table td:last-child {{
        text-align: right;
        font-weight: 700;
        color: #1a3a5c;
        width: 50px;
      }}
      .tally-two-col {{ display: flex; flex-direction: column; gap: 14px; }}



      /* ── MAIN CONTENT ── */
      .main-content {{
        flex: 1;
        min-width: 0;
        padding: 20px 24px 60px;
        overflow-y: auto;
        overflow-x: hidden;
        height: 100%;
      }}
      .main-content::-webkit-scrollbar {{ width: 6px; }}
      .main-content::-webkit-scrollbar-thumb {{ background: #c8d3e0; border-radius: 3px; }}

      /* Section heading */
      .section-heading {{
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8a97aa;
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid #dde3ec;
        display: flex;
        align-items: center;
        gap: 8px;
      }}
      .section-heading .sh-count {{
        background: #e8f0fe;
        color: #0d6efd;
        font-size: 10px;
        padding: 1px 7px;
        border-radius: 10px;
        font-weight: 700;
      }}

      /* Buttons */
      .btn {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 5px 13px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        border: none;
        transition: background 0.15s, box-shadow 0.15s, transform 0.1s;
        user-select: none;
        white-space: nowrap;
      }}
      .btn:active {{ transform: translateY(1px); }}
      .btn-results {{
        background: #0d6efd; color: #fff;
        box-shadow: 0 2px 5px rgba(13,110,253,0.3);
      }}
      .btn-results:hover {{ background: #0b5ed7; }}
      .btn-payload {{
        background: #495057; color: #fff;
        box-shadow: 0 2px 5px rgba(73,80,87,0.3);
      }}
      .btn-payload:hover {{ background: #343a40; }}
      .btn-group {{ display: flex; gap: 6px; flex-wrap: wrap; }}

      /* Resource card */
      .resource-card {{
        background: #fff;
        border: 1px solid #dde3ec;
        border-radius: 8px;
        margin-bottom: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: box-shadow 0.15s;
      }}
      .resource-card:hover {{ box-shadow: 0 3px 12px rgba(0,0,0,0.09); }}
      .resource-card.hidden-by-filter {{ display: none; }}

      .resource-header {{
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        padding: 10px 16px;
        background: #f7f9fc;
        border-bottom: 1px solid #dde3ec;
        cursor: default;
      }}
      .resource-uri {{
        flex: 1;
        font-weight: 700;
        font-size: 13px;
        color: #0d1b2a;
        word-break: break-all;
        font-family: "Cascadia Code","Consolas",monospace;
      }}
      .resource-type {{
        font-size: 11px;
        color: #6c757d;
        font-style: italic;
      }}
      .resource-badges {{ display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }}
      .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
      }}
      .badge-pass {{ background:#d4edda; color:#145a32; }}
      .badge-warn {{ background:#fff3cd; color:#7d6008; }}
      .badge-fail {{ background:#f8d7da; color:#7b241c; }}

      /* Collapsible panels */
      .results {{ display: none; }}
      .resultsShow {{ display: block; }}

      /* Properties table */
      .prop-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }}
      .prop-table th {{
        background: #f0f4f8;
        color: #2c3e50;
        font-weight: 700;
        padding: 7px 12px;
        text-align: left;
        border-bottom: 2px solid #dde3ec;
      }}
      .prop-table td {{
        padding: 5px 12px;
        border: none;
        border-bottom: 1px solid #f0f2f5;
        vertical-align: top;
        background: #fff;
        color: #333;
        word-break: break-word;
      }}
      .prop-table tr:last-child td {{ border-bottom: none; }}
      .prop-table tr:hover td {{ background: #f8fafc; }}
      .prop-table td.res-pass {{ background:#eafaf1; color:#145a32; font-weight:700; text-align:center; width:90px; }}
      .prop-table td.res-fail {{ background:#fdedec; color:#922b21; font-weight:700; text-align:center; width:90px; }}
      .prop-table td.res-warn {{ background:#fef9e7; color:#7d6008; font-weight:700; text-align:center; width:90px; }}
      .prop-table td.res-skip {{ background:#f5f7fa; color:#7f8c8d; font-style:italic; text-align:center; width:90px; }}
      .msg-fail {{ color:#c0392b; font-size:11px; margin-top:2px; }}
      .msg-warn {{ color:#b7770d; font-size:11px; margin-top:2px; }}

      /* Panel toolbars */
      .panel-toolbar {{
        display: flex; align-items: center; justify-content: flex-end;
        padding: 5px 10px;
        background: #eef2f7;
        border-bottom: 1px solid #dde3ec;
        gap: 6px;
      }}
      .payload-toolbar {{
        display: flex; align-items: center; justify-content: flex-end;
        padding: 5px 10px;
        background: #12151e;
        gap: 6px;
      }}

      /* Payload */
      .payload-panel {{
        background: #1e2130;
        color: #a8d8aa;
        font-family: "Cascadia Code","Consolas",monospace;
        font-size: 11px;
        padding: 14px 16px;
        overflow-x: auto;
        white-space: pre-wrap;
        word-wrap: break-word;
        max-height: 500px;
        overflow-y: auto;
      }}

      /* Copy buttons */
      .btn-copy {{
        display: inline-flex; align-items: center; gap: 4px;
        padding: 3px 10px;
        font-size: 11px; font-weight: 600;
        border-radius: 4px; cursor: pointer; border: 1px solid;
        transition: background 0.15s, color 0.15s;
        user-select: none;
      }}
      .btn-copy-light {{ background:#fff; color:#555; border-color:#c8d3e0; }}
      .btn-copy-light:hover {{ background:#e8f0fe; color:#0d6efd; border-color:#0d6efd; }}
      .btn-copy-dark {{ background:transparent; color:#a8d8aa; border-color:#3a4a5c; }}
      .btn-copy-dark:hover {{ background:#2a3a4c; color:#fff; }}
      .btn-copy.copied {{ color:#27ae60!important; border-color:#27ae60!important; }}

      /* No-match message */
      .filter-no-match {{
        text-align:center; padding:40px;
        color:#aaa; font-size:14px; display:none;
      }}

      /* Scroll-to-top */
      #scrollTopBtn {{
        position: fixed;
        bottom: 24px; right: 24px;
        width: 42px; height: 42px;
        border-radius: 50%;
        background: #0d6efd; color: #fff;
        border: none; cursor: pointer;
        font-size: 20px; line-height: 42px;
        text-align: center;
        box-shadow: 0 4px 14px rgba(13,110,253,0.45);
        display: none; z-index: 1100;
        transition: background 0.2s, transform 0.2s;
      }}
      #scrollTopBtn:hover {{ background:#0b5ed7; transform:translateY(-2px); }}

      a {{ color:#0d6efd; }}

      /* ════ RESPONSIVE ════ */
      @media (max-width: 860px) {{
        .nav-hamburger {{ display: flex; }}
        .top-nav-search-wrap {{ width: 240px; }}
        .top-nav-meta {{ display: none; }}
        .sidebar {{
          position: fixed;
          left: -300px;
          top: 56px;
          height: calc(100vh - 56px);
        }}
        .sidebar.open {{ left: 0; }}
        .main-content {{ width: 100%; }}
      }}
      @media (max-width: 540px) {{
        .top-nav {{ padding: 0 10px; gap: 8px; }}
        .top-nav img {{ height: 28px; }}
        .nav-brand {{ display: none; }}
        .top-nav-search-wrap {{ width: 180px; }}
        .score-grid {{ grid-template-columns: 1fr 1fr; }}
        .resource-header {{ flex-direction: column; align-items: flex-start; }}
        .btn-group {{ flex-wrap: wrap; }}
      }}
    </style>
  </head>
  <body>

    <!-- ════ TOP NAVBAR ════ -->
    <nav class="top-nav">
      <button class="nav-hamburger" id="hamburgerBtn" onclick="toggleSidebar()" title="Menu">&#9776;</button>
      <img alt="DMTF Redfish Logo" src="data:image/gif;base64,{}"/>
      <div class="nav-brand">
        <div class="top-nav-title">Redfish Service Validator</div>
        <div class="top-nav-sub">Test Report</div>
      </div>
      <div class="top-nav-search-wrap">
        <div class="nav-filter-wrap">
          <span class="fi">&#8260;</span>
          <input id="uriFilter" type="text" placeholder="Filter by URI&hellip;" autocomplete="off"/>
          <button id="filterClear" onclick="clearFilter()" title="Clear">&#10005;</button>
        </div>
        <div class="nav-filter-meta">Showing <b id="filterCount">&#8230;</b> resources</div>
      </div>
      <div class="top-nav-meta">
        Version: {} &nbsp;|&nbsp; Generated: {}<br/>
        <a href="https://github.com/DMTF/Redfish-Service-Validator" target="_blank">DMTF/Redfish-Service-Validator</a>
      </div>
    </nav>

    <!-- Mobile sidebar overlay -->
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
    <div class="app-shell">

      <!-- ════ LEFT SIDEBAR ════ -->
      <aside class="sidebar">

        <!-- System Info -->
        <div class="sidebar-section">
          <div class="sidebar-label">System Under Test</div>
          <table class="sys-table">
            <tr><td>Host</td><td>{}</td></tr>
            <tr><td>User</td><td>{}</td></tr>
            <tr><td>Password</td><td>{}</td></tr>
            <tr><td>Product</td><td>{}</td></tr>
            <tr><td>Manufacturer</td><td>{}</td></tr>
            <tr><td>Model</td><td>{}</td></tr>
            <tr><td>Firmware</td><td>{}</td></tr>
          </table>
        </div>

        <!-- Score tiles -->
        <div class="sidebar-section">
          <div class="sidebar-label">Results Summary</div>
          <div class="score-grid">
            <div class="score-tile st-pass"><div class="snum">{}</div><div class="slbl">&#10003; Pass</div></div>
            <div class="score-tile st-warn"><div class="snum">{}</div><div class="slbl">&#9888; Warning</div></div>
            <div class="score-tile st-fail"><div class="snum">{}</div><div class="slbl">&#10007; Fail</div></div>
            <div class="score-tile st-skip"><div class="snum">{}</div><div class="slbl">&#8212; Not Tested</div></div>
          </div>
        </div>

        <!-- Failure / Warning tallies -->
        <div class="sidebar-section">
          {}
        </div>



      </aside>

      <!-- ════ MAIN CONTENT ════ -->
      <main class="main-content">

        <div class="section-heading">
          Resources Validated
          <span class="sh-count" id="totalCount"></span>
        </div>

        <div id="resourceList">
          {}
        </div>

        <div class="filter-no-match" id="filterNoMatch">
          No resources match your filter.
        </div>

      </main>
    </div><!-- /app-shell -->

    <!-- Scroll to top -->
    <button id="scrollTopBtn" title="Back to top"
      onclick="document.querySelector('.main-content').scrollTo({{top:0,behavior:'smooth'}})">&#8679;</button>

    <script>
      /* ── Scroll-to-top for main content ── */
      document.querySelector('.main-content').addEventListener('scroll', function() {{
        document.getElementById('scrollTopBtn').style.display =
          this.scrollTop > 200 ? 'block' : 'none';
      }});

      /* ── URI Filter ── */
      var allCards = [];
      window.addEventListener('DOMContentLoaded', function() {{
        allCards = Array.from(document.querySelectorAll('.resource-card'));
        var tot = allCards.length;
        document.getElementById('filterCount').innerHTML = tot + ' / ' + tot;
        document.getElementById('totalCount').textContent = tot;
        document.getElementById('uriFilter').addEventListener('input', applyFilter);
      }});
      function applyFilter() {{
        var q = document.getElementById('uriFilter').value.trim().toLowerCase();
        document.getElementById('filterClear').style.display = q ? 'block' : 'none';
        var visible = 0, tot = allCards.length;
        allCards.forEach(function(c) {{
          var uri = (c.querySelector('.resource-uri') || {{}}).textContent || '';
          var match = !q || uri.toLowerCase().indexOf(q) !== -1;
          c.classList.toggle('hidden-by-filter', !match);
          if (match) visible++;
        }});
        document.getElementById('filterNoMatch').style.display =
          (visible === 0 && q) ? 'block' : 'none';
        document.getElementById('filterCount').innerHTML =
          '<b>' + visible + '</b> / ' + tot;
      }}
      function clearFilter() {{
        document.getElementById('uriFilter').value = '';
        applyFilter();
      }}

      /* ── Copy helper ── */
      function copyToClipboard(btn, targetId) {{
        var el = document.getElementById(targetId);
        var text = el ? el.innerText : '';
        var orig = btn.innerHTML;
        function done() {{
          btn.innerHTML = '&#10003; Copied!';
          btn.classList.add('copied');
          setTimeout(function() {{ btn.innerHTML = orig; btn.classList.remove('copied'); }}, 1800);
        }}
        if (navigator.clipboard) {{
          navigator.clipboard.writeText(text).then(done).catch(function() {{
            fallbackCopy(text); done();
          }});
        }} else {{ fallbackCopy(text); done(); }}
      }}
      function fallbackCopy(text) {{
        var ta = document.createElement('textarea');
        ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
        document.body.appendChild(ta); ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }}
      /* ── Mobile sidebar toggle ── */
      function toggleSidebar() {{
        var sb = document.querySelector('.sidebar');
        var ov = document.getElementById('sidebarOverlay');
        var open = sb.classList.toggle('open');
        ov.classList.toggle('show', open);
      }}
    </script>
  </body>
</html>
"""

error_tally_html = ""  # unused placeholder kept for compatibility


def build_resource_header(uri, resource_type, uri_summary, payload_id, results_id):
    """Builds the enterprise-styled resource card header row."""
    return """
  <div class="resource-card">
    <div class="resource-header">
      <div>
        <div class="resource-uri">{uri}</div>
        <div class="resource-type">{rtype}</div>
      </div>
      <div class="resource-badges">{badges}</div>
      <div class="btn-group">
        <span class="btn btn-results"
          onclick="(function(){{var r=document.getElementById('{rid}'),p=document.getElementById('{pid}');p.classList.remove('resultsShow');r.classList.toggle('resultsShow');}})()">
          &#9776; Results
        </span>
        <span class="btn btn-payload"
          onclick="(function(){{var r=document.getElementById('{rid}'),p=document.getElementById('{pid}');r.classList.remove('resultsShow');p.classList.toggle('resultsShow');}})()">
          &#123;&#125; Payload
        </span>
      </div>
    </div>
""".format(
        uri=html_mod.escape(uri),
        rtype=html_mod.escape(resource_type),
        badges=uri_summary,
        pid=payload_id,
        rid=results_id,
    )


def build_resource_detail(results_id, results_str, payload_id, payload_str):
    """Builds the collapsible results + payload panels with copy buttons."""
    return """
    <div class="results" id="{rid}">
      <div class="panel-toolbar">
        <span class="btn-copy btn-copy-light" onclick="copyToClipboard(this, '{rid}-inner')" title="Copy table as text">&#128203; Copy</span>
      </div>
      <div id="{rid}-inner">
      <table class="prop-table">
        <tr>
          <th style="width:30%">Property</th>
          <th>Value</th>
          <th style="width:90px">Result</th>
        </tr>
        {rows}
      </table>
      </div>
    </div>
    <div class="results" id="{pid}">
      <div class="payload-toolbar">
        <span class="btn-copy btn-copy-dark" onclick="copyToClipboard(this, '{pid}-inner')" title="Copy JSON payload">&#128203; Copy JSON</span>
      </div>
      <pre class="payload-panel" id="{pid}-inner">{payload}</pre>
    </div>
  </div>
""".format(rid=results_id, rows=results_str, pid=payload_id, payload=html_mod.escape(payload_str))


def build_not_tested_section(sut, uris):
    """Removed — Not Tested section no longer included in report."""
    return ""


def build_error_tally(error_classes, panel_title=None):
    """
    Creates a table of error/warning type counts.

    Args:
        error_classes: A dictionary containing the counts of types of errors
        panel_title: Optional heading for the tally panel

    Returns:
        The HTML string to insert in the results summary
    """
    if not error_classes:
        return ""
    rows = ""
    for etype in sorted(error_classes.keys()):
        rows += "<tr><td>{}</td><td>{}</td></tr>".format(html_mod.escape(etype + "s"), error_classes[etype])
    heading = "<h3>{}</h3>".format(html_mod.escape(panel_title)) if panel_title else ""
    return (
        '<div class="tally-panel">{}'
        '<table class="tally-table">'
        '<tr><th>Type</th><th style="text-align:right;width:80px">Count</th></tr>'
        "{}"
        "</table></div>"
    ).format(heading, rows)


def html_report(sut: SystemUnderTest, report_dir, time, tool_version):
    """
    Creates the HTML report for the system under test

    Args:
        sut: The system under test
        report_dir: The directory for the report
        time: The time the tests finished
        tool_version: The version of the tool

    Returns:
        The path to the HTML report
    """
    file = report_dir / datetime.strftime(time, "RedfishServiceValidatorReport_%m_%d_%Y_%H%M%S.html")
    html = ""

    # Build the error summary details — combined side-by-side panel
    error_tally = build_error_tally(sut._error_classes, "Failure Types")
    warning_tally = build_error_tally(sut._warning_classes, "Warning Types")
    if error_tally or warning_tally:
        combined_tally = '<div class="tally-two-col">{}{}</div>'.format(error_tally, warning_tally)
    else:
        combined_tally = ""

    # Build the URI results
    uris = sorted(list(sut._resources.keys()), key=str.lower)
    for index, uri in enumerate(uris):
        if not sut._resources[uri]["Validated"]:
            # Skip resources we didn't test
            # They might just be cached for reference link checks
            continue

        # Get the type info for the URI
        try:
            resource_type = sut._resources[uri]["Response"].dict["@odata.type"][1:].split(".")[0]
            try:
                resource_version = metadata.get_version(sut._resources[uri]["Response"].dict["@odata.type"])
                resource_version_str = "v{}.{}.{}".format(resource_version[0], resource_version[1], resource_version[2])
                resource_type += ", {}".format(resource_version_str)
            except:
                pass
        except:
            resource_type = "Unknown Resource Type"

        # Build the results summary for the URI
        uri_summary = '<span class="badge badge-pass">&#10003; Pass: {}</span>'.format(sut._resources[uri]["Pass"])
        if sut._resources[uri]["Warn"]:
            uri_summary += ' <span class="badge badge-warn">&#9888; Warn: {}</span>'.format(sut._resources[uri]["Warn"])
        if sut._resources[uri]["Fail"]:
            uri_summary += ' <span class="badge badge-fail">&#10007; Fail: {}</span>'.format(
                sut._resources[uri]["Fail"]
            )

        # Insert the URI results header
        results_id = "results{}".format(index)
        payload_id = "payload{}".format(index)
        html += build_resource_header(uri, resource_type, uri_summary, payload_id, results_id)

        # Insert the URI results details
        results_str = ""
        props = sorted(list(sut._resources[uri]["Results"]), key=str.lower)
        for prop in props:
            if prop == "":
                prop_str = "-"
            else:
                prop_str = prop[1:]
            result_class = ""
            raw_val = sut._resources[uri]["Results"][prop]["Value"]
            value_str = "<div>{}</div>".format(html_mod.escape(str(raw_val)) if raw_val is not None else "")
            if sut._resources[uri]["Results"][prop]["Result"] == "PASS":
                result_class = 'class="res-pass"'
            elif sut._resources[uri]["Results"][prop]["Result"] == "WARN":
                result_class = 'class="res-warn"'
                value_str += '<div class="msg-warn">{}</div>'.format(
                    html_mod.escape(sut._resources[uri]["Results"][prop]["Message"])
                )
            elif sut._resources[uri]["Results"][prop]["Result"] == "FAIL":
                result_class = 'class="res-fail"'
                value_str += '<div class="msg-fail">{}</div>'.format(
                    html_mod.escape(sut._resources[uri]["Results"][prop]["Message"])
                )
            elif sut._resources[uri]["Results"][prop]["Result"] == "SKIP":
                result_class = 'class="res-skip"'
            results_str += "<tr><td>{}</td><td>{}</td><td {}>{}</td></tr>".format(
                prop_str, value_str, result_class, sut._resources[uri]["Results"][prop]["Result"]
            )
        try:
            payload_str = json.dumps(
                sut._resources[uri]["Response"].dict, sort_keys=True, indent=4, separators=(",", ": ")
            )
        except:
            payload_str = "Malformed JSON"
        html += build_resource_detail(results_id, results_str, payload_id, payload_str)

    # Append the not-tested summary section (empty — removed per requirements)
    html += build_not_tested_section(sut, uris)

    with open(str(file), "w", encoding="utf-8") as fd:
        fd.write(
            html_template.format(
                redfish_logo.logo,
                tool_version,
                time.strftime("%c"),
                sut.rhost,
                sut.username,
                "********",
                sut.product,
                sut.manufacturer,
                sut.model,
                sut.firmware_version,
                sut.pass_count,
                sut.warn_count,
                sut.fail_count,
                sut.skip_count,
                combined_tally,
                html,
            )
        )
    return file
