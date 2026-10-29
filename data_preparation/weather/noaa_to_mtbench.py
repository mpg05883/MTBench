import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--noaa_folder", type=str, default="../../data/noaa-weather/forecast_hourly")
parser.add_argument("--split", type=str, default="test", help="test or test_unseen_station")
parser.add_argument(
    "--save_path", type=str, default="../../data/processed/weather/noaa_aligned_in7days_out1days"
)
parser.add_argument(
    "--mtbench_weather_dir", type=str, default="../../data/processed/weather",
    help="existing MTBench weather folders, used to drop overlapping samples",
)
parser.add_argument(
    "--keep_event_extends_into_target",
    action="store_true",
    help="keep samples whose event continues into the forecast window",
)
args = parser.parse_args()

noaa_folder = Path(args.noaa_folder)
save_path = Path(args.save_path)
save_path.mkdir(parents=True, exist_ok=True)

npz = np.load(noaa_folder / f"{args.split}.npz", allow_pickle=False)
channels = [str(c) for c in npz["channels"]]
temperature = npz["x"][:, :, channels.index("temperature")]
with open(noaa_folder / f"{args.split}_meta.jsonl") as f:
    metas = [json.loads(line) for line in f]
assert len(metas) == len(temperature)


def interpolate_nans(series: np.ndarray) -> np.ndarray:
    return pd.Series(series).interpolate(limit_direction="both").to_numpy()


def build_text(meta: dict) -> str:
    parts = [meta["text_summary"]]
    if meta["episode_narratives"]:
        parts.append("Episode Narrative: " + " ".join(meta["episode_narratives"]))
    if meta["event_narratives"]:
        parts.append("Event Narrative: " + " ".join(meta["event_narratives"]))
    return " ".join(parts)


def load_mtbench_windows(weather_dir: Path) -> dict:
    """Map station -> list of (start, end) covering input and output timestamps."""
    windows = {}
    for json_file in weather_dir.glob("*/*.json"):
        if json_file.parent.name.startswith("noaa_"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        timestamps = data["input_timestamps"] + data.get("output_timestamps", [])
        station = json_file.stem.rsplit("_", 1)[0]
        windows.setdefault(station, []).append((timestamps[0], timestamps[-1]))
    return windows


mtbench_windows = load_mtbench_windows(Path(args.mtbench_weather_dir))

written = skipped = overlapped = 0
for meta, series in zip(metas, temperature):
    history_len, horizon = meta["history_len"], meta["horizon"]
    if meta["event_extends_into_target"] and not args.keep_event_extends_into_target:
        skipped += 1
        continue
    # drop events starting in the forecast window (the report would leak the answer)
    if any(e["begin_lst"] >= meta["target_start_local"] for e in meta["events"]):
        skipped += 1
        continue
    if np.isnan(series).mean() >= 0.7:
        skipped += 1
        continue

    series = interpolate_nans(series)
    timestamps = pd.date_range(
        meta["history_start_local"], periods=history_len + horizon, freq="h"
    ).strftime("%Y-%m-%d %H:%M:%S").tolist()

    # drop samples whose input/output dates overlap an MTBench window at the same station
    if any(
        timestamps[0] <= end and start <= timestamps[-1]
        for start, end in mtbench_windows.get(meta["station"], [])
    ):
        overlapped += 1
        continue

    sample = {
        "text": build_text(meta),
        "input_timestamps": timestamps[:history_len],
        "input_window": series[:history_len].round(2).tolist(),
        "output_timestamps": timestamps[history_len:],
        "output_window": series[history_len:].round(2).tolist(),
    }
    with open(save_path / f"{meta['sample_id']}.json", "w") as f:
        json.dump(sample, f, indent=2)
    written += 1

print(
    f"Wrote {written} samples to {save_path} "
    f"(skipped {skipped}, dropped {overlapped} overlapping MTBench)"
)
