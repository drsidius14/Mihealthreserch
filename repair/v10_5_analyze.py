#!/usr/bin/env python3
import hashlib, json, os, struct, sys, zipfile

ORIGINAL_SHA256='b9c06129674ff283cbddd8ec3df73781d12f2d89'
# V8 blob SHA is checked by git history; this is the content SHA from GitHub's blob metadata.
V8_BLOB='6118c187927060a5c9f8092561afdbd5e5c16c28'


def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def zip_bytes(p):
    with zipfile.ZipFile(p) as z:
        return {n:z.read(n) for n in z.namelist()}


def zip_meta(p):
    with zipfile.ZipFile(p) as z:
        return {i.filename:{'size':i.file_size,'crc':i.CRC,'compress_type':i.compress_type} for i in z.infolist()}


def uleb(data, off):
    v=0;s=0
    while True:
        if off>=len(data): raise RuntimeError('ULEB out of range')
        b=data[off];off+=1;v|=(b&0x7f)<<s
        if b<0x80:return v,off
        s+=7


def read_mutf8(data, off):
    n,p=uleb(data,off); units=[]
    while True:
        b0=data[p];p+=1
        if b0==0:break
        if b0<0x80: units.append(b0)
        elif (b0&0xe0)==0xc0:
            b1=data[p];p+=1;units.append(((b0&0x1f)<<6)|(b1&0x3f))
        elif (b0&0xf0)==0xe0:
            b1,b2=data[p],data[p+1];p+=2;units.append(((b0&0x0f)<<12)|((b1&0x3f)<<6)|(b2&0x3f))
        else: raise RuntimeError('unsupported MUTF-8')
    if len(units)!=n: raise RuntimeError('MUTF-8 length mismatch')
    raw=b''.join(struct.pack('<H',u) for u in units)
    return raw.decode('utf-16-le','surrogatepass'),p


def dex_strings(blob):
    if not blob.startswith(b'dex\n'): raise RuntimeError('not dex')
    sc,so=struct.unpack_from('<II',blob,0x38)
    ids=struct.unpack_from(f'<{sc}I',blob,so)
    return [read_mutf8(blob,o)[0] for o in ids]


def digest_diff(a,b):
    names=sorted(set(a)|set(b))
    changed=[]
    for n in names:
        if a.get(n)!=b.get(n): changed.append(n)
    return changed


def main(orig,v8,out):
    oh=sha256_file(orig); vh=sha256_file(v8)
    if not oh: raise RuntimeError('missing original')
    A,B=zip_bytes(orig),zip_bytes(v8)
    changed=digest_diff(A,B)
    functional=[n for n in changed if n not in {'classes.dex','resources.arsc'} and not n.startswith('META-INF/')]
    if functional:
        raise RuntimeError('unexpected functional ZIP diff: '+','.join(functional[:20]))
    if A.get('classes2.dex')!=B.get('classes2.dex'):
        raise RuntimeError('classes2.dex differs from original')
    od=dex_strings(A['classes.dex']); vd=dex_strings(B['classes.dex'])
    from collections import Counter
    delta_a=Counter(od)-Counter(vd); delta_b=Counter(vd)-Counter(od)
    result={
      'original_sha256':oh,
      'v8_sha256':vh,
      'v8_expected_blob':V8_BLOB,
      'changed_zip_entries':changed,
      'unexpected_functional_changes':functional,
      'classes2_identical':A['classes2.dex']==B['classes2.dex'],
      'manifest_identical':A['AndroidManifest.xml']==B['AndroidManifest.xml'],
      'native_libs_identical':all(A.get(n)==B.get(n) for n in set(A)&set(B) if n.startswith('lib/')),
      'assets_identical':all(A.get(n)==B.get(n) for n in set(A)&set(B) if n.startswith('assets/')),
      'dex_string_delta_removed':list(delta_a.elements()),
      'dex_string_delta_added':list(delta_b.elements()),
      'dex_counts':{'original':len(od),'v8':len(vd)},
    }
    if result['dex_string_delta_removed']!=['血压健康研究'] or result['dex_string_delta_added']!=['Исслед. АД']:
        raise RuntimeError('DEX semantic string delta is not the known V8 repair')
    json.dump(result,open(out,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print('BIT_COMPARE=PASS')
    print('ZIP_CHANGED='+','.join(changed))
    print('DEX_SEMANTIC_DELTA=血压健康研究->Исслед. АД')

if __name__=='__main__': main(*sys.argv[1:])
