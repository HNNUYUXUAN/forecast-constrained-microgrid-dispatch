from __future__ import annotations

import pytest

from c_grid.src.problem1 import solve_problem1


def test_problem1_baseline_is_feasible_and_nondegenerate() -> None:
    schedule, metrics = solve_problem1()

    assert len(schedule) == 144
    assert metrics.solver_status == "PASS"
    assert metrics.purchase_cost_yuan > 0
    assert metrics.purchased_energy_kwh > 0
    assert metrics.initial_storage_kwh == pytest.approx(6000.0, abs=1e-6)
    assert metrics.final_storage_kwh == pytest.approx(6000.0, abs=1e-6)
    assert metrics.minimum_storage_kwh >= 1200.0 - 1e-6
    assert metrics.maximum_storage_kwh <= 10800.0 + 1e-6
    assert metrics.max_balance_residual_kwh <= 1e-6
    assert metrics.max_storage_residual_kwh <= 1e-6
    assert metrics.simultaneous_charge_discharge_kwh <= 1e-6
