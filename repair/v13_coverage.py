#!/usr/bin/env python3
"""Report translation coverage among default Chinese string resources."""
import json,re,sys
from pathlib import Path
HEADER=re.compile(r'^\s*resource\s+0x[0-9a-fA-F]+\s+string/([^\s]+) PUBLIC')
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
 covered=sorted(chinese&done); missed=sorted(chinese-done)
 deliberate=[k for k in missed if k.startswith(DELIBERATELY_UNTRANSLATED)]
 user_visible_candidates=[k for k in missed if k not in deliberate]
 ratio=len(covered)/max(1,len(chinese))
 report={'default_chinese_strings':len(chinese),'translated_chinese_keys':len(covered),'coverage_ratio':ratio,'untranslated_keys':missed,'deliberately_untranslated_calendar_keys':deliberate,'untranslated_not_calendar':user_visible_candidates,'keys_written_total':len(done),'skipped_rich_xml':audit.get('skipped_rich_xml',[])}
 Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('V13_DEFAULT_CJK_STRING_KEYS='+str(len(chinese)))
 print('V13_CJK_KEYS_TRANSLATED='+str(len(covered)))
 print('V13_CJK_TRANSLATION_COVERAGE_PERCENT='+f'{ratio*100:.1f}')
 print('V13_UNTRANSLATED_CJK_NON_CALENDAR='+str(len(user_visible_candidates)))
 print('V13_TRANSLATION_COVERAGE_REPORT='+report_path)
 if ratio<0.90: raise SystemExit('V13_TRANSLATION_COVERAGE_BELOW_90_PERCENT')
if __name__=='__main__':
 if len(sys.argv)!=4: raise SystemExit('usage: v13_coverage.py aapt2-resources.dump translation-audit.json coverage-report.json')
 main(*sys.argv[1:])
