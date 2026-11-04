"""Keeps a folder of NSE's daily files current: the input of NseHistory (nse.py) and the sector engine.

    python -m finlit_technicals fetch-nse --dir /srv/finlit/nse          # first run ~40 min, then a minute a day

Run it once a day after 7 pm IST (NSE publishes the day's files in the evening). It skips what it already has, so
an interrupted run is simply run again. What it keeps in --dir:
    bhav/<year>/<yyyymmdd>.csv.gz, bhav_<year>.csv.gz   every security NSE's cash market traded each day (2016 on)
    idx/<year>/<yyyymmdd>.csv.gz,  idx_<year>.csv.gz    the close of every NSE index
    ref/EQUITY_L.csv, ref/symbolchange.csv, ref/namechange.csv
    ref/corporate_actions.txt   splits, bonuses, rights and demergers newer than the bundled list (NSE's website)
    ref/industries_extra.json   NSE industry of new listings missing from the bundled list (NSE's website)
    amfi/<yyyy>H<n>.xlsx        AMFI's half-yearly average market caps
    fetch_log.txt
The archive files come from nsearchives.nseindia.com and AMFI. Corporate actions and industries come from NSE's
website API, which sometimes refuses scripts; when it does, the run says so and the rest still works (splits are
then caught from the price gap only when no price band allows the move).

Standard library only. Nothing is sent anywhere.
"""
import argparse
import http.cookiejar
import json
import re
import csv
import datetime as dt
import gzip
import io
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path.cwd()            # set from --dir by main()
ARCH = "https://nsearchives.nseindia.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
START = dt.date(2016, 1, 1)
OLD_LAST = dt.date(2024, 7, 5)          # last day of NSE's old bhavcopy format
UDIFF_FIRST = dt.date(2024, 1, 1)       # the new (UDiFF) format is also published for 2024's first half
FULL_FIRST = dt.date(2020, 1, 1)        # sec_bhavdata_full files start in 2020
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "last", "prev_close",
        "volume", "value", "trades"]
OLD_MAP = {"TIMESTAMP": "date", "SYMBOL": "symbol", "SERIES": "series", "ISIN": "isin", "OPEN": "open",
           "HIGH": "high", "LOW": "low", "CLOSE": "close", "LAST": "last", "PREVCLOSE": "prev_close",
           "TOTTRDQTY": "volume", "TOTTRDVAL": "value", "TOTALTRADES": "trades"}
UDIFF_MAP = {"TRADDT": "date", "TCKRSYMB": "symbol", "SCTYSRS": "series", "ISIN": "isin", "OPNPRIC": "open",
             "HGHPRIC": "high", "LWPRIC": "low", "CLSPRIC": "close", "LASTPRIC": "last",
             "PRVSCLSGPRIC": "prev_close", "TTLTRADGVOL": "volume", "TTLTRFVAL": "value",
             "TTLNBOFTXSEXCTD": "trades"}
FULL_MAP = {"DATE1": "date", "SYMBOL": "symbol", "SERIES": "series", "OPEN_PRICE": "open", "HIGH_PRICE": "high",
            "LOW_PRICE": "low", "CLOSE_PRICE": "close", "LAST_PRICE": "last", "PREV_CLOSE": "prev_close",
            "TTL_TRD_QNTY": "volume", "TURNOVER_LACS": "value_lacs", "NO_OF_TRADES": "trades"}

