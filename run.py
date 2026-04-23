"""
SurplusIQ — Master Pipeline Runner
Run this daily to scrape, enrich, verify, and export leads

Usage:
  python run.py                    # Full run, all 10 counties
  python run.py --counties miami-dade-fl broward-fl   # Specific counties
  python run.py --skip-scrape      # Use today's existing raw data
  python run.py --skip-enrich      # Skip PropertyRadar (use existing enriched)
  python run.py --skip-clerk       # Skip clerk checks
  python run.py --test             # Quick test with 2 counties
  python run.py --headed           # Show browser windows (useful for CAPTCHA)
"""

import asyncio
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "enrichment"))
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "output"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def banner(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


async def main():
    parser = argparse.ArgumentParser(description="SurplusIQ Daily Pipeline")
    parser.add_argument("--counties",     nargs="+", help="Specific county IDs to run")
    parser.add_argument("--skip-scrape",  action="store_true", help="Skip auction scraping")
    parser.add_argument("--skip-enrich",  action="store_true", help="Skip PropertyRadar enrichment")
    parser.add_argument("--skip-clerk",   action="store_true", help="Skip clerk docket checks")
    parser.add_argument("--test",         action="store_true", help="Test mode: 2 counties only")
    parser.add_argument("--headed",       action="store_true", help="Show browser windows")
    parser.add_argument("--date",         type=str,            help="Date string YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    today     = args.date or date.today().isoformat()
    headless  = not args.headed

    if args.test:
        county_ids = ["miami-dade-fl", "cuyahoga-oh"]
        print("🧪 TEST MODE: Running Miami-Dade + Cuyahoga only")
    else:
        county_ids = args.counties

    banner(f"SurplusIQ Daily Run — {today}")

    # ── STEP 1: Scrape Auction Results ────────────────────────────────
    raw_properties = []

    if not args.skip_scrape:
        banner("STEP 1 — Scraping Real Foreclosure")
        from realforeclose import run_all_counties, load_raw
        raw_properties = await run_all_counties(county_ids=county_ids, headless=headless)
    else:
        banner("STEP 1 — Loading existing raw data (skip-scrape)")
        from realforeclose import load_raw
        raw_properties = load_raw(today)
        print(f"  Loaded {len(raw_properties)} properties from {today}")

    if not raw_properties:
        print("⚠️  No raw properties found. Check scraper output.")
        return

    # ── STEP 2: Filter Third-Party Sales Only ─────────────────────────
    banner("STEP 2 — Filtering Third-Party Sales")
    from pipeline import is_third_party_sale, MIN_SURPLUS_THRESHOLD, clean_dollar
    import re

    third_party_props = []
    for prop in raw_properties:
        if is_third_party_sale(prop):
            # Quick surplus check before enriching
            final  = float(prop.get("final_sale_price", 0) or 0)
            opening = float(prop.get("opening_bid", 0) or 0)
            if final > opening and (final - opening) >= MIN_SURPLUS_THRESHOLD:
                third_party_props.append(prop)

    print(f"  Total scraped:        {len(raw_properties)}")
    print(f"  Third-party surplus:  {len(third_party_props)}")

    if not third_party_props:
        print("⚠️  No third-party surplus properties found today.")
        # Still build empty output
        _finalize([], today)
        return

    # ── STEP 3: PropertyRadar Enrichment ──────────────────────────────
    enriched_props = []

    if not args.skip_enrich:
        banner("STEP 3 — PropertyRadar Enrichment")
        try:
            import re as re_module
            import sys
            sys.modules["re"] = re_module
            from enrichment import enrich_batch, save_enriched
            enriched_props = enrich_batch(third_party_props, delay=0.6)
            save_enriched(enriched_props, today)
        except Exception as e:
            print(f"  ⚠ PropertyRadar enrichment failed: {e}")
            print("  Continuing with un-enriched properties...")
            enriched_props = third_party_props
    else:
        banner("STEP 3 — Loading existing enriched data (skip-enrich)")
        from enrichment import load_enriched
        enriched_props = load_enriched(today)
        if not enriched_props:
            print("  No enriched data found, using raw third-party props")
            enriched_props = third_party_props
        else:
            print(f"  Loaded {len(enriched_props)} enriched properties")

    # ── STEP 4: Surplus Detection & Scoring ───────────────────────────
    banner("STEP 4 — Surplus Detection & Lead Scoring")
    from pipeline import run_pipeline, save_leads
    scored_leads = run_pipeline(enriched_props)
    save_leads(scored_leads, today)

    # ── STEP 5: Clerk Docket Checks ───────────────────────────────────
    verified_leads = scored_leads

    if not args.skip_clerk:
        banner("STEP 5 — Clerk Docket Verification")
        try:
            from clerk import run_clerk_checks, save_verified
            verified_leads = await run_clerk_checks(scored_leads, headless=headless)
            save_verified(verified_leads, today)

            # Re-score after clerk check (claim status may have changed)
            banner("STEP 5b — Re-scoring after clerk verification")
            from pipeline import run_pipeline
            verified_leads = run_pipeline(verified_leads)
            save_leads(verified_leads, today)

        except Exception as e:
            print(f"  ⚠ Clerk checks failed: {e}")
            print("  Continuing with pre-verification scores...")
    else:
        banner("STEP 5 — Skipping clerk checks (skip-clerk)")

    # ── STEP 6: Export ────────────────────────────────────────────────
    banner("STEP 6 — Generating Exports")
    _finalize(verified_leads, today)

    # ── STEP 7: Update Dashboard Data ────────────────────────────────
    banner("STEP 7 — Updating Dashboard")
    _update_dashboard(verified_leads, today)

    # ── Done ──────────────────────────────────────────────────────────
    banner("✅ SurplusIQ Run Complete")
    a_plus = sum(1 for l in verified_leads if l.get("grade") == "A+")
    outreach = sum(1 for l in verified_leads if l.get("outreach_ready"))
    total_surplus = sum(l.get("net_surplus", 0) or 0 for l in verified_leads)
    print(f"  Total leads:     {len(verified_leads)}")
    print(f"  A+ leads:        {a_plus}")
    print(f"  Outreach ready:  {outreach}")
    print(f"  Total surplus:   ${total_surplus:,.0f}")
    print(f"\n  📊 Dashboard: dashboard/index.html")
    print(f"  📋 Excel:     output/SurplusIQ_Leads_{today}.xlsx")


def _finalize(leads: list, date_str: str):
    """Build Excel export."""
    try:
        from excel_export import build_excel
        build_excel(leads, date_str)
    except Exception as e:
        print(f"  ⚠ Excel export failed: {e}")


def _update_dashboard(leads: list, date_str: str):
    """Write JSON files for the GitHub Pages dashboard."""
    dashboard_data_dir = ROOT / "dashboard" / "data"
    dashboard_data_dir.mkdir(parents=True, exist_ok=True)

    # Summary stats
    total_surplus = sum(l.get("net_surplus", 0) or 0 for l in leads)
    grades = {"A+": 0, "A": 0, "B": 0, "C": 0}
    for l in leads:
        g = l.get("grade", "C")
        grades[g] = grades.get(g, 0) + 1

    # Per-county breakdown
    counties = {}
    for lead in leads:
        cid = lead.get("county_id", "")
        if cid not in counties:
            counties[cid] = {
                "id":       cid,
                "name":     lead.get("county_name", ""),
                "state":    lead.get("state", ""),
                "leads":    0,
                "surplus":  0,
                "aplus":    0,
            }
        counties[cid]["leads"]   += 1
        counties[cid]["surplus"] += lead.get("net_surplus", 0) or 0
        if lead.get("grade") == "A+":
            counties[cid]["aplus"] += 1

    summary = {
        "generated_at":   date_str,
        "total_leads":    len(leads),
        "total_surplus":  total_surplus,
        "grades":         grades,
        "outreach_ready": sum(1 for l in leads if l.get("outreach_ready")),
        "docs_ready":     sum(1 for l in leads if l.get("doc_available")),
        "counties":       list(counties.values()),
    }

    with open(dashboard_data_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Lead data (sanitized for dashboard — no raw docket text)
    dashboard_leads = []
    for lead in leads:
        dashboard_leads.append({
            "grade":           lead.get("grade"),
            "score":           lead.get("score"),
            "county_name":     lead.get("county_name"),
            "state":           lead.get("state"),
            "address":         lead.get("address"),
            "owner_name":      lead.get("owner_name"),
            "case_number":     lead.get("case_number"),
            "sale_date":       lead.get("sale_date"),
            "final_sale_price": lead.get("final_sale_price"),
            "opening_bid":     lead.get("opening_bid"),
            "net_surplus":     lead.get("net_surplus"),
            "gross_surplus":   lead.get("gross_surplus"),
            "claim_status":    lead.get("claim_status"),
            "partial_claim":   lead.get("partial_claim"),
            "doc_status":      lead.get("doc_status"),
            "doc_available":   lead.get("doc_available"),
            "has_secondary_liens": lead.get("has_secondary_liens"),
            "lien_flags_str":  lead.get("lien_flags_str"),
            "winner_name":     lead.get("winner_name"),
            "outreach_ready":  lead.get("outreach_ready"),
            "next_check":      lead.get("next_check"),
            "pr_enriched":     lead.get("pr_enriched"),
            "lead_type":       lead.get("lead_type", "Mortgage Foreclosure"),
        })

    with open(dashboard_data_dir / "leads.json", "w") as f:
        json.dump(dashboard_leads, f, indent=2)

    print(f"  ✅ Dashboard data written to dashboard/data/")
    print(f"     summary.json — {len(leads)} leads, ${total_surplus:,.0f} total surplus")


if __name__ == "__main__":
    asyncio.run(main())
