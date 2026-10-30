import pandas as pd
import pytest

from mtbench.adapters.schema import make_meta


def build_sample(
    entity="STN1",
    issue_time="2024-01-07 12:00:00",
    text="Rain is expected later this week.",
    n_in=48,
    n_out=24,
    start="2024-01-06 00:00:00",
    group="g1",
    text_kind="forecast_of_future",
    in_values=None,
    out_values=None,
    **meta_kwargs,
):
    stamps = pd.date_range(start, periods=n_in + n_out, freq="h").strftime("%Y-%m-%d %H:%M:%S")
    stamps = stamps.tolist()
    in_ts, out_ts = stamps[:n_in], stamps[n_in:]
    return {
        "text": text,
        "input_timestamps": in_ts,
        "input_window": in_values if in_values is not None else [10.0 + (i % 24) for i in range(n_in)],
        "output_timestamps": out_ts,
        "output_window": out_values if out_values is not None else [12.0] * n_out,
        "meta": make_meta(
            source="toy",
            domain="weather",
            entity_id=entity,
            issue_time=issue_time,
            text_kind=text_kind,
            has_numeric_forecast=False,
            split_group=group,
            output_timestamps=out_ts,
            **meta_kwargs,
        ),
    }


@pytest.fixture
def sample():
    return build_sample()
