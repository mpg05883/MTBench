"""nws_afd entry point (scripts/sources/<source>.py convention); logic is in mtbench.adapters.nws_afd.

  python scripts/sources/nws_afd.py plan|fetch [args]   -> data_preparation/weather/nws_afd_download.py
  python scripts/sources/nws_afd.py build [args]        -> data_preparation/weather/nws_afd_to_mtbench.py
"""
import runpy
import sys
from pathlib import Path

WEATHER = Path(__file__).resolve().parents[2] / "data_preparation" / "weather"
STEPS = {"plan": ("nws_afd_download.py", ["--plan"]), "fetch": ("nws_afd_download.py", []),
         "build": ("nws_afd_to_mtbench.py", [])}

if len(sys.argv) < 2 or sys.argv[1] not in STEPS:
    sys.exit(__doc__)
script, extra = STEPS[sys.argv[1]]
sys.argv = [script, *extra, *sys.argv[2:]]
sys.path.insert(0, str(WEATHER))
runpy.run_path(str(WEATHER / script), run_name="__main__")
