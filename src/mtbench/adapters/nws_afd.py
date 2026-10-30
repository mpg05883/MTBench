"""NWS Area Forecast Discussions (IEM AFOS archive) + GHCNh hourly temperature.

One sample per (station, anchor): the input window ends at `anchor_hour` local standard time on the
anchor day, the text is the latest AFD from the station's forecast office (WFO) issued at or before
that moment (gap <= MAX_TEXT_GAP_H), and the output window follows hourly. All sample timestamps and
`meta.issue_time` are local standard time (no DST); `meta.issue_time_utc` keeps the UTC issue time.
"""
import bisect
import csv
import json
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

from mtbench.adapters import filters
from mtbench.adapters.base import SampleFilter, SourceAdapter, log_fetch
from mtbench.adapters.schema import make_meta
from mtbench.env import get_user_agent
from mtbench.path import resolve_data_dir, resolve_weather_data_dir

AFD_URL = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
GHCNH_URL = (
    "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/"
    "by-year/{year}/parquet/GHCNh_{station}_{year}.parquet"
)
SETTINGS = {"short": (7, 1), "long": (14, 3)}  # name -> (input days, output days)
MAX_TEXT_GAP_H = 6
MIN_ANCHOR_SPACING_H = 48
BAD_QC = {"2", "3", "6", "7"}  # GHCNh suspect / erroneous quality codes
SIZE_GATE_BYTES = 2 * 1024**3
EST_AFD_MONTH_BYTES = 1_500_000  # one WFO-month of AFDs (subset months were 1.0-1.6 MB)
MIN_COVERED_HOURS = 6  # a section counts as covering the output window with >= this overlap

# ---- text processing ------------------------------------------------------------------------
PRODUCT_RE = re.compile(r"\x01(.*?)\x03", re.S)
WMO_RE = re.compile(r"^[A-Z]{4}\d{2} (K[A-Z0-9]{3}) (\d{2})(\d{2})(\d{2})(?: [A-Z]{3})?$")
ISSUED_LINE_RE = re.compile(r"^\d{3,4} (?:AM|PM) [A-Z]{2,4} [A-Za-z]{3} [A-Za-z]{3} +\d{1,2} \d{4}$")
SECTION_RE = re.compile(r"^\.([A-Z][A-Z0-9 /&\-]*?)\s*(?:/|\.\.\.|$)")
WARNINGS_RE = re.compile(r"WATCHES|WARNINGS")
# sections whose content is not about air temperature over the output window
NON_FORECAST_RE = re.compile(r"AVIATION|MARINE|FIRE WEATHER|HYDRO|CLIMATE|TIDE|BEACH|RIP CURRENT|SPOTTER")
# approximate forecast horizon (hours after issue) covered by common section names
SECTION_HORIZON = {"NEAR TERM": (0, 24), "SHORT TERM": (0, 72), "LONG TERM": (72, 192)}
ALL_HORIZON = (0, 192)  # KEY MESSAGES, DISCUSSION, SYNOPSIS, preamble and unknown names

_TEMP_WORD = r"(?:highs?|lows?|temps?|temperatures?|readings?)"
_NOT_UNIT = r"(?!\s*(?:to\s+\d+\s*)?(?:mph|kt|kts|knots?|%|percent|inch|inches|miles?|feet|ft)\b)"
_NUM = rf"(?:(?:upper|lower|mid)[ -]?)?\d{{1,3}}s?\b{_NOT_UNIT}"
NUMERIC_FORECAST_RES = [
    re.compile(
        rf"\b{_TEMP_WORD}\b[^.;:\n]{{0,80}}?\b(?:in the|near|around|of|to|into|from|at|be|reach|reaching|"
        rf"climb(?:ing)?|top(?:ping)?|only|up to|below|above)\s+(?:the\s+)?{_NUM}",
        re.I,
    ),
    re.compile(rf"\b(?:around|near|about)\s+\d{{2,3}}\b{_NOT_UNIT}", re.I),
    re.compile(r"\bin the (?:(?:upper|lower|mid)[ -])?[1-9]0s\b", re.I),
]


def section_name(line: str) -> Optional[str]:
    m = SECTION_RE.match(line.strip())
    return m.group(1).strip() if m else None


