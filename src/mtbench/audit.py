"""Audit functions to call from every source audit.

All functions take a list of samples in the adapter schema (see mtbench.adapters.schema).
The proxies are deliberately cheap: they show whether a trivial text-only or series-only model
already gets the signal, not what a real model can do.
"""
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline

from mtbench.adapters.schema import to_timestamp

EPS = 1e-6

# Numeric statements that could carry the answer. Sources phrase forecasts differently, so
# pass your own list where these are not enough.
_UNITS = r"(?:°|degrees?|deg|mph|kt|kts|knots?|inch(?:es)?|mm|cm|ft|feet|%|percent|mb|hpa|kp)"
DEFAULT_PATTERNS = [
    rf"\b\d+(?:\.\d+)?\s?{_UNITS}(?![a-z])",
    rf"\b\d{{1,3}}\s?(?:to|-|–)\s?\d{{1,3}}\s?{_UNITS}(?![a-z])",
    r"\b(?:will|expected to|forecast to|likely to|should|to)\s+"
    r"(?:reach|rise|fall|peak|crest|increase|decrease|drop|climb|top|exceed)\b[^.]{0,40}\d",
]


def _arr(values) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def sample_id(sample: dict) -> str:
    meta = sample["meta"]
    return f"{meta['entity_id']}_{meta['issue_time']}"


def leakage_scan(samples: list[dict], patterns: Optional[list[str]] = None) -> dict:
    """Regex scan of the text for numeric statements. Returns the hit rate and 20 examples."""
    compiled = [re.compile(p, re.IGNORECASE) for p in (patterns or DEFAULT_PATTERNS)]
    hits, examples = 0, []
    for s in samples:
        text = s["text"]
        found = next(((p, m) for p in compiled if (m := p.search(text))), None)
        if found is None:
            continue
        hits += 1
        if len(examples) < 20:
            pattern, m = found
            examples.append(
                {
                    "sample": sample_id(s),
                    "pattern": pattern.pattern,
                    "snippet": text[max(0, m.start() - 60) : m.end() + 60].replace("\n", " "),
                }
            )
    return {
        "rate": hits / len(samples) if samples else 0.0,
        "n_hits": hits,
        "n": len(samples),
        "examples": examples,
    }


def infer_season_length(timestamps: list) -> int:
    """Steps per natural cycle from the median step: daily cycle if sub-daily, then week, year."""
    stamps = [to_timestamp(t) for t in timestamps]
    step = float(np.median([(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]))
    day = 86400.0
    if step < 0.9 * day:
        return max(1, round(day / step))
    if step < 1.5 * day:
        return 7
    if step < 10 * day:
        return 52
    return 12


def persistence_baseline(samples: list[dict], season_length: Optional[int] = None) -> dict:
    """MAE of last-value and seasonal-naive forecasts on output_window.

    Seasonal naive repeats the last `season_length` input values (inferred per sample when None);
    samples with a shorter input than one cycle fall back to last value and are counted.
    """
    last_mae, seas_mae, fallbacks = [], [], 0
    for s in samples:
        x, y = _arr(s["input_window"]), _arr(s["output_window"])
        finite = x[np.isfinite(x)]
        if not finite.size:
            last_mae.append(np.nan)
            seas_mae.append(np.nan)
            continue
        last_pred = np.full(len(y), finite[-1])
        period = season_length or infer_season_length(s["input_timestamps"])
        if len(x) >= period and np.isfinite(x[-period:]).all():
            cycle = x[-period:]
            seas_pred = cycle[np.arange(len(y)) % period]
        else:
            seas_pred, fallbacks = last_pred, fallbacks + 1
        last_mae.append(np.nanmean(np.abs(y - last_pred)))
        seas_mae.append(np.nanmean(np.abs(y - seas_pred)))
    return {
        "last_value_mae": float(np.nanmean(last_mae)),
        "seasonal_naive_mae": float(np.nanmean(seas_mae)),
        "per_sample_last_value": np.array(last_mae),
        "per_sample_seasonal_naive": np.array(seas_mae),
        "n": len(samples),
        "n_seasonal_fallback": fallbacks,
    }


def _targets(samples: list[dict]) -> np.ndarray:
    """Normalized change: (mean(output) - last input value) / std(input)."""
    y = np.full(len(samples), np.nan)
    for i, s in enumerate(samples):
        x, out = _arr(s["input_window"]), _arr(s["output_window"])
        finite = x[np.isfinite(x)]
        if finite.size and np.isfinite(out).any():
            y[i] = (np.nanmean(out) - finite[-1]) / max(np.std(finite), EPS)
    return y


def _ts_features(samples: list[dict]) -> np.ndarray:
    rows = []
    for s in samples:
        x = _arr(s["input_window"])
        miss = float(np.isnan(x).mean())
        idx = np.flatnonzero(np.isfinite(x))
        if idx.size < 2:
            rows.append([0.0] * 6 + [miss])
            continue
        v, scale = x[idx], max(np.std(x[idx]), EPS)
        slope = np.polyfit(idx, v, 1)[0] * len(x)
        rows.append(
            [
                (v[-1] - v.mean()) / scale,
                (v[-1] - v[0]) / scale,
                slope / scale,
                (v.max() - v.min()) / scale,
                scale / (abs(v.mean()) + EPS),
                (v[-1] - v[-min(len(v), 4) :].mean()) / scale,
                miss,
            ]
        )
    return np.nan_to_num(np.array(rows, dtype=float))


def _grouped_cv(samples: list[dict], X, model_factory) -> dict:
    """Out-of-fold absolute error of the normalized change, GroupKFold by split_group."""
    y = _targets(samples)
    groups = np.array([s["meta"]["split_group"] for s in samples])
    ok = np.isfinite(y)
    n_groups = len(set(groups[ok]))
    if n_groups < 2:
        raise ValueError("need at least 2 split_group values with finite targets for grouped CV")
    n_splits = min(5, n_groups)
    idx = np.flatnonzero(ok)
    err = np.full(len(samples), np.nan)
    pred = np.full(len(samples), np.nan)
    for train, test in GroupKFold(n_splits=n_splits).split(idx, y[idx], groups[idx]):
        tr, te = idx[train], idx[test]
        model = model_factory()
        model.fit(X(tr), y[tr])
        pred[te] = model.predict(X(te))
        err[te] = np.abs(pred[te] - y[te])
    return {
        "oof_error": err,
        "oof_pred": pred,
        "mae": float(np.nanmean(err)),
        "mean_predictor_mae": float(np.mean(np.abs(y[ok] - y[ok].mean()))),
        "zero_predictor_mae": float(np.mean(np.abs(y[ok]))),
        "n": int(ok.sum()),
        "n_splits": n_splits,
        "n_groups": n_groups,
    }


def text_only_proxy(samples: list[dict]) -> dict:
    """TF-IDF + ridge from text alone to the normalized change, grouped CV by split_group."""
    texts = np.array([s["text"] for s in samples], dtype=object)
    min_df = 2 if len(samples) >= 20 else 1
    return _grouped_cv(
        samples,
        lambda i: texts[i],
        lambda: make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2), min_df=min_df, sublinear_tf=True), Ridge(alpha=1.0)
        ),
    )


