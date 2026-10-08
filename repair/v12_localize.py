#!/usr/bin/env python3
"""Add reviewed Russian overlays by resource key; never mutate base strings or code."""
import json, re, sys, xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path

CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
LOCALE_CODES = {
    'af','am','ar','bg','bn','ca','cs','da','de','el','en','es','fa','fi','fr','he','hi','hr','hu',
    'id','in','it','iw','ja','ko','ms','nb','nl','no','pl','pt','ro','ru','sk','sl','sr','sv','sw',
    'ta','th','tr','uk','ur','vi','zh'
}
LANGUAGE_SEGMENT_RE = re.compile(r'^(?:[a-z]{2,3}|b\+[A-Za-z0-9+]+)$')
PLACEHOLDER_RE = re.compile(r'%(?:\d+\$)?[-+# 0,(]*\d*(?:\.\d+)?[a-zA-Z%]')
CRITICAL = {
    'app_name','onboarding_app_name','onboarding_welcome_use','onboarding_slogan',
    'onboarding_agree','onboarding_disagree_and_continue','onboarding_exit_app',
    'onboarding_please_read','onboarding_join_experience_program','onboarding_privacy_tips_2'
}
RICH_SEGMENTS = {
    'onboarding_join_experience_program': {
        'lead': 'Присоединитесь к ',
        'anchors': ['программе улучшения пользовательского опыта'],
        'tails': [' и предоставьте больше данных, чтобы улучшать продукты и услуги.']
    },
    'onboarding_privacy_tips_2': {
        'lead': ' ',
        'anchors': [
            'Пользовательское соглашение Xiaomi Health Research',
            'политика конфиденциальности Xiaomi Health Research',
            'краткое изложение политики конфиденциальности'
        ],
        'tails': [', ', ' и ', '']
    },
    'onboarding_privacy_tips_xieyi': {
        'lead': ' ', 'anchors': ['Пользовательское соглашение Xiaomi Health Research'], 'tails': ['']
    },
    'onboarding_privacy_tips_yinsi': {
        'lead': ' ', 'anchors': ['Политика конфиденциальности Xiaomi Health Research'], 'tails': ['']
    },
    'onboarding_privacy_tips_zhaiyao': {
        'lead': ' ', 'anchors': ['Краткое изложение политики конфиденциальности'], 'tails': ['']
    },
    'onboarding_read_and_agree_privacy': {
        'lead': 'Прочитайте ', 'anchors': ['политику конфиденциальности'],
        'tails': ', чтобы узнать о ваших правах и обработке данных.'
    },
    'blood_pressure_guidance_text': {
        'lead': 'Для более точных рекомендаций измеряйте давление каждые полчаса во время бодрствования. Измерений выполнено: %1$d. Продолжайте измерять давление регулярно. ',
        'anchors': ['Инструкция по измерению'], 'tails': ''
    },
    'blood_pressure_no_data_guidance_text': {
        'lead': 'Во время бодрствования приложение напоминает измерять давление, а во время сна устройство автоматически измеряет его через заданные интервалы. Так фиксируются изменения давления за 24 часа. ',
        'anchors': ['Инструкция по измерению'], 'tails': ''
    },
    'mine_about_case_number': {
        'lead': 'Регистрационный номер: ',
        'anchors': ['京ICP备10046444-161A'], 'tails': ['']
    },
    'privacy_sensitive_notify_msg': {
        'lead': 'Внимательно прочитайте ',
        'anchors': ['уведомление о сборе и обработке чувствительной персональной информации'],
        'tails': [', чтобы узнать, как собираются и обрабатываются данные. При отказе соответствующие функции будут недоступны.']
    },
    'eco_device_scale_bind_account_fail_tip': {
        'lead': 'Не удалось добавить устройство: привязка к аккаунту не выполнена. ',
        'anchors': ['Подробнее'], 'tails': ['']
    },
    'eco_device_scale_bind_auth_fail_tip': {
        'lead': 'Не удалось добавить устройство: стандартная авторизация не выполнена. ',
        'anchors': ['Подробнее'], 'tails': ['']
    },
    'eco_device_scale_bind_connect_fail_tip': {
        'lead': 'Не удалось добавить устройство: телефон не подключился к нему. ',
        'anchors': ['Подробнее'], 'tails': ['']
    }
}

