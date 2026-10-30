"""SourceAdapter interface and the SampleFilter that counts every dropped sample by reason."""
import re
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from mtbench.adapters import filters
from mtbench.adapters.schema import validate_sample, write_sample
from mtbench.env import get_logger, redact
from mtbench.path import resolve_processed_data_dir, resolve_raw_data_dir


def log_fetch(source: str, url: str, note: str = "") -> None:
    """Append a fetched URL to data/raw/<source>/MANIFEST.md, with key values redacted."""
    manifest = resolve_raw_data_dir() / source / "MANIFEST.md"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = f"- {stamp} {redact(url)}" + (f" ({redact(note)})" if note else "")
    with open(manifest, "a") as f:
        f.write(line + "\n")


class SampleFilter:
    """Runs the common filters in a fixed order and counts kept samples and drops by reason.

    Order: schema, issue time, event-extends-into-target, missing TS, complete TS, overlap with
    existing MTBench windows, adapter-specific checks, then text dedup (last, so that only samples
    that would otherwise be kept register their text).
    """

    def __init__(
        self,
        mtbench_windows: Optional[dict] = None,
        expected_in: Optional[int] = None,
        expected_out: Optional[int] = None,
        keep_event_extends_into_target: bool = False,
        dedup: Optional[filters.TextDeduper] = None,
    ):
        self.mtbench_windows = mtbench_windows or {}
        self.expected_in = expected_in
        self.expected_out = expected_out
        self.keep_event_extends_into_target = keep_event_extends_into_target
        self.dedup = dedup or filters.TextDeduper()
        self.extra: list[tuple[str, Callable[[dict], bool]]] = []
        self.kept = 0
        self.dropped: Counter = Counter()

    def register(self, reason: str, drop_if: Callable[[dict], bool]) -> None:
        """Add an adapter-specific rule: the sample is dropped with `reason` when drop_if is true."""
        self.extra.append((reason, drop_if))

    def reason(self, sample: dict) -> Optional[str]:
        """First failing reason for the sample, or None. Registers the text if it is kept."""
        if validate_sample(sample):
            return "invalid_schema"
        checks = [
            filters.check_issue_time,
            lambda s: None
            if self.keep_event_extends_into_target or not s["meta"]["event_extends_into_target"]
            else "event_extends_into_target",
            filters.check_missing,
            lambda s: filters.check_complete(s, self.expected_in, self.expected_out),
            lambda s: filters.check_overlap(s, self.mtbench_windows),
        ]
        for check in checks:
            reason = check(sample)
            if reason:
                return reason
        for reason, drop_if in self.extra:
            if drop_if(sample):
                return reason
        return self.dedup.check(sample["text"])

    def apply(self, sample: dict) -> bool:
        reason = self.reason(sample)
        if reason:
            self.dropped[reason] += 1
            return False
        self.kept += 1
        return True

    def report(self) -> str:
        total = self.kept + sum(self.dropped.values())
        pct = lambda n: f"{100 * n / total:5.1f}%" if total else "    -"  # noqa: E731
        rows = [("kept", self.kept)] + sorted(self.dropped.items(), key=lambda kv: -kv[1])
        width = max([len(r) for r, _ in rows] + [len("total")])
        lines = [f"{'reason':<{width}}  {'count':>7}  {'share':>6}", "-" * (width + 17)]
        lines += [f"{r:<{width}}  {n:>7}  {pct(n)}" for r, n in rows]
        lines += ["-" * (width + 17), f"{'total':<{width}}  {total:>7}"]
        text = "\n".join(lines)
        print(text)
        return text


class SourceAdapter(ABC):
    """One (time series, aligned text) source. Subclasses implement the five steps.

    Set `name` (folder name under data/raw and data/processed), `domain`, and `out_subdir`
    (e.g. "aligned_in7days_out1days"). Only `download` may touch the network.
    """

    name: str
    domain: str
    out_subdir: str = "aligned"

    def __init__(self):
        self.log = get_logger(f"mtbench.{self.name}")

    @property
    def raw_dir(self) -> Path:
        return resolve_raw_data_dir() / self.name

    @property
    def out_dir(self) -> Path:
        return resolve_processed_data_dir() / self.name / self.out_subdir

    @abstractmethod
    def download(self) -> None:
        """Fetch raw files into raw_dir; call log_fetch(self.name, url) for every URL."""

    @abstractmethod
    def load_ts(self):
        """Load the raw time series (any structure the adapter's align() understands)."""

    @abstractmethod
    def load_text(self):
        """Load the raw text records, each with an issue time."""

    @abstractmethod
    def align(self, ts, texts):
        """Pair each text with its entity's time series; yield (text_record, input/output slices)."""

    @abstractmethod
    def make_samples(self) -> list[dict]:
        """Build schema samples (see schema.make_meta) from load_ts, load_text and align."""

    def sample_filter(self) -> SampleFilter:
        """Override to set expected lengths or the MTBench windows to avoid overlapping."""
        return SampleFilter()

    def run(self) -> SampleFilter:
        flt = self.sample_filter()
        for sample in self.make_samples():
            if flt.apply(sample):
                meta = sample["meta"]
                anchor = re.sub(r"[^0-9A-Za-z]+", "", meta["issue_time"])
                write_sample(sample, self.out_dir, f"{meta['entity_id']}_{anchor}")
        flt.report()
        return flt
