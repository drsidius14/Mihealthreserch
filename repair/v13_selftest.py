#!/usr/bin/env python3
"""Offline regression tests for V13 localization and resource semantics."""
import json, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v13_compare_resource_tables import normalize_value
from v13_restore_attribute_formats import main as restore_attribute_formats

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
    v=translations['hospital_bloodpressure_abnormal_from_device']
    assert '%1s' in v and 'Источник:' in v
    assert normalize_value('(file) res/aB.webp type=drawable') == normalize_value('(file) res/drawable-xxhdpi/about_img.webp type=drawable')
    assert normalize_value('(file) res/aB.webp type=drawable') != normalize_value('(file) res/aB.webp type=raw')
    assert normalize_value('(attr) type=any') == normalize_value('(attr) type=reference|string|integer|boolean|color|float|dimension|fraction')
    assert normalize_value('(attr) type=reference|enum') != normalize_value('(attr) type=reference')

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
                val='<string name="%s" translatable="false"> <a href="%%1$s">《小米健康研究用户协议》</a>、<a href="%%2$s">《小米健康研究隐私政策》</a><a href="%%3$s">（《隐私政策》摘要）</a></string>' % name
            else:
                val='<string name="%s">中文测试</string>' % name
            lines.append(val)
        lines.append('<string name="onboarding_privacy_tips_xieyi"> &lt;a href="%1$s"&gt;《小米健康研究用户协议》&lt;/a&gt;</string>')
        lines.append('<string name="common_am" translatable="false">上午</string>')
        lines.append('<string name="common_pm">%1$s下午</string>')
        lines.append('</resources>')
        base_xml='\n'.join(lines)+'\n'; source=values/'strings.xml'; source.write_text(base_xml,encoding='utf-8')
        tr=work/'translations.json'; translations['common_pm']='下午'; tr.write_text(json.dumps(translations,ensure_ascii=False,indent=2),encoding='utf-8')
        audit=work/'audit.json'
        proc=subprocess.run([sys.executable,str(Path(__file__).with_name('v13_localize.py')),str(root),str(tr),str(audit)],capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError('V13 localizer fixture failed:\n'+proc.stdout+'\n'+proc.stderr)
        data=json.loads(audit.read_text(encoding='utf-8'))
        assert set(CRITICAL)==set(data['critical_keys_written']), data.get('critical_keys_written')
        assert {x['key'] for x in data['nontranslatable_critical_overrides']} >= {'onboarding_join_experience_program','onboarding_privacy_tips_2'}
        assert any(x.get('key')=='common_am' and x.get('reason')=='translatable_false' for x in data['skipped_rich_xml'])
        assert any(x.get('key')=='common_pm' and x.get('reason')=='placeholder_mismatch' for x in data['skipped_rich_xml'])
        assert source.read_text(encoding='utf-8') == base_xml, 'base values must remain untouched'
        out=ET.parse(root/'res'/'values-ru'/'strings.xml').getroot()
        outmap={e.attrib.get('name'):e for e in list(out) if isinstance(e.tag,str)}
        for key, hrefs in [('onboarding_join_experience_program',['%1$s']),('onboarding_privacy_tips_2',['%1$s','%2$s','%3$s'])]:
            el=outmap[key]
            assert not any('\u3400' <= c <= '\u9fff' for c in ''.join(el.itertext())), key+' still contains CJK'
            actual=[n.attrib['href'] for n in el.iter() if isinstance(n.tag,str) and 'href' in n.attrib]
            assert actual==hrefs,(key,actual)
            assert not any(ch in ''.join(el.itertext()) for ch in ('用户体验','小米健康研究','隐私政策')), key+' untranslated text'
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
if __name__=='__main__': main()