REF = {
    "EQUITY_L.csv": ARCH + "/content/equities/EQUITY_L.csv",
    "symbolchange.csv": ARCH + "/content/equities/symbolchange.csv",
    "namechange.csv": ARCH + "/content/equities/namechange.csv",
}
_A = "https://www.amfiindia.com/Themes/Theme1/downloads/"
AMFI = {
    "2017H2": _A + "Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jul-Dec%202017.xlsx",
    "2018H1": _A + "Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jan-June%202018.xlsx",
    "2018H2": _A + "Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20Jul-Dec%202018.xlsx",
    "2019H1": _A + "Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jan-June%202019.xlsx",
    "2019H2": _A + "Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20Jul-Dec%202019.xlsx",
    "2020H1": _A + "Average%20Market%20Capitalization%20of%20Listed%20Companies%20during%20Jan%20-%20Jun%202020_Final.xlsx",
    "2020H2": _A + "Average%20Market%20Capitalization%20of%20Listed%20Companies%20during%20Jul%20-%20Dec%202020_Final.xlsx",
    "2021H1": _A + "Average%20Market%20Capitalization%20of%20List%20Companies%20during%20Jan-June%202021.xlsx",
    "2021H2": _A + "Average%20Market%20Capitalisation%20of%20Listed%20Companies%20during%20Jul%20-%20Dec%202021.xlsx",
    "2022H1": _A + "AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended30June2022.xlsx",
    "2022H2": _A + "AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2022.xlsx",
    "2023H1": _A + "AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended30Jun2023.xlsx",
    "2023H2": _A + "AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2023.xlsx",
    "2024H1": "https://www.amfiindia.com/uploads/Average_Market_Capitalization_30_Jun2024_2a1ab4c1d8.xlsx",
    "2024H2": _A + "AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2024.xlsx",
    "2025H1": _A + "AverageMarketCapitalization30Jun2025.xlsx",
    "2025H2": _A + "AverageMarketCapitalization31Dec2025.xlsx",
    "2026H1": "https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.xlsx",
}

LOG = None


def log(msg, also_print=True):
    line = time.strftime("%H:%M:%S ") + msg
    if also_print:
        print(line, flush=True)
    if LOG:
        LOG.write(line + "\n")
        LOG.flush()


# ---------------------------------------------------------------------------------------------- downloading
class Fetcher:
    """GET with a browser-like header, polite pacing and retries. Falls back to the Mac's own curl when Python
    cannot verify NSE's certificate (a python.org install without its certificates)."""

    def __init__(self, delay=0.3):
        self.delay = delay
        self.use_curl = False
        self.last = 0.0
        try:
            import certifi  # noqa: F401  (present in Anaconda)
            self.ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:      # noqa: BLE001
            self.ctx = ssl.create_default_context()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.ctx),
                                                  urllib.request.HTTPCookieProcessor(self.jar))
        self.cookie_file = None

    def _pace(self):
        wait = self.delay - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()

    def _urllib(self, url, referer):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": referer,
                                                   "Accept-Language": "en-US,en;q=0.9"})
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def _curl(self, url, referer):
        fd, tmp = tempfile.mkstemp()
        os.close(fd)
        try:
            if self.cookie_file is None:
                fd2, self.cookie_file = tempfile.mkstemp()
                os.close(fd2)
            p = subprocess.run(["curl", "-sS", "-L", "--max-time", "60", "-A", UA, "-e", referer,
                                "-b", self.cookie_file, "-c", self.cookie_file,
                                "-o", tmp, "-w", "%{http_code}", url], capture_output=True, text=True, timeout=90)
            code = int((p.stdout or "0").strip()[-3:] or 0)
            if code == 0:
                raise OSError(p.stderr.strip() or "curl failed")
            return code, Path(tmp).read_bytes()
        finally:
            os.remove(tmp)

    def get(self, url, referer="https://www.nseindia.com/"):
        """Returns (status, body). Retries network errors and 403/429/5xx with growing waits."""
        waits = [5, 15, 45, 90, 180]
        for attempt in range(len(waits) + 1):
            self._pace()
            try:
                if self.use_curl:
                    code, body = self._curl(url, referer)
                else:
                    code, body = self._urllib(url, referer)
            except ssl.SSLError as e:
                if not self.use_curl and shutil.which("curl"):
                    log(f"Python could not check the site's certificate ({e.__class__.__name__}); using curl instead.")
                    self.use_curl = True
                    continue
                code, body = -1, str(e).encode()
            except Exception as e:      # timeouts, resets
                if isinstance(getattr(e, "reason", None), ssl.SSLError) and not self.use_curl and shutil.which("curl"):
                    log("Python could not check the site's certificate; using curl instead.")
                    self.use_curl = True
                    continue
                code, body = -1, str(e).encode()
            if code in (200, 404):
                return code, body
            if attempt < len(waits):
                log(f"  {url.rsplit('/', 1)[-1]}: got {code}, waiting {waits[attempt]}s and trying again", False)
                time.sleep(waits[attempt])
        return code, body


