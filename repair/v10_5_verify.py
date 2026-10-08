#!/usr/bin/env python3
import hashlib,json,sys,zipfile

def entries(p):
    with zipfile.ZipFile(p) as z:return {n:z.read(n) for n in z.namelist()}
def sha(p):return hashlib.sha256(open(p,'rb').read()).hexdigest()
def main(orig,v8,final,analysis):
    A,B,C=entries(orig),entries(v8),entries(final)
    allowed={'classes.dex','resources.arsc'}
    for n in sorted(set(A)|set(C)):
        if n in allowed or n.startswith('META-INF/'): continue
        if A.get(n)!=C.get(n): raise SystemExit('ORIGINAL_PAYLOAD_CHANGED:'+n)
    if C['classes.dex']!=B['classes.dex']: raise SystemExit('V10.5_DEX_NOT_V8')
    if C['classes2.dex']!=A['classes2.dex']: raise SystemExit('V10.5_DEX2_CHANGED')
    if C['AndroidManifest.xml']!=A['AndroidManifest.xml']: raise SystemExit('V10.5_MANIFEST_CHANGED')
    if C['resources.arsc']==A['resources.arsc']: raise SystemExit('RU_RESOURCE_OVERLAY_NOT_APPLIED')
    if len(C.get('resources.arsc',b'')) < 64: raise SystemExit('BAD_RESOURCES_ARSC')
    with open(analysis,encoding='utf-8') as f: a=json.load(f)
    if a['unexpected_functional_changes']: raise SystemExit('ORIGINAL_V8_COMPARE_NOT_CLEAN')
    print('V10.5_FUNCTIONAL_PAYLOAD=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_DEX=V8_BYTE_IDENTICAL')
    print('V10.5_DEX2=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_MANIFEST=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_SHA256='+sha(final))
if __name__=='__main__': main(*sys.argv[1:])
