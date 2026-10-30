# MTBench pipeline notes

Read-only study of the existing pipeline and of the 10 candidate sources in `docs/new_sources.md`. Nothing was downloaded or modified to produce this.

Confidence tags used in section 3: **V** = checked against the publisher's page during this study; **U** = from memory, verify before relying on it.

## 0. How the pipeline works

There is no central loader or dataset class. The "pipeline" is per-domain preparation scripts, a small path helper, and evaluation scripts that glob a folder of JSON.

**Raw data.** `download_raw_dataset.py` pulls four HF datasets into `data/raw/{finance,weather}/...`. `data/raw/` does not exist in this checkout. The local data is `data/processed/{finance,weather}` plus a NOAA drop in `data/noaa-weather/` (`*.npz` and `*_meta.jsonl` per scale: `forecast_hourly`, `forecast_hourly_long`, `forecast_4hourly`, `forecast_daily`, `infill_*`; question rows in `qa/`).

**Alignment (weather, original).** `data_preparation/weather/create_pairs.py`: the anchor is a news item's `END_TIMESTAMP`. The input is `days_before` calendar days ending on the anchor date, and the output is the next `days_after` calendar days. Both are put on an hourly grid, interpolated, then ffill/bfilled. Settings are 7 days in / 1 day out (168 / 24 points) and 14 in / 3 out (336 / 72). The audit in `docs/shortcut_audit.md` (W10) documents a resampling bug that leaves some output windows flat.

**Alignment (weather, NOAA).** `data_preparation/weather/noaa_to_mtbench.py` converts `npz` + `meta.jsonl` into one JSON per `sample_id`. It drops samples whose event extends into the target window, whose events start in the target window, with ≥70% NaN, or that overlap an original MTBench window at the same station. `noaa_qa_to_mtbench.py` makes the QA version, with `extra_series` and `qtype`.

**Alignment (finance).** `data_preparation/finance/create_pairs.py` with `utils.sample_a_stock_pair_flexible_units_given_event`: the anchor is the article's `published_utc`. The input is `[t-W, t)` and the output is `[t, t+H)`, subsampled from 5-minute bars. It then adds `trend`, `technical` and `alignment` fields. Short is 7 days @ 5 min → 1 day; long is 30 days @ 1 h → 7 days. `finance/create_mcqa.py` is empty in this checkout.

**Paths.** `src/mtbench/path.py` only has finance and weather resolvers.

**Prompts and metrics.** `evaluation/{weather,finance}/meta_prompt.py` plus one script per task.
- Modes: `timeseries_only`, `text_only`, `combined`.
- Forecasting: MSE/MAE/RMSE; the prediction is interpolated to the target length; samples with MSE > 100 are excluded from the mean (finance MACD uses 10).
- Trend classification: accuracy. Weather labels come from `compute_temperature_trend` (slope ≥ 0.25 or day-to-day diff ≥ 0.5).
- Indicators: weather max/min/diff; finance MACD and Bollinger bands.
- MCQA: letter accuracy.
- Finance only: correlation label.
- `evaluation/utils.py` hard-codes 24 points per day when reshaping.

## 1. Exact sample schema

All families are one JSON per sample (finance aligned pairs are also shipped as parquet). Readers use `data.get(...)`, so extra keys are tolerated.

### Weather aligned (`aligned_in7days_out1days`, `aligned_in14days_out3days`, `noaa_aligned_*`)

| Field | Type | Notes |
|---|---|---|
| `text` | str | Event report; NOAA "no event" controls use a fixed template |
| `input_timestamps` | list[str] | `"YYYY-MM-DD HH:MM:SS"`, hourly |
| `input_window` | list[float] | °C |
| `output_timestamps` | list[str] | |
| `output_window` | list[float] | |
| `hasrain` | bool | Original MTBench only |

File name: `<station>_<k>.json` (NOAA: `<station>_<YYYY-MM-DD>[_ctrl].json`). The station exists only in the file name; there is no location, lat/lon or text timestamp field in the sample. The NOAA `*_meta.jsonl` has them but they are not carried over.

### Weather QA (`QAshort`, `QAlong`, `noaa_QAshort`, `noaa_QAlong`)

`text`, `input_timestamps`, `input_window`, `question` (options embedded as `A) … D)`), `answer` (a letter). Original QA also keeps `output_*`. NOAA QA has no `output_*` and adds `extra_series` (dict of name → list) and `qtype`.

### Finance aligned (`aligned_in7days_out1days`, `aligned_in30days_out7days`)