# ---------------------------------------------------------------------------------------------- parsing
def _num(x):
    x = (x or "").strip()
    if x in ("", "-", "NA", "nan"):
        return ""
    try:
        return repr(float(x.replace(",", "")))
    except ValueError:
        return ""


class StaleFile(ValueError):
    """NSE returned another day's file (it does this on holidays)."""


def parse(body, kind, day):
    """Bhavcopy bytes (zip or csv) -> list of rows in COLS order."""
    if kind in ("old", "udiff"):
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
            text = z.read(name).decode("utf-8", "replace")
        cmap = OLD_MAP if kind == "old" else UDIFF_MAP
    else:
        text = body.decode("utf-8", "replace")
        cmap = FULL_MAP
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().upper() for h in next(rd)]
    idx = {cmap[h]: i for i, h in enumerate(head) if h in cmap}
    need = {"symbol", "series", "open", "high", "low", "close", "prev_close", "volume"}
    if not need <= set(idx):
        raise ValueError(f"unexpected columns {head}")
    out = []
    for r in rd:
        if len(r) < len(head) - 2 or not r[idx["symbol"]].strip():
            continue
        if kind == "full" and "date" in idx and not out:
            try:
                fd = dt.datetime.strptime(r[idx["date"]].strip().title(), "%d-%b-%Y").date()
            except ValueError:
                fd = day
            if fd != day:
                raise StaleFile(f"file is for {fd}")
        g = lambda k: r[idx[k]].strip() if k in idx and idx[k] < len(r) else ""   # noqa: E731
        if kind == "udiff" and g("series") == "" and "FININSTRMTP" in head:
            continue
        value = _num(g("value"))
        if kind == "full":
            lacs = _num(g("value_lacs"))
            value = repr(float(lacs) * 1e5) if lacs else ""
        out.append([day.isoformat(), g("symbol"), g("series"), g("isin"), _num(g("open")), _num(g("high")),
                    _num(g("low")), _num(g("close")), _num(g("last")), _num(g("prev_close")),
                    _num(g("volume")), value, _num(g("trades"))])
    return out


def urls_for(day):
    old = f"{ARCH}/content/historical/EQUITIES/{day.year}/{MONTHS[day.month - 1]}/cm{day.day:02d}{MONTHS[day.month - 1]}{day.year}bhav.csv.zip"
    udiff = f"{ARCH}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    full = f"{ARCH}/products/content/sec_bhavdata_full_{day:%d%m%Y}.csv"
    if day <= OLD_LAST:
        order = [("old", old)]
        if day >= UDIFF_FIRST:
            order.append(("udiff", udiff))
    else:
        order = [("udiff", udiff)]
    if day >= FULL_FIRST:
        order.append(("full", full))
    if day.weekday() >= 5:                 # weekends: special sessions only, so one try is enough
        order = order[:1]
    return order


def looks_valid(body, kind):
    if kind in ("old", "udiff"):
        return body[:2] == b"PK"
    return body[:40].upper().lstrip().startswith(b"SYMBOL")


