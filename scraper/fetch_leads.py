"""
SurplusIQ — Excess Elite API Fetcher
Pulls all leads for our 10 counties directly from the Excess Elite API.
Replaces the Real Foreclosure scraper entirely.
"""

import os
import json
import time
import requests
from datetime import date, datetime
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

API_KEY  = os.getenv("EXCESS_ELITE_API_KEY", "IzQhXdhNByrufs-BIqfgEsrjLIkvm_Dla_vPy8wEYidYxuGkuFQ64bv2gN3wgcAn")
BASE_URL = "https://excesselite.com/api"
HEADERS  = {"X-Api-Key": API_KEY}

# ── Our 10 counties — exact names as Excess Elite expects ─────────────
COUNTIES = [
    {"id": "miami-dade-fl",  "name": "Miami Dade",  "state": "FL", "doc_days": 14},
    {"id": "broward-fl",     "name": "Broward",      "state": "FL", "doc_days": 7},
    {"id": "duval-fl",       "name": "Duval",        "state": "FL", "doc_days": 5},
    {"id": "lee-fl",         "name": "Lee",          "state": "FL", "doc_days": 7},
    {"id": "orange-fl",      "name": "Orange",       "state": "FL", "doc_days": 2},
    {"id": "cuyahoga-oh",    "name": "Cuyahoga",     "state": "OH", "doc_days": 10},
    {"id": "franklin-oh",    "name": "Franklin",     "state": "OH", "doc_days": 10},
    {"id": "montgomery-oh",  "name": "Montgomery",   "state": "OH", "doc_days": 10},
    {"id": "summit-oh",      "name": "Summit",       "state": "OH", "doc_days": 10},
    {"id": "hamilton-oh",    "name": "Hamilton",     "state": "OH", "doc_days": 10},
]

PLAINTIFF_KEYWORDS = [
    "bank", "n.a.", "trust", "financial", "federal", "national",
    "mortgage", "fannie", "freddie", "wells fargo", "chase", "citibank",
    "us bank", "u.s. bank", "pennymac", "newrez", "ocwen", "nationstar",
    "mr. cooper", "lakeview", "freedom", "plaintiff", "certificate",
]


def clean_dollar(s) -> float:
    """Convert '$123,456.00' or number to float."""
    if not s:
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def normalize_lead(raw: dict, county: dict) -> dict:
    """
    Normalize an Excess Elite API lead into our standard format.
    Maps API fields to our internal field names.
    """
    surplus     = clean_dollar(raw.get("surplus_amount"))
    opening_bid = clean_dollar(raw.get("opening_bid"))
    closing_bid = clean_dollar(raw.get("closing_bid"))

    # Build full address
    street   = (raw.get("property_street") or "").title()
    city     = (raw.get("property_city") or "").title()
    state    = (raw.get("property_state") or county["state"]).upper()
    zip_code = raw.get("property_zip_code") or ""
    address  = f"{street}, {city}, {state} {zip_code}".strip(", ")

    # Owner name
    first = (raw.get("first_name") or "").strip()
    last  = (raw.get("last_name") or "").strip()
    owner = f"{first} {last}".strip() if (first or last) else ""

    # Sale date normalization
    sale_date = raw.get("normalized_date_sold") or raw.get("date_sold") or ""

    return {
        # Identity
        "county_id":          county["id"],
        "county_name":        county["name"],
        "state":              county["state"],
        "excess_elite_id":    raw.get("id"),

        # Property
        "address":            address,
        "property_street":    street,
        "property_city":      city,
        "property_zip":       zip_code,
        "parcel_id":          raw.get("parcel_number") or "",
        "case_number":        raw.get("case_number") or "",

        # Owner
        "owner_name":         owner,
        "first_name":         first,
        "last_name":          last,

        # Financial
        "surplus_amount":     surplus,
        "opening_bid":        opening_bid,
        "final_sale_price":   closing_bid,
        "gross_surplus":      surplus,   # Already calculated by Excess Elite
        "net_surplus":        surplus,   # Will be refined after lien check

        # Metadata
        "lead_type":          raw.get("lead_category") or raw.get("type_of_foreclosure") or "",
        "sale_date":          sale_date,
        "source":             raw.get("source") or "",
        "county_page_url":    raw.get("county_page_url") or "",

        # Pipeline defaults (filled in later)
        "claim_status":       "unknown",
        "doc_status":         "pending",
        "doc_available":      False,
        "has_secondary_liens": None,
        "total_secondary_liens": 0,
        "lien_flags_str":     "",
        "pr_enriched":        False,
        "score":              0,
        "grade":              "C",
        "outreach_ready":     False,
        "next_check":         "pending",
        "fetched_at":         datetime.now().isoformat(),
    }


