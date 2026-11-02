"""FinLit patches to fetch.py (FINLIT_PATCHES.md): a folder that holds only the joined year files stays intact and is not fetched again."""
import csv
import datetime as dt
import gzip
from pathlib import Path

from finlit_technicals import fetch


def _write_joined(path: Path, days, cols=fetch.COLS):
    with gzip.open(path, "wt", newline="") as g:
        w = csv.writer(g)
        w.writerow(cols)
        for d in days:
            for s in ("AAA", "BBB"):
                w.writerow([d, s, "EQ", "INE000", 10, 11, 9, 10, 10, 10, 100, 1000, 5])


def _write_day(root: Path, day: str):
    y = root / "bhav" / day[:4]
    y.mkdir(parents=True, exist_ok=True)
    name = day.replace("-", "") + ".csv.gz"
    with gzip.open(y / name, "wt", newline="") as g:
        w = csv.writer(g)
        w.writerow(fetch.COLS)
        w.writerow([day, "AAA", "EQ", "INE000", 20, 21, 19, 20, 20, 20, 100, 2000, 5])


def test_joined_dates_reads_the_dates_in_the_year_files(tmp_path):
    fetch.HERE = tmp_path
    _write_joined(tmp_path / "bhav_2026.csv.gz", ["2026-01-05", "2026-01-06"])
    assert fetch.joined_dates("bhav") == {"2026-01-05", "2026-01-06"}
    assert fetch.joined_dates("idx") == set()


def test_join_years_keeps_days_only_the_old_joined_file_has(tmp_path):
    fetch.HERE = tmp_path
    old = ["2026-01-05", "2026-01-06", "2026-01-07"]
    _write_joined(tmp_path / "bhav_2026.csv.gz", old)
    _write_day(tmp_path, "2026-01-08")                    # the only day file the server has fetched
    (tmp_path / "bhav_2026.csv.gz").touch()
    import os
    os.utime(tmp_path / "bhav_2026.csv.gz", (1, 1))        # older than the day file, so it is rebuilt
    fetch.join_years("bhav")
    assert fetch.joined_dates("bhav") == set(old) | {"2026-01-08"}
    with gzip.open(tmp_path / "bhav_2026.csv.gz", "rt") as g:
        lines = g.read().splitlines()
    assert lines[0].startswith("date,") and len(lines) == 1 + 2 * 3 + 1
    dates = [l[:10] for l in lines[1:]]
    assert dates == sorted(dates)


def test_join_years_replaces_a_day_that_has_a_day_file(tmp_path):
    import os
    fetch.HERE = tmp_path
    _write_joined(tmp_path / "bhav_2026.csv.gz", ["2026-01-05"])
    _write_day(tmp_path, "2026-01-05")
    os.utime(tmp_path / "bhav_2026.csv.gz", (1, 1))
    fetch.join_years("bhav")
    with gzip.open(tmp_path / "bhav_2026.csv.gz", "rt") as g:
        rows = list(csv.reader(g))[1:]
    assert len(rows) == 1 and rows[0][4] == "20"          # the day file wins, as before the patch


class _NoNetwork:
    def get(self, url, referer=None):
        raise AssertionError("must not fetch a day the joined files already hold: " + url)


def test_fetch_days_skips_days_in_the_joined_files_and_old_holidays(tmp_path):
    fetch.HERE = tmp_path
    first, last = dt.date(2026, 1, 5), dt.date(2026, 3, 13)
    days = [d.isoformat() for d in (first + dt.timedelta(n) for n in range((last - first).days + 1)) if d.weekday() < 5 and d != dt.date(2026, 1, 26)]
    _write_joined(tmp_path / "bhav_2026.csv.gz", days)
    # asking for the days up to a month before the newest joined day: all done or written off, so NSE is never asked
    got, miss, fail = fetch.fetch_days(_NoNetwork(), first, dt.date(2026, 2, 10))
    assert (got, miss, fail) == (0, 0, 0)
    written_off = set((tmp_path / "bhav" / "_no_session.txt").read_text().split())
    assert "2026-01-26" in written_off and "2026-01-10" in written_off      # the holiday and a Saturday: never asked for
