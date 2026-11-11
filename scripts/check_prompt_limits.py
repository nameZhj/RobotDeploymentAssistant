#!/usr/bin/env python3
from pathlib import Path
import argparse
p = argparse.ArgumentParser(description='Check prompt line limits.')
p.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
p.add_argument('--max-lines', type=int, default=180)
a = p.parse_args()
files = sorted((Path(a.root).resolve()/'prompts').glob('*.md'))
if not files:
    raise SystemExit('No prompt files found.')
failed = False
for f in files:
    n = len(f.read_text(encoding='utf-8').splitlines())
    ok = n <= a.max_lines
    print(f"[{'PASS' if ok else 'FAIL'}] {n:3d}/{a.max_lines} {f.name}")
    failed |= not ok
print(f'Checked {len(files)} prompts.')
raise SystemExit(1 if failed else 0)
