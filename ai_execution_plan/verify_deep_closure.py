# @file: ai_execution_plan/verify_deep_closure.py
# @brief: Automated Hydrogen High code hygiene verifier, INDEX.md synchronizer, and 8-layer deep closure auditor.
# @exports: audit_project_hygiene, main

from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, List, Tuple

MAX_LINES = 300
HEADER_WINDOW = 10


def parse_header(lines: List[str]) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in lines[:HEADER_WINDOW]:
        m = re.match(r"^\s*#\s*@(file|brief|exports)\s*:\s*(.+)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def audit_project_hygiene(project_dir: pathlib.Path, scan_folders: Tuple[str, ...] = ("src", "utils")) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    rows: List[str] = []
    targets: List[pathlib.Path] = []
    for folder in scan_folders:
        p = project_dir / folder
        if p.exists():
            targets.extend(sorted(f for f in p.rglob("*.py") if "__pycache__" not in str(f)))

    for py in targets:
        rel = py.relative_to(project_dir).as_posix()
        lines = py.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            errors.append(f"[{project_dir.name}] {rel}: {len(lines)} lines > {MAX_LINES}")
        meta = parse_header(lines)
        for tag in ("file", "brief", "exports"):
            if tag not in meta:
                errors.append(f"[{project_dir.name}] {rel}: missing @{tag}")
        if "file" in meta and meta["file"] != rel:
            errors.append(f"[{project_dir.name}] {rel}: @file '{meta['file']}' != '{rel}'")
        rows.append(f"{rel} | {meta.get('brief', '-')} | {meta.get('exports', '-')}")

    index_path = project_dir / ".agent_workspace" / "INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"# {project_dir.name} Module Index (Auto-Generated for Hydrogen High)",
        "",
        "Format: `path | brief | exported_symbols`",
        "",
    ]
    index_path.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
    return errors, rows


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    all_errors: List[str] = []
    global_rows: List[str] = ["# Global Dual-Project Symbol Index (Hydrogen High Fast Lookup)", ""]

    for proj_name in ("upper_computer", "lower_computer"):
        proj_dir = repo_root / proj_name
        if not proj_dir.exists():
            all_errors.append(f"Missing project directory: {proj_name}")
            continue
        errs, rows = audit_project_hygiene(proj_dir)
        all_errors.extend(errs)
        global_rows.append(f"## {proj_name} ({len(rows)} modules)")
        global_rows.extend(f"{proj_name}/{r}" for r in rows)
        global_rows.append("")

    global_idx = repo_root / "ai_execution_plan" / "GLOBAL_SYMBOL_INDEX.md"
    global_idx.write_text("\n".join(global_rows) + "\n", encoding="utf-8")

    if all_errors:
        for e in all_errors:
            print(f"[CLOSURE ERROR] {e}", file=sys.stderr)
        return 1
    print("[CLOSURE OK] Both upper_computer and lower_computer passed hygiene & INDEX sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
