#!/usr/bin/env python3
"""Report hard-coded CJK DEX literals without changing executable code."""
import json
import re
import sys
import zipfile
from pathlib import Path
from v12_forensic import dex_strings

CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')

def main(apk, out):
    with zipfile.ZipFile(apk, 'r') as z:
        bad = z.testzip()
        if bad:
            raise SystemExit('DEX_CJK_AUDIT_BAD_ZIP:' + bad)
        dex = z.read('classes.dex')
    values = sorted(set(s for s in dex_strings(dex) if CJK.search(s)))
    rows = [{'text': s, 'length': len(s)} for s in values]
    Path(out).write_text(json.dumps({
        'source_apk': Path(apk).name,
        'unique_cjk_dex_literals': len(rows),
        'note': 'Report only. DEX literals are not translated or patched without a verified code-reference/call-site analysis.',
        'strings': rows,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V12_HARDCODED_CJK_DEX_LITERALS=' + str(len(rows)))
    print('V12_DEX_CJK_AUDIT_MODE=REPORT_ONLY_NO_CODE_PATCH')
    print('V12_DEX_CJK_AUDIT=' + out)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: v12_dex_cjk_audit.py source.apk report.json')
    main(sys.argv[1], sys.argv[2])