| Field | Type | Notes |
|---|---|---|
| `input_timestamps`, `output_timestamps` | list[float] | epoch **seconds** |
| `input_window`, `output_window` | list[float] | prices; short = 390 in / 78 out |
| `text` | JSON string (dict in the JSON writer) | `content`, `timestamp_ms`, `published_utc`, `article_url`, `label_type`, `label_time`, `label_sentiment` |
| `trend` | JSON string | input/output/overall % change and bin labels |
| `technical` | JSON string | `in_/out_/overall_` × sma/ema 10/50/200, macd, signal, upper_bb, lower_bb |
| `alignment` | str | `consistent` / `inconsistent` |

### Finance QA (`QAshort`, `QAlong`)

The aligned fields plus `timestamp_ms`, `published_utc`, `article_url`, `news_price_correlation` and `MCQA` = `{question, answer}`. `text` is a plain string here. Ticker and index exist only in the file name `<idx>_<TICKER>.json`.

### Inconsistencies to be aware of

- Timestamps are strings in weather and epoch seconds in finance.
- `text` is a string in weather, a dict or JSON string in finance.
- The entity (station, ticker) lives in the file name.
- Weather prompts hard-code "hourly", "temperature" and "a location in the United States".

## 2. Where a new source plugs in

There is no registry or loader function, so the plug-in point is a convention:

1. `scripts/sources/<source>.py` writes `data/processed/<source>/aligned_in{X}_out{Y}/<entity>_<anchor>.json` in the **weather schema** (string timestamps, `text`, `input_*`, `output_*`). Use `noaa_to_mtbench.py` as the template: argparse, explicit drop rules, overlap check, printed counts.
2. Optional additive fields, safe because readers use `.get`: `source`, `entity_id`, `text_timestamp`, `text_horizon`, `freq`, `variable`. These carry what the file name carries today and make the leakage rule checkable.
3. Add one small resolver per source to `src/mtbench/path.py`, in the existing style.
4. **Evaluation is not adapter-only.** `evaluation/weather/meta_prompt.py` hard-codes temperature, "United States", hourly granularity and 24-point days, and `evaluation/utils.compute_temperature_trend` reshapes by 24. A new source needs its own prompt builder and a granularity-aware metric path. This is outside "add adapters" in CLAUDE.md, so it needs a decision (see open questions).

Checks every adapter should apply (from CLAUDE.md): text timestamp ≤ end of input window; input and output windows complete (no NaN gaps, correct length for the declared frequency); the text's entity matches the series' entity.

### Leakage rule

Forecast text (AFD, NHC, SWPC, SEP) legitimately describes the future; that is the signal being tested. What leaks is text or data created after the anchor: Storm Events narratives (written afterwards), FOMC minutes (released about three weeks after the meeting, so use the release date, not the meeting date), later-revised values (GDP, ILINet, EIA, WASDE vintages), and HURDAT2 best track (post-season reanalysis, not what the forecaster saw). The existing data already has a mild version of this (`shortcut_audit.md` W6: about 6% of weather texts mention the forecast day), so adapters should store `text_timestamp` and filter on it.

## 3. The 10 sources

Output horizons in the current benchmark are short (1–3 days weather, 1–7 days finance). Several sources below naturally have longer horizons or coarser frequency.

### 1. Normal weather: NWS AFDs + GHCNh

- **Download:** AFDs at `https://api.weather.gov/products/types/AFD` (**V**: the page documents the `products/types/{type}` pattern for other products and requires a User-Agent header; it does not document an AFD archive, and `/alerts` is limited to 7 days). For history, the Iowa Environmental Mesonet AFOS text archive (**U**). GHCNh bulk files (PSV or Parquet, by year or location) from `https://www.ncei.noaa.gov/oa/global-historical-climatology-network/index.html#hourly/` and the station list `https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.txt` (**V**; individual file paths **U**).
- **Auth:** none; User-Agent header required for api.weather.gov (**V**).
- **Size:** AFD text roughly 0.5–1 GB per year across all offices (my estimate); GHCNh is small per station but large in total, so restrict to a station list and ask before exceeding 2 GB.
- **Update:** AFDs several times a day per office; GHCNh hourly observations, refresh cadence not stated on the page.
- **Doesn't fit:**
  - One office covers many stations (1:N), so a text maps to several samples and needs an office→station map.
  - The text states a horizon in sections ("Saturday through Wednesday"), up to about 7 days, longer than the current 1–3 day outputs.
  - Issue times are local; convert to the station's window.
  - Overlaps with existing weather windows should be dropped the way `noaa_to_mtbench.py` does.

### 2. Cyclones: NHC discussions + HURDAT2

