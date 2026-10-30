# Adapter harness notes

How to plug a new (time series, aligned text) source into MTBench with the shared tooling. The harness adds files only; the existing domain scripts, `evaluation/` and `path.py` are unchanged.

| Piece | File |
|---|---|
| Adapter interface, `SampleFilter`, `log_fetch` | `src/mtbench/adapters/base.py` |
| Sample schema, `make_meta`, `validate_sample`, `write_sample` | `src/mtbench/adapters/schema.py` |
| Filters and text dedup | `src/mtbench/adapters/filters.py` |
| Audit functions | `src/mtbench/audit.py` |
| Constants (`POST_CUTOFF_DATE`, missing threshold, MinHash settings) | `src/mtbench/config.py` |
| Keys, `redact`, loggers | `src/mtbench/env.py` |
| Tests | `tests/test_common.py` |

## 1. Adding a source

1. Create `scripts/sources/<source>.py` with a subclass of `SourceAdapter` and a short README section.
2. Set `name` (the folder under `data/raw/` and `data/processed/`), `domain`, and `out_subdir` (for example `aligned_in7days_out1days`). Raw files go in `data/raw/<name>/`, output in `data/processed/<name>/<out_subdir>/`.
3. Implement the five steps:
   - `download()`: the only method that may use the network. Call `log_fetch(self.name, url)` for every URL; it appends to `data/raw/<name>/MANIFEST.md` with key values redacted. Ask before downloading more than 2 GB.
   - `load_ts()`, `load_text()`: read the raw files into whatever structure `align()` needs.
   - `align()`: pair each text with its entity's series and cut the input and output windows.
   - `make_samples()`: return a list of schema dicts (below). Use `make_meta(...)` for `meta`.
4. Override `sample_filter()` to return a `SampleFilter` with the source's expected window lengths and the existing MTBench windows:

```python
from mtbench.adapters.base import SampleFilter, SourceAdapter
from mtbench.adapters.filters import load_mtbench_windows
from mtbench.adapters.schema import make_meta
from mtbench.path import resolve_weather_data_dir


class MySource(SourceAdapter):
    name = "my_source"
    domain = "weather"
    out_subdir = "aligned_in7days_out1days"

    def sample_filter(self):
        windows = load_mtbench_windows([resolve_weather_data_dir()])
        return SampleFilter(mtbench_windows=windows, expected_in=168, expected_out=24)

    # download, load_ts, load_text, align, make_samples ...


if __name__ == "__main__":
    MySource().run()  # writes survivors, prints the kept/dropped table
```

`run()` pushes every sample through the filter, writes the survivors with `write_sample` (strict JSON, `NaN` becomes `null`) and prints the table.

## 2. Sample schema

The weather schema plus `meta`. Readers use `data.get(...)`, so the extra key is tolerated by existing code.

| Field | Type | Notes |
|---|---|---|
| `text` | str | |
| `input_timestamps`, `output_timestamps` | list[str] | `"YYYY-MM-DD HH:MM:SS"`; epoch seconds are also accepted |
| `input_window`, `output_window` | list[float or None] | |
| `meta.source`, `meta.domain` | str | |
| `meta.entity_id` | str | station, storm, region, commodity; used for the MTBench overlap check |
| `meta.issue_time` | str | when the text was issued, on the same clock as the timestamps |
| `meta.text_kind` | str | `report_of_past`, `forecast_of_future` or `mixed` |
| `meta.has_numeric_forecast` | bool | the text states numeric values for the output window |
| `meta.event_extends_into_target` | bool | dropped by default (`keep_event_extends_into_target=True` keeps them) |
| `meta.post_cutoff` | bool | derived by `make_meta` from the first output timestamp and `config.POST_CUTOFF_DATE` (2025-07-01); never set by hand |
| `meta.split_group` | str | storm id, season or station; a group must never appear in two of train, test and audit |

Put all timestamps and `issue_time` on one clock (the existing weather data uses local standard time) and convert before building the sample; comparisons are made on the parsed values with no time-zone handling.

## 3. Filters and their reasons

`SampleFilter` stops at the first failing rule and counts it. Order and reasons:

