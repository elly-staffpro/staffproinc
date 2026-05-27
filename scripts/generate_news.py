#!/usr/bin/env python3
"""
StaffPro Monthly HR News Generator
Runs on the 1st of each month via GitHub Actions.
Fetches top HR/compliance news and uses Claude to write a curated monthly bulletin.
"""

import os
import json
import re
import requests
from anthropic import Anthropic
from datetime import datetime
from pathlib import Path

NEWS_API_KEY  = os.environ["NEWS_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

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


# ── Fetch ──────────────────────────────────────────────────────────────────────

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


# ── Curate with Claude ─────────────────────────────────────────────────────────

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
      "takeaway": "One practical sentence: what should a business owner do or know because of this?"
    }}
  ],
  "closing": "1–2 sentences encouraging readers to reach out to StaffPro with questions."
}}

Select the 5 most relevant stories for small-to-mid-size employers. Plain English only — no legalese, no filler."""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    print(f"  Generated {len(data['stories'])} stories for {data['month']}.")
    return data


# ── HTML rendering ─────────────────────────────────────────────────────────────

def build_story_html(story):
    color, bg = CATEGORY_STYLES.get(story["category"], ("var(--color-primary)", "rgba(37,64,200,.08)"))
    return f"""
      <article class="news-card fade-in">
        <div class="news-cat" style="color:{color};background:{bg};">{story['category']}</div>
        <h3 class="news-headline">{story['headline']}</h3>
        <p class="news-summary">{story['summary']}</p>
        <div class="news-takeaway">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;color:var(--color-primary);"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          <span><strong>Takeaway:</strong> {story['takeaway']}</span>
        </div>
      </article>"""


def render_html(data):
    month_year = data["month"]
    stories_html = "\n".join(build_story_html(s) for s in data["stories"])
    updated = datetime.now().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>HR &amp; Compliance News — {month_year} | StaffPro Inc.</title>
  <meta name="description" content="Monthly HR and compliance news bulletin from StaffPro Inc. — {month_year}" />
  <link rel="icon" type="image/png" href="assets/images/favicon.png" />
  <link rel="stylesheet" href="css/style.css" />
  <style>
    .news-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: var(--sp-6);
      max-width: 780px;
      margin-inline: auto;
    }}
    .news-card {{
      background: var(--white);
      border: 1.5px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: var(--sp-6) var(--sp-7);
      transition: box-shadow var(--trans), border-color var(--trans);
    }}
    .news-card:hover {{
      border-color: var(--blue-200);
      box-shadow: 0 4px 24px rgba(37,64,200,.07);
    }}
    .news-cat {{
      display: inline-block;
      font-size: var(--text-xs);
      font-weight: 700;
      letter-spacing: .07em;
      text-transform: uppercase;
      padding: 3px 10px;
      border-radius: 999px;
      margin-bottom: var(--sp-3);
    }}
    .news-headline {{
      font-size: var(--text-xl);
      font-weight: 700;
      color: var(--color-text);
      margin-bottom: var(--sp-3);
      line-height: 1.35;
    }}
    .news-summary {{
      font-size: var(--text-base);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-4);
    }}
    .news-takeaway {{
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
    }}
    .news-intro {{
      max-width: 780px;
      margin-inline: auto;
      margin-bottom: var(--sp-10);
    }}
    .news-intro p {{
      font-size: var(--text-lg);
      color: var(--color-text-secondary);
      line-height: 1.8;
      margin-top: var(--sp-3);
    }}
    .news-closing {{
      max-width: 780px;
      margin-inline: auto;
      margin-top: var(--sp-12);
      padding: var(--sp-8) var(--sp-10);
      background: var(--blue-50);
      border: 1.5px solid var(--blue-100);
      border-radius: var(--radius-xl);
      text-align: center;
    }}
    .news-closing p {{
      font-size: var(--text-base);
      color: var(--color-text-secondary);
      line-height: 1.75;
      margin-bottom: var(--sp-5);
    }}
    .news-meta {{
      font-size: var(--text-xs);
      color: var(--color-text-muted);
      text-align: center;
      margin-top: var(--sp-8);
      max-width: 780px;
      margin-inline: auto;
    }}
  </style>
</head>
<body>

<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="index.html" class="nav-logo">
      <img src="assets/images/logo.png" alt="StaffPro Inc." class="nav-logo-img"
           onerror="this.onerror=null;this.style.display='none';this.nextElementSibling.style.display='flex';" />
      <span class="nav-logo-fallback" aria-hidden="true"><span class="lf-staff">staff</span><span class="lf-pro">pro</span></span>
    </a>
    <div class="nav-links">
      <a href="services.html"  class="nav-link">Services</a>
      <a href="about.html"     class="nav-link">About Us</a>
      <a href="resources.html" class="nav-link">Resources</a>
      <a href="news.html"      class="nav-link active">News</a>
      <a href="contact.html"   class="nav-link">Contact</a>
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
  <a href="services.html"  class="nav-mobile-link">Services</a>
  <a href="about.html"     class="nav-mobile-link">About Us</a>
  <a href="resources.html" class="nav-mobile-link">Resources</a>
  <a href="news.html"      class="nav-mobile-link">News</a>
  <a href="contact.html"   class="nav-mobile-link">Contact</a>
  <div class="nav-mobile-divider"></div>
  <a href="https://staffpro.payplus360.com/login/" class="nav-mobile-link" target="_blank" rel="noopener noreferrer">Employee Login ↗</a>
  <a href="https://staffpro.payplus360.com/login/" class="btn btn-primary nav-mobile-cta" target="_blank" rel="noopener noreferrer">Client Login</a>
</div>


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
      <a href="contact.html" class="btn btn-primary">Get in Touch</a>
    </div>

    <p class="news-meta">Auto-generated bulletin &middot; Last updated {updated}</p>

  </div>
</section>


<footer class="footer">
  <div class="container">
    <div class="footer-grid">
      <div>
        <div class="footer-logo">
          <img src="assets/images/logo.png" alt="StaffPro Inc." class="footer-logo-img"
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
          <a href="services.html#payroll"     class="footer-link">Payroll Processing</a>
          <a href="services.html#hr"          class="footer-link">HR Administration</a>
          <a href="services.html#benefits"    class="footer-link">Employee Benefits</a>
          <a href="services.html#workerscomp" class="footer-link">Workers' Compensation</a>
          <a href="services.html#screening"   class="footer-link">Background Screening</a>
          <a href="services.html#compliance"  class="footer-link">Tax &amp; Compliance</a>
        </div>
      </div>
      <div>
        <div class="footer-col-title">Resources</div>
        <div class="footer-links">
          <a href="resources.html#w2"         class="footer-link">W-2 Retrieval</a>
          <a href="resources.html#1095"        class="footer-link">1095 Retrieval</a>
          <a href="resources.html#onboarding"  class="footer-link">Client Onboarding Tutorials</a>
          <a href="resources.html#posters"     class="footer-link">Labor Law Poster Orders</a>
        </div>
        <div style="margin-top:var(--sp-5);">
          <div class="footer-col-title">Company</div>
          <div class="footer-links">
            <a href="about.html"   class="footer-link">About StaffPro</a>
            <a href="news.html"    class="footer-link">HR News</a>
            <a href="contact.html" class="footer-link">Contact Us</a>
          </div>
        </div>
      </div>
      <div>
        <div class="footer-col-title">Client Access</div>
        <div class="footer-links">
          <a href="https://staffpro.payplus360.com/login/" class="footer-link" target="_blank" rel="noopener noreferrer">PayPlus — Client Login</a>
          <a href="https://staffpro.payplus360.com/login/" class="footer-link" target="_blank" rel="noopener noreferrer">PayPlus — Employee Login</a>
        </div>
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
</footer>

<script src="js/main.js"></script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== StaffPro Monthly News Generator ===")
    print("Fetching articles...")
    articles = fetch_articles()

    print("Curating with Claude...")
    data = curate_with_claude(articles)

    print("Rendering HTML...")
    html = render_html(data)

    out = Path(__file__).parent.parent / "news.html"
    out.write_text(html, encoding="utf-8")
    print(f"Done. Written to {out}")


if __name__ == "__main__":
    main()
