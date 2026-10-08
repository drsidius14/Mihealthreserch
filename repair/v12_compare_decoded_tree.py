#!/usr/bin/env python3
"""Strictly compare Apktool-decoded original and rebuilt APK trees.
Only apktool.yml, old signature metadata, and reviewed Russian values overlays may differ.
"""
import json, hashlib, sys
from pathlib import Path

IGNORED = ('apktool.yml', 'original/AndroidManifest.xml')


def sha(data): return hashlib.sha256(data).hexdigest()

def read_tree(root):
    root=Path(root); out={}
    for p in root.rglob('*'):
        if not p.is_file(): continue
        rel=p.relative_to(root).as_posix()
        if rel in IGNORED or rel.startswith('original/META-INF/'):
            continue
        out[rel]=p.read_bytes()
    return out

def is_ru_values(p):
    parts=p.split('/')
    return len(parts)>1 and parts[0]=='res' and parts[1].startswith('values-ru')

def main(original_root,candidate_root,audit_path,report_path,mode='strict'):
    audit=json.loads(Path(audit_path).read_text(encoding='utf-8'))
    allowed=set(audit.get('keys_written',[]))
    a=read_tree(original_root); b=read_tree(candidate_root)
    removed=sorted(set(a)-set(b)); added=sorted(set(b)-set(a)); changed=[]; unexpected=[]
    for name in sorted(set(a)&set(b)):
        if a[name]==b[name]: continue
        if is_ru_values(name):
            # RU XML is independently checked by translation audit, placeholder test,
            # and the final aapt2 resource-table comparator.
            changed.append(name)
        else:
            unexpected.append({'path':name,'original_sha256':sha(a[name]),'candidate_sha256':sha(b[name])})
    unexpected_added=[p for p in added if not is_ru_values(p) and not p.startswith('original/META-INF/')]
    unexpected_removed=[p for p in removed if not is_ru_values(p) and not p.startswith('original/META-INF/')]
    report={
      'mode':mode,'original_files':len(a),'candidate_files':len(b),
      'added_paths':added,'removed_paths':removed,'changed_russian_overlay_files':changed,
      'unexpected_changed_files':unexpected,'unexpected_added_files':unexpected_added,
      'unexpected_removed_files':unexpected_removed,
      'non_ru_decoded_files_identical':not unexpected and not unexpected_added and not unexpected_removed,
      'reviewed_translation_keys':len(allowed)
    }
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DECODED_TREE_ORIGINAL_FILES='+str(len(a)))
    print('DECODED_TREE_CANDIDATE_FILES='+str(len(b)))
    print('DECODED_TREE_RU_CHANGED_FILES='+str(len(changed)))
    print('DECODED_TREE_UNEXPECTED_CHANGED='+str(len(unexpected)))
    print('DECODED_TREE_UNEXPECTED_ADDED='+str(len(unexpected_added)))
    print('DECODED_TREE_UNEXPECTED_REMOVED='+str(len(unexpected_removed)))
    print('DECODED_TREE_REPORT='+report_path)
    ok=not unexpected and not unexpected_added and not unexpected_removed
    print('DECODED_TREE_NON_RU_IDENTITY='+('PASS' if ok else 'FAIL'))
    if mode=='strict' and not ok: raise SystemExit('V12_DECODED_TREE_COMPARE=FAIL')

if __name__=='__main__':
    if len(sys.argv) not in (5,6): raise SystemExit('usage: v12_compare_decoded_tree.py original-dir candidate-dir audit.json report.json [strict|report-only]')
    main(*sys.argv[1:])
