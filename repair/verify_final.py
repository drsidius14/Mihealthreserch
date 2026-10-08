#!/usr/bin/env python3
import hashlib, os, struct, sys, zipfile, zlib
sys.path.insert(0, os.path.dirname(__file__))
from repair_v8 import parse_dex, dex_integrity_ok, validate_order, TARGET, EXPECTED_NEW_INDEX

apk = sys.argv[1]
with zipfile.ZipFile(apk, 'r') as z:
    if z.testzip() is not None:
        raise SystemExit('APK_ZIP=FAIL')
    dex_names = sorted(n for n in z.namelist() if n.endswith('.dex'))
    if 'classes.dex' not in dex_names:
        raise SystemExit('classes.dex missing')
    for name in dex_names:
        d = z.read(name)
        if not dex_integrity_ok(d):
            raise SystemExit(f'{name}_INTEGRITY=FAIL')
        strings = validate_order(d)
        if name == 'classes.dex':
            if strings[EXPECTED_NEW_INDEX] != TARGET:
                raise SystemExit('TARGET_INDEX=FAIL')
            if strings.count(TARGET) != 1:
                raise SystemExit('TARGET_COUNT=FAIL')
            if 'Lcom/mi/research/SearchApplication;' not in strings:
                raise SystemExit('SearchApplication string missing')
    print('FINAL_DEX_VERIFY=PASS')
    print('DEX_FILES=' + ','.join(dex_names))
print('FINAL_APK_SHA256=' + hashlib.sha256(open(apk,'rb').read()).hexdigest())
