#!/usr/bin/env python3
"""Require Apktool Smali round-trip to preserve all code except reviewed string constants."""
import json
import re
import sys
from pathlib import Path

from v17_01_smali_strings import decode_smali_literal

CONST_RE = re.compile(r'^(?P<prefix>\s*const-string(?:/jumbo)?\s+[^,]+,\s*)(?P<literal>"(?:\\.|[^"\\])*")(?P<tail>\s*(?:#.*)?)$')


def decode(literal):
    return decode_smali_literal(literal)


def file_map(root: Path):
    return {p.relative_to(root).as_posix(): p for p in root.rglob('*.smali')}


def line_method_contexts(lines):
    """Map line indexes to const-string values in their enclosing method."""
    out = {}
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith('.method '):
            i += 1
            continue
        start = i
        block = []
        while i < len(lines):
            block.append(lines[i])
            if lines[i].lstrip().startswith('.end method'):
                i += 1
                break
            i += 1
        values = set()
        for line in block:
            match = CONST_RE.match(line)
            if match:
                values.add(decode(match.group('literal')))
        for pos in range(start, i):
            out[pos] = values
    return out


def normalize_pair(a: str, b: str, source_to_target: dict[str, str], scopes: dict[str, str], label: str):
    aa, bb = a.splitlines(), b.splitlines()
    contexts = line_method_contexts(aa)
    if len(aa) != len(bb):
        return False, f'{label}:line-count {len(aa)} != {len(bb)}'
    for i, (la, lb) in enumerate(zip(aa, bb), 1):
        if la == lb:
            continue
        ma, mb = CONST_RE.match(la), CONST_RE.match(lb)
        if ma and mb and ma.group('tail') == mb.group('tail'):
            pa = re.sub(r'const-string(?:/jumbo)?', 'const-string', ma.group('prefix'), count=1)
            pb = re.sub(r'const-string(?:/jumbo)?', 'const-string', mb.group('prefix'), count=1)
            va, vb = decode(ma.group('literal')), decode(mb.group('literal'))
            # Dalvik may widen const-string to const-string/jumbo after string
            # pool reindexing. Permit that encoding-only change if the register
            # and value remain equivalent, or the literal is allow-listed.
            scoped_ok = not (va in scopes and va != vb) or scopes[va] in contexts.get(i - 1, set())
            if pa == pb and scoped_ok and (va == vb or source_to_target.get(va) == vb):
                continue
        return False, f'{label}:{i}: unexpected Smali difference: {la!r} != {lb!r}'
    return True, ''


