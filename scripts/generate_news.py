#!/usr/bin/env python3
"""
StaffPro Monthly HR News Generator
Runs on the 1st of each month via GitHub Actions.
Fetches top HR/compliance news and uses Claude to write a curated monthly bulletin.
Saves each issue to news/YYYY-MM.html and maintains an archive index.
"""

import os
import json
import re
import requests
from anthropic import Anthropic
from datetime import datetime
from pathlib import Path

NEWS_API_KEY      = os.environ["NEWS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

ROOT          = Path(__file__).parent.parent
ARCHIVE_DIR   = ROOT / "news"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"

QUERIES = [
    "employment law regulations",
    "HR compliance update",
    "payroll tax changes employers",
    "workers compensation law update",
    "OSHA workplace regulations",
    "employee benefits compliance",
    "labor law update",
    "ACA Affordable Care Act employers",
    "paid family leave update",
    "minimum wage law",
]

CATEGORY_STYLES = {
    "Employment Law":    ("var(--color-primary)", "rgba(37,64,200,.08)"),
    "Payroll & Tax":     ("#059669",              "rgba(5,150,105,.08)"),
    "Employee Benefits": ("#7C3AED",              "rgba(124,58,237,.08)"),
    "Workplace Safety":  ("#D97706",              "rgba(217,119,6,.08)"),
    "Workers' Comp":     ("#DC2626",              "rgba(220,38,38,.08)"),
    "HR Compliance":     ("#0891B2",              "rgba(8,145,178,.08)"),
}


# ── Archive helpers ─────────────────────────────────────────────────────────────

def load_archive():
    if ARCHIVE_INDEX.exists():
        return json.loads(ARCHIVE_INDEX.read_text(encoding="utf-8"))
    return []

def save_archive_index(entries):
    ARCHIVE_DIR.mkdir(exist_ok=True)
    ARCHIVE_INDEX.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ── Fetch ───────────────────────────────────────────────────────────────────────

def fetch_articles():
    seen, articles = set(), []
    for query in QUERIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": NEWS_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for a in resp.json().get("articles", []):
                title = a.get("title", "")
                if title and title != "[Removed]" and title not in seen:
                    seen.add(title)
                    articles.append(a)
        except Exception as e:
            print(f"  Warning — query '{query}' failed: {e}")
    print(f"  Fetched {len(articles)} unique articles.")
    return articles[:25]


# ── Curate with Claude ──────────────────────────────────────────────────────────

def curate_with_claude(articles):
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    month_year = datetime.now().strftime("%B %Y")

    article_list = "\n".join(
        f"{i+1}. {a['title']}\n   Source: {a['source']['name']}\n   {a.get('description') or ''}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are writing the monthly HR & Compliance bulletin for StaffPro Inc., a Professional Employer Organization serving small and mid-size businesses.

Here are recent HR and compliance news stories:

{article_list}

Write a polished monthly bulletin for {month_year}. Return ONLY valid JSON — no markdown, no code fences — in this exact structure:

{{
  "month": "{month_year}",
  "intro": "2–3 sentence paragraph summarizing the key themes this month. Warm, professional tone.",
  "stories": [
    {{
      "headline": "Clear, compelling headline written in your own words",
      "category": "One of: Employment Law | Payroll & Tax | Employee Benefits | Workplace Safety | Workers' Comp | HR Compliance",
      "summary": "2–3 sentences explaining what happened and why it matters to employers.",
      "takeaway": "One practical sentence: what should a business owner do or know because of this?",
      "detail": "3–5 paragraphs expanding on the story with specific details, affected parties, step-by-step guidance where relevant, and any important nuance. Use short paragraphs. Optionally use a section heading (prefix with ##) before each paragraph to organize the content. Plain English only."
    }}
  ],
  "closing": "1–2 sentences encouraging readers to reach out to StaffPro with questions."
}}

Select the 5 most relevant stories for small-to-mid-size employers. Plain English only — no legalese, no filler."""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    print(f"  Generated {len(data['stories'])} stories for {data['month']}.")
    return data


# ── HTML rendering ──────────────────────────────────────────────────────────────

def build_detail_html(raw_detail: str) -> str:
    """Convert the detail field (plain text with optional ## headings) into HTML paragraphs."""
    if not raw_detail:
        return ""
    lines, html_parts = raw_detail.strip().split("\n"), []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            html_parts.append(f"<h4>{line[3:].strip()}</h4>")
        else:
            html_parts.append(f"<p>{line}</p>")
    return "\n        ".join(html_parts)


def build_story_html(story):
    color, bg = CATEGORY_STYLES.get(story["category"], ("var(--color-primary)", "rgba(37,64,200,.08)"))
    detail_raw  = story.get("detail", "")
    detail_html = build_detail_html(detail_raw)
    expand_block = ""
    if detail_html:
        expand_block = f"""
        <button class="news-expand-toggle" aria-expanded="false">
          <span class="expand-label">Read more</span>
          <svg class="expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="news-detail" hidden>
        {detail_html}
        </div>"""
    return f"""
      <article class="news-card fade-in">
        <div class="news-cat" style="color:{color};background:{bg};">{story['category']}</div>
        <h3 class="news-headline">{story['headline']}</h3>
        <p class="news-summary">{story['summary']}</p>
        <div class="news-takeaway">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;color:var(--color-primary);"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          <span><strong>Takeaway:</strong> {story['takeaway']}</span>
        </div>{expand_block}
      </article>"""


def build_archive_section(archive, prefix=""):
    """Render the Previous Issues grid. prefix='' for main page, '../' unused here."""
    if not archive:
        return ""
    cards = "\n".join(
        f'        <a href="{prefix}news/{e["file"]}" class="archive-card">'
        f'<div class="archive-month">{e["month"]}</div>'
        f'<div class="archive-count">{e["count"]} stories</div></a>'
        for e in archive
    )
    return f"""
    <div class="archive-section fade-in">
      <div class="archive-title">Previous Issues</div>
      <div class="archive-grid">
{cards}
      </div>
    </div>"""


SHARED_STYLES = """
    .news-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: var(--sp-6);
      max-width: 780px;
      margin-inline: auto;
    }
    .news-card {
      background: var(--white);
      border: 1.5px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: var(--sp-6) var(--sp-7);
      overflow: hidden;
      transition: box-shadow var(--trans), border-color var(--trans);
    }
    .news-card:hover {
      border-color: var(--blue-200);
      box-shadow: 0 4px 24px rgba(37,64,200,.07);
    }
    .news-cat {
      display: inline-block;
      font-size: var(--text-xs);
      font-weight: 700;
      letter-spacing: .07em;
      text-transform: uppercase;
      padding: 3px 10px;
      border-radius: 999px;
      margin-bottom: var(--sp-3);
    }
    .news-headline {
      font-size: var(--text-xl);
      font-weight: 700;
      color: var(--color-text);
      margin-bottom: var(--sp-3);
      line-height: 1.35;
    }
    .news-summary {
      font-size: var(--text-base);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-4);
    }
    .news-takeaway {
      display: flex;
      align-items: flex-start;
      gap: var(--sp-2);
      background: var(--blue-50);
      border: 1px solid var(--blue-100);
      border-radius: var(--radius);
      padding: var(--sp-3) var(--sp-4);
      font-size: var(--text-sm);
      color: var(--color-text-secondary);
      line-height: 1.65;
    }
    .news-intro {
      max-width: 780px;
      margin-inline: auto;
      margin-bottom: var(--sp-10);
    }
    .news-intro p {
      font-size: var(--text-lg);
      color: var(--color-text-secondary);
      line-height: 1.8;
      margin-top: var(--sp-3);
    }
    .news-intro .eyebrow {
      font-size: var(--text-base);
    }
    .news-closing {
      max-width: 780px;
      margin-inline: auto;
      margin-top: var(--sp-12);
      padding: var(--sp-8) var(--sp-10);
      background: var(--blue-50);
      border: 1.5px solid var(--blue-100);
      border-radius: var(--radius-xl);
      text-align: center;
    }
    .news-disclaimer {
      font-size: var(--text-xs);
      color: var(--color-text-muted);
      line-height: 1.7;
      text-align: center;
      max-width: 780px;
      margin-inline: auto;
      margin-top: var(--sp-6);
      padding-top: var(--sp-5);
      border-top: 1px solid var(--color-border);
    }
    .news-closing p {
      font-size: var(--text-base);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-5);
    }
    .archive-section {
      max-width: 780px;
      margin-inline: auto;
      margin-top: var(--sp-16);
      padding-top: var(--sp-10);
      border-top: 1.5px solid var(--color-border);
    }
    .archive-title {
      font-size: var(--text-xs);
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--color-text-muted);
      margin-bottom: var(--sp-5);
    }
    .archive-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: var(--sp-4);
    }
    .archive-card {
      display: flex;
      flex-direction: column;
      gap: var(--sp-1);
      background: var(--white);
      border: 1.5px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: var(--sp-4) var(--sp-5);
      text-decoration: none;
      transition: border-color var(--trans), box-shadow var(--trans);
    }
    .archive-card:hover {
      border-color: var(--blue-200);
      box-shadow: 0 4px 16px rgba(37,64,200,.07);
    }
    .archive-month {
      font-size: var(--text-sm);
      font-weight: 700;
      color: var(--color-text);
    }
    .archive-count {
      font-size: var(--text-xs);
      color: var(--color-text-muted);
    }
    @media (max-width: 640px) {
      .archive-grid { grid-template-columns: repeat(2, 1fr); }
    }
    .news-expand-toggle {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: var(--sp-2);
      width: 100%;
      margin-top: var(--sp-4);
      padding: var(--sp-4) 0 var(--sp-1);
      border: none;
      border-top: 1px solid var(--color-border);
      background: none;
      cursor: pointer;
      font-size: var(--text-sm);
      font-weight: 600;
      color: var(--color-primary);
      text-align: center;
      user-select: none;
    }
    .news-expand-toggle:hover { opacity: .75; }
    .expand-icon {
      flex-shrink: 0;
      transition: transform .2s ease;
    }
    .news-card.expanded .expand-icon { transform: rotate(180deg); }
    .news-detail {
      margin-top: var(--sp-5);
      padding-top: var(--sp-5);
      border-top: 1px dashed var(--color-border);
    }
    .news-detail h4 {
      font-size: var(--text-base);
      font-weight: 700;
      color: var(--color-text);
      margin-top: var(--sp-5);
      margin-bottom: var(--sp-2);
    }
    .news-detail h4:first-child { margin-top: 0; }
    .news-detail p {
      font-size: var(--text-sm);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-3);
    }
    .news-detail ul, .news-detail ol {
      font-size: var(--text-sm);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-3);
      padding-left: var(--sp-5);
    }
    .news-detail li { margin-bottom: var(--sp-1); }
    .news-detail strong { color: var(--color-text); font-weight: 600; }
    .news-detail a { color: var(--color-primary); }"""


def render_nav(p, active_news=True):
    """Render nav. p = path prefix ('' for root, '../' for news/ subdir)."""
    active = 'class="nav-link active"' if active_news else 'class="nav-link"'
    return f"""<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="{p}index.html" class="nav-logo">
      <img src="{p}assets/images/logo.png" alt="StaffPro Inc." class="nav-logo-img"
           onerror="this.onerror=null;this.style.display='none';this.nextElementSibling.style.display='flex';" />
      <span class="nav-logo-fallback" aria-hidden="true"><span class="lf-staff">staff</span><span class="lf-pro">pro</span></span>
    </a>
    <div class="nav-links">
      <a href="{p}services.html"  class="nav-link">Services</a>
      <a href="{p}about.html"     class="nav-link">About Us</a>
      <a href="{p}resources.html" class="nav-link">Resources</a>
      <a href="{p}news.html"      {active}>News</a>
      <a href="{p}contact.html"   class="nav-link">Contact</a>
    </div>
    <div class="nav-actions">
      <a href="https://staffpro.payplus360.com/login/" class="btn btn-outline btn-sm" target="_blank" rel="noopener noreferrer">Employee Login</a>
      <a href="https://staffpro.payplus360.com/login/" class="btn btn-primary btn-sm" target="_blank" rel="noopener noreferrer">Client Login</a>
    </div>
    <button class="nav-toggle" id="navToggle" aria-label="Open menu">
      <span></span><span></span><span></span>
    </button>
  </div>
</nav>
<div class="nav-mobile" id="navMobile">
  <a href="{p}services.html"  class="nav-mobile-link">Services</a>
  <a href="{p}about.html"     class="nav-mobile-link">About Us</a>
  <a href="{p}resources.html" class="nav-mobile-link">Resources</a>
  <a href="{p}news.html"      class="nav-mobile-link">News</a>
  <a href="{p}contact.html"   class="nav-mobile-link">Contact</a>
  <div class="nav-mobile-divider"></div>
  <a href="https://staffpro.payplus360.com/login/" class="nav-mobile-link" target="_blank" rel="noopener noreferrer">Employee Login ↗</a>
  <a href="https://staffpro.payplus360.com/login/" class="btn btn-primary nav-mobile-cta" target="_blank" rel="noopener noreferrer">Client Login</a>
</div>"""


def render_footer(p):
    return f"""<footer class="footer">
  <div class="container">
    <div class="footer-grid">
      <div>
        <div class="footer-logo">
          <img src="{p}assets/images/logo.png" alt="StaffPro Inc." class="footer-logo-img"
               onerror="this.onerror=null;this.style.display='none';this.nextElementSibling.style.display='flex';" />
          <span class="footer-logo-fallback" aria-hidden="true"><span class="lf-staff">staff</span><span class="lf-pro">pro</span></span>
        </div>
        <p class="footer-tagline">Build Your Business, Not Your HR Department</p>
        <div class="footer-contact-item"><svg class="footer-contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.57 3.46 2 2 0 0 1 3.54 1.29h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.8a16 16 0 0 0 5.55 5.55l1.88-1.88a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21.93 14.72"/></svg><a href="tel:7184711122">718-471-1122</a></div>
        <div class="footer-contact-item"><svg class="footer-contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg><a href="mailto:info@staffproonline.com">info@staffproonline.com</a></div>
        <div class="footer-contact-item"><svg class="footer-contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg><span>167 Lawrence Avenue, Inwood, NY 11096</span></div>
      </div>
      <div>
        <div class="footer-col-title">Services</div>
        <div class="footer-links">
          <a href="{p}services.html#payroll"     class="footer-link">Payroll Processing</a>
          <a href="{p}services.html#hr"          class="footer-link">HR Administration</a>
          <a href="{p}services.html#benefits"    class="footer-link">Employee Benefits</a>
          <a href="{p}services.html#workerscomp" class="footer-link">Workers' Compensation</a>
          <a href="{p}services.html#screening"   class="footer-link">Background Screening</a>
          <a href="{p}services.html#compliance"  class="footer-link">Tax &amp; Compliance</a>
        </div>
      </div>
      <div>
        <div class="footer-col-title">Resources</div>
        <div class="footer-links">
          <a href="{p}resources.html#w2"         class="footer-link">W-2 Retrieval</a>
          <a href="{p}resources.html#1095"        class="footer-link">1095 Retrieval</a>
          <a href="{p}resources.html#onboarding"  class="footer-link">Client Onboarding Tutorials</a>
          <a href="{p}resources.html#posters"     class="footer-link">Labor Law Poster Orders</a>
        </div>
        <div style="margin-top:var(--sp-5);">
          <div class="footer-col-title">Company</div>
          <div class="footer-links">
            <a href="{p}about.html"   class="footer-link">About StaffPro</a>
            <a href="{p}news.html"    class="footer-link">HR News</a>
            <a href="{p}contact.html" class="footer-link">Contact Us</a>
          </div>
        </div>
      </div>
      <div>
        <div class="footer-col-title">Client Access</div>
        <div style="margin-top:var(--sp-6);display:flex;flex-direction:column;gap:var(--sp-2);">
          <a href="https://staffpro.payplus360.com/login/" class="btn btn-primary btn-sm" target="_blank" rel="noopener noreferrer" style="justify-content:center;">Client Login</a>
          <a href="https://staffpro.payplus360.com/login/" class="btn btn-outline btn-sm" target="_blank" rel="noopener noreferrer" style="justify-content:center;border-color:rgba(255,255,255,0.2);color:rgba(255,255,255,0.7);">Employee Login</a>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <span>&copy; 2026 StaffPro Inc. All rights reserved.</span>
      <span>167 Lawrence Avenue &middot; Inwood, NY 11096</span>
    </div>
  </div>
</footer>"""


def render_page(data, p="", archive=None):
    """
    Render full news page HTML.
    p = path prefix: '' for root news.html, '../' for news/YYYY-MM.html
    archive = list of past issues (shown only on root page)
    """
    month_year   = data["month"]
    stories_html = "\n".join(build_story_html(s) for s in data["stories"])
    archive_html = build_archive_section(archive) if archive and not p else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>HR &amp; Compliance News — {month_year} | StaffPro Inc.</title>
  <meta name="description" content="Monthly HR and compliance news bulletin from StaffPro Inc. — {month_year}" />
  <link rel="icon" type="image/png" href="{p}assets/images/favicon.png" />
  <link rel="stylesheet" href="{p}css/style.css" />
  <style>{SHARED_STYLES}
  </style>
</head>
<body>

{render_nav(p)}


<section class="page-hero">
  <div class="container page-hero-inner">
    <span class="eyebrow eyebrow-light">Monthly Bulletin</span>
    <h1 class="page-hero-title">HR &amp; Compliance News</h1>
    <p class="page-hero-text">
      A monthly roundup of what's changing in HR, employment law, payroll, and compliance — curated for business owners.
    </p>
  </div>
</section>


<section class="section">
  <div class="container">

    <div class="news-intro fade-in">
      <span class="eyebrow">{month_year}</span>
      <p>{data['intro']}</p>
    </div>

    <div class="news-grid">
{stories_html}
    </div>

    <div class="news-closing fade-in">
      <p>{data['closing']}</p>
      <a href="{p}contact.html" class="btn btn-primary">Get in Touch</a>
    </div>

    <p class="news-disclaimer">This bulletin is provided for general informational purposes only and does not constitute legal advice. Employment laws vary by jurisdiction and are subject to change — consult qualified legal counsel before taking action based on any content in this publication.</p>

{archive_html}

  </div>
</section>


{render_footer(p)}

<script src="{p}js/main.js"></script>
</body>
</html>"""


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    print("=== StaffPro Monthly News Generator ===")

    # Load existing archive
    archive = load_archive()
    print(f"  Archive has {len(archive)} existing issues.")

    # Fetch and curate
    print("Fetching articles...")
    articles = fetch_articles()

    print("Curating with Claude...")
    data = curate_with_claude(articles)

    now      = datetime.now()
    filename = f"{now.strftime('%Y-%m')}.html"

    # Save archive copy (news/YYYY-MM.html) — with '../' prefix for assets
    print("Saving archive copy...")
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_html = render_page(data, p="../")
    (ARCHIVE_DIR / filename).write_text(archive_html, encoding="utf-8")

    # Update archive index (add current month if not already there)
    if not any(e["file"] == filename for e in archive):
        archive.insert(0, {
            "month": data["month"],
            "file":  filename,
            "count": len(data["stories"])
        })
        save_archive_index(archive)
        print(f"  Added {filename} to archive index.")

    # Render main news.html with archive section (remaining items = past issues)
    print("Rendering main news.html...")
    past_issues = [e for e in archive if e["file"] != filename]
    main_html   = render_page(data, p="", archive=past_issues)
    (ROOT / "news.html").write_text(main_html, encoding="utf-8")

    print("Done.")


if __name__ == "__main__":
    main()