def clean_afd(block: str) -> tuple[str, list[str]]:
    """Strip header, `$$` footer, `&&` markers and the watches/warnings section.

    Returns (text, section names present). Remaining sections are kept as written.
    """
    lines = [ln.rstrip() for ln in block.replace("\x01", "").replace("\x03", "").split("\n")]
    start = next((i + 1 for i, ln in enumerate(lines[:15]) if ISSUED_LINE_RE.match(ln.strip())), None)
    if start is None:  # unknown header layout: start at the first section heading
        start = next((i for i, ln in enumerate(lines) if section_name(ln)), 0)
    body = lines[start:]
    if "$$" in [ln.strip() for ln in body]:
        body = body[: [ln.strip() for ln in body].index("$$")]
    kept, names, skipping = [], [], False
    for ln in body:
        name = section_name(ln)
        if name:
            skipping = bool(WARNINGS_RE.search(name))
            if not skipping:
                names.append(name)
        if skipping or ln.strip() == "&&":
            continue
        kept.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return text, names


def split_sections(text: str) -> list[tuple[Optional[str], str]]:
    """[(section name or None for the preamble, section text)] in order."""
    out: list[tuple[Optional[str], list[str]]] = [(None, [])]
    for ln in text.split("\n"):
        name = section_name(ln)
        if name:
            out.append((name, []))
        out[-1][1].append(ln)
    return [(n, "\n".join(ls)) for n, ls in out if "".join(ls).strip()]


def has_numeric_temperature(text: str) -> bool:
    return any(rx.search(text) for rx in NUMERIC_FORECAST_RES)


def covering_text(text: str, start_h: float, end_h: float) -> str:
    """Sections that cover the output window [start_h, end_h] (hours after the AFD issue time)."""
    parts = []
    for name, body in split_sections(text):
        if name and NON_FORECAST_RE.search(name):
            continue
        lo, hi = SECTION_HORIZON.get(name, ALL_HORIZON)
        if min(hi, end_h) - max(lo, start_h) >= MIN_COVERED_HOURS:
            parts.append(body)
    return "\n".join(parts)


def parse_afd_file(raw: str, win_start: datetime, win_end: datetime) -> list[dict]:
    """Products of one IEM response as [{wfo, issue_utc, text, sections}], oldest first."""
    products = {}
    for block in PRODUCT_RE.findall(raw):
        head = [ln.strip() for ln in block.split("\n")[:6]]
        m = next((WMO_RE.match(ln) for ln in head if WMO_RE.match(ln)), None)
        if not m:
            continue
        dd, hh, mm = int(m.group(2)), int(m.group(3)), int(m.group(4))
        issue = None
        for shift in (0, -1, 1):
            month = win_start.month + shift
            year = win_start.year + (month - 1) // 12
            try:
                cand = datetime(year, (month - 1) % 12 + 1, dd, hh, mm)
            except ValueError:
                continue
            if win_start - timedelta(days=1) <= cand < win_end + timedelta(days=1):
                issue = cand
                break
        if issue is None:
            continue
        text, names = clean_afd(block)
        if text:
            products[issue] = {"wfo": m.group(1)[1:], "issue_utc": issue, "text": text, "sections": names}
    return [products[k] for k in sorted(products)]


