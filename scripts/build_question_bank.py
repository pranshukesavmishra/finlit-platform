"""Builds site-api/backend/question_bank.json from the Sena / FinLit Predefined Question Bank PDF.
Usage: python3 scripts/build_question_bank.py <path to the PDF>
Every question keeps its own ID (C.1.1.1 ...), its section path, its text and the placeholders it uses; nothing is reworded."""
import json, re, sys
from pypdf import PdfReader

# the company questions the assistant offers as one-tap suggestions on a company page (IDs of the bank; the text is copied from it, never reworded)
SUGGESTED = ["C.2.1.2", "C.2.1.3", "C.2.2.1", "C.2.5.1", "C.3.5.1", "C.5.1.1", "C.6.1.1", "C.7.2.1"]
PREFIX = {"X": "Sector-specific", "C": "Company", "M": "Mutual Fund", "E": "ETF", "F": "FinLit", "S": "Market and Sector", "P": "Screener Presets", "T": "Earnings Call"}
ID = re.compile(r"^([CMEFSPTX])\.(\d+(?:\.\d+)*)\s+(.*)$")
SECTION = re.compile(r"^\d+\. [A-Z][A-Z ,&/\-]+ \([A-Z]\)$")   # "8. SECTOR-SPECIFIC COMPANY QUESTIONS (X)": what follows until the next ID is prose, not a question
FOOT = re.compile(r"^(Sena / FinLit Predeﬁned Question Bank|Sena / FinLit Predefined Question Bank|Page \d+ of \d+)$")

def main(pdf, out):
    text = "\n".join(p.extract_text() for p in PdfReader(pdf).pages)
    lines = [l.strip() for l in text.splitlines() if l.strip() and not FOOT.match(l.strip())]
    items = []          # (id, text)
    live = False
    for l in lines:
        if SECTION.match(l):
            live = False
            continue
        m = ID.match(l)
        if m:
            items.append([f"{m.group(1)}.{m.group(2)}", m.group(3)]); live = True
        elif items and live:
            items[-1][1] += " " + l
    heads = {}
    qs = []
    for iid, t in items:
        t = re.sub(r"\s+", " ", t).strip()
        depth = iid.count(".") + 1
        if not t.endswith(("?", ".")) and "{" not in t and len(t.split()) <= 8 and "?" not in t:
            heads[iid] = t            # a section heading such as "C.1.1 Identity"
            continue
        qs.append({"id": iid, "text": t})
    for q in qs:
        parts = q["id"].split(".")
        q["group"] = PREFIX[parts[0]]
        q["path"] = [heads[".".join(parts[:k])] for k in range(1, len(parts)) if ".".join(parts[:k]) in heads]
        q["placeholders"] = sorted(set(re.findall(r"\{(\w+)\}", q["text"])))
    json.dump({"source": "Sena / FinLit Predefined Question Bank", "questions": qs}, open(out, "w"), ensure_ascii=False, indent=1)
    by_id = {q["id"]: q for q in qs}
    sug = [{"id": i, "text": by_id[i]["text"]} for i in SUGGESTED if i in by_id]
    json.dump({"company": sug}, open("frontend/src/content/questionSuggestions.json", "w"), ensure_ascii=False, indent=1)
    by = {}
    for q in qs: by[q["group"]] = by.get(q["group"], 0) + 1
    print(len(qs), "questions", by, "| headings", len(heads))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "site-api/backend/question_bank.json")
