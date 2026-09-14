"""Problem 2 causal day-ahead baseline and realized settlement."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .data_loader import load_attachment2_actual_profiles, load_problem1
from .forecast_baseline import (
    build_lag7_causal_forecasts,
    build_lag7_quantile_net_forecasts,
)
from .problem1 import solve_problem1


SPECIFIED_REPORT_DATES = (
    "2025-03-20",
    "2025-06-21",
    "2025-09-23",
    "2025-12-21",
)


@dataclass(frozen=True)
class Problem2Summary:
    solver_status: str
    evaluated_days: int
    planned_purchase_kwh: float
    emergency_purchase_kwh: float
    planned_cost_yuan: float
    emergency_cost_yuan: float
    total_cost_yuan: float
    actual_curtailment_kwh: float
    max_settlement_balance_residual_kwh: float


def _evaluate_problem2(
    actual: pd.DataFrame,
    forecasts: pd.DataFrame,
    dates: Iterable[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, Problem2Summary]:
    """Evaluate supplied causal forecasts under realized load and PV.

    This baseline keeps each day's terminal storage equal to its initial storage,
    using the common Problem 1 LP.  Realized deficits are covered by emergency
    purchases at five times the fixed daily tariff; realized surpluses are
    curtailed.  The model never uses target-day actuals when creating the plan.
    """

    fixed_price = load_problem1().loc[
        :, ["period_index", "source_time_label", "price_yuan_per_kwh"]
    ]

    available_dates = pd.DatetimeIndex(forecasts["date"].drop_duplicates().sort_values())
    if dates is None:
        selected_dates = available_dates
    else:
        selected_dates = pd.DatetimeIndex(pd.to_datetime(list(dates), errors="raise"))
        missing = selected_dates.difference(available_dates)
        if len(missing):
            formatted = [value.strftime("%Y-%m-%d") for value in missing]
            raise ValueError(f"Dates fall outside the causal evaluation range: {formatted}")

    interval_results: list[pd.DataFrame] = []
    daily_results: list[dict[str, object]] = []
    step_hours = 1.0 / 6.0

    for target_date in selected_dates:
        forecast_day = forecasts.loc[forecasts["date"].eq(target_date)].copy()
        actual_day = actual.loc[actual["date"].eq(target_date)].copy()
        if len(forecast_day) != 144 or len(actual_day) != 144:
            raise ValueError(f"Incomplete data for {target_date:%Y-%m-%d}.")

        planning_data = fixed_price.merge(
            forecast_day.loc[
                :, ["period_index", "source_time_label", "load_forecast_kw", "pv_forecast_kw"]
            ],
            on=["period_index", "source_time_label"],
            how="inner",
            validate="one_to_one",
        ).rename(columns={"load_forecast_kw": "load_kw"})
        planning_data = planning_data.loc[
            :,
            [
                "period_index",
                "source_time_label",
                "price_yuan_per_kwh",
                "load_kw",
                "pv_forecast_kw",
            ],
        ]
        schedule, _ = solve_problem1(planning_data)

        settled = schedule.merge(
            actual_day.loc[
                :, ["period_index", "source_time_label", "load_actual_kw", "pv_actual_kw"]
            ],
            on=["period_index", "source_time_label"],
            how="inner",
            validate="one_to_one",
        )
        actual_net_requirement = (
            settled["load_actual_kw"].to_numpy(float)
            - settled["pv_actual_kw"].to_numpy(float)
        ) * step_hours
        scheduled_net_supply = (
            settled["grid_purchase_kwh"].to_numpy(float)
            + settled["discharge_kwh"].to_numpy(float)
            - settled["charge_kwh"].to_numpy(float)
        )
        deficit = actual_net_requirement - scheduled_net_supply
        emergency = np.maximum(deficit, 0.0)
        actual_curtailment = np.maximum(-deficit, 0.0)
        price = settled["price_yuan_per_kwh"].to_numpy(float)
        emergency_cost = 5.0 * price * emergency
        settlement_residual = (
            scheduled_net_supply + emergency - actual_net_requirement - actual_curtailment
        )

        settled.insert(0, "date", target_date)
        settled["forecast_source_date"] = forecast_day["forecast_source_date"].iloc[0]
        settled["emergency_purchase_kwh"] = emergency
        settled["actual_curtailment_kwh"] = actual_curtailment
        settled["emergency_cost_yuan"] = emergency_cost
        settled["realized_total_cost_yuan"] = (
            settled["period_purchase_cost_yuan"] + emergency_cost
        )
        interval_results.append(settled)

        daily_results.append(
            {
                "date": target_date,
                "forecast_source_date": forecast_day["forecast_source_date"].iloc[0],
                "planned_purchase_kwh": float(settled["grid_purchase_kwh"].sum()),
                "emergency_purchase_kwh": float(emergency.sum()),
                "planned_cost_yuan": float(settled["period_purchase_cost_yuan"].sum()),
                "emergency_cost_yuan": float(emergency_cost.sum()),
                "total_cost_yuan": float(settled["realized_total_cost_yuan"].sum()),
                "actual_curtailment_kwh": float(actual_curtailment.sum()),
                "load_mae_kw": float(
                    np.mean(
                        np.abs(
                            settled["load_kw"].to_numpy(float)
                            - settled["load_actual_kw"].to_numpy(float)
                        )
                    )
                ),
                "pv_mae_kw": float(
                    np.mean(
                        np.abs(
                            settled["pv_forecast_kw"].to_numpy(float)
                            - settled["pv_actual_kw"].to_numpy(float)
                        )
                    )
                ),
                "max_settlement_balance_residual_kwh": float(
                    np.max(np.abs(settlement_residual))
                ),
            }
        )

    intervals = pd.concat(interval_results, ignore_index=True)
    daily = pd.DataFrame(daily_results).sort_values("date", ignore_index=True)
    summary = Problem2Summary(
        solver_status="PASS",
        evaluated_days=len(daily),
        planned_purchase_kwh=float(daily["planned_purchase_kwh"].sum()),
        emergency_purchase_kwh=float(daily["emergency_purchase_kwh"].sum()),
        planned_cost_yuan=float(daily["planned_cost_yuan"].sum()),
        emergency_cost_yuan=float(daily["emergency_cost_yuan"].sum()),
        total_cost_yuan=float(daily["total_cost_yuan"].sum()),
        actual_curtailment_kwh=float(daily["actual_curtailment_kwh"].sum()),
        max_settlement_balance_residual_kwh=float(
            daily["max_settlement_balance_residual_kwh"].max()
        ),
    )
    return intervals, daily, summary


def evaluate_lag7_problem2(
    dates: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Problem2Summary]:
    """Evaluate the unadjusted same-weekday forecast baseline."""

    actual = load_attachment2_actual_profiles()
    forecasts = build_lag7_causal_forecasts(actual)
    return _evaluate_problem2(actual, forecasts, dates)


def evaluate_quantile_problem2(
    dates: Iterable[str] | None = None,
    *,
    quantile: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame, Problem2Summary]:
    """Evaluate the causal lag-7 forecast with a net-load quantile margin."""

    actual = load_attachment2_actual_profiles()
    forecasts = build_lag7_quantile_net_forecasts(actual, quantile=quantile)
    return _evaluate_problem2(actual, forecasts, dates)


def main() -> None:
    _, daily, summary = evaluate_lag7_problem2(SPECIFIED_REPORT_DATES)
    print(daily.to_string(index=False))
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