# ---- adapter --------------------------------------------------------------------------------
class NwsAfdAdapter(SourceAdapter):
    name = "nws_afd"
    domain = "weather"

    def __init__(
        self,
        setting: str = "short",
        stations: Optional[list] = None,
        start_year: int = 2019,
        end_year: int = 2023,
        anchor_hour: int = 23,
        seed: int = 0,
        subset: bool = False,
        check_overlap: bool = True,
        delay: float = 1.0,
    ):
        super().__init__()
        self.setting = setting
        self.in_days, self.out_days = SETTINGS[setting]
        self.station_filter = stations
        self.start_year, self.end_year = start_year, end_year
        self.anchor_hour = anchor_hour
        self.seed = seed
        self.check_overlap = check_overlap
        self.delay = delay
        self.stride_days = -(-MIN_ANCHOR_SPACING_H // 24)
        self.out_subdir = ("subset_" if subset else "") + f"aligned_in{self.in_days}days_out{self.out_days}days"
        self.flt: Optional[SampleFilter] = None
        self._last_request = 0.0
        self._session = None

    # paths
    @property
    def afd_dir(self) -> Path:
        return self.raw_dir / "afd_bulk"

    @property
    def ghcnh_dir(self) -> Path:
        return self.raw_dir / "ghcnh"

    @property
    def station_csv(self) -> Path:
        return self.raw_dir / "station_wfo.csv"

    def ghcnh_path(self, station: str, year: int) -> Path:
        return self.ghcnh_dir / f"GHCNh_{station}_{year}.parquet"

    def afd_path(self, wfo: str, year: int, month: int) -> Path:
        return self.afd_dir / f"{wfo}_{year}{month:02d}.txt"

    def months(self):
        return [(y, m) for y in range(self.start_year, self.end_year + 1) for m in range(1, 13)]

    # network
    def _get(self, url: str, params: Optional[dict] = None, retries: int = 3):
        if self._session is None:
            self._session = requests.Session()
            self._session.headers["User-Agent"] = get_user_agent()
        for attempt in range(retries):
            wait = self.delay - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()
            try:
                resp = self._session.get(url, params=params, timeout=120)
            except requests.RequestException as e:
                self.log.warning("request error %s; retry %d/%d", e, attempt + 1, retries)
                time.sleep(2 * (attempt + 1))
                continue
            log_fetch(self.name, resp.url, f"status {resp.status_code}, {len(resp.content)} bytes")
            if resp.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            return resp
        return None

    # stations
    def _station_meta(self) -> dict:
        """station -> {lat, lon, offset_h} from the NOAA benchmark metadata."""
        meta_dir = resolve_data_dir() / "noaa-weather" / "forecast_hourly"
        out = {}
        for meta_file in sorted(meta_dir.glob("*_meta.jsonl")):
            with open(meta_file) as f:
                for line in f:
                    m = json.loads(line)
                    out.setdefault(
                        m["station"], {"lat": m["lat"], "lon": m["lon"], "offset_h": m["local_std_utc_offset_h"]}
                    )
        return out

    def resolve_stations(self, fetch: bool = True) -> dict:
        """station -> {lat, lon, offset_h, wfo} for stations with GHCNh files already on disk.

        The station->WFO mapping (api.weather.gov points -> cwa) is cached in station_wfo.csv.
        """
        cached = {}
        if self.station_csv.exists():
            with open(self.station_csv, newline="") as f:
                cached = {r["station"]: r for r in csv.DictReader(f)}
        on_disk = sorted({p.name.split("_")[1] for p in self.ghcnh_dir.glob("GHCNh_*_*.parquet")})
        wanted = self.station_filter or on_disk
        meta = self._station_meta()
        legacy = self.raw_dir / "offices.json"  # earlier points lookups, reused to save requests
        legacy_wfo = json.loads(legacy.read_text()) if legacy.exists() else {}
        rows, changed = {}, False
        for s in wanted:
            if s not in meta:
                self.log.warning("no lat/lon metadata for %s; skipped", s)
                continue
            wfo = (cached.get(s) or {}).get("wfo") or legacy_wfo.get(s)
            if not wfo and fetch:
                r = self._get(POINTS_URL.format(lat=round(meta[s]["lat"], 4), lon=round(meta[s]["lon"], 4)))
                wfo = r.json()["properties"]["cwa"] if r is not None and r.status_code == 200 else None
            if not wfo:
                continue
            if s not in cached or cached[s].get("wfo") != wfo:
                changed = True
            rows[s] = {**meta[s], "wfo": wfo}
        if changed:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            all_rows = {**cached, **{s: {"station": s, **v} for s, v in rows.items()}}
            with open(self.station_csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["station", "lat", "lon", "offset_h", "wfo"])
                w.writeheader()
                w.writerows({k: r[k] for k in w.fieldnames} for r in all_rows.values())
        return rows

    # download
    def plan(self, stations: dict) -> dict:
        wfos = sorted({v["wfo"] for v in stations.values()})
        afd_missing = [(w, y, m) for w in wfos for y, m in self.months() if not self.afd_path(w, y, m).exists()]
        ghcnh_missing = [
            (s, y) for s in stations for y in range(self.start_year, self.end_year + 1)
            if not self.ghcnh_path(s, y).exists()
        ]
        sizes = [p.stat().st_size for p in self.ghcnh_dir.glob("*.parquet")]
        ghcnh_bytes = len(ghcnh_missing) * (int(np.median(sizes)) if sizes else 2_000_000)
        total = len(afd_missing) * EST_AFD_MONTH_BYTES + ghcnh_bytes
        info = {
            "stations": len(stations), "wfos": len(wfos),
            "afd_requests": len(afd_missing), "ghcnh_files_missing": len(ghcnh_missing),
            "estimated_bytes": total,
        }
        print(json.dumps(info, indent=2), "->", "OVER the 2 GB gate" if total > SIZE_GATE_BYTES else "under 2 GB")
        return info

    def download(self, allow_large: bool = False) -> None:
        stations = self.resolve_stations()
        info = self.plan(stations)
        if info["estimated_bytes"] > SIZE_GATE_BYTES and not allow_large:
            raise SystemExit("Planned download is over 2 GB; get the user's OK, then pass allow_large.")
        self.afd_dir.mkdir(parents=True, exist_ok=True)
        for wfo in sorted({v["wfo"] for v in stations.values()}):
            for y, m in self.months():
                path = self.afd_path(wfo, y, m)
                if path.exists():
                    continue
                start = datetime(y, m, 1)
                end = datetime(y + (m == 12), m % 12 + 1, 1)
                params = {
                    "pil": f"AFD{wfo}", "fmt": "text", "order": "asc", "limit": 9999,
                    "sdate": f"{start:%Y-%m-%dT%H:%M}Z", "edate": f"{end:%Y-%m-%dT%H:%M}Z",
                }
                r = self._get(AFD_URL, params)
                if r is not None and r.status_code == 200:
                    path.write_bytes(r.content)
                else:
                    self.log.warning("AFD fetch failed for %s %d-%02d", wfo, y, m)
        for s in stations:  # GHCNh files already on disk are never re-downloaded
            for y in range(self.start_year, self.end_year + 1):
                path = self.ghcnh_path(s, y)
                if path.exists():
                    continue
                r = self._get(GHCNH_URL.format(station=s, year=y))
                if r is not None and r.status_code == 200:
                    self.ghcnh_dir.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(r.content)

    # load
    def load_ts(self):
        """station -> (hourly local-standard-time temperature in degC with NaN gaps, observed mask)."""
        out = {}
        for s, info in self.resolve_stations(fetch=False).items():
            years = [y for y in range(self.start_year - 1, self.end_year + 2) if self.ghcnh_path(s, y).exists()]
            if not years:
                continue
            df = pd.concat(
                [pd.read_parquet(self.ghcnh_path(s, y), columns=["DATE", "temperature", "temperature_Quality_Code"])
                 for y in years],
                ignore_index=True,
            )
            df = df[df["temperature"].notna() & ~df["temperature_Quality_Code"].astype(str).isin(BAD_QC)]
            local = pd.to_datetime(df["DATE"], utc=True).dt.tz_localize(None) + pd.Timedelta(hours=info["offset_h"])
            # nearest-hour bucketing: a METAR at 00:53 is the observation for the 01:00 hour
            hourly = df["temperature"].groupby(local.dt.round("h")).mean()
            index = pd.date_range(f"{min(years)}-01-01", f"{max(years)}-12-31 23:00", freq="h")
            hourly = hourly.reindex(index)
            out[s] = (hourly.interpolate(limit=3, limit_area="inside"), hourly.notna())
        return out

    def load_text(self):
        """wfo -> (sorted UTC issue times, records) for the months in range."""
        wfos = sorted({v["wfo"] for v in self.resolve_stations(fetch=False).values()})
        out = {}
        for wfo in wfos:
            recs = []
            for y, m in self.months():
                path = self.afd_path(wfo, y, m)
                if not path.exists():
                    continue
                start = datetime(y, m, 1)
                end = datetime(y + (m == 12), m % 12 + 1, 1)
                recs += parse_afd_file(path.read_bytes().decode("latin-1"), start, end)
            recs.sort(key=lambda r: r["issue_utc"])
            out[wfo] = ([r["issue_utc"] for r in recs], recs)
        return out

    # align + samples
    def _drop(self, reason: str) -> None:
        if self.flt is not None:
            self.flt.dropped[reason] += 1

    def anchors(self, station: str) -> list:
        """Anchor input-end timestamps for one station, spaced >= MIN_ANCHOR_SPACING_H apart."""
        days = pd.date_range(f"{self.start_year}-01-01", f"{self.end_year}-12-31", freq="D")
        offset = random.Random(f"{self.seed}:{station}").randrange(self.stride_days)
        return [d + pd.Timedelta(hours=self.anchor_hour) for d in days[offset::self.stride_days]]

    def align(self, ts, texts):
        """Yield (station, info, input_end, afd record, input index, output index, series, observed)."""
        stations = self.resolve_stations(fetch=False)
        for s, info in stations.items():
            if s not in ts:
                self._drop("no_ghcnh")
                continue
            series, observed = ts[s]
            issues, recs = texts.get(info["wfo"], ([], []))
            offset = timedelta(hours=info["offset_h"])
            for end in self.anchors(s):
                in_idx = pd.date_range(end=end, periods=24 * self.in_days, freq="h")
                out_idx = pd.date_range(end + pd.Timedelta(hours=1), periods=24 * self.out_days, freq="h")
                if in_idx[0] < series.index[0] or out_idx[-1] > series.index[-1]:
                    self._drop("ts_out_of_range")
                    continue
                i = bisect.bisect_right(issues, end.to_pydatetime() - offset) - 1  # issue_utc <= input end
                if i < 0:
                    self._drop("no_afd_before_input_end")
                    continue
                gap_h = (end.to_pydatetime() - offset - issues[i]).total_seconds() / 3600
                if gap_h > MAX_TEXT_GAP_H:
                    self._drop("afd_gap_gt_6h")
                    continue
                yield s, info, end, recs[i], gap_h, in_idx, out_idx, series, observed

    def make_samples(self) -> list[dict]:
        samples = []
        for s, info, end, afd, gap_h, in_idx, out_idx, series, observed in self.align(self.load_ts(), self.load_text()):
            issue_local = pd.Timestamp(afd["issue_utc"]) + pd.Timedelta(hours=info["offset_h"])
            stamps = lambda idx: idx.strftime("%Y-%m-%d %H:%M:%S").tolist()  # noqa: E731
            x, y = series.loc[in_idx].to_numpy(), series.loc[out_idx].to_numpy()
            start_h = (out_idx[0] - issue_local).total_seconds() / 3600
            end_h = (out_idx[-1] - issue_local).total_seconds() / 3600
            out_ts = stamps(out_idx)
            meta = make_meta(
                source=self.name,
                domain=self.domain,
                entity_id=s,
                issue_time=issue_local.strftime("%Y-%m-%d %H:%M:%S"),
                text_kind="forecast_of_future",
                has_numeric_forecast=has_numeric_temperature(covering_text(afd["text"], start_h, end_h)),
                split_group=info["wfo"],
                output_timestamps=out_ts,
            )
            meta.update(
                wfo=info["wfo"], sections=afd["sections"],
                issue_time_utc=afd["issue_utc"].strftime("%Y-%m-%d %H:%M:%S"), afd_gap_hours=round(gap_h, 2),
                obs_frac_in=round(float(observed.loc[in_idx].mean()), 3),
                obs_frac_out=round(float(observed.loc[out_idx].mean()), 3),
                variable="temperature_c", freq="1h", setting=self.setting,
            )
            samples.append({
                "text": afd["text"],
                "input_timestamps": stamps(in_idx),
                "input_window": np.round(x, 2).tolist(),
                "output_timestamps": out_ts,
                "output_window": np.round(y, 2).tolist(),
                "meta": meta,
            })
        return samples

    def sample_filter(self) -> SampleFilter:
        windows = filters.load_mtbench_windows([resolve_weather_data_dir()]) if self.check_overlap else {}
        flt = SampleFilter(mtbench_windows=windows, expected_in=24 * self.in_days, expected_out=24 * self.out_days)
        has_nan = lambda w: any(v is None or not np.isfinite(v) for v in w)  # noqa: E731
        flt.register("ts_has_gaps", lambda s: has_nan(s["input_window"]) or has_nan(s["output_window"]))
        flt.register("ts_low_coverage", lambda s: s["meta"]["obs_frac_in"] < 0.9 or s["meta"]["obs_frac_out"] < 20 / 24)
        flt.register("flat_output", lambda s: np.ptp(s["output_window"]) == 0)
        self.flt = flt
        return flt
