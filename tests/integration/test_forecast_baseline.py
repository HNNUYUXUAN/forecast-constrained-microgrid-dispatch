from __future__ import annotations

from c_grid.src.forecast_baseline import (
    build_lag7_causal_forecasts,
    build_lag7_quantile_net_forecasts,
)


def test_lag7_forecast_is_complete_and_causal() -> None:
    forecast = build_lag7_causal_forecasts()

    assert forecast["date"].nunique() == 334
    assert len(forecast) == 334 * 144
    assert (forecast["forecast_source_date"] < forecast["date"]).all()
    assert (
        forecast["date"] - forecast["forecast_source_date"]
    ).dt.days.unique().tolist() == [7]
    assert forecast.groupby("date")["period_index"].nunique().eq(144).all()


def test_quantile_margin_uses_only_prior_residuals() -> None:
    forecast = build_lag7_quantile_net_forecasts()

    assert forecast["date"].nunique() == 334
    assert len(forecast) == 334 * 144
    assert (forecast["latest_training_date"] < forecast["date"]).all()
    assert (forecast["forecast_source_date"] < forecast["date"]).all()
    assert forecast["net_residual_quantile_kw"].notna().all()
