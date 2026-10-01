# Publishing the Monthly HR Newsletter

**Who this is for:** whoever approves the StaffPro newsletter each month. No website
experience needed. You will not touch any code.

**The one-sentence version:** on the 1st of each month a draft newsletter appears as a
"pull request" on GitHub; you read it, check the facts, and click **Merge** to publish it.

**Nothing goes on the website until you click Merge.** If you do nothing, nothing publishes.

---

## What happens automatically

On the 1st of every month, in the morning Eastern time, the system:

1. Collects recent HR and compliance news articles
2. Has Claude write up to five stories from them
3. **Inspects the finished pages for problems** (broken links, unreadable text, and so on)
4. Saves the result as a **draft** and opens a review page on GitHub
5. **Stops there and waits for you**

GitHub sometimes runs it a few hours late. In October 2026 the draft appeared at
about 12:30pm rather than first thing. That's normal.

### One-time setup: make sure GitHub emails you

GitHub only emails you about new drafts if you are **watching** the repository.
In October 2026 no email came for exactly this reason. To turn it on:

1. Go to https://github.com/elly-staffpro/staffproinc
2. Click **Watch** (top right)
3. Choose **All Activity**

After that you'll get an email titled **"Monthly HR news — [Month] [Year]"** each month.
If one ever doesn't arrive, check your spam folder, or just go straight to Step 1.

---

## Your monthly steps

### Step 1 — Open the draft

Either click the link in the GitHub email, **or** go to:

> https://github.com/elly-staffpro/staffproinc/pulls

You'll see one item named **"Monthly HR news — October 2026"** (with that month's name).
Click it.

### Step 2 — Check the inspection result, then preview it

The very top of the draft page tells you whether the automatic inspection passed:

- **"Site Checks: passed"** — carry on.
- **"⚠️ Site Checks FAILED on this draft — do not merge"** — stop. The title will also
  start with **CHECKS FAILED**. The problems are listed right there. Don't merge; ask for
  a fix, or close the draft and skip the month.

Right under that is a **Preview** link. Click it to see the newsletter exactly as a
visitor would. (GitHub's own "Files changed" tab only shows raw code, not the page.)

The link always follows the same pattern, if you ever need to type it:

> https://news-2026-11.staffproinc.pages.dev/news

with that month's year and number in place of `2026-11`.

Further down the draft page, find **"Candidate sources"** and click the small triangle
to expand it. That's the list of real articles the stories came from, with links.

### Step 3 — Read every story and check it

This is the part that matters. Claude wrote these stories from news headlines. It is
usually right, but it is not a person and it does not know your clients.

**For each of the five stories, ask:**

- [ ] Is every **date, dollar amount, percentage, deadline, and agency name** correct?
      Click the **"Source:"** link at the bottom of the story and check it against the
      original article. If you cannot confirm a number, that story needs to be removed or
      the number taken out.
- [ ] Is anything **wrong for New York or New Jersey** specifically? Most of our clients
      are NY.
- [ ] Is this **old news** or a repeat of last month?
- [ ] Does it read like **legal advice**? It should not.
- [ ] Would you be comfortable if a client **acted on this and it turned out wrong?**

> **The rule: if you cannot verify it, it does not publish.**
> There is no penalty for skipping a month. There is a real penalty for a client acting
> on a wrong compliance date.

### Step 4 — Publish, or don't

**If everything checks out:**
Scroll to the bottom of the GitHub draft page → click the green **"Merge pull request"**
button → then **"Confirm merge"**.

The newsletter goes live at https://www.staffproinc.com/news within about 2 minutes.

**If something is wrong:**

- *One story is bad, the rest are fine* → reply on the draft page saying which story to
  cut, and ask for it to be removed before merging. Do not merge until it's fixed.
- *The whole thing is weak or wrong* → click **"Close pull request"**. Nothing publishes.
  Last month's newsletter stays up. That is a perfectly fine outcome.

---

## Common questions

**What if I'm away on the 1st?**
Nothing breaks. The draft waits. Merge it on the 5th, the 10th, whenever. The site keeps
showing the previous month until you do.

**What if I merge something wrong by accident?**
It can be undone. Say so and it gets reverted — it's a couple of minutes of work.

**What if no draft shows up?**
Check https://github.com/elly-staffpro/staffproinc/actions for a red X on
"Monthly HR News Update". A red X means it failed and needs a look. No draft and no red X
means it had nothing new to publish.

**Do the published stories link to their sources?**
Yes. Every story ends with **"Source: [outlet name]"** and that link goes to the original
article. If a story cannot be traced back to a real article, it is dropped automatically
and never reaches the draft.

**Where do the articles come from?**
An approved list of HR, employment-law, benefits and workers' comp publications, plus the
major business wires. If a given month is quiet and the approved list comes up short, the
search widens — and the draft page shows a clear warning naming which articles came from
outside the approved list. Those deserve extra scrutiny.

**Who can do this?** Anyone with access to the GitHub repository. It does not have to be
the same person every month.

---

## Why it works this way

Before September 2026 this system published straight to the live website with nobody
reading it first, and Claude was being asked to write several paragraphs of supporting
detail that went beyond what the source articles actually said. That content went public
automatically.

The review step exists so that a person reads every word before a client can.
**Your merge click is the only thing standing between a draft and your clients.**
