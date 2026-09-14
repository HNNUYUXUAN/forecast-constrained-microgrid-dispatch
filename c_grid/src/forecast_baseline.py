"""Causal forecasting baselines for Problem 2 and later comparisons."""

from __future__ import annotations

import pandas as pd

from .data_loader import load_attachment2_actual_profiles


def build_lag7_causal_forecasts(
    actual_profiles: pd.DataFrame | None = None,
    *,
    start_date: str = "2025-02-01",
    end_date: str = "2025-12-31",
) -> pd.DataFrame:
    """Use the same weekday one week earlier as a leakage-free baseline.

    Every target record carries its source date so the information boundary can
    be audited directly.  This simple model is a baseline, not a final forecast.
    """

    if actual_profiles is None:
        actual_profiles = load_attachment2_actual_profiles()
    required = {
        "date",
        "period_index",
        "source_time_label",
        "load_actual_kw",
        "pv_actual_kw",
    }
    if set(actual_profiles.columns) != required:
        raise ValueError(f"Actual profile columns must be exactly {sorted(required)}.")

    actual = actual_profiles.copy()
    actual["date"] = pd.to_datetime(actual["date"], errors="raise").dt.normalize()
    source = actual.rename(
        columns={
            "date": "forecast_source_date",
            "load_actual_kw": "load_forecast_kw",
            "pv_actual_kw": "pv_forecast_kw",
        }
    )
    source["date"] = source["forecast_source_date"] + pd.Timedelta(days=7)

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    forecast = source.loc[source["date"].between(start, end)].copy()
    columns = [
        "date",
        "period_index",
        "source_time_label",
        "forecast_source_date",
        "load_forecast_kw",
        "pv_forecast_kw",
    ]
    forecast = forecast.loc[:, columns].sort_values(
        ["date", "period_index"], ignore_index=True
    )

    if forecast.empty:
        raise ValueError("The requested causal forecast range is empty.")
    if not (forecast["forecast_source_date"] < forecast["date"]).all():
        raise AssertionError("Forecast source dates must precede every target date.")
    counts = forecast.groupby("date")["period_index"].nunique()
    if not (counts == 144).all():
        raise ValueError("Each forecast date must contain all 144 periods.")
    return forecast


def build_lag7_quantile_net_forecasts(
    actual_profiles: pd.DataFrame | None = None,
    *,
    quantile: float = 0.8,
    residual_window_days: int = 28,
    minimum_residual_days: int = 14,
    start_date: str = "2025-02-01",
    end_date: str = "2025-12-31",
) -> pd.DataFrame:
    """Add a causal per-period residual quantile to the lag-7 net-load forecast.

    For target day ``d``, the base profile is day ``d-7`` and the residual
    distribution uses only errors observed through ``d-1``.  With normal planned
    energy priced at ``c`` and emergency energy at ``5c``, the one-period
    newsvendor critical fractile is (5c-c)/(5c-c+c) = 0.8.
    """

    if not 0 < quantile < 1:
        raise ValueError("quantile must be in (0, 1).")
    if residual_window_days < minimum_residual_days or minimum_residual_days < 1:
        raise ValueError("Residual-window parameters are inconsistent.")
    if actual_profiles is None:
        actual_profiles = load_attachment2_actual_profiles()

    actual = actual_profiles.copy()
    actual["date"] = pd.to_datetime(actual["date"], errors="raise").dt.normalize()
    actual["net_load_kw"] = actual["load_actual_kw"] - actual["pv_actual_kw"]
    net = actual.pivot(index="date", columns="period_index", values="net_load_kw").sort_index()
    if net.shape != (365, 144):
        raise ValueError(f"Expected a 365 by 144 net-load matrix, got {net.shape}.")

    lag7 = net.shift(7)
    realized_lag7_error = net - lag7
    causal_margin = (
        realized_lag7_error.shift(1)
        .rolling(
            window=residual_window_days,
            min_periods=minimum_residual_days,
        )
        .quantile(quantile)
    )
    forecast_net = lag7 + causal_margin
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    selected = forecast_net.loc[start:end]
    margins = causal_margin.loc[start:end]
    if selected.isna().any().any() or margins.isna().any().any():
        raise ValueError("Insufficient causal residual history for the requested range.")

    long_forecast = selected.stack().rename("net_forecast_kw").reset_index()
    long_margin = margins.stack().rename("net_residual_quantile_kw").reset_index()
    result = long_forecast.merge(
        long_margin,
        on=["date", "period_index"],
        how="inner",
        validate="one_to_one",
    )
    labels = (
        actual.loc[:, ["period_index", "source_time_label"]]
        .drop_duplicates()
        .sort_values("period_index")
    )
    result = result.merge(labels, on="period_index", how="left", validate="many_to_one")
    result["forecast_source_date"] = result["date"] - pd.Timedelta(days=7)
    result["latest_training_date"] = result["date"] - pd.Timedelta(days=1)
    result["load_forecast_kw"] = result["net_forecast_kw"].clip(lower=0.0)
    result["pv_forecast_kw"] = (-result["net_forecast_kw"]).clip(lower=0.0)
    result = result.loc[
        :,
        [
            "date",
            "period_index",
            "source_time_label",
            "forecast_source_date",
            "latest_training_date",
            "load_forecast_kw",
            "pv_forecast_kw",
            "net_residual_quantile_kw",
        ],
    ].sort_values(["date", "period_index"], ignore_index=True)
    if not (result["latest_training_date"] < result["date"]).all():
        raise AssertionError("Residual training data leaked into its target date.")
    return result
