#!/usr/bin/env python3
"""Create a conservative Russian resource overlay from a reviewed exact-string whitelist.

Never machine-translates strings and never inserts an untranslated Chinese string into values-ru.
Existing Russian resource files are merged, not overwritten.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

ZH_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
URL_RE = re.compile(r'^(?:https?://|ftp://)', re.I)
LOCALE_CODES = {
    'af','am','ar','bg','bn','ca','cs','da','de','el','en','es','fa','fi','fr','he','hi','hr','hu',
    'id','in','it','iw','ja','ko','ms','nb','nl','no','pl','pt','ro','ru','sk','sl','sr','sv','sw',
    'ta','th','tr','uk','ur','vi','zh'
}
LANGUAGE_SEGMENT_RE = re.compile(r'^(?:[a-z]{2,3}|b\+[A-Za-z0-9+]+)$')

# Exact, manually reviewed substitutions only. No fallback machine translation.
OVERRIDES = {
    '小米运动健康': 'Mi Fitness',
    '小米运动健康APP': 'Mi Fitness',
    '小米运动健康 App': 'Mi Fitness',
    '血压': 'артериальное давление',
    '动态血压': 'суточное мониторирование АД',
    '无感血压': 'бесконтактное измерение АД',
    '心率': 'частота пульса',
    '睡眠': 'сон',
    '健康研究': 'исследование здоровья',
    '血压健康研究': 'исследование артериального давления',
    '风险评估问卷': 'Анкета оценки риска',
    '最新结果': 'Последний результат',
    '网络连接失败，请重试': 'Не удалось подключиться к сети, повторите попытку',
    '获取评价列表:开始时间:': 'Получение списка оценок: время начала:',
    '删除失败': 'Не удалось удалить',
    '数据同步失败': 'Не удалось синхронизировать данные',
    'yyyy年MM月dd日': 'dd.MM.yyyy',
    'yyyy年M月': 'MM.yyyy',
    'yyyy年M月d': 'dd.MM.yyyy',
    'yyyy年M月d日': 'dd.MM.yyyy',
    'M月d': 'd.MM',
    'M月d日': 'd.MM',
    'M月d日 HH:mm': 'd.MM HH:mm',
}


def eligible_exact(text, attrs=None):
    if not text or not text.strip() or not ZH_RE.search(text):
        return False
    attrs = attrs or {}
    if attrs.get('translatable', 'true').lower() == 'false':
        return False
    if URL_RE.search(text.strip()) or text.strip().startswith(('@', '?')):
        return False
    return text in OVERRIDES


def locale_qualified(dirname):
    suffix = dirname[len('values'):]
    if not suffix:
        return False
    if not suffix.startswith('-'):
        return False
    parts = suffix[1:].split('-')
    # Do not transform values already scoped to any language, including BCP-47 folders.
    for part in parts:
        if part in LOCALE_CODES or LANGUAGE_SEGMENT_RE.fullmatch(part):
            return True
        if re.fullmatch(r'r[A-Z]{2}', part):
            return True
    return False


def target_values_dir(dirname):
    if locale_qualified(dirname):
        return None
    if dirname == 'values':
        return 'values-ru'
    return 'values-ru' + dirname[len('values'):]


def resource_key(elem):
    tag = elem.tag.split('}')[-1]
    name = elem.attrib.get('name')
    if tag == 'item' and elem.attrib.get('type') == 'string':
        tag = 'string'
    if not name:
        return None
    return (tag, name)


def translate_simple(elem):
    tag = elem.tag.split('}')[-1]
    if tag == 'string':
        if eligible_exact(elem.text, elem.attrib):
            out = deepcopy(elem)
            out.text = OVERRIDES[elem.text]
            return out
        return None
    if tag == 'item' and elem.attrib.get('type') == 'string':
        if eligible_exact(elem.text, elem.attrib):
            out = deepcopy(elem)
            out.text = OVERRIDES[elem.text]
            return out
        return None
    if tag not in ('string-array', 'array', 'plurals'):
        return None

    items = list(elem.findall('item'))
    if not items:
        return None
    replacements = []
    any_translation = False
    for item in items:
        source = item.text or ''
        if ZH_RE.search(source):
            # An array is one resource ID: avoid a RU array containing untranslated Chinese.
            if not eligible_exact(source, item.attrib):
                return None
            replacements.append(OVERRIDES[source])
            any_translation = True
        else:
            replacements.append(source)
    if not any_translation:
        return None
    out = deepcopy(elem)
    for old, new in zip(out.findall('item'), replacements):
        old.text = new
    return out


def merge_write(target_path, additions):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        tree = ET.parse(target_path)
        root = tree.getroot()
        if root.tag.split('}')[-1] != 'resources':
            raise RuntimeError('Unexpected root in existing Russian resource file: ' + str(target_path))
    else:
        root = ET.Element('resources')

    existing = {}
    for elem in list(root):
        key = resource_key(elem)
        if key:
            existing.setdefault(key, []).append(elem)
    for addition in additions:
        key = resource_key(addition)
        if key:
            for prior in existing.get(key, []):
                if prior in list(root):
                    root.remove(prior)
            existing[key] = []
        root.append(addition)
        if key:
            existing[key] = [addition]

    ET.ElementTree(root).write(target_path, encoding='utf-8', xml_declaration=True)


def main(root_path, cache_path):
    root = Path(root_path)
    # Audit contains only translations actually written, not every available override.
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    grouped = {}
    for values_dir in sorted(root.glob('res/values*')):
        if not values_dir.is_dir():
            continue
        target_dir = target_values_dir(values_dir.name)
        if not target_dir:
            continue
        for xml_path in sorted(values_dir.glob('*.xml')):
            try:
                tree = ET.parse(xml_path)
            except ET.ParseError as exc:
                raise RuntimeError(f'Cannot parse decoded resource {xml_path}: {exc}') from exc
            new_items = []
            for elem in list(tree.getroot()):
                translated = translate_simple(elem)
                if translated is not None:
                    new_items.append(translated)
            if new_items:
                target_path = root / 'res' / target_dir / xml_path.name
                grouped.setdefault(target_path, []).extend(new_items)

    if not grouped:
        raise SystemExit('SAFE_RUSSIAN_OVERLAY_EMPTY: no exact reviewed resource strings were found')
    total = 0
    audit_rows = []
    for target, elements in sorted(grouped.items(), key=lambda item: str(item[0])):
        merge_write(target, elements)
        total += len(elements)
        for elem in elements:
            audit_rows.append({
                'file': str(target.relative_to(root)),
                'resource': resource_key(elem),
                'value': elem.text if elem.text is not None else ''
            })

    if total == 0:
        raise SystemExit('SAFE_RUSSIAN_OVERLAY_EMPTY: nothing was written')
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump({
            'mode': 'exact-reviewed-overrides-only',
            'machine_translation': False,
            'overrides_written': total,
            'resources': audit_rows
        }, f, ensure_ascii=False, indent=2)
    print('V10.6_TRANSLATION_MODE=EXACT_REVIEWED_OVERRIDES_ONLY')
    print('V10.6_NO_MACHINE_TRANSLATION=PASS')
    print('V10.6_RU_OVERLAY_FILES=' + str(len(grouped)))
    print('V10.6_RU_OVERLAY_RESOURCES=' + str(total))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: v10_6_localize.py <apktool-decoded-root> <translation-audit.json>')
    main(*sys.argv[1:])
