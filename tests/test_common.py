import json
import logging
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from conftest import build_sample
from dotenv import dotenv_values

from mtbench import audit, config, env
from mtbench.adapters import filters
from mtbench.adapters.base import SampleFilter
from mtbench.adapters.schema import make_meta, validate_sample, write_sample

ROOT = Path(__file__).resolve().parents[1]


# ---- filters ----------------------------------------------------------------------------

def test_issue_time_must_not_follow_input_end():
    ok = build_sample(issue_time="2024-01-07 23:00:00")  # last input hour is 23:00 on Jan 7
    late = build_sample(issue_time="2024-01-08 00:00:00")
    assert filters.check_issue_time(ok) is None
    assert filters.check_issue_time(late) == "text_after_input_end"


def test_missing_boundary_is_ge_70_percent():
    n = 10
    at_70 = build_sample(n_in=n, in_values=[None] * 7 + [1.0] * 3)
    below = build_sample(n_in=n, in_values=[None] * 6 + [1.0] * 4)
    assert filters.check_missing(at_70) == "ts_missing_ge70pct"
    assert filters.check_missing(below) is None
    out_missing = build_sample(n_out=10, out_values=[None] * 8 + [1.0, 2.0])
    assert filters.check_missing(out_missing) == "ts_missing_ge70pct"


def test_complete_checks_length_order_and_last_value():
    s = build_sample(n_in=24, n_out=12)
    assert filters.check_complete(s, 24, 12) is None
    assert filters.check_complete(s, 48, 12) == "ts_window_incomplete"
    s["input_window"][-1] = None
    assert filters.check_complete(s) == "ts_window_incomplete"
    bad = build_sample()
    bad["output_timestamps"][1] = bad["output_timestamps"][0]
    assert filters.check_complete(bad) == "ts_window_incomplete"


def _write_existing(root: Path, folder: str, name: str, start: str, n_in=24, n_out=24):
    s = build_sample(start=start, n_in=n_in, n_out=n_out)
    d = root / folder
    d.mkdir(parents=True)
    (d / f"{name}.json").write_text(
        json.dumps({k: s[k] for k in s if k != "meta"}), encoding="utf-8"
    )


def test_overlap_with_existing_windows_same_entity_only(tmp_path):
    _write_existing(tmp_path, "aligned_in7days_out1days", "STN1_3", "2024-01-06 00:00:00")
    _write_existing(tmp_path, "noaa_aligned_in7days_out1days", "STN9_2024-01-06", "2024-01-06 00:00:00")
    windows = filters.load_mtbench_windows([tmp_path])
    assert set(windows) == {"STN1"}  # noaa_* folders are skipped
    inside = build_sample(entity="STN1", start="2024-01-06 12:00:00")
    other_entity = build_sample(entity="STN2", start="2024-01-06 12:00:00")
    later = build_sample(entity="STN1", start="2024-02-01 00:00:00")
    assert filters.check_overlap(inside, windows) == "overlaps_mtbench"
    assert filters.check_overlap(other_entity, windows) is None
    assert filters.check_overlap(later, windows) is None


def test_exact_and_near_duplicate_text():
    base = (
        "Forecast discussion for the region. A cold front moves through Tuesday with heavy rain "
        "likely across the northern counties and gusty winds along the coast through the evening. "
        "Temperatures fall into the 40s by Wednesday morning and stay below normal into the weekend. "
        "Confidence is high in the timing of the front but lower in the exact rainfall totals, "
        "with the heaviest bands expected to set up near the river valleys late Tuesday night. "
        "The next update will be issued early Wednesday once the latest model guidance arrives."
    )
    d = filters.TextDeduper()
    assert d.check(base) is None
    assert d.check(base.upper()) == "dup_exact"
    assert d.check(base.replace("40s", "30s")) == "dup_exact"  # digits are normalized away
    assert d.check(base + " Details to follow.") == "dup_near"
    assert d.check("A completely different note about solar flares and geomagnetic activity.") is None


# ---- SampleFilter -------------------------------------------------------------------------