def ts_only_proxy(samples: list[dict]) -> dict:
    """Ridge on input-window summary features only, same target and folds as the text proxy."""
    feats = _ts_features(samples)
    return _grouped_cv(samples, lambda i: feats[i], lambda: Ridge(alpha=1.0))


def joint_headroom(samples: list[dict]) -> dict:
    """Rough 'text adds something' indicator from the two proxies' out-of-fold errors.

    text_helps: share of samples where the TS-only error is above its median AND the text-only
    error is lower than the TS-only error. ts_helps is the reverse (text error above its median
    and TS-only lower). Both are heuristics, not an estimate of what a joint model would gain.
    """
    text, ts = text_only_proxy(samples), ts_only_proxy(samples)
    te, se = text["oof_error"], ts["oof_error"]
    ok = np.isfinite(te) & np.isfinite(se)
    te, se = te[ok], se[ok]
    text_helps = (se > np.median(se)) & (te < se)
    ts_helps = (te > np.median(te)) & (se < te)
    n = int(ok.sum())
    return {
        "text_helps_frac": float(text_helps.mean()) if n else 0.0,
        "ts_helps_frac": float(ts_helps.mean()) if n else 0.0,
        "text_helps_n": int(text_helps.sum()),
        "ts_helps_n": int(ts_helps.sum()),
        "n": n,
        "text_mae": text["mae"],
        "ts_mae": ts["mae"],
    }


def _describe(values) -> dict:
    s = pd.Series(values, dtype=float)
    return s.describe().to_dict() if len(s) else {}


def length_stats(samples: list[dict]) -> dict:
    """Token counts for text, TS lengths, missingness, and counts per split_group / text_kind."""
    meta = [s["meta"] for s in samples]
    return {
        "n": len(samples),
        "text_tokens": _describe([len(s["text"].split()) for s in samples]),
        "input_len": _describe([len(s["input_window"]) for s in samples]),
        "output_len": _describe([len(s["output_window"]) for s in samples]),
        "input_missing_frac": _describe([np.isnan(_arr(s["input_window"])).mean() for s in samples]),
        "output_missing_frac": _describe([np.isnan(_arr(s["output_window"])).mean() for s in samples]),
        "per_split_group": pd.Series([m["split_group"] for m in meta]).value_counts().to_dict(),
        "per_text_kind": pd.Series([m["text_kind"] for m in meta]).value_counts().to_dict(),
    }


def dump_review_sheet(samples: list[dict], n: int = 40, path="review_sheet.csv", seed: int = 0):
    """Write a CSV of n random samples for human audit, round-robin over split_group x text_kind."""
    rng = np.random.default_rng(seed)
    strata: dict = {}
    for s in samples:
        strata.setdefault((s["meta"]["split_group"], s["meta"]["text_kind"]), []).append(s)
    queues = [[v[i] for i in rng.permutation(len(v))] for v in strata.values()]
    queues = [queues[i] for i in rng.permutation(len(queues))]
    picked = []
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop())
    rows = []
    for s in picked:
        x, y = _arr(s["input_window"]), _arr(s["output_window"])
        meta = s["meta"]
        rows.append(
            {
                "sample_id": sample_id(s),
                "source": meta["source"],
                "entity_id": meta["entity_id"],
                "issue_time": meta["issue_time"],
                "text_kind": meta["text_kind"],
                "split_group": meta["split_group"],
                "has_numeric_forecast": meta["has_numeric_forecast"],
                "text": s["text"][:600],
                "n_in": len(x),
                "n_out": len(y),
                "last_in": None if np.isnan(x).all() else float(x[np.isfinite(x)][-1]),
                "mean_out": None if np.isnan(y).all() else float(np.nanmean(y)),
                "missing_in": float(np.isnan(x).mean()),
                "missing_out": float(np.isnan(y).mean()),
            }
        )
    df = pd.DataFrame(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df
