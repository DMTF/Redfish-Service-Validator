# Copyright Notice:
# Copyright 2016-2026 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

from redfish_service_validator import redfish_logo

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{page_title}</title>
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

      /* Configuration toggle */
      .btn-config {{
        display: inline-flex; align-items: center; gap: 4px;
        padding: 4px 12px; border-radius: 5px; cursor: pointer;
        font-size: 11px; font-weight: 600; border: none;
        background: #0d6efd; color: #fff;
        box-shadow: 0 2px 5px rgba(13,110,253,0.3);
        transition: background 0.15s; user-select: none;
        margin-bottom: 6px;
      }}
      .btn-config:hover {{ background: #0b5ed7; }}
      .config-panel {{ display: none; }}
      .config-panel.open {{ display: block; }}
      .config-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        margin-top: 6px;
      }}
      .config-table tr:nth-child(even) td {{ background: #f5f7fa; }}
      .config-table tr:nth-child(odd) td {{ background: #ffffff; }}
      .config-table td {{
        padding: 5px 8px;
        border: 1px solid #dde3ec;
        vertical-align: top;
        word-break: break-all;
        color: #333;
      }}
      .config-table td:first-child {{
        font-weight: 700;
        color: #1a3a5c;
        white-space: nowrap;
        width: 45%;
        background: #eef4fb;
      }}
      .config-table td:last-child {{
        font-weight: 400;
        color: #444;
      }}

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

      a {{ color: #0d6efd; }}

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

      /* ── Shared badge colors ── */
      .badge-pass {{ background: #d4edda; color: #145a32; }}
      .badge-warn {{ background: #fff3cd; color: #7d6008; }}
      .badge-fail {{ background: #f8d7da; color: #7b241c; }}
      .badge-skip {{ background: #f5f7fa; color: #7f8c8d; }}

      /* ── Tool-specific styles ── */
      {extra_css}
    </style>
  </head>
  <body>

    <!-- ════ TOP NAVBAR ════ -->
    <nav class="top-nav">
      <button class="nav-hamburger" id="hamburgerBtn" onclick="toggleSidebar()" title="Menu">&#9776;</button>
      <img alt="DMTF Redfish Logo" src="data:image/gif;base64,{logo_b64}"/>
      <div class="nav-brand">
        <div class="top-nav-title">{tool_title}</div>
        <div class="top-nav-sub">{tool_subtitle}</div>
      </div>
      <div class="top-nav-search-wrap">
        <div class="nav-filter-wrap">
          <span class="fi">&#8260;</span>
          <input id="uriFilter" type="text" placeholder="{filter_placeholder}" autocomplete="off"/>
          <button id="filterClear" onclick="clearFilter()" title="Clear">&#10005;</button>
        </div>
        <div class="nav-filter-meta">Showing <b id="filterCount">&#8230;</b> {filter_count_label}</div>
      </div>
      <div class="top-nav-meta">
        Version: {tool_version} &nbsp;|&nbsp; Generated: {generated_time}<br/>
        <a href="{tool_link}" target="_blank">{tool_repo}</a>
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
            <tr><td>Host</td><td>{sut_host}</td></tr>
            <tr><td>User</td><td>{sut_user}</td></tr>
            <tr><td>Password</td><td>{sut_password}</td></tr>
            <tr><td>Product</td><td>{sut_product}</td></tr>
            <tr><td>Manufacturer</td><td>{sut_manufacturer}</td></tr>
            <tr><td>Model</td><td>{sut_model}</td></tr>
            <tr><td>Firmware</td><td>{sut_firmware}</td></tr>
          </table>
        </div>

        <!-- Score tiles -->
        <div class="sidebar-section">
          <div class="sidebar-label">Results Summary</div>
          <div class="score-grid">
            <div class="score-tile st-pass"><div class="snum">{pass_count}</div><div class="slbl">&#10003; Pass</div></div>
            <div class="score-tile st-warn"><div class="snum">{warn_count}</div><div class="slbl">&#9888; Warning</div></div>
            <div class="score-tile st-fail"><div class="snum">{fail_count}</div><div class="slbl">&#10007; Fail</div></div>
            <div class="score-tile st-skip"><div class="snum">{skip_count}</div><div class="slbl">&#8212; Not Tested</div></div>
          </div>
        </div>

        <!-- Tool-specific sidebar section (e.g. tally panel) -->
        {sidebar_extra_html}

        <!-- Configuration -->
        <div class="sidebar-section">
          <div class="sidebar-label">Configuration</div>
          <span class="btn-config" id="btnConfig"
            onclick="(function(){{var p=document.getElementById('configPanel'),b=document.getElementById('btnConfig');if(p.classList.contains('open')){{p.classList.remove('open');b.innerHTML='&#9881; Show Configuration';}}else{{p.classList.add('open');b.innerHTML='&#9650; Hide Configuration';}}}})()">
            &#9881; Show Configuration
          </span>
          <div class="config-panel" id="configPanel">
            <table class="config-table">
              {config_rows_html}
            </table>
          </div>
        </div>

      </aside>

      <!-- ════ MAIN CONTENT ════ -->
      <main class="main-content">

        {main_prefix_html}
        {main_content_html}
        {main_suffix_html}

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

      /* ── Mobile sidebar toggle ── */
      function toggleSidebar() {{
        var sb = document.querySelector('.sidebar');
        var ov = document.getElementById('sidebarOverlay');
        var open = sb.classList.toggle('open');
        ov.classList.toggle('show', open);
      }}

      /* ── Tool-specific JS ── */
      {extra_js}
    </script>
  </body>
</html>
"""


def build_html_report(
    *,
    page_title,
    tool_title,
    tool_subtitle="Test Report",
    filter_placeholder,
    filter_count_label,
    tool_link,
    tool_repo,
    tool_version,
    generated_time,
    sut_host,
    sut_user,
    sut_password,
    sut_product,
    sut_manufacturer,
    sut_model,
    sut_firmware,
    pass_count,
    warn_count,
    fail_count,
    skip_count,
    sidebar_extra_html="",
    config_rows_html="",
    extra_css="",
    main_prefix_html="",
    main_content_html="",
    main_suffix_html="",
    extra_js="",
):
    """
    Builds the full HTML report page string.

    Args:
        page_title: HTML <title> text
        tool_title: Tool name shown in the navbar brand
        tool_subtitle: Subtitle shown below the tool name (default: "Test Report")
        filter_placeholder: Placeholder text for the navbar filter input
        filter_count_label: Label after the filter count (e.g. "resources" or "test blocks")
        tool_link: URL for the tool's GitHub link in the navbar
        tool_repo: Display text for the GitHub link
        tool_version: Tool version string
        generated_time: Formatted timestamp string
        sut_host: System under test hostname/IP
        sut_user: Username used for authentication
        sut_password: Password (caller should mask as needed)
        sut_product: Product name reported by the SUT
        sut_manufacturer: Manufacturer reported by the SUT
        sut_model: Model reported by the SUT
        sut_firmware: Firmware version reported by the SUT
        pass_count: Number of passing checks
        warn_count: Number of warnings
        fail_count: Number of failures
        skip_count: Number of skipped/not-tested items
        sidebar_extra_html: Optional HTML block inserted between the score tiles and
                            configuration sections in the sidebar (e.g. failure tally)
        config_rows_html: HTML <tr> rows for the configuration table
        extra_css: Tool-specific CSS rules inserted at the end of the <style> block
        main_prefix_html: HTML inserted before the main content (e.g. section heading or toolbar)
        main_content_html: The primary rendered content (resource cards, test sections, etc.)
        main_suffix_html: HTML inserted after the main content (e.g. filter-no-match notice)
        extra_js: Tool-specific JavaScript inserted at the end of the <script> block

    Returns:
        The complete HTML document as a string
    """
    return _HTML_TEMPLATE.format(
        page_title=page_title,
        tool_title=tool_title,
        tool_subtitle=tool_subtitle,
        filter_placeholder=filter_placeholder,
        filter_count_label=filter_count_label,
        tool_link=tool_link,
        tool_repo=tool_repo,
        logo_b64=redfish_logo.logo,
        tool_version=tool_version,
        generated_time=generated_time,
        sut_host=sut_host,
        sut_user=sut_user,
        sut_password=sut_password,
        sut_product=sut_product,
        sut_manufacturer=sut_manufacturer,
        sut_model=sut_model,
        sut_firmware=sut_firmware,
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        skip_count=skip_count,
        sidebar_extra_html=sidebar_extra_html,
        config_rows_html=config_rows_html,
        extra_css=extra_css,
        main_prefix_html=main_prefix_html,
        main_content_html=main_content_html,
        main_suffix_html=main_suffix_html,
        extra_js=extra_js,
    )
