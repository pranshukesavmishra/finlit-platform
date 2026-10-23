"""A small reader for the old Excel format (.xls, BIFF8 inside an OLE2 container), standard library only.

Some fund houses still publish their monthly portfolio as .xls (Aditya Birla Sun Life: one 8 MB workbook, about 100 sheets). Only cell values are read:
text, numbers, RK numbers and formula results; formatting, dates-as-text and charts are ignored. The workbook stream is held in memory once (8 MB),
sheets are read one at a time.
"""

from __future__ import annotations

import struct
from typing import Dict, Iterator, List, Optional, Tuple, Union

Cell = Union[str, float, None]
FREESECT, ENDOFCHAIN = 0xFFFFFFFF, 0xFFFFFFFE


class XlsError(ValueError):
    pass


def _ole_stream(data: bytes, want: Tuple[str, ...] = ("Workbook", "Book")) -> bytes:
    if data[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
        raise XlsError("not an OLE2 compound file")
    shift = struct.unpack_from("<H", data, 30)[0]
    mini_shift = struct.unpack_from("<H", data, 32)[0]
    ssz, msz = 1 << shift, 1 << mini_shift
    n_fat = struct.unpack_from("<I", data, 44)[0]
    dir_start = struct.unpack_from("<I", data, 48)[0]
    mini_cutoff = struct.unpack_from("<I", data, 56)[0]
    minifat_start = struct.unpack_from("<I", data, 60)[0]
    difat_start = struct.unpack_from("<I", data, 68)[0]
    n_difat = struct.unpack_from("<I", data, 72)[0]

    def sector(i: int) -> bytes:
        off = (i + 1) * ssz
        return data[off:off + ssz]

    difat = list(struct.unpack_from("<109I", data, 76))
    s = difat_start
    for _ in range(n_difat):
        if s in (FREESECT, ENDOFCHAIN):
            break
        blk = struct.unpack_from(f"<{ssz // 4}I", sector(s))
        difat.extend(blk[:-1])
        s = blk[-1]
    fat: List[int] = []
    for fs in difat[:n_fat]:
        if fs in (FREESECT, ENDOFCHAIN):
            continue
        fat.extend(struct.unpack_from(f"<{ssz // 4}I", sector(fs)))

    def chain(start: int) -> List[int]:
        out, seen = [], set()
        while start not in (ENDOFCHAIN, FREESECT) and start < len(fat) and start not in seen:
            seen.add(start)
            out.append(start)
            start = fat[start]
        return out

    dirdata = b"".join(sector(i) for i in chain(dir_start))
    entries = []
    for off in range(0, len(dirdata) - 127, 128):
        nlen = struct.unpack_from("<H", dirdata, off + 64)[0]
        name = dirdata[off:off + max(nlen - 2, 0)].decode("utf-16-le", "ignore")
        typ = dirdata[off + 66]
        start = struct.unpack_from("<I", dirdata, off + 116)[0]
        size = struct.unpack_from("<Q", dirdata, off + 120)[0] & 0xFFFFFFFF
        entries.append((name, typ, start, size))
    root = next((e for e in entries if e[1] == 5), None)
    target = next((e for e in entries if e[0] in want and e[1] == 2), None)
    if target is None:
        raise XlsError("no Workbook stream")
    name, _, start, size = target
    if size >= mini_cutoff:
        return b"".join(sector(i) for i in chain(start))[:size]
    # small stream: lives in the mini stream
    if root is None:
        raise XlsError("no root entry")
    mini_stream = b"".join(sector(i) for i in chain(root[2]))
    mini_fat: List[int] = []
    for i in chain(minifat_start):
        mini_fat.extend(struct.unpack_from(f"<{ssz // 4}I", sector(i)))
    out, c, seen = [], start, set()
    while c not in (ENDOFCHAIN, FREESECT) and c < len(mini_fat) and c not in seen:
        seen.add(c)
        out.append(mini_stream[c * msz:(c + 1) * msz])
        c = mini_fat[c]
    return b"".join(out)[:size]


def _rk(v: int) -> float:
    if v & 2:
        x = float(v >> 2) if not (v & 0x80000000) else float(((v >> 2) - (1 << 30)))
        # integer RK: signed 30-bit
        x = float(struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFC))[0] >> 2)
    else:
        x = struct.unpack("<d", struct.pack("<Q", (v & 0xFFFFFFFC) << 32))[0]
    return x / 100.0 if v & 1 else x


class _Rec:
    """The workbook stream cut into records, CONTINUE records kept attached."""

    def __init__(self, buf: bytes):
        self.buf = buf

    def iter_from(self, pos: int) -> Iterator[Tuple[int, bytes, List[bytes]]]:
        buf, n = self.buf, len(self.buf)
        while pos + 4 <= n:
            rid, ln = struct.unpack_from("<HH", buf, pos)
            body = buf[pos + 4:pos + 4 + ln]
            pos += 4 + ln
            conts: List[bytes] = []
            while pos + 4 <= n and struct.unpack_from("<H", buf, pos)[0] == 0x3C:
                cl = struct.unpack_from("<H", buf, pos + 2)[0]
                conts.append(buf[pos + 4:pos + 4 + cl])
                pos += 4 + cl
            yield rid, body, conts
            if rid == 0x0A:
                return