def fetch_county(county: dict, per_page: int = 100) -> list:
    """
    Fetch all leads for one county from the Excess Elite API.
    Handles pagination automatically.
    """
    leads = []
    page  = 1

    print(f"  Fetching {county['name']}, {county['state']}...")

    while True:
        try:
            params = {
                "states[]":   county["state"],
                "counties[]": county["name"],
                "per_page":   per_page,
                "page":       page,
                "sort":       "normalized_date_sold",
                "direction":  "desc",
            }
            r = requests.get(
                f"{BASE_URL}/leads",
                headers=HEADERS,
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()

            batch = data.get("data", [])
            meta  = data.get("meta", {})

            for raw in batch:
                leads.append(normalize_lead(raw, county))

            total   = meta.get("total_count", 0)
            has_next = meta.get("has_next", False)

            if page == 1:
                print(f"    Total available: {total} | Fetching page {page}/{meta.get('total_pages', 1)}")

            if not has_next:
                break

            page += 1
            time.sleep(0.3)  # Respect rate limit (120 req/min)

        except requests.exceptions.RequestException as e:
            print(f"    ⚠ API error on page {page}: {e}")
            break

    print(f"    ✓ {len(leads)} leads fetched")
    return leads


def fetch_lead_detail(lead_id: int) -> dict:
    """
    Fetch full detail for a single lead (includes phone, email, mailing address).
    """
    try:
        r = requests.get(
            f"{BASE_URL}/leads/{lead_id}",
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("data", {})
    except Exception as e:
        print(f"    ⚠ Detail fetch failed for {lead_id}: {e}")
        return {}


def enrich_with_details(leads: list, max_detail: int = 200) -> list:
    """
    Fetch full detail records for leads to get phone, email, mailing address.
    Limits to max_detail to avoid rate limits.
    """
    print(f"\n  Fetching contact details for up to {max_detail} leads...")
    enriched = 0

    for lead in leads[:max_detail]:
        lead_id = lead.get("excess_elite_id")
        if not lead_id:
            continue

        detail = fetch_lead_detail(lead_id)
        if detail:
            # Add contact fields from detail response
            lead["phone1"]          = detail.get("phone1") or detail.get("phone") or ""
            lead["phone2"]          = detail.get("phone2") or ""
            lead["email"]           = detail.get("email") or detail.get("email_address") or ""
            lead["mailing_address"] = detail.get("mailing_address") or detail.get("mailing_street") or ""
            lead["mailing_city"]    = detail.get("mailing_city") or ""
            lead["mailing_state"]   = detail.get("mailing_state") or ""
            lead["mailing_zip"]     = detail.get("mailing_zip") or ""
            lead["owner_age"]       = detail.get("age") or ""
            lead["deceased"]        = detail.get("deceased") or False
            enriched += 1

        time.sleep(0.5)

    print(f"    ✓ {enriched} leads enriched with contact details")
    return leads


def fetch_all_counties(county_ids: list = None, get_details: bool = True) -> list:
    """
    Main function: fetch all leads for all 10 counties.
    Returns normalized list ready for the scoring pipeline.
    """
    targets = COUNTIES
    if county_ids:
        targets = [c for c in COUNTIES if c["id"] in county_ids]

    all_leads = []
    print(f"\n📡 Fetching from Excess Elite API — {len(targets)} counties...")

    for county in targets:
        leads = fetch_county(county)
        all_leads.extend(leads)
        time.sleep(0.5)

    # Optional: get contact details for top leads
    if get_details and all_leads:
        # Sort by surplus descending before fetching details
        all_leads.sort(key=lambda x: x.get("surplus_amount", 0), reverse=True)
        all_leads = enrich_with_details(all_leads, max_detail=100)

    # Save to JSONL
    today    = date.today().isoformat()
    out_file = DATA_DIR / f"raw_all_{today}.jsonl"
    with open(out_file, "w") as f:
        for lead in all_leads:
            f.write(json.dumps(lead) + "\n")

    print(f"\n✅ Fetch complete: {len(all_leads)} total leads")
    print(f"💾 Saved: {out_file}")

    # Print county summary
    county_counts = {}
    for lead in all_leads:
        k = f"{lead['county_name']} ({lead['state']})"
        county_counts[k] = county_counts.get(k, 0) + 1

    print("\n  County breakdown:")
    for county, count in sorted(county_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {county}: {count}")

    total_surplus = sum(l.get("surplus_amount", 0) or 0 for l in all_leads)
    print(f"\n  Total surplus in system: ${total_surplus:,.0f}")

    return all_leads


def load_raw(date_str: str = None) -> list:
    """Load fetched leads from JSONL file."""
    if not date_str:
        date_str = date.today().isoformat()
    fp = DATA_DIR / f"raw_all_{date_str}.jsonl"
    if not fp.exists():
        return []
    with open(fp) as f:
        return [json.loads(l) for l in f if l.strip()]


def get_stats() -> dict:
    """Quick stats check against the API."""
    stats = {}
    for county in COUNTIES:
        r = requests.get(
            f"{BASE_URL}/leads",
            headers=HEADERS,
            params={"states[]": county["state"], "counties[]": county["name"], "per_page": 1},
            timeout=10,
        )
        total = r.json().get("meta", {}).get("total_count", 0)
        stats[county["id"]] = total
        time.sleep(0.3)
    return stats


if __name__ == "__main__":
    import sys
    county_ids = sys.argv[1:] if len(sys.argv) > 1 else None

    if "--stats" in sys.argv:
        print("\n📊 Live county stats from Excess Elite API:")
        stats = get_stats()
        total = 0
        for county in COUNTIES:
            count = stats.get(county["id"], 0)
            total += count
            print(f"  {county['name']:15} ({county['state']}): {count:,} leads")
        print(f"\n  Total: {total:,} leads")
    else:
        leads = fetch_all_counties(county_ids=county_ids, get_details=False)
