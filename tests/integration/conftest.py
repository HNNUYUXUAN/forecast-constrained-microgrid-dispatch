from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = Path(__file__).resolve().parent
REQUIRED_INPUTS = (
    ROOT / "c_grid" / "attachments" / "附件1.xlsx",
    ROOT / "c_grid" / "attachments" / "附件2.xlsx",
    ROOT / "c_grid" / "attachments" / "附件3.xlsx",
    ROOT / "c_grid" / "attachments" / "附件4.xlsx",
    ROOT / "c_grid" / "attachments" / "附件5" / "result1.xlsx",
    ROOT / "c_grid" / "attachments" / "附件5" / "result2.xlsx",
    ROOT / "c_grid" / "attachments" / "附件5" / "result3.xlsx",
    ROOT / "c_grid" / "attachments" / "附件5" / "result4-2.xlsx",
    ROOT / "c_grid" / "attachments" / "附件5" / "result4-3.xlsx",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if all(path.is_file() for path in REQUIRED_INPUTS):
        return
    marker = pytest.mark.skip(
        reason="official C-problem inputs are absent; run scripts/verify_inputs.py"
    )
    for item in items:
        if Path(str(item.path)).resolve().is_relative_to(INTEGRATION_DIR):
            item.add_marker(marker)
