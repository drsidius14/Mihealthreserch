#!/usr/bin/env python3
import pathlib, re, sys
src = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
needles = ('isPrivilegedPackage', 'DefaultBinderPoolWrapper', 'queryBinder', 'class Validator', 'Validator;')
files = list(src.rglob('*.smali'))
hits=[]
for p in files:
    try: lines=p.read_text(errors='replace').splitlines()
    except OSError: continue
    matching=[i for i,s in enumerate(lines) if any(n in s for n in needles)]
    if not matching: continue
    hits.append(f'FILE {p.relative_to(src)}')
    selected=set()
    for i in matching:
        lo=max(0,i-35); hi=min(len(lines),i+100)
        selected.update(range(lo,hi))
    last=-2
    for i in sorted(selected):
        if i>last+1: hits.append('...')
        hits.append(f'{i+1:6}: {lines[i]}'); last=i
    hits.append('')
(out/'validator-context.txt').write_text('\n'.join(hits) if hits else 'No target method names found in decoded smali. Inspect all DEX strings and update target signatures.\n')
(out/'smali-file-count.txt').write_text(f'smali_files={len(files)}\nmatched_files={sum(1 for p in files if any(n in p.read_text(errors="replace") for n in needles))}\n')