- **Download:** HURDAT2 Atlantic `https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt` (about 6.8 MB) and NE/N-Central Pacific `.../hurdat2-nepac-1949-2025-092926.txt` (about 4 MB) (**V**). Discussions: `https://www.nhc.noaa.gov/archive/<year>/` (1999–2025 as text, earlier as scans) (**V**); the per-storm discussion page pattern is **U**.
- **Auth:** none.
- **Size:** under 100 MB.
- **Update:** discussions every 6 hours per active storm; HURDAT2 revised annually after the season (**V**: last revisions dated Sept 2026).
- **Doesn't fit:**
  - The entity is a storm ID, not a location, and the storm moves.
  - Multivariate: lat, lon, max wind, pressure. Pressure is −999 for early records.
  - HURDAT2 includes irregular non-synoptic rows (landfall, peak intensity) besides 00/06/12/18 UTC.
  - Storms last days, so a 7-day input is impossible; use roughly 24–72 h in and up to 120 h out.
  - Best track is reanalysed after the fact, so it differs from what the forecaster saw.
  - The text's 5-day forecast table is longer than the output horizon.

### 3. Space weather: SWPC discussion + Kp

- **Download:** the SWPC page redirects to `https://www.spaceweather.gov/products/forecast-discussion` (**V**). Current text `https://services.swpc.noaa.gov/text/discussion.txt` and archive `ftp.swpc.noaa.gov/pub/forecasts/discussion/` (**U**). Kp from GFZ Potsdam (`kp.gfz-potsdam.de`) or `https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json` (**U**).
- **Auth:** none expected.
- **Size:** under 100 MB.
- **Update:** discussion issued daily (exact times **U**); Kp every 3 hours.
- **Doesn't fit:**
  - Global series with no location; the sample has nothing to match, so the entity check is trivial. The existing weather prompts would need a different preamble.
  - Kp is a bounded ordinal with thirds (5−, 5o, 5+), so it needs a numeric mapping.
  - Nowcast Kp and the later definitive Kp differ.
  - The text covers exactly the next 3 days (24 three-hour bins), future by design.
  - The "Detailed List" entry for this source in `new_sources.md` is cut off mid-sentence; use the earlier section.

### 4. Floods and storms: NWS warnings + USGS gauges

- **Download:** NWS flood warning/statement text via the IEM AFOS archive (**U**). Storm Events CSVs at `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_{details,fatalities,locations}-ftp_v1.0_d{YEAR}_c{DATE}.csv.gz`, 1950–2026 (**V**). USGS via the OGC API at `https://api.waterdata.usgs.gov/` (**V**); the legacy `waterservices.usgs.gov/nwis/iv` may still work but its status was not confirmed.
- **Auth:** USGS API key optional, higher rate limits with a key (**V**).
- **Size:** Storm Events details are at most about 16 MB per year, compressed (**V**, units not stated by the listing). USGS 15-minute data is about 35,000 rows per gauge per parameter per year, so restrict to gauges named in warnings.
- **Update:** warnings in real time; gauges every 15 minutes; Storm Events refreshed periodically (**U**).
- **Doesn't fit:**
  - Warnings name NWS location IDs (5 characters), not USGS site numbers; a crosswalk is needed (NWPS gauge metadata includes a USGS id, **U**).
  - Storm Events narratives are written after the event, so they leak unless limited to the real-time warning text.
  - Stage and discharge are two variables with gaps, provisional data, and ice/datum flags.
  - The text predicts a future crest, hours to days ahead, possibly beyond a short output window.

### 5. Macro: FOMC documents + FRED

- **Download:** `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` for the meeting list; statement, minutes and SEP pages follow date-based names such as `fomcminutes{YYYYMMDD}.htm` and `fomcprojtabl{YYYYMMDD}.htm` (**U**). FRED observations at `https://api.stlouisfed.org/fred/series/observations`; ALFRED provides vintages (**U**).
- **Auth:** free FRED API key.
- **Size:** under 100 MB.
- **Update:** 8 meetings a year, SEP 4 times a year; minutes about 3 weeks after each meeting; FRED series monthly or quarterly.
- **Doesn't fit:**
  - SEP is annual year-end projections for the next three years plus longer run, not quarterly values as `new_sources.md` says.
  - Quarterly/monthly frequency does not fit the hourly-based evaluation code.
  - About 60 samples in total (roughly 15 years × 4).
  - GDP and PCE are revised, so use vintages.
  - Global (US) series with no location.
  - Minutes should be timestamped at release, not at the meeting.

### 6. Agriculture: WASDE

- **Download:** USDA ESMIS at `https://usda.library.cornell.edu` (WASDE publication; API requires a key, **U**). USDA FAS PSD API `api.fas.usda.gov` and NASS Quick Stats as alternatives for series (**U**).
- **Auth:** free API keys (**U**).
- **Size:** under 1 GB.
- **Update:** monthly, around the 9th–12th at noon ET.
- **Doesn't fit:**
  - Each report restates the whole marketing-year balance sheet; the "time series" is a sequence of forecast vintages rather than observations.
  - Many commodity × U.S./world combinations, and marketing years do not match calendar years.
  - Monthly gives about 12 samples per commodity per year.
  - Global with no location; the entity is the commodity.
  - Text and numbers share one timestamp, so the input window must end before the report that provides the text.