def test_sample_filter_counts_each_reason_and_prints_table(capsys):
    flt = SampleFilter(expected_in=48, expected_out=24)
    samples = [
        build_sample(entity="A", text="alpha bravo charlie delta echo foxtrot golf hotel"),
        build_sample(entity="B", text="alpha bravo charlie delta echo foxtrot golf hotel"),  # dup
        build_sample(entity="C", issue_time="2024-02-01 00:00:00", text="india juliet kilo lima"),
        build_sample(entity="D", text="mike november oscar papa", event_extends_into_target=True),
        build_sample(entity="E", text="quebec romeo sierra tango", n_in=47),
    ]
    kept = [flt.apply(s) for s in samples]
    assert kept == [True, False, False, False, False]
    assert flt.kept == 1
    assert flt.dropped == {
        "dup_exact": 1,
        "text_after_input_end": 1,
        "event_extends_into_target": 1,
        "ts_window_incomplete": 1,
    }
    flt.report()
    out = capsys.readouterr().out
    assert "kept" in out and "dup_exact" in out and "total" in out


def test_sample_filter_flag_and_custom_rule():
    s = build_sample(event_extends_into_target=True)
    assert SampleFilter(keep_event_extends_into_target=True).apply(s)
    flt = SampleFilter()
    flt.register("short_text", lambda x: len(x["text"]) < 100)
    assert not flt.apply(build_sample())
    assert flt.dropped["short_text"] == 1


def test_dropped_samples_do_not_register_text_for_dedup():
    flt = SampleFilter()
    text = "one two three four five six seven eight nine ten"
    assert not flt.apply(build_sample(text=text, issue_time="2025-01-01 00:00:00"))
    assert flt.apply(build_sample(text=text))


# ---- schema -----------------------------------------------------------------------------

def test_post_cutoff_boundary():
    assert config.POST_CUTOFF_DATE == "2025-07-01"
    before = build_sample(start="2025-06-28 00:00:00", n_in=24, n_out=24)  # output starts 06-29
    after = build_sample(start="2025-06-30 12:00:00", n_in=24, n_out=24)  # output starts 07-01 12:00
    assert before["meta"]["post_cutoff"] is False
    assert after["meta"]["post_cutoff"] is True


def test_post_cutoff_constant_defined_once():
    hits = [
        p for p in (ROOT / "src").rglob("*.py") if "2025-07-01" in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in hits] == ["config.py"]


def test_validate_sample_rejects_bad_input(sample):
    assert validate_sample(sample) == []
    sample["meta"]["text_kind"] = "rumor"
    assert any("text_kind" in p for p in validate_sample(sample))
    with pytest.raises(ValueError):
        make_meta(
            source="s", domain="d", entity_id="e", issue_time="2024-01-01 00:00:00",
            text_kind="nope", has_numeric_forecast=False, split_group="g",
            output_timestamps=["2024-01-02 00:00:00"],
        )


def test_write_sample_is_strict_json(tmp_path, sample):
    sample["input_window"][0] = float("nan")
    path = write_sample(sample, tmp_path, "x")
    loaded = json.loads(path.read_text(), parse_constant=lambda c: pytest.fail(c))
    assert loaded["input_window"][0] is None


# ---- env / redaction ----------------------------------------------------------------------