# ---------------------------------------------------------------------------------------------- steps
def fetch_days(f, start, end):
    root = HERE / "bhav"
    root.mkdir(exist_ok=True)
    nos_file = root / "_no_session.txt"
    no_session = set(nos_file.read_text().split()) if nos_file.exists() else set()
    # Trading days dhan_alerts already knows (the Nifty 50's calendar): never written off as holidays.
    cal_file = HERE.parent / "data" / "prices" / "_CALENDAR.csv"
    known = set()
    if cal_file.exists():
        with open(cal_file) as c:
            known = {line.split(",", 1)[0] for line in c if line[:2] in ("19", "20")}
    no_session -= known
    days = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    # FinLit patch: a server that was given only the joined year files (bhav_<year>.csv.gz, not the bhav/<year>/ day files) must not fetch ten years again.
    # A day inside a joined file is done; a day before the last month that is missing from them was a weekend or holiday.
    joined = joined_dates("bhav")
    if joined:
        horizon = (dt.date.fromisoformat(max(joined)) - dt.timedelta(days=30)).isoformat()
        no_session |= {d.isoformat() for d in days if d.isoformat() <= horizon and d.isoformat() not in joined}
    todo = [d for d in days if d.isoformat() not in no_session and d.isoformat() not in joined
            and not (root / str(d.year) / f"{d:%Y%m%d}.csv.gz").exists()]
    have = len(days) - len(todo) - len(no_session & {d.isoformat() for d in days})
    log(f"Bhavcopies {start} to {end}: {have} trading days already saved, {len(todo)} days to check.")
    got = miss = fail = 0
    t0 = time.time()
    for k, d in enumerate(todo, 1):
        saved = False
        status = []
        for kind, url in urls_for(d):
            code, body = f.get(url)
            status.append(f"{kind}:{code}")
            if code == 200 and looks_valid(body, kind):
                try:
                    rows = parse(body, kind, d)
                except StaleFile:
                    status.append(f"{kind}:404")
                    continue
                except Exception as e:
                    status.append(f"parse error {e}")
                    continue
                if not rows:
                    status.append("empty")
                    continue
                (root / str(d.year)).mkdir(exist_ok=True)
                tmp = root / str(d.year) / f".{d:%Y%m%d}.tmp"
                with gzip.open(tmp, "wt", newline="") as g:
                    w = csv.writer(g)
                    w.writerow(COLS)
                    w.writerows(rows)
                tmp.rename(root / str(d.year) / f"{d:%Y%m%d}.csv.gz")
                saved = True
                got += 1
                log(f"{d} saved ({kind}, {len(rows)} rows)", False)
                break
        if not saved:
            if (all(s.endswith(":404") for s in status) and (dt.date.today() - d).days > 3
                    and d.isoformat() not in known):
                no_session.add(d.isoformat())
                miss += 1
                if miss % 20 == 0:
                    nos_file.write_text("\n".join(sorted(no_session)) + "\n")
            else:
                fail += 1
                log(f"{d} not saved: {' '.join(status)}", d.weekday() < 5)
        if k % 100 == 0 or k == len(todo):
            rate = (time.time() - t0) / k
            left = (len(todo) - k) * rate / 60
            log(f"  {k}/{len(todo)} days checked: {got} saved, {miss} holidays/weekends, {fail} failed. "
                f"About {left:.0f} min left.")
    nos_file.write_text("\n".join(sorted(no_session)) + "\n")
    return got, miss, fail


def day_files(kind="bhav"):
    """Daily files under <kind>/<year>/ (the _stale folder and anything else is skipped)."""
    root = HERE / kind
    if not root.exists():
        return []
    return sorted(p for y in root.iterdir() if y.is_dir() and y.name.isdigit() and len(y.name) == 4
                  for p in y.glob("*.csv.gz") if p.name[:8].isdigit())


def drop_stale_days():
    """Set aside day files that repeat the previous trading day exactly (holiday copies saved by the first version
    of this script). They are moved to bhav/_stale, not deleted, and the day is marked as a holiday."""
    root = HERE / "bhav"
    stray = HERE / "bhav__stale.csv.gz"           # left by an earlier version
    if stray.exists():
        (root / "_stale").mkdir(exist_ok=True)
        stray.rename(root / "_stale" / "joined_stale.csv.gz")
    files = day_files("bhav")
    nos_file = root / "_no_session.txt"
    no_session = set(nos_file.read_text().split()) if nos_file.exists() else set()
    prev_rows = None
    moved = []
    for p in files:
        with gzip.open(p, "rt") as g:
            rows = [tuple(r[1:3] + r[4:8] + r[10:11]) for r in csv.reader(g)][1:]
        rows = sorted(r for r in rows if r[1] == "EQ")
        if prev_rows is not None and rows and len(rows) >= 0.95 * len(prev_rows):
            prev = set(prev_rows)
            same = sum(1 for r in rows if r in prev)
            if same >= 0.95 * len(rows):
                (root / "_stale").mkdir(exist_ok=True)
                p.rename(root / "_stale" / p.name)
                d = dt.datetime.strptime(p.name[:8], "%Y%m%d").date().isoformat()
                no_session.add(d)
                moved.append(d)
                continue
        prev_rows = rows
    if moved:
        nos_file.write_text("\n".join(sorted(no_session)) + "\n")
        for y in sorted({d[:4] for d in moved}):          # rebuild the affected years
            out = HERE / f"bhav_{y}.csv.gz"
            if out.exists():
                out.rename(root / "_stale" / f"bhav_{y}.old.csv.gz")
        log(f"Set aside {len(moved)} holiday files that repeated the previous day (now in bhav/_stale).")


