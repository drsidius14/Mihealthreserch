#!/usr/bin/env python3
"""Restore enum/flags format bits from the original compiled resource table."""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HEADER = re.compile(r'^\s*resource\s+0x[0-9a-fA-F]+\s+([^\s/]+)/([^\s]+)')
VALUE = re.compile(r'^\s{6}\(([^)]*)\)\s+\(attr\) type=(.+?)\s*$')
SPECIAL = {'enum', 'flags'}


def local_parser():
    return ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))


def parse_special_attributes(dump_path):
    result = {}
    current = None
    for line in Path(dump_path).read_text(encoding='utf-8', errors='replace').splitlines():
        h = HEADER.match(line)
        if h:
            current = (h.group(1), h.group(2))
            continue
        if current and current[0] == 'attr':
            value = VALUE.match(line)
            if value:
                config = value.group(1).strip()
                tokens = [part.strip() for part in value.group(2).split('|') if part.strip()]
                if config in ('', 'default') and SPECIAL.intersection(tokens):
                    result[current[1]] = tokens
    return result


def main(decoded_root, dump_path, report_path):
    root = Path(decoded_root)
    desired = parse_special_attributes(dump_path)
    if not desired:
        report = {'original_special_attributes': {}, 'changed': [], 'missing_sources': [], 'result': 'no-special-attributes-found'}
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('V13_ATTRIBUTE_FORMAT_REPAIR=NOT_NEEDED')
        return

    found = {name: [] for name in desired}
    changed = []
    for xml_path in sorted(root.glob('res/values*/*.xml')):
        try:
            tree = ET.parse(xml_path, parser=local_parser())
        except ET.ParseError as exc:
            raise SystemExit(f'V13_ATTRIBUTE_XML_PARSE_ERROR:{xml_path}:{exc}')
        dirty = False
        root_elem = tree.getroot()
        parents = {child: parent for parent in root_elem.iter() for child in list(parent)}
        for elem in root_elem.iter():
            if not isinstance(elem.tag, str) or elem.tag.rsplit('}', 1)[-1] != 'attr':
                continue
            name = elem.attrib.get('name')
            if name not in desired:
                continue
            # Do not rewrite bare references inside <declare-styleable>. Only touch
            # a top-level resource declaration, or a nested declaration that already
            # carries format/range metadata or enum/flag symbols of its own.
            has_symbols = any(isinstance(ch.tag, str) and ch.tag.rsplit('}', 1)[-1] in ('enum', 'flag') for ch in list(elem))
            is_definition = parents.get(elem) is root_elem or 'format' in elem.attrib or 'min' in elem.attrib or 'max' in elem.attrib or has_symbols
            if not is_definition:
                continue
            found[name].append(str(xml_path.relative_to(root)))
            wanted = '|'.join(desired[name])
            old = elem.attrib.get('format')
            if old != wanted:
                elem.set('format', wanted)
                changed.append({'name': name, 'file': str(xml_path.relative_to(root)), 'old_format': old, 'restored_format': wanted})
                dirty = True
        if dirty:
            tree.write(xml_path, encoding='utf-8', xml_declaration=True)

    missing = sorted(name for name, paths in found.items() if not paths)
    report = {
        'original_special_attributes': desired,
        'source_declarations': found,
        'changed': changed,
        'missing_sources': missing,
        'result': 'fail' if missing else 'pass'
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V13_SPECIAL_ATTRS_FROM_ORIGINAL=' + str(len(desired)))
    print('V13_SPECIAL_ATTR_FORMATS_RESTORED=' + str(len(changed)))
    print('V13_SPECIAL_ATTR_SOURCE_DECLARATIONS=' + str(sum(len(paths) for paths in found.values())))
    print('V13_ATTRIBUTE_FORMAT_REPAIR_REPORT=' + str(report_path))
    if missing:
        raise SystemExit('V13_SPECIAL_ATTR_SOURCE_NOT_FOUND:' + ','.join(missing))
    print('V13_ATTRIBUTE_FORMAT_REPAIR=PASS')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('usage: v13_restore_attribute_formats.py <decoded-root> <original-resources.dump> <report.json>')
    main(*sys.argv[1:])