def local_xml_parser():
    return ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))

def chinese_present(text):
    return bool(CJK_RE.search(text or ''))

def language_for_part(part):
    if part in LOCALE_CODES:
        return part
    if part.startswith("b+"):
        bits = part.split("+")
        if len(bits) > 1 and bits[1] in LOCALE_CODES:
            return bits[1]
    return None

def target_values_dir(dirname):
    """Route base and non-Russian locale resources into equivalent values-ru qualifiers."""
    if dirname == 'values':
        return 'values-ru'
    if not dirname.startswith('values-'):
        return None
    parts = dirname[len('values-'):].split('-')
    language_indexes = [i for i,p in enumerate(parts) if language_for_part(p)]
    if any(language_for_part(parts[i]) == 'ru' for i in language_indexes):
        return None  # Existing Russian resources are merge targets, never source data.
    if not language_indexes:
        return 'values-ru-' + '-'.join(parts)
    remove = set(language_indexes)
    for i,p in enumerate(parts):
        if re.fullmatch(r'r[A-Z]{2}', p) and any(j < i for j in language_indexes):
            remove.add(i)
    kept = [p for i,p in enumerate(parts) if i not in remove]
    return 'values-ru' + (('-' + '-'.join(kept)) if kept else '')

def source_priority(dirname):
    if dirname == 'values':
        return (0, dirname)
    parts = dirname[len('values-'):].split('-') if dirname.startswith('values-') else []
    has_language = any(language_for_part(p) for p in parts)
    return (1 if has_language else 0, dirname)

def resource_key(elem):
    tag = elem.tag.split('}')[-1]
    if tag == 'item' and elem.attrib.get('type') == 'string': tag = 'string'
    name = elem.attrib.get('name')
    return (tag, name) if name else None

def all_text(elem):
    return ''.join(elem.itertext())

def placeholder_signature(elem):
    bits = [all_text(elem)]
    for node in elem.iter():
        bits.extend(node.attrib.values())
    return Counter(PLACEHOLDER_RE.findall(' '.join(bits)))

def replace_rich(elem, name, translated):
    spec = RICH_SEGMENTS.get(name)
    anchors = [n for n in elem.iter() if n is not elem and ('href' in n.attrib or n.tag.split('}')[-1] == 'a')]
    if not spec:
        if len(list(elem)) == 0:
            elem.text = translated
            return True
        # Some Android strings use inline formatting tags (for example <b>)
        # rather than clickable links. Keep the first formatting wrapper and
        # put the complete translation inside it, preserving styling without
        # relying on Chinese character offsets. Clickable/link strings are never
        # flattened by this branch.
        if not anchors:
            allowed_inline = {'b', 'i', 'u', 'tt', 'small', 'big', 'sup', 'sub', 'strike', 's', 'em', 'strong'}
            if all(node is elem or node.tag.split('}')[-1] in allowed_inline for node in elem.iter()):
                children = list(elem)
                if not children:
                    elem.text = translated
                else:
                    first = children[0]
                    first.text = translated
                    for nested in list(first):
                        first.remove(nested)
                    first.tail = None
                    for child in children[1:]:
                        elem.remove(child)
                    elem.text = None
                return True
        return False
    if not anchors:
        if len(list(elem)) == 0:
            elem.text = translated
            return True
        return False
    if len(anchors) != len(spec['anchors']):
        raise RuntimeError(f'Unexpected rich-text anchor count for {name}: {len(anchors)}')
    # Unknown sibling/formatting elements can alter visual styling; fail closed.
    known = set(anchors)
    other = [n for n in list(elem) if n not in known]
    if other:
        return False
    elem.text = spec['lead']
    tails = spec['tails']
    for i, node in enumerate(anchors):
        node.text = spec['anchors'][i]
        if isinstance(tails, str):
            node.tail = tails if i == len(anchors)-1 else ''
        else:
            node.tail = tails[i]
    return True

