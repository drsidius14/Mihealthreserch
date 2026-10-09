#!/usr/bin/env python3
"""Compare a locally produced V10.7 forensic report with a fresh GitHub-run copy."""
import json, sys
from pathlib import Path
FIELDS = [
 ('sha256','original'),('sha256','v10_7'),('sha256','v8'),
 ('zip_entries','original'),('zip_entries','v10_7'),('zip_entries','added'),('zip_entries','removed'),('zip_entries','common_changed'),('zip_entries','original_manifest_sha256'),('zip_entries','v10_7_manifest_sha256'),
 ('payload_identity','AndroidManifest.xml_identical'),('payload_identity','classes2.dex_identical'),
 ('payload_identity','assets_identical'),('payload_identity','native_libraries_identical'),
 ('dex','original_strings'),('dex','v10_7_strings'),('dex','strings_removed'),('dex','strings_added'),('dex','v10_7_exact_v8'),('dex','bytes_original'),('dex','bytes_v10_7'),('dex','bytes_v8'),
 ('dex','original_sha1_signature_valid'),('dex','v10_7_sha1_signature_valid'),
 ('dex','original_adler32_valid'),('dex','v10_7_adler32_valid'),
 ('resource_safety','provider_xml_present'),('resource_safety','original_res_entries'),('resource_safety','v10_7_res_entries'),
 ('critical_risk','original_signing_certificate_sha256'),('critical_risk','v10_7_signing_certificate_sha256'),('critical_risk','same_signing_certificate'),('critical_risk','server_auth_may_reject_repacked_signature')]
def walk(obj,path):
 for k in path: obj=obj[k]
 return obj
def main(reference,github,report):
 a=json.loads(Path(reference).read_text(encoding='utf-8')); b=json.loads(Path(github).read_text(encoding='utf-8'))
 diffs=[]
 for path in FIELDS:
  x,y=walk(a,path),walk(b,path)
  if x!=y: diffs.append({'field':'.'.join(path),'local':x,'github':y})
 out={'fields_compared':len(FIELDS),'differences':diffs,'independent_report_match':not diffs}
 Path(report).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print('FORENSIC_FIELDS_COMPARED='+str(len(FIELDS)))
 print('FORENSIC_REPORT_DIFFERENCES='+str(len(diffs)))
 print('LOCAL_VS_GITHUB_FORENSICS='+('PASS' if not diffs else 'FAIL'))
 print('FORENSIC_CROSSCHECK_REPORT='+report)
 if diffs: raise SystemExit('V13_CROSS_ENV_FORENSIC_MISMATCH')
if __name__=='__main__':
 if len(sys.argv)!=4: raise SystemExit('usage: v13_compare_forensic_reports.py local.json github.json report.json')
 main(*sys.argv[1:])
