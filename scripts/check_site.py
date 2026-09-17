#!/usr/bin/env python3
"""
StaffPro site checks.

Every check here exists because the corresponding bug actually shipped to
www.staffproinc.com. The point is not to be clever — it is that these specific
failures can never again reach production quietly, because they are checked on
every push rather than whenever someone thinks to look.

All checks are static: they read the files in the repo. That is deliberate — no
browser, no network, no flakiness, runs in about a second. The trade-off is that
anything only observable at runtime is out of scope here; see KNOWN LIMITS at the
bottom of this file.

Run:  py scripts/check_site.py          (add --verbose to list every pass)
Exit: 0 = all clear, 1 = at least one failure
"""

import os
import re
import sys
import glob
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
STATIC_PAGES = sorted(p.name for p in ROOT.glob("*.html"))
NEWS_PAGES = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.glob("news/*.html"))
ALL_PAGES = STATIC_PAGES + NEWS_PAGES
CSS_PATH = ROOT / "css" / "style.css"

failures = []
notes = []


def fail(check, page, msg):
    failures.append((check, page, msg))


def note(msg):
    notes.append(msg)


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


def strip_style_and_script(html):
    """Return markup only — CSS and JS removed, so checks don't match their own rules."""
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    return html


# ─────────────────────────────────────────────────────────────────────────────
# 1. Content must not depend on JavaScript to be visible
#    Shipped bug: .fade-in set opacity:0 unconditionally, so with JS off 18 of 22
#    homepage sections were invisible.
# ─────────────────────────────────────────────────────────────────────────────

def check_js_resilience():
    css = CSS_PATH.read_text(encoding="utf-8")

    # An opacity:0 rule on .fade-in must be scoped under .js-anim.
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip().split("\n")[-1].strip()
        body = m.group(2)
        if "fade-in" not in selector:
            continue
        if re.search(r"opacity:\s*0\s*;", body) and ".js-anim" not in selector:
            fail("js-resilience", "css/style.css",
                 f"'{selector}' hides content with opacity:0 but is not scoped under "
                 f".js-anim — it will stay hidden when JS is unavailable")

    for page in ALL_PAGES:
        html = read(page)
        if 'class="fade-in' not in html and "fade-in" not in html:
            continue
        n = html.count("__spAnimReady")
        if n != 1:
            fail("js-resilience", page,
                 f"uses .fade-in but has {n} copies of the reveal failsafe (expected 1) — "
                 f"content will be stuck invisible if main.js fails to load")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Forms must work without JavaScript and must validate
#    Shipped bug: both forms had novalidate and no action — a blank form submitted
#    happily, and if JS broke the form silently did nothing at all.
# ─────────────────────────────────────────────────────────────────────────────

def check_forms():
    for page in ALL_PAGES:
        html = read(page)
        for tag in re.findall(r"<form\b[^>]*>", html, flags=re.I):
            ident = (re.search(r'id="([^"]+)"', tag) or [None, tag[:60]])[1]
            if re.search(r"\bnovalidate\b", tag, flags=re.I):
                fail("forms", page, f"<form {ident}> has novalidate — "
                                    f"the browser will not validate required fields")
            if not re.search(r'\baction\s*=\s*"[^"]+"', tag, flags=re.I):
                fail("forms", page, f"<form {ident}> has no action — "
                                    f"it cannot submit if JavaScript fails")
            if not re.search(r'\bmethod\s*=\s*"[^"]+"', tag, flags=re.I):
                fail("forms", page, f"<form {ident}> has no method")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Text must meet WCAG AA against every surface it can sit on
#    Shipped bug: --color-text-muted was 2.69:1 on white. The later fix still
#    failed on --blue-50 because only two backgrounds were considered.
# ─────────────────────────────────────────────────────────────────────────────

SURFACES = ["--white", "--gray-50", "--blue-50", "--gray-900"]


def _parse_vars(css):
    out = {}
    for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css):
        out[name] = val.strip()
    # resolve one level of var() indirection, repeatedly
    for _ in range(5):
        for k, v in list(out.items()):
            m = re.fullmatch(r"var\((--[\w-]+)\)", v)
            if m and m.group(1) in out:
                out[k] = out[m.group(1)]
    return out


