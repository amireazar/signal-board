#!/usr/bin/env python3
"""Render the Analytica Horizon website from tools/pages/*.html into site/.

Each page fragment starts with a JSON header on its first line:
  <!--{"path": "commodities/", "title": "...", "description": "...", "nav": "commodities", "page": "commodities"}-->
The rest of the file is the page's <main> content. Shared header, live bar and
footer come from this script, and every link is made relative so the site works
both at https://<user>.github.io/<repo>/ and at the custom domain.

Run:  python tools/build_site.py
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "tools" / "pages"
SITE = ROOT / "site"
CFG = json.loads((ROOT / "tools" / "site.json").read_text())

NAV = [
    ("monitor", "Macro Monitor", "monitor/"),
    ("commodities", "Commodities", "commodities/"),
    ("solutions", "Solutions", "solutions/"),
    ("technology", "Technology", "technology/"),
    ("research", "Research", "research/"),
    ("about", "About", "about/"),
]

MARK = """<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
  <path d="M5 21a11 11 0 0 1 22 0" fill="none" stroke="currentColor" stroke-width="1.8"/>
  <path d="M16 6.2v3.1M8.2 9.4l2.1 2.2M23.8 9.4l-2.1 2.2M4.4 15.2l2.9.9M27.6 15.2l-2.9.9" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M2.5 21h27" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
  <path d="M7 25.5h18M11 29h10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".45"/>
</svg>"""


def header(root, current):
    links = []
    for key, label, href in NAV:
        cur = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{root}{href}"{cur}>{label}</a>')
    cur = ' aria-current="page"' if current == "contact" else ""
    links.append(f'<a class="btn primary small" href="{root}contact/"{cur}>Request a demo</a>')
    return f"""<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="container">
    <a class="brand" href="{root}" aria-label="{html.escape(CFG['company'])} home">
      {MARK}
      <span class="brand-name"><b>Analytica Horizon</b><span>Technology</span></span>
    </a>
    <button class="menu-btn" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="nav" id="site-nav" aria-label="Main">
      {' '.join(links)}
    </nav>
  </div>
</header>
<div class="livebar" aria-label="Live indicators">
  <div class="container" id="livebar"><span class="live-dot"><i></i>Live</span><span class="tick">Loading live data…</span></div>
</div>"""


def footer(root):
    reg = []
    if CFG.get("registration_number"):
        reg.append(f"Registration number {html.escape(CFG['registration_number'])}.")
    if CFG.get("registered_office"):
        reg.append(f"Registered office: {html.escape(CFG['registered_office'])}.")
    reg_line = " ".join(reg)
    return f"""<footer class="site-footer">
  <div class="container">
    <div class="foot-grid">
      <div>
        <a class="brand" href="{root}" aria-label="{html.escape(CFG['company'])} home">{MARK}<span class="brand-name"><b>Analytica Horizon</b><span>Technology</span></span></a>
        <p style="margin-top:14px;max-width:38ch">AI-driven analytics for macroeconomics and commodity futures. Built in Abu Dhabi.</p>
      </div>
      <div><h4>Live data</h4><ul>
        <li><a href="{root}monitor/">Macro Monitor</a></li>
        <li><a href="{root}commodities/">Commodities</a></li>
        <li><a href="{root}research/">Research</a></li>
      </ul></div>
      <div><h4>Company</h4><ul>
        <li><a href="{root}solutions/">Solutions</a></li>
        <li><a href="{root}technology/">Technology</a></li>
        <li><a href="{root}about/">About</a></li>
        <li><a href="{root}contact/">Contact</a></li>
      </ul></div>
      <div><h4>Legal</h4><ul>
        <li><a href="{root}legal/#disclaimer">Disclaimer</a></li>
        <li><a href="{root}legal/#terms">Terms of use</a></li>
        <li><a href="{root}legal/#privacy">Privacy notice</a></li>
        <li><a href="{root}legal/#data">Data sources</a></li>
      </ul></div>
    </div>
    <div class="foot-legal">
      <p>{html.escape(CFG['company'])} is a company registered in {html.escape(CFG['jurisdiction'])}. {reg_line}</p>
      <p>Content on this website is general information about markets and economic data. It is not investment, financial, legal or tax advice, not a recommendation to buy or sell any security, futures contract or other instrument, and not an offer of any regulated financial service. See the <a href="{root}legal/#disclaimer">disclaimer</a>.</p>
      <p>© <span data-year>2026</span> {html.escape(CFG['company'])}.</p>
    </div>
  </div>
</footer>"""


def render(frag: Path):
    text = frag.read_text()
    m = re.match(r"<!--(\{.*?\})-->\n", text, re.S)
    if not m:
        raise SystemExit(f"{frag.name}: missing JSON header")
    meta = json.loads(m.group(1))
    body = text[m.end():]
    path = meta["path"]
    depth = path.strip("/").count("/") + 1 if path.strip("/") else 0
    root = "../" * depth if depth else "./"
    body = body.replace("{{root}}", root)
    body = body.replace("{{formspree_id}}", html.escape(CFG.get("formspree_id", "")))
    body = body.replace("{{company}}", html.escape(CFG["company"]))
    body = body.replace("{{jurisdiction}}", html.escape(CFG["jurisdiction"]))
    title = meta["title"]
    full_title = f"{title} · {CFG['company']}" if meta.get("nav") != "home" else f"{CFG['company']} · {title}"
    canonical = CFG["url"].rstrip("/") + "/" + path
    libs = ""
    if meta.get("charts"):
        libs = '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" defer></script>\n'
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(meta['description'])}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(meta['description'])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta name="theme-color" content="#080D14" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#F4F6F9" media="(prefers-color-scheme: light)">
<link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body data-page="{meta['page']}" data-root="{root}">
{header(root, meta.get('nav'))}
<main id="main">
{body.strip()}
</main>
{footer(root)}
{libs}<script src="{root}assets/site.js" defer></script>
</body>
</html>
"""
    out = SITE / path / "index.html" if path else SITE / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    return out.relative_to(ROOT)


def main():
    (SITE / "assets" / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#080D14"/>'
        '<path d="M6 21a10 10 0 0 1 20 0" fill="none" stroke="#E9EEF4" stroke-width="2"/>'
        '<path d="M16 7.5v3M9 10.5l2 2M23 10.5l-2 2" stroke="#5CC8D7" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M4 21h24" stroke="#E9EEF4" stroke-width="2" stroke-linecap="round"/></svg>')
    for frag in sorted(PAGES.glob("*.html")):
        print("built", render(frag))


if __name__ == "__main__":
    main()
