# MTBench preliminary shortcut audit

Audit of possible shortcuts an LLM could use to answer MTBench questions without doing the intended multimodal reasoning. Done before running any model, so everything here is a **heuristic baseline computed from the data**, not a model result. Each shortcut lists the statistic and real examples (file names refer to `data/processed/...`).

## Scope and method

- **Weather (original MTBench):** aligned pairs `aligned_in7days_out1days` / `aligned_in14days_out3days` (1,959 samples each; used for forecasting, trend and indicator tasks), and MCQA `QAshort` (645) / `QAlong` (728).
- **Weather (new NOAA data):** `noaa_aligned_in7days_out1days` (7,905), `noaa_aligned_in14days_out3days` (7,871), `noaa_QAshort` (7,905), `noaa_QAlong` (7,871), plus the raw NOAA question rows (58,827 hourly rows) for answer priors.
- **Finance:** aligned pairs from the `train` parquet (750 short, 525 long; there is no other split on disk) and QA `QAshort` (491) / `QAlong` (516).
- Baselines use the same label rules as `evaluation/utils.py` (trend slope >= 0.25 / diff >= 0.5; daily max/min).
- Only the question/option **text** was analysed for style shortcuts. Whether a model actually uses them is untested.

## Summary

| # | Shortcut | Where | Key evidence | Severity |
|---|---|---|---|---|
| W1 | Answer-position prior | weather MCQA | B is correct 43% (short) / 48% (long); chance is 25% | High |
| W2 | Longest option is correct | weather MCQA | 45% / 43% vs 25% chance | High |
| W3 | Hedged vs extreme wording | weather MCQA | "moderate" 5.0x, "slight" 3.5x more likely in the correct option (each appears in only 1-4% of options) | Low-Medium |
| W4 | "Storm means cooling" prior | weather MCQA, trend | 65% of correct options describe a decrease vs 49% an increase; future-trend label is `decreasing` 57% of the time | High |
| W5 | Text-only solvable (no series needed) | weather MCQA | stems restate the event and date from the report | Medium |
| W6 | Report text refers to the forecast day | weather, NOAA | 117/1959 aligned, 42/645 QAshort, 215/7905 NOAA | Medium |
| W7 | Naive forecasts match LLM-level error | weather forecasting | repeat-last-day MSE 21.1 (7d) / 25.7 (14d); mean-of-input 19.4 / 21.0 | High |
| W8 | Label priors (trend / indicators) | weather trend, indicator | majority trend class `decreasing`; day-1 range 7.2 +/- 4.0 C | Medium |
| W9 | Prior knowledge / memorisation / duplicate narratives | weather | 196 samples name a storm; 486 samples share an episode narrative | Medium |
| W10 | Flat output windows (resampling artifact) | weather forecasting, trend, indicator, MCQA | 124/1,959 (7-day) and 108/1,959 (14-day) outputs are one repeated value; also skews 50 `QAshort` questions | High (data quality) |
| N1 | Class imbalance in NOAA questions | NOAA MCQA | thunder `No` 79.5%, joint rain+wind `No` 70.8%, precipitation `none/trace` 63.2% | High |
| N2 | "No event" report is a label cue | NOAA MCQA | thunder `Yes` 8.5% without an event vs 32.8% with | Medium |
| F1 | Majority-class trend label | finance trend | `-2% ~ +2%` is 68% (short) / 39% (long) | High (short) |
| F2 | News sentiment tags the outcome | finance trend | see section F2 (Bullish -> price up ~79-88%) | High |
| F3 | Indicator targets have fixed starting values | finance indicators | `out_macd[0] == 0` and `out_upper_bb[0]` is NaN for 100% of samples | Medium |
| F4 | Persistence + price-scale | finance forecasting | last-value MAPE 1.9% (short) / 3.4% (long) | High |
| F5 | Prior knowledge of 2021-2023 stocks | finance | ticker + publish date + quoted prices in the article | Medium |
| F6 | Correlation label is ~ output direction / momentum | finance correlation | label sign matches output direction 71-78%, input trend 63-66% | High |
| F7 | Hedged vs absolute wording | finance MCQA | false options use "will", "solely", "directly"; true options hedge | High |

Severity is a judgement of how much a shortcut could inflate accuracy relative to the intended skill, not a measured effect.

---
# Weather

## W1. Answer-position prior (MCQA)

| Folder | A | B | C | D |
|---|---|---|---|---|
| QAshort (n=644) | 19.4% | 42.9% | 26.6% | 11.2% |
| QAlong (n=725) | 12.3% | 48.0% | 28.0% | 11.7% |

Always answering `B` scores about 43-48%; `A` is rare. A model with a positional bias, or one that has learned the generator's habits, gets this for free. Examples (answer marked `*`, option text trimmed):

```text
QAshort/USW00003947_31.json
  stem: Given the temperature trend observed in time series A leading up to the severe weather events reported on June 21, and considering that a Tropical Air Mass typically contributes to severe thunderstorm ...
  A  (129 chars) The temperatures in time series B are expected to drop significantly due to cold air advection following the t ...
  B* (144 chars) The temperature in time series B will show a marked increase as the warm air ahead of the cold front continues ...
  C  (126 chars) The temperature trends in time series B are irrelevant as they do not correlate with the severity of the prior ...
  D  (124 chars) The temperature on June 22 will remain steady because the thunderstorms have minimal effect on local atmospher ...
```

```text
QAshort/USW00094823_31.json
  stem: Based on the temperature trends in time series A leading up to the weather events reported on September 9, 2015, and considering the typical atmospheric responses to heavy rainfall and thunderstorms, ...
  A  (148 chars) The significant cooling reflected in time series B is primarily due to the increase in solar radiation followi ...
  B* (153 chars) The decline in temperatures is expected as a direct consequence of the flash flooding events, which typically ...
  C  (172 chars) The temperature drop in time series B corresponds with a seasonal transition marked by the onset of autumn, wh ...
  D  (171 chars) The fluctuations in temperature observed in series B arose from an unexpected heat wave that resulted from the ...
```

```text
QAshort/USW00012916_17.json
  stem: Considering the significant thunderstorms, tornado development, and hail events reported on June 19-20, 2023, what is the most likely contributing factor for the drop in temperature observed in the fo ...
  A  ( 64 chars) Increased solar radiation due to clearing skies after the storm.
  B* ( 72 chars) Anomalous cold front passage immediately after the severe weather event.
  C  ( 74 chars) Heightened humidity levels causing a drop in temperature during the night.
  D  ( 70 chars) Persistent warm air advection from the southeast due to high pressure.
```

```text
QAlong/USW00093738_31.json
  stem: Based on the temperature trends in time series A leading up to the weather event and the conditions reported, what can be inferred about the expected temperature change in the subsequent days captured ...
  A  ( 89 chars) Temperature is likely to drop significantly due to the intense thunderstorm and flooding.
  B* ( 77 chars) Temperature will likely rise steadily due to the high humidity from the rain.
  C  ( 85 chars) The temperature should drop sharply due to the cold front following the thunderstorm.
  D  ( 69 chars) The temperature is expected to remain stable with minor fluctuations.
```