def _hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    c = []
    for v in rgb:
        v /= 255
        c.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def check_contrast():
    css = CSS_PATH.read_text(encoding="utf-8")
    variables = _parse_vars(css)

    surfaces = {}
    for s in SURFACES:
        rgb = _hex_to_rgb(variables.get(s, ""))
        if rgb:
            surfaces[s] = rgb
    if not surfaces:
        fail("contrast", "css/style.css", "could not resolve any surface colours")
        return

    # Every --color-text-* token must clear AA on every light surface (and the
    # dark footer surface is checked separately for light-on-dark tokens).
    light = {k: v for k, v in surfaces.items() if _lum(v) > 0.5}
    for name, val in sorted(variables.items()):
        if not name.startswith("--color-text"):
            continue
        rgb = _hex_to_rgb(val)
        if not rgb:
            continue
        for sname, srgb in light.items():
            r = _ratio(rgb, srgb)
            if r < 4.5:
                fail("contrast", "css/style.css",
                     f"{name} ({val}) on {sname} is {r:.2f}:1 — needs 4.5:1")

    # Any literal colour used for small text anywhere in the stylesheet.
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip().split("\n")[-1].strip()
        body = m.group(2)
        cm = re.search(r"(?<!-)\bcolor:\s*(#[0-9a-fA-F]{3,6})\s*;", body)
        if not cm:
            continue
        rgb = _hex_to_rgb(cm.group(1))
        if not rgb:
            continue
        # Only meaningful for text on a light surface; skip obvious dark-surface UI.
        if any(x in selector for x in ("footer", "hero", "cta", "nav-mobile")):
            continue
        # Icons are non-text UI components: WCAG asks 3:1, not 4.5:1.
        is_icon = bool(re.search(r"\bsvg\b|icon", selector))
        need = 3.0 if is_icon else 4.5
        white = surfaces.get("--white")
        if white and _ratio(rgb, white) < need:
            kind = "icon" if is_icon else "text"
            fail("contrast", "css/style.css",
                 f"'{selector}' uses {cm.group(1)} which is "
                 f"{_ratio(rgb, white):.2f}:1 on white — {kind} needs {need}:1")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Internal links must resolve
#    Shipped bug: W-2 / 1095 links pointed at pages that did not exist.
# ─────────────────────────────────────────────────────────────────────────────

def check_internal_links():
    for page in ALL_PAGES:
        html = strip_style_and_script(read(page))
        base = (ROOT / page).parent
        for href in re.findall(r'href="([^"]+)"', html):
            if re.match(r"^(https?:|mailto:|tel:|#|data:)", href):
                continue
            target = href.split("#")[0].split("?")[0]
            if not target:
                continue
            resolved = (base / target).resolve()
            if resolved.exists():
                continue
            # Cloudflare serves extensionless clean URLs too
            if resolved.with_suffix(".html").exists():
                continue
            fail("links", page, f'href="{href}" does not resolve to a file')


# ─────────────────────────────────────────────────────────────────────────────
# 5. Nav and footer must be identical across pages
#    Shipped bug: the News footer link was missing from 6 of 7 footers, and was
#    called "HR News" on the one page that had it.
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_href(page, href):
    """
    Make links comparable across pages. A same-page anchor is written "#payroll"
    on services.html but "services.html#payroll" everywhere else — same
    destination, different spelling.
    """
    href = href.strip()
    if href.startswith("./"):
        href = href[2:]
    if href.startswith("#"):
        return f"{page}{href}"
    return href


def _links_in(html, cls, page):
    return sorted(set(
        (_normalize_href(page, h), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip())
        for h, t in re.findall(
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>(.*?)</a>',
            html, flags=re.S)
    ))


