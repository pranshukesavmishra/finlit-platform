"""Company classification and profile selection, independent of provider I/O."""
import re

def resolve_group(profile):
    text = " ".join(str(profile.get(key) or "") for key in ("industry", "sector", "sub_industry", "macro_sector")).lower()
    rules = [
        ("INSURANCE", r"insurance"), ("NBFC", r"nbfc|non.?bank|housing finance|financial company|finance company"),
        ("BANK", r"\bbanks?\b|banking"), ("REALTY", r"real estate|realty"),
        ("UTILITY", r"power|utilities|telecom|construction|infrastructure"),
        ("HEAVY", r"cement|metal|steel|mining|oil|petroleum|refiner|gas"),
        ("LIGHT", r"software|information technology|\bit -|fmcg|fast moving|pharma|media|entertainment|asset management|brok|exchange|retail|hotel|restaurant|consumer services"),
    ]
    for group, pattern in rules:
        # Vehicle manufacturing is not construction/infrastructure activity.
        # Preserve the precedence of financial groups and real estate.
        if group == "UTILITY" and re.search(r"\bautomobiles?\b|\bauto parts\b|\bvehicles?\b", text):
            return "MFG", False
        if re.search(pattern, text): return group, False
    known_mfg = bool(re.search(r"auto|capital goods|engineering|chemical|textile|defen|hospital|diagnostic|logistic|transport|consumer durable|manufactur|machiner|electrical|industrial", text))
    return "MFG", not known_mfg

def profile_from(raw):
    p = raw.get("profile", {})
    if isinstance(p, list): p = p[0] if p else {}
    if not isinstance(p, dict): return {}
    return p.get("profile", p) if isinstance(p.get("profile", p), dict) else {}
