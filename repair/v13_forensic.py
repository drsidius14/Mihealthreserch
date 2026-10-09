#!/usr/bin/env python3
"""Independent offline APK forensic comparison: original Xiaomi CN APK vs V10.7."""
import collections, hashlib, json, os, re, struct, sys, zipfile, zlib, subprocess, tempfile

EXPECTED_ORIGINAL = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
EXPECTED_V107 = '5f3c9ea4eec8a7260324669fe8fe789f1f789c5de0ffb3fc34257407df00a92e'
EXPECTED_V8 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'
EXPECTED_XIAOMI_CERT = '9c:b6:46:2c:d3:15:47:c8:23:76:3e:e8:ca:30:d3:5a:d4:48:f4:03:44:12:cf:6e:6e:e7:7d:fb:52:93:df:1d'
EXPECTED_V107_CERT = '48:e4:21:b8:f5:d2:dd:75:0f:ff:98:4f:5e:39:c2:98:49:0b:7a:57:bc:df:ee:9f:f6:90:dd:a4:36:28:d4:ed'
SIG_SUFFIX = ('.MF','.SF','.RSA','.DSA','.EC')

def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()
def read_uleb(data, p):
    val=0; shift=0
    while True:
        b=data[p]; p+=1; val |= (b&127)<<shift
        if not (b&128): return val,p
        shift+=7
        if shift>35: raise ValueError('invalid ULEB128')
def dex_strings(dex):
    if not dex.startswith(b'dex\n') or len(dex)<112: raise ValueError('not a valid DEX header')
    declared=struct.unpack_from('<I',dex,32)[0]
    count,off=struct.unpack_from('<II',dex,56)
    if declared!=len(dex) or off+count*4>len(dex): raise ValueError('bad DEX boundaries')
    out=[]
    for i in range(count):
        p=struct.unpack_from('<I',dex,off+i*4)[0]
        _utf16,p=read_uleb(dex,p)
        end=dex.index(b'\0',p,p+65536)
        out.append(dex[p:end].decode('utf-8','replace'))
    return out

def load(path):
    z=zipfile.ZipFile(path)
    bad=z.testzip()
    if bad: raise RuntimeError(f'{path}: bad CRC: {bad}')
    names=z.namelist()
    if len(names)!=len(set(names)): raise RuntimeError(f'{path}: duplicate ZIP names')
    data={n:z.read(n) for n in names if not n.endswith('/')}
    return data

def signer_fingerprint(entries, label):
    cert_entries=[(name,data) for name,data in entries.items()
                  if name.startswith('META-INF/') and name.upper().endswith(('.RSA','.DSA','.EC'))]
    if not cert_entries:
        raise RuntimeError(label+': signature certificate container not found')
    import tempfile, pathlib
    with tempfile.TemporaryDirectory(prefix='v13-cert-') as td:
        container=pathlib.Path(td)/'signature.bin'; pem=pathlib.Path(td)/'cert.pem'
        container.write_bytes(cert_entries[0][1])
        p=subprocess.run(['openssl','pkcs7','-inform','DER','-in',str(container),'-print_certs','-out',str(pem)],capture_output=True,text=True)
        if p.returncode != 0:
            raise RuntimeError(label+': cannot parse PKCS#7 certificate: '+p.stderr[-500:])
        p=subprocess.run(['openssl','x509','-in',str(pem),'-noout','-fingerprint','-sha256'],capture_output=True,text=True)
        if p.returncode != 0:
            raise RuntimeError(label+': cannot read signing certificate: '+p.stderr[-500:])
        m=re.search(r'Fingerprint=([0-9A-Fa-f:]+)',p.stdout)
        if not m: raise RuntimeError(label+': SHA-256 certificate fingerprint missing')
        return m.group(1).lower()

