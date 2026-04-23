# SurplusIQ — Project Architecture

## Overview

Multi-state surplus funds intelligence system matching the signed SOW. Phase 1 + 2 covers 10 counties (FL 5 + OH 5). Built as 8 modular components that each do one job well.

## Project Structure

```
surplusiq/
├── config/
│   ├── counties.py          # All county configs (URLs, formats, quirks)
│   ├── thresholds.py        # Business rules (min surplus, score weights)
│   └── __init__.py
│
├── core/                    # The 8 SOW components
│   ├── auction/             # Component 4.1 — Auction Tracking Engine
│   │   ├── base.py          # Abstract base class
│   │   ├── realforeclose.py # FL + OH (shared platform)
│   │   ├── sri.py           # Indiana (Phase 3)
│   │   └── __init__.py
│   │
│   ├── surplus/             # Component 4.2 — Surplus Detection Engine
│   │   ├── detector.py      # Core surplus calculation
│   │   └── __init__.py
│   │
│   ├── enrichment/          # Component 4.3 — Property Intelligence
│   │   ├── propertyradar.py # PropertyRadar API wrapper
│   │   └── __init__.py
│   │
│   ├── documents/           # Component 4.4 — Document Retrieval
│   │   ├── retriever.py     # Core doc retrieval logic
│   │   ├── recheck.py       # Day 3/7/14 re-scan scheduler
│   │   └── __init__.py
│   │
│   ├── clerks/              # Component 4.5 — Court Docket Verification
│   │   ├── base.py          # Abstract clerk scraper
│   │   ├── oscar.py         # Miami-Dade
│   │   ├── broward.py       # Broward Web2
│   │   ├── core_duval.py    # Duval CORE
│   │   ├── lee.py           # Lee eFiling
│   │   ├── orange.py        # Orange myEClerk
│   │   ├── cuyahoga.py      # Cuyahoga CP Docket
│   │   ├── franklin.py      # Franklin FCJS
│   │   ├── montgomery.py    # Montgomery
│   │   ├── summit.py        # Summit
│   │   ├── hamilton.py      # Hamilton
│   │   └── __init__.py
│   │
│   ├── taxdeed/             # Component 4.4b — Tax Deed Portal Scrapers
│   │   ├── realtdm.py       # FL RealTDM portal
│   │   ├── orange_comp.py   # Orange Comptroller
│   │   └── __init__.py
│   │
│   ├── scoring/             # Component 4.7 — Lead Scoring
│   │   ├── scorer.py        # A+/A/B/C grading logic
│   │   └── __init__.py
│   │
│   └── output/              # Component 4.8 — Output Formats
│       ├── excel.py         # XLSX export
│       ├── csv_export.py    # CSV export
│       ├── dashboard.py     # JSON for dashboard
│       └── __init__.py
│
├── pipeline/
│   ├── orchestrator.py      # Main daily runner
│   ├── state.py             # Pipeline state tracking
│   └── __init__.py
│
├── utils/
│   ├── captcha.py           # Manual CAPTCHA pause helpers
│   ├── browser.py           # Playwright session management
│   ├── dedup.py             # Check Excess Elite for duplicates
│   └── __init__.py
│
├── data/                    # Runtime data (gitignored)
│   ├── raw/                 # Raw scraped data by county/date
│   ├── enriched/            # After PropertyRadar enrichment
│   ├── verified/            # After clerk verification
│   ├── final/               # Final scored leads
│   └── diagnostics/         # Screenshots, HTML dumps for debugging
│
├── docs/                    # GitHub Pages dashboard
│   ├── index.html
│   └── data/
│       ├── leads.json
│       └── summary.json
│
├── output/                  # Excel exports (gitignored)
│
├── tests/                   # Per-component tests
│   ├── test_auction.py
│   ├── test_clerks.py
│   └── ...
│
├── .github/
│   └── workflows/
│       └── daily_pipeline.yml
│
├── run.py                   # Main entry point
├── .env                     # API keys (gitignored)
├── .gitignore
├── requirements.txt
└── README.md
```

## Data Flow

```
[Auction Scraper]
      ↓
  Raw Sales
      ↓
[Surplus Detector] ← filters for 3rd party + $10K+ surplus
      ↓
  Surplus Leads
      ↓
[PropertyRadar Enricher] ← adds lien/debt data
      ↓
  Enriched Leads
      ↓
[Clerk Docket Verifier] ← checks claim status, Cert of Disbursement
      ↓
  Verified Leads
      ↓
[Document Retriever] ← Day 3/7/14 re-checks
      ↓
[Scorer] ← A+/A/B/C grading
      ↓
[Output] ← Excel + Dashboard JSON
      ↓
[Dedup Check] ← skip leads already in Excess Elite
      ↓
  DELIVERY: Hosted Site + Excel
```

## Build Order

### Phase 1 (Florida) — Week 1-2
1. Build `auction/realforeclose.py` working for Miami-Dade
2. Build `clerks/oscar.py` for Miami-Dade OSCAR
3. Build `surplus/detector.py` with Eric's rules
4. Build `enrichment/propertyradar.py`
5. Connect end-to-end for Miami-Dade
6. Replicate auction config for Broward, Duval, Lee, Orange
7. Build each FL clerk scraper
8. Build `taxdeed/realtdm.py` for FL tax sales

### Phase 2 (Ohio) — Week 3
9. Extend `auction/realforeclose.py` with Ohio 2/3 appraisal logic
10. Build 5 Ohio clerk scrapers
11. Handle Ohio's "prayer amount" lookup for debt

### Polish — Week 4
12. `documents/recheck.py` Day 3/7/14 scheduler
13. Dashboard polish + GitHub Actions automation
14. Excel formatting final pass
15. Dedup against Excess Elite API
16. Deliver

## Key Design Principles

**Each county scraper is independent** — if Hamilton breaks, the other 9 keep running. No shared state between counties.

**Every stage saves output** — auction → surplus → enriched → verified → final. If any stage fails, we can resume from the last checkpoint.

**CAPTCHA counties run headed with manual pause** — Lee, Cuyahoga, Hamilton prompt the user to solve manually. The pipeline pauses until they press Enter.

**All selectors/URLs live in config** — when a county changes its site, update the config file, not the code.

**Dedup before delivery** — the final step hits Excess Elite API to skip any case numbers already in his system. Only NEW leads go to Eric.