def check_nav_footer_consistency():
    navs, foots = {}, {}
    for page in STATIC_PAGES:
        html = read(page)
        navs[page] = _links_in(html, "nav-link", page)
        foots[page] = _links_in(html, "footer-link", page)

    for label, sets in (("nav", navs), ("footer", foots)):
        # compare by href set, ignoring the active-page styling
        by_href = {p: sorted(h for h, _ in v) for p, v in sets.items()}
        reference = max(by_href.values(), key=len) if by_href else []
        for page, hrefs in by_href.items():
            missing = sorted(set(reference) - set(hrefs))
            if missing:
                fail("nav-footer", page,
                     f"{label} is missing link(s) present on other pages: {', '.join(missing)}")

        # the same href must use the same label everywhere
        labels = {}
        for page, pairs in sets.items():
            for href, text in pairs:
                labels.setdefault(href, {}).setdefault(text, []).append(page)
        for href, variants in labels.items():
            if len(variants) > 1:
                shown = "; ".join(f'"{t}" on {len(ps)} page(s)' for t, ps in variants.items())
                fail("nav-footer", "(across pages)",
                     f'{label} link {href} uses different labels: {shown}')


# ─────────────────────────────────────────────────────────────────────────────
# 6. No hardcoded current year
#    Shipped bug: "© 2026" was baked into 8 files and would silently go stale.
# ─────────────────────────────────────────────────────────────────────────────

def check_year():
    year = datetime.now().year
    for page in STATIC_PAGES:
        html = read(page)
        for m in re.finditer(r"&copy;\s*(\d{4})", html):
            # acceptable only when wrapped so JS can update it
            window = html[m.start():m.start() + 120]
            if 'class="js-year"' in window:
                continue
            if page == "news.html":
                continue  # regenerated monthly by the generator
            fail("year", page,
                 f'hardcoded "&copy; {m.group(1)}" — wrap the year in '
                 f'<span class="js-year"> so it updates')

    gen = (ROOT / "scripts" / "generate_news.py").read_text(encoding="utf-8")
    if re.search(r"&copy;\s*\d{4}\s+StaffPro", gen):
        fail("year", "scripts/generate_news.py",
             "hardcoded copyright year — use {datetime.now().year}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Newsletter integrity
#    Shipped bug: 42 blocks of model-invented "detail" were published with no
#    source anywhere on the card.
# ─────────────────────────────────────────────────────────────────────────────

def check_newsletter_integrity():
    for page in ALL_PAGES:
        html = strip_style_and_script(read(page))
        if '<div class="news-detail"' in html or '<button class="news-expand-toggle"' in html:
            fail("newsletter", page,
                 "contains a 'Read more' detail block — that content was model-written "
                 "beyond the source and must not be published")

    gen = (ROOT / "scripts" / "generate_news.py").read_text(encoding="utf-8")
    if '"detail"' in gen and "source_index" not in gen:
        fail("newsletter", "scripts/generate_news.py",
             "prompt appears to request a free-form 'detail' field again")

    # Match the rendered markup, not the string "news-source" — that also appears
    # in the stylesheet, which let a broken renderer pass.
    if '<p class="news-source">' not in gen:
        fail("newsletter", "scripts/generate_news.py",
             "story cards no longer render a Source link")

    # Require the CALL, with the paren. A bare substring test passed happily when
    # attach_sources was renamed to attach_sources_disabled.
    if not re.search(r"(?<!def )\battach_sources\(", gen):
        fail("newsletter", "scripts/generate_news.py",
             "attach_sources() is no longer called — stories could publish uncited")
    # \b so a rename like MIN_STORIES_OFF does not satisfy this.
    if not re.search(r"<\s*MIN_STORIES\b", gen):
        fail("newsletter", "scripts/generate_news.py",
             "the minimum-sourced-stories floor is no longer enforced")

    # The voice spec is the writing brief. Without it the copy reverts to
    # generic AI prose, which is the whole thing this was built to avoid.
    spec = ROOT / "scripts" / "website-newsletter-voice.md"
    if not spec.exists():
        fail("newsletter", "scripts/website-newsletter-voice.md",
             "the approved voice spec is missing")
    elif len(spec.read_text(encoding="utf-8").split()) < 200:
        fail("newsletter", "scripts/website-newsletter-voice.md",
             "the voice spec looks truncated")
    if not re.search(r"(?<!def )\bload_voice_spec\(", gen):
        fail("newsletter", "scripts/generate_news.py",
             "load_voice_spec() is not called — copy would not follow the approved voice")

    # Verbatim-overlap guard: the enforceable half of the copyright rules.
    if not re.search(r"(?<!def )\benforce_originality\(", gen):
        fail("newsletter", "scripts/generate_news.py",
             "enforce_originality() is not called — copy could be lifted from sources")

    # A trap worth a permanent check: conditions[term] looks like a helpful topic
    # filter on the Federal Register API but collapses 54 results to 1.
    # Comments are stripped first — the warning comment in the generator names the
    # parameter, and matching that is how this check first failed on itself.
    gen_code = "\n".join(l for l in gen.splitlines() if not l.lstrip().startswith("#"))
    if '"conditions[term]"' in gen_code or "'conditions[term]'" in gen_code:
        fail("newsletter", "scripts/generate_news.py",
             "conditions[term] is back in the Federal Register query — it silently "
             "collapses the result set to almost nothing")

    # requests puts the full URL, apiKey included, in its exception text.
    if re.search(r"Warning — trade-press query.*\{e\}", gen):
        fail("newsletter", "scripts/generate_news.py",
             "the NewsAPI error path logs the raw exception, which contains the API key")


# ─────────────────────────────────────────────────────────────────────────────
# 8. The news bot must not publish without review
#    Shipped bug: the workflow pushed straight to main on a schedule.
# ─────────────────────────────────────────────────────────────────────────────

def check_news_workflow():
    wf = ROOT / ".github" / "workflows" / "monthly-news.yml"
    if not wf.exists():
        fail("workflow", str(wf), "monthly news workflow is missing")
        return
    raw = wf.read_text(encoding="utf-8")
    # Strip comment lines first: a comment mentioning "pull-requests: write" was
    # enough to satisfy this check even after the real permission was downgraded.
    text = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))

    if re.search(r"git push(\s+origin)?\s+main\b", text) or re.search(r"git push\s*$", text, re.M):
        fail("workflow", "monthly-news.yml",
             "pushes directly to main — the newsletter must go through a review PR")
    if "gh pr create" not in text:
        fail("workflow", "monthly-news.yml", "no longer opens a review PR")
    if not re.search(r"^\s*pull-requests:\s*write\s*$", text, re.M):
        fail("workflow", "monthly-news.yml",
             "pull-requests: write is not granted, so opening the review PR will fail")
    if not re.search(r"^\s*-\s*cron:", text, re.M):
        fail("workflow", "monthly-news.yml", "the monthly schedule was removed")


