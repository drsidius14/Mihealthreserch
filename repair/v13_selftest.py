#!/usr/bin/env python3
"""Offline regression tests for V13 localization and resource semantics."""
import json, re, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v13_compare_resource_tables import normalize_value
from v13_restore_attribute_formats import main as restore_attribute_formats
from v13_localize import target_values_dir, language_for_part, placeholder_signature, replace_rich, all_text

CRITICAL = {
 'app_name':'Исследование здоровья Xiaomi',
 'onboarding_app_name':'Исследование здоровья Xiaomi',
 'onboarding_welcome_use':'Добро пожаловать',
 'onboarding_slogan':'Наслаждайтесь здоровой жизнью',
 'onboarding_agree':'Согласен',
 'onboarding_disagree_and_continue':'Не соглашаться и перейти в базовый режим',
 'onboarding_exit_app':'Выйти из приложения',
 'onboarding_please_read':'Прочитайте и примите условия',
 'onboarding_join_experience_program':'Присоединитесь к',
 'onboarding_privacy_tips_2':'Пользовательское соглашение Xiaomi Health Research',
}

def main():
    translations=json.loads((Path(__file__).with_name('v13_translations.json')).read_text(encoding='utf-8'))
    # Android locale routing must recognize valid ISO language tags beyond the short allow-list.
    assert language_for_part('bo') == 'bo'
    assert language_for_part('ug') == 'ug'
    assert language_for_part('b+bo+CN') == 'bo'
    assert target_values_dir('values-bo-rCN') == 'values-ru'
    assert target_values_dir('values-ug-rCN') == 'values-ru'
    assert target_values_dir('values-zh-rCN') == 'values-ru'
    assert target_values_dir('values-b+bo+CN') == 'values-ru'
    assert target_values_dir('values-night') == 'values-ru-night'
    assert target_values_dir('values-sw600dp-land') == 'values-ru-sw600dp-land'
    # `car` is an Android UI-mode qualifier; do not mistake it for the obscure
    # ISO 639-3 language code and erase a valid configuration dimension.
    assert language_for_part('car') is None
    assert language_for_part('abc') is None
    assert language_for_part('b+bo+CN') == 'bo'
    assert target_values_dir('values-car') == 'values-ru-car'
    assert target_values_dir('values-mcc460-zh-rCN-sw600dp') == 'values-mcc460-ru-sw600dp'
    assert target_values_dir('values-mcc310-night') == 'values-mcc310-ru-night'
    assert target_values_dir('values-night-car') == 'values-ru-night-car'
    assert target_values_dir('values-ru') is None
    assert target_values_dir('values-ru-rRU') is None
    # `% s` is invalid for Java Formatter string conversions; it must not be treated as a required placeholder.
    fake = ET.fromstring('<string name="format">Рост составил 10% s за неделю</string>')
    assert not placeholder_signature(fake), placeholder_signature(fake)
    valid = ET.fromstring('<string name="format">%1$s — %2$d%%</string>')
    assert placeholder_signature(valid) == {'%1$s': 1, '%2$d': 1, '%%': 1}
    datefmt = ET.fromstring('<string name="format">Year %1$tY</string>')
    assert placeholder_signature(datefmt) == {'%1$tY': 1}
    # Regression from the actual V16 audit: Chinese text survived in a styled
    # string's first child tail after a Russian replacement.
    styled = ET.fromstring('<string name="hospital_sleep_need_opened_tips"><b>中文开头</b>”，点击右上角菜单，开启“</string>')
    replacement = 'Чтобы использовать исследование апноэ сна, включите «Высокоточную регистрацию сна».'
    assert replace_rich(styled, 'hospital_sleep_need_opened_tips', replacement)
    assert all_text(styled) == replacement, all_text(styled)
    assert not re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]', all_text(styled)), all_text(styled)
    prose = ET.fromstring('<string name="format">10% increase; more than 5% is unusual</string>')
    assert not placeholder_signature(prose), placeholder_signature(prose)

    v=translations['hospital_bloodpressure_abnormal_from_device']
    assert '%1s' in v and 'Источник:' in v
    assert normalize_value('(file) res/aB.webp type=drawable') == normalize_value('(file) res/drawable-xxhdpi/about_img.webp type=drawable')
    assert normalize_value('(file) res/aB.webp type=drawable') != normalize_value('(file) res/aB.webp type=raw')
    assert normalize_value('(attr) type=any') == normalize_value('(attr) type=reference|string|integer|boolean|color|float|dimension|fraction')
    assert normalize_value('(attr) type=reference|enum') != normalize_value('(attr) type=reference')

    # Coverage is a diagnostic metric, not an arbitrary 90% release gate.
    # The critical app-owned onboarding keys remain mandatory.
    from v13_coverage import main as coverage_main
    with tempfile.TemporaryDirectory(prefix="v13-coverage-gate-") as td:
        work=Path(td); dump=work/"resources.dump"; audit=work/"audit.json"; report=work/"coverage.json"
        dump.write_text("\n".join([
            "resource 0x7f010001 string/app_name", '      () "小米健康研究"',
            "resource 0x7f010002 string/library_label PUBLIC", '      () "设置"',
        ])+"\n",encoding="utf-8")
        critical={"app_name","onboarding_app_name","onboarding_welcome_use","onboarding_slogan",
                  "onboarding_agree","onboarding_disagree_and_continue","onboarding_exit_app",
                  "onboarding_please_read","onboarding_join_experience_program","onboarding_privacy_tips_2"}
        audit.write_text(json.dumps({"keys_written":sorted(critical)}),encoding="utf-8")
        coverage_main(str(dump),str(audit),str(report))
        coverage=json.loads(report.read_text(encoding="utf-8"))
        assert coverage["default_chinese_strings"] == 2, coverage
        assert coverage["translated_chinese_keys"] == 1, coverage
        assert coverage["coverage_ratio"] < 0.90 and coverage["coverage_gate"] == "diagnostic_only"
        audit.write_text(json.dumps({"keys_written":["app_name"]}),encoding="utf-8")
        try:
            coverage_main(str(dump),str(audit),str(report))
        except SystemExit as exc:
            assert "V16_CRITICAL_RU_UI_KEYS_MISSING" in str(exc)
        else:
            raise AssertionError("missing critical Russian UI keys must fail")
        empty_dump=work/"empty.dump"; empty_dump.write_text("no string entries\n",encoding="utf-8")
        empty_report=work/"empty-coverage.json"
        try:
            coverage_main(str(empty_dump),str(audit),str(empty_report))
        except SystemExit as exc:
            assert "V16_COVERAGE_PARSER_FOUND_ZERO_DEFAULT_CJK_STRINGS" in str(exc)
            assert empty_report.is_file()
            assert json.loads(empty_report.read_text(encoding="utf-8"))["coverage_parser_found_cjk_strings"] is False
        else:
            raise AssertionError("coverage parser must not silently pass an empty input")
    print("V16_COVERAGE_DIAGNOSTIC_AND_CRITICAL_UI_GATE=PASS")

    # Restore enum/flags format masks from the original compiled resource dump,
    # the exact V10.7 regression that the strict table gate must not overlook.
    with tempfile.TemporaryDirectory(prefix='v13-attr-format-') as td:
        work=Path(td); vals=work/'decoded'/'res'/'values'; vals.mkdir(parents=True)
        attrs=vals/'attrs.xml'
        attrs.write_text('<?xml version="1.0"?><resources><attr name="expandState" format="reference" /><declare-styleable name="Example"><attr name="expandState" /></declare-styleable></resources>',encoding='utf-8')
        dump=work/'original.dump'; dump.write_text('resource 0x7f040291 attr/expandState PUBLIC\n      () (attr) type=reference|enum\n',encoding='utf-8')
        report=work/'repair.json'
        restore_attribute_formats(str(work/'decoded'),str(dump),str(report))
        updated_root=ET.parse(attrs).getroot()
        updated=updated_root.find('attr')
        nested_ref=updated_root.find('declare-styleable/attr')
        assert updated is not None and updated.attrib.get('format')=='reference|enum'
        assert nested_ref is not None and 'format' not in nested_ref.attrib, 'bare styleable reference must remain untouched'
        repair=json.loads(report.read_text(encoding='utf-8'))
        assert repair['result']=='pass' and repair['changed']

    # Exercise the actual strict comparator: a renamed path with the same file
    # type may pass, but a changed file type or lost enum metadata must fail.
    with tempfile.TemporaryDirectory(prefix='v13-resource-selftest-') as td:
        work=Path(td)
        base_lines=[
            'resource 0x7f010001 attr/expandState PUBLIC',
            '      () (attr) type=reference|enum',
            'resource 0x7f020001 drawable/photo PUBLIC',
            '      () (file) res/aB.webp type=drawable',
            'resource 0x7f030001 string/example PUBLIC',
            '      () "Source text"',
        ]
        candidate_lines=[
            'resource 0x7f010001 attr/expandState PUBLIC',
            '      () (attr) type=reference|enum',
            'resource 0x7f020001 drawable/photo PUBLIC',
            '      () (file) res/drawable-xxhdpi/photo.webp type=drawable',
            'resource 0x7f030001 string/example PUBLIC',
            '      () "Source text"',
            '      (ru) "Russian text"',
        ]
        base_dump=work/'base.dump'; cand_dump=work/'candidate.dump'
        base_dump.write_text('\n'.join(base_lines)+'\n',encoding='utf-8')
        cand_dump.write_text('\n'.join(candidate_lines)+'\n',encoding='utf-8')
        audit=work/'audit.json'; audit.write_text(json.dumps({'keys_written':['example']}),encoding='utf-8')
        report=work/'report.json'
        cmp_script=Path(__file__).with_name('v13_compare_resource_tables.py')
        ok=subprocess.run([sys.executable,str(cmp_script),str(base_dump),str(cand_dump),str(audit),str(report),'strict'],capture_output=True,text=True)
        assert ok.returncode==0,ok.stdout+ok.stderr
        for broken in ('file-type','enum-loss'):
            bad=list(candidate_lines)
            if broken=='file-type': bad[3]='      () (file) res/drawable-xxhdpi/photo.webp type=raw'
            else: bad[1]='      () (attr) type=reference'
            bad_dump=work/(broken+'.dump'); bad_dump.write_text('\n'.join(bad)+'\n',encoding='utf-8')
            proc=subprocess.run([sys.executable,str(cmp_script),str(base_dump),str(bad_dump),str(audit),str(work/(broken+'.json')),'strict'],capture_output=True,text=True)
            assert proc.returncode!=0,(broken,proc.stdout,proc.stderr)

    # Build a realistic small Android values tree with both live XML links and
    # an optional-translatable=false flag. The two mandatory onboarding strings
    # must still receive an RU overlay, retaining their href placeholders.
    with tempfile.TemporaryDirectory(prefix='v13-selftest-') as td:
        work=Path(td); root=work/'decoded'; values=root/'res'/'values'; values.mkdir(parents=True)
        lines=['<?xml version="1.0" encoding="utf-8"?>','<resources>']
        for name in sorted(CRITICAL):
            if name=='onboarding_join_experience_program':
                val='<string name="%s" translatable="false"> 加入<!-- 注释中的旧文本 --><b><a href="%%1$s">用户体验改进计划</a></b>提供更多数据来帮助改进产品和服务。</string>' % name
            elif name=='onboarding_privacy_tips_2':
                # Apktool 3 decodes the compiled HTML payload into a Data node.
                val='<string name="%s" translatable="false"><Data> &lt;a href=\"%%1$s\"&gt;《小米健康研究用户协议》&lt;/a&gt;、&lt;a href=\"%%2$s\"&gt;《小米健康研究隐私政策》&lt;/a&gt;&lt;a href=\"%%3$s\"&gt;（《隐私政策》摘要）&lt;/a&gt;</Data></string>' % name
            else:
                val='<string name="%s">中文测试</string>' % name
            lines.append(val)
        lines.append('<string name="onboarding_privacy_tips_xieyi"> &lt;a href="%1$s"&gt;《小米健康研究用户协议》&lt;/a&gt;</string>')
        lines.append('<string name="common_am" translatable="false">上午</string>')
        lines.append('<string name="common_pm">%1$s下午</string>')
        lines.append('<string name="sport_run_rate_increase_suggestion">建议跑量增加的上限不超过前一周的10% s</string>')
        lines.append('<string name="hospital_sleep_need_opened_tips"><b>需开启中文说明</b>”，点击右上角菜单，开启“</string>')
        lines.append('</resources>')
        base_xml='\n'.join(lines)+'\n'; source=values/'strings.xml'; source.write_text(base_xml,encoding='utf-8')
        translations['common_pm']='下午'
        translations['bo_only_translation_test']='Русский текст из bo'
        translations['ug_only_translation_test']='Русский текст из ug'
        translations['car_only_translation_test']='Русский текст для режима автомобиля'
        translations['mcc_only_translation_test']='Русский текст для MCC-квалификатора'
        for locale_dir, key, source_text in [
            ('values-bo-rCN','bo_only_translation_test','藏文源文本'),
            ('values-ug-rCN','ug_only_translation_test','维吾尔文源文本'),
            ('values-car','car_only_translation_test','汽车模式资源测试'),
            ('values-mcc460-zh-rCN-sw600dp','mcc_only_translation_test','移动国家码语言资源测试'),
        ]:
            loc = root/'res'/locale_dir; loc.mkdir(parents=True, exist_ok=True)
            (loc/'locale_only.xml').write_text('<resources><string name="'+key+'">'+source_text+'</string></resources>',encoding='utf-8')
        tr=work/'translations.json'; tr.write_text(json.dumps(translations,ensure_ascii=False,indent=2),encoding='utf-8')
        audit=work/'audit.json'
        proc=subprocess.run([sys.executable,str(Path(__file__).with_name('v13_localize.py')),str(root),str(tr),str(audit)],capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError('V13 localizer fixture failed:\n'+proc.stdout+'\n'+proc.stderr)
        data=json.loads(audit.read_text(encoding='utf-8'))
        assert set(CRITICAL)==set(data['critical_keys_written']), data.get('critical_keys_written')
        assert not any(x.get('reason') == 'unsupported_rich_xml_shape' for x in data['skipped_rich_xml']), data['skipped_rich_xml']
        assert not any(x.get('key') == 'sport_run_rate_increase_suggestion' for x in data['skipped_rich_xml']), data['skipped_rich_xml']
        assert 'sport_run_rate_increase_suggestion' in data['keys_written'], data['skipped_rich_xml']
        sleep_tip = next(row for row in data['translations'] if row['resource'][1]=='hospital_sleep_need_opened_tips')
        assert sleep_tip['value'] == translations['hospital_sleep_need_opened_tips'], sleep_tip
        assert not re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]', sleep_tip['value']), sleep_tip
        locale_only = ET.parse(root/'res'/'values-ru'/'locale_only.xml').getroot()
        assert {e.attrib.get('name') for e in locale_only} == {'bo_only_translation_test','ug_only_translation_test'}
        car_locale_only = ET.parse(root/'res'/'values-ru-car'/'locale_only.xml').getroot()
        assert {e.attrib.get('name') for e in car_locale_only} == {'car_only_translation_test'}
        mcc_locale_only = ET.parse(root/'res'/'values-mcc460-ru-sw600dp'/'locale_only.xml').getroot()
        assert {e.attrib.get('name') for e in mcc_locale_only} == {'mcc_only_translation_test'}
        validator = Path(__file__).with_name('v13_validate_ru_resource_dirs.py')
        valid = subprocess.run([sys.executable,str(validator),str(root),str(work/'ru-dirs.json')],capture_output=True,text=True)
        assert valid.returncode==0,valid.stdout+valid.stderr
        # Negative test: the exact failure observed in GitHub must be caught before aapt2.
        invalid_dirs = [root/'res'/'values-ru-bo-rCN', root/'res'/'values-ru-ug-rCN']
        for d in invalid_dirs: d.mkdir(parents=True)
        invalid = subprocess.run([sys.executable,str(validator),str(root),str(work/'bad-ru-dirs.json')],capture_output=True,text=True)
        assert invalid.returncode!=0 and 'values-ru-bo-rCN' in invalid.stdout and 'values-ru-ug-rCN' in invalid.stdout, invalid.stdout+invalid.stderr
        for d in invalid_dirs: d.rmdir()
        ru_xml=ET.parse(root/'res'/'values-ru'/'strings.xml').getroot()
        privacy=next(e for e in ru_xml if e.attrib.get('name')=='onboarding_privacy_tips_2')
        payload=privacy.find('Data')
        assert payload is not None and '%1$s' in ''.join(payload.itertext()) and 'Пользовательское соглашение Xiaomi Health Research' in ''.join(payload.itertext())
        assert '<a href=\"%1$s\">' in ''.join(payload.itertext()), 'encoded HTML links must remain encoded and functional'
        assert {x['key'] for x in data['nontranslatable_critical_overrides']} >= {'onboarding_join_experience_program','onboarding_privacy_tips_2'}
        assert any(x.get('key')=='common_am' and x.get('reason')=='translatable_false' for x in data['skipped_rich_xml'])
        assert any(x.get('key')=='common_pm' and x.get('reason')=='placeholder_mismatch' for x in data['skipped_rich_xml'])
        assert source.read_text(encoding='utf-8') == base_xml, 'base values must remain untouched'
        out=ET.parse(root/'res'/'values-ru'/'strings.xml').getroot()
        outmap={e.attrib.get('name'):e for e in list(out) if isinstance(e.tag,str)}
        for key, hrefs in [('onboarding_join_experience_program',['%1$s']),('onboarding_privacy_tips_2',['%1$s','%2$s','%3$s'])]:
            el=outmap[key]
            visible=''.join(el.itertext())
            assert not any('\u3400' <= c <= '\u9fff' for c in visible), key+' still contains CJK'
            actual=[n.attrib['href'] for n in el.iter() if isinstance(n.tag,str) and 'href' in n.attrib]
            if key=='onboarding_privacy_tips_2' and el.find('Data') is not None:
                # Apktool 3 encodes the original HTML anchors inside Data text.
                payload=el.find('Data').text or ''
                assert all(('href=\"'+ph+'\"') in payload for ph in hrefs), (key,payload)
            else:
                assert actual==hrefs,(key,actual)
            assert not any(ch in visible for ch in ('用户体验','小米健康研究','隐私政策')), key+' untranslated text'
        escaped=outmap['onboarding_privacy_tips_xieyi']
        assert isinstance(escaped.text,str) and '<a href="%1$s">' in escaped.text, 'escaped HTML link text/placeholder lost'
        assert not any('\u3400' <= c <= '\u9fff' for c in escaped.text), 'escaped HTML link left CJK'

        # Critical-gate failures must persist an audit rather than leave an empty log.
        failroot=work/'missing'; (failroot/'res'/'values').mkdir(parents=True)
        missingxml='\n'.join(lines[:2]+[line for line in lines[2:-1] if 'onboarding_join_experience_program' not in line]+['</resources>'])+'\n'
        (failroot/'res'/'values'/'strings.xml').write_text(missingxml,encoding='utf-8')
        failaudit=work/'failed-audit.json'
        failed=subprocess.run([sys.executable,str(Path(__file__).with_name('v13_localize.py')),str(failroot),str(tr),str(failaudit)],capture_output=True,text=True)
        assert failed.returncode != 0 and failaudit.is_file(), failed.stdout+failed.stderr
        failure=json.loads(failaudit.read_text(encoding='utf-8'))
        assert 'onboarding_join_experience_program' in failure['critical_keys_missing']
        assert 'V13_CRITICAL_SOURCE_SHAPE=onboarding_join_experience_program:' in failed.stdout

    # Smoke-test the same UI text checker that the Android emulator job invokes.
    with tempfile.TemporaryDirectory(prefix='v13-ui-probe-') as td:
        work=Path(td); ui=work/'ui.xml'
        visible=['Добро пожаловать','Исследование здоровья Xiaomi','Наслаждайтесь здоровой жизнью','Согласен','Не соглашаться и перейти в базовый режим','программе улучшения пользовательского опыта','Пользовательское соглашение Xiaomi Health Research','политика конфиденциальности Xiaomi Health Research','краткое изложение политики конфиденциальности']
        nodes=''.join(f'<node text="{item}" bounds="[10,20][210,80]" />' for item in visible)
        ui.write_text('<hierarchy>'+nodes+'</hierarchy>',encoding='utf-8')
        probe=Path(__file__).with_name('v13_ui_probe.py')
        checked=subprocess.run([sys.executable,str(probe),str(ui),'check'],capture_output=True,text=True)
        assert checked.returncode==0,checked.stdout+checked.stderr
        tapped=subprocess.run([sys.executable,str(probe),str(ui),'tap'],capture_output=True,text=True)
        assert tapped.returncode==0 and tapped.stdout.strip().splitlines()[-1]=='110 50',tapped.stdout+tapped.stderr
        basic=work/'basic.xml'; basic.write_text('<hierarchy><node text="Настройки" /></hierarchy>',encoding='utf-8')
        basic_result=subprocess.run([sys.executable,str(probe),str(basic),'check-basic'],capture_output=True,text=True)
        assert basic_result.returncode==0,basic_result.stdout+basic_result.stderr

    code=Path(__file__).with_name('v13_localize.py').read_text(encoding='utf-8')
    assert 'mandatory_ru_overlay_for_translatable_false_source' in code
    assert 'V13_LOCALIZATION_FAILURE_AUDIT=' in code
    assert 'Clear ALL text/tails before writing' in code
    assert 'Clear ALL text/tails before writing' in code
    print('V16_ANDROID_LANGUAGE_QUALIFIER_ROUTING=PASS')
    print('V16_ANDROID_CAR_MODE_QUALIFIER_PRESERVED=PASS')
    print('V16_ANDROID_MCC_QUALIFIER_ORDER_PRESERVED=PASS')
    print('V16_INVALID_RU_DIRECTORY_NEGATIVE_TEST=PASS')
    print('V16_RESOURCE_COVERAGE_PARSER_PUBLIC_AND_NONPUBLIC=PASS')
    print('V16_EMPTY_COVERAGE_PARSER_FAILS_CLOSED=PASS')
    print('V16_JAVA_FORMATTER_PLACEHOLDER_VALIDATION=PASS')
    print('V13_PLACEHOLDER_REPAIR=PASS')
    print('V13_RESOURCE_FILE_TYPE_PRESERVATION=PASS')
    print('V13_ANY_ATTR_NORMALIZATION=PASS')
    print('V13_ENUM_METADATA_DIFF_NOT_IGNORED=PASS')
    print('V13_ENUM_FORMAT_RESTORATION=PASS')
    print('V13_STYLEABLE_ATTR_REFERENCES_PRESERVED=PASS')
    print('V13_STRICT_RESOURCE_COMPARATOR_NEGATIVE_TESTS=PASS')
    print('V13_CRITICAL_NONTRANSLATABLE_OVERLAY=PASS')
    print('V13_RICH_LINK_AND_PLACEHOLDER_PRESERVATION=PASS')
    print('V13_BASE_VALUES_IMMUTABLE=PASS')
    print('V13_NONCRITICAL_NONTRANSLATABLE_STILL_SKIPPED=PASS')
    print('V13_PLACEHOLDER_MISMATCH_FAILSAFE=PASS')
    print('V13_FAILURE_AUDIT_PERSISTENCE=PASS')
    print('V13_ANDROID_UI_PROBE=PASS')
    # Release pipeline must keep native-library alignment compatible with 16 KiB pages,
    # and alignment must be re-verified on the signed artifact.
    workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'v13.yml'
    if workflow.is_file():
        text = workflow.read_text(encoding='utf-8')
        assert 'zipalign" -f -P 16 -v 4' in text
        assert 'zipalign" -c -P 16 -v 4' in text
        assert text.index('zipalign" -f -P 16 -v 4') < text.index('apksigner" sign')
        assert text.index('apksigner" sign') < text.index('apksigner" verify')
        print('V16_SIGNING_ALIGNMENT_ORDER_AND_16K_NATIVE_ALIGNMENT=PASS')

if __name__=='__main__': main()