| Reason | Rule |
|---|---|
| `invalid_schema` | `validate_sample` reports a problem |
| `text_after_input_end` | `issue_time` is later than the last input timestamp |
| `event_extends_into_target` | flag set in `meta` |
| `ts_missing_ge70pct` | 70% or more of the input or output window is missing |
| `ts_window_incomplete` | wrong length, non-increasing timestamps, or no usable last input value |
| `overlaps_mtbench` | input to output span intersects an existing MTBench window at the same `entity_id` (same logic as `noaa_to_mtbench.py`) |
| your own | `flt.register("reason", lambda sample: bool)` |
| `dup_exact`, `dup_near` | normalized-text hash, then MinHash (word 5-shingles, Jaccard 0.9) |

Dedup runs last so that a sample dropped for another reason doesn't use up its text. It is global to the run, not per entity, because boilerplate shared between entities is what it should catch.

For the existing windows, entities come from file names (`<station>_<k>.json`); folders starting with `noaa_` are skipped, as in the original script.

### Leakage rules per source type

Forecast text (AFD, NHC, SWPC, SEP) legitimately describes the future. What leaks is text or data created after the anchor: Storm Events narratives, FOMC minutes (use the release date, not the meeting date), revised values (GDP, ILINet, EIA, WASDE vintages), and HURDAT2 best track. Store the real publication time in `issue_time`. See `docs/pipeline_notes.md` section 2.

## 4. Auditing a source

Call these on the list of samples before and after filtering:

```python
from mtbench import audit

audit.leakage_scan(samples, patterns=None)     # {rate, n_hits, n, examples[:20]}; pass source-specific patterns
audit.persistence_baseline(samples)            # last-value and seasonal-naive MAE
audit.text_only_proxy(samples)                 # TF-IDF + ridge, grouped CV by split_group
audit.ts_only_proxy(samples)                   # same target, TS summary features
audit.joint_headroom(samples)                  # text_helps_frac, ts_helps_frac (rough indicator)
audit.length_stats(samples)                    # tokens, lengths, missingness, per-group counts
audit.dump_review_sheet(samples, n=40, path="review.csv")
```

- The proxies predict `(mean(output) - last input) / std(input)` and report the mean absolute error of that. Compare `mae` with `mean_predictor_mae` and `zero_predictor_mae` (persistence) in the same result; a proxy that does not beat them has found no signal.
- They need at least two distinct `split_group` values and use `min(5, n_groups)` folds.
- `joint_headroom` reads the two out-of-fold errors: `text_helps_frac` is the share of samples where the TS-only error is above its median and the text-only error is lower, and `ts_helps_frac` is the reverse. It is a heuristic, not an estimate of what a joint model gains.
- `persistence_baseline` infers the seasonal period from the timestamp step (24 for hourly, 8 for 3-hourly, 7 for daily, 52 for weekly, 12 for monthly). Pass `season_length` to override it.
- The default leakage patterns look for numbers with units, percent chances and "will rise to N" phrasing. They are a starting point; pass your own for each source.
- The review sheet is a seeded round-robin over `split_group` and `text_kind`, with the text cut to 600 characters. Read it before trusting any number.

## 5. Keys and logging

- Keys come from `.env` (gitignored): `FRED_API_KEY`, `EIA_API_KEY`, `DELPHI_EPIDATA_API_KEY`, `QUICK_STATS_API_KEY`. Use `env.get_key("NAME")`; it raises a clear error when the key is missing.
- api.weather.gov needs a descriptive User-Agent. Set `NWS_USER_AGENT` in `.env` (an app name and a contact) and use `env.get_user_agent()`.
- Use `env.get_logger(name)` for logging and `env.redact(text)` for anything else you write. `redact` strips the values of the known keys and any `*_API_KEY`, `*_TOKEN` or `*_SECRET` environment variable, key-like URL query parameters (EIA takes its key in the URL) and `Authorization` headers.
- Never paste a key into code, a notebook, a MANIFEST or a report. `tests/test_common.py` fails if a `.env` value or a key-like assignment appears in a tracked or untracked-but-not-ignored file, in `data/raw/*/MANIFEST.md`, or under `logs/`.

## 6. Out of scope

Evaluation prompts and metrics still assume hourly temperature data (see `docs/pipeline_notes.md` section 2, item 4). Adapters produce data only.
