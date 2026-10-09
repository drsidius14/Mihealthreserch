#!/usr/bin/env python3
"""Report translation coverage among Chinese string resources in an aapt2 dump.

The parser intentionally accepts resource headers both with and without PUBLIC.
It inspects every value/configuration under each string resource, not just the first.
"""
import json
import re
import sys
from pathlib import Path

HEADER = re.compile(r'^\s*resource\s+0x[0-9a-fA-F]+\s+string/([^\s]+)(?:\s+PUBLIC)?\s*$')
VALUE = re.compile(r'^\s{6}\(([^)]*)\)\s+(.*)$')
QUOTED_VALUE = re.compile(r'^"(.*)"(?:\s+Data:.*)?$')
CJK = re.compile(r'[\u3400-\u9fff]')
DELIBERATELY_UNTRANSLATED = ('chinese_', 'earthly_', 'heavenly_', 'fmt_chinese_date')


def main(dump, audit_path, report_path):
    audit = json.loads(Path(audit_path).read_text(encoding='utf-8'))
    done = set(audit.get('keys_written', []))
    chinese = set()
    cur = None

    for line in Path(dump).read_text(encoding='utf-8', errors='replace').splitlines():
        header = HEADER.match(line)
        if header:
            cur = header.group(1)
            continue
        if cur is None:
            continue
        value_line = VALUE.match(line)
        if not value_line:
            continue
        raw = value_line.group(2).strip()
        parsed = QUOTED_VALUE.match(raw)
        # Ignore non-value lines (e.g. file references); don't count their metadata.
        if parsed and CJK.search(parsed.group(1)):
            chinese.add(cur)

    covered = sorted(chinese & done)
    missed = sorted(chinese - done)
    deliberate = [key for key in missed if key.startswith(DELIBERATELY_UNTRANSLATED)]
    user_visible_candidates = [key for key in missed if key not in deliberate]
    ratio = len(covered) / max(1, len(chinese))
    report = {
        'default_chinese_strings': len(chinese),
        'translated_chinese_keys': len(covered),
        'coverage_ratio': ratio,
        'untranslated_keys': missed,
        'deliberately_untranslated_calendar_keys': deliberate,
        'untranslated_not_calendar': user_visible_candidates,
        'keys_written_total': len(done),
        'skipped_rich_xml': audit.get('skipped_rich_xml', []),
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V13_DEFAULT_CJK_STRING_KEYS=' + str(len(chinese)))
    print('V13_CJK_KEYS_TRANSLATED=' + str(len(covered)))
    print('V13_CJK_TRANSLATION_COVERAGE_PERCENT=' + f'{ratio * 100:.1f}')
    print('V13_UNTRANSLATED_CJK_NON_CALENDAR=' + str(len(user_visible_candidates)))
    print('V13_TRANSLATION_COVERAGE_REPORT=' + str(report_path))
    if ratio < 0.90:
        raise SystemExit('V13_TRANSLATION_COVERAGE_BELOW_90_PERCENT')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('usage: v13_coverage.py aapt2-resources.dump translation-audit.json coverage-report.json')
    main(*sys.argv[1:])
