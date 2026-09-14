"""Fail closed if tracked files cross the intended public-release boundary."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 5 * 1024 * 1024
FORBIDDEN_TOP_LEVEL = {
    "archive",
    "deliverables",
    "notebooks",
    "outputs",
    "paper",
    "tmp",
}
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".caj",
    ".dll",
    ".doc",
    ".docx",
    ".exe",
    ".gz",
    ".pdf",
    ".rar",
    ".so",
    ".tar",
    ".tgz",
    ".xls",
    ".xlsx",
    ".xz",
    ".zip",
}
TEXT_SUFFIXES = {
    "",
    ".cff",
    ".csv",
    ".json",
    ".md",
    ".py",
    ".sha256",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "aws-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "assigned-secret": re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|secret[_-]?key|password|passwd)"
        r"\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
    ),
    "personal-path": re.compile(
        r"(?i)(/home/" + "yux" + r"uan\b|[A-Z]:\\Users\\" + "yux" + r"ua\b)"
    ),
}


def tracked_files() -> list[Path]:
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
        paths = [Path(value.decode("utf-8")) for value in raw.split(b"\0") if value]
        if paths:
            return paths
        raw = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
        paths = [Path(value.decode("utf-8")) for value in raw.split(b"\0") if value]
        if paths:
            return paths
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def main() -> None:
    violations: list[dict[str, str | int]] = []
    paths = tracked_files()
    for relative in paths:
        path = ROOT / relative
        parts = {part.lower() for part in relative.parts}
        suffix = path.suffix.lower()
        if relative.parts and relative.parts[0].lower() in FORBIDDEN_TOP_LEVEL:
            violations.append({"path": relative.as_posix(), "reason": "forbidden-path"})
        if suffix in FORBIDDEN_SUFFIXES or re.search(r"\.part\d+$", path.name, re.I):
            violations.append({"path": relative.as_posix(), "reason": "forbidden-binary"})
        if any(part in {".env", "credentials", "secrets"} for part in parts):
            violations.append({"path": relative.as_posix(), "reason": "sensitive-name"})
        if path.stat().st_size > MAX_FILE_BYTES:
            violations.append(
                {
                    "path": relative.as_posix(),
                    "reason": "file-too-large",
                    "bytes": path.stat().st_size,
                }
            )
        if suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    violations.append(
                        {"path": relative.as_posix(), "reason": f"content:{name}"}
                    )
    result = {
        "status": "PASS" if not violations else "FAIL",
        "tracked_files": len(paths),
        "tracked_bytes": sum((ROOT / path).stat().st_size for path in paths),
        "violations": violations,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