## W2. Longest option is correct (MCQA)

The longest option is the correct one in 288/644 (44.7%) of QAshort and 312/725 (43.0%) of QAlong (chance 25%). The correct answer tends to carry the most qualifiers and context.

```text
QAshort/USW00012839_6.json
  stem: Given the 7-day temperature time series A exhibiting a gradual warming trend leading up to May 25, 2020, and considering a subsequent report of severe weather e ...
  A  (144 chars) The tornado activity likely contributed to a sudden increase in temperature readings on May 26, 2020 ...
  B* (217 chars) The reported heavy rainfall and flooding typically result in a cooling effect on temperatures; thus, ...
  C  (166 chars) The significant property damage due to the tornado implies that temperature would stabilize at highe ...
  D  (186 chars) The upper-level troughing described in the weather report suggests continued warming trends even aft ...
```

```text
QAshort/USW00012894_3.json
  stem: Based on the reported weather events, which of the following statements accurately describes the correlation between the weather conditions following Hurricane ...
  A  (202 chars) The drop in temperatures observed on September 15th indicates a direct cooling effect due to the exc ...
  B* (239 chars) The temperatures on September 15th remained stable and only slightly decreased, indicating that desp ...
  C  (196 chars) The increase in temperature the day after the flood event suggests that the region's climate has gro ...
  D  (207 chars) The dramatic drop in temperature following the flood event is a common phenomenon indicating a faile ...
```

```text
QAlong/USW00012849_37.json
  stem: Based on the observed temperatures in time series A leading up to the flood event reported on August 13, 2019, which of the following statements is the most acc ...
  A  (180 chars) The drastic drop in temperature observed in time series B implies a stable weather pattern is establ ...
  B* (234 chars) The sustained cooler temperatures in time series B suggest the lingering effects of the flash flood ...
  C  (211 chars) The trend in temperatures from time series A starting to climb towards the event shows a high likeli ...
  D  (213 chars) Since time series A illustrated consistently high temperatures leading up to the flood, it is expect ...
```

```text
QAlong/USW00023169_11.json
  stem: Considering the extreme weather events reported between September 13 and 16, 2011, what influence do you expect these events to have on the temperature trend ob ...
  A  ( 95 chars) Temperature is likely to remain consistently high due to residual heat from the storm activity.
  B* (147 chars) The temperature is expected to drop significantly as the effects of the flooding and cooling rains f ...
  C  (116 chars) The temperature will stabilize without changes, as weather events have no correlation with temperatu ...
  D  (133 chars) Temperature will rapidly increase over the three days as the atmospheric pressure returns to normal, ...
```


## W3. Hedged vs extreme wording (MCQA)

Probability that a word appears in the correct option vs in a distractor (ratio > 1 favours the correct option):

| Word | Correct | Distractor | Ratio |
|---|---|---|---|
| moderate | 2.8% | 0.6% | 4.96 |
| slight | 3.9% | 1.1% | 3.52 |
| cool | 36.8% | 18.8% | 1.96 |
| likely | 20.5% | 13.5% | 1.52 |
| decrease | 14.0% | 7.5% | 1.85 |
| remain | 6.9% | 11.3% | 0.61 |
| fluctuat | 3.9% | 9.9% | 0.40 |
| minimal | 0.7% | 1.9% | 0.39 |
| dramatic | 1.1% | 2.2% | 0.50 |

Correct options describe measured, moderate changes; distractors are written as extremes ("dramatic", "fluctuating", "no change"). Examples where the correct option contains `moderate`/`slight`:

```text
QAshort/USW00003927_17.json
  stem: Given the severe weather events reported between May 23 and May 28, 2015, including flash floods, tornadoes, and heavy rainfall, what is the most probable tempe ...
  A  (112 chars) A significant drop in temperatures to seasonal lows due to lingering cold air associated with the stalled front.
  B  (110 chars) An immediate increase in temperatures to seasonal highs as the severe weather subsides and clear skies return.
  C* (133 chars) A moderate rise in temperatures leading to highs around 25°C as moisture may still be lingering in the atmosphere, affec ...
  D  (128 chars) Fluctuating temperatures with a drastic drop towards evening due to residual atmospheric disturbances from the tornado a ...
```

```text
QAshort/USW00023234_27.json
  stem: Based on the 7-day temperature time series A and the reported weather events, which of the following statements about the temperature trend and potential impact ...
  A  (272 chars) The significant drop in temperature towards the end of series A suggests that the weather events were likely due to cold ...
  B  (240 chars) The increase in temperature observed prior to the weather events indicates that the region would experience a dramatic r ...
  C* (258 chars) The stabilization of temperatures in series A just before the weather events likely allowed for suitable conditions for ...
  D  (197 chars) The heavy rain and flooding resulted in a notable cooling effect in the area, meaning the temperature for the next day i ...
```

```text
QAlong/USW00024229_1.json
  stem: Considering the temperature trends observed in time series A and the reported weather event on June 4, 2009, which statement best describes the expected tempera ...
  A  (126 chars) The temperature is likely to drop significantly and remain low for several days due to the cooling effect of the thunder ...
  B  (151 chars) Following the thunderstorm, temperatures are expected to rise rapidly due to the rain creating high humidity levels, lea ...
  C* (147 chars) Following the thunderstorm, the temperature is expected to stabilize slightly above the average for the summer, reflecti ...
  D  (113 chars) The temperature will remain low for an extended period, indicating a prolonged cold front after the thunderstorm.
```

```text
QAshort/USW00012844_35.json
  stem: Based on the temperature trends observed from April 18 to April 24, 2018 (time series A) and the reported weather events on April 24, how would you expect the t ...
  A  (144 chars) The temperature would drop dramatically due to the influx of cold air from the storm system, leading to a significant de ...
  B  (148 chars) The temperature would remain fairly stable around the previous day's high, reflecting the typical warming trends in Apri ...
  C* (162 chars) The temperature may slightly decrease due to the cooler air mass from the storm, but it would likely still maintain a ge ...
  D  (142 chars) The temperature could potentially increase, as warm fronts are known to follow severe weather events and raise temperatu ...
```


## W4. "Storm means cooling" prior (MCQA, trend)

- 64.7% of correct options contain decrease wording (drop/decrease/fall/cool/colder/lower...) vs 48.6% with increase wording.
- When exactly one option mentions a decrease, it is the correct option 52.4% of the time (187/357); for a unique increase option it is 37.3%.
- The same prior shows up in the label distribution of the time-series tasks: the *future* trend (next-day mean vs last input day, +/-0.5 C) is `decreasing` for 57.5% of `aligned_in7days_out1days` samples, `increasing` 28.0%, `stable` 14.5% (similar for the 14-day setting: 58.2% / 28.1% / 13.7%). Guessing `decreasing` for every sample gets more than half of them right.

