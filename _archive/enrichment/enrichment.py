"""
SurplusIQ — PropertyRadar Enrichment
Pulls mortgage, lien, and owner data for each flagged property
API docs: https://help.propertyradar.com/en/articles/6885272-using-the-propertyradar-import-api
"""

import os
import json
import time
import requests
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

# ── API Config ────────────────────────────────────────────────────────
PR_TOKEN = os.getenv("PROPERTY_RADAR_TOKEN", "9ffe6b0ba3006ee59b74184dd200802f3cf42700")
PR_BASE  = "https://api.propertyradar.com/v1"

HEADERS = {
    "Authorization": f"Bearer {PR_TOKEN}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}

# Lien types that can reduce net surplus
LIEN_FIELDS = [
    "OpenMortgageBalance1",   # First mortgage
    "OpenMortgageBalance2",   # Second mortgage / HELOC
    "TaxLienAmount",          # IRS / state tax lien
    "HOALienAmount",          # HOA lien
    "JudgmentLienAmount",     # Judgment lien
    "MechanicsLienAmount",    # Mechanics lien
]

OWNER_FIELDS = [
    "OwnerName1",
    "OwnerName2",
    "MailingAddress",
    "MailingCity",
    "MailingState",
    "MailingZip",
    "Phone1",
    "Phone2",
    "EmailAddress",
]

PROPERTY_FIELDS = [
    "SitusAddress",
    "SitusCity",
    "SitusState",
    "SitusZip",
    "ParcelNumber",
    "LotSqFt",
    "Bedrooms",
    "Bathrooms",
    "YearBuilt",
    "PropertyType",
    "EstimatedValue",
]


def search_by_address(address: str, city: str, state: str) -> dict:
    """
    Search PropertyRadar for a property by address.
    Returns the first matching property's Purchase ID (used for detail pulls).
    """
    try:
        url = f"{PR_BASE}/properties"
        params = {
            "address": address,
            "city":    city,
            "state":   state,
            "fields":  "PurchaseID,SitusAddress,ParcelNumber",
            "limit":   1,
        }
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("data", [])
        if results:
            return results[0]
        return {}
    except requests.exceptions.RequestException as e:
        print(f"    PR search error for {address}: {e}")
        return {}


def get_property_detail(purchase_id: str) -> dict:
    """
    Pull full property detail from PropertyRadar using Purchase ID.
    Returns lien amounts, owner info, mortgage balance.
    """
    try:
        all_fields = LIEN_FIELDS + OWNER_FIELDS + PROPERTY_FIELDS
        url = f"{PR_BASE}/properties/{purchase_id}"
        params = {"fields": ",".join(all_fields)}
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {})
    except requests.exceptions.RequestException as e:
        print(f"    PR detail error for {purchase_id}: {e}")
        return {}


