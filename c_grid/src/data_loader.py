"""Validated, read-only loaders for the official C-problem workbooks.

Official files are never modified here.  The functions return normalized copies
whose time and date keys can safely be used by the optimization code.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ATTACHMENTS_DIR = (PROJECT_ROOT / "c_grid" / "attachments").resolve()


def _official_workbook(relative_path: str) -> Path:
    """Resolve a fixed workbook path while enforcing the official-data boundary."""

    path = (ATTACHMENTS_DIR / relative_path).resolve(strict=True)
    if not path.is_relative_to(ATTACHMENTS_DIR):
        raise ValueError(f"Workbook escapes the official attachment directory: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"Expected an .xlsx workbook, got: {path.name}")
    return path


def _require_columns(frame: pd.DataFrame, expected: list[str], source: Path) -> None:
    actual = [str(column).strip() for column in frame.columns]
    if actual != expected:
        raise ValueError(
            f"Unexpected columns in {source.name}. Expected {expected}, got {actual}."
        )


def _numeric_block(
    frame: pd.DataFrame, columns: list[str], source: Path, *, nonnegative: bool = True
) -> pd.DataFrame:
    values = frame.loc[:, columns].apply(pd.to_numeric, errors="raise")
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise ValueError(f"Non-finite numeric value found in {source.name}.")
    if nonnegative and (array < 0).any():
        raise ValueError(f"Negative value found in nonnegative fields of {source.name}.")
    return values.astype(float)


def _clock_label(value: object) -> str:
    if isinstance(value, time):
        return f"{value.hour}:{value.minute:02d}"
    text = str(value).strip()
    if text == "0:00+1":
        return text
    pieces = text.split(":")
    if len(pieces) in (2, 3) and all(piece.isdigit() for piece in pieces):
        hour, minute = int(pieces[0]), int(pieces[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour}:{minute:02d}"
    raise ValueError(f"Unsupported clock label: {value!r}")


def _expected_ten_minute_labels() -> list[str]:
    labels: list[str] = []
    for endpoint_minute in range(10, 24 * 60 + 1, 10):
        if endpoint_minute == 24 * 60:
            labels.append("0:00+1")
        else:
            hour, minute = divmod(endpoint_minute, 60)
            labels.append(f"{hour}:{minute:02d}")
    return labels


def load_problem1() -> pd.DataFrame:
    """Load Attachment 1 as 144 ordered ten-minute records.

    The official clock labels are preserved.  Their interpretation as interval
    starts or ends remains deliberately separate from row-order optimization.
    """

    source = _official_workbook("附件1.xlsx")
    frame = pd.read_excel(source, engine="openpyxl")
    expected = ["时间", "电价", "小区负载", "光伏发电预测功率"]
    _require_columns(frame, expected, source)
    if len(frame) != 144:
        raise ValueError(f"Attachment 1 must contain 144 records, got {len(frame)}.")

    labels = [_clock_label(value) for value in frame["时间"]]
    if labels != _expected_ten_minute_labels():
        raise ValueError("Attachment 1 clock labels are not the expected 10-minute grid.")

    numeric = _numeric_block(frame, expected[1:], source)
    normalized = pd.DataFrame(
        {
            "period_index": np.arange(144, dtype=int),
            "source_time_label": labels,
            "price_yuan_per_kwh": numeric["电价"],
            "load_kw": numeric["小区负载"],
            "pv_forecast_kw": numeric["光伏发电预测功率"],
        }
    )
    return normalized


def load_attachment3_forecasts() -> pd.DataFrame:
    """Load Attachment 3 and reconstruct its deliberately blank date cells.

    Each official date labels only the 0:00 issue row.  The following 6:00,
    12:00 and 18:00 rows inherit that date.  Reading from the official workbook
    avoids the derived CSV defect that replaced those blanks with ``28``.
    """

    source = _official_workbook("附件3.xlsx")
    frame = pd.read_excel(source, engine="openpyxl")
    expected = ["日期", "预报时刻"] + [f"预报{i}小时" for i in range(1, 25)]
    _require_columns(frame, expected, source)
    if len(frame) != 365 * 4:
        raise ValueError(
            f"Attachment 3 must contain 1460 forecast records, got {len(frame)}."
        )

    raw_dates = frame["日期"].replace(r"^\s*$", pd.NA, regex=True)
    blank_count = int(raw_dates.isna().sum())
    if blank_count != 365 * 3:
        raise ValueError(
            "Attachment 3 date layout changed: expected 1095 inherited date cells, "
            f"got {blank_count}."
        )
    dates = pd.to_datetime(raw_dates.ffill(), format="%Y-%m-%d", errors="raise")

    issue_labels = [_clock_label(value) for value in frame["预报时刻"]]
    issue_hours = pd.Series(issue_labels).map(
        {"0:00": 0, "6:00": 6, "12:00": 12, "18:00": 18}
    )
    if issue_hours.isna().any():
        raise ValueError("Attachment 3 contains an unsupported forecast issue time.")

    forecast_columns = expected[2:]
    numeric = _numeric_block(frame, forecast_columns, source)
    normalized = pd.DataFrame(
        {
            "date": dates.dt.normalize(),
            "issue_hour": issue_hours.astype(int),
        }
    )
    normalized = pd.concat(
        [
            normalized,
            numeric.rename(
                columns={name: f"horizon_{index}_kw" for index, name in enumerate(forecast_columns, 1)}
            ).reset_index(drop=True),
        ],
        axis=1,
    )

    expected_hours = (0, 6, 12, 18)
    grouped = normalized.groupby("date", sort=True)["issue_hour"].apply(tuple)
    if len(grouped) != 365 or not grouped.map(lambda value: value == expected_hours).all():
        raise ValueError("Attachment 3 must have exactly four ordered forecasts per date.")
    return normalized


def _normalize_daily_wide_profile(
    frame: pd.DataFrame, source: Path, *, value_name: str
) -> pd.DataFrame:
    if frame.shape != (365, 145):
        raise ValueError(
            f"{source.name} profile must have shape (365, 145), got {frame.shape}."
        )
    first_column = str(frame.columns[0]).strip()
    if first_column != "日期\\时间":
        raise ValueError(
            f"Unexpected first column in {source.name}: {first_column!r}."
        )
    labels = [_clock_label(value) for value in frame.columns[1:]]
    if labels != _expected_ten_minute_labels():
        raise ValueError(f"{source.name} is not on the expected 10-minute grid.")

    dates = pd.to_datetime(frame.iloc[:, 0], errors="raise").dt.normalize()
    if dates.nunique() != 365 or dates.duplicated().any():
        raise ValueError(f"{source.name} must contain 365 unique dates.")
    values = frame.iloc[:, 1:].apply(pd.to_numeric, errors="raise").to_numpy(float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{source.name} contains invalid nonnegative profile values.")

    return pd.DataFrame(
        {
            "date": np.repeat(dates.to_numpy(), 144),
            "period_index": np.tile(np.arange(144, dtype=int), 365),
            "source_time_label": np.tile(labels, 365),
            value_name: values.reshape(-1),
        }
    )


def load_attachment2_actual_profiles() -> pd.DataFrame:
    """Load the full-year actual load and PV profiles in normalized long form."""

    source = _official_workbook("附件2.xlsx")
    sheets = pd.read_excel(source, sheet_name=None, engine="openpyxl")
    expected_sheets = {"小区负载", "光伏发电实际功率"}
    if set(sheets) != expected_sheets:
        raise ValueError(
            f"Unexpected Attachment 2 sheets. Expected {expected_sheets}, got {set(sheets)}."
        )
    load = _normalize_daily_wide_profile(
        sheets["小区负载"], source, value_name="load_actual_kw"
    )
    pv = _normalize_daily_wide_profile(
        sheets["光伏发电实际功率"], source, value_name="pv_actual_kw"
    )
    keys = ["date", "period_index", "source_time_label"]
    merged = load.merge(pv, on=keys, how="inner", validate="one_to_one")
    if len(merged) != 365 * 144:
        raise ValueError("Attachment 2 profiles did not align one-to-one.")
    return merged


def load_attachment4_actual_prices() -> pd.DataFrame:
    """Load the full-year realized price profile in normalized long form."""

    source = _official_workbook("附件4.xlsx")
    frame = pd.read_excel(source, sheet_name="Sheet1", engine="openpyxl")
    return _normalize_daily_wide_profile(
        frame, source, value_name="price_actual_yuan_per_kwh"
    )