Examples where the unique decrease option is correct:

```text
QAlong/USW00014739_34.json
  stem: Considering the temperature time series A during the period of 2012-10-16 to 2012-10-29, there appears to be a significant cooling trend leading up to a severe ...
  A  (121 chars) The temperatures are likely to increase sharply due to the dissipating effects of high winds from the stalling ...
  B* (103 chars) A gradual decrease in temperature is anticipated as lingering winds from the hurricane cool the region.
  C  (149 chars) The temperatures will fluctuate widely due to the instability brought by the transition from tropical to extra ...
  D  (116 chars) Expect stable and warm temperatures as the storm clears will lead to a sudden high-pressure system taking domi ...
```

```text
QAlong/USW00013904_24.json
  stem: Considering the reported severe weather event in Austin on May 14-15, 2008, which had significant hail and wind impacts, what can be inferred about the potentia ...
  A  (112 chars) After such a storm, temperatures generally rise significantly due to increased solar radiation from clear skie ...
  B* (105 chars) Post-thunderstorm, temperatures typically drop due to enhanced cloud cover and water evaporation effects.
  C  (107 chars) Temperature variations are unrelated to storm events; hence, previous data cannot inform future conditions.
  D  (122 chars) Following a severe thunderstorm, temperatures tend to stabilize with no significant fluctuations over the subs ...
```

```text
QAlong/USW00023174_3.json
  stem: Considering the heavy rain and resulting cold temperatures experienced from January 7th to January 11th, which aspect of temperature trends following the event ...
  A  (119 chars) A gradual increase in temperature leading to above-average highs in the subsequent days due to the tropical in ...
  B* (141 chars) A sustained drop in temperature, coupled with high humidity, due to residual effects of the storm and subseque ...
  C  (110 chars) An immediate spike in temperature due to the heat generated from increased cloud cover and trapping of warmth.
  D  ( 97 chars) A constant temperature without significant fluctuation due to stable weather patterns post-storm.
```


## W5. Question text restates the report (text-only solvable)

The generated stems quote the event, location and date from the report, and the options differ mainly in *which physical story* (cold front vs warm air vs no change) is told. A model can pick the plausible story from the text alone, without reading the series. Below, the report snippet and the stem say the same thing:

```text
QAshort/USW00094847_33.json
  report: The following events were reported: Flood, Hail, Thunderstorm Wind, Tornado. These occurred near station USW00094847, approximately 20.043 km away, between 2010-07-23 17:03:00 and 2010-07-23 20:34:00. The events included records with hailstones measuring 53.67 ...
  stem:   Considering the weather event report indicating significant flooding and severe thunderstorms on July 23, 2010, how is the temperature in time series B for July 24, 2010, correlated with the atmospheric conditions immediately following such severe weather?
  answer: C) The slight decrease in temperature compared to the previous series suggests the presence of residual moisture in the atmosphere, causing increased hum ...
```

```text
QAshort/USW00012844_14.json
  report: The following events were reported: Hail, Thunderstorm Wind. These occurred near station USW00012844, approximately 22.1452 km away, between 2020-05-27 14:24:00 and 2020-05-27 14:50:00. The events included records with hailstones measuring 28.0 inches.Thankful ...
  stem:   Considering the reported weather events occurring on May 27, 2020, with hail and thunderstorm winds near station USW00012844, what would be the anticipated impact on the temperature profile for May 28, particularly in relation to the Tropical Storm Bertha phen ...
  answer: D) The temperature would gradually increase as the atmospheric conditions stabilize post-storm and the influence of Tropical Storm Bertha diminishes.
```

```text
QAlong/USW00093721_34.json
  report: The following events were reported: Funnel Cloud, Hail, Thunderstorm Wind. These occurred near station USW00093721, approximately 36.3677 km away, between 2008-06-10 16:36:00 and 2008-06-10 19:50:00. The events included records with hailstones measuring 33.667 ...
  stem:   Based on the observed temperature trends during the 14-day period prior to June 10, 2008, and considering the conditions described in the weather event report (including a strong cold front), how would you expect the temperature to behave in the immediate days ...
  answer: D) Expect moderate temperatures in the days following the cold front passage, as transient warm air invades the region shortly after the thunderstorms di ...
```


## W6. Report text refers to the forecast day (leakage)

Episode narratives are written after the fact and sometimes mention the day *after* the end of the input window, i.e. the day being predicted or asked about.

| Folder | Samples | Text mentions next day | Share |
|---|---|---|---|
| aligned_in7days_out1days | 1,959 | 117 | 6.0% |
| aligned_in14days_out3days | 1,959 | 117 | 6.0% |
| QAshort | 645 | 42 | 6.5% |
| QAlong | 728 | 38 | 5.2% |
| noaa_aligned_in7days_out1days | 7,905 | 215 | 2.7% |

```text
aligned_in7days_out1days/USW00013739_24.json  (last input hour: 2015-06-23 23:00:00)
  "...Philadelphia and Washington D.C. and Keystone service between Philadelphia and Harrisburg. That service was restored on the 24th. PECO Energy reported about 250,000 of its customers lost power in southeastern..."
```

```text
aligned_in7days_out1days/USW00093721_15.json  (last input hour: 2007-04-16 23:00:00)
  "...er weakened and meandered across southwest New England and the New York and New Jersey coastal waters. By 2 a.m. EDT on the 17th, the nor'easter's central pressure rose to 988 millibars and a second storm for..."
```

```text
QAshort/USW00014820_6.json  (last input hour: 2020-04-07 23:00:00)
  "...xtended west-southwestward from the low and swept south-southeastward through northern Ohio during the early morning of the 8th. Along and ahead of the cold front, clusters of thunderstorms, including superc..."
```

```text
QAshort/USW00013739_31.json  (last input hour: 2010-06-24 23:00:00)
  "...r, the 11th worst outage in company history. Chester and Delaware Counties were hit the hardest. as of 1201 a.m. EDT on the 25th, 190,000 customers were without power. That number dropped to 152,000 at Noon E..."
```

```text
noaa_aligned_in7days_out1days/USW00093242_2019-03-02.json  (last input hour: 2019-03-02 23:00:00)
  "...s generally picked up between a tenth to a half an inch of rainfall. The storm moved east of the area by the morning of March 3. Event Narrative: Several social media reports and images of several downed tre..."
```

```text
noaa_aligned_in7days_out1days/USW00053958_2022-04-12.json  (last input hour: 2022-04-12 23:00:00)
  "...nd power lines, and even spawning isolated tornadoes as well. While these storms exited the region prior to daybreak on the 13th, additional showers and thunderstorms developed along the associated cold front..."
```


## W7. Naive forecasts are competitive (temperature forecasting)

MSE of trivial predictors over the whole output window (degrees C squared):

