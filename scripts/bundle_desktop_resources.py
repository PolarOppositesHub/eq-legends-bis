#!/usr/bin/env python3
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'desktop' / 'resources'
LEGENDS = Path(os.environ.get('EQ_LEGENDS_ROOT') or (ROOT.parent / 'eq-legends'))
DECODED = ROOT / 'data' / 'decoded'
if not (DECODED / 'catalog.json').exists():
    DECODED = LEGENDS / 'decoded'

def main():
    print('==> Bundling into', RES)
    (RES / 'data' / 'decoded').mkdir(parents=True, exist_ok=True)
    (RES / 'frontend').mkdir(parents=True, exist_ok=True)
    (RES / 'eq-legends').mkdir(parents=True, exist_ok=True)
    (RES / 'eq-api').mkdir(parents=True, exist_ok=True)
    print('  JSON from', DECODED)
    for src in DECODED.glob('*.json'):
        shutil.copy2(src, RES / 'data' / 'decoded' / src.name)
    races = ROOT / 'data' / 'races.json'
    if races.exists():
        shutil.copy2(races, RES / 'data' / 'races.json')
    help_md = ROOT / 'data' / 'HELP_BUTTON.md'
    if not help_md.exists():
        help_md = ROOT / 'frontend' / 'public' / 'HELP_BUTTON.md'
    if help_md.exists():
        shutil.copy2(help_md, RES / 'data' / 'HELP_BUTTON.md')
    # Zone research (prefer copy of symlink target for portable Windows packs)
    zr = ROOT / 'data' / 'zone-research'
    if not (zr / 'zones_index.json').exists():
        zr = LEGENDS / 'zone-research'
    if (zr / 'zones_index.json').exists():
        dst_zr = RES / 'data' / 'zone-research'
        if dst_zr.exists():
            shutil.rmtree(dst_zr)
        shutil.copytree(zr, dst_zr, ignore=lambda d, names: {n for n in names if n.startswith('.') or n.startswith('_batch')})
        print('  zone-research ->', dst_zr)
    # Seed item icons so packaged installs show BiS pictures without first-run wiki fetches.
    icons_src = ROOT / 'data' / 'item-images'
    if icons_src.is_dir() and any(icons_src.glob('*.png')):
        icons_dst = RES / 'data' / 'item-images'
        if icons_dst.exists():
            shutil.rmtree(icons_dst)
        shutil.copytree(icons_src, icons_dst)
        print('  item-images ->', icons_dst, f'({sum(1 for _ in icons_dst.glob("*.png"))} png)')
    lr = ROOT / 'data' / 'log-research'
    if not lr.exists():
        lr = LEGENDS / 'log-research'
    if lr.exists() and (lr / 'HELP_BUTTON.md').exists():
        dst_lr = RES / 'data' / 'log-research'
        if dst_lr.exists():
            shutil.rmtree(dst_lr)
        # only ship help + patterns samples needed for docs (keep small)
        dst_lr.mkdir(parents=True, exist_ok=True)
        for name in ('HELP_BUTTON.md', 'patterns.md', 'commands.md', 'REPORT.md'):
            src = lr / name
            if src.exists():
                shutil.copy2(src, dst_lr / name)
        samp = lr / 'samples'
        if samp.exists():
            shutil.copytree(samp, dst_lr / 'samples', dirs_exist_ok=True)
        print('  log-research (subset) ->', dst_lr)
    dist = ROOT / 'frontend' / 'dist'
    if not dist.exists():
        print('ERROR: frontend/dist missing; build UI first')
        return 1
    shutil.copytree(dist, RES / 'frontend' / 'dist', dirs_exist_ok=True)
    vendor = ROOT / 'backend' / 'vendor'
    for name in ('build_planner.py', 'build_xlsx.py', 'decode_local.py', 'item-urls.txt'):
        src = LEGENDS / name
        if not src.exists() and (vendor / name).exists():
            src = vendor / name
        if src.exists():
            shutil.copy2(src, RES / 'eq-legends' / name)
    backend_dst = RES / 'backend'
    if backend_dst.exists():
        shutil.rmtree(backend_dst)
    def _ignore(_dir, names):
        skip = set()
        for n in names:
            if n == '__pycache__' or n.endswith('.pyc'):
                skip.add(n)
        return skip
    shutil.copytree(ROOT / 'backend', backend_dst, ignore=_ignore)
    (RES / 'eq-api' / 'README.txt').write_text(
        'Place eq-api.exe here (from build-windows.ps1)\n', encoding='utf-8')
    print('Done.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