def merge_write(path, additions):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        tree = ET.parse(path, parser=local_xml_parser())
        root = tree.getroot()
        if root.tag.split('}')[-1] != 'resources':
            raise RuntimeError('Unexpected root in existing Russian resources: ' + str(path))
    else:
        root = ET.Element('resources')
    existing = {}
    for elem in list(root):
        k = resource_key(elem)
        if k: existing.setdefault(k, []).append(elem)
    for elem in additions:
        k = resource_key(elem)
        if k:
            for prior in existing.get(k, []):
                if prior in list(root): root.remove(prior)
        root.append(elem)
        if k: existing[k] = [elem]
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)

def main(root_path, translations_path, audit_path):
    root = Path(root_path)
    translations = json.loads(Path(translations_path).read_text(encoding='utf-8'))
    if not isinstance(translations, dict) or not translations:
        raise SystemExit('V12_TRANSLATION_MAP_EMPTY')
    for name, val in translations.items():
        if not isinstance(name, str) or not isinstance(val, str) or not val:
            raise SystemExit('V12_TRANSLATION_MAP_INVALID_ENTRY:' + repr(name))

    # Read base resources first, then localized source folders only for keys absent
    # from the base. This covers resources supplied solely in values-zh-rCN.
    source_dirs = []
    for values_dir in root.glob('res/values*'):
        if not values_dir.is_dir():
            continue
        target_dir = target_values_dir(values_dir.name)
        if target_dir:
            source_dirs.append((source_priority(values_dir.name), values_dir, target_dir))
    source_dirs.sort(key=lambda row: (row[0], row[1].name))

    grouped = {}
    seen_by_target_dir = set()
    skipped = []
    for _, values_dir, target_dir in source_dirs:
        for xml_path in sorted(values_dir.glob('*.xml')):
            try:
                tree = ET.parse(xml_path, parser=local_xml_parser())
            except ET.ParseError as exc:
                raise RuntimeError(f'XML parse error {xml_path}: {exc}') from exc
            for elem in list(tree.getroot()):
                k = resource_key(elem)
                if not k or k[0] != 'string' or k[1] not in translations:
                    continue
                name = k[1]
                dedup_key = (target_dir, name)
                if dedup_key in seen_by_target_dir:
                    continue
                if elem.attrib.get('translatable', 'true').lower() == 'false':
                    skipped.append({'key':name,'file':str(xml_path.relative_to(root)),'reason':'translatable_false'})
                    continue
                original_ph = placeholder_signature(elem)
                new = deepcopy(elem)
                if not replace_rich(new, name, translations[name]):
                    skipped.append({'key':name,'file':str(xml_path.relative_to(root)),'reason':'unsupported_rich_xml_shape'})
                    continue
                translated_ph = placeholder_signature(new)
                if translated_ph != original_ph:
                    # A bad translation must not abort the entire build or damage
                    # a formatted UI string. Skip only this resource and preserve
                    # the exact original implementation for it. The full mismatch
                    # is recorded in the audit for review.
                    skipped.append({
                        'key': name,
                        'file': str(xml_path.relative_to(root)),
                        'reason': 'placeholder_mismatch',
                        'source_placeholders': dict(original_ph),
                        'translation_placeholders': dict(translated_ph)
                    })
                    continue
                for a,b in zip(elem.iter(),new.iter()):
                    if a.attrib != b.attrib:
                        raise RuntimeError(f'ATTRIBUTE_CHANGED:{name}')
                target_path = root / 'res' / target_dir / xml_path.name
                grouped.setdefault(target_path, {})[name] = new
                seen_by_target_dir.add(dedup_key)

    written_names = {name for _,name in seen_by_target_dir}
    missing = sorted(CRITICAL - written_names)
    if missing:
        raise SystemExit('V12_CRITICAL_TRANSLATIONS_MISSING_FROM_BASE_OR_LOCALE_RESOURCES:' + ','.join(missing))

    # Remove existing Russian definitions for overridden keys across every XML in the
    # target locale folder, so the new key-based value cannot create duplicate resources.
    keys_per_dir = {}
    for target_path, additions in grouped.items():
        keys_per_dir.setdefault(target_path.parent, set()).update(additions)
    for target_dir_path, names in keys_per_dir.items():
        if not target_dir_path.exists():
            continue
        for existing_path in sorted(target_dir_path.glob('*.xml')):
            try:
                tree = ET.parse(existing_path, parser=local_xml_parser())
            except ET.ParseError as exc:
                raise RuntimeError(f'Existing RU XML parse error {existing_path}: {exc}') from exc
            rt = tree.getroot()
            changed = False
            for elem in list(rt):
                k = resource_key(elem)
                if k and k[0] == 'string' and k[1] in names:
                    rt.remove(elem); changed = True
            if changed:
                if len(rt) == 0:
                    existing_path.unlink()
                else:
                    tree.write(existing_path, encoding='utf-8', xml_declaration=True)

    total = 0
    audit_rows = []
    for target_path, by_name in sorted(grouped.items(), key=lambda x: str(x[0])):
        additions = list(by_name.values())
        merge_write(target_path, additions)
        for elem in additions:
            k = resource_key(elem); total += 1
            audit_rows.append({'file':str(target_path.relative_to(root)), 'resource':k, 'value':all_text(elem)})
    used_keys = sorted(written_names)
    audit = {
      'mode':'resource-keyed-reviewed-Russian-overlay-v12',
      'translation_map_keys':len(translations),
      'unique_resource_keys_written':len(used_keys),
      'resource_entries_written':total,
      'overlay_files':len(grouped),
      'keys_written':used_keys,
      'critical_keys_written':sorted(CRITICAL),
      'keys_missing_from_resources':sorted(set(translations)-written_names),
      'skipped_rich_xml':skipped,
      'translations':audit_rows,
      'base_values_untouched':True,
      'dex_manifest_native_assets_untouched_by_localizer':True
    }
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    Path(audit_path).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V12_TRANSLATION_MODE=RESOURCE_KEYED_REVIEWED_OVERLAY')
    print('V12_BASE_VALUES_NOT_MODIFIED=PASS')
    print('V12_TRANSLATION_MAP_KEYS='+str(len(translations)))
    print('V12_UNIQUE_RESOURCE_KEYS_WRITTEN='+str(len(used_keys)))
    print('V12_RESOURCE_ENTRIES_WRITTEN='+str(total))
    print('V12_OVERLAY_FILES='+str(len(grouped)))
    print('V12_CRITICAL_ONBOARDING_TRANSLATIONS=PASS')
    print('V12_UNTRANSLATED_MAP_KEYS='+str(len(set(translations)-written_names)))
    rich_skips=[x for x in skipped if x['reason']=='unsupported_rich_xml_shape']
    nontrans_skips=[x for x in skipped if x['reason']=='translatable_false']
    placeholder_skips=[x for x in skipped if x['reason']=='placeholder_mismatch']
    print('V12_SKIPPED_UNSUPPORTED_RICH_XML='+str(len(rich_skips)))
    print('V12_SKIPPED_NON_TRANSLATABLE='+str(len(nontrans_skips)))
    print('V12_SKIPPED_PLACEHOLDER_MISMATCH='+str(len(placeholder_skips)))
    for row in placeholder_skips:
        print('V12_PLACEHOLDER_MISMATCH_DETAIL='+json.dumps(row,ensure_ascii=False,sort_keys=True))
    if skipped:
        print('V12_SKIPPED_KEYS='+','.join(x['key'] for x in skipped))

if __name__ == '__main__':
    if len(sys.argv)!=4: raise SystemExit('usage: v12_localize.py <apktool-decoded-root> <translations.json> <audit.json>')
    main(*sys.argv[1:])
