"""Download NWS AFDs (IEM AFOS archive) and resolve station -> WFO for the nws_afd source.

GHCNh station files already in data/raw/nws_afd/ghcnh are reused, never re-downloaded.
Every URL fetched is logged to data/raw/nws_afd/MANIFEST.md.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mtbench.adapters.nws_afd import NwsAfdAdapter  # noqa: E402

SUBSET_STATIONS = ["USW00003030", "USW00000379", "USW00000120"]  # AMA, PHI, RNK


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stations", nargs="*", default=None, help="GHCN station ids (default: all on disk)")
    parser.add_argument("--start_year", type=int, default=2019)
    parser.add_argument("--end_year", type=int, default=2023)
    parser.add_argument("--subset", action="store_true", help="3 stations, 1 year (2022)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")


def adapter_kwargs(args) -> dict:
    if args.subset:
        return {"stations": SUBSET_STATIONS, "start_year": 2022, "end_year": 2022, "subset": True, "delay": args.delay}
    return {"stations": args.stations, "start_year": args.start_year, "end_year": args.end_year, "delay": args.delay}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--plan", action="store_true", help="print the download plan and stop")
    parser.add_argument("--allow_large", action="store_true", help="only after the user OKs >2 GB")
    args = parser.parse_args()
    adapter = NwsAfdAdapter(**adapter_kwargs(args))
    if args.plan:
        adapter.plan(adapter.resolve_stations())
    else:
        adapter.download(allow_large=args.allow_large)
