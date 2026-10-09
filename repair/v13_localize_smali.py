#!/usr/bin/env python3
"""Translate an exact allow-list of user-visible const-string literals in Smali.

No opcodes, registers, method descriptors, resource IDs, branches, or attributes are edited.
The script fails closed if any reviewed source literal is missing or remains untranslated.
"""
import json
import re
import sys
from pathlib import Path

from v17_01_smali_strings import decode_smali_literal, encode_smali_literal

CONST_RE = re.compile(r'^(?P<prefix>\s*const-string(?:/jumbo)?\s+[^,]+,\s*)(?P<literal>"(?:\\.|[^"\\])*")(?P<tail>\s*(?:#.*)?)$')


def _line_method_contexts(lines):
    """Map each line index to all const-string literals in its enclosing method."""
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
        literals = set()
        for line in block:
            m = CONST_RE.match(line.rstrip('\r\n'))
            if m:
                literals.add(decode_smali_literal(m.group('literal')))
        for pos in range(start, i):
            out[pos] = literals
    return out


def localize(root: Path, map_path: Path, audit_path: Path) -> dict:
    payload = json.loads(map_path.read_text(encoding='utf-8'))
    rows = payload.get('translations')
    if payload.get('schema') != 1 or not isinstance(rows, list) or not rows:
        raise SystemExit('V16_DEX_TRANSLATION_MAP_INVALID')
    mapping = {}
    scope_contexts = {}
    for row in rows:
        source, target = row.get('source'), row.get('target')
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise SystemExit('V16_DEX_TRANSLATION_MAP_ENTRY_INVALID')
        if source == target or source in mapping:
            raise SystemExit('V16_DEX_TRANSLATION_MAP_DUPLICATE_OR_NOOP:' + source)
        mapping[source] = target
        scope_context = row.get('scope_context')
        if scope_context is not None:
            if not isinstance(scope_context, str) or not scope_context:
                raise SystemExit('V16_DEX_TRANSLATION_SCOPE_INVALID:' + source)
            scope_contexts[source] = scope_context

    smali_files = sorted(root.rglob('*.smali'))
    if not smali_files:
        raise SystemExit('V16_DEX_NO_SMALI_FILES:' + str(root))
    counts = {source: 0 for source in mapping}
    changed_files = []
    for path in smali_files:
        original = path.read_text(encoding='utf-8')
        lines = original.splitlines(keepends=True)
        contexts = _line_method_contexts(lines)
        new_lines = []
        changed = False
        for lineno, line in enumerate(lines, 1):
            logical = line.rstrip('\r\n')
            ending = line[len(logical):]
            match = CONST_RE.match(logical)
            if match:
                value = decode_smali_literal(match.group('literal'))
                if value in mapping:
                    required_context = scope_contexts.get(value)
                    if required_context and required_context not in contexts.get(lineno - 1, set()):
                        new_lines.append(line)
                        continue
                    target = mapping[value]
                    new_lines.append(match.group('prefix') + encode_smali_literal(target) + match.group('tail') + ending)
                    counts[value] += 1
                    changed = True
                    continue
            new_lines.append(line)
        if changed:
            path.write_text(''.join(new_lines), encoding='utf-8', newline='')
            changed_files.append(str(path.relative_to(root)))

    missing = [s for s, count in counts.items() if count == 0]
    if missing:
        report = {
            'mode': 'exact-smali-const-string-only',
            'root': str(root),
            'translation_count': len(mapping),
            'source_occurrences': counts,
            'missing_source_literals': missing,
            'changed_files': changed_files,
            'status': 'FAIL'
        }
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        raise SystemExit('V16_DEX_TRANSLATION_SOURCE_LITERAL_MISSING:' + repr(missing))

    # Independent second pass: no allow-listed source literal may remain in a const-string.
    remaining = {source: 0 for source in mapping}
    remaining_in_scope = {source: 0 for source in scope_contexts}
    target_counts = {target: 0 for target in mapping.values()}
    for path in sorted(root.rglob('*.smali')):
        lines = path.read_text(encoding='utf-8').splitlines()
        contexts = _line_method_contexts(lines)
        for lineno, line in enumerate(lines, 1):
            match = CONST_RE.match(line)
            if not match:
                continue
            value = decode_smali_literal(match.group('literal'))
            if value in remaining:
                required_context = scope_contexts.get(value)
                if not required_context:
                    remaining[value] += 1
                elif required_context in contexts.get(lineno - 1, set()):
                    remaining_in_scope[value] += 1
            if value in target_counts:
                target_counts[value] += 1
    if any(remaining.values()) or any(remaining_in_scope.values()) or any(target_counts[t] < counts[s] for s, t in mapping.items()):
        raise SystemExit('V16_DEX_TRANSLATION_POSTCHECK_FAILED')

    report = {
        'mode': 'exact-smali-const-string-only',
        'source_smali_files': len(smali_files),
        'translation_count': len(mapping),
        'source_occurrences': counts,
        'target_occurrences': target_counts,
        'remaining_source_occurrences': remaining,
        'remaining_scoped_source_occurrences': remaining_in_scope,
        'scoped_translations': scope_contexts,
        'changed_files': changed_files,
        'changed_file_count': len(changed_files),
        'control_flow_or_identifiers_modified': False,
        'status': 'PASS'
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for source, target in mapping.items():
        print('V16_DEX_STRING_TRANSLATED=' + json.dumps({'source': source, 'target': target, 'occurrences': counts[source]}, ensure_ascii=False))
    print('V16_DEX_TRANSLATION_FILES=' + str(len(changed_files)))
    print('V16_DEX_TRANSLATION_POSTCHECK=PASS')
    return report


def self_test() -> None:
    import tempfile
    from pathlib import Path
    map_obj = {
        'schema': 1,
        'translations': [
            {'source': '原文一', 'target': 'Перевод один'},
            {'source': '他说“打开”', 'target': 'Он сказал «Открыть»'},
            {'source': '第二行', 'target': 'Вторая строка'},
            {'source': '取消', 'target': 'Отмена', 'scope_context': 'уникальный диалог'}
        ]
    }
    with tempfile.TemporaryDirectory(prefix='v16-smali-selftest-') as td:
        base = Path(td)
        smali = base / 'smali'; smali.mkdir()
        (smali / 'Example.smali').write_text(
            '.class public LExample;\n'
            '.method public test()V\n'
            '    .locals 1\n'
            '    const-string v0, "原文一"\n'
            '    const-string v0, "他说\\u201c打开\\u201d"\n'
            '    const-string v0, "第二行"\n'
            '    const-string v0, "UNRELATED"\n'
            '    const-string v0, "уникальный диалог"\n'
            '    const-string v0, "取消"\n'
            '    return-void\n'
            '.end method\n'
            '.method public unrelated()V\n'
            '    .locals 1\n'
            '    const-string v0, "取消"\n'
            '    return-void\n'
            '.end method\n', encoding='utf-8')
        mp, ap = base/'map.json', base/'audit.json'
        mp.write_text(json.dumps(map_obj, ensure_ascii=False), encoding='utf-8')
        result = localize(smali, mp, ap)
        final = (smali/'Example.smali').read_text(encoding='utf-8')
        assert result['status'] == 'PASS'
        # V17.01 canonically escapes non-ASCII characters as \uXXXX; compare decoded
        # string values, not raw UTF-8 appearance in a Smali source file.
        decoded_values = [
            decode_smali_literal(match.group('literal'))
            for line in final.splitlines()
            if (match := CONST_RE.match(line))
        ]
        assert 'Перевод один' in decoded_values and 'Вторая строка' in decoded_values and 'UNRELATED' in decoded_values
        assert 'Он сказал «Открыть»' in decoded_values and 'Отмена' in decoded_values
        assert decoded_values.count('取消') == 1, 'short common labels must change only in scoped dialog method'
        assert result['remaining_scoped_source_occurrences']['取消'] == 0
        # Opcodes/register count and all non-target lines remain untouched.
        assert final.count('const-string') == 7 and 'return-void' in final
    print('V16_SMALI_LOCALIZER_SELFTEST=PASS')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--self-test':
        self_test()
    elif len(sys.argv) == 4:
        localize(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit('usage: v13_localize_smali.py <smali-dir> <translations.json> <audit.json> | --self-test')