def enrich_property(prop: dict) -> dict:
    """
    Main enrichment function.
    Takes a scraped property dict, returns it enriched with PR data.
    """
    enriched = prop.copy()
    enriched["pr_enriched"] = False
    enriched["pr_error"]    = None

    # Parse address components
    address = prop.get("address", "")
    state   = prop.get("state", "")

    # Try to split city from address if combined
    # Format might be "123 Main St, Miami, FL 33101"
    city = ""
    addr_clean = address
    addr_parts = address.split(",")
    if len(addr_parts) >= 2:
        addr_clean = addr_parts[0].strip()
        city       = addr_parts[1].strip() if len(addr_parts) > 1 else ""
        # Remove state/zip from city if present
        city = re.sub(r"\s*(FL|OH|[A-Z]{2})\s*\d{5}.*", "", city, flags=re.IGNORECASE).strip()

    if not addr_clean:
        enriched["pr_error"] = "no_address"
        return enriched

    # Step 1: Search for property
    search_result = search_by_address(addr_clean, city, state)
    if not search_result:
        # Try with just address and state (no city)
        search_result = search_by_address(addr_clean, "", state)

    if not search_result:
        enriched["pr_error"] = "not_found"
        return enriched

    purchase_id = search_result.get("PurchaseID", "")
    if not purchase_id:
        enriched["pr_error"] = "no_purchase_id"
        return enriched

    enriched["pr_purchase_id"] = purchase_id

    # Step 2: Get full detail
    detail = get_property_detail(purchase_id)
    if not detail:
        enriched["pr_error"] = "detail_failed"
        return enriched

    # ── Owner Info ────────────────────────────────────────────────────
    enriched["owner_name"]      = detail.get("OwnerName1", prop.get("owner_name", ""))
    enriched["owner_name2"]     = detail.get("OwnerName2", "")
    enriched["mailing_address"] = detail.get("MailingAddress", "")
    enriched["mailing_city"]    = detail.get("MailingCity", "")
    enriched["mailing_state"]   = detail.get("MailingState", "")
    enriched["mailing_zip"]     = detail.get("MailingZip", "")
    enriched["phone1"]          = detail.get("Phone1", "")
    enriched["phone2"]          = detail.get("Phone2", "")
    enriched["email"]           = detail.get("EmailAddress", "")

    # ── Property Info ─────────────────────────────────────────────────
    enriched["parcel_id"]       = detail.get("ParcelNumber", prop.get("parcel_id", ""))
    enriched["property_type"]   = detail.get("PropertyType", "")
    enriched["estimated_value"] = float(detail.get("EstimatedValue", 0) or 0)
    enriched["year_built"]      = detail.get("YearBuilt", "")
    enriched["bedrooms"]        = detail.get("Bedrooms", "")
    enriched["bathrooms"]       = detail.get("Bathrooms", "")

    # ── Lien Analysis ─────────────────────────────────────────────────
    mortgage1  = float(detail.get("OpenMortgageBalance1", 0) or 0)
    mortgage2  = float(detail.get("OpenMortgageBalance2", 0) or 0)
    tax_lien   = float(detail.get("TaxLienAmount", 0) or 0)
    hoa_lien   = float(detail.get("HOALienAmount", 0) or 0)
    jdg_lien   = float(detail.get("JudgmentLienAmount", 0) or 0)
    mech_lien  = float(detail.get("MechanicsLienAmount", 0) or 0)

    enriched["mortgage_balance_1"] = mortgage1
    enriched["mortgage_balance_2"] = mortgage2
    enriched["tax_lien_amount"]    = tax_lien
    enriched["hoa_lien_amount"]    = hoa_lien
    enriched["judgment_lien"]      = jdg_lien
    enriched["mechanics_lien"]     = mech_lien

    # Total known encumbrances (excluding first mortgage — already in judgment)
    enriched["total_secondary_liens"] = mortgage2 + tax_lien + hoa_lien + jdg_lien + mech_lien

    # Lien flag
    enriched["has_secondary_liens"] = enriched["total_secondary_liens"] > 0
    enriched["lien_flags"] = []
    if mortgage2 > 0:  enriched["lien_flags"].append(f"2nd Mortgage: ${mortgage2:,.0f}")
    if tax_lien > 0:   enriched["lien_flags"].append(f"Tax Lien: ${tax_lien:,.0f}")
    if hoa_lien > 0:   enriched["lien_flags"].append(f"HOA: ${hoa_lien:,.0f}")
    if jdg_lien > 0:   enriched["lien_flags"].append(f"Judgment: ${jdg_lien:,.0f}")
    if mech_lien > 0:  enriched["lien_flags"].append(f"Mechanics: ${mech_lien:,.0f}")
    enriched["lien_flags_str"] = " | ".join(enriched["lien_flags"]) if enriched["lien_flags"] else "None"

    enriched["pr_enriched"] = True
    return enriched


def enrich_batch(properties: list, delay: float = 0.5) -> list:
    """
    Enrich a list of properties with PropertyRadar data.
    Respects rate limits with delay between calls.
    """
    import re  # import here for the re used in enrich_property
    enriched_list = []
    total = len(properties)

    print(f"\n🔍 PropertyRadar enrichment: {total} properties...")

    for i, prop in enumerate(properties):
        print(f"  [{i+1}/{total}] {prop.get('address', 'unknown')}")
        enriched = enrich_property(prop)
        enriched_list.append(enriched)

        if (i + 1) % 10 == 0:
            print(f"  ✓ {i+1}/{total} enriched")

        time.sleep(delay)

    success = sum(1 for p in enriched_list if p.get("pr_enriched"))
    print(f"  ✅ Enrichment complete: {success}/{total} succeeded")
    return enriched_list


def save_enriched(properties: list, date_str: str = None):
    """Save enriched properties to JSONL."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"enriched_{date_str}.jsonl"
    with open(filepath, "w") as f:
        for prop in properties:
            f.write(json.dumps(prop) + "\n")
    print(f"💾 Enriched data saved: {filepath}")
    return filepath


def load_enriched(date_str: str = None) -> list:
    """Load enriched data from JSONL."""
    if not date_str:
        date_str = date.today().isoformat()
    filepath = DATA_DIR / f"enriched_{date_str}.jsonl"
    if not filepath.exists():
        return []
    with open(filepath) as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import re
    # Test with a single known address
    test_prop = {
        "address": "4821 NW 7th Ave, Miami, FL 33127",
        "state": "FL",
        "case_number": "TEST-001",
        "county_name": "Miami-Dade",
        "final_sale_price": 312000,
        "opening_bid": 263800,
    }
    print("Testing PropertyRadar enrichment...")
    result = enrich_property(test_prop)
    print(json.dumps(result, indent=2))
