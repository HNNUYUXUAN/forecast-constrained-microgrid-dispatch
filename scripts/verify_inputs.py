"""Verify locally supplied official inputs without modifying them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "INPUTS.sha256"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def expected_files() -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for line_number, raw in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            expected, relative = line.split(maxsplit=1)
        except ValueError as error:
            raise ValueError(f"Malformed manifest line {line_number}: {raw!r}") from error
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise ValueError(f"Invalid SHA-256 on manifest line {line_number}.")
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT / "c_grid" / "attachments"):
            raise ValueError(f"Input escapes c_grid/attachments: {relative}")
        rows.append((expected, path))
    return rows


def main() -> None:
    missing: list[str] = []
    mismatched: list[str] = []
    checked: list[str] = []
    for expected, path in expected_files():
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            missing.append(relative)
            continue
        actual = digest(path)
        if actual != expected:
            mismatched.append(relative)
        else:
            checked.append(relative)
    result = {
        "status": "PASS" if not missing and not mismatched else "FAIL",
        "checked": checked,
        "missing": missing,
        "mismatched": mismatched,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

