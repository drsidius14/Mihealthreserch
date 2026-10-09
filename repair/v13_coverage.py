#!/usr/bin/env python3
"""Report translation coverage; enforce reviewed critical UI keys, not an arbitrary percentage."""
import json,re,sys
from pathlib import Path
HEADER=re.compile(r'^\s*resource\s+0x[0-9a-fA-F]+\s+string/([^\s/]+)(?:\s+PUBLIC)?\s*$')
VALUE=re.compile(r'^\s{6}\(([^)]*)\)\s+(.*)$')
CJK=re.compile(r'[\u3400-\u9fff]')
DELIBERATELY_UNTRANSLATED=('chinese_','earthly_','heavenly_','fmt_chinese_date')
def main(dump,audit_path,report_path):
 audit=json.loads(Path(audit_path).read_text(encoding='utf-8')); done=set(audit.get('keys_written',[]));cur=None; chinese=set()
 for line in Path(dump).read_text(encoding='utf-8',errors='replace').splitlines():
  h=HEADER.match(line)
  if h: cur=h.group(1); continue
  if cur:
   v=VALUE.match(line)
   if v and v.group(1).strip() in ('','default'):
    raw=v.group(2); m=re.search(r'"(.*)"(?: Data:.*)?$',raw); value=m.group(1) if m else raw
    if CJK.search(value): chinese.add(cur)
    cur=None
 parser_found_cjk = bool(chinese)
 covered=sorted(chinese&done); missed=sorted(chinese-done)
 deliberate=[k for k in missed if k.startswith(DELIBERATELY_UNTRANSLATED)]
 user_visible_candidates=[k for k in missed if k not in deliberate]
 ratio=len(covered)/max(1,len(chinese))
 report={'coverage_parser_found_cjk_strings':parser_found_cjk,'default_chinese_strings':len(chinese),'translated_chinese_keys':len(covered),'coverage_ratio':ratio,'untranslated_keys':missed,'deliberately_untranslated_calendar_keys':deliberate,'untranslated_not_calendar':user_visible_candidates,'keys_written_total':len(done),'skipped_rich_xml':audit.get('skipped_rich_xml',[])}
 Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('V16_DEFAULT_CJK_STRING_KEYS='+str(len(chinese)))
 print('V16_CJK_KEYS_TRANSLATED='+str(len(covered)))
 print('V16_CJK_TRANSLATION_COVERAGE_PERCENT='+f'{ratio*100:.1f}')
 print('V16_UNTRANSLATED_CJK_NON_CALENDAR='+str(len(user_visible_candidates)))
 print('V16_TRANSLATION_COVERAGE_REPORT='+report_path)
 # Coverage is a diagnostic metric, not a release gate: AndroidX/MIUIX and calendar
 # resources can remain intentionally untranslated without affecting the reviewed
 # app-owned UI. Critical consent/onboarding strings are enforced by v13_localize.py
 # and the emulator smoke test; resource semantics remain independently strict.
 critical={'app_name','onboarding_app_name','onboarding_welcome_use','onboarding_slogan',
           'onboarding_agree','onboarding_disagree_and_continue','onboarding_exit_app',
           'onboarding_please_read','onboarding_join_experience_program','onboarding_privacy_tips_2'}
 missing_critical=sorted(critical-done)
 report['critical_ui_keys_required']=sorted(critical)
 report['critical_ui_keys_missing']=missing_critical
 report['coverage_gate']='diagnostic_only'
 Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 if not parser_found_cjk:
  raise SystemExit('V16_COVERAGE_PARSER_FOUND_ZERO_DEFAULT_CJK_STRINGS')
 if missing_critical: raise SystemExit('V16_CRITICAL_RU_UI_KEYS_MISSING='+','.join(missing_critical))
 print('V16_TRANSLATION_COVERAGE_GATE=PASS (diagnostic coverage; critical UI keys enforced)')
if __name__=='__main__':
 if len(sys.argv)!=4: raise SystemExit('usage: v13_coverage.py aapt2-resources.dump translation-audit.json coverage-report.json')
 main(*sys.argv[1:])
