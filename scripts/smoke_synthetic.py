"""Run the core optimizer on a tiny synthetic profile."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from c_grid.src.online_dispatch import optimize  # noqa: E402
from c_grid.src.settlement import storage_residual  # noqa: E402


def main() -> None:
    result = optimize(
        [1000.0, -3000.0, 3000.0],
        [0.2, 0.2, 1.0],
        6000.0,
        terminal_value=0.6,
    )
    residual = storage_residual(
        result["soc"], result["charge"], result["discharge"]
    )
    checks = {
        "finite": bool(
            all(np.isfinite(np.asarray(value)).all() for value in result.values())
        ),
        "max_storage_residual_kwh": float(np.max(np.abs(residual))),
        "max_charge_kw": float(np.max(result["charge"])),
        "max_discharge_kw": float(np.max(result["discharge"])),
    }
    if not checks["finite"] or checks["max_storage_residual_kwh"] > 0.01:
        raise RuntimeError(checks)
    print(json.dumps({"status": "PASS", **checks}, indent=2))


if __name__ == "__main__":
    main()
