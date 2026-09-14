"""Validate local Markdown links and machine-readable repository metadata."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main() -> None:
    errors: list[str] = []

    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    if project.get("license") != "MIT":
        errors.append("pyproject.toml license is not MIT")

    for path in ROOT.rglob("*.json"):
        if ".git" in path.parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"invalid JSON: {path.relative_to(ROOT)}: {error}")

    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, re.I):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(
                    f"broken link: {path.relative_to(ROOT)} -> {target}"
                )

    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    for required in ("cff-version:", "title:", "authors:", "license: MIT"):
        if required not in cff:
            errors.append(f"CITATION.cff missing {required}")

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(
        json.dumps(
            {"status": "PASS", "json_files": len(list(ROOT.rglob("*.json")))},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

