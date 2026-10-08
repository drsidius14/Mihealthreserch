#!/usr/bin/env python3
import hashlib
import json
import struct
import sys
import zipfile

EXPECTED_ORIGINAL_SHA256 = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
EXPECTED_V8_SHA256 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'


def entries(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1024 * 1024), b''):
            h.update(c)
    return h.hexdigest()


def arsc_sanity(blob):
    if len(blob) < 12:
        raise SystemExit('BAD_RESOURCES_ARSC_TOO_SMALL')
    typ, hs, size = struct.unpack_from('<HHI', blob, 0)
    if typ != 0x0002 or hs < 12 or size != len(blob):
        raise SystemExit(f'BAD_RESOURCES_ARSC_HEADER:type={typ} header={hs} size={size} file={len(blob)}')
    if len(blob) < hs + 8:
        raise SystemExit('BAD_RESOURCES_ARSC_NO_CHILDREN')
    ctyp, chs, csize = struct.unpack_from('<HHI', blob, hs)
    if ctyp != 0x0001 or chs < 28 or csize > len(blob) - hs:
        raise SystemExit('BAD_RESOURCES_ARSC_STRING_POOL')


def main(orig, v8, final, analysis):
    if sha(orig) != EXPECTED_ORIGINAL_SHA256:
        raise SystemExit('ORIGINAL_SHA256_MISMATCH')
    if sha(v8) != EXPECTED_V8_SHA256:
        raise SystemExit('V8_SHA256_MISMATCH')
    A, B, C = entries(orig), entries(v8), entries(final)

    for n in sorted(set(A) | set(C)):
        if n in {'classes.dex', 'resources.arsc'} or n.startswith('META-INF/'):
            continue
        if A.get(n) != C.get(n):
            raise SystemExit('ORIGINAL_PAYLOAD_CHANGED:' + n)
    if C['classes.dex'] != B['classes.dex']:
        raise SystemExit('V10.5_DEX_NOT_V8')
    if C['classes2.dex'] != A['classes2.dex']:
        raise SystemExit('V10.5_DEX2_CHANGED')
    if C['AndroidManifest.xml'] != A['AndroidManifest.xml']:
        raise SystemExit('V10.5_MANIFEST_CHANGED')
    if C['resources.arsc'] == A['resources.arsc']:
        raise SystemExit('RU_RESOURCE_OVERLAY_NOT_APPLIED')
    arsc_sanity(C['resources.arsc'])
    with open(analysis, encoding='utf-8') as f:
        a = json.load(f)
    if a['unexpected_functional_changes']:
        raise SystemExit('ORIGINAL_V8_COMPARE_NOT_CLEAN')
    print('V10.5_FUNCTIONAL_PAYLOAD=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_DEX=V8_BYTE_IDENTICAL')
    print('V10.5_DEX2=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_MANIFEST=ORIGINAL_BYTE_IDENTICAL')
    print('V10.5_ARSC=STRUCTURALLY_VALID')
    print('V10.5_SHA256=' + sha(final))


if __name__ == '__main__':
    main(*sys.argv[1:])