def main(original,v107,v8,out):
    A=load(original); B=load(v107); V=load(v8)
    hsA=file_sha(original); hsB=file_sha(v107); hsV=file_sha(v8)
    if hsA != EXPECTED_ORIGINAL: raise SystemExit('ORIGINAL_SHA256_MISMATCH '+hsA)
    if hsB != EXPECTED_V107: raise SystemExit('V10_7_SHA256_MISMATCH '+hsB)
    if hsV != EXPECTED_V8: raise SystemExit('V8_SHA256_MISMATCH '+hsV)
    an,bn=set(A),set(B); added=sorted(bn-an); removed=sorted(an-bn); common=sorted(an&bn)
    changed=[n for n in common if A[n]!=B[n]]
    manifest_A=[{'path':n,'size':len(A[n]),'sha256':sha(A[n])} for n in sorted(A)]
    manifest_B=[{'path':n,'size':len(B[n]),'sha256':sha(B[n])} for n in sorted(B)]
    manifest_hash_A=sha(json.dumps(manifest_A,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    manifest_hash_B=sha(json.dumps(manifest_B,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    cat=collections.Counter('signature-data' if n.startswith('META-INF/') else 'resource-file' if n.startswith('res/') else n for n in changed)
    groups={}
    for prefix,label in [('lib/','native_libs'),('assets/','assets'),('res/','res_files')]:
        names=sorted(n for n in set(A)|set(B) if n.startswith(prefix))
        groups[label]={'original':sum(n in A for n in names),'v10_7':sum(n in B for n in names),'byte_identical_common':sum(n in A and n in B and A[n]==B[n] for n in names),'changed_common':sum(n in A and n in B and A[n]!=B[n] for n in names),'removed':sum(n in A and n not in B for n in names),'added':sum(n in B and n not in A for n in names)}
    dA=A['classes.dex']; dB=B['classes.dex']; dV=V['classes.dex']; d2A=A.get('classes2.dex'); d2B=B.get('classes2.dex')
    certA=signer_fingerprint(A,'ORIGINAL'); certB=signer_fingerprint(B,'V10.7')
    if certA != EXPECTED_XIAOMI_CERT: raise SystemExit('ORIGINAL_SIGNER_CERT_MISMATCH '+certA)
    if certB != EXPECTED_V107_CERT: raise SystemExit('V10_7_SIGNER_CERT_MISMATCH '+certB)
    sA=dex_strings(dA); sB=dex_strings(dB)
    sa,sb=set(sA),set(sB)
    result={
      'sha256':{'original':hsA,'v10_7':hsB,'v8':hsV},
      'zip_entries':{'original':len(A),'v10_7':len(B),'added':len(added),'removed':len(removed),'common_changed':len(changed),'changed_categories':dict(cat),
       'original_manifest_sha256':manifest_hash_A,'v10_7_manifest_sha256':manifest_hash_B},
      'entry_manifests':{'original':manifest_A,'v10_7':manifest_B},
      'entry_delta':{
       'added_paths':added,'removed_paths':removed,
       'changed_common':[{'path':n,'original_size':len(A[n]),'v10_7_size':len(B[n]),'original_sha256':sha(A[n]),'v10_7_sha256':sha(B[n])} for n in changed],
       'changed_categories':dict(cat),
       'added_sample':added[:80],'removed_sample':removed[:80],'changed_non_resource':[n for n in changed if not n.startswith('res/')][:100]},
      'payload_identity':{
       'AndroidManifest.xml_identical':A.get('AndroidManifest.xml')==B.get('AndroidManifest.xml'),
       'classes2.dex_identical':d2A is not None and d2A==d2B,
       'assets_identical':groups['assets']['removed']==0 and groups['assets']['added']==0 and groups['assets']['changed_common']==0,
       'native_libraries_identical':groups['native_libs']['removed']==0 and groups['native_libs']['added']==0 and groups['native_libs']['changed_common']==0,
       'resources_arsc_identical':A.get('resources.arsc')==B.get('resources.arsc'),
       'classes.dex_identical':dA==dB,
       'classes.dex_v10_7_exact_v8':dB==dV,
      },
      'groups':groups,
      'dex':{
       'original_bytes':len(dA),'v10_7_bytes':len(dB),'original_strings':len(sA),'v10_7_strings':len(sB),
       'strings_removed':sorted(sa-sb),'strings_added':sorted(sb-sa),
       'v10_7_exact_v8':dB==dV,
       'bytes_original':len(dA),'bytes_v10_7':len(dB),'bytes_v8':len(dV),
       'original_sha1_signature_valid':hashlib.sha1(dA[32:]).digest()==dA[12:32],
       'v10_7_sha1_signature_valid':hashlib.sha1(dB[32:]).digest()==dB[12:32],
       'original_adler32_valid':zlib.adler32(dA[12:])&0xffffffff==struct.unpack_from('<I',dA,8)[0],
       'v10_7_adler32_valid':zlib.adler32(dB[12:])&0xffffffff==struct.unpack_from('<I',dB,8)[0],
      },
      'resource_safety':{
       'resource_table_original_bytes':len(A.get('resources.arsc',b'')),
       'resource_table_v10_7_bytes':len(B.get('resources.arsc',b'')),
       'provider_xml_present': 'res/xml/appupgrade_provider_paths.xml' in B,
       'provider_xml_size':len(B.get('res/xml/appupgrade_provider_paths.xml',b'')),
       'original_res_entries':sum(n.startswith('res/') for n in A),
       'v10_7_res_entries':sum(n.startswith('res/') for n in B),
      },
      'critical_risk':{
       'original_signing_certificate_sha256':certA,
       'v10_7_signing_certificate_sha256':certB,
       'same_signing_certificate':certA==certB,
       'server_auth_may_reject_repacked_signature':True,
       'runtime_functionality_confirmed_by_local_device':False,
      }
    }
    if 'res/xml/appupgrade_provider_paths.xml' in A and 'res/xml/appupgrade_provider_paths.xml' in B:
        result['resource_safety']['provider_xml_byte_identical']=A['res/xml/appupgrade_provider_paths.xml']==B['res/xml/appupgrade_provider_paths.xml']
    with open(out,'w',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print('LOCAL_FORENSIC=PASS')
    print(f"ORIGINAL_SHA256={hsA}")
    print(f"V10_7_SHA256={hsB}")
    print(f"V8_SHA256={hsV}")
    print(f"ZIP_ENTRIES original={len(A)} v10.7={len(B)} added={len(added)} removed={len(removed)} changed_common={len(changed)}")
    print('MANIFEST_IDENTICAL='+str(result['payload_identity']['AndroidManifest.xml_identical']))
    print('CLASSES2_IDENTICAL='+str(result['payload_identity']['classes2.dex_identical']))
    print('V10_7_CLASSES_DEX_EXACT_V8='+str(result['dex']['v10_7_exact_v8']))
    print('SIGNER_CERTIFICATES='+certA+' -> '+certB)
    print('ASSETS_IDENTICAL='+str(result['payload_identity']['assets_identical']))
    print('NATIVE_LIBS_IDENTICAL='+str(result['payload_identity']['native_libraries_identical']))
    print('DEX_STRINGS_REMOVED='+repr(result['dex']['strings_removed']))
    print('DEX_STRINGS_ADDED='+repr(result['dex']['strings_added']))
    print('DEX_CHECKSUMS='+str(result['dex']['original_sha1_signature_valid'] and result['dex']['v10_7_sha1_signature_valid'] and result['dex']['original_adler32_valid'] and result['dex']['v10_7_adler32_valid']))
    print('PROVIDER_XML_PRESENT='+str(result['resource_safety']['provider_xml_present']))
    print('SIGNING_CERTIFICATE_CHANGED=True')
    print('RESOURCE_PATHS_REBUILT='+str(len(removed)))
    print('REPORT='+out)
if __name__=='__main__':
    if len(sys.argv)!=5: raise SystemExit('usage: v13_forensic.py original.apk v10.7.apk v8.apk report.json')
    main(*sys.argv[1:])
