"""Company classification and profile selection, independent of provider I/O."""
import re

# Bump when the rules below change what a stored report would show. Reports stamped with an older
# version that were NOT RATED because of the classification blocker are recalculated by the nightly job.
CLASSIFICATION_VERSION = 3

# Precedence (first match wins). Financial labels are resolved before UTILITY/HEAVY because FinEdge puts
# "Financial Services" in macro_sector for every financial company, and words such as "infrastructure" or
# "power" appear in lender names ("Infrastructure Finance", "Power Finance").
RULES = [
    ("INSURANCE", r"insurance"),
    ("NBFC", r"nbfc|non.?bank|housing finance|financial company|finance company|infrastructure finance|power finance|micro.?finance|consumer finance|specialized finance|specialised finance|financial institution|gold loan|leasing|lending"),
    ("BANK", r"\bbanks?\b|banking"),
    # Asset-light financial services (fee income, no balance-sheet lending) stay LIGHT.
    ("LIGHT", r"asset management|brok|exchange|capital markets?|depositor|clearing|rating agenc|credit information|registrar|fintech|financial technology|payment"),
    # Generic financial labels (Finance, Financial Services, holding / investment / diversified financial
    # companies such as Bajaj Finserv, whose earnings are dominated by lending and insurance subsidiaries)
    # use the NBFC model: gross/net NPA, capital adequacy fallback, ROA, P/B, P/E, PEG.
    ("NBFC", r"financ|holding compan|investment compan|diversified financial|\bloans?\b"),
    ("REALTY", r"real estate|realty"),
    ("UTILITY", r"power|utilities|telecom|construction|infrastructure"),
    ("HEAVY", r"cement|metal|steel|mining|oil|petroleum|refiner|gas"),
    ("LIGHT", r"software|information technology|\bit -|fmcg|fast moving|pharma|media|entertainment|asset management|brok|exchange|retail|hotel|restaurant|consumer services"),
    # LIGHT/MFG fallbacks for labels that used to fall through are in FALLBACK_RULES, applied after the
    # recognised-manufacturing check so that no previously recognised label changes group.
]

FALLBACK_RULES = [
    # Asset-light trade and services.
    ("LIGHT", r"\bservices?\b|\btrading\b|\btraders?\b|wholesale|distribut|education|\bschools?\b|staffing|consult|advertis|e-?commerce|\bleisure\b|\bonline\b|marketing"),
    # Product businesses with plant and inventory: manufacturing.
    ("MFG", r"agricultur|\bagro|farm|paper|printing|publication|plastic|packag|shipping|\bships?\b|airline|aviation|\bsugar|\btea\b|\bcoffee|fertili[sz]er|jewel|\bgems?\b|food|beverage|tobacco|leather|footwear|apparel|garment|ceramic|glass|rubber|furniture|paint|cable|wire|electronic|appliance|semiconductor|fibre|fiber|yarn|pesticide|agrochemical|fisher|aqua|edible|dairy|\bcotton\b|\bsilk\b|\bwood\b|timber|\bsalt\b|\bpipes?\b|\btyres?\b|battery|batteries|bearing"),
]

# Added in classification version 3 (Coal India and its kind were NOT RATED because their labels matched nothing). Applied only after every rule
# above, so no label that already had a group changes group. Economics: asset-heavy resource and process businesses are HEAVY, networks and
# regulated infrastructure UTILITY, plant-and-inventory product businesses MFG, asset-light trade and services LIGHT.
NEW_FALLBACK_RULES = [
    ("UTILITY", r"renewable|\bsolar\b|\bwind\b|electricity|hydro|\bports?\b|airports?|\bhighways?\b|\btoll\b|railway|communications? sector|\bwater\b"),
    ("HEAVY", r"\bcoal\b|lignite|minerals?|\benergy\b|uranium|petrochem|alumin|\bcopper\b|\bzinc\b|\biron\b|ferro|\balloys?\b|forging|foundr|smelt|forest products"),
    ("MFG", r"health|medical|nursing|clinic|wellness|aerospace|process industries|producer|specialty|\bdyes?\b|pigment|polymer|building products|home furnishings|diversified|conglomerate|multi.?industry|alcohol|liquor|brew|distill|spirits|\bwine|cigarette"),
    ("LIGHT", r"investment managers?|fund (?:manag|advis|house)|mutual fund (?:manag|compan|house)|consumer|household|personal care|cosmetic|travel|tourism|hospitality|gaming|broadcast|cinema|multiplex|television|\bfilms?\b|couriers?|air freight|specialty stores|office equipment"),
]

