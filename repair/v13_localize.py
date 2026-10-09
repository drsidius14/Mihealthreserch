#!/usr/bin/env python3
"""Add reviewed Russian overlays by resource key; never mutate base strings or code."""
import json, re, sys, xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path

CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
# Android's legacy locale qualifier uses a two-letter ISO 639-1 language code;
# BCP-47 locale qualifiers use the explicit `b+...` form. Do not classify 3-letter
# UI-mode/resource qualifiers such as `car` as languages.
LANGUAGE_SEGMENT_RE = re.compile(r'^(?:[a-z]{2}|b\+[A-Za-z0-9+]+)$')
# Java Formatter conversions used by Android string resources. Date/time uses a
# two-character t/T + suffix conversion; invalid printf-looking prose is ignored.
FORMAT_SPEC_RE = re.compile(
    r'%(?P<arg>\d+\$)?(?P<flags>[-+# 0,(<]*)?(?P<width>\d+)?'
    r'(?:\.(?P<precision>\d+))?'
    r'(?:(?P<date>[tT])(?P<dateconv>[HIklMSLNpzZsQBbhAaCYyjmdeRTrDFc])'
    r'|(?P<conv>[bBhHsScCdoxXeEfgGaAn%]))'
)
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
    """Return a locale language code for any Android language qualifier.

    Do not limit this to a short allow-list: APKs can contain valid Android
    resource locales such as Tibetan (bo) and Uyghur (ug), even when the app
    has no reviewed translations for those languages. Otherwise the locale
    segment is mistaken for an unrelated qualifier and can leak into the new
    values-ru-* directory name (for example, values-ru-bo-rCN, rejected by
    aapt2).
    """
    if not LANGUAGE_SEGMENT_RE.fullmatch(part):
        return None
    if part.startswith("b+"):
        bits = part.split("+")
        if len(bits) > 1 and re.fullmatch(r"[A-Za-z]{2}", bits[1]):
            return bits[1].lower()
        return None
    return part

def target_values_dir(dirname):
    """Route source locale resources to valid Russian-qualified values directories.

    Android requires MCC/MNC qualifiers before locale qualifiers. When converting
    e.g. values-mcc460-zh-rCN-sw600dp, keep the MCC first and insert `ru` after it;
    blindly prefixing `values-ru-` would create an invalid qualifier order.
    """
    if dirname == 'values':
        return 'values-ru'
    if not dirname.startswith('values-'):
        return None
    parts = dirname[len('values-'):].split('-')
    language_indexes = [i for i,p in enumerate(parts) if language_for_part(p)]
    if any(language_for_part(parts[i]) == 'ru' for i in language_indexes):
        return None  # Existing Russian resources are merge targets, never source data.

    # MCC/MNC may legally precede the language qualifier and must remain before it.
    prefix = []
    prefix_indexes = set()
    for i, part in enumerate(parts):
        if re.fullmatch(r'(?:mcc\d{3}|mnc\d{2,3})', part):
            if i == len(prefix_indexes):
                prefix.append(part)
                prefix_indexes.add(i)
                continue
        break

    if not language_indexes:
        # A region (rUS/rCN/...) is only meaningful after a language qualifier.
        if any(re.fullmatch(r'r[A-Z]{2}', p) for p in parts):
            raise RuntimeError('INVALID_REGION_QUALIFIER_WITHOUT_LANGUAGE:' + dirname)

    remove = set(language_indexes)
    for i,p in enumerate(parts):
        if re.fullmatch(r'r[A-Z]{2}', p) and any(j < i for j in language_indexes):
            remove.add(i)
    suffix = [p for i,p in enumerate(parts) if i not in remove and i not in prefix_indexes]
    routed = prefix + ['ru'] + suffix
    return 'values-' + '-'.join(routed)

def source_priority(dirname):
    if dirname == 'values':
        return (0, dirname)
    parts = dirname[len('values-'):].split('-') if dirname.startswith('values-') else []
    has_language = any(language_for_part(p) for p in parts)
    return (1 if has_language else 0, dirname)

def tag_name(elem):
    return elem.tag.rsplit('}', 1)[-1] if isinstance(elem.tag, str) else ''

def resource_key(elem):
    tag = tag_name(elem)
    if tag == 'item' and elem.attrib.get('type') == 'string': tag = 'string'
    name = elem.attrib.get('name')
    return (tag, name) if name else None

def all_text(elem):
    return ''.join(elem.itertext())

def _valid_formatter_match(match):
    """Reject flag/conversion combinations not accepted by Java Formatter.

    In particular, `% s` is not a valid Java Formatter string conversion: the
    space flag is numeric-only. Also avoid interpreting ordinary text such as
    `% increase` as a format marker simply because the next word starts with an
    ASCII letter. Date/time placeholders retain the complete `%tY`-style token.
    """
    flags = match.group('flags') or ''
    conv = match.group('conv')
    if match.group('date'):
        return all(flag in '-<' for flag in flags)
    if conv in 'sSbBhHcC':
        return all(flag in '-<' for flag in flags)
    if conv == '%':
        return not match.group('arg') and all(flag == '-' for flag in flags) and not match.group('precision')
    if conv == 'n':
        return not match.group('arg') and not flags and not match.group('width') and not match.group('precision')
    return True

