"""
SurplusIQ — Master Pipeline Runner v2
Uses Excess Elite API instead of Real Foreclosure scraper.

Usage:
  python run.py                    # Full run, all 10 counties
  python run.py --test             # Miami Dade + Cuyahoga only
  python run.py --skip-fetch       # Use today's existing data
  python run.py --skip-enrich      # Skip PropertyRadar
  python run.py --skip-clerk       # Skip clerk checks
  python run.py --stats            # Just show county lead counts
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
    parser.add_argument("--test",        action="store_true", help="Test: Miami Dade + Cuyahoga only")
    parser.add_argument("--skip-fetch",  action="store_true", help="Skip API fetch, use existing data")
    parser.add_argument("--skip-enrich", action="store_true", help="Skip PropertyRadar enrichment")
    parser.add_argument("--skip-clerk",  action="store_true", help="Skip clerk docket checks")
    parser.add_argument("--stats",       action="store_true", help="Show live county stats only")
    parser.add_argument("--date",        type=str,            help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    today = args.date or date.today().isoformat()

    if args.stats:
        from fetch_leads import get_stats, COUNTIES
        print("\n📊 Live county stats from Excess Elite API:")
        stats = get_stats()
        total = 0
        for county in COUNTIES:
            count = stats.get(county["id"], 0)
            total += count
            bar = "█" * (count // 20)
            print(f"  {county['name']:15} ({county['state']}): {count:>4} leads  {bar}")
        print(f"\n  Total: {total:,} leads across 10 counties")
        return

    if args.test:
        county_ids = ["miami-dade-fl", "cuyahoga-oh"]
        print("🧪 TEST MODE: Miami Dade + Cuyahoga only")
    else:
        county_ids = None

    banner(f"SurplusIQ Daily Run — {today}")

    # STEP 1: Fetch from Excess Elite API
    raw_leads = []
    if not args.skip_fetch:
        banner("STEP 1 — Fetching leads from Excess Elite API")
        from fetch_leads import fetch_all_counties
        raw_leads = fetch_all_counties(county_ids=county_ids, get_details=False)
    else:
        banner("STEP 1 — Loading existing data (skip-fetch)")
        from fetch_leads import load_raw
        raw_leads = load_raw(today)
        print(f"  Loaded {len(raw_leads)} leads from {today}")

    if not raw_leads:
        print("No leads found.")
        return

    # STEP 2: Score leads
    banner("STEP 2 — Scoring leads")
    scored_leads = score_leads(raw_leads)

    # STEP 3: PropertyRadar enrichment (top leads only)
    if not args.skip_enrich:
        banner("STEP 3 — PropertyRadar Enrichment (top 100 leads)")
        try:
            import re as re_mod
            sys.modules.setdefault("re", re_mod)
            from enrichment import enrich_batch, save_enriched
            top    = [l for l in scored_leads if l.get("grade") in ("A+", "A")][:100]
            rest   = [l for l in scored_leads if l not in top]
            top    = enrich_batch(top, delay=0.6)
            scored_leads = score_leads(top + rest)
        except Exception as e:
            print(f"  PropertyRadar skipped: {e}")
    else:
        banner("STEP 3 — Skipping PropertyRadar")

    # STEP 4: Clerk checks (top A+/A only)
    if not args.skip_clerk:
        banner("STEP 4 — Clerk Docket Checks")
        try:
            from clerk import run_clerk_checks
            top  = [l for l in scored_leads if l.get("grade") in ("A+", "A")][:50]
            rest = [l for l in scored_leads if l not in top]
            top  = await run_clerk_checks(top, headless=True)
            scored_leads = score_leads(top + rest)
        except Exception as e:
            print(f"  Clerk checks skipped: {e}")
    else:
        banner("STEP 4 — Skipping clerk checks")

    # Save
    out = DATA_DIR / f"leads_{today}.jsonl"
    with open(out, "w") as f:
        for l in scored_leads:
            f.write(json.dumps(l) + "\n")
    print(f"\n💾 Leads saved: {out}")

    # Excel
    banner("STEP 5 — Excel export")
    try:
        from excel_export import build_excel
        build_excel(scored_leads, today)
    except Exception as e:
        print(f"  Excel failed: {e}")

    # Dashboard
    banner("STEP 6 — Dashboard update")
    update_dashboard(scored_leads, today)

    # Summary
    banner("✅ Done")
    a_plus   = sum(1 for l in scored_leads if l.get("grade") == "A+")
    outreach = sum(1 for l in scored_leads if l.get("outreach_ready"))
    surplus  = sum(l.get("net_surplus", 0) or 0 for l in scored_leads)
    print(f"  Total leads:    {len(scored_leads):,}")
    print(f"  A+ leads:       {a_plus}")
    print(f"  Outreach ready: {outreach}")
    print(f"  Total surplus:  ${surplus:,.0f}")
    print(f"\n  📋 output/SurplusIQ_Leads_{today}.xlsx")
    print(f"  🌐 dashboard/index.html")


def score_leads(leads: list) -> list:
    scored = []
    for lead in leads:
        surplus      = float(lead.get("surplus_amount") or lead.get("net_surplus") or 0)
        claim_status = lead.get("claim_status", "unknown")
        has_liens    = lead.get("has_secondary_liens")
        doc_avail    = lead.get("doc_available", False)
        pr_enriched  = lead.get("pr_enriched", False)

        score = 0
        if surplus >= 100000:  score += 50
        elif surplus >= 50000: score += 42
        elif surplus >= 25000: score += 34
        elif surplus >= 10000: score += 24
        elif surplus >= 5000:  score += 14
        elif surplus >= 1000:  score += 6

        if claim_status == "none":       score += 25
        elif claim_status == "unknown":  score += 18
        elif claim_status == "partial":  score += 12
        elif claim_status == "filed":    score += 3

        if has_liens is False:   score += 15
        elif has_liens is None:  score += 10
        if doc_avail:            score += 7
        if pr_enriched:          score += 3

        if score >= 80:    grade = "A+"
        elif score >= 65:  grade = "A"
        elif score >= 45:  grade = "B"
        else:              grade = "C"

        if claim_status == "disbursed": grade = "C"; score = min(score, 10)
        if surplus < 1000:              grade = "C"; score = min(score, 5)

        lead["score"]         = score
        lead["grade"]         = grade
        lead["net_surplus"]   = surplus
        lead["outreach_ready"] = (
            grade in ("A+", "A")
            and claim_status in ("none", "unknown", "partial")
            and surplus >= 5000
        )
        scored.append(lead)

    scored.sort(key=lambda x: (
        {"A+": 4, "A": 3, "B": 2, "C": 1}.get(x.get("grade", "C"), 0),
        x.get("net_surplus", 0)
    ), reverse=True)

    grades = {g: sum(1 for l in scored if l.get("grade") == g) for g in ["A+","A","B","C"]}
    print(f"  {len(scored)} leads — A+:{grades['A+']} A:{grades['A']} B:{grades['B']} C:{grades['C']}")
    return scored


def update_dashboard(leads: list, date_str: str):
    dd = ROOT / "dashboard" / "data"
    dd.mkdir(parents=True, exist_ok=True)

    total_surplus = sum(l.get("net_surplus", 0) or 0 for l in leads)
    grades = {g: sum(1 for l in leads if l.get("grade") == g) for g in ["A+","A","B","C"]}

    counties = {}
    for lead in leads:
        cid = lead.get("county_id", "")
        if cid not in counties:
            counties[cid] = {"id": cid, "name": lead.get("county_name",""), "state": lead.get("state",""), "leads": 0, "surplus": 0, "aplus": 0}
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
        "counties":       list(counties.values()),
    }
    (dd / "summary.json").write_text(json.dumps(summary, indent=2))

    dash = [{
        "grade": l.get("grade"), "score": l.get("score"),
        "county_name": l.get("county_name"), "state": l.get("state"),
        "address": l.get("address"), "owner_name": l.get("owner_name"),
        "case_number": l.get("case_number"), "parcel_id": l.get("parcel_id"),
        "sale_date": l.get("sale_date"), "final_sale_price": l.get("final_sale_price"),
        "opening_bid": l.get("opening_bid"), "net_surplus": l.get("net_surplus"),
        "surplus_amount": l.get("surplus_amount"), "lead_type": l.get("lead_type"),
        "claim_status": l.get("claim_status"), "doc_available": l.get("doc_available"),
        "outreach_ready": l.get("outreach_ready"), "source": l.get("source"),
    } for l in leads]
    (dd / "leads.json").write_text(json.dumps(dash, indent=2))
    print(f"  ✅ Dashboard updated — {len(leads)} leads, ${total_surplus:,.0f} surplus")


if __name__ == "__main__":
    asyncio.run(main())