| Folder | n | Repeat last 24 h | Mean of input |
|---|---|---|---|
| aligned_in7days_out1days | 1,959 | 21.07 | 19.42 |
| aligned_in14days_out3days | 1,959 | 25.66 | 21.02 |
| noaa_aligned_in7days_out1days | 7,905 | 23.93 | 29.48 |
| noaa_aligned_in14days_out3days | 7,871 | 32.48 | 32.08 |

For reference, the README reports GPT-4o time-series-only MSE of 21.67 for weather forecasting, no better than "repeat yesterday" (21.1) or "predict the input mean" (19.4) on the 7-day setting (different eval subset, so only indicative). Because the series is hourly with a strong daily cycle, a model that merely copies the last 24 hours reproduces most of the signal and the text is not needed. Examples where repeating the last day is nearly exact:

```text
aligned_in7days_out1days/USW00013960_39.json  (repeat-last-day MSE 0.25)
  last input day   : 13.9, 13.9, 13.9, 13.9, 13.9, 13.9, 13.9, 13.9  (every 3rd hour)
  output (truth)   : 14.4, 14.4, 14.4, 14.4, 14.4, 14.4, 14.4, 14.4
  report: The following events were reported: Hail, Thunderstorm Wind, Tornado. These occurred near station USW00013960, approximately 32.9239 km away, between ...
```

```text
aligned_in7days_out1days/USW00012839_30.json  (repeat-last-day MSE 2.21)
  last input day   : 28.3, 26.1, 25.0, 25.0, 24.4, 25.6, 23.3, 27.2  (every 3rd hour)
  output (truth)   : 25.0, 26.7, 24.4, 23.9, 25.0, 26.1, 22.8, 24.4
  report: The following events were reported: Marine Thunderstorm Wind. These occurred near station USW00012839, approximately 23.5879 km away, between 2007-09- ...
```

```text
aligned_in7days_out1days/USW00022521_0.json  (repeat-last-day MSE 0.98)
  last input day   : 26.7, 25.0, 23.3, 23.6, 23.9, 24.3, 25.0, 25.0  (every 3rd hour)
  output (truth)   : 28.3, 26.6, 25.0, 24.4, 23.9, 24.4, 25.0, 25.0
  report: The following events were reported: Debris Flow, Flash Flood, Heavy Rain, Thunderstorm Wind. These occurred near station USW00022521, approximately 17 ...
```


## W8. Label priors (trend / indicators)

| Folder | past trend (from the input only) | future trend `decreasing` | `increasing` | `stable` | day-1 range (C) |
|---|---|---|---|---|---|
| aligned_in7days_out1days | computable from the input | 57.5% | 28.0% | 14.5% | 7.2 +/- 4.0 |
| aligned_in14days_out3days | computable from the input | 58.2% | 28.1% | 13.7% | 7.4 +/- 3.9 |
| noaa_aligned_in7days_out1days | computable from the input | 44.5% | 38.1% | 17.4% | 10.4 +/- 4.1 |
| noaa_aligned_in14days_out3days | computable from the input | 44.7% | 38.0% | 17.3% | 10.4 +/- 4.2 |

- The `past` trend label (default for `trend_classification.py`) is a deterministic function of the input window; a model with the series needs no text.
- The indicator task (day-1 max / min / range) is close to a constant plus the last day's values: mean absolute difference between the next day's max and the last input day's max is about 3.2 C, and the range has sd of only ~4 C.

