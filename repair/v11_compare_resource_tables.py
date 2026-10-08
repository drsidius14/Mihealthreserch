#!/usr/bin/env python3
"""Compare aapt2 semantic resource-table dumps, allowing RU overlays only."""
import collections, json, re, sys
from pathlib import Path

HEADER = re.compile(r'^\s*resource\s+(0x[0-9a-fA-F]+)\s+([^\s/]+)/([^\s]+)')
VALUE = re.compile(r'^\s{6}\(([^)]*)\)\s+(.*)$')
FILE_VALUE = re.compile(r'^\(file\)\s+\S+\s+type=(\S+)$')

def normalize_value(v):
    v=v.strip()
    m=FILE_VALUE.match(v)
    if m:
        # Apktool renames obfuscated resources to resource-qualified paths.
        # Compare the compiled file type, not the implementation-dependent ZIP name.
        return '<FILE type='+m.group(1)+'>'
    return v

def parse_dump(path):
    resources={}
    cur=None
    with open(path,encoding='utf-8',errors='replace') as f:
        for line in f:
            h=HEADER.match(line)
            if h:
                cur=(h.group(1).lower(),h.group(2),h.group(3))
                resources.setdefault(cur,collections.defaultdict(list))
                continue
            if cur is None: continue
            v=VALUE.match(line)
            if v:
                config=v.group(1).strip() or 'default'
                resources[cur][config].append(normalize_value(v.group(2)))
    return resources

def is_ru(config):
    x=config.strip().lower()
    return x == 'ru' or x.startswith('ru-') or x.startswith('ru_') or x.startswith('ru-r')

def main(base_dump,candidate_dump,audit_path,report_path,mode='strict'):
    base=parse_dump(base_dump); cand=parse_dump(candidate_dump)
    audit=json.loads(Path(audit_path).read_text(encoding='utf-8')) if audit_path and Path(audit_path).exists() else {}
    allowed=set(audit.get('keys_written',[]))
    # Existing V10.7 audit's resource entries are key tuples, not key strings.
    if not allowed and audit.get('resources'):
        for row in audit['resources']:
            k=row.get('resource')
            if isinstance(k,list) and len(k)>1: allowed.add(k[1])
    missing=sorted(set(base)-set(cand)); added=sorted(set(cand)-set(base))
    unexpected=[]; allowed_diffs=[]; config_diffs=collections.Counter()
    for key in sorted(set(base)&set(cand)):
        bconfs=base[key]; cconfs=cand[key]
        for config in sorted(set(bconfs)|set(cconfs)):
            bv=bconfs.get(config); cv=cconfs.get(config)
            if bv==cv: continue
            # Only a reviewed string resource may acquire/change a Russian locale value.
            if key[1]=='string' and key[2] in allowed and is_ru(config):
                allowed_diffs.append({'id':key[0],'type':key[1],'name':key[2],'config':config,'base':bv,'candidate':cv})
                config_diffs['allowed_ru']+=1
            else:
                unexpected.append({'id':key[0],'type':key[1],'name':key[2],'config':config,'base':bv,'candidate':cv})
                config_diffs[config]+=1
    report={
      'mode':mode,'base_entries':len(base),'candidate_entries':len(cand),
      'missing_resource_keys':[{'id':k[0],'type':k[1],'name':k[2]} for k in missing],
      'added_resource_keys':[{'id':k[0],'type':k[1],'name':k[2]} for k in added],
      'allowed_ru_differences':allowed_diffs,
      'unexpected_differences':unexpected,
      'difference_counts_by_config':dict(config_diffs),
      'resource_key_set_identical':not missing and not added,
      'non_ru_semantics_unchanged':not unexpected,
      'allowed_translation_keys':len(allowed)
    }
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESOURCE_TABLE_BASE_ENTRIES='+str(len(base)))
    print('RESOURCE_TABLE_CANDIDATE_ENTRIES='+str(len(cand)))
    print('RESOURCE_KEYS_MISSING='+str(len(missing)))
    print('RESOURCE_KEYS_ADDED='+str(len(added)))
    print('RU_OVERLAY_DIFFERENCES='+str(len(allowed_diffs)))
    print('UNEXPECTED_RESOURCE_DIFFERENCES='+str(len(unexpected)))
    print('UNEXPECTED_DIFF_CONFIGS='+json.dumps(dict(config_diffs),ensure_ascii=False,sort_keys=True))
    print('RESOURCE_KEY_SET_IDENTICAL='+str(not missing and not added))
    print('NON_RU_SEMANTICS_UNCHANGED='+str(not unexpected))
    print('RESOURCE_TABLE_REPORT='+report_path)
    if mode=='strict' and (missing or added or unexpected):
        raise SystemExit('V11_RESOURCE_TABLE_SEMANTIC_COMPARE=FAIL')
    print('RESOURCE_TABLE_SEMANTIC_COMPARE='+('PASS' if not missing and not added and not unexpected else 'REPORT_ONLY'))

if __name__=='__main__':
    if len(sys.argv) not in (5,6): raise SystemExit('usage: v11_compare_resource_tables.py base.dump candidate.dump audit.json report.json [strict|report-only]')
    main(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)==6 else 'strict')
