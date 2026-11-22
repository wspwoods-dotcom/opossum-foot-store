#!/usr/bin/env python3
"""Assemble the store bundle: copy the shippable web app into native/www.
Run before `npx cap sync`. The beta tree and the store tree's sources stay
put; only the pruned copy ships inside the wrapper."""
import shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
WWW = ROOT / 'native' / 'www'
INCLUDE_FILES = ['index.html', 'manifest.json', 'sw.js']
INCLUDE_DIRS = ['css', 'js', 'vendor', 'assets']
EXCLUDE_PARTS = {('assets', 'icons', 'drafts')}
if WWW.exists():
    shutil.rmtree(WWW)
WWW.mkdir(parents=True)
total = 0
for f in INCLUDE_FILES:
    shutil.copy2(ROOT / f, WWW / f); total += (WWW / f).stat().st_size
for d in INCLUDE_DIRS:
    for src in sorted((ROOT / d).rglob('*')):
        rel = src.relative_to(ROOT)
        if any(rel.parts[:len(e)] == e for e in EXCLUDE_PARTS):
            continue
        dst = WWW / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst); total += dst.stat().st_size
print('www assembled: %.1f MB' % (total / 1e6))
