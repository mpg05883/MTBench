from pathlib import Path
from typing import Literal


def resolve_root_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def resolve_data_dir() -> Path:
    return resolve_root_dir() / "data"


def resolve_processed_data_dir() -> Path:
    return resolve_data_dir() / "processed"


def resolve_finance_data_dir() -> Path:
    return resolve_processed_data_dir() / "finance"


def resolve_weather_data_dir() -> Path:
    return resolve_processed_data_dir() / "weather"


def resolve_finance_aligned_pairs_short_data_dir() -> Path:
    return resolve_finance_data_dir() / "aligned_in7days_out1days"


def resolve_finance_aligned_pairs_long_data_dir() -> Path:
    return resolve_finance_data_dir() / "aligned_in30days_out7days"


def resolve_finance_QA_short_data_dir() -> Path:
    return resolve_finance_data_dir() / "QAshort"


def resolve_finance_QA_long_data_dir() -> Path:
    return resolve_finance_data_dir() / "QAlong"


def resolve_finance_aligned_pairs_data_path(term: Literal["short", "long"]) -> Path:
    dirpath = (
        resolve_finance_aligned_pairs_short_data_dir()
        if term == "short"
        else resolve_finance_aligned_pairs_long_data_dir()
    )
    return dirpath / "data" / "train-00000-of-00001.parquet"