### 7. Finance: Haiwen's multimodal stock dataset

- **Download:** not in the repo or docs; the location is unknown.
- **Doesn't fit / unknown:** `new_sources.md` says "already aligned." The existing finance schema uses epoch-second timestamps, 5-min or 1-h bars, and a text dict. Need the path and format to confirm it matches or needs conversion.

### 8. Energy: STEO + grid alerts + EIA-930

- **Download:** EIA API v2 `https://api.eia.gov/v2/` with route `/electricity/rto` for the EIA-930 style regional data (**V**). The page does not document a STEO route. Bulk `https://www.eia.gov/opendata/bulk/EBA.zip` (**U**). STEO PDFs at `eia.gov/outlooks/steo/archives` (**U**). DOE OE-417 annual spreadsheets (**U**). ISO notices and prices from ERCOT, CAISO OASIS, PJM Data Miner (**U**).
- **Auth:** EIA key, passed in the URL, not a header (**V**); PJM needs a key (**U**).
- **Size:** EBA bulk may exceed 2 GB; ask before downloading.
- **Update:** STEO monthly; EIA-930 hourly; alerts irregular.
- **Doesn't fit:**
  - Mixed frequencies: monthly prices and stocks, hourly demand, 5-minute ISO prices.
  - Entities are balancing authorities or ISOs with their own identifiers, plus DST and time-zone handling.
  - Price spikes of 100× break the MSE>100 filter and scale-based metrics.
  - There is no central archive of alerts.
  - "Busted" alerts need matched negative samples.
  - This is the largest adapter effort; consider splitting into STEO-only and grid-alert sub-sources.

### 9. Transportation: ATCSCC advisories + airport operations

- **Download:** advisories on `https://www.fly.faa.gov/adv/` (archive depth **U**). Delay data from BTS On-Time Performance (flight-level, includes TaxiOut/TaxiIn) or FAA ASPM/OPSNET (**U**).
- **Auth:** ASPM and OPSNET need registration (**U**); BTS none.
- **Size:** BTS around 200 MB or more per month as CSV (**U**), so several years exceed 2 GB; ask first.
- **Update:** advisories in real time; BTS monthly.
- **Doesn't fit:**
  - No public 15-minute airport delay series; it would have to be derived from flight-level records.
  - Advisories are often national or per-facility, not per-airport.
  - ICAO is "K" + IATA for the contiguous US.
  - Ground stops and expected delays are forward-looking.
  - Whether a usable advisory archive exists is unconfirmed. This is the highest-risk source.

### 10. Healthcare: FluView + ILINet

- **Download:** Delphi Epidata `https://api.delphi.cmu.edu/epidata/fluview/` (**V**: requires `epiweeks` and `regions`). Lab positivity through the clinical endpoint (**U**). CDC weekly narrative pages under `cdc.gov/fluview/surveillance/` (**U**).
- **Auth:** none, optional key (**U**).
- **Size:** under 100 MB.
- **Update:** weekly, published on Fridays for the previous MMWR week.
- **Doesn't fit:**
  - Weekly frequency and MMWR-week to date mapping, including week 53.
  - Summer gaps between seasons.
  - ILINet is back-filled, so use the issue/vintage parameter to avoid leakage.
  - The entity is an HHS region or state, which maps cleanly to a location field.
  - At best about 600 samples per region, and the text is narrative about the current week.

## 4. Cross-cutting issues

- **Frequency.** Evaluation assumes hourly data and 24-point days. Monthly, weekly and quarterly sources need a `freq` field and a non-24 path.
- **Entity.** Global series (Kp, FOMC, WASDE) have no location; prompts must not say "location in the United States".
- **Sample counts.** Macro, agriculture and flu will have tens to hundreds of samples. Decide if that is acceptable.
- **Repo mismatches.** `data/raw/<source>/` and `scripts/sources/` from CLAUDE.md do not exist yet; the NOAA data sits in `data/noaa-weather/`; the README mentions `requirements.txt` but the file is `requirement.txt`; `data_preparation/finance/create_mcqa.py` is empty.
- **Data quality in the base data.** See `docs/shortcut_audit.md`; adapters should avoid reproducing W6 (text naming the forecast day) and W10 (flat windows).

## 5. Decisions

1. **Source 7 (Haiwen's dataset):** skipped for now until its location and format are known.
2. **Eval scope:** adapters produce data only. No changes under `evaluation/` for now; prompt and metric support for non-hourly or location-free sources is a later, separate step.
3. **First adapter:** NWS AFD + GHCNh (source 1). Sources 8 and 9 remain the riskiest and are deferred.
