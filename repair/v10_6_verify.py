#!/usr/bin/env python3
import hashlib
import json
import struct
import sys
import zipfile

EXPECTED_ORIGINAL_SHA256 = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
EXPECTED_V8_SHA256 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'
EXPECTED_TRANSLATIONS = {
    'Последний результат',
    'Анкета оценки риска',
    'Не удалось подключиться к сети, повторите попытку',
}


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def entries(path):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit('ZIP_CRC_FAILURE:' + bad)
        return {n: z.read(n) for n in z.namelist()}


def read_len8(blob, p):
    x = blob[p]
    p += 1
    if x & 0x80:
        x = ((x & 0x7f) << 8) | blob[p]
        p += 1
    return x, p


def read_len16(blob, p):
    x = struct.unpack_from('<H', blob, p)[0]
    p += 2
    if x & 0x8000:
        y = struct.unpack_from('<H', blob, p)[0]
        p += 2
        x = ((x & 0x7fff) << 16) | y
    return x, p


def parse_global_string_pool(blob):
    if len(blob) < 40:
        raise SystemExit('BAD_RESOURCES_ARSC_TOO_SMALL')
    root_type, root_header, root_size = struct.unpack_from('<HHI', blob, 0)
    if root_type != 2 or root_header < 12 or root_size != len(blob):
        raise SystemExit(f'BAD_RESOURCES_ARSC_ROOT:type={root_type} header={root_header} size={root_size} actual={len(blob)}')
    off = root_header
    typ, hs, size = struct.unpack_from('<HHI', blob, off)
    if typ != 1 or hs < 28 or size < hs or size > len(blob) - off:
        raise SystemExit('BAD_RESOURCES_ARSC_GLOBAL_STRING_POOL_HEADER')
    count, style_count, flags, strings_start, styles_start = struct.unpack_from('<5I', blob, off + 8)
    if strings_start < hs or count > (size - hs) // 4:
        raise SystemExit('BAD_RESOURCES_ARSC_STRING_POOL_BOUNDS')
    offsets = struct.unpack_from(f'<{count}I', blob, off + hs)
    utf8 = bool(flags & 0x100)
    strings = []
    for rel in offsets:
        p = off + strings_start + rel
        if p >= off + size:
            raise SystemExit('BAD_RESOURCES_ARSC_STRING_OFFSET')
        if utf8:
            _, p = read_len8(blob, p)  # UTF-16 code-unit length
            byte_len, p = read_len8(blob, p)
            end = p + byte_len
            if end >= off + size or blob[end] != 0:
                raise SystemExit('BAD_RESOURCES_ARSC_UTF8_STRING_TRUNCATED')
            strings.append(blob[p:end].decode('utf-8', 'replace'))
        else:
            unit_len, p = read_len16(blob, p)
            end = p + unit_len * 2
            if end + 2 > off + size or blob[end:end + 2] != b'\0\0':
                raise SystemExit('BAD_RESOURCES_ARSC_UTF16_STRING_TRUNCATED')
            strings.append(blob[p:end].decode('utf-16-le', 'surrogatepass'))
    return strings


def main(original, v8, final, analysis):
    if sha(original) != EXPECTED_ORIGINAL_SHA256:
        raise SystemExit('ORIGINAL_SHA256_MISMATCH')
    if sha(v8) != EXPECTED_V8_SHA256:
        raise SystemExit('V8_SHA256_MISMATCH')
    A, B, C = entries(original), entries(v8), entries(final)

    for name in sorted(set(A) | set(C)):
        if name in {'classes.dex', 'resources.arsc'} or name.startswith('META-INF/'):
            continue
        if A.get(name) != C.get(name):
            raise SystemExit('ORIGINAL_PAYLOAD_CHANGED:' + name)
    if C.get('classes.dex') != B.get('classes.dex'):
        raise SystemExit('V10.6_CLASSES_DEX_NOT_EXACT_V8')
    if C.get('classes2.dex') != A.get('classes2.dex'):
        raise SystemExit('V10.6_CLASSES2_DEX_CHANGED')
    if C.get('AndroidManifest.xml') != A.get('AndroidManifest.xml'):
        raise SystemExit('V10.6_MANIFEST_CHANGED')
    if C.get('resources.arsc') == A.get('resources.arsc'):
        raise SystemExit('RU_RESOURCE_OVERLAY_NOT_APPLIED')
    pool = parse_global_string_pool(C['resources.arsc'])
    missing = sorted(EXPECTED_TRANSLATIONS - set(pool))
    if missing:
        raise SystemExit('RU_TRANSLATIONS_MISSING_FROM_COMPILED_RESOURCE_POOL:' + ' | '.join(missing))

    with open(analysis, encoding='utf-8') as f:
        a = json.load(f)
    if a.get('unexpected_functional_changes'):
        raise SystemExit('ORIGINAL_V8_COMPARE_NOT_CLEAN')
    if a.get('original_sha256') != EXPECTED_ORIGINAL_SHA256 or a.get('v8_sha256') != EXPECTED_V8_SHA256:
        raise SystemExit('ANALYSIS_SOURCE_HASHES_MISMATCH')

    print('V10.6_FUNCTIONAL_PAYLOAD=ORIGINAL_BYTE_IDENTICAL')
    print('V10.6_CLASSES_DEX=V8_BYTE_IDENTICAL')
    print('V10.6_CLASSES2_DEX=ORIGINAL_BYTE_IDENTICAL')
    print('V10.6_MANIFEST=ORIGINAL_BYTE_IDENTICAL')
    print('V10.6_ARSC=STRUCTURALLY_VALID')
    print('V10.6_RUSSIAN_STRINGS=PASS')
    print('V10.6_SHA256=' + sha(final))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: v10_6_verify.py original.apk v8.apk final.apk analysis.json')
    main(*sys.argv[1:])