def fetch_refs(f):
    (HERE / "ref").mkdir(exist_ok=True)
    for name, url in REF.items():
        code, body = f.get(url)
        if code == 200 and body:
            (HERE / "ref" / name).write_bytes(body)
            log(f"ref/{name} saved ({len(body) // 1024} KB)")
        else:
            log(f"ref/{name} NOT saved (status {code})")


def fetch_amfi(f):
    (HERE / "amfi").mkdir(exist_ok=True)
    for period, urls in amfi_candidates().items():
        dest = HERE / "amfi" / f"{period}.xlsx"
        if dest.exists():
            continue
        for url in urls:
            code, body = f.get(url, referer="https://www.amfiindia.com/otherdata/categorisation-of-stocks")
            if code == 200 and body[:2] == b"PK":
                dest.write_bytes(body)
                log(f"amfi/{period}.xlsx saved ({len(body) // 1024} KB)")
                break
    for period, url in AMFI.items():
        dest = HERE / "amfi" / f"{period}.xlsx"
        if dest.exists() and dest.stat().st_size > 10000:
            continue
        code, body = f.get(url, referer="https://www.amfiindia.com/otherdata/categorisation-of-stocks")
        if code == 200 and body[:2] == b"PK":
            dest.write_bytes(body)
            log(f"amfi/{period}.xlsx saved ({len(body) // 1024} KB)")
        else:
            log(f"amfi/{period}.xlsx NOT saved (status {code}) from {url}")


def joined_dates(kind="bhav"):
    """ISO dates already inside the joined year files <kind>_<year>.csv.gz (FinLit patch, see join_years)."""
    out = set()
    for p in sorted(HERE.glob(f"{kind}_[0-9][0-9][0-9][0-9].csv.gz")):
        try:
            with gzip.open(p, "rt") as g:
                next(g, None)
                last = None
                for line in g:
                    d = line[:10]
                    if d != last:
                        out.add(d)
                        last = d
        except (OSError, EOFError):
            continue
    return out


def join_years(kind="bhav", cols=COLS):
    """Join each year's day files into <kind>_<year>.csv.gz.

    FinLit patch: days that are in an existing joined file but have no day file are KEPT. Without this, a server that holds the joined files and only the
    newest day files would overwrite a year's history with the few days it has fetched since."""
    root = HERE / kind
    if not root.exists():
        return
    for ydir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 4):
        files = sorted(ydir.glob("*.csv.gz"))
        if not files:
            continue
        out = HERE / f"{kind}_{ydir.name}.csv.gz"
        newest = max(p.stat().st_mtime for p in files)
        if out.exists() and out.stat().st_mtime >= newest:
            continue
        chunks = {}                                 # ISO date -> that day's rows (text), from the day files
        for p in files:
            with gzip.open(p, "rt") as s:
                next(s)
                chunks[dt.datetime.strptime(p.name[:8], "%Y%m%d").date().isoformat()] = s.read()
        kept, only_old = 0, set()
        if out.exists():                            # days only the old joined file knows
            try:
                with gzip.open(out, "rt") as s:
                    next(s, None)
                    for line in s:
                        d = line[:10]
                        if d not in chunks or d in only_old:
                            only_old.add(d)
                            chunks[d] = chunks.get(d, "") + line
                            kept += 1
            except (OSError, EOFError):
                pass
        tmp = HERE / f".{kind}_{ydir.name}.tmp"
        with gzip.open(tmp, "wt", newline="") as g:
            g.write(",".join(cols) + "\n")
            for d in sorted(chunks):
                g.write(chunks[d])
        tmp.rename(out)
        log(f"{kind}_{ydir.name}.csv.gz: {len(files)} days" + (f" (+ {kept} rows of earlier days kept)" if kept else ""))