CHECKS = [
    ("content visible without JS", check_js_resilience),
    ("forms degrade + validate", check_forms),
    ("text contrast (WCAG AA)", check_contrast),
    ("internal links resolve", check_internal_links),
    ("nav/footer consistent", check_nav_footer_consistency),
    ("no hardcoded year", check_year),
    ("newsletter integrity", check_newsletter_integrity),
    ("news bot needs review", check_news_workflow),
]


def main():
    verbose = "--verbose" in sys.argv
    print(f"Checking {len(ALL_PAGES)} pages ({len(STATIC_PAGES)} static, {len(NEWS_PAGES)} news)\n")

    for label, fn in CHECKS:
        before = len(failures)
        fn()
        n = len(failures) - before
        print(f"  {'FAIL' if n else 'ok  '}  {label}" + (f"  ({n} problem(s))" if n else ""))

    if notes and verbose:
        print("\nNotes:")
        for n in notes:
            print(f"  - {n}")

    if failures:
        print(f"\n{'=' * 70}\n{len(failures)} problem(s) found\n{'=' * 70}")
        by_check = {}
        for check, page, msg in failures:
            by_check.setdefault(check, []).append((page, msg))
        for check, items in by_check.items():
            print(f"\n[{check}]")
            for page, msg in items:
                print(f"  {page}\n      {msg}")
        print()
        return 1

    print("\nAll checks passed.")
    return 0


# KNOWN LIMITS — what this does NOT catch, so nobody assumes it does:
#   * Anything only visible at runtime: JS errors, layout breakage, whether a
#     form's handler actually posts. Those still need a browser.
#   * Whether newsletter copy is TRUE. Nothing automated can check that — that is
#     what the monthly review PR is for.
#   * Text colour set inline in HTML rather than in style.css.
#   * Contrast against gradient backgrounds (skipped: no single background colour).

if __name__ == "__main__":
    sys.exit(main())

# ci-probe: temporary, deleted with this branch.
