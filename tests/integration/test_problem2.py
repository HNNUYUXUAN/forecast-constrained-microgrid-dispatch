from __future__ import annotations

import pytest

from c_grid.src.problem2 import evaluate_lag7_problem2, evaluate_quantile_problem2


def test_problem2_one_day_settlement_is_causal_and_balanced() -> None:
    intervals, daily, summary = evaluate_lag7_problem2(["2025-03-20"])

    assert len(intervals) == 144
    assert len(daily) == 1
    assert summary.solver_status == "PASS"
    assert summary.evaluated_days == 1
    assert (intervals["forecast_source_date"] < intervals["date"]).all()
    assert summary.planned_purchase_kwh > 0
    assert summary.emergency_purchase_kwh >= 0
    assert summary.total_cost_yuan == pytest.approx(
        summary.planned_cost_yuan + summary.emergency_cost_yuan
    )
    assert summary.max_settlement_balance_residual_kwh <= 1e-6


def test_problem2_quantile_baseline_is_causal_and_balanced() -> None:
    intervals, daily, summary = evaluate_quantile_problem2(["2025-03-20"])

    assert len(intervals) == 144
    assert len(daily) == 1
    assert (intervals["forecast_source_date"] < intervals["date"]).all()
    assert summary.max_settlement_balance_residual_kwh <= 1e-6
