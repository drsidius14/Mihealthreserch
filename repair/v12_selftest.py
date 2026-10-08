#!/usr/bin/env python3
import json, re, tempfile, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v12_compare_resource_tables import normalize_value

def main():
    translations=json.loads((Path(__file__).with_name('v12_translations.json')).read_text(encoding='utf-8'))
    v=translations['hospital_bloodpressure_abnormal_from_device']
    assert '%1s' in v and 'Источник:' in v
    assert normalize_value('(file) res/aB.webp') == normalize_value('(file) res/drawable-xxhdpi/about_img.webp')
    assert normalize_value('(attr) type=any') == normalize_value('(attr) type=reference|string|integer|boolean|color|float|dimension|fraction')
    assert normalize_value('(attr) type=reference|enum') != normalize_value('(attr) type=reference')
    # Ensure the localizer no longer has a fail-fast placeholder mismatch raise.
    code=Path(__file__).with_name('v12_localize.py').read_text(encoding='utf-8')
    assert 'PLACEHOLDER_MISMATCH:{name}' not in code
    assert "'reason': 'placeholder_mismatch'" in code
    print('V12_TRANSLATION_PLACEHOLDER_FIX=PASS')
    print('V12_RESOURCE_PATH_NORMALIZATION=PASS')
    print('V12_ANY_ATTR_NORMALIZATION=PASS')
    print('V12_ENUM_METADATA_DIFF_NOT_IGNORED=PASS')
    print('V12_FAIL_SAFE_PLACEHOLDER_AUDIT=PASS')
if __name__=='__main__': main()
