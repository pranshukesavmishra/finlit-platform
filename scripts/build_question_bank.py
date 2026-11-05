"""Builds site-api/backend/question_bank.json from the Sena / FinLit Predefined Question Bank PDF.
Usage: python3 scripts/build_question_bank.py <path to the PDF>
Every question keeps its own ID (C.1.1.1 ...), its section path, its text and the placeholders it uses; nothing is reworded."""
import json, re, sys
from pathlib import Path

COMPANY40 = Path(__file__).with_name("data") / "company40.json"   # the founder's 40 company questions, with the answer plan and data limits of each

# the company questions the assistant offers as one-tap suggestions on a company page (IDs of the bank; the text is copied from it, never reworded)
SUGGESTED = ["C.2.1.2", "C.2.1.3", "C.2.2.1", "C.2.5.1", "C.3.5.1", "C.5.1.1", "C.6.1.1", "C.7.2.1"]
PREFIX = {"X": "Sector-specific", "C": "Company", "M": "Mutual Fund", "E": "ETF", "F": "FinLit", "S": "Market and Sector", "P": "Screener Presets", "T": "Earnings Call"}
ID = re.compile(r"^([CMEFSPTX])\.(\d+(?:\.\d+)*)\s+(.*)$")
SECTION = re.compile(r"^\d+\. [A-Z][A-Z ,&/\-]+ \([A-Z]\)$")   # "8. SECTOR-SPECIFIC COMPANY QUESTIONS (X)": what follows until the next ID is prose, not a question
FOOT = re.compile(r"^(Sena / FinLit Predeﬁned Question Bank|Sena / FinLit Predefined Question Bank|Page \d+ of \d+)$")

def add_company40(bank_path="site-api/backend/question_bank.json", sug_path="frontend/src/content/questionSuggestions.json", src=COMPANY40):
    """Adds (or refreshes) the founder's 40 company questions: ids C.<section>.Q<n> (n = the question's number 1-40, so they never meet the bank's C.2.1.1 ids),
    in the bank file for the matcher and the assistant's answer plan, and as the grouped 'More questions' list in the suggestions file. Safe to run again."""
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    bank = json.loads(Path(bank_path).read_text(encoding="utf-8"))
    bank["questions"] = [q for q in bank["questions"] if q.get("set") != "company40"]
    for d in data["questions"]:
        q = {"id": d["id"], "text": d["text"], "group": "Company", "path": [d["sectionTitle"]], "placeholders": sorted(set(re.findall(r"\{(\w+)\}", d["text"]))),
             "set": "company40", "n": d["n"], "section": d["section"], "status": d["status"], "covers": d["covers"], "tools": d["tools"], "plan": d["plan"], "limits": d["limits"]}
        for flag in ("lendersOnly", "needsSecondCompany"):
            if d.get(flag): q[flag] = True
        bank["questions"].append(q)
    Path(bank_path).write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    sug = json.loads(Path(sug_path).read_text(encoding="utf-8"))
    sug["groups"] = [{"n": int(n), "title": title, "items": [{k: v for k, v in {"id": d["id"], "text": d["text"], "lendersOnly": d.get("lendersOnly"), "needsSecondCompany": d.get("needsSecondCompany")}.items() if v}
                                                              for d in data["questions"] if d["section"] == int(n)]} for n, title in data["sections"].items()]
    Path(sug_path).write_text(json.dumps(sug, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(data["questions"]), "company questions added in", len(sug["groups"]), "groups")


def main(pdf, out):
    from pypdf import PdfReader
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
    add_company40(out)

if __name__ == "__main__":
    if sys.argv[1:2] == ["--company40"]:      # only refresh the founder's 40 questions in the existing bank
        add_company40(); sys.exit()
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "site-api/backend/question_bank.json")