def placeholder_signature(elem):
    bits = [all_text(elem)]
    for node in elem.iter():
        bits.extend(node.attrib.values())
    text = ' '.join(bits)
    return Counter(match.group(0) for match in FORMAT_SPEC_RE.finditer(text) if _valid_formatter_match(match))

def set_first_text_leaf(elem, value):
    # Keep every XML tag and attribute (especially href targets), placing the
    # translated visible label in the first textual slot inside the link.
    children = [child for child in list(elem) if isinstance(child.tag, str)]
    if children:
        set_first_text_leaf(children[0], value)
    else:
        elem.text = value

def replace_rich(elem, name, translated):
    spec = RICH_SEGMENTS.get(name)
    anchors = [n for n in elem.iter() if n is not elem and
               (('href' in n.attrib) or tag_name(n) == 'a')]
    # Apktool 3 encodes Android's compiled HTML-bearing string payload as a
    # single <Data> child containing escaped HTML. This must be handled before
    # the live-anchor path below: the <a> tags are text, not XML elements.
    children = [child for child in list(elem) if isinstance(child.tag, str)]
    if len(children) == 1 and tag_name(children[0]) == 'Data' and not anchors:
        elem.text = None
        children[0].text = translated
        children[0].tail = None
        return True
    if not spec:
        if len(list(elem)) == 0:
            elem.text = translated
            return True
        # Apktool 3 represents HTML-bearing Android strings as a single <Data>
        # child whose text contains escaped HTML. Keep that node and every
        # attribute intact, and replace only its text payload. Do not mistake
        # the encoded <a href=...> markup for live XML child elements.
        children = [child for child in list(elem) if isinstance(child.tag, str)]
        if len(children) == 1 and tag_name(children[0]) == 'Data':
            data = children[0]
            elem.text = None
            data.text = translated
            data.tail = None
            return True
        # For simple emphasis-only resources retain existing wrappers.
        if not anchors:
            allowed_inline = {'b','i','u','tt','small','big','sup','sub','strike','s','em','strong'}
            element_nodes = [node for node in elem.iter() if node is elem or tag_name(node)]
            if all(node is elem or tag_name(node) in allowed_inline for node in element_nodes):
                children = [node for node in list(elem) if isinstance(node.tag, str)]
                if not children:
                    elem.text = translated
                else:
                    elem.text = None
                    set_first_text_leaf(children[0], translated)
                    # Empty later wrappers rather than retaining old-language text.
                    first_branch = set(children[0].iter())
                    for node in elem.iter():
                        if node is elem or node in first_branch:
                            continue
                        if isinstance(node.tag, str): node.text = None
                        node.tail = None
                return True
        return False

    if not anchors:
        # Escaped HTML-link strings are text nodes; writing the reviewed whole
        # string preserves the markup and its printf placeholders verbatim.
        if len(list(elem)) == 0:
            elem.text = translated
            return True
        return False
    if len(anchors) != len(spec['anchors']):
        return False
    # Nested links are invalid/ambiguous for the reviewed segment map.
    anchor_ids = {id(node) for node in anchors}
    for i, node in enumerate(anchors):
        descendants = {id(d) for d in node.iter() if d is not node}
        if descendants & (anchor_ids - {id(node)}):
            return False

    # Clear source-language text, but preserve the complete XML tree and all
    # attributes. Then put reviewed text around the existing link nodes. This
    # supports harmless styling/annotation wrappers around links without
    # dropping href values or leaving Chinese sibling text behind.
    for node in elem.iter():
        if node is elem:
            continue
        # Comments are non-rendering XML nodes too; clear their text so they
        # cannot contaminate visible-text audits or leak source-language text.
        node.text = None
        node.tail = None
    elem.text = spec['lead']
    tails = spec['tails']
    for i, (node, label) in enumerate(zip(anchors, spec['anchors'])):
        set_first_text_leaf(node, label)
        if isinstance(tails, str):
            node.tail = tails if i == len(anchors) - 1 else ''
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
        raise SystemExit('V13_TRANSLATION_MAP_EMPTY')
    for name, val in translations.items():
        if not isinstance(name, str) or not isinstance(val, str) or not val:
            raise SystemExit('V13_TRANSLATION_MAP_INVALID_ENTRY:' + repr(name))

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
    nontranslatable_critical_overrides = []
    critical_source_shapes = {key: [] for key in CRITICAL}
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
                if name in CRITICAL:
                    critical_source_shapes.setdefault(name, []).append({
                        'file': str(xml_path.relative_to(root)),
                        'translatable': elem.attrib.get('translatable', 'true'),
                        'root_tag': tag_name(elem),
                        'child_tags': [tag_name(child) or '#comment' for child in list(elem)],
                        'href_values': [node.attrib.get('href') for node in elem.iter() if isinstance(node.tag, str) and 'href' in node.attrib],
                        'source_has_cjk': chinese_present(all_text(elem))
                    })
                dedup_key = (target_dir, name)
                if dedup_key in seen_by_target_dir:
                    continue
                if elem.attrib.get('translatable', 'true').lower() == 'false':
                    if name in CRITICAL:
                        # This XML attribute excludes a value from translator tooling;
                        # it does not prevent Android runtime resource-qualifier lookup.
                        # The reviewed RU overlay must still translate mandatory consent UI.
                        nontranslatable_critical_overrides.append({
                            'key': name, 'file': str(xml_path.relative_to(root)),
                            'reason': 'mandatory_ru_overlay_for_translatable_false_source'
                        })
                    else:
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
        failure_audit = {
            'mode': 'resource-keyed-reviewed-Russian-overlay-v13-failed-closed',
            'translation_map_keys': len(translations),
            'keys_written': sorted(written_names),
            'critical_keys_written': sorted(CRITICAL & written_names),
            'critical_keys_missing': missing,
            'keys_missing_from_resources': sorted(set(translations) - written_names),
            'skipped_rich_xml': skipped,
            'nontranslatable_critical_overrides': nontranslatable_critical_overrides,
            'critical_source_shapes': critical_source_shapes,
            'base_values_untouched': True,
            'overlay_files_not_written_because_critical_gate_failed': True
        }
        Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audit_path).write_text(json.dumps(failure_audit, ensure_ascii=False, indent=2), encoding='utf-8')
        for row in skipped:
            print('V13_LOCALIZATION_SKIP_DETAIL=' + json.dumps(row, ensure_ascii=False, sort_keys=True))
        for key in missing:
            print('V13_CRITICAL_SOURCE_SHAPE=' + key + ':' + json.dumps(critical_source_shapes.get(key, []), ensure_ascii=False, sort_keys=True))
        print('V13_LOCALIZATION_FAILURE_AUDIT=' + audit_path)
        raise SystemExit('V13_CRITICAL_TRANSLATIONS_MISSING:' + ','.join(missing) + '; diagnostics saved')

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
      'mode':'resource-keyed-reviewed-Russian-overlay-v13',
      'translation_map_keys':len(translations),
      'unique_resource_keys_written':len(used_keys),
      'resource_entries_written':total,
      'overlay_files':len(grouped),
      'keys_written':used_keys,
      'critical_keys_written':sorted(CRITICAL & set(used_keys)),
      'critical_keys_missing':sorted(CRITICAL - set(used_keys)),
      'nontranslatable_critical_overrides':nontranslatable_critical_overrides,
      'critical_source_shapes':critical_source_shapes,
      'keys_missing_from_resources':sorted(set(translations)-written_names),
      'skipped_rich_xml':skipped,
      'translations':audit_rows,
      'base_values_untouched':True,
      'dex_manifest_native_assets_untouched_by_localizer':True
    }
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    Path(audit_path).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V13_TRANSLATION_MODE=RESOURCE_KEYED_REVIEWED_OVERLAY')
    print('V13_BASE_VALUES_NOT_MODIFIED=PASS')
    print('V13_TRANSLATION_MAP_KEYS='+str(len(translations)))
    print('V13_UNIQUE_RESOURCE_KEYS_WRITTEN='+str(len(used_keys)))
    print('V13_RESOURCE_ENTRIES_WRITTEN='+str(total))
    print('V13_OVERLAY_FILES='+str(len(grouped)))
    print('V13_CRITICAL_ONBOARDING_TRANSLATIONS=PASS')
    print('V13_UNTRANSLATED_MAP_KEYS='+str(len(set(translations)-written_names)))
    rich_skips=[x for x in skipped if x['reason']=='unsupported_rich_xml_shape']
    nontrans_skips=[x for x in skipped if x['reason']=='translatable_false']
    placeholder_skips=[x for x in skipped if x['reason']=='placeholder_mismatch']
    print('V13_SKIPPED_UNSUPPORTED_RICH_XML='+str(len(rich_skips)))
    print('V13_SKIPPED_NON_TRANSLATABLE='+str(len(nontrans_skips)))
    print('V13_SKIPPED_PLACEHOLDER_MISMATCH='+str(len(placeholder_skips)))
    for row in placeholder_skips:
        print('V13_PLACEHOLDER_MISMATCH_DETAIL='+json.dumps(row,ensure_ascii=False,sort_keys=True))
    if skipped:
        print('V13_SKIPPED_KEYS='+','.join(x['key'] for x in skipped))
        for row in skipped:
            print('V13_LOCALIZATION_SKIP_DETAIL=' + json.dumps(row, ensure_ascii=False, sort_keys=True))
    print('V13_NONTRANSLATABLE_CRITICAL_OVERRIDES='+str(len(nontranslatable_critical_overrides)))

if __name__ == '__main__':
    if len(sys.argv)!=4: raise SystemExit('usage: v13_localize.py <apktool-decoded-root> <translations.json> <audit.json>')
    main(*sys.argv[1:])