IDX_COLS = ["date", "index", "open", "high", "low", "close", "volume", "turnover_cr", "pe", "pb", "div_yield"]
IDX_MAP = {"INDEX NAME": "index", "OPEN INDEX VALUE": "open", "HIGH INDEX VALUE": "high", "LOW INDEX VALUE": "low",
           "CLOSING INDEX VALUE": "close", "VOLUME": "volume", "TURNOVER (RS. CR.)": "turnover_cr", "P/E": "pe",
           "P/B": "pb", "DIV YIELD": "div_yield"}


def parse_index(body, day):
    rd = csv.reader(io.StringIO(body.decode("utf-8", "replace")))
    head = [h.strip().upper() for h in next(rd)]
    idx = {IDX_MAP[h]: i for i, h in enumerate(head) if h in IDX_MAP}
    if "index" not in idx or "close" not in idx:
        raise ValueError(f"unexpected columns {head}")
    out = []
    for r in rd:
        if len(r) <= idx["close"] or not r[idx["index"]].strip():
            continue
        out.append([day.isoformat(), r[idx["index"]].strip()]
                   + [_num(r[idx[k]]) if k in idx and idx[k] < len(r) else "" for k in IDX_COLS[2:]])
    return out


def fetch_indices(f):
    """Closing values of every NSE index, for each trading day that has a bhavcopy."""
    days = sorted(dt.datetime.strptime(p.name[:8], "%Y%m%d").date() for p in day_files("bhav"))
    root = HERE / "idx"
    root.mkdir(exist_ok=True)
    todo = [d for d in days if not (root / str(d.year) / f"{d:%Y%m%d}.csv.gz").exists()]
    log(f"Index closes: {len(days) - len(todo)} days already saved, {len(todo)} to fetch.")
    got = fail = 0
    t0 = time.time()
    for k, d in enumerate(todo, 1):
        code, body = f.get(f"{ARCH}/content/indices/ind_close_all_{d:%d%m%Y}.csv")
        if code == 200 and body[:20].upper().lstrip().startswith(b"INDEX NAME"):
            try:
                rows = parse_index(body, d)
            except Exception as e:      # noqa: BLE001
                log(f"{d} index file not read: {e}")
                fail += 1
                continue
            (root / str(d.year)).mkdir(exist_ok=True)
            tmp = root / str(d.year) / f".{d:%Y%m%d}.tmp"
            with gzip.open(tmp, "wt", newline="") as g:
                w = csv.writer(g)
                w.writerow(IDX_COLS)
                w.writerows(rows)
            tmp.rename(root / str(d.year) / f"{d:%Y%m%d}.csv.gz")
            got += 1
        else:
            fail += 1
            log(f"{d} index closes not saved (status {code})", False)
        if k % 200 == 0 or k == len(todo):
            left = (len(todo) - k) * (time.time() - t0) / k / 60
            log(f"  {k}/{len(todo)} index days: {got} saved, {fail} missing. About {left:.0f} min left.")
    return got, fail


# ---------------------------------------------------------------------------------------------- NSE website API
WWW = "https://www.nseindia.com"


def _api(f, path, referer):
    """GET a JSON API on NSE's website (cookies from the home page first). None when refused."""
    if not getattr(f, "_www_ready", False):
        f.get(WWW + "/", referer=WWW + "/")
        f._www_ready = True
    old_delay, f.delay = f.delay, max(f.delay, 0.4)
    try:
        code, body = f.get(WWW + path, referer=referer)
    finally:
        f.delay = old_delay
    if code != 200 or not body[:1] in (b"[", b"{"):
        return None
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None


