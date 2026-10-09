#!/usr/bin/env python3
"""Fail closed when localization creates invalid locale-qualified values dirs."""
import json, re, sys
from pathlib import Path
from v13_localize import language_for_part

REGION = re.compile(r'^r[A-Z]{2}$')

def main(root_path, report_path):
    root = Path(root_path)
    res = root / 'res'
    if not res.is_dir():
        raise SystemExit('RU_RESOURCE_DIR_AUDIT_RES_DIR_MISSING:' + str(res))
    checked = []
    bad = []
    for path in sorted(res.glob('values-ru*')):
        if not path.is_dir():
            continue
        checked.append(str(path.relative_to(root)))
        parts = path.name[len('values-'):].split('-')
        if not parts or parts[0] != 'ru':
            continue
        tail = parts[1:]
        # A locale language must occur only in the first qualifier position.
        # The region directly following `ru` is valid (values-ru-rRU); a
        # second language such as `bo` or `ug` is not (values-ru-bo-rCN).
        tail_languages = [part for part in tail if language_for_part(part)]
        if tail_languages:
            bad.append({'directory': path.name, 'reason': 'nested_language_qualifier', 'segments': tail_languages})
        # Reject region-only source remnants only when they follow another
        # non-locale qualifier; a single region after `ru` is valid.
        if len(tail) > 1 and any(REGION.fullmatch(part) for part in tail[1:]) and not tail_languages:
            bad.append({'directory': path.name, 'reason': 'region_qualifier_order_suspicious', 'segments': tail})
    report = {'checked_russian_values_dirs': checked, 'invalid_dirs': bad, 'count_checked': len(checked)}
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if bad:
        for item in bad:
            print('V16_INVALID_RU_RESOURCE_DIR=' + json.dumps(item, ensure_ascii=False, sort_keys=True))
        raise SystemExit('V16_RU_RESOURCE_DIR_VALIDATION=FAIL')
    print('V16_RU_RESOURCE_DIRS_CHECKED=' + str(len(checked)))
    print('V16_RU_RESOURCE_DIR_VALIDATION=PASS')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: v13_validate_ru_resource_dirs.py decoded-root report.json')
    main(sys.argv[1], sys.argv[2])
