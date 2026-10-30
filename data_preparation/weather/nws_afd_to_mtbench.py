"""Convert downloaded AFDs + GHCNh temperature into MTBench samples (7d->1d and 14d->3d, hourly)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtbench.adapters.nws_afd import SETTINGS, NwsAfdAdapter  # noqa: E402
from nws_afd_download import add_common_args, adapter_kwargs  # noqa: E402


def print_samples(adapter: NwsAfdAdapter, n: int = 5, chars: int = 700) -> None:
    files = sorted(adapter.out_dir.glob("*.json"))
    if not files:
        print("no samples written")
        return
    for f in [files[int(i * (len(files) - 1) / max(n - 1, 1))] for i in range(min(n, len(files)))]:
        s = json.loads(f.read_text())
        m = s["meta"]
        print(f"\n=== {f.name}  station={m['entity_id']} wfo={m['wfo']} issue={m['issue_time']} "
              f"(utc {m['issue_time_utc']}, gap {m['afd_gap_hours']}h)")
        print(f"input  {s['input_timestamps'][0]} .. {s['input_timestamps'][-1]} ({len(s['input_window'])})")
        print(f"output {s['output_timestamps'][0]} .. {s['output_timestamps'][-1]} ({len(s['output_window'])})")
        print(f"has_numeric_forecast={m['has_numeric_forecast']} sections={m['sections']}")
        print(s["text"][:chars] + (" ..." if len(s["text"]) > chars else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--settings", nargs="*", default=list(SETTINGS), choices=list(SETTINGS))
    parser.add_argument("--no_overlap_check", action="store_true")
    parser.add_argument("--show", type=int, default=5, help="samples to print per setting")
    args = parser.parse_args()
    for setting in args.settings:
        adapter = NwsAfdAdapter(setting=setting, check_overlap=not args.no_overlap_check, **adapter_kwargs(args))
        print(f"\n##### setting={setting} -> {adapter.out_dir}")
        adapter.run()
        print_samples(adapter, args.show)
