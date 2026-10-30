"""Sample schema: the weather schema plus a `meta` dict."""
import json
import math
from pathlib import Path
from typing import TypedDict

import pandas as pd

from mtbench.config import POST_CUTOFF_DATE, TEXT_KINDS

REQUIRED_KEYS = (
    "text", "input_timestamps", "input_window", "output_timestamps", "output_window", "meta",
)


class Meta(TypedDict):
    source: str
    domain: str
    entity_id: str
    issue_time: str
    text_kind: str
    has_numeric_forecast: bool
    event_extends_into_target: bool
    post_cutoff: bool
    split_group: str


def to_timestamp(value) -> pd.Timestamp:
    """Parse "YYYY-MM-DD HH:MM:SS" strings (weather) or epoch seconds (finance)."""
    if isinstance(value, (int, float)):
        return pd.Timestamp(value, unit="s")
    return pd.Timestamp(value)


def make_meta(
    *,
    source: str,
    domain: str,
    entity_id: str,
    issue_time: str,
    text_kind: str,
    has_numeric_forecast: bool,
    split_group: str,
    output_timestamps: list,
    event_extends_into_target: bool = False,
) -> Meta:
    """Build `meta`; post_cutoff is derived from the first output timestamp, never passed in."""
    if text_kind not in TEXT_KINDS:
        raise ValueError(f"text_kind must be one of {TEXT_KINDS}, got {text_kind!r}")
    post_cutoff = to_timestamp(output_timestamps[0]) > pd.Timestamp(POST_CUTOFF_DATE)
    return Meta(
        source=source,
        domain=domain,
        entity_id=entity_id,
        issue_time=str(issue_time),
        text_kind=text_kind,
        has_numeric_forecast=bool(has_numeric_forecast),
        event_extends_into_target=bool(event_extends_into_target),
        post_cutoff=bool(post_cutoff),
        split_group=str(split_group),
    )


def validate_sample(sample: dict) -> list[str]:
    """Return a list of schema problems (empty when the sample is valid)."""
    problems = [f"missing key: {k}" for k in REQUIRED_KEYS if k not in sample]
    if problems:
        return problems
    meta = sample["meta"]
    for key in Meta.__annotations__:
        if key not in meta:
            problems.append(f"missing meta key: {key}")
    if meta.get("text_kind") not in TEXT_KINDS:
        problems.append(f"bad text_kind: {meta.get('text_kind')!r}")
    for side in ("input", "output"):
        if len(sample[f"{side}_timestamps"]) != len(sample[f"{side}_window"]):
            problems.append(f"{side} timestamps/window length mismatch")
        if not sample[f"{side}_window"]:
            problems.append(f"empty {side} window")
    if not problems and to_timestamp(sample["output_timestamps"][0]) <= to_timestamp(
        sample["input_timestamps"][-1]
    ):
        problems.append("output window does not start after input window")
    return problems


def _strict(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_strict(v) for v in value]
    if isinstance(value, dict):
        return {k: _strict(v) for k, v in value.items()}
    return value


def write_sample(sample: dict, out_dir: Path, name: str) -> Path:
    """Write one sample as strict JSON (NaN -> null) to out_dir/<name>.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    with open(path, "w") as f:
        json.dump(_strict(sample), f, indent=2)
    return path
