"""Common sample filters. Each check returns None when the sample is kept, else a drop reason."""
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from datasketch import MinHash, MinHashLSH

from mtbench.adapters.schema import to_timestamp
from mtbench.config import (
    MINHASH_NUM_PERM,
    MINHASH_SHINGLE,
    MINHASH_THRESHOLD,
    MISSING_FRAC_MAX,
)


def _missing_frac(values: list) -> float:
    arr = np.array([np.nan if v is None else v for v in values], dtype=float)
    return float(np.isnan(arr).mean()) if arr.size else 1.0


def check_issue_time(sample: dict) -> Optional[str]:
    """The text must exist by the end of the input window (no future leakage)."""
    issue = to_timestamp(sample["meta"]["issue_time"])
    if issue > to_timestamp(sample["input_timestamps"][-1]):
        return "text_after_input_end"
    return None


def check_missing(sample: dict) -> Optional[str]:
    for side in ("input", "output"):
        if _missing_frac(sample[f"{side}_window"]) >= MISSING_FRAC_MAX:
            return "ts_missing_ge70pct"
    return None


def check_complete(
    sample: dict, expected_in: Optional[int] = None, expected_out: Optional[int] = None
) -> Optional[str]:
    """Windows must have the declared length, increasing timestamps and a usable last input value."""
    for side, expected in (("input", expected_in), ("output", expected_out)):
        stamps = [to_timestamp(t) for t in sample[f"{side}_timestamps"]]
        if len(stamps) != len(sample[f"{side}_window"]):
            return "ts_window_incomplete"
        if expected is not None and len(stamps) != expected:
            return "ts_window_incomplete"
        if any(b <= a for a, b in zip(stamps, stamps[1:])):
            return "ts_window_incomplete"
    last = sample["input_window"][-1]
    if last is None or not np.isfinite(last):
        return "ts_window_incomplete"
    return None


def station_of(json_file: Path) -> str:
    """Entity from an existing MTBench file name: <station>_<k or date>.json."""
    return json_file.stem.rsplit("_", 1)[0]


def load_mtbench_windows(
    dirs: Iterable[Path], skip_prefixes: tuple[str, ...] = ("noaa_",)
) -> dict:
    """Map entity -> list of (start, end) over input+output timestamps of existing samples.

    Same logic as data_preparation/weather/noaa_to_mtbench.py: <dir>/*/*.json, skipping the
    subfolders that start with `skip_prefixes` (those are the converted NOAA outputs themselves).
    """
    windows: dict = {}
    for root in dirs:
        for json_file in Path(root).glob("*/*.json"):
            if json_file.parent.name.startswith(skip_prefixes):
                continue
            with open(json_file) as f:
                data = json.load(f)
            stamps = data["input_timestamps"] + data.get("output_timestamps", [])
            if not stamps:
                continue
            windows.setdefault(station_of(json_file), []).append(
                (to_timestamp(stamps[0]), to_timestamp(stamps[-1]))
            )
    return windows


def check_overlap(sample: dict, windows: dict) -> Optional[str]:
    start = to_timestamp(sample["input_timestamps"][0])
    end = to_timestamp(sample["output_timestamps"][-1])
    for w_start, w_end in windows.get(sample["meta"]["entity_id"], []):
        if start <= w_end and w_start <= end:
            return "overlaps_mtbench"
    return None


_NON_WORD = re.compile(r"[^a-z0-9#\s]")
_DIGITS = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lowercase, collapse digit runs to '#', drop punctuation and extra whitespace."""
    text = _DIGITS.sub("#", text.lower())
    return _SPACE.sub(" ", _NON_WORD.sub(" ", text)).strip()


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()


def _minhash(norm: str) -> MinHash:
    tokens = norm.split()
    n = MINHASH_SHINGLE
    shingles = {" ".join(tokens[i : i + n]) for i in range(max(1, len(tokens) - n + 1))}
    mh = MinHash(num_perm=MINHASH_NUM_PERM)
    for s in shingles:
        mh.update(s.encode("utf-8"))
    return mh


class TextDeduper:
    """Exact (normalized-text hash) and near (MinHash LSH) duplicate detection, stateful."""

    def __init__(self, threshold: float = MINHASH_THRESHOLD):
        self.threshold = threshold
        self._hashes: set[str] = set()
        # LSH is probabilistic and misses some pairs right at the threshold, so retrieve
        # candidates with a looser threshold and verify each against the real one.
        self._lsh = MinHashLSH(threshold=max(0.1, threshold - 0.15), num_perm=MINHASH_NUM_PERM)
        self._minhashes: dict[str, MinHash] = {}

    def check(self, text: str) -> Optional[str]:
        """Return a drop reason, or register the text and return None."""
        norm = normalize_text(text)
        digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()
        if digest in self._hashes:
            return "dup_exact"
        mh = _minhash(norm)
        if any(mh.jaccard(self._minhashes[k]) >= self.threshold for k in self._lsh.query(mh)):
            return "dup_near"
        self._hashes.add(digest)
        key = str(len(self._minhashes))
        self._minhashes[key] = mh
        self._lsh.insert(key, mh)
        return None
