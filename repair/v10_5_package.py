#!/usr/bin/env python3
import hashlib,os,sys,tempfile,zipfile

def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def read(p,n):
    with zipfile.ZipFile(p) as z:return z.read(n)

def main(orig,v8,compiled,out):
    with zipfile.ZipFile(compiled) as z:
        res=z.read('resources.arsc')
    dex=read(v8,'classes.dex')
    if len(res)<16: raise RuntimeError('compiled resources.arsc is too small')
    if len(dex)<8 or not dex.startswith(b'dex\n'): raise RuntimeError('V8 classes.dex invalid')
    with zipfile.ZipFile(orig,'r') as zin:
        fd,tmp=tempfile.mkstemp(prefix='v105-',suffix='.apk',dir=os.path.dirname(out) or '.')
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp,'w') as zout:
                seen=set()
                for info in zin.infolist():
                    n=info.filename
                    if n.startswith('META-INF/') and n.upper().endswith(('.MF','.SF','.RSA','.DSA')):
                        continue
                    if n in ('classes.dex','resources.arsc'):
                        data=dex if n=='classes.dex' else res
                        zi=zipfile.ZipInfo(n,date_time=info.date_time)
                        zi.compress_type=zipfile.ZIP_STORED
                        zi.external_attr=info.external_attr
                        zi.comment=info.comment
                        zout.writestr(zi,data)
                    else:
                        zout.writestr(info,zin.read(n))
                    seen.add(n)
            os.replace(tmp,out)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    print('FUNCTIONAL_BASE=ORIGINAL')
    print('DEX_BASE=V8')
    print('RESOURCE_PAYLOAD=APKTOOL_COMPILED_RU_OVERLAY_ONLY')
    print('UNSIGNED_SHA256='+sha(out))

if __name__=='__main__': main(*__import__('sys').argv[1:])