def test_get_key_missing_raises_clear_error(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        env.get_key("FRED_API_KEY")
    monkeypatch.delenv("NWS_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="NWS_USER_AGENT"):
        env.get_user_agent()


def test_redact_text_url_and_logger(monkeypatch, caplog):
    fake = "fake" + "Key" + "0123456789abcdef"
    monkeypatch.setenv("EIA_API_KEY", fake)
    assert fake not in env.redact(f"calling with {fake}")
    url = "https://api.example.org/v2/data?frequency=hourly&api_key=" + "z" * 20 + "&length=5"
    red = env.redact(url)
    assert "z" * 20 not in red and "frequency=hourly" in red and "length=5" in red
    assert "secret-token-value" not in env.redact("Authorization: Bearer secret-token-value")
    logger = env.get_logger("mtbench.test")
    with caplog.at_level(logging.INFO, logger="mtbench.test"):
        logger.info("fetching %s", url + "&x=" + fake)
    assert fake not in caplog.text and "z" * 20 not in caplog.text


def test_log_fetch_writes_redacted_manifest(monkeypatch, tmp_path):
    from mtbench.adapters import base

    monkeypatch.setattr(base, "resolve_raw_data_dir", lambda: tmp_path)
    base.log_fetch("toy", "https://x.org/a?api_key=" + "q" * 20)
    text = (tmp_path / "toy" / "MANIFEST.md").read_text()
    assert "https://x.org/a" in text and "q" * 20 not in text


# ---- audit smoke tests -----------------------------------------------------------------------

def _toy_set(n=60):
    rng = np.random.default_rng(0)
    out = []
    for i in range(n):
        shift = float(rng.normal())
        word = "warming" if shift > 0 else "cooling"
        out.append(
            build_sample(
                entity=f"S{i % 6}",
                issue_time="2024-01-07 12:00:00",
                text=f"Expect {word} trend with {rng.integers(1, 9)} inches possible id{i}",
                group=f"g{i % 6}",
                text_kind=["report_of_past", "forecast_of_future", "mixed"][i % 3],
                out_values=[10.0 + shift * 3] * 24,
            )
        )
    return out


def test_audit_functions_run_on_toy_set(tmp_path):
    samples = _toy_set()
    scan = audit.leakage_scan(samples)
    assert scan["n_hits"] == len(samples) and len(scan["examples"]) == 20
    assert audit.leakage_scan(samples, [r"zzz-no-match"])["rate"] == 0.0

    base = audit.persistence_baseline(samples)
    assert base["last_value_mae"] > 0 and base["n_seasonal_fallback"] == 0

    text, ts = audit.text_only_proxy(samples), audit.ts_only_proxy(samples)
    assert text["n_splits"] == 5 and text["mae"] < text["mean_predictor_mae"]
    assert np.isfinite(ts["mae"])

    head = audit.joint_headroom(samples)
    assert 0 <= head["text_helps_frac"] <= 1 and 0 <= head["ts_helps_frac"] <= 1

    stats = audit.length_stats(samples)
    assert stats["n"] == 60 and stats["per_split_group"]["g0"] == 10

    df = audit.dump_review_sheet(samples, n=12, path=tmp_path / "r.csv")
    assert len(df) == 12 and df["text"].str.len().max() <= 600
    assert df["text_kind"].nunique() == 3 and df["split_group"].nunique() == 6
    assert (tmp_path / "r.csv").exists()


def test_proxy_needs_two_groups():
    with pytest.raises(ValueError):
        audit.text_only_proxy([build_sample(group="only") for _ in range(4)])


# ---- secrets ---------------------------------------------------------------------------------

# The value must contain a digit so identifiers like api_key=ANTHROPIC_API_KEY don't match.
KEY_LIKE = re.compile(
    r"""(api[_-]?key|token|secret)\s*[:=]\s*["']?(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{16,}""",
    re.IGNORECASE,
)


def _git(*args) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.split("\0" if "-z" in args else "\n") if line]


def _scan_targets() -> list[Path]:
    """Tracked and untracked-but-not-ignored files, plus ignored places that may hold logs."""
    names = set(_git("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    paths = {ROOT / n for n in names}
    paths |= set((ROOT / "data" / "raw").glob("*/MANIFEST.md"))
    for folder in ("logs", "save"):
        paths |= {p for p in (ROOT / folder).rglob("*") if p.is_file()}
    skip = {"uv.lock", ".env"}
    return sorted(p for p in paths if p.is_file() and p.name not in skip)


def _text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def test_env_file_is_ignored_and_untracked():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ".env" not in _git("ls-files")


def test_no_key_values_in_files():
    secrets = {
        k: v
        for k, v in dotenv_values(ROOT / ".env").items()
        if v and len(v) >= env.MIN_SECRET_LEN
    }
    leaks = []
    for path in _scan_targets():
        text = _text(path)
        if text is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        leaks += [f"{rel}: value of {k}" for k, v in secrets.items() if v in text]
        leaks += [f"{rel}: key-like assignment" for _ in KEY_LIKE.finditer(text)]
    assert not leaks, "key-looking strings found:\n" + "\n".join(leaks)
