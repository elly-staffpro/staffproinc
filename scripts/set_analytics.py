#!/usr/bin/env python3
"""
Add, update or remove the Cloudflare Web Analytics beacon across the whole site.

Why this exists: staffproinc.com keeps its nameservers at GoDaddy so the email
records stay put, which means the domain is not a Cloudflare zone — it reaches
Cloudflare through a CNAME to the Pages project. Cloudflare's one-click
"automatic injection" only works for domains proxied through Cloudflare, so the
beacon has to live in the HTML instead. That is 17 pages plus the news
generator, and they must all carry the SAME token or the numbers split.

Usage
  py scripts/set_analytics.py <site-token>   install or update the beacon
  py scripts/set_analytics.py --remove       take it back out
  py scripts/set_analytics.py --status       report what is installed

Get the token: Cloudflare dashboard -> Analytics & Logs -> Web Analytics ->
Add a site -> enter staffproinc.com -> copy the value of "token" from the
snippet it shows you (a 32-character hex string).
"""

import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(ROOT, "scripts", "generate_news.py")

BEGIN = "<!-- Cloudflare Web Analytics -->"
END = "<!-- End Cloudflare Web Analytics -->"

# Cookie-free and privacy-preserving, so no consent banner is required.
# defer keeps it off the critical path; it must never delay the page.
SNIPPET = (
    '  {begin}\n'
    '  <script defer src="https://static.cloudflareinsights.com/beacon.min.js"\n'
    "          data-cf-beacon='{{\"token\": \"{token}\"}}'></script>\n"
    '  {end}\n'
)

# Consumes the whole line, indentation included. Matching only from the opening
# comment leaves the snippet's two leading spaces behind, and those pile up in
# front of </head> on every install/remove cycle.
BLOCK_RE = re.compile(
    r"^[ \t]*" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"[ \t]*\n?",
    re.S | re.M)
TOKEN_RE = re.compile(r'"token":\s*"([0-9a-fA-F]{6,})"')


def pages():
    """Every page a visitor can land on, newest generator template aside."""
    out = sorted(glob.glob(os.path.join(ROOT, "*.html")))
    out += sorted(glob.glob(os.path.join(ROOT, "news", "*.html")))
    return out


def strip(text):
    return BLOCK_RE.sub("", text)


def install(text, token, indent="  "):
    """Put the beacon immediately before </head>, replacing any existing one."""
    text = strip(text)
    snippet = SNIPPET.format(begin=BEGIN, end=END, token=token)
    if indent != "  ":
        snippet = "\n".join((indent + l[2:]) if l.startswith("  ") else l
                            for l in snippet.split("\n"))
    marker = "</head>"
    i = text.find(marker)
    if i == -1:
        return None
    return text[:i] + snippet + text[i:]


def status():
    tokens = {}
    missing = []
    for p in pages() + [GENERATOR]:
        t = io.open(p, encoding="utf-8").read()
        m = BLOCK_RE.search(t)
        if not m:
            missing.append(os.path.relpath(p, ROOT))
            continue
        tok = TOKEN_RE.search(m.group(0))
        tokens.setdefault(tok.group(1) if tok else "(unreadable)", []).append(
            os.path.relpath(p, ROOT))

    total = len(pages()) + 1
    if not tokens:
        print(f"No beacon installed. {total} file(s) would be updated.")
        return 0
    print(f"Beacon present on {total - len(missing)} of {total} file(s).")
    for tok, files in tokens.items():
        print(f"  token {tok[:8]}...  on {len(files)} file(s)")
    if missing:
        print(f"  MISSING from {len(missing)}: {', '.join(missing[:6])}"
              + (" ..." if len(missing) > 6 else ""))
    if len(tokens) > 1:
        print("  WARNING: more than one token in use — traffic will be split.")
        return 1
    return 0 if not missing else 1


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    arg = sys.argv[1]

    if arg == "--status":
        return status()

    removing = arg == "--remove"
    if not removing and not re.fullmatch(r"[0-9a-fA-F]{6,}", arg):
        print(f"'{arg}' does not look like a Cloudflare site token "
              f"(expected hex, usually 32 characters).")
        return 2

    changed = 0
    for p in pages():
        t0 = io.open(p, encoding="utf-8").read()
        t = strip(t0) if removing else install(t0, arg)
        if t is None:
            print(f"  SKIPPED (no </head>): {os.path.relpath(p, ROOT)}")
            continue
        if t != t0:
            io.open(p, "w", encoding="utf-8", newline="").write(t)
            changed += 1

    # The generator writes future news pages, so it needs the beacon too. Its
    # template is an f-string: the braces in the JSON have to be doubled.
    t0 = io.open(GENERATOR, encoding="utf-8").read()
    if removing:
        t = strip(t0)
    else:
        snippet = SNIPPET.format(begin=BEGIN, end=END, token=arg)
        snippet = snippet.replace("{", "{{").replace("}", "}}")
        snippet = snippet.replace("{{begin}}", BEGIN).replace("{{end}}", END)
        t = strip(t0)
        marker = "  <style>{SHARED_STYLES}"
        i = t.find(marker)
        if i == -1:
            print("  ERROR: could not find the generator's head template")
            return 1
        t = t[:i] + snippet + t[i:]
    if t != t0:
        io.open(GENERATOR, "w", encoding="utf-8", newline="").write(t)
        changed += 1

    print(f"{'Removed from' if removing else 'Installed on'} {changed} file(s).")
    print("Run: py scripts/check_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
