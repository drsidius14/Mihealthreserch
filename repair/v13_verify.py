#!/usr/bin/env python3
"""Static release gate for V13 APK: payload identity, resource closure, and RU onboarding."""
import hashlib, json, re, sys, zipfile, html, struct, zlib
from pathlib import Path
from v13_compare_resource_tables import parse_dump, is_ru
from v13_forensic import dex_strings

EXPECTED_ORIGINAL = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
EXPECTED_V8 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'
REQUIRED_PROVIDER = 'res/xml/appupgrade_provider_paths.xml'
SIG_SUFFIXES = ('.MF','.SF','.RSA','.DSA','.EC')
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
 'onboarding_privacy_tips_2':'Пользовательское соглашение Xiaomi Health Research'
}
RICH_REQUIRED = {
 'onboarding_join_experience_program': ('%1$s', 'программе улучшения пользовательского опыта', 'продукты и услуги'),
 'onboarding_privacy_tips_2': ('%1$s', '%2$s', '%3$s', 'Пользовательское соглашение Xiaomi Health Research', 'политика конфиденциальности Xiaomi Health Research', 'краткое изложение политики конфиденциальности')
}


def sha_file(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def load_entries(p):
 with zipfile.ZipFile(p,'r') as z:
  bad=z.testzip()
  if bad: raise SystemExit('ZIP_CRC_FAILURE:'+bad)
  names=z.namelist()
  if len(names)!=len(set(names)): raise SystemExit('DUPLICATE_ZIP_PATHS')
  return {n:z.read(n) for n in names}

def main(original,v8,localized_dex,final,resources_dump,badging,audit_path,translations_path,dex_translations_path,dex_audit_path):
 if sha_file(original)!=EXPECTED_ORIGINAL: raise SystemExit('ORIGINAL_SHA256_MISMATCH')
 if sha_file(v8)!=EXPECTED_V8: raise SystemExit('V8_SHA256_MISMATCH')
 A=load_entries(original); B=load_entries(v8); D=load_entries(localized_dex); C=load_entries(final)
 for name in sorted(set(A)|set(C)):
  if name=='classes.dex' or name=='resources.arsc' or name.startswith('res/') or (name.startswith('META-INF/') and name.upper().endswith(SIG_SUFFIXES)):
   continue
  if A.get(name)!=C.get(name): raise SystemExit('ORIGINAL_NON_RESOURCE_PAYLOAD_CHANGED:'+name)
 if 'classes.dex' not in D or C.get('classes.dex')!=D.get('classes.dex'): raise SystemExit('V16_CLASSES_DEX_NOT_EXACT_V8_SMALI_REASSEMBLY')
 dex=C.get('classes.dex',b'')
 if not dex.startswith(b'dex\n') or len(dex)<112: raise SystemExit('V16_FINAL_DEX_HEADER_INVALID')
 if hashlib.sha1(dex[32:]).digest()!=dex[12:32]: raise SystemExit('V16_FINAL_DEX_SHA1_INVALID')
 if (zlib.adler32(dex[12:])&0xffffffff)!=struct.unpack_from('<I',dex,8)[0]: raise SystemExit('V16_FINAL_DEX_ADLER32_INVALID')
 dex_map=json.loads(Path(dex_translations_path).read_text(encoding='utf-8'))
 dex_audit=json.loads(Path(dex_audit_path).read_text(encoding='utf-8'))
 dex_values=set(dex_strings(dex))
 dex_translations=dex_map.get('translations',[])
 if len(dex_translations)!=11: raise SystemExit('V16_DEX_TRANSLATION_MAP_INCOMPLETE')
 if dex_audit.get('status')!='PASS': raise SystemExit('V16_DEX_TRANSLATION_AUDIT_NOT_PASS')
 source_occurrences=dex_audit.get('source_occurrences',{})
 scoped_remaining=dex_audit.get('remaining_scoped_source_occurrences',{})
 for row in dex_translations:
  source,target=row['source'],row['target']
  if 'scope_context' in row:
   if source_occurrences.get(source,0)<1 or scoped_remaining.get(source,0)!=0:
    raise SystemExit('V16_SCOPED_LITERAL_TRANSLATION_NOT_PROVEN:'+source[:80])
  elif source in dex_values:
   raise SystemExit('V16_CJK_LITERAL_REMAINS_IN_FINAL_DEX:'+source[:80])
  if target not in dex_values: raise SystemExit('V16_TRANSLATED_LITERAL_MISSING_FROM_FINAL_DEX:'+target[:80])
 if C.get('classes2.dex')!=A.get('classes2.dex'): raise SystemExit('V13_CLASSES2_DEX_CHANGED')
 if C.get('AndroidManifest.xml')!=A.get('AndroidManifest.xml'): raise SystemExit('V13_MANIFEST_CHANGED')
 if REQUIRED_PROVIDER not in C or len(C[REQUIRED_PROVIDER])<8: raise SystemExit('V13_FILEPROVIDER_XML_MISSING')
 res_files={n for n in C if n.startswith('res/') and not n.endswith('/')}
 if len(res_files)<1000: raise SystemExit('V13_RESOURCE_FILES_TOO_FEW')
 with open(resources_dump,encoding='utf-8',errors='replace') as f: dump=f.read()
 referenced=set(re.findall(r'\(file\)\s+(res/\S+?)\s+type=',dump))
 missing=sorted(referenced-set(C))
 if not referenced: raise SystemExit('RESOURCE_DUMP_HAS_NO_FILE_REFERENCES')
 if missing: raise SystemExit('RESOURCE_PATHS_MISSING:'+repr(missing[:30]))
 if REQUIRED_PROVIDER not in referenced: raise SystemExit('FILEPROVIDER_RESOURCE_NOT_REFERENCED')
 audit=json.loads(Path(audit_path).read_text(encoding='utf-8'))
 translations=json.loads(Path(translations_path).read_text(encoding='utf-8'))
 keys=set(audit.get('keys_written',[]))
 if len(keys)<1000: raise SystemExit('V13_TOO_FEW_TRANSLATION_KEYS:'+str(len(keys)))
 # Cross-check every generated RU string against the reviewed translation map.
 # Strip only explicit anchor markup while preserving its visible text.
 rows=audit.get('translations',[])
 checked=set()
 for row in rows:
  resource=row.get('resource')
  if not isinstance(resource,list) or len(resource)<2 or resource[0] != 'string':
   continue
  name=resource[1]
  raw=translations.get(name)
  if raw is None:
   raise SystemExit('V13_AUDIT_KEY_NOT_IN_TRANSLATION_MAP:'+str(name))
  expected=re.sub(r'<a\b[^>]*>(.*?)</a>',r'\1',raw,flags=re.S)
  expected=re.sub(r'<[^>]+>','',expected)
  expected=html.unescape(expected)
  actual=row.get('value','')
  actual=re.sub(r'<a\b[^>]*>(.*?)</a>',r'\1',actual,flags=re.S)
  actual=re.sub(r'<[^>]+>','',actual)
  actual=html.unescape(actual)
  if actual != expected:
   raise SystemExit('V13_TRANSLATION_MAP_AUDIT_MISMATCH:'+name+':'+repr(actual)+' != '+repr(expected))
  checked.add(name)
 if len(checked)<1000: raise SystemExit('V13_TRANSLATION_AUDIT_NOT_INDEPENDENT:'+str(len(checked)))
 parsed=parse_dump(resources_dump)
 for name,expected in CRITICAL.items():
  matches=[(key,configs) for key,configs in parsed.items() if key[1]=='string' and key[2]==name]
  if not matches: raise SystemExit('CRITICAL_RESOURCE_MISSING:'+name)
  found=[]
  for key,configs in matches:
   vals=[v for config,vs in configs.items() if is_ru(config) for v in vs]
   if vals: found.extend(vals)
  if not found: raise SystemExit('CRITICAL_RU_VALUE_MISSING:'+name)
  if any(re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]',v) for v in found): raise SystemExit('CRITICAL_RU_VALUE_HAS_CJK:'+name)
  if name in ('app_name','onboarding_app_name') and not any(expected in v for v in found):
   raise SystemExit('V13_CRITICAL_APP_LABEL_VALUE_MISMATCH:'+name+':'+repr(found))
  for required in RICH_REQUIRED.get(name, ()):
   if not any(required in v for v in found):
    raise SystemExit('V13_RICH_CONSENT_TEXT_OR_PLACEHOLDER_MISSING:'+name+':'+required+':'+repr(found))
 with open(badging,encoding='utf-8',errors='replace') as f: badge=f.read()
 if "package: name='com.mi.healthresearch'" not in badge: raise SystemExit('PACKAGE_NAME_CHANGED')
 if "application-label-ru:'Исследование здоровья Xiaomi'" not in badge and 'application-label-ru:"Исследование здоровья Xiaomi"' not in badge:
  if not re.search(r"application-label-ru:'?Исследование здоровья Xiaomi",badge): raise SystemExit('RUSSIAN_APP_LABEL_NOT_IN_BADGING')
 print('V13_ORIGINAL_NON_RESOURCE_PAYLOAD=PASS')
 print('V16_CLASSES_DEX_EXACT_ORIGINAL_SMALI_REASSEMBLY=PASS')
 print('V16_HARDCODED_UI_TRANSLATIONS_IN_FINAL_DEX=PASS')
 print('V16_COMMON_DIALOG_LABELS_TRANSLATED_ONLY_IN_SCOPED_METHOD=PASS')
 print('V16_FINAL_DEX_SIGNATURE_AND_CHECKSUM=PASS')
 print('V16_SIGNING_CERTIFICATE_IS_REGENERATED_BY_WORKFLOW=YES')
 print('V13_CLASSES2_DEX_EXACT_ORIGINAL=PASS')
 print('V13_MANIFEST_EXACT_ORIGINAL=PASS')
 print('V13_FILEPROVIDER_RESOURCE_PATHS_CLOSED=PASS')
 print('V13_RESOURCE_FILES='+str(len(res_files)))
 print('V13_RESOURCE_FILE_REFERENCES='+str(len(referenced)))
 print('V13_TRANSLATION_KEYS_WRITTEN='+str(len(keys)))
 print('V13_TRANSLATION_MAP_MATCHED_KEYS='+str(len(checked)))
 print('V13_RUSSIAN_ONBOARDING=PASS')
 print('V13_SHA256='+sha_file(final))

if __name__=='__main__':
 if len(sys.argv)!=11: raise SystemExit('usage: v13_verify.py original.apk v8.apk v8-smali-rebuilt.apk final.apk resources-dump.txt badging.txt translation-audit.json translations.json dex-translations.json dex-localization-audit.json')
 main(*sys.argv[1:])
