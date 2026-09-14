"""Problem 1 deterministic storage scheduling baseline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .data_loader import load_problem1


@dataclass(frozen=True)
class Problem1Metrics:
    solver_status: str
    purchase_cost_yuan: float
    purchased_energy_kwh: float
    charged_energy_kwh: float
    discharged_energy_kwh: float
    curtailed_energy_kwh: float
    initial_storage_kwh: float
    final_storage_kwh: float
    minimum_storage_kwh: float
    maximum_storage_kwh: float
    max_balance_residual_kwh: float
    max_storage_residual_kwh: float
    simultaneous_charge_discharge_kwh: float


def solve_problem1(
    data: pd.DataFrame | None = None,
    *,
    initial_storage_kwh: float = 6000.0,
    storage_efficiency: float = 0.9,
    storage_min_kwh: float = 1200.0,
    storage_max_kwh: float = 10800.0,
    max_power_kw: float = 5000.0,
    step_hours: float = 1.0 / 6.0,
) -> tuple[pd.DataFrame, Problem1Metrics]:
    """Solve the 144-period LP with a lexicographic throughput tie-break.

    The primary objective is exact purchase cost.  A second LP minimizes total
    battery throughput within numerical tolerance of that optimum, removing
    zero-cost simultaneous charge/discharge degeneracy without a binary model.
    """

    if data is None:
        data = load_problem1()
    required = {
        "period_index",
        "source_time_label",
        "price_yuan_per_kwh",
        "load_kw",
        "pv_forecast_kw",
    }
    if set(data.columns) != required:
        raise ValueError(f"Problem 1 data columns must be exactly {sorted(required)}.")
    if len(data) != 144:
        raise ValueError(f"Problem 1 requires 144 periods, got {len(data)}.")
    if not (0 < storage_efficiency <= 1):
        raise ValueError("storage_efficiency must be in (0, 1].")
    if not (0 <= storage_min_kwh <= initial_storage_kwh <= storage_max_kwh):
        raise ValueError("Initial storage must lie within valid storage bounds.")
    if max_power_kw <= 0 or step_hours <= 0:
        raise ValueError("Power and time-step parameters must be positive.")

    price = data["price_yuan_per_kwh"].to_numpy(dtype=float)
    load_energy = data["load_kw"].to_numpy(dtype=float) * step_hours
    pv_energy = data["pv_forecast_kw"].to_numpy(dtype=float) * step_hours
    if not np.isfinite(np.concatenate([price, load_energy, pv_energy])).all():
        raise ValueError("Problem 1 data contains non-finite values.")
    if (price < 0).any() or (load_energy < 0).any() or (pv_energy < 0).any():
        raise ValueError("Problem 1 inputs must be nonnegative.")

    periods = len(data)
    grid = slice(0, periods)
    charge = slice(periods, 2 * periods)
    discharge = slice(2 * periods, 3 * periods)
    curtailment = slice(3 * periods, 4 * periods)
    storage = slice(4 * periods, 5 * periods + 1)
    variable_count = 5 * periods + 1

    equality_rows = 2 * periods + 2
    a_eq = np.zeros((equality_rows, variable_count), dtype=float)
    b_eq = np.zeros(equality_rows, dtype=float)

    for t in range(periods):
        # grid + PV + discharge = load + charge + curtailment
        a_eq[t, grid.start + t] = 1.0
        a_eq[t, charge.start + t] = -1.0
        a_eq[t, discharge.start + t] = 1.0
        a_eq[t, curtailment.start + t] = -1.0
        b_eq[t] = load_energy[t] - pv_energy[t]

        row = periods + t
        # E[t+1] = E[t] + eta*charge - discharge/eta
        a_eq[row, charge.start + t] = -storage_efficiency
        a_eq[row, discharge.start + t] = 1.0 / storage_efficiency
        a_eq[row, storage.start + t] = -1.0
        a_eq[row, storage.start + t + 1] = 1.0

    a_eq[2 * periods, storage.start] = 1.0
    b_eq[2 * periods] = initial_storage_kwh
    a_eq[2 * periods + 1, storage.stop - 1] = 1.0
    b_eq[2 * periods + 1] = initial_storage_kwh

    max_interval_energy = max_power_kw * step_hours
    bounds = (
        [(0.0, None)] * periods
        + [(0.0, max_interval_energy)] * periods
        + [(0.0, max_interval_energy)] * periods
        + [(0.0, None)] * periods
        + [(storage_min_kwh, storage_max_kwh)] * (periods + 1)
    )

    purchase_objective = np.zeros(variable_count, dtype=float)
    purchase_objective[grid] = price
    primary = linprog(
        purchase_objective,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not primary.success:
        raise RuntimeError(f"Problem 1 primary LP failed: {primary.message}")

    cost_tolerance = max(1e-7, abs(float(primary.fun)) * 1e-9)
    throughput_objective = np.zeros(variable_count, dtype=float)
    throughput_objective[charge] = 1.0
    throughput_objective[discharge] = 1.0
    secondary = linprog(
        throughput_objective,
        A_ub=purchase_objective.reshape(1, -1),
        b_ub=np.array([float(primary.fun) + cost_tolerance]),
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not secondary.success:
        raise RuntimeError(f"Problem 1 tie-break LP failed: {secondary.message}")

    vector = secondary.x
    grid_values = vector[grid]
    charge_values = vector[charge]
    discharge_values = vector[discharge]
    curtailment_values = vector[curtailment]
    storage_values = vector[storage]

    balance_residual = (
        grid_values
        + pv_energy
        + discharge_values
        - load_energy
        - charge_values
        - curtailment_values
    )
    storage_residual = (
        storage_values[1:]
        - storage_values[:-1]
        - storage_efficiency * charge_values
        + discharge_values / storage_efficiency
    )

    schedule = data.copy()
    schedule["grid_purchase_kwh"] = grid_values
    schedule["charge_kwh"] = charge_values
    schedule["discharge_kwh"] = discharge_values
    schedule["curtailment_kwh"] = curtailment_values
    schedule["storage_start_kwh"] = storage_values[:-1]
    schedule["storage_end_kwh"] = storage_values[1:]
    schedule["period_purchase_cost_yuan"] = price * grid_values

    metrics = Problem1Metrics(
        solver_status="PASS",
        purchase_cost_yuan=float(np.dot(price, grid_values)),
        purchased_energy_kwh=float(grid_values.sum()),
        charged_energy_kwh=float(charge_values.sum()),
        discharged_energy_kwh=float(discharge_values.sum()),
        curtailed_energy_kwh=float(curtailment_values.sum()),
        initial_storage_kwh=float(storage_values[0]),
        final_storage_kwh=float(storage_values[-1]),
        minimum_storage_kwh=float(storage_values.min()),
        maximum_storage_kwh=float(storage_values.max()),
        max_balance_residual_kwh=float(np.max(np.abs(balance_residual))),
        max_storage_residual_kwh=float(np.max(np.abs(storage_residual))),
        simultaneous_charge_discharge_kwh=float(
            np.minimum(charge_values, discharge_values).sum()
        ),
    )
    return schedule, metrics


def main() -> None:
    _, metrics = solve_problem1()
    print(json.dumps(asdict(metrics), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
