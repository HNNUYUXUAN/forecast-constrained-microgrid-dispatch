from __future__ import annotations

from c_grid.src.data_loader import (
    load_attachment2_actual_profiles,
    load_attachment3_forecasts,
    load_attachment4_actual_prices,
    load_problem1,
)


def test_problem1_official_workbook_loads_on_expected_grid() -> None:
    frame = load_problem1()

    assert frame.shape == (144, 5)
    assert frame.iloc[0]["source_time_label"] == "0:10"
    assert frame.iloc[-1]["source_time_label"] == "0:00+1"
    assert frame[["price_yuan_per_kwh", "load_kw", "pv_forecast_kw"]].notna().all().all()


def test_attachment3_dates_are_reconstructed_from_official_workbook() -> None:
    frame = load_attachment3_forecasts()

    assert frame.shape == (1460, 26)
    assert frame["date"].nunique() == 365
    assert frame["issue_hour"].value_counts().to_dict() == {0: 365, 6: 365, 12: 365, 18: 365}
    assert frame["date"].min().strftime("%Y-%m-%d") == "2025-01-01"
    assert frame["date"].max().strftime("%Y-%m-%d") == "2025-12-31"


def test_full_year_actual_profiles_align() -> None:
    profiles = load_attachment2_actual_profiles()
    prices = load_attachment4_actual_prices()

    assert profiles.shape == (365 * 144, 5)
    assert prices.shape == (365 * 144, 4)
    assert profiles[["load_actual_kw", "pv_actual_kw"]].notna().all().all()
    assert prices["price_actual_yuan_per_kwh"].notna().all()
    assert profiles[["date", "period_index"]].equals(prices[["date", "period_index"]])
