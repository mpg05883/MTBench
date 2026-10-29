import argparse
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

# history channels each question type depends on (besides temperature)
QTYPE_CHANNELS = {
    "temp_max_change": [],
    "temp_min_change": [],
    "precip_total": ["precipitation"],
    "peak_wind_max": ["peak_wind"],
    "pressure_change": ["altimeter"],
    "thunder": ["wx_thunder"],
    "joint_rain_wind": ["precipitation", "peak_wind"],
}

parser = argparse.ArgumentParser()
parser.add_argument("--setting", type=str, choices=["short", "long"], required=True)
parser.add_argument("--noaa_root", type=str, default="../../data/noaa-weather")
parser.add_argument("--weather_dir", type=str, default="../../data/processed/weather")
parser.add_argument("--splits", type=str, nargs="+", default=["test", "train", "val"])
parser.add_argument("--seed", type=int, default=0)
args = parser.parse_args()

scale = "forecast_hourly" if args.setting == "short" else "forecast_hourly_long"
aligned_dir = Path(args.weather_dir) / (
    "noaa_aligned_in7days_out1days" if args.setting == "short" else "noaa_aligned_in14days_out3days"
)
save_path = Path(args.weather_dir) / ("noaa_QAshort" if args.setting == "short" else "noaa_QAlong")
save_path.mkdir(parents=True, exist_ok=True)
rng = random.Random(args.seed)


def clean_series(series: np.ndarray) -> list:
    series = pd.Series(series.astype(np.float64)).interpolate(limit_direction="both").fillna(0.0)
    return series.round(2).tolist()


def format_question(row: dict) -> str:
    options = "\n".join(f"{letter}) {text}" for letter, text in row["options"].items())
    return f"{row['question']}\n\n{options}"


written = skipped = 0
qtype_counts = {}
for split in args.splits:
    npz = np.load(Path(args.noaa_root) / scale / f"{split}.npz", allow_pickle=False)
    channels = [str(c) for c in npz["channels"]]
    all_x = npz["x"]  # each npz["x"] access reloads the array, so read it once
    with open(Path(args.noaa_root) / "qa" / scale / f"{split}.jsonl") as f:
        rows = [json.loads(line) for line in f]

    by_sample = {}
    for row in rows:
        by_sample.setdefault(row["sample_id"], []).append(row)

    for sample_id in sorted(by_sample):
        aligned_file = aligned_dir / f"{sample_id}.json"
        if not aligned_file.exists():  # filtered out of the aligned set (leakage / overlap / missing)
            skipped += 1
            continue
        row = rng.choice(sorted(by_sample[sample_id], key=lambda r: r["qtype"]))
        with open(aligned_file) as f:
            aligned = json.load(f)

        history_len = len(aligned["input_window"])
        x = all_x[row["sample_index"]]
        extra_series = {
            name: clean_series(x[:history_len, channels.index(name)])
            for name in QTYPE_CHANNELS[row["qtype"]]
        }
        sample = {
            "text": aligned["text"],
            "input_timestamps": aligned["input_timestamps"],
            "input_window": aligned["input_window"],
            "extra_series": extra_series,
            "qtype": row["qtype"],
            "question": format_question(row),
            "answer": row["answer"],
        }
        with open(save_path / f"{sample_id}.json", "w") as f:
            json.dump(sample, f, indent=2)
        written += 1
        qtype_counts[row["qtype"]] = qtype_counts.get(row["qtype"], 0) + 1

print(f"Wrote {written} samples to {save_path} (skipped {skipped} without an aligned sample)")
print(qtype_counts)
