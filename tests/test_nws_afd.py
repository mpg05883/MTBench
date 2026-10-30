from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from mtbench.adapters.nws_afd import (
    NwsAfdAdapter,
    clean_afd,
    covering_text,
    has_numeric_temperature,
    parse_afd_file,
)
from mtbench.adapters.schema import REQUIRED_KEYS, Meta, validate_sample

RAW = """\x01
FXUS63 KDMX 010529
AFDDMX

Area Forecast Discussion
National Weather Service Des Moines IA
1129 PM CST Tue Dec 31 2024

.KEY MESSAGES...
- Highs in the 30s Wednesday.

&&

.SHORT TERM...Through Tonight...
Lows near 15 tonight with winds 10 to 15 mph.

&&

.LONG TERM...Friday through Tuesday...
Highs in the 50s.

&&

.AVIATION /06Z TAFS THROUGH 06Z THURSDAY/...
VFR.

&&

.DMX WATCHES/WARNINGS/ADVISORIES...
None.

&&

$$

DISCUSSION...Small
\x03"""


def test_clean_afd_strips_boilerplate():
    text, names = clean_afd(RAW)
    assert names == ["KEY MESSAGES", "SHORT TERM", "LONG TERM", "AVIATION"]
    for gone in ("FXUS63", "Area Forecast Discussion", "National Weather Service", "&&", "$$",
                 "WATCHES", "Small"):
        assert gone not in text
    assert text.startswith(".KEY MESSAGES...") and "VFR." in text


def test_numeric_flag_regex():
    assert has_numeric_temperature("Highs in the 80s today.")
    assert has_numeric_temperature("A low near 45 tonight.")
    assert has_numeric_temperature("Temperatures around 70 expected.")
    assert not has_numeric_temperature("Winds around 15 mph, gusts near 30 knots.")
    assert not has_numeric_temperature("Cooler with highs well below normal.")


def test_covering_text_follows_horizon():
    text, _ = clean_afd(RAW)
    short = covering_text(text, 3, 27)
    assert "Lows near 15" in short and "Highs in the 50s" not in short and "VFR" not in short
    assert "Highs in the 50s" in covering_text(text, 80, 120)


def test_parse_afd_file_issue_time():
    prods = parse_afd_file(RAW, datetime(2025, 1, 1), datetime(2025, 2, 1))
    assert [p["issue_utc"] for p in prods] == [datetime(2025, 1, 1, 5, 29)]
    assert prods[0]["wfo"] == "DMX"


class FakeAdapter(NwsAfdAdapter):
    """Adapter on synthetic data: one station, hourly temperature, AFDs every 6h at xx:30 UTC."""

    def __init__(self, setting, afd_hours=None, **kw):
        super().__init__(setting=setting, start_year=2022, end_year=2022, check_overlap=False, **kw)
        self.afd_hours = afd_hours

    def resolve_stations(self, fetch=True):
        return {"STN1": {"lat": 40.0, "lon": -100.0, "offset_h": -6, "wfo": "DMX"}}

    def load_ts(self):
        idx = pd.date_range("2021-01-01", "2023-12-31 23:00", freq="h")
        vals = pd.Series(10 + 8 * np.sin(np.arange(len(idx)) / 24 * 2 * np.pi), index=idx)
        return {"STN1": (vals, pd.Series(True, index=idx))}

    def load_text(self):
        times = pd.date_range("2021-12-30", "2023-01-02", freq="6h") + pd.Timedelta(minutes=30)
        if self.afd_hours is not None:
            times = times[times.hour.isin(self.afd_hours)]
        recs = [{"wfo": "DMX", "issue_utc": t.to_pydatetime(), "text": f".DISCUSSION...\nHighs in the 40s {t}.",
                 "sections": ["DISCUSSION"]} for t in times]
        return {"DMX": ([r["issue_utc"] for r in recs], recs)}


@pytest.fixture(params=[("short", 168, 24), ("long", 336, 72)])
def samples(request, tmp_path, monkeypatch):
    setting, n_in, n_out = request.param
    adapter = FakeAdapter(setting)
    monkeypatch.setattr(type(adapter), "out_dir", property(lambda self: tmp_path))
    adapter.sample_filter()
    return adapter.make_samples(), n_in, n_out


def test_window_lengths_and_hourly_monotonic(samples):
    out, n_in, n_out = samples
    assert out
    for s in out:
        assert len(s["input_timestamps"]) == len(s["input_window"]) == n_in
        assert len(s["output_timestamps"]) == len(s["output_window"]) == n_out
        stamps = pd.to_datetime(s["input_timestamps"] + s["output_timestamps"])
        assert (np.diff(stamps.values) == np.timedelta64(1, "h")).all()


def test_no_afd_after_input_end(samples):
    out, _, _ = samples
    for s in out:
        m = s["meta"]
        assert pd.Timestamp(m["issue_time"]) <= pd.Timestamp(s["input_timestamps"][-1])
        assert 0 <= m["afd_gap_hours"] <= 6
        assert validate_sample(s) == []


def test_schema_keys_match(samples):
    out, _, _ = samples
    for s in out:
        assert set(REQUIRED_KEYS) <= set(s)
        assert set(Meta.__annotations__) <= set(s["meta"])
        assert s["meta"]["text_kind"] == "forecast_of_future" and s["meta"]["domain"] == "weather"
        assert isinstance(s["meta"]["sections"], list)


def test_anchor_spacing_at_least_48h():
    ends = FakeAdapter("short").anchors("STN1")
    assert all(b - a >= timedelta(hours=48) for a, b in zip(ends, ends[1:]))


def test_gap_over_6h_is_skipped():
    adapter = FakeAdapter("short", afd_hours=[0])  # AFDs only at 00:30 UTC = 18:30 local -> 4.5h before 23:00
    adapter.sample_filter()
    assert adapter.make_samples()
    adapter = FakeAdapter("short", afd_hours=[12])  # 12:30 UTC = 06:30 local -> 16.5h gap
    flt = adapter.sample_filter()
    assert adapter.make_samples() == []
    assert flt.dropped["afd_gap_gt_6h"] > 0