def compare(baseline: Path, rebuilt: Path, map_path: Path, report_path: Path):
    obj=json.loads(map_path.read_text(encoding='utf-8'))
    rows=obj.get('translations', [])
    mapping={r['source']:r['target'] for r in rows}
    scopes={r['source']:r['scope_context'] for r in rows if r.get('scope_context')}
    if not mapping or len(mapping)!=len(rows):
        raise SystemExit('V16_SMALI_COMPARE_MAP_INVALID')
    before=file_map(baseline); after=file_map(rebuilt)
    added=sorted(set(after)-set(before)); removed=sorted(set(before)-set(after))
    report={'baseline_files':len(before),'rebuilt_files':len(after),'added_smali_files':added,'removed_smali_files':removed,'checked_files':0,'allowed_literal_differences':0,'scoped_literal_contexts':scopes,'unexpected_differences':[]}
    if added or removed:
        report['unexpected_differences'].append(f'SMALI_FILE_SET_CHANGED added={added[:10]} removed={removed[:10]}')
    allowed=0
    for name in sorted(set(before)&set(after)):
        a=before[name].read_text(encoding='utf-8'); b=after[name].read_text(encoding='utf-8')
        ok,msg=normalize_pair(a,b,mapping,scopes,name)
        report['checked_files']+=1
        if not ok:
            report['unexpected_differences'].append(msg)
            if len(report['unexpected_differences']) >= 25: break
        else:
            for la,lb in zip(a.splitlines(),b.splitlines()):
                ma,mb=CONST_RE.match(la),CONST_RE.match(lb)
                if ma and mb and ma.group('tail')==mb.group('tail'):
                    pa=re.sub(r'const-string(?:/jumbo)?','const-string',ma.group('prefix'),count=1)
                    pb=re.sub(r'const-string(?:/jumbo)?','const-string',mb.group('prefix'),count=1)
                    try: diff = pa==pb and mapping.get(decode(ma.group('literal'))) == decode(mb.group('literal'))
                    except Exception: diff=False
                    if diff and ma.group('literal') != mb.group('literal'): allowed+=1
    report['allowed_literal_differences']=allowed
    report['status']='PASS' if not report['unexpected_differences'] else 'FAIL'
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V16_SMALI_BASELINE_FILES='+str(len(before)))
    print('V16_SMALI_ROUNDTRIP_FILES='+str(len(after)))
    print('V16_SMALI_ALLOWED_STRING_CHANGES='+str(allowed))
    if report['unexpected_differences']:
        for msg in report['unexpected_differences'][:10]: print('V16_SMALI_DIFFERENCE='+msg)
        raise SystemExit('V16_SMALI_ROUNDTRIP_UNEXPECTED_DIFFERENCES')
    if allowed < len(mapping):
        raise SystemExit(f'V16_SMALI_EXPECTED_TRANSLATIONS_NOT_PROVEN:allowed={allowed} expected>={len(mapping)}')
    print('V16_SMALI_ROUNDTRIP_ONLY_REVIEWED_STRINGS_CHANGED=PASS')


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory(prefix='v16-smali-compare-') as td:
        root=Path(td); a=root/'a'; b=root/'b'; a.mkdir(); b.mkdir()
        (a/'X.smali').write_text(
            '.class X\n'
            '.method public dialog()V\n'
            ' const-string v0, "unique dialog"\n'
            ' const-string v1, "源文"\n'
            ' const-string v2, "unchanged"\n'
            ' return-void\n'
            '.end method\n'
            '.method public other()V\n'
            ' const-string v0, "源文"\n'
            ' return-void\n'
            '.end method\n',encoding='utf-8')
        (b/'X.smali').write_text(
            '.class X\n'
            '.method public dialog()V\n'
            ' const-string v0, "unique dialog"\n'
            ' const-string/jumbo v1, "Перевод"\n'
            ' const-string/jumbo v2, "unchanged"\n'
            ' return-void\n'
            '.end method\n'
            '.method public other()V\n'
            ' const-string v0, "源文"\n'
            ' return-void\n'
            '.end method\n',encoding='utf-8')
        map_obj={'translations':[
            {'source':'源文','target':'Перевод','scope_context':'unique dialog'}
        ]}
        mp=root/'map.json'; mp.write_text(json.dumps(map_obj,ensure_ascii=False),encoding='utf-8')
        compare(a,b,mp,root/'report.json')
        # The exact same replacement in a method without the unique prompt must fail.
        text=(b/'X.smali').read_text(encoding='utf-8')
        text=text.replace(' const-string v0, "源文"\n', ' const-string v0, "Перевод"\n')
        (b/'X.smali').write_text(text,encoding='utf-8')
        try: compare(a,b,mp,root/'report2.json')
        except SystemExit: pass
        else: raise AssertionError('out-of-scope string translation was not rejected')
        # A control-flow edit must also fail even if the visible strings still match.
        (b/'X.smali').write_text(text.replace('return-void','invoke-static {}, Lx;->danger()V'),encoding='utf-8')
        try: compare(a,b,mp,root/'report3.json')
        except SystemExit: pass
        else: raise AssertionError('unexpected instruction change was not rejected')
    print('V16_SMALI_ROUNDTRIP_COMPARE_SELFTEST=PASS')

if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--self-test': self_test()
    elif len(sys.argv)==5: compare(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
    else: raise SystemExit('usage: v13_compare_smali.py <baseline-smali> <rebuilt-smali> <dex-translation-map.json> <report.json> | --self-test')
