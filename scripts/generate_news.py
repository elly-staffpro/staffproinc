#!/usr/bin/env python3
"""
StaffPro Monthly HR News Generator
Runs on the 1st of each month via GitHub Actions.
Fetches top HR/compliance news and uses Claude to write a curated monthly bulletin.
Saves each issue to news/YYYY-MM.html and maintains an archive index.
"""

import os
import sys
import json
import re
import time
import html as html_mod
import requests
from anthropic import Anthropic
from datetime import datetime, timedelta
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

# Outlets the bulletin is allowed to draw from: employment-law trade press, the
# major employment-law firms' update blogs, benefits/payroll trade press, and
# mainstream business wires. Deliberately excludes SEO content farms and payroll
# vendors' marketing blogs, which NewsAPI indexes alongside everything else.
#
# Note: federal and state agency sites (dol.gov, irs.gov, osha.gov) are NOT here
# because NewsAPI does not index them. Agency announcements reach us only via the
# outlets below reporting on them.
APPROVED_DOMAINS = [
    # HR / employment trade press
    "shrm.org", "hrdive.com", "hrexecutive.com", "workforce.com", "hrmorning.com",
    # Employment law
    "natlawreview.com", "jdsupra.com", "law360.com", "bloomberglaw.com",
    "littler.com", "jacksonlewis.com", "ogletree.com", "fisherphillips.com",
    "seyfarth.com", "employmentlawworldview.com",
    # Benefits / payroll / retirement
    "benefitspro.com", "benefitnews.com", "plansponsor.com", "planadviser.com",
    "accountingtoday.com", "taxnotes.com",
    # Insurance / workers' comp
    "businessinsurance.com", "insurancejournal.com", "workcompcentral.com",
    # Mainstream wires
    "reuters.com", "apnews.com", "cnbc.com", "bloomberg.com", "wsj.com",
]

# If the whitelist yields fewer than this, do a second unrestricted pass so a
# quiet news month still produces a bulletin. Anything from that pass is tagged
# and called out in the review PR.
MIN_APPROVED_ARTICLES = 8

# ── Three-tier sourcing ─────────────────────────────────────────────────────────
#
# The bulletin used to be written from NewsAPI headlines alone — 60-80 words of
# real material per story. That is why the old "detail" section had to be
# invented. These tiers exist to give the writer actual source text.
#
#   Tier 1  Federal Register        full rule text, structured effective dates,
#                                   PUBLIC DOMAIN (17 U.S.C. 105)
#   Tier 2  DOL / OSHA newsroom     complete press releases, PUBLIC DOMAIN
#   Tier 3  Trade press (NewsAPI)   headline + blurb, COPYRIGHTED — facts only,
#                                   short summary, always linked
#
# Tiers 1 and 2 carry no copyright restriction, which is exactly why they are
# primary. Tier 3 fills gaps federal rulemaking does not cover (state law, court
# decisions) and is kept deliberately short.

FR_API = "https://www.federalregister.gov/api/v1/documents.json"
FR_DAYS_BACK = 75          # a monthly bulletin needs a little overlap
FR_PER_PAGE = 20
FR_MAX_FULLTEXT = 8        # full-text fetches per run, to bound time and bandwidth
FR_BODY_WORDS = 600        # words of rule text handed to the writer

# NOTE: do NOT add conditions[term] to this query. It looks like a helpful topic
# filter but it collapses the result set — agency-scoped returns 54 documents
# over 75 days, and adding a term filter dropped that to 1. Relevance filtering
# is the writer's job, with the review PR as the backstop.
FR_AGENCIES = [
    "labor-department",
    "equal-employment-opportunity-commission",
    "employee-benefits-security-administration",
    "internal-revenue-service",
]
FR_TYPES = ["RULE", "PRORULE"]

# Public-domain agency newsrooms. Verified to return full release text in the RSS
# description (46-941 words), not a teaser.
#
# OSHA's own feed (osha.gov/news/newsreleases.xml) is deliberately NOT here: it
# returns 403 to a non-browser user agent, and spoofing a browser to get around
# that is not something to do quietly. It is also unnecessary — the DOL feed below
# already carries OSHA releases along with WHD, ETA and OSEC.
AGENCY_FEEDS = [
    ("U.S. Department of Labor", "https://www.dol.gov/rss/releases.xml"),
]

UA = "StaffProNewsBot/1.0 (+https://www.staffproinc.com)"

# Per-tier caps on the candidate list. Without these the combined list is
# truncated in tier order and trade press never survives — tier 1 and tier 2
# alone returned 30 candidates against an overall cap of 25.
TIER_CAPS = {1: 12, 2: 6, 3: 7}