def action_lines(symbol, ex_date, subject, face_value):
    """NSE corporate-action subject -> lines of nse_corporate_actions.txt (see nse.load_actions)."""
    s = " ".join(str(subject or "").split())
    d = ex_date.strftime("%Y%m%d")
    out = []
    if re.search(r"debenture|ncrps|preference|warrant|ccps", s, re.I):
        return out
    m = re.search(r"bonus\s*[-:]?\s*(\d+)\s*:\s*(\d+)", s, re.I)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        out.append(f"{symbol} {d} {b}/{a + b} B")
    m = re.search(r"(split|sub-?div|splt).*?fro?m\s*R[se]\.?\s*([\d.]+).*?to\s*R[se]\.?\s*([\d.]+)", s, re.I)
    if m:
        out.append(f"{symbol} {d} {float(m.group(3)):g}/{float(m.group(2)):g} S")
    m = re.search(r"consolid.*?fro?m\s*R[se]\.?\s*([\d.]+).*?to\s*R[se]\.?\s*([\d.]+)", s, re.I)
    if m and not out:
        out.append(f"{symbol} {d} {float(m.group(2)):g}/{float(m.group(1)):g} C")
    m = re.search(r"rights?\s*(?:issue\s*)?[-:]?\s*(\d+)\s*:\s*(\d+)(?:.*?premium\s*(?:of\s*)?R[se]\.?\s*([\d.]+))?", s, re.I)
    if m and not out:
        prem = m.group(3) if m.group(3) is not None else "?"
        try:
            fv = f"{float(face_value):g}"
        except (TypeError, ValueError):
            fv = "?"
        out.append(f"{symbol} {d} R {m.group(1)}:{m.group(2)} {prem} {fv}")
    if not out and re.search(r"demerger|scheme of arrangement|capital reduction", s, re.I):
        out.append(f"{symbol} {d} D")
    return out