def _read_string(chunks: List[bytes], ci: int, off: int, nchars: int, flags: int) -> Tuple[str, int, int]:
    """Read nchars characters of an XLUnicodeString body starting at chunks[ci][off] (after the flag byte); handles continue-boundary flag bytes."""
    out: List[str] = []
    wide = bool(flags & 1)
    remaining = nchars
    while remaining > 0:
        chunk = chunks[ci]
        if off >= len(chunk):
            ci += 1
            if ci >= len(chunks):
                break
            chunk, off = chunks[ci], 0
            wide = bool(chunk[0] & 1)
            off = 1
        width = 2 if wide else 1
        take = min(remaining, (len(chunk) - off) // width)
        raw = chunk[off:off + take * width]
        out.append(raw.decode("utf-16-le" if wide else "latin-1", "replace"))
        off += take * width
        remaining -= take
    return "".join(out), ci, off


def _sst(body: bytes, conts: List[bytes]) -> List[str]:
    chunks = [body] + conts
    total, uniq = struct.unpack_from("<II", body, 0)
    strings: List[str] = []
    ci, off = 0, 8
    while len(strings) < uniq:
        chunk = chunks[ci]
        if off + 3 > len(chunk):
            ci += 1
            if ci >= len(chunks):
                break
            off = 0
            chunk = chunks[ci]
            if off + 3 > len(chunk):
                break
        nchars = struct.unpack_from("<H", chunk, off)[0]
        flags = chunk[off + 2]
        off += 3
        runs = ext = 0
        if flags & 8:
            runs = struct.unpack_from("<H", chunk, off)[0]
            off += 2
        if flags & 4:
            ext = struct.unpack_from("<I", chunk, off)[0]
            off += 4
        s, ci, off = _read_string(chunks, ci, off, nchars, flags)
        skip = runs * 4 + ext
        while skip > 0 and ci < len(chunks):
            avail = len(chunks[ci]) - off
            if skip <= avail:
                off += skip
                skip = 0
            else:
                skip -= avail
                ci += 1
                off = 0
        strings.append(s)
    return strings


class XlsWorkbook:
    def __init__(self, path_or_bytes):
        data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
        self.rec = _Rec(_ole_stream(bytes(data)))
        del data
        self.sheets: List[Tuple[str, int]] = []
        self.shared: List[str] = []
        self._globals()

    def close(self):
        self.rec = None  # type: ignore

    def _globals(self):
        first = True
        for rid, body, conts in self.rec.iter_from(0):
            if rid == 0x0809 and not first:
                break
            first = False
            if rid == 0x0085:
                off = struct.unpack_from("<I", body, 0)[0]
                nlen, fl = body[6], body[7]
                nm = body[8:8 + nlen * (2 if fl & 1 else 1)].decode("utf-16-le" if fl & 1 else "latin-1", "replace")
                if body[5] == 0:   # worksheet
                    self.sheets.append((nm, off))
            elif rid == 0x00FC:
                self.shared = _sst(body, conts)

    def rows(self, sheet_index: int) -> Iterator[List[Cell]]:
        pos = self.sheets[sheet_index][1]
        cells: Dict[int, Dict[int, Cell]] = {}
        pending: Optional[Tuple[int, int]] = None
        started = False
        for rid, body, conts in self.rec.iter_from(pos):
            if rid == 0x0809:
                if started:
                    break
                started = True
                continue
            if rid == 0x00FD:
                r, c, _, idx = struct.unpack_from("<HHHI", body, 0)
                if idx < len(self.shared):
                    cells.setdefault(r, {})[c] = self.shared[idx]
            elif rid == 0x0203:
                r, c, _, v = struct.unpack_from("<HHHd", body, 0)
                cells.setdefault(r, {})[c] = v
            elif rid == 0x027E:
                r, c, _, v = struct.unpack_from("<HHHI", body, 0)
                cells.setdefault(r, {})[c] = _rk(v)
            elif rid == 0x00BD:
                r, c0 = struct.unpack_from("<HH", body, 0)
                c1 = struct.unpack_from("<H", body, len(body) - 2)[0]
                for k, c in enumerate(range(c0, c1 + 1)):
                    v = struct.unpack_from("<I", body, 4 + k * 6 + 2)[0]
                    cells.setdefault(r, {})[c] = _rk(v)
            elif rid == 0x0204:
                r, c, _, ln = struct.unpack_from("<HHHH", body, 0)
                fl = body[8]
                cells.setdefault(r, {})[c] = body[9:9 + ln * (2 if fl & 1 else 1)].decode("utf-16-le" if fl & 1 else "latin-1", "replace")
            elif rid == 0x0006:
                r, c = struct.unpack_from("<HH", body, 0)
                if body[12:14] == b"\xff\xff":
                    if body[6] == 0:
                        pending = (r, c)
                else:
                    cells.setdefault(r, {})[c] = struct.unpack_from("<d", body, 6)[0]
            elif rid == 0x0207 and pending:
                ln = struct.unpack_from("<H", body, 0)[0]
                fl = body[2]
                cells.setdefault(pending[0], {})[pending[1]] = body[3:3 + ln * (2 if fl & 1 else 1)].decode("utf-16-le" if fl & 1 else "latin-1", "replace")
                pending = None
        for r in sorted(cells):
            row = cells[r]
            out: List[Cell] = [None] * (max(row) + 1)
            for c, v in row.items():
                out[c] = v
            yield out