# Labels the model deliberately does not rate: trusts and funds have no operating business to score. resolve_group still returns
# defaulted=True for them (no model group); unmapped_reason() gives the honest, specific text instead of the generic one.
UNRATED_KINDS = [
    ("trust", r"\breits?\b|\binvits?\b|real estate investment trust|infrastructure investment trust|investment trusts?|business trust"),
    ("fund", r"\betfs?\b|exchange.traded|mutual funds?|\bspacs?\b|special purpose acquisition|closed.?end|\bfunds?\b"),
]
UNRATED_TEXT = {
    "trust": "Trusts (REITs, InvITs) are not rated by this model, which scores operating companies.",
    "fund": "Funds, ETFs and SPACs are not rated by this model, which scores operating companies.",
}


def _profile_text(profile):
    return " ".join(str(profile.get(key) or "") for key in ("industry", "sector", "sub_industry", "macro_sector")).lower()


def unrated_kind(profile):
    """'trust' or 'fund' for an instrument the model intentionally does not rate, else None. Checked before the group rules."""
    text = _profile_text(profile)
    if re.search(r"asset management|investment managers?|fund (?:manag|advis|house)|mutual fund (?:manag|compan|house)", text): return None
    for kind, pattern in UNRATED_KINDS:
        if re.search(pattern, text): return kind
    return None


def unmapped_reason(profile):
    """The plain-language reason for a company that has no model group: the inputs were fine, the industry rules are the gap."""
    kind = unrated_kind(profile)
    label = label_text(profile) or str(profile.get("macro_sector") or "").strip() or "none given"
    if kind: return f'Prism has no model group for this instrument ("{label}"): {UNRATED_TEXT[kind]}'
    return (f'Prism has no model group for this industry yet ("{label}"). The inputs were available; '
            "the rating needs the industry rules extended, so the overall rating is withheld until then.")


def resolve_group(profile):
    text = _profile_text(profile)
    if unrated_kind(profile): return "MFG", True
    for group, pattern in RULES:
        # Vehicle manufacturing is not construction/infrastructure activity.
        # Preserve the precedence of financial groups and real estate.
        if group == "UTILITY" and re.search(r"\bautomobiles?\b|\bauto parts\b|\bvehicles?\b", text):
            return "MFG", False
        if re.search(pattern, text): return group, False
    if re.search(r"auto|capital goods|engineering|chemical|textile|defen|hospital|diagnostic|logistic|transport|consumer durable|manufactur|machiner|electrical|industrial", text):
        return "MFG", False
    for group, pattern in FALLBACK_RULES + NEW_FALLBACK_RULES:
        if re.search(pattern, text): return group, False
    return "MFG", True


def label_text(profile):
    """The company's own classification labels for display: distinct industry / sector / sub-industry values."""
    seen = []
    for key in ("industry", "sector", "sub_industry"):
        value = str(profile.get(key) or "").strip()
        if value and value.lower() not in [v.lower() for v in seen]:
            seen.append(value)
    return " / ".join(seen) or str(profile.get("macro_sector") or "").strip()

def profile_from(raw):
    p = raw.get("profile", {})
    if isinstance(p, list): p = p[0] if p else {}
    if not isinstance(p, dict): return {}
    return p.get("profile", p) if isinstance(p.get("profile", p), dict) else {}