def fetch_actions(f, days=120):
    """Corporate actions with an ex-date in the last `days` days and the next 30, into ref/corporate_actions.txt."""
    (HERE / "ref").mkdir(exist_ok=True)
    path = HERE / "ref" / "corporate_actions.txt"
    have = set(path.read_text().splitlines()) if path.exists() else set()
    a = dt.date.today() - dt.timedelta(days=days)
    b = dt.date.today() + dt.timedelta(days=30)
    j = _api(f, f"/api/corporates-corporateActions?index=equities&from_date={a:%d-%m-%Y}&to_date={b:%d-%m-%Y}",
             WWW + "/companies-listing/corporate-filings-actions")
    if j is None:
        log("Corporate actions: NSE's website refused the request. Splits and bonuses after the bundled list "
            "will be caught from price gaps only; run again later.")
        return None
    new = []
    for x in j:
        try:
            ex = dt.datetime.strptime(str(x.get("exDate", "")).strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        for line in action_lines(str(x.get("symbol", "")).strip(), ex, x.get("subject"), x.get("faceVal")):
            if line not in have:
                have.add(line)
                new.append(line)
    if new:
        with open(path, "a") as fh:
            if path.stat().st_size == 0:
                fh.write("# corporate actions fetched from NSE (same format as the bundled list)\n")
            fh.write("\n".join(new) + "\n")
    log(f"Corporate actions: {len(j)} filings read, {len(new)} new split/bonus/rights/demerger lines.")
    return len(new)


def fetch_industries(f, known, limit=400):
    """NSE industry of listed stocks missing from `known` (new listings), into ref/industries_extra.json."""
    eq = HERE / "ref" / "EQUITY_L.csv"
    if not eq.exists():
        return None
    path = HERE / "ref" / "industries_extra.json"
    extra = json.loads(path.read_text()).get("stocks", {}) if path.exists() else {}
    syms = []
    with open(eq, newline="", encoding="utf-8", errors="replace") as fh:
        rd = csv.reader(fh)
        head = [h.strip().upper() for h in next(rd)]
        si, se = head.index("SYMBOL"), head.index("SERIES") if "SERIES" in head else None
        for r in rd:
            if r and r[si].strip() and r[si].strip() not in known and r[si].strip() not in extra:
                syms.append((r[si].strip(), r[se].strip() if se is not None else "EQ"))
    if not syms:
        log("Industries: every listed stock already has an NSE industry.")
        return 0
    got = 0
    for sym, ser in syms[:limit]:
        j = _api(f, "/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series="
                 + urllib.request.quote(ser or "EQ") + "&symbol=" + urllib.request.quote(sym),
                 WWW + "/get-quote/equity/" + urllib.request.quote(sym))
        if j is None:
            if got == 0:
                log("Industries: NSE's website refused the request; new listings stay unclassified for now.")
                break
            continue
        try:
            si_ = j["equityResponse"][0]["secInfo"]
            ind, sec = si_.get("industryInfo"), si_.get("sector")
        except (KeyError, IndexError, TypeError, AttributeError):   # AttributeError: NSE sent "secInfo": null for this stock
            continue
        if ind:
            extra[sym] = [ind, sec or ""]
            got += 1
    path.write_text(json.dumps({"_note": "NSE industry of stocks listed after the bundled classification",
                                "stocks": extra}, indent=0))
    log(f"Industries: {got} of {min(len(syms), limit)} new listings classified.")
    return got


def amfi_candidates():
    """AMFI lists newer than the known ones: the portal's naming pattern for each half-year since."""
    last = max(AMFI)
    y, h = int(last[:4]), int(last[5])
    today = dt.date.today()
    out = {}
    while True:
        y, h = (y, 2) if h == 1 else (y + 1, 1)
        end = dt.date(y, 6, 30) if h == 1 else dt.date(y, 12, 31)
        if end + dt.timedelta(days=5) > today:
            break
        tag = f"30Jun{y}" if h == 1 else f"31Dec{y}"
        out[f"{y}H{h}"] = ["https://portal.amfiindia.com/spages/AverageMarketCapitalization" + tag + ".xlsx",
                           _A + "AverageMarketCapitalization" + tag + ".xlsx"]
    return out


def probe(f):
    """Quick check that NSE's archive answers before the long run."""
    tests = [("old", dt.date(2017, 1, 2)), ("udiff", dt.date(2024, 10, 28))]
    ok = True
    for kind, d in tests:
        url = dict(urls_for(d))[kind]
        code, body = f.get(url)
        good = code == 200 and looks_valid(body, kind)
        if good:
            rows = parse(body, kind, d)
            eq = sum(1 for r in rows if r[2] == "EQ")
            log(f"Check {kind} format ({d}): OK, {len(rows)} rows, {eq} EQ stocks")
        else:
            log(f"Check {kind} format ({d}): FAILED (status {code})")
            ok = False
    return ok


def main(argv=None):
    global LOG, HERE
    ap = argparse.ArgumentParser(prog="python -m finlit_technicals fetch-nse", description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=os.environ.get("FINLIT_NSE_DIR"), required=not os.environ.get("FINLIT_NSE_DIR"),
                    help="folder to keep the files in (or set FINLIT_NSE_DIR)")
    ap.add_argument("--no-actions", action="store_true", help="skip corporate actions from NSE's website")
    ap.add_argument("--no-industries", action="store_true", help="skip the industry of new listings")
    ap.add_argument("--from", dest="start", default=START.isoformat(), help="first day, YYYY-MM-DD (default 2016-01-01)")
    ap.add_argument("--to", dest="end", default=dt.date.today().isoformat(), help="last day (default today)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests (default 0.3)")
    ap.add_argument("--skip-amfi", action="store_true")
    ap.add_argument("--skip-indices", action="store_true")
    a = ap.parse_args(argv)
    HERE = Path(a.dir).expanduser().resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    LOG = open(HERE / "fetch_log.txt", "a")
    log(f"--- fetch-nse started in {HERE} (Python {sys.version.split()[0]}) ---")
    f = Fetcher(a.delay)
    if not probe(f):
        log("NSE's archive did not answer as expected. Check the internet connection and run again; "
            "fetch_log.txt has the details.")
        return 1
    fetch_refs(f)
    if not a.skip_amfi:
        fetch_amfi(f)
    got, miss, fail = fetch_days(f, dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))
    drop_stale_days()
    join_years()
    ifail = 0
    if not a.skip_indices:
        _, ifail = fetch_indices(f)
        join_years("idx", IDX_COLS)
    if not a.no_actions:
        fetch_actions(f)
    if not a.no_industries:
        from .industries import load_industries
        fetch_industries(f, set(load_industries()))
    n_days = len(day_files("bhav"))
    n_idx = len(day_files("idx"))
    log(f"Done. {n_days} trading days of stock prices and {n_idx} of index closes saved; "
        f"{fail + ifail} days could not be fetched this run.")
    fail += ifail
    if fail:
        log("Run the same command again to retry the failed days.")
    else:
        log("All set.")
    return 0


if __name__ == "__main__":     # python -m finlit_technicals.fetch --dir ...
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Stopped. Run the same command again to carry on where it left off.")
        sys.exit(130)
