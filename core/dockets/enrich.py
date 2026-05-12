"""
SurplusIQ — Docket Enrichment CLI

Reads current leads from data/raw/<county>_<date>.jsonl, runs the docket
scraper against each one, and saves enriched results to data/dockets/.

Usage:
  python -m core.dockets.enrich cuyahoga-oh                # all Cuyahoga leads
  python -m core.dockets.enrich cuyahoga-oh --case CV25110711
  python -m core.dockets.enrich cuyahoga-oh --headed       # see browser
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Project paths
def _find_project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "config" / "counties.py").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _find_project_root()
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DOCKETS_DIR = PROJECT_ROOT / "data" / "dockets"
DOCKETS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))
from core.dockets import get_scraper, SCRAPER_REGISTRY


def latest_raw_file(county_id: str) -> Path | None:
    files = sorted(p for p in RAW_DIR.glob(f"{county_id}_*.jsonl") if p.stat().st_size > 0)
    return files[-1] if files else None


def load_cases_from_raw(county_id: str) -> list[dict]:
    f = latest_raw_file(county_id)
    if not f:
        return []
    records = []
    with open(f) as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


async def run_one(county_id: str, case_number: str, headless: bool, final_sale_price: float = 0.0) -> dict:
    scraper = get_scraper(county_id, headless=headless)
    result = await scraper.scrape_case(case_number)

    # Re-classify with the actual sale price if provided
    if final_sale_price > 0:
        result.classification, result.classification_reason = scraper.classify(result, final_sale_price)

    return result.to_dict()


async def run_county(county_id: str, headless: bool, only_case: str | None = None) -> dict:
    if county_id not in SCRAPER_REGISTRY:
        raise SystemExit(f"No docket scraper for {county_id}. Available: {list(SCRAPER_REGISTRY.keys())}")

    records = load_cases_from_raw(county_id)
    if not records:
        raise SystemExit(f"No raw scraper data found for {county_id}. Run the auction scraper first.")

    if only_case:
        records = [r for r in records if r.get("case_number", "").startswith(only_case[:8])]

    print(f"\n🏛  Cuyahoga docket scrape — processing {len(records)} leads")
    print(f"    Headless: {headless}")
    print()

    results = []
    for i, rec in enumerate(records, 1):
        case = rec.get("case_number", "")
        final = float(rec.get("final_sale_price") or 0.0)
        opening = float(rec.get("opening_bid") or 0.0)
        apparent = float(rec.get("gross_surplus") or 0.0)
        print(f"  [{i}/{len(records)}] {case}  (apparent surplus ${apparent:,.0f})")

        try:
            result = await run_one(county_id, case, headless=headless, final_sale_price=final)
        except Exception as e:
            print(f"      ⚠ scrape failed: {e}")
            continue

        prayer = result.get("prayer_amount", 0.0)
        true_surplus = final - prayer if prayer > 0 else None
        cls = result.get("classification", "?")
        reason = result.get("classification_reason", "")

        if prayer > 0:
            print(f"      prayer amount: ${prayer:,.0f}   |   true surplus: ${true_surplus:,.0f}")
        else:
            print(f"      prayer amount: not found")
        print(f"      classification: {cls.upper()}  ({reason})")
        if result.get("kill_signals"):
            print(f"      🚨 kill signals: {', '.join(result['kill_signals'])}")
        if result.get("proof_of_surplus"):
            print(f"      ✅ proof: {result['proof_of_surplus']}")
        if result.get("competing_filers"):
            print(f"      ⚠️  competing: {', '.join(result['competing_filers'])}")
        print()

        # Tag with the auction lead's original data for downstream use
        result["_auction_data"] = {
            "final_sale_price": final,
            "opening_bid":      opening,
            "apparent_surplus": apparent,
            "true_surplus":     true_surplus,
            "address":          rec.get("address", ""),
        }
        results.append(result)

    # Save enriched results
    out_file = DOCKETS_DIR / f"{county_id}_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(out_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\n💾 Saved {len(results)} docket results to {out_file.relative_to(PROJECT_ROOT)}")

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    by_class = {}
    for r in results:
        c = r.get("classification", "unknown")
        by_class[c] = by_class.get(c, 0) + 1
    for c in ["green", "yellow", "red", "killed", "unknown"]:
        if by_class.get(c):
            print(f"  {c.upper():<8}  {by_class[c]:>3} leads")
    print()

    return {"county_id": county_id, "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("county_id", help="County identifier, e.g. cuyahoga-oh")
    ap.add_argument("--case", help="Run against one specific case number prefix only")
    ap.add_argument("--headed", action="store_true", help="Show browser window (default: headless)")
    args = ap.parse_args()

    asyncio.run(run_county(args.county_id, headless=not args.headed, only_case=args.case))


if __name__ == "__main__":
    main()
