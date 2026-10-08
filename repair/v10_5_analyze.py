#!/usr/bin/env python3
import hashlib
import json
import struct
import sys
import zipfile
from collections import Counter

ORIGINAL_SHA256 = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
V8_SHA256 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'
ORIGINAL_GIT_BLOB = 'b9c06129674ff283cbddd8ec3df73781d12f2d89'
V8_GIT_BLOB = '6118c187927060a5c9f8092561afdbd5e5c16c28'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path):
    h = hashlib.sha1()
    size = 0
    chunks = []
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            size += len(chunk)
            chunks.append(chunk)
    h.update(f'blob {size}\0'.encode('ascii'))
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def zip_bytes(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def uleb(data, off):
    value = 0
    shift = 0
    while True:
        if off >= len(data):
            raise RuntimeError('ULEB out of range')
        b = data[off]
        off += 1
        value |= (b & 0x7f) << shift
        if b < 0x80:
            return value, off
        shift += 7
        if shift > 35:
            raise RuntimeError('ULEB too long')


def read_mutf8(data, off):
    length, p = uleb(data, off)
    units = []
    while True:
        if p >= len(data):
            raise RuntimeError('MUTF-8 out of range')
        b0 = data[p]
        p += 1
        if b0 == 0:
            break
        if b0 < 0x80:
            units.append(b0)
        elif (b0 & 0xe0) == 0xc0:
            b1 = data[p]
            p += 1
            units.append(((b0 & 0x1f) << 6) | (b1 & 0x3f))
        elif (b0 & 0xf0) == 0xe0:
            b1, b2 = data[p], data[p + 1]
            p += 2
            units.append(((b0 & 0x0f) << 12) | ((b1 & 0x3f) << 6) | (b2 & 0x3f))
        else:
            raise RuntimeError('unsupported MUTF-8 sequence')
    if len(units) != length:
        raise RuntimeError(f'MUTF-8 length mismatch: declared={length} actual={len(units)}')
    raw = b''.join(struct.pack('<H', u) for u in units)
    return raw.decode('utf-16-le', 'surrogatepass'), p


def dex_strings(blob):
    if not blob.startswith(b'dex\n'):
        raise RuntimeError('not a DEX file')
    string_count, string_off = struct.unpack_from('<II', blob, 0x38)
    ids = struct.unpack_from(f'<{string_count}I', blob, string_off)
    return [read_mutf8(blob, off)[0] for off in ids]


def arsc_sanity(blob):
    if len(blob) < 12:
        raise RuntimeError('resources.arsc too small')
    typ, header_size, total_size = struct.unpack_from('<HHI', blob, 0)
    if typ != 0x0002:
        raise RuntimeError(f'resources.arsc bad root type: 0x{typ:04x}')
    if header_size < 12 or total_size != len(blob):
        raise RuntimeError(f'resources.arsc bad root header: header={header_size} size={total_size} file={len(blob)}')
    # The first child must be a global string pool.
    if len(blob) < header_size + 8:
        raise RuntimeError('resources.arsc missing first child')
    ctyp, chs, csize = struct.unpack_from('<HHI', blob, header_size)
    if ctyp != 0x0001 or chs < 28 or csize > len(blob) - header_size:
        raise RuntimeError('resources.arsc global string pool is malformed')


def diff_names(a, b):
    return sorted(n for n in (set(a) | set(b)) if a.get(n) != b.get(n))


def main(original, v8, out):
    oh = sha256_file(original)
    vh = sha256_file(v8)
    og = git_blob_sha1(original)
    vg = git_blob_sha1(v8)
    if oh != ORIGINAL_SHA256 or og != ORIGINAL_GIT_BLOB:
        raise SystemExit(f'ORIGINAL_MISMATCH sha256={oh} git_blob={og}')
    if vh != V8_SHA256 or vg != V8_GIT_BLOB:
        raise SystemExit(f'V8_MISMATCH sha256={vh} git_blob={vg}')

    A, B = zip_bytes(original), zip_bytes(v8)
    changed = diff_names(A, B)
    functional = [n for n in changed if n not in {'classes.dex', 'resources.arsc'} and not n.startswith('META-INF/')]
    if functional:
        raise SystemExit('unexpected functional ZIP diff: ' + ','.join(functional[:20]))
    if A.get('AndroidManifest.xml') != B.get('AndroidManifest.xml'):
        raise SystemExit('AndroidManifest.xml differs')
    if A.get('classes2.dex') != B.get('classes2.dex'):
        raise SystemExit('classes2.dex differs from original')
    for prefix in ('lib/', 'assets/'):
        for name in sorted(set(n for n in A if n.startswith(prefix)) | set(n for n in B if n.startswith(prefix))):
            if A.get(name) != B.get(name):
                raise SystemExit(f'{prefix} differs: {name}')

    od = dex_strings(A['classes.dex'])
    vd = dex_strings(B['classes.dex'])
    delta_removed = list((Counter(od) - Counter(vd)).elements())
    delta_added = list((Counter(vd) - Counter(od)).elements())
    if delta_removed != ['血压健康研究'] or delta_added != ['Исслед. АД']:
        raise SystemExit(f'DEX semantic delta mismatch removed={delta_removed} added={delta_added}')
    arsc_sanity(A['resources.arsc'])
    arsc_sanity(B['resources.arsc'])

    result = {
        'original_sha256': oh,
        'v8_sha256': vh,
        'original_git_blob_sha1': og,
        'v8_git_blob_sha1': vg,
        'changed_zip_entries': changed,
        'unexpected_functional_changes': functional,
        'manifest_identical': True,
        'classes2_identical': True,
        'native_libs_identical': True,
        'assets_identical': True,
        'dex_string_delta_removed': delta_removed,
        'dex_string_delta_added': delta_added,
        'dex_counts': {'original': len(od), 'v8': len(vd)},
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('BIT_COMPARE=PASS')
    print('ORIGINAL_EXACT=PASS')
    print('V8_EXACT=PASS')
    print('ZIP_CHANGED=' + ','.join(changed))
    print('DEX_SEMANTIC_DELTA=血压健康研究->Исслед. АД')


if __name__ == '__main__':
    main(*sys.argv[1:])