# Longest run of consecutive words the published copy may share with its source.
# Facts are not copyrightable; a long verbatim run is a different matter, and on
# public-domain sources it is still just lazy writing in the wrong voice.
MAX_VERBATIM_WORDS = 18

VOICE_SPEC_PATH = Path(__file__).parent / "website-newsletter-voice.md"

CATEGORY_STYLES = {
    "Employment Law":    ("var(--color-primary)", "rgba(37,64,200,.08)"),
    "Payroll & Tax":     ("#007F52",              "rgba(0,127,82,.08)"),
    "Employee Benefits": ("#7C3AED",              "rgba(124,58,237,.08)"),
    "Workplace Safety":  ("#B45200",              "rgba(180,82,0,.08)"),
    "Workers' Comp":     ("#D62020",              "rgba(214,32,32,.08)"),
    "HR Compliance":     ("#007899",              "rgba(0,120,153,.08)"),
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

def _candidate(title, source_name, url, published, body, tier, public_domain,
               approved_source=True, effective_on=None, doc_type=None):
    """One normalised candidate, whatever tier it came from."""
    return {
        "title": (title or "").strip(),
        "source": {"name": source_name},
        "url": url,
        "published": published,
        "body": " ".join((body or "").split()),
        "_tier": tier,
        "_public_domain": public_domain,
        "_approved_source": approved_source,
        "_effective_on": effective_on,
        "_doc_type": doc_type,
    }


def _redact(e):
    """
    Error text safe to log. requests embeds the full URL in its exceptions, which
    for NewsAPI includes apiKey=<secret>, so strip any query string and any
    occurrence of the key itself before it reaches a build log.
    """
    msg = re.sub(r"\?\S*", "?<redacted>", str(e))
    if NEWS_API_KEY:
        msg = msg.replace(NEWS_API_KEY, "<redacted>")
    return msg[:200]


def _strip_tags(s):
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return " ".join(s.split())


def _extract_fr_body(raw, words=FR_BODY_WORDS):
    """
    Pull the useful part out of a Federal Register document.

    The raw text opens with citation boilerplate and ends in tables and appendices.
    The substance a reader cares about is the SUMMARY / SUPPLEMENTARY INFORMATION
    block, so start there when it exists and fall back to the top of the document.
    """
    text = _strip_tags(raw)
    m = re.search(r"\bSUMMARY:\s*", text)
    if not m:
        m = re.search(r"\bSUPPLEMENTARY INFORMATION:\s*", text)
    start = m.end() if m else 0
    return " ".join(text[start:].split()[:words])


def fetch_federal_register():
    """Tier 1 — actual rulemaking. Public domain, with real effective dates."""
    since = (datetime.now() - timedelta(days=FR_DAYS_BACK)).date().isoformat()
    params = [
        ("per_page", str(FR_PER_PAGE)),
        ("order", "newest"),
        ("conditions[publication_date][gte]", since),
    ]
    params += [("conditions[type][]", t) for t in FR_TYPES]
    params += [("conditions[agencies][]", a) for a in FR_AGENCIES]
    params += [("fields[]", f) for f in
               ("title", "abstract", "html_url", "publication_date",
                "effective_on", "type", "agency_names", "raw_text_url")]

    out = []
    try:
        resp = requests.get(FR_API, params=params, timeout=20,
                            headers={"User-Agent": UA})
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
    except Exception as e:
        print(f"  Warning — Federal Register query failed: {e}")
        return out

    fulltext_budget = FR_MAX_FULLTEXT
    for r in results:
        body = (r.get("abstract") or "").strip()
        if fulltext_budget > 0 and r.get("raw_text_url"):
            try:
                ft = requests.get(r["raw_text_url"], timeout=25,
                                  headers={"User-Agent": UA})
                ft.raise_for_status()
                deeper = _extract_fr_body(ft.text)
                if len(deeper.split()) > len(body.split()):
                    body = deeper
                fulltext_budget -= 1
            except Exception as e:
                print(f"  Note — full text unavailable for "
                      f"{(r.get('title') or '')[:45]}: {e}")
        agency = (r.get("agency_names") or ["Federal Register"])[0]
        out.append(_candidate(
            title=r.get("title"),
            source_name=f"Federal Register ({agency})",
            url=r.get("html_url"),
            published=r.get("publication_date"),
            body=body,
            tier=1,
            public_domain=True,
            effective_on=r.get("effective_on"),
            doc_type=r.get("type"),
        ))
    print(f"  Tier 1 — Federal Register: {len(out)} documents "
          f"({FR_MAX_FULLTEXT - fulltext_budget} with full text).")
    return out


def fetch_agency_feeds():
    """Tier 2 — DOL and OSHA newsroom releases. Public domain, full release text."""
    out = []
    for agency, url in AGENCY_FEEDS:
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": UA})
            resp.raise_for_status()
            items = re.findall(r"<item>(.*?)</item>", resp.text, re.S)
        except Exception as e:
            print(f"  Warning — {agency} feed failed: {e}")
            continue
        got = 0
        for it in items:
            grab = lambda pat: (re.search(pat, it, re.S).group(1)
                                if re.search(pat, it, re.S) else "")
            title = _strip_tags(grab(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>"))
            link = _strip_tags(grab(r"<link>(.*?)</link>"))
            body = _strip_tags(grab(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>"))
            pub = _strip_tags(grab(r"<pubDate>(.*?)</pubDate>"))
            if not (title and link):
                continue
            out.append(_candidate(title, agency, link, pub, body,
                                  tier=2, public_domain=True))
            got += 1
        print(f"  Tier 2 — {agency}: {got} release(s).")
    return out


def _query_newsapi(query, seen, articles, domains=None, approved=True):
    params = {
        "q": query,
        "language": "en",
        # relevancy, not publishedAt: we want the most relevant compliance news of
        # the month, not simply whatever was posted most recently.
        "sortBy": "relevancy",
        "pageSize": 5,
        "apiKey": NEWS_API_KEY,
    }
    if domains:
        params["domains"] = ",".join(domains)
    try:
        resp = requests.get("https://newsapi.org/v2/everything", params=params, timeout=10)
        resp.raise_for_status()
        for a in resp.json().get("articles", []):
            title = (a.get("title") or "").strip()
            if title and title != "[Removed]" and title not in seen:
                seen.add(title)
                # Tier 3 is a headline and a blurb, and it is copyrighted. Keep
                # whatever real text NewsAPI gives us, trimmed of its truncation marker.
                blurb = " ".join(filter(None, [a.get("description"),
                                               re.sub(r"\[\+\d+ chars\]$", "",
                                                      a.get("content") or "")]))
                articles.append(_candidate(
                    title=title,
                    source_name=(a.get("source") or {}).get("name") or "Source",
                    url=a.get("url"),
                    published=a.get("publishedAt"),
                    body=blurb,
                    tier=3,
                    public_domain=False,
                    approved_source=approved,
                ))
    except Exception as e:
        # Deliberately does NOT print the exception's message: requests puts the
        # full request URL in it, apiKey included. GitHub masks registered secrets
        # in logs, but there is no reason to write the key there at all.
        print(f"  Warning — trade-press query '{query}' failed "
              f"({type(e).__name__}: {_redact(e)})")


def fetch_articles():
    """
    Build the candidate list across all three tiers, best source first.

    Public-domain material leads because it is both authoritative and free of
    copyright constraints. Trade press comes last and stays short.
    """
    candidates = fetch_federal_register() + fetch_agency_feeds()

    seen = {c["title"] for c in candidates}
    trade = []
    for query in QUERIES:
        _query_newsapi(query, seen, trade, domains=APPROVED_DOMAINS, approved=True)
    print(f"  Tier 3 — approved trade press: {len(trade)} article(s).")

    if len(trade) < MIN_APPROVED_ARTICLES:
        print(f"  Below {MIN_APPROVED_ARTICLES} — widening beyond the approved outlet list.")
        for query in QUERIES:
            _query_newsapi(query, seen, trade, domains=None, approved=False)
        extra = sum(1 for a in trade if not a["_approved_source"])
        print(f"  Added {extra} article(s) from outside the approved list.")

    candidates += trade
    if not candidates:
        raise RuntimeError("no candidate articles from any tier")

    # Cap each tier separately so a heavy rulemaking month cannot crowd trade
    # press out of the list entirely. Unused room is handed to the better tiers.
    selected, spare = [], 0
    for tier in (1, 2, 3):
        group = [c for c in candidates if c["_tier"] == tier]
        cap = TIER_CAPS[tier] + spare
        selected += group[:cap]
        spare = max(0, cap - len(group))

    pd = sum(1 for c in selected if c["_public_domain"])
    words = sum(len(c["body"].split()) for c in selected)
    counts = {t: sum(1 for c in selected if c["_tier"] == t) for t in (1, 2, 3)}
    print(f"  {len(selected)} candidates selected "
          f"(tier1={counts[1]}, tier2={counts[2]}, tier3={counts[3]}) — "
          f"{pd} public domain, {words} words of source text.")
    return selected


# ── Curate with Claude ──────────────────────────────────────────────────────────

def extract_json(text: str):
    """Pull a JSON object out of the model response, tolerant of code fences or
    stray prose around it. Raises ValueError if no parseable object is found."""
    text = text.strip()
    # Strip leading/trailing markdown code fences if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: grab everything from the first '{' to the last '}'.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON object found in model response")


MIN_STORIES = 3  # below this the bulletin is too thin to be worth publishing


def load_voice_spec():
    """
    The approved voice spec is the writing brief. If it goes missing the run fails
    rather than quietly falling back to generic AI prose — the whole point is that
    the copy sounds like StaffPro.
    """
    if not VOICE_SPEC_PATH.exists():
        raise RuntimeError(f"voice spec not found at {VOICE_SPEC_PATH}")
    spec = VOICE_SPEC_PATH.read_text(encoding="utf-8")
    if len(spec.split()) < 200:
        raise RuntimeError("voice spec looks truncated")
    return spec


def _words(s):
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def longest_verbatim_run(published, source):
    """
    Longest run of consecutive words the published copy shares with its source.

    Facts cannot be copyrighted, so restating them is fine. Copying sentences is
    not — and even on public-domain government text it means the copy is in the
    government's voice rather than StaffPro's. Classic DP over word lists.
    """
    a, b = _words(published), _words(source)
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def enforce_originality(data, articles):
    """
    Drop any story that copies too long a run from its source. Runs after
    attach_sources, so each story already knows which article it came from.
    """
    kept, dropped = [], []
    for s in data.get("stories", []):
        src = next((a for a in articles if a.get("url") == s.get("_source_url")), None)
        if not src or not src.get("body"):
            kept.append(s)
            continue
        published = " ".join([s.get("headline", "")] + summary_paragraphs(s.get("summary")) + [
                              s.get("takeaway", "")])
        run = longest_verbatim_run(published, src["body"])
        s["_verbatim_run"] = run
        if run > MAX_VERBATIM_WORDS:
            dropped.append((s.get("headline", "(untitled)"), run))
        else:
            kept.append(s)

    for headline, run in dropped:
        print(f"  Dropped ({run}-word verbatim run from source): {headline}")
    if len(kept) < MIN_STORIES:
        raise ValueError(
            f"only {len(kept)} stories passed the originality check "
            f"(need {MIN_STORIES}) — copy is too close to the sources")
    data["stories"] = kept
    worst = max((s.get("_verbatim_run", 0) for s in kept), default=0)
    print(f"  Originality: longest shared run across kept stories is {worst} words "
          f"(limit {MAX_VERBATIM_WORDS}).")
    return data


def summary_paragraphs(summary):
    """
    Normalise a story summary to a list of paragraphs.

    The model is asked for a two-element array, but a single string or a string
    with blank lines in it both have to render sensibly rather than blow up.
    """
    if isinstance(summary, (list, tuple)):
        parts = [str(s).strip() for s in summary]
    else:
        parts = re.split(r"\n\s*\n", str(summary or ""))
        parts = [p.strip() for p in parts]
    return [p for p in parts if p]


def attach_sources(data, articles):
    """
    Resolve each story's source_index against the real article list and attach the
    actual outlet name and URL. The model never supplies a URL itself, so it cannot
    invent one. A story whose source cannot be resolved is DROPPED — an uncited
    story is exactly what we are trying to stop publishing.
    """
    kept, dropped = [], []
    for s in data.get("stories", []):
        try:
            i = int(s.get("source_index")) - 1
        except (TypeError, ValueError):
            i = -1
        a = articles[i] if 0 <= i < len(articles) else None
        if a and a.get("url"):
            s["_source_name"]     = (a.get("source") or {}).get("name") or "Source"
            s["_source_url"]      = a["url"]
            s["_source_approved"] = bool(a.get("_approved_source", True))
            kept.append(s)
        else:
            dropped.append(s.get("headline", "(untitled)"))

    for d in dropped:
        print(f"  Dropped (no resolvable source): {d}")
    if len(kept) < MIN_STORIES:
        raise ValueError(
            f"only {len(kept)} of {len(data.get('stories', []))} stories had a "
            f"resolvable source (need {MIN_STORIES})")

    data["stories"] = kept
    unapproved = [s["_source_name"] for s in kept if not s["_source_approved"]]
    if unapproved:
        print(f"  NOTE: {len(unapproved)} story/stories cite outlets outside the "
              f"approved list: {', '.join(sorted(set(unapproved)))}")
    return data


def write_source_digest(articles):
    """
    Write the candidate articles to the path in NEWS_SOURCES_OUT, if set, so the
    review PR can list what the month's stories were actually drawn from.
    No-op when the variable is unset (local runs), and never fatal: failing to
    write a review aid must not lose an otherwise good bulletin.
    """
    dest = os.environ.get("NEWS_SOURCES_OUT")
    if not dest:
        return
    try:
        outside = [a for a in articles if not a.get("_approved_source", True)]
        by_tier = {1: [], 2: [], 3: []}
        for a in articles:
            by_tier.setdefault(a.get("_tier", 3), []).append(a)

        lines = [""]
        if outside:
            lines += [f"> **{len(outside)} of {len(articles)} candidates came from outside the "
                      f"approved outlet list** (the approved list was short this month). "
                      f"Anything cited from those needs a closer look.", ""]
        lines += [
            "**Where this month's candidates came from** — "
            f"{len(by_tier.get(1, []))} Federal Register, {len(by_tier.get(2, []))} agency "
            f"newsroom, {len(by_tier.get(3, []))} trade press. Tiers 1 and 2 are US "
            "government material and carry no copyright restriction; tier 3 is "
            "copyrighted, so those stories are kept short and always linked.", ""]

        TIER_NAME = {1: "Tier 1 — Federal Register (public domain)",
                     2: "Tier 2 — Agency newsroom (public domain)",
                     3: "Tier 3 — Trade press (copyrighted)"}
        lines += [f"<details><summary>Candidate sources ({len(articles)})</summary>", ""]
        for tier in (1, 2, 3):
            group = by_tier.get(tier) or []
            if not group:
                continue
            lines += [f"**{TIER_NAME[tier]}**", ""]
            for a in group:
                title = (a.get("title") or "(untitled)").replace("|", "\\|")
                name = (a.get("source") or {}).get("name") or "unknown source"
                flag = "" if a.get("_approved_source", True) else " ⚠️ *outside approved list*"
                eff = f" · effective {a['_effective_on']}" if a.get("_effective_on") else ""
                wc = len((a.get("body") or "").split())
                url = a.get("url")
                head = f"[{title}]({url})" if url else title
                lines.append(f"- {head} — {name}{eff} · {wc} words of source text{flag}")
            lines.append("")
        lines += ["</details>", ""]
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"  Wrote source digest for review -> {dest}")
    except Exception as e:  # noqa: BLE001 — a review aid must never fail the run
        print(f"  Could not write source digest: {e}")


def curate_with_claude(articles):
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    month_year = datetime.now().strftime("%B %Y")

    TIER_LABEL = {
        1: "TIER 1 — Federal Register (US government, PUBLIC DOMAIN)",
        2: "TIER 2 — Federal agency newsroom (US government, PUBLIC DOMAIN)",
        3: "TIER 3 — Trade press (COPYRIGHTED: facts only, keep it short)",
    }
    blocks = []
    for i, a in enumerate(articles, 1):
        head = [f"{i}. {a['title']}",
                f"   {TIER_LABEL[a['_tier']]}",
                f"   Outlet: {a['source']['name']}",
                f"   Published: {a.get('published') or 'unknown'}"]
        if a.get("_doc_type"):
            head.append(f"   Document type: {a['_doc_type']}")
        if a.get("_effective_on"):
            head.append(f"   Effective date (from the government): {a['_effective_on']}")
        head.append(f"   SOURCE TEXT ({len(a['body'].split())} words): {a['body'] or '(none)'}")
        blocks.append("\n".join(head))
    article_list = "\n\n".join(blocks)

    # Hand the same candidate list to the reviewer. Without this the review PR
    # asks someone to fact-check stories against sources they cannot see.
    write_source_digest(articles)

    voice_spec = load_voice_spec()

    prompt = f"""You are writing the monthly HR & Compliance bulletin published on the public website of StaffPro Inc., a New York State–licensed Professional Employer Organization serving small and mid-size businesses.

Write it in StaffPro's voice. This is the approved voice specification — follow it exactly, including the register rules in section 1 and the "Never" list in section 3:

<voice_spec>
{voice_spec}
</voice_spec>

Below are this month's candidate sources. Each one includes the real source text. Base every story on that text and nothing else.

<candidates>
{article_list}
</candidates>

Return ONLY valid JSON — no markdown, no code fences — in this exact structure:

{{
  "month": "{month_year}",
  "intro": "2-3 sentences on the themes this month, in StaffPro's voice.",
  "stories": [
    {{
      "headline": "Plain and specific. What happened, in StaffPro's words.",
      "category": "One of: Employment Law | Payroll & Tax | Employee Benefits | Workplace Safety | Workers' Comp | HR Compliance",
      "summary": ["First paragraph: what changed and who it touches. Mention the source naturally in the prose.",
                  "Second paragraph: why it matters to an employer, and the honest scope - who is actually affected and who is not."],
      "takeaway": "One sentence that ORIENTS the reader. Do not instruct a public reader to do something by a date.",
      "source_index": 3
    }}
  ],
  "closing": "1-2 sentences inviting readers to get in touch."
}}

Pick UP TO 5 items. There is no quota — see RELEVANCE.

RELEVANCE. Most candidates will not be relevant. Federal rulemaking sweeps in
corporate and international tax, agency housekeeping, and rules for narrow
sectors. Choose only items that affect how ordinary employers pay people, provide
benefits, keep workers safe, or stay compliant. Prefer TIER 1 and TIER 2: they are
authoritative and public domain.

Apply this test to every story before you include it: write the honest takeaway
first. If that takeaway would say the item is "not a general employer issue", that
"employers don't administer this", or that it is relevant only to a narrow group
that most readers are not in — then DO NOT INCLUDE THE STORY AT ALL. Cut it and
move on. Do not soften it into something that sounds relevant.

Returning 3 strong stories is a better bulletin than 5 with two that do not apply.
Do not pad to reach a number.

ROUTINE RELEASES ARE NOT STORIES. Recurring statistical publications — the weekly
unemployment claims report, monthly jobs numbers, quarterly indices — are not
developments. Nothing changed for an employer because a number moved. Skip them
unless the release itself reports a genuine change in policy or method. If the
only takeaway you can write is that something is "a general indicator", it is not
a story.

THE INTRO COMES LAST. Choose your stories first, then write the intro describing
ONLY what those stories cover. Do not mention a topic you decided to cut — an
intro that promises subjects the bulletin does not contain reads as careless.

SOURCING. "source_index" is REQUIRED and must be the number of the ONE candidate
the story is based on. Each story is published with a link to that source, so the
number must be the one you actually used. Never merge several candidates into one
story.

LENGTH. "summary" is an array of exactly TWO paragraphs, 2-3 sentences each.
The first says what changed; the second says why it matters and who it really
affects. Two short paragraphs, not one long one split in half — each should
stand on its own. Only write a second paragraph you can support from the
source; if there is genuinely nothing more to say, the story is too thin to
run and should be cut.

ACCURACY. Write only what the source text supports. Do not add dates, dollar
amounts, thresholds, effective dates, agency names, or case outcomes that the
source does not state. An effective date may be used ONLY when it is given above.
If a detail is not in the source, leave it out. Describe scope honestly — if a
rule mostly binds state agencies or federal contractors rather than employers
generally, say so.

ORIGINALITY AND COPYRIGHT. Write original sentences. Never copy a run of more
than {MAX_VERBATIM_WORDS} consecutive words from any source; stories that do are
discarded automatically. TIER 1 and TIER 2 text is public domain, so the facts are
free to use — but government prose is not StaffPro's voice, so rewrite it. TIER 3
is copyrighted: take the facts, write your own sentences, keep it brief, and lean
on Tier 1 and 2 for anything substantial."""

    last_err = None
    for attempt in range(1, 4):  # up to 3 tries
        try:
            message = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            if not message.content or not message.content[0].text:
                raise ValueError("Empty response from Claude")
            data = extract_json(message.content[0].text)
            if not data.get("stories"):
                raise ValueError("Response contained no stories")
            # Inside the retry loop on purpose: a response whose stories cannot be
            # traced back to a real article gets another attempt rather than shipping.
            data = attach_sources(data, articles)
            data = enforce_originality(data, articles)
            print(f"  Generated {len(data['stories'])} sourced stories for {data['month']}.")
            return data
        except Exception as e:  # noqa: BLE001 — retry on any transient/parse failure
            last_err = e
            print(f"  Attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt)  # 2s, then 4s

    raise RuntimeError(f"Claude curation failed after 3 attempts: {last_err}")


# ── HTML rendering ──────────────────────────────────────────────────────────────

def build_story_html(story):
    # No "Read more" / .news-detail block any more. That section used to be 2-3
    # paragraphs the model wrote to "expand on" a story it only knew from a
    # headline and a one-line description, and nothing on the card linked to the
    # original article — so a reader had no way to check it. A card now says only
    # what the source supports: category, headline, summary, takeaway.
    #
    # The .news-detail CSS in SHARED_STYLES and the expand handler in main.js are
    # deliberately KEPT: already-published archive pages still contain those blocks
    # and would break without them.
    color, bg = CATEGORY_STYLES.get(story["category"], ("var(--color-primary)", "rgba(37,64,200,.08)"))
    paras = summary_paragraphs(story.get("summary"))
    if len(paras) < 2:
        print(f"  Note - only {len(paras)} paragraph(s) for: {story.get('headline','?')[:55]}")
    sep = chr(10) + "        "
    summary_html = sep.join(
        f'<p class="news-summary">{para}</p>' for para in paras)
    return f"""
      <article class="news-card fade-in">
        <div class="news-cat" style="color:{color};background:{bg};">{story['category']}</div>
        <h3 class="news-headline">{story['headline']}</h3>
        {summary_html}
        <div class="news-takeaway">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;color:var(--color-primary);"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          <span><strong>Takeaway:</strong> {story['takeaway']}</span>
        </div>
        <p class="news-source">Source: <a href="{story['_source_url']}" target="_blank" rel="noopener noreferrer nofollow">{story['_source_name']}</a></p>
      </article>"""


def build_archive_section(archive, prefix=""):
    """
    Render the Previous Issues grid.
    prefix='' on news.html, '../' on an archive page (news/YYYY-MM.html).

    An archive page lists the issues published before it, plus a link back to the
    current issue — so a reader who lands on an old bulletin can reach any other
    one. Pages are not rewritten in later months: that would put every archive
    file into every monthly review PR and bury the actual new content.
    """
    if not archive:
        return ""
    cards = "\n".join(
        f'        <a href="{prefix}news/{e["file"]}" class="archive-card">'
        f'<div class="archive-month">{e["month"]}</div>'
        f'<div class="archive-count">{e["count"]} stories</div></a>'
        for e in archive
    )
    current = (
        f'\n      <a href="{prefix}news.html" class="archive-current">'
        f'View the current issue &rarr;</a>' if prefix else ""
    )
    return f"""
    <div class="archive-section fade-in">
      <div class="archive-title">Previous Issues</div>
      <div class="archive-grid">
{cards}
      </div>{current}
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
      margin-bottom: var(--sp-3);
    }
    /* Stories run two paragraphs, kept close together. The larger gap before the
       takeaway lives on the takeaway itself — :last-of-type cannot do this job,
       because the last <p> in a card is the source line, not the last paragraph. */
    .news-takeaway {
      margin-top: var(--sp-5);
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
    .news-source {
      margin-top: var(--sp-4);
      padding-top: var(--sp-3);
      border-top: 1px solid var(--color-border);
      font-size: var(--text-xs);
      color: var(--color-text-muted);
    }
    .news-source a {
      color: var(--color-primary);
      font-weight: 600;
      text-decoration: none;
    }
    .news-source a:hover { text-decoration: underline; }
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
    .archive-current {
      display: inline-block;
      margin-top: var(--sp-5);
      font-size: var(--text-sm);
      font-weight: 600;
      color: var(--color-primary);
      text-decoration: none;
    }
    .archive-current:hover { text-decoration: underline; }
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
      <a href="tel:7184711122" class="nav-icon-btn" aria-label="Call StaffPro at 718-471-1122" title="Call 718-471-1122">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.57 3.46 2 2 0 0 1 3.54 1.29h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.8a16 16 0 0 0 5.55 5.55l1.88-1.88a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21.93 14.72"/></svg>
      </a>
      <a href="https://staffpro.payplus360.com/login/" class="nav-login-link" target="_blank" rel="noopener noreferrer">Login</a>
      <a href="{p}contact.html" class="btn btn-primary btn-sm">Get a Quote</a>
    </div>
    <button class="nav-toggle" id="navToggle" aria-label="Open menu" aria-expanded="false" aria-controls="navMobile">
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
  <a href="tel:7184711122" class="nav-mobile-link">Call 718-471-1122</a>
  <a href="https://staffpro.payplus360.com/login/" class="nav-mobile-link" target="_blank" rel="noopener noreferrer">Client / Employee Login ↗</a>
  <a href="{p}contact.html" class="btn btn-primary nav-mobile-cta">Get a Quote</a>
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
          <a href="{p}employee-resources.html#w2"         class="footer-link">W-2 Retrieval</a>
          <a href="{p}employee-resources.html#1095"        class="footer-link">1095 Retrieval</a>
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
      <span>&copy; {datetime.now().year} StaffPro Inc. All rights reserved.</span>
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
    # Archive pages get the grid too, not just news.html — otherwise a reader who
    # lands on an old issue has no way to reach any other one.
    archive_html = build_archive_section(archive, prefix=p) if archive else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>HR &amp; Compliance News — {month_year} | StaffPro Inc.</title>
  <meta name="description" content="Monthly HR and compliance news bulletin from StaffPro Inc. — {month_year}" />
  <meta property="og:title"       content="HR &amp; Compliance News — {month_year} | StaffPro Inc." />
  <meta property="og:description" content="Monthly HR and compliance news bulletin from StaffPro Inc. — {month_year}" />
  <meta property="og:type"        content="article" />
  <meta property="og:image"       content="https://www.staffproinc.com/assets/images/logo.png" />
  <link rel="icon" type="image/png" href="{p}assets/images/favicon.png" />
  <link rel="stylesheet" href="{p}css/style.css" />
  <script>
    /* Reveal-on-scroll is opt-in. Hide content only when scripting works, and
       reveal it again if main.js never initializes (blocked, 404, offline). */
    (function () {{
      var d = document.documentElement;
      d.className += (d.className ? ' ' : '') + 'js-anim';
      setTimeout(function () {{
        if (!window.__spAnimReady) {{
          d.className = d.className.replace(/\\bjs-anim\\b/, '').trim();
        }}
      }}, 2500);
    }})();
  </script>
  <!-- Cloudflare Web Analytics -->
  <script defer src="https://static.cloudflareinsights.com/beacon.min.js"
          data-cf-beacon='{{"token": "c0b373a9584b47a58428c3ec5453366a"}}'></script>
  <!-- End Cloudflare Web Analytics -->
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


# ── Sitemap ─────────────────────────────────────────────────────────────────────

SITEMAP_STATIC = [
    ("",               "monthly", "1.0"),
    ("services.html",  "monthly", "0.9"),
    ("about.html",     "yearly",  "0.7"),
    ("resources.html", "monthly", "0.7"),
    ("employee-resources.html", "monthly", "0.7"),
    ("news.html",      "monthly", "0.8"),
    ("contact.html",   "yearly",  "0.6"),
]
BASE_URL = "https://www.staffproinc.com/"

def build_sitemap(archive):
    """Rebuild sitemap.xml from the static pages plus every archived news issue,
    so it never goes stale as new monthly issues are added."""
    rows = []
    for path, freq, prio in SITEMAP_STATIC:
        rows.append(f"  <url>\n    <loc>{BASE_URL}{path}</loc>\n"
                    f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>")
    for e in archive:
        rows.append(f"  <url>\n    <loc>{BASE_URL}news/{e['file']}</loc>\n"
                    f"    <changefreq>never</changefreq>\n    <priority>0.4</priority>\n  </url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(rows) + "\n</urlset>\n")
    (ROOT / "sitemap.xml").write_text(xml, encoding="utf-8")
    print(f"  Rebuilt sitemap.xml ({len(SITEMAP_STATIC)} pages + {len(archive)} news issues).")


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    print("=== StaffPro Monthly News Generator ===")

    # Load existing archive
    archive = load_archive()
    print(f"  Archive has {len(archive)} existing issues.")

    # Idempotency guard: if this month's issue was already generated, a SCHEDULED
    # run is the safety-net second attempt — do nothing. A manual run
    # (workflow_dispatch) or local run still regenerates on purpose.
    this_month_file = f"{datetime.now().strftime('%Y-%m')}.html"
    already_done = (ARCHIVE_DIR / this_month_file).exists()
    if already_done and os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        print(f"  {this_month_file} already exists — this month is done. Skipping.")
        return

    # Fetch and curate
    print("Fetching articles...")
    articles = fetch_articles()
    if not articles:
        raise RuntimeError("NewsAPI returned zero usable articles — aborting so we don't publish an empty bulletin.")

    print("Curating with Claude...")
    data = curate_with_claude(articles)

    now      = datetime.now()
    filename = f"{now.strftime('%Y-%m')}.html"

    # Save archive copy (news/YYYY-MM.html) — with '../' prefix for assets
    print("Saving archive copy...")
    ARCHIVE_DIR.mkdir(exist_ok=True)
    # The archive copy lists every OTHER issue (this month's own page is current,
    # so it does not link to itself).
    other_issues = [e for e in archive if e["file"] != filename]
    archive_html = render_page(data, p="../", archive=other_issues)
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

    # Keep sitemap.xml in sync with the full archive
    print("Rebuilding sitemap...")
    build_sitemap(archive)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        # ::error:: makes GitHub Actions surface this prominently and the
        # non-zero exit marks the whole run as failed (so it isn't silent).
        print(f"::error::Monthly news generation failed: {e}")
        sys.exit(1)
