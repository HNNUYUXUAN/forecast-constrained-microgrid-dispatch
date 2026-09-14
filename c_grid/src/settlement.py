"""Independent settlement and storage checks, in kW, kWh and yuan.

The adjustment formula follows the existing notebook convention: cancelled
energy retains a 50% charge, and incremental energy costs 150% of the tariff.
This module does not optimize controls or assume future observations are known.
"""
import numpy as np


def _arrays(*values):
    arrays = [np.asarray(value, dtype=float) for value in values]
    if not arrays or any(a.shape != arrays[0].shape for a in arrays):
        raise ValueError('All interval arrays must have the same shape')
    if any(not np.isfinite(a).all() or (a < 0).any() for a in arrays):
        raise ValueError('Interval values must be finite and nonnegative')
    return arrays


def settle_purchase(price, planned_kw, adjusted_kw, emergency_kw, *, step_hours=1/6):
    """Return interval cost components; retain the original commitment explicitly."""
    if not np.isfinite(step_hours) or step_hours <= 0:
        raise ValueError('step_hours must be finite and positive')
    price, plan, adjusted, emergency = _arrays(price, planned_kw, adjusted_kw, emergency_kw)
    planned_cost = price*plan*step_hours
    incremental_cost = 1.5*price*np.maximum(adjusted-plan,0)*step_hours
    cancellation_credit = .5*price*np.maximum(plan-adjusted,0)*step_hours
    emergency_cost = 5*price*emergency*step_hours
    return {'planned_cost':planned_cost,'incremental_cost':incremental_cost,
            'cancellation_credit':cancellation_credit,'emergency_cost':emergency_cost,
            'total_cost':planned_cost+incremental_cost-cancellation_credit+emergency_cost}


def storage_residual(storage_kwh, charge_kw, discharge_kw, *, efficiency=.9, step_hours=1/6):
    """Return conservation residuals; the last dimension is the time axis."""
    storage = np.asarray(storage_kwh, dtype=float)
    charge, discharge = _arrays(charge_kw, discharge_kw)
    if not 0 < efficiency <= 1 or not np.isfinite(step_hours) or step_hours <= 0:
        raise ValueError('Invalid efficiency or time step')
    if charge.ndim < 1 or storage.shape != (*charge.shape[:-1],charge.shape[-1]+1):
        raise ValueError('SOC must have exactly one more time point than interval controls')
    if not np.isfinite(storage).all():
        raise ValueError('SOC must be finite')
    return np.diff(storage,axis=-1)-efficiency*charge*step_hours+discharge/efficiency*step_hours