Examples (labels computed with the repo's rules):

```text
aligned_in7days_out1days/USW00003947_11.json
  past trend: stable, future trend: decreasing, day-1 max/min: 21.7/10.0, last input day max/min: 27.8/14.4
  report: The following events were reported: Flash Flood, Flood, Hail, Heavy Rain. These occurred near station USW00003947, approximately 35.4383 km ...
```

```text
aligned_in7days_out1days/USW00014732_15.json
  past trend: decreasing, future trend: decreasing, day-1 max/min: 17.8/13.3, last input day max/min: 23.9/19.4
  report: The following events were reported: Thunderstorm Wind, Tornado. These occurred near station USW00014732, approximately 25.8941 km away, betw ...
```

```text
aligned_in7days_out1days/USW00024233_7.json
  past trend: increasing, future trend: increasing, day-1 max/min: 12.8/10.6, last input day max/min: 15.6/7.8
  report: The following events were reported: Debris Flow. These occurred near station USW00024233, approximately 20.0223 km away, between 2014-03-02 ...
```

```text
aligned_in7days_out1days/USW00014739_23.json
  past trend: increasing, future trend: decreasing, day-1 max/min: 26.7/26.7, last input day max/min: 35.6/25.0
  report: The following events were reported: Flood, Lightning, Thunderstorm Wind. These occurred near station USW00014739, approximately 20.657 km aw ...
```


## W9. Prior knowledge, memorisation and duplicated narratives

- 196 of 1,959 samples name a storm (e.g. Hurricane Ida, Hurricane Floyd, Tropical Storm Andrea/Debby). These are public events whose weather is documented in pre-training data; the date in the timestamps plus the storm name identifies the event.
- Location, season and year are given (station id, timestamps), so climatology ("July in Florida is warm") is a strong prior for the series; the prompt itself says "summers are hot and winters are cold".
- 486 samples share their episode narrative with at least one other sample (same weather episode at neighbouring stations or days), so the same text recurs with different series.

```text
aligned_in7days_out1days/USW00023183_24.json  (input ends 2018-10-13 23:00:00)
  "...therly flow ahead of the low advected in some tropical moisture being shed from Tropical Storm Sergio which recently passed by to the south of Arizona, and this infusion of tropical moisture helped to support the very he ......"
```

```text
aligned_in7days_out1days/USW00012844_26.json  (input ends 2012-08-27 23:00:00)
  "...ed property damage valued at 15000.0 and crop damage of 0.0. Episode Narrative: Tropical Storm Isaac passed southwest of east-central Florida, making its closest approach during the late afternoon and evening hours of Au..."
```

```text
aligned_in7days_out1days/USW00012842_3.json  (input ends 2013-06-06 23:53:00)
  "...ed property damage valued at 61000.0 and crop damage of 0.0. Episode Narrative: Tropical Storm Andrea developed in the Gulf of Mexico on the morning of the 5th and moved northeast, making landfall 10 miles south of Stein ......"
```

```text
Same episode narrative reused across samples: USW00012842_3.json, USW00012842_6.json, USW00012894_1.json
```

```text
Same episode narrative reused across samples: USW00012839_19.json, USW00012839_6.json, USW00012849_6.json
```


## W10. Flat (constant) output windows: a resampling artifact in the original data

Some original weather samples have an output window that is a single repeated value (see `USW00013904_34`: all 24 / 72 output hours are exactly 27.0 C). This is a data-pipeline artifact, not weather.

**Cause.** `data_preparation/weather/create_pairs.py` (`interpolate_data`, lines 85-106) builds an hourly grid starting at the first reading in the window, left-joins the station readings on *exact* timestamps, interpolates, and then forward/back-fills what is left. When a station's later readings fall off that minute grid, only the first reading matches, nothing can be interpolated, and the fill copies it across the whole window. Consistent with this, the first output timestamp has a different minute than the last input timestamp in the flat samples (see the table).

| Folder | Samples | Fully flat output | Share | Flat for >= half the window | First-output minute differs from last-input minute (among flat) | Distinct stations |
|---|---|---|---|---|---|---|
| aligned_in7days_out1days | 1,959 | 124 | 6.3% | 168 (8.6%) | 121/124 | 23 |
| aligned_in14days_out3days | 1,959 | 108 | 5.5% | 122 (6.2%) | 108/108 | 22 |
| noaa_aligned_* (7-day and 14-day) | 15,776 | 0 | 0% | - | - | - |

The 108 flat samples of the 14-day set are the same samples as in the 7-day set. The affected samples are spread across 22-23 stations and most years between 2003 and 2023, so they are not one broken station or period. The NOAA samples are not affected (they use NOAA's own hourly grid).

**Effect on the tasks**

- *Forecasting:* the "truth" is a flat line. Its distance from the last input value is small on average (median 0.5 C, mean 1.7 C), so a flat or persistence forecast scores well; the time-series metric is trivially gameable on these samples.
- *Indicators:* the day-1 range is exactly 0 for every flat sample, which drags the range/max/min targets away from real weather (real day-1 range is 7.2 +/- 4.0 C, see W8).
- *Trend:* the `future trend` label is computed from that single repeated value (7-day set: 69 `decreasing`, 39 `increasing`, 16 `stable` among the 124 flat samples), so it measures one reading, not the next day's temperature.

Examples (the output window is one repeated value):

```text
aligned_in7days_out1days/USW00014821_11.json
  last input hours : [22.8, 23.3, 23.3, 22.2]  (ends 2022-07-17 23:51:00)
  output (24 h)    : [22.2] for all hours, first timestamp 2022-07-18 00:08:00
  report: The following events were reported: Flood, Tornado. These occurred near station USW00014821, approximately 41.3263 km aw ...
```

```text
aligned_in7days_out1days/USW00012849_36.json
  last input hours : [30.6, 28.9, 28.9, 29.4]  (ends 2020-07-04 23:53:00)
  output (24 h)    : [29.4] for all hours, first timestamp 2020-07-05 00:13:00
  report: The following events were reported: Hail, Thunderstorm Wind. These occurred near station USW00012849, approximately 19.5 ...
```

```text
aligned_in7days_out1days/USW00023293_2.json
  last input hours : [10.9, 10.9, 12.2, 12.2]  (ends 2012-12-23 23:53:00)
  output (24 h)    : [12.0] for all hours, first timestamp 2012-12-24 00:32:00
  report: The following events were reported: Debris Flow, Flash Flood, Flood. These occurred near station USW00023293, approximat ...
```

```text
aligned_in7days_out1days/USW00023293_3.json
  last input hours : [16.1, 15.6, 15.6, 16.1]  (ends 2009-10-13 23:53:00)
  output (24 h)    : [16.0] for all hours, first timestamp 2009-10-14 00:30:00
  report: The following events were reported: Flash Flood, Flood. These occurred near station USW00023293, approximately 34.9527 k ...
```

**It also reaches the multiple-choice questions.** `QAshort` files carry no output window, but they were generated for the same samples (same file name and identical input window). For the flat samples the questions are written about a temperature that supposedly stays put:

- 50 of the 124 flat samples also exist as `QAshort` questions (identical input window).
- In these, the correct option describes stability / no change in 29/50 (58%) of the cases, against 185/644 (29%) across all `QAshort` questions. Many questions therefore appear to have been written from the flat line (first and third examples below). Others describe a change the flat window does not show (second example: a "drastic drop" against 22.0 vs 21.1 C), so the QA ground truth cannot be trusted for these samples either way. Whether the generator saw the flat window is inferred from the question text, not verified.

```text
QAshort/USW00093225_24.json  (flat output value 16.0, last input 16.1)
  stem: Given the reported tornado activity on March 26, 2014, in interior Northern California and the steady temperature recorded the following day, what could be the most plaus ...
  A  (147 chars) The temperatures were influenced by the terrain and consistent, uniform weather patterns characteristic of the region af ...
  B  (122 chars) The tornado activity caused prolonged local heating which elevated the temperatures for several hours following the even ...
  C* (125 chars) A high-pressure system developed rapidly after the cold front, resulting in a uniform and stable temperature across the ...
  D  (123 chars) The impact of the previous day's heavy snowfall and subsequent melting elevated the average temperatures despite the sto ...
```

```text
QAshort/USW00023169_17.json  (flat output value 22.0, last input 21.1)
  stem: Considering the temperature trends observed in time series A, which of the following best explains the drastic drop in temperature observed in time series B on the day fo ...
  A  (165 chars) The flash flooding event caused a significant increase in local humidity, which then contributed to an abrupt drop in te ...
  B* (169 chars) The low temperature observed in time series B is due to sustained cloud cover from the previous day's thunderstorms, whi ...
  C  (150 chars) The drop in temperature is primarily due to a cold front moving in from the northwest, which is common after storm event ...
  D  (156 chars) The severe thunderstorms and flash flooding resulted in local heat islands dissipating rapidly, leading to a cooler envi ...
```

```text
QAshort/USW00013904_13.json  (flat output value 20.6, last input 20.6)
  stem: Given the extreme weather events reported on May 25, 2015, which of the following temperature trends is most likely to occur on May 26, 2015, directly following these eve ...
  A  (178 chars) A significant drop in temperature due to the influx of cold air from the upper level low causing a consistent drop, lead ...
  B  (192 chars) A consistent warm temperature due to the lingering heat from the thunderstorms and no cooling effect from the atmospheri ...
  C* (180 chars) A consistent cool temperature of around 20.6°C throughout the day due to the extensive rainfall and cloud cover resultin ...
  D  (127 chars) A spike in temperature due to the clearing of skies post thunderstorms leading to intensified solar heating throughout t ...
```

**Possible fix (untested):** drop (or regenerate) samples whose output window has no variation, and fix the grid in `create_pairs.py` by merging with `pd.merge_asof` or by resampling to the hour (`df.resample('h').mean()`) before interpolating. Affected files: the 124 (7-day) and 108 (14-day) listed by `np.ptp(output_window) == 0`.

---
# New NOAA data

## N1. Class imbalance in the NOAA questions

Answer distribution of the raw NOAA question rows (all splits, hourly setting):

| Question type | n | A | B | C | D | Majority-class accuracy |
|---|---|---|---|---|---|---|
| temp_max_change | 8,367 | 23.9% | 26.9% | 22.8% | 26.4% | 26.9% (B) |
| temp_min_change | 8,367 | 25.4% | 25.1% | 21.5% | 27.9% | 27.9% (D) |
| precip_total | 8,424 | 63.2% | 12.4% | 12.3% | 12.2% | 63.2% (A) |
| peak_wind_max | 8,424 | 20.3% | 26.1% | 28.1% | 25.5% | 28.1% (C) |
| pressure_change | 8,397 | 23.0% | 24.8% | 27.5% | 24.7% | 27.5% (C) |
| thunder | 8,424 | 20.5% | 79.5% | - | - | 79.5% (B) |
| joint_rain_wind | 8,424 | 29.2% | 70.8% | - | - | 70.8% (B) |

`thunder`, `joint_rain_wind` (A = Yes, B = No) and `precip_total` (A = none/trace) are dominated by the "nothing happens" answer, so always answering that scores 63-80% on these types. The quantile-binned types (temperature, wind, pressure) are balanced by construction (25-28% majority).

```text
noaa_QAshort/USW00003856_2023-03-03.json
  report: The following events were reported: Thunderstorm Wind. They occurred near station USW00003856 (LAUDERDALE,ALABAMA), 0.1 to 24.1 km away, between 2023- ...
  question: Will thunder be reported at the station during the next 24 hours?
  answer: B (No)
```

```text
noaa_QAshort/USW00014940_2020-04-13_ctrl.json
  report: No severe weather events were reported within 50 km of station USW00014940 (CERRO GORDO,IOWA) on 2020-04-13.
  question: Will thunder be reported at the station during the next 24 hours?
  answer: B (No)
```

```text
noaa_QAshort/USW00004838_2020-07-23_ctrl.json
  report: No severe weather events were reported within 50 km of station USW00004838 (COOK,ILLINOIS) on 2020-07-23.
  question: Will thunder be reported at the station during the next 24 hours?
  answer: B (No)
```


## N2. A "no event" report is a label cue

51% of NOAA samples have no storm event; their text is a fixed template ("No severe weather events were reported within 50 km of station ..."). It correlates with the answers:

| Question | Answer | With an event | Without an event |
|---|---|---|---|
| thunder | Yes | 32.8% | 8.5% |
| joint rain + wind | Yes | 39.2% | 19.4% |
| precipitation >= 9.6 mm (D) | D | 18.0% | 6.5% |
| max-temperature change >= 1.7 C (D) | D | 18.7% | 33.8% |
| min-temperature change >= 1.1 C (D) | D | 17.1% | 38.4% |

A model can read only the first words of the report and shift its answer. Examples (template text vs an event report, same question type):

```text
noaa_QAshort/USW00094949_2020-11-20_ctrl.json
  report: No severe weather events were reported within 50 km of station USW00094949 (FILLMORE,NEBRASKA) on 2020-11-20.
  question: What will the total precipitation at the station be over the next 24 hours?
  answer: A) none or trace (below 0.3 mm)
```

```text
noaa_QAshort/USW00013739_2019-08-25_ctrl.json
  report: No severe weather events were reported within 50 km of station USW00013739 (MONTGOMERY,PENNSYLVANIA) on 2019-08-25.
  question: What will the total precipitation at the station be over the next 24 hours?
  answer: A) none or trace (below 0.3 mm)
```

```text
noaa_QAshort/USW00004853_2019-08-06.json
  report: The following events were reported: Thunderstorm Wind. They occurred near station USW00004853 (CUYAHOGA,OHIO), 8.4 to 18.1 km away ...
  question: What will the total precipitation at the station be over the next 24 hours?
  answer: B) 0.3 to 2.0 mm
```

```text
noaa_QAshort/USW00053954_2021-09-21.json
  report: The following events were reported: Thunderstorm Wind. They occurred near station USW00053954 (MCDONALD,MISSOURI), 5.7 to 5.7 km a ...
  question: What will the total precipitation at the station be over the next 24 hours?
  answer: A) none or trace (below 0.3 mm)
```


## N3. Next-day references and negative results

- 215 of 7,905 NOAA samples still mention the next day in the report (W6). The converter already dropped samples where the event extends into the forecast window; these are narrative mentions only.
- Bin edges are fixed per question type (one option set for all samples), so a model cannot infer the answer from the bins; the "bin that contains 0" heuristic scores only 21-25% on temperature/pressure change, so persistence is not a shortcut on those.

```text
noaa_aligned_in7days_out1days/USW00093988_2019-05-08.json  (last input hour: 2019-05-08 23:00:00)
  "...ss portions of the southern half of the state during the early evening hours of the 8th into the early morning hours on the 9th, producing some wind damage and flash flooding. One brief tornado was observed..."
```

```text
noaa_aligned_in7days_out1days/USW00053905_2023-04-02.json  (last input hour: 2023-04-02 23:00:00)
  "...t Texas during the late afternoon and evening, and across the remainder of the region during the early morning hours on the 3rd. Given the increased forcing along these boundaries and the approaching upper t..."
```

```text
noaa_aligned_in7days_out1days/USW00063820_2021-12-10.json  (last input hour: 2021-12-10 23:00:00)
  "...t night, an EF-1 tornado occurred in Prentiss County before the severe weather threat began to wind down around 6 AM on December 11, 2021. ||In total, there were 18 tornadoes across the NWS Memphis CWA. Along w..."
```


---
# Finance

## F1. Majority-class trend label

Output-window percentage-change bin (5 classes, the label for trend prediction):

| Setting | n | <-4% | -4%~-2% | -2%~+2% | +2%~+4% | >+4% | P(output up) |
|---|---|---|---|---|---|---|---|
| short (7d in, 1d out) | 750 | 2.1% | 4.7% | 67.9% | 19.3% | 6.0% | 59.7% |
| long (30d in, 7d out) | 525 | 6.1% | 6.3% | 38.9% | 29.9% | 18.9% | 68.2% |

In the short setting two thirds of the samples are in the middle bin, so always predicting `-2% ~ +2%` reaches about 68% 5-way accuracy. The README reports trend-prediction accuracies of 41-47% for the short setting without saying whether they are 5-way or 3-way (the script computes both); if 5-way they are below this trivial baseline. Either way the baseline should be reported next to the metric. Input and output moves are uncorrelated (r = 0.00 short, 0.04 long), so there is no momentum shortcut here. Examples:

```text
aligned_in7days_out1days row 655
  output bin: -2% ~ +2% (-0.11%), input bin: -2% ~ +2%
  article: Dynex Capital (DX) Gains But Lags Market: What You Should Know By Zacks Equity Research Published on: 2022-01-11T23:00:17Z In the latest trading sessi ...
```

```text
aligned_in7days_out1days row 515
  output bin: -2% ~ +2% (-0.33%), input bin: -2% ~ +2%
  article: MSA Safety (MSA) to Report Q1 Results: What to Expect By Zacks Equity Research Published on: 2022-04-20T19:01:36Z MSA Safety (MSA) doesn't possess the ...
```

```text
aligned_in7days_out1days row 78
  output bin: -2% ~ +2% (+1.68%), input bin: -2% ~ +2%
  article: Gen Z less concerned about fraud and identity theft according to Equifax Canada survey By Equifax Canada Published on: 2022-03-01T16:00:00Z Checking y ...
```


## F2. News sentiment tags the outcome

The aligned dataset keeps the article's sentiment label (`label_sentiment`). Cross-tabulated with the direction of the output move:

| Setting | Sentiment | n | Output up | Output down |
|---|---|---|---|---|
| short | Bullish | 213 | 79% | 21% |
| short | Bearish | 32 | 6% | 94% |
| short | Neutral/other | 505 | 55% | 45% |
| long | Bullish | 220 | 88% | 12% |
| long | Bearish | 28 | 18% | 82% |
| long | Neutral/other | 277 | 58% | 42% |

Bullish articles are followed by a rise 79-88% of the time (base rate 60-68%), bearish ones by a fall 82-94% (only 32 and 28 bearish samples, so that figure is noisy). A model that reads the tone of the article (text-only) predicts the direction well above chance, and the `alignment` field ("consistent" for 81% / 82% of samples) suggests the data was filtered for agreement between article and price. Examples (tag, output move, title):

```text
aligned_in7days_out1days row 410
  sentiment: ['[1][a] Bullish']  -> output move +2.39% (+2% ~ +4%)
  article: Haemonetics (HAE) Just Overtook the 20-Day Moving Average By Zacks Equity Research Published on: 2023-07-18T13:35:03Z Good things could be o ...
```

```text
aligned_in7days_out1days row 578
  sentiment: ['[1][a] Bullish']  -> output move +3.37% (+2% ~ +4%)
  article: Is SunCoke Energy (SXC) Stock Undervalued Right Now? By Zacks Equity Research Published on: 2023-03-16T13:40:13Z Here at Zacks, our focus is ...
```

```text
aligned_in7days_out1days row 166
  sentiment: ['[1][a] Bullish']  -> output move +5.18% (>+4%)
  article: Access to Myriad Genetics’ GeneSight Test Improves Depression Remission Rates In Largest Ever Mental Health PGx Randomized Controlled Trial ...
```

```text
aligned_in7days_out1days row 171
  sentiment: ['[1][a] Bullish']  -> output move +4.77% (>+4%)
  article: RPC (RES) Beats Q3 Earnings and Revenue Estimates By Zacks Equity Research Published on: 2021-10-27T11:55:06Z RPC (RES) delivered earnings a ...
```


## F3. Indicator targets have fixed starting values

- `out_macd[0] == 0` in 1275/1275 samples and `out_upper_bb[0]` is NaN in 1275/1275: the output indicators are computed on the output window alone, so their first values are known and carry no information about the market.
- Because of this restart, continuing the input indicator is *worse* than predicting zero: in the short setting the MSE of an all-zero MACD guess is 0.233 vs 0.445 for repeating the last input MACD value.
- A model that just emits values near 0 therefore already beats continuing the input indicator, without using the news or the trend.

```text
aligned_in7days_out1days row 369
  in_macd[-3:]  = [-0.309, -0.297, -0.27]
  out_macd[:3]  = [0.0, -0.001, 0.013]   <- always starts at 0
  out_upper_bb[:3] = [None, 52.869, 53.12]   <- NaN start
```

```text
aligned_in7days_out1days row 713
  in_macd[-3:]  = [-0.692, -0.686, -0.684]
  out_macd[:3]  = [0.0, -0.013, -0.026]   <- always starts at 0
  out_upper_bb[:3] = [None, 29.511, 29.457]   <- NaN start
```

```text
aligned_in7days_out1days row 647
  in_macd[-3:]  = [-0.009, -0.008, -0.007]
  out_macd[:3]  = [0.0, 0.0, -0.0]   <- always starts at 0
  out_upper_bb[:3] = [None, 9.125, 9.125]   <- NaN start
```


## F4. Persistence and price-scale effects (forecasting)

- Predicting the last input price for every output step has a mean absolute percentage error of 1.9% (short) / 3.4% (long).
- Absolute error is dominated by price level: median last price 62, maximum 2,558. An MSE-based metric is therefore driven by a few expensive tickers rather than by forecasting skill.

```text
aligned_in7days_out1days row 406
  last input price: 284.77
  first / mean / last output price: 284.41 / 290.77 / 281.62
  persistence MAPE: 2.08%
```

```text
aligned_in7days_out1days row 121
  last input price: 37.20
  first / mean / last output price: 37.20 / 37.73 / 37.85
  persistence MAPE: 1.40%
```

```text
aligned_in7days_out1days row 707
  last input price: 171.49
  first / mean / last output price: 170.89 / 170.63 / 169.94
  persistence MAPE: 0.51%
```


## F5. Prior knowledge of 2021-2023 stocks

Every QA sample has a ticker (in the file name), a publication timestamp and an article with quoted prices; the data covers 2021-2023 US equities (about 330 distinct tickers per setting, e.g. NVDA, AAPL, NFLX, DIS). A model trained on market news and price data from this period can recall what the stock did around that earnings date without using the series. Examples with quoted prices in the article:

```text
QAshort/7831_INTC.json  (ticker INTC, published 2022-06-27T21:45:19Z)
  "...closed at $38.63, marking a +0.05% move from the previous day. This change outpaced the..."
  last input price: 38.55, last output price: 37.85
```

```text
QAshort/9980_LNG.json  (ticker LNG, published 2023-02-01T22:45:23Z)
  "...closed at $153.96 in the latest trading session, marking a +0.77% move from the prior d..."
  last input price: 153.62, last output price: 148.74
```

```text
QAshort/9180_NKE.json  (ticker NKE, published 2022-05-16T21:45:10Z)
  "...closed at $112.60 in the latest trading session, marking a -0.36% move from the prior d..."
  last input price: 112.57, last output price: 115.63
```

```text
QAshort/681_MO.json  (ticker MO, published 2022-09-21T21:50:17Z)
  "...closed at $43.01, marking a +0.21% move from the previous day. The stock outpaced the S..."
  last input price: 43.12, last output price: 43.41
```


## F6. Correlation label is mostly output direction or momentum

The correlation label (5 classes) encodes whether the price moved with or against the article's sentiment. Almost all articles are positive, so the label reduces to the output direction:

| Setting | n | Label sign positive & output up | Label sign negative & output down | Label sign matches input trend | `No Correlation` |
|---|---|---|---|---|---|
| QAshort | 491 | 183/244 (75%) | 154/211 (73%) | 63% | 7.3% |
| QAlong | 516 | 163/210 (78%) | 184/258 (71%) | 66% | 9.3% |

- Majority class is `Moderate Positive Correlation` (30.5%, short) or `Strong Negative Correlation` (27.5%, long); `No Correlation` is only 7-9%, so the neutral option can nearly always be ruled out.
- Label sign agrees with the *input* trend 63-66% of the time (momentum), and with the output direction 71-78%, so the series alone gives a prediction.
- A positive-minus-negative keyword count over the article does not separate the classes (positive words dominate even for negative-correlation labels), so the label is not recoverable from tone alone.

```text
QAshort/151_SPY.json  label: Moderate Negative Correlation
  keywords in article: 0 positive vs 0 negative
  input trend -2.28, output move +1.81
```

```text
QAshort/121_MYGN.json  label: Moderate Negative Correlation
  keywords in article: 0 positive vs 1 negative
  input trend +1.40, output move -0.06
```

```text
QAshort/5196_CHRW.json  label: Strong Negative Correlation
  keywords in article: 11 positive vs 0 negative
  input trend -4.39, output move +0.08
```


## F7. Hedged vs absolute wording (MCQA)

526/1007 questions ask which statement is *incorrect*; the rest ask for the correct one.

| Stem type | Word | In the answer option | In a distractor |
|---|---|---|---|
| asks for incorrect | `will` | 17.3% | 0.3% |
| asks for incorrect | `solely` | 2.5% | 0.1% |
| asks for incorrect | `directly` | 1.0% | 0.0% |
| asks for incorrect | `because` | 0.6% | 0.0% |
| asks for incorrect | `entirely` | 0.4% | 0.0% |
| asks for correct | `may` | 15.0% | 3.3% |
| asks for correct | `could` | 10.0% | 3.0% |
| asks for correct | `potential` | 17.7% | 6.1% |
| asks for correct | `slight` | 3.3% | 0.7% |

In "which is incorrect" questions the false statement overclaims ("will", "solely", "directly"), whereas the three true statements hedge ("may", "slight"); in "which is correct" questions the answer is the hedged one. A model can use writing style without checking the price data. Examples (answer marked `*`):

```text
QAlong/12931_MXL.json  (asks for incorrect)
  stem: Which of the following statements about MXL's stock price and the given financial analysis is incorrect?
  A  (217 chars) The statement from analysts noting a consensus EPS estimate increase of 11.8% over the last 30 days can positively influence investor sentiment and po ...
  B  (238 chars) Following the news publication, the stock's price continued to decline initially, reaching a low of $39.13 before showing signs of recovery, which ali ...
  C* (203 chars) The publication of the news on May 11, 2022, guaranteed a positive turnaround for MXL based solely on the hammer pattern, meaning investors could expe ...
  D  (230 chars) The formation of the hammer chart pattern on May 11, 2022, is a potential bullish signal, suggesting that the stock may have found support at its rece ...
```

```text
QAlong/13988_CAH.json  (asks for incorrect)
  stem: Which of the following statements about CAH's stock price and the given financial analysis is incorrect?
  A  (202 chars) The Zacks Rank of #2 (Buy) suggests that despite recent lackluster performance, there may be underlying factors that could help CAH recover if positiv ...
  B  (217 chars) The earnings estimates for CAH remain stable, with a slight adjustment of -0.1% over the last 30 days, indicating relative stability in expected perfo ...
  C  (212 chars) The historical stock movement prior to the news publication demonstrates a gradual increase in price, peaking near $80.65 before trending downwards, i ...
  D* (169 chars) The recent price movements suggest that CAH's stock is likely to drop below $75 in the next week based solely on the recent downward adjustments in pr ...
```

```text
QAshort/222_ACGL.json  (asks for incorrect)
  stem: Which of the following statements about ACGL's stock price and the given financial analysis is incorrect?
  A  (189 chars) The historical stock prices for Arch Capital (ACGL) showed a general upward trend until the news publication on September 20, 2022, peaking at approxi ...
  B* (192 chars) Implied volatility surging without corresponding high trading volume means that the stock price will experience a rapid and sustained increase, as hig ...
  C  (188 chars) The significant drop in stock prices after the news publication could suggest that investors are reacting to expectations of volatility and uncertaint ...
  D  (195 chars) Following the publication of the news regarding surging implied volatility, the stock price of Arch Capital experienced a downward movement, indicatin ...
```

```text
QAlong/12246_CLF.json  (asks for correct)
  stem: Which of the following statements about CLF's stock price and the given financial analysis is correct?
  A* (218 chars) The stock price of Cleveland-Cliffs (CLF) exhibited some volatility during the 30-day period, with a peak of approximately $18.675, indicating potenti ...
  B  (178 chars) The most recent stock price of CLF at $17.29 after the news suggests that the stock is undervalued, and investors should expect a price correction abo ...
  C  (247 chars) Despite the anticipated earnings miss communicated in the news, the stock price of CLF is likely to increase leading into the earnings announcement, a ...
  D  (248 chars) Based on the historical trend leading up to the news, it can be predicted that CLF's stock price will rebound sharply after the earnings report, regar ...
```

```text
QAlong/965_DDD.json  (asks for correct)
  stem: Which of the following statements about DDD's stock price and the given financial analysis is correct?
  A  (199 chars) After posting Q3 results, DDD's stock is projected to drop further due to consistent losses across all business segments, resulting in a lack of inves ...
  B* (237 chars) Despite a decline in revenue in Q3 2022, the non-GAAP metrics indicated a slight growth when excluding divestitures and adjusting for currency, sugges ...
  C  (200 chars) The strong performance in the stock price post-announcement suggests that the financial results exceeded investor expectations significantly, despite ...
  D  (229 chars) The stock price decline prior to the news announcement indicates that investors were reacting negatively to the expectations of reduced revenues, whic ...
```


Checks that did **not** show a shortcut in finance MCQA: answer position is balanced (A-D each 23-28%), the longest option is correct 29% of the time (chance 25%), and numbers quoted in options appear in the article only 44-51% of the time regardless of whether the option is correct.

---
# Suggested next steps

1. **Report trivial baselines next to every model score:** majority class and always-`B` for MCQA; repeat-last-day and input-mean for forecasting; always-`decreasing` (weather trend) and always-`-2% ~ +2%` (finance trend); always-`No` for the NOAA yes/no questions.
2. **Modality ablations:** run text-only, series-only and shuffled-text (a report from another sample) variants. Tasks where text-only or series-only already matches the combined score do not test multimodal reasoning (W5, F2, F6 are the likeliest).
3. **Rebalance MCQA:** shuffle option order so the correct letter is uniform, and rewrite or filter options so length, hedging and absolute wording do not predict the label (W1-W3, F7).
4. **Remove report text that refers to the prediction window** (W6) and check that narratives dated after the input end are cut before the prompt is built.
5. **Decontamination probes:** ask models for the realised price/temperature given only the ticker/station and date to estimate memorisation (F5, W9).
6. **Remove or regenerate the flat-output samples (W10)** and fix the exact-timestamp merge in `create_pairs.py`, so that forecasting, trend, indicator and the affected MCQA labels reflect real weather.
7. **Metric fixes:** use scale-free errors for finance forecasting (MAPE or normalised MSE), and drop the first, deterministic values of the indicator targets (F3, F4).
8. **Balance the NOAA questions:** stratify by answer or report balanced accuracy for the skewed yes/no and precipitation types (N1) and consider including a no-event control with matched labels (N2).

_Generated by a read-only analysis script on 2026-10-29; all counts above are recomputed from the files on disk._
