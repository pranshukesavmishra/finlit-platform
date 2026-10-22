"""A small streaming .xlsx reader (standard library only): rows come out one at a time, so a 20 MB workbook never sits in memory as objects.

Only what the portfolio files need: sheet names, rows as lists of str/float/None (dates stay serial numbers; callers that need a date read the text).
"""

from __future__ import annotations

import re
import zipfile
from typing import Iterator, List, Optional, Union
from defusedxml.ElementTree import iterparse   # refuses entity-expansion and external-entity tricks in a downloaded file

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
Cell = Union[str, float, None]


def col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


class Workbook:
    def __init__(self, path_or_file):
        self.z = zipfile.ZipFile(path_or_file)
        self.shared: Optional[List[str]] = None
        self.sheets = self._sheets()

    def close(self):
        self.z.close()

    def _sheets(self) -> List[tuple]:
        rels = {}
        for _, el in iterparse(self.z.open("xl/_rels/workbook.xml.rels")):
            if el.tag == PNS + "Relationship":
                rels[el.get("Id")] = el.get("Target")
        out = []
        for _, el in iterparse(self.z.open("xl/workbook.xml")):
            if el.tag == NS + "sheet":
                tgt = rels.get(el.get(RNS + "id"), "")
                tgt = tgt.lstrip("/")
                out.append((el.get("name"), tgt if tgt.startswith("xl/") else "xl/" + tgt))
        return out

    def _strings(self) -> List[str]:
        if self.shared is not None:
            return self.shared
        out: List[str] = []
        if "xl/sharedStrings.xml" in self.z.namelist():
            buf: List[str] = []
            for ev, el in iterparse(self.z.open("xl/sharedStrings.xml"), events=("end",)):
                if el.tag == NS + "t":
                    buf.append(el.text or "")
                elif el.tag == NS + "si":
                    out.append("".join(buf))
                    buf = []
                    el.clear()
        self.shared = out
        return out

    def rows(self, sheet_index: int) -> Iterator[List[Cell]]:
        strings = self._strings()
        path = self.sheets[sheet_index][1]
        row: List[Cell] = []
        for ev, el in iterparse(self.z.open(path), events=("end",)):
            if el.tag == NS + "c":
                i = col_index(el.get("r") or "A1")
                t = el.get("t")
                v = el.find(NS + "v")
                val: Cell = None
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in el.iter(NS + "t"))
                elif v is not None and v.text is not None:
                    if t == "s":
                        val = strings[int(v.text)]
                    elif t in ("str", "e"):
                        val = v.text
                    elif t == "b":
                        val = v.text
                    else:
                        try:
                            val = float(v.text)
                        except ValueError:
                            val = v.text
                while len(row) <= i:
                    row.append(None)
                row[i] = val
                el.clear()
            elif el.tag == NS + "row":
                yield row
                row = []
                el.clear()


def clean(v: Cell) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else repr(v)
    return re.sub(r"\s+", " ", str(v)).strip()
