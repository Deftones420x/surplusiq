# SurplusIQ — VA Loom Audit Template

Please watch each Loom video and fill in this template per county.
Paste the completed doc back into the chat when done.

---

## Overview for the VA

You are watching 10 Loom videos where Eric walks through his surplus funds research process for each county. Your job is to capture the exact URLs, case formats, and quirks so the developer can automate the work.

**For each county, capture:**
1. Every URL visited (copy from browser address bar)
2. The case number format shown (e.g., "2025-CA-048821")
3. Whether there's CAPTCHA, VPN issues, or other blockers
4. The exact click sequence from home page to the data
5. Screenshots of key pages (save them with county name)

**Priority fields are bold.** These are the absolute minimum.

---

## Loom Links

1. Miami-Dade: https://www.loom.com/share/d8e3fd2a6d8b4ed6b92033ed4e3a82d8
2. Broward: https://www.loom.com/share/0d5437959df24b66983b30a102660a0e
3. Duval: https://www.loom.com/share/4558cf7cbe0747c8abb3f952e451628d
4. Lee + Orange: https://www.loom.com/share/0a2126022c76497a9cbed78906fb3b6c
5. Cuyahoga: https://www.loom.com/share/90ee6cbc59d14c799acd3da45bb2fe88
6. Franklin: https://www.loom.com/share/ab9d3e65620245d2947311e5f8d5a4fb
7. Montgomery: https://www.loom.com/share/10a38347aa874a2b80b7666eada1fffb
8. Summit: https://www.loom.com/share/9301d98e665f45cebebfca87a4643093
9. Hamilton: https://www.loom.com/share/78a3db7c1a034e8399090a93db7bd066

---

## Template — Fill In Per County

Copy this block 10 times, once per county.

```
═══════════════════════════════════════════════════════════════════
COUNTY: [name]
STATE:  [FL or OH]
═══════════════════════════════════════════════════════════════════

## AUCTION (RealForeclose)

**Base URL shown in video:** [e.g. miami-dade.realforeclose.com]
**URL when viewing yesterday's sold results:** [exact URL from address bar]
**URL when viewing a specific auction day:** [exact URL]
**How do they navigate to "sold" results?** [describe click sequence]

## CLERK DOCKET SYSTEM

**Clerk URL (main search page):** [exact URL]
**How do they enter the case number?**
  [ ] Paste the whole thing (e.g., "2024-CA-001234")
  [ ] Split into separate fields (year, sequence, code)
  [ ] Other: ___
**Case number format example from video:** [e.g., "2024-CA-048821"]
**Is there a CAPTCHA?** Yes / No
**What happens after searching?** [describe what loads]

## TAX DEED / SURPLUS PORTAL (if separate)

**Tax deed URL:** [exact URL or "N/A — same calendar as mortgage"]
**How do they search?** [paste case number, search by year, etc.]
**What document shows surplus?** [e.g., "Notice of Surplus", "Surplus Letter"]

## OHIO SPECIFIC (skip for Florida counties)

**What's the "prayer amount" or actual debt lookup method?**
  [ ] Search docket for "judgment"
  [ ] Search docket for "prayer"
  [ ] Look at "Motion for Default Judgment"
  [ ] Other: ___
**Public excess funds list URL (if any):** [URL]

## QUIRKS & WATCH-FORS

**Sale schedule:** [e.g., "daily", "Fridays only", "Mon mortgage / Wed tax"]
**Doc timing:** [how many days after sale do surplus docs post?]
**Keywords Eric flags as "kill the lead":** [e.g., "motion to vacate", "order cancelling sale"]
**Keywords Eric flags as "surplus exists":** [e.g., "Certificate of Disbursement"]
**Keywords Eric flags as "already claimed":** [e.g., "motion to disburse"]

## SCREENSHOTS (save to folder and list filenames here)

- `[county]_auction_home.png` — auction site home
- `[county]_auction_sold.png` — sold results page
- `[county]_clerk_search.png` — clerk search page
- `[county]_clerk_docket.png` — example case docket

## NOTES

[Any other quirks, warnings, or things the developer should know]
```

---

## Quality Checklist

Before submitting, confirm for each county:
- [ ] All URLs copied directly from the browser address bar (not typed from memory)
- [ ] Case number format written exactly as shown
- [ ] CAPTCHA yes/no flagged
- [ ] Click sequence described in plain English
- [ ] At least 3 screenshots saved per county
- [ ] Ohio counties: debt lookup method specified

## Delivery Format

Save everything in one folder per county:
```
county_audits/
├── miami-dade-fl/
│   ├── template.md
│   ├── auction_home.png
│   ├── auction_sold.png
│   ├── clerk_search.png
│   └── clerk_docket.png
├── broward-fl/
│   └── ...
```

Then paste the filled-in template back into chat when done with each county.
