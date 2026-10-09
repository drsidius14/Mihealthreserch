#!/usr/bin/env python3
"""Inventory actual decoded XML shapes/attributes for mandatory onboarding strings."""
import json, sys, xml.etree.ElementTree as ET
from pathlib import Path
KEYS={'app_name','onboarding_app_name','onboarding_welcome_use','onboarding_slogan','onboarding_agree','onboarding_disagree_and_continue','onboarding_exit_app','onboarding_please_read','onboarding_join_experience_program','onboarding_privacy_tips_2'}
def tag(n): return n.tag.rsplit('}',1)[-1] if isinstance(n.tag,str) else '#comment'
def main(root,out):
 root=Path(root); found={k:[] for k in KEYS}
 for p in sorted(root.glob('res/values*/*.xml')):
  try: tree=ET.parse(p,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
  except ET.ParseError as e: raise SystemExit('CRITICAL_SOURCE_XML_PARSE_ERROR:'+str(p)+':'+str(e))
  for e in list(tree.getroot()):
   name=e.attrib.get('name')
   if name not in KEYS: continue
   found[name].append({'file':str(p.relative_to(root)),'tag':tag(e),'attributes':dict(e.attrib),'child_tags':[tag(c) for c in list(e)],'href_values':[n.attrib.get('href') for n in e.iter() if isinstance(n.tag,str) and 'href' in n.attrib],'visible_text':''.join(e.itertext())})
 payload={'found':found,'missing_keys':sorted(k for k,v in found.items() if not v)}
 Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 print('V13_CRITICAL_SOURCE_SHAPE_KEYS_FOUND='+str(sum(bool(v) for v in found.values()))+'/'+str(len(KEYS)))
 print('V13_CRITICAL_SOURCE_SHAPE_REPORT='+str(out))
if __name__=='__main__':
 if len(sys.argv)!=3: raise SystemExit('usage: v13_extract_critical_sources.py <decoded-root> <report.json>')
 main(sys.argv[1],sys.argv[2])
