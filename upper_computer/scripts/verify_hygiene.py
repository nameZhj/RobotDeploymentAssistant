# @file: scripts/verify_hygiene.py
# @brief: Automated code hygiene checker (<=300 lines/file, @file/@brief/@exports headers) and INDEX.md generator.
# @exports: audit_directory, update_index, main

from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, List, Tuple

MAX_LINES = 300
HEADER_WINDOW = 10
FORBIDDEN_ROOT_DIRS = ("runtime", "cache", "installer")


def parse_file_header(lines: List[str]) -> Dict[str, str]:
    """Extract @file, @brief, and @exports tags from the top comment block."""
    meta: Dict[str, str] = {}
    for line in lines[:HEADER_WINDOW]:
        match = re.match(r"^\s*#\s*@(file|brief|exports)\s*:\s*(.+)$", line)
        if match:
            meta[match.group(1)] = match.group(2).strip()
    return meta


def audit_directory(root_dir: pathlib.Path) -> Tuple[List[str], List[str]]:
    """Audit Python files under src/ and utils/; return (errors, index_rows)."""
    errors: List[str] = []
    index_rows: List[str] = []

    for forbidden in FORBIDDEN_ROOT_DIRS:
        if (root_dir / forbidden).exists():
            errors.append(f"Forbidden root directory present: {forbidden}/")

    targets: List[pathlib.Path] = []
    for folder_name in ("src", "utils"):
        folder = root_dir / folder_name
        if folder.exists():
            targets.extend(sorted(p for p in folder.rglob("*.py") if "__pycache__" not in str(p)))

    for py_file in targets:
        rel_path = py_file.relative_to(root_dir).as_posix()
        lines = py_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            errors.append(f"{rel_path}: {len(lines)} lines exceeds limit {MAX_LINES}")

        meta = parse_file_header(lines)
        for tag in ("file", "brief", "exports"):
            if tag not in meta:
                errors.append(f"{rel_path}: missing header tag @{tag}")
        if "file" in meta and meta["file"] != rel_path:
            errors.append(f"{rel_path}: @file '{meta['file']}' does not match path")

        brief = meta.get("brief", "-")
        exports = meta.get("exports", "-")
        index_rows.append(f"{rel_path} | {brief} | {exports}")

    return errors, index_rows


def update_index(root_dir: pathlib.Path, index_rows: List[str]) -> pathlib.Path:
    """Write the synchronized module index to .agent_workspace/INDEX.md."""
    index_path = root_dir / ".agent_workspace" / "INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Workspace Module Index (Auto-Generated)",
        "",
        "Format: `path | brief | exported_symbols`",
        "",
    ]
    content = "\n".join(header + index_rows) + "\n"
    index_path.write_text(content, encoding="utf-8")
    return index_path


def main() -> int:
    root_dir = pathlib.Path(__file__).resolve().parents[1]
    errors, rows = audit_directory(root_dir)
    update_index(root_dir, rows)
    if errors:
        for err in errors:
            print(f"[HYGIENE ERROR] {err}", file=sys.stderr)
        return 1
    print(f"[HYGIENE OK] Audited {len(rows)} files; INDEX.md updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
