"""
SurplusIQ — County Configuration (v3)
Single source of truth for all 10 counties.
Fields marked [VA TO VERIFY] need confirmation from Loom video audit.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CountyConfig:
    # Identity
    id:              str
    name:            str
    state:           str
    state_full:      str

    # Auction platform
    auction_url:     str
    auction_platform: str
    auction_results_pattern: str = ""

    # Clerk / docket
    clerk_url:       str = ""
    clerk_system:    str = ""
    case_format:     str = ""
    case_search_method: Literal["paste_full", "split_fields", "paste_with_dashes"] = "paste_full"

    # Tax deed portal (separate from clerk)
    tax_deed_url:    str = ""
    tax_deed_system: str = ""

    # Quirks
    has_captcha:     bool = False
    vpn_blocked:     bool = False
    doc_timing_days: int = 10

    # Sale schedule
    sale_days:       list = field(default_factory=list)
    mortgage_tax_separated: bool = False

    # Ohio two-tier
    is_two_tier:     bool = False
    debt_lookup_method: str = ""

    # Resources
    recorder_url:    str = ""
    claim_form_url:  str = ""
    excess_funds_list_url: str = ""

    # Lead types
    lead_types:      list = field(default_factory=lambda: ["Mortgage Foreclosure"])
    notes:           str = ""


# ═══════════════════════════════════════════════════════════════════════
# FLORIDA
# ═══════════════════════════════════════════════════════════════════════

MIAMI_DADE = CountyConfig(
    id="miami-dade-fl", name="Miami-Dade", state="FL", state_full="Florida",
    auction_url="https://miami-dade.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://www2.miamidadeclerk.gov/ocs/Search.aspx",
    clerk_system="oscar",
    case_format=r"\d{4}-[A-Z]{2,4}-\d{4,}",
    case_search_method="split_fields",
    tax_deed_url="https://miamidade.realtdm.com/public/cases",
    tax_deed_system="realtdm",
    doc_timing_days=14,
    lead_types=["Mortgage Foreclosure", "Tax Deed", "HOA Foreclosure"],
    notes=(
        "Case # split into 3 fields (year + sequence + code). "
        "CA = mortgage, CC = HOA. Tax deeds use RealTDM portal. "
        "Doc timing 10-14 days. PIR contains lien list."
    ),
)

BROWARD = CountyConfig(
    id="broward-fl", name="Broward", state="FL", state_full="Florida",
    auction_url="https://broward.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://www.browardclerk.org/Web2/CaseSearchECA/Search",
    clerk_system="broward_web2",
    case_format=r"\d{4}-[A-Z]{2,4}-\d{4,}",
    case_search_method="paste_full",
    has_captcha=True,
    doc_timing_days=7,
    mortgage_tax_separated=True,
    lead_types=["Mortgage Foreclosure", "Tax Deed"],
    notes=(
        "CAPTCHA on clerk. Can paste full case number. "
        "Tax sales on separate calendar. Watch 'motion to vacate'. "
        "Large surpluses filed fast — prioritize."
    ),
)

DUVAL = CountyConfig(
    id="duval-fl", name="Duval", state="FL", state_full="Florida",
    auction_url="https://duval.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://core.duvalclerk.com/CoreCivil/CaseSearch",
    clerk_system="core_duval",
    case_format=r"\d{4}-[A-Z]{2,4}-\d{4,}",
    case_search_method="paste_full",
    tax_deed_url="",  # [VA TO VERIFY]
    tax_deed_system="duval_taxdeed",
    doc_timing_days=5,
    mortgage_tax_separated=True,
    lead_types=["Mortgage Foreclosure", "Tax Deed"],
    notes=(
        "Mortgage + tax calendars separated. CORE clerk portal. "
        "Has Title Express OE Report for tax deed liens. "
        "Can paste full case number."
    ),
)

LEE = CountyConfig(
    id="lee-fl", name="Lee", state="FL", state_full="Florida",
    auction_url="https://lee.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="",  # [VA TO VERIFY]
    clerk_system="lee_portal",
    case_format=r"\d{4}-[A-Z]{2,4}-\d{4,}",
    case_search_method="paste_full",
    has_captcha=True,
    doc_timing_days=7,
    lead_types=["Mortgage Foreclosure", "Tax Deed"],
    notes="CAPTCHA flagged by Eric. [VA TO VERIFY clerk URL from Loom]",
)

ORANGE = CountyConfig(
    id="orange-fl", name="Orange", state="FL", state_full="Florida",
    auction_url="https://orange.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://myeclerk.myorangeclerk.com/Cases/Search",
    clerk_system="orange_eclerk",
    case_format=r"\d{4}-[A-Z]{2,4}-\d{4,}",
    case_search_method="paste_full",
    tax_deed_url="https://www.occompt.com/taxdeeds",
    tax_deed_system="orange_comptroller",
    has_captcha=True,
    vpn_blocked=True,
    doc_timing_days=2,
    mortgage_tax_separated=True,
    lead_types=["Mortgage Foreclosure", "Tax Deed"],
    notes=(
        "VPN MUST BE OFF. CAPTCHA present. "
        "Fastest doc posting (2 days). "
        "Tax deeds via Comptroller — 'Active Overbid' status. "
        "View Claims shows Notice of Surplus + claim form."
    ),
)

# ═══════════════════════════════════════════════════════════════════════
# OHIO — all two-tier
# ═══════════════════════════════════════════════════════════════════════

CUYAHOGA = CountyConfig(
    id="cuyahoga-oh", name="Cuyahoga", state="OH", state_full="Ohio",
    auction_url="https://cuyahoga.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://cpdocket.cp.cuyahogacounty.us/Search.aspx",
    clerk_system="cuyahoga_docket",
    case_format=r"CV\d{2}\d{6,}",
    case_search_method="paste_with_dashes",
    has_captcha=True,
    is_two_tier=True,
    debt_lookup_method="prayer_amount",
    doc_timing_days=10,
    sale_days=["monday", "wednesday"],
    mortgage_tax_separated=True,
    lead_types=["Mortgage Foreclosure", "Tax Deed"],
    notes=(
        "TWO-TIER: opening bid = 2/3 appraised value, NOT debt. "
        "Search docket for 'prayer amount' for actual debt. "
        "Mondays = mortgage, Wednesdays = tax. "
        "Has public spreadsheet of excess funds [VA TO FIND URL]."
    ),
)

FRANKLIN = CountyConfig(
    id="franklin-oh", name="Franklin", state="OH", state_full="Ohio",
    auction_url="https://franklin.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://fcdcfcjs.co.franklin.oh.us/CaseInformationOnline/caseSearch",
    clerk_system="franklin_fcjs",
    case_format=r"\d{2}CV\d{6,}",
    case_search_method="paste_full",
    is_two_tier=True,
    debt_lookup_method="judgment_search",
    doc_timing_days=10,
    lead_types=["Mortgage Foreclosure"],
    notes=(
        "TWO-TIER. Franklin posts 'Notice of Excess Proceeds' when "
        "surplus exists — cleanest Ohio county. "
        "Search docket for 'judgment' keyword to find debt. "
        "Public list of $7.3M+ held excess proceeds."
    ),
)

MONTGOMERY = CountyConfig(
    id="montgomery-oh", name="Montgomery", state="OH", state_full="Ohio",
    auction_url="https://montgomery.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://www.mcohio.org/government/elected_officials/clerk_of_courts/civil_division/case_search.php",
    clerk_system="montgomery_clerk",
    case_format=r"\d{4}-CV-\d{4,}",
    case_search_method="paste_full",
    is_two_tier=True,
    debt_lookup_method="judgment_search",
    doc_timing_days=10,
    sale_days=["friday"],
    lead_types=["Mortgage Foreclosure"],
    notes=(
        "TWO-TIER. Sales ONLY Fridays. Must agree to T&C before search. "
        "Public excess funds list ($5.8M held). "
        "Posts 'notice of excess funds' document."
    ),
)

SUMMIT = CountyConfig(
    id="summit-oh", name="Summit", state="OH", state_full="Ohio",
    auction_url="https://summit.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://www.summitcountyclerk.com/civil-case-search",
    clerk_system="summit_clerk",
    case_format=r"CV-\d{4}-\d{2}-\d{4,}",
    case_search_method="split_fields",
    is_two_tier=True,
    debt_lookup_method="judgment_search",
    doc_timing_days=10,
    lead_types=["Mortgage Foreclosure"],
    notes=(
        "TWO-TIER. Weird format: CV-YYYY-##-####. Must split fields. "
        "Unclaimed funds sent to state. Has own excess funds list."
    ),
)

HAMILTON = CountyConfig(
    id="hamilton-oh", name="Hamilton", state="OH", state_full="Ohio",
    auction_url="https://hamilton.realforeclose.com",
    auction_platform="realforeclose",
    clerk_url="https://courtclerk.org/records-search",
    clerk_system="hamilton_clerk",
    case_format=r"[A-Z]\d{7,}",
    case_search_method="paste_full",
    has_captcha=True,
    is_two_tier=True,
    debt_lookup_method="propertyradar_fallback",
    doc_timing_days=10,
    sale_days=["twice_per_month"],
    lead_types=["Mortgage Foreclosure"],
    notes=(
        "TWO-TIER. CAPTCHA required. Sales twice per month. "
        "CRITICAL: docket documents NOT LABELED — click each one. "
        "Eric's advice: skip docket parsing, use PropertyRadar to "
        "compare sale price vs original principal. "
        "Use excess funds list for older leads."
    ),
)

# ═══════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════

ALL_COUNTIES = [
    MIAMI_DADE, BROWARD, DUVAL, LEE, ORANGE,
    CUYAHOGA, FRANKLIN, MONTGOMERY, SUMMIT, HAMILTON,
]
FL_COUNTIES = [c for c in ALL_COUNTIES if c.state == "FL"]
OH_COUNTIES = [c for c in ALL_COUNTIES if c.state == "OH"]
COUNTY_BY_ID = {c.id: c for c in ALL_COUNTIES}
CAPTCHA_COUNTIES = [c.id for c in ALL_COUNTIES if c.has_captcha]


def get_county(county_id: str) -> CountyConfig:
    return COUNTY_BY_ID[county_id]


def needs_verification(county: CountyConfig) -> list:
    gaps = []
    if not county.clerk_url:               gaps.append("clerk_url")
    if county.state == "FL" and county.mortgage_tax_separated and not county.tax_deed_url:
        gaps.append("tax_deed_url")
    if county.state == "OH" and not county.excess_funds_list_url:
        gaps.append("excess_funds_list_url")
    return gaps


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  SurplusIQ County Configuration")
    print("="*70)
    print(f"\nTotal: {len(ALL_COUNTIES)} | FL: {len(FL_COUNTIES)} | OH: {len(OH_COUNTIES)}")
    print(f"CAPTCHA: {len(CAPTCHA_COUNTIES)} counties")
    print(f"\n{'County':<15} {'Flags':<22} {'Status'}")
    print("-"*70)
    for c in ALL_COUNTIES:
        gaps = needs_verification(c)
        flags = []
        if c.has_captcha: flags.append("CAPTCHA")
        if c.vpn_blocked: flags.append("NO-VPN")
        if c.is_two_tier: flags.append("2-TIER")
        flag_str = ",".join(flags) if flags else "-"
        status = "✅" if not gaps else f"⚠️  {','.join(gaps)}"
        print(f"  {c.state} {c.name:<12} {flag_str:<22} {status}")
