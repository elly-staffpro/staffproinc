#!/usr/bin/env python3
"""
Tests for check_site.py.

A check that never fails is decorative. This re-introduces each bug that actually
shipped, into a throwaway copy of the site, and asserts the checker catches it —
so we know the guardrail is real and not just green.

Run:  py scripts/test_check_site.py
Exit: 0 = every check proven to catch its bug
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


def build_sandbox(tmp):
    """Copy the site into a temp dir so mutations never touch the real repo."""
    dst = Path(tmp) / "site"
    shutil.copytree(
        ROOT, dst,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".claude"))
    return dst


def run_checker(site):
    r = subprocess.run([sys.executable, str(site / "scripts" / "check_site.py")],
                       capture_output=True, text=True, cwd=str(site))
    return r.returncode, r.stdout + r.stderr


def edit(path, fn):
    t = io.open(path, encoding="utf-8").read()
    t2 = fn(t)
    assert t2 != t, f"mutation was a no-op on {path} — the test itself is broken"
    io.open(path, "w", encoding="utf-8", newline="").write(t2)


# (name, expected check tag, mutation)
CASES = [
    ("content hidden when JS fails (page loses failsafe)", "js-resilience",
     lambda s: edit(s / "index.html", lambda t: t.replace("__spAnimReady", "__notTheFlag", 1))),

    ("content hidden when JS fails (CSS unscoped)", "js-resilience",
     lambda s: edit(s / "css" / "style.css",
                    lambda t: t.replace(".js-anim .fade-in {", ".fade-in {", 1))),

    ("form stops validating (novalidate returns)", "forms",
     lambda s: edit(s / "contact.html",
                    lambda t: t.replace('<form id="contactForm"',
                                        '<form novalidate id="contactForm"', 1))),

    ("form cannot submit without JS (action removed)", "forms",
     lambda s: edit(s / "resources.html",
                    lambda t: t.replace(' action="https://api.web3forms.com/submit"', "", 1))),

    ("muted text contrast regresses", "contrast",
     lambda s: edit(s / "css" / "style.css",
                    lambda t: t.replace("--gray-450: #6C6C80;", "--gray-450: #9C9CB0;", 1))),

    ("internal link points nowhere", "links",
     lambda s: edit(s / "about.html",
                    lambda t: t.replace('href="contact.html"', 'href="contact-us.html"', 1))),

    ("footer link disappears from one page", "nav-footer",
     lambda s: edit(s / "about.html",
                    lambda t: re.sub(r'\s*<a href="news\.html"\s*class="footer-link">HR News</a>',
                                     "", t, count=1))),

    ("one link gets two different names", "nav-footer",
     lambda s: edit(s / "index.html",
                    lambda t: t.replace(">Client Onboarding Tutorials<", ">Onboarding Videos<", 1))),

    ("copyright year hardcoded again", "year",
     lambda s: edit(s / "index.html",
                    lambda t: t.replace('&copy; <span class="js-year">2026</span>',
                                        "&copy; 2026", 1))),

    ("fabricated 'Read more' block returns", "newsletter",
     lambda s: edit(s / "news.html",
                    lambda t: t.replace("</article>",
                                        '<div class="news-detail" hidden><p>invented</p></div></article>', 1))),

    ("story cards stop citing sources", "newsletter",
     lambda s: edit(s / "scripts" / "generate_news.py",
                    lambda t: t.replace('class="news-source"', 'class="news-src-disabled"'))),

    ("source resolution removed", "newsletter",
     lambda s: edit(s / "scripts" / "generate_news.py",
                    lambda t: t.replace("attach_sources", "attach_sources_disabled"))),

    ("news bot publishes straight to main", "workflow",
     lambda s: edit(s / ".github" / "workflows" / "monthly-news.yml",
                    lambda t: t.replace("gh pr create", "git push origin main #", 1))),

    # Note: target the real permissions line, not the comment above it that also
    # mentions "pull-requests: write" — mutating the comment proved nothing.
    ("review PR loses permission to open", "workflow",
     lambda s: edit(s / ".github" / "workflows" / "monthly-news.yml",
                    lambda t: re.sub(r"^(\s*)pull-requests:\s*write\s*$", r"\1pull-requests: read",
                                     t, count=1, flags=re.M))),

    ("monthly schedule removed", "workflow",
     lambda s: edit(s / ".github" / "workflows" / "monthly-news.yml",
                    lambda t: re.sub(r"^\s*-\s*cron:.*$", "", t, flags=re.M))),

    ("minimum sourced-story floor removed", "newsletter",
     lambda s: edit(s / "scripts" / "generate_news.py",
                    lambda t: t.replace("MIN_STORIES", "MIN_STORIES_OFF"))),
]


def main():
    print("Proving each check catches the bug it exists for.\n")

    with tempfile.TemporaryDirectory() as tmp:
        clean = build_sandbox(tmp)
        code, out = run_checker(clean)
        if code != 0:
            print("Baseline is not clean — fix the site before trusting these tests:\n")
            print(out)
            return 1
        print("  ok    baseline passes\n")

    passed = failed = 0
    for label, tag, mutate in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            site = build_sandbox(tmp)
            mutate(site)
            code, out = run_checker(site)
            caught = code != 0 and f"[{tag}]" in out
            if caught:
                passed += 1
                print(f"  ok    caught: {label}")
            else:
                failed += 1
                print(f"  FAIL  NOT caught: {label}")
                print(f"        expected check '{tag}' to fail; exit={code}")
                for line in out.splitlines():
                    if "FAIL" in line or "problem" in line:
                        print(f"        | {line}")

    print(f"\n{passed} caught, {failed} missed, {len(CASES)} total")
    if failed:
        print("\nA missed case means that bug could ship again unnoticed.")
        return 1
    print("Every check is proven to fail when its bug is reintroduced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
