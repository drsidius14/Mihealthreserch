#!/usr/bin/env python3
import hashlib, os, struct, sys, tempfile, zipfile

EXPECTED_ORIGINAL = '9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc'
EXPECTED_V8 = 'c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path, name):
    with zipfile.ZipFile(path) as z:
        return z.read(name)


def check_arsc(blob):
    if len(blob) < 40:
        raise RuntimeError('compiled resources.arsc too small')
    typ, header_size, total_size = struct.unpack_from('<HHI', blob, 0)
    if typ != 2 or header_size < 12 or total_size != len(blob):
        raise RuntimeError(f'compiled resources.arsc invalid root: type={typ} header={header_size} total={total_size} actual={len(blob)}')
    ctyp, chs, csize = struct.unpack_from('<HHI', blob, header_size)
    if ctyp != 1 or chs < 28 or csize < chs or csize > len(blob) - header_size:
        raise RuntimeError('compiled resources.arsc global string pool is malformed')


def main(original, v8, compiled, out):
    if sha(original) != EXPECTED_ORIGINAL:
        raise SystemExit('ORIGINAL_SHA256_MISMATCH_BEFORE_PACKAGE')
    if sha(v8) != EXPECTED_V8:
        raise SystemExit('V8_SHA256_MISMATCH_BEFORE_PACKAGE')
    with zipfile.ZipFile(compiled) as cz:
        bad = cz.testzip()
        if bad:
            raise SystemExit('APKTOOL_OUTPUT_ZIP_CRC_ERROR:' + bad)
        res = cz.read('resources.arsc')
    check_arsc(res)
    dex = read(v8, 'classes.dex')
    if len(dex) < 112 or not dex.startswith(b'dex\n'):
        raise SystemExit('V8_CLASSES_DEX_INVALID')

    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='v106-', suffix='.apk', dir=out_dir)
    os.close(fd)
    try:
        with zipfile.ZipFile(original, 'r') as zin, zipfile.ZipFile(tmp, 'w') as zout:
            seen = set()
            for info in zin.infolist():
                name = info.filename
                if name in seen:
                    raise SystemExit('DUPLICATE_ORIGINAL_ZIP_ENTRY:' + name)
                seen.add(name)
                # Original certificate files are invalid after any APK modification.
                if name.startswith('META-INF/') and name.upper().endswith(('.MF', '.SF', '.RSA', '.DSA', '.EC')):
                    continue
                if name == 'classes.dex':
                    payload = dex
                    new_info = zipfile.ZipInfo(name, date_time=info.date_time)
                    new_info.compress_type = zipfile.ZIP_STORED
                    new_info.external_attr = info.external_attr
                    new_info.comment = info.comment
                    zout.writestr(new_info, payload)
                elif name == 'resources.arsc':
                    new_info = zipfile.ZipInfo(name, date_time=info.date_time)
                    new_info.compress_type = zipfile.ZIP_STORED
                    new_info.external_attr = info.external_attr
                    new_info.comment = info.comment
                    zout.writestr(new_info, res)
                else:
                    zout.writestr(info, zin.read(name))
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit('PACKAGED_APK_ZIP_CRC_ERROR:' + bad)
        if z.read('classes.dex') != dex or z.read('resources.arsc') != res:
            raise SystemExit('PACKAGED_PAYLOAD_RECHECK_FAILED')
    print('V10.6_FUNCTIONAL_BASE=ORIGINAL_BYTE_PRESERVED')
    print('V10.6_CLASSES_DEX=V8_EXACT')
    print('V10.6_RESOURCES=APKTOOL_REBUILT_OVERLAY')
    print('UNSIGNED_SHA256=' + sha(out))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: v10_6_package.py original.apk v8.apk apktool-compiled.apk unsigned.apk')
    main(*sys.argv[1:])
