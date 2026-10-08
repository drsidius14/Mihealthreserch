#!/usr/bin/env python3
import hashlib, os, shutil, struct, sys, tempfile, zipfile, zlib

TARGET = "Исслед. АД"
DUMMY = "获取评价列表:开始时间: "
EXPECTED_BAD_INDEX = 42753
EXPECTED_INSERT_INDEX = 42577


def uleb(data, off):
    value = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        value |= (b & 0x7f) << shift
        if b < 0x80:
            return value, off
        shift += 7


def mutf8_decode(raw):
    chars = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b < 0x80:
            chars.append(chr(b))
            i += 1
        elif b < 0xe0:
            chars.append(chr(((b & 0x1f) << 6) | (raw[i + 1] & 0x3f)))
            i += 2
        else:
            chars.append(chr(((b & 0x0f) << 12) | ((raw[i + 1] & 0x3f) << 6) | (raw[i + 2] & 0x3f)))
            i += 3
    return ''.join(chars).encode('utf-16le', 'surrogatepass').decode('utf-16le', 'surrogatepass')


def read_string(data, off):
    _, p = uleb(data, off)
    q = data.index(b'\x00', p)
    return mutf8_decode(data[p:q])


def mutf8_encode(s):
    # Encode UTF-16 code units as DEX modified UTF-8.
    raw = s.encode('utf-16le', 'surrogatepass')
    out = bytearray()
    for i in range(0, len(raw), 2):
        u = raw[i] | (raw[i + 1] << 8)
        if 0x0001 <= u <= 0x007f:
            out.append(u)
        elif u == 0:
            out.extend((0xc0, 0x80))
        elif u <= 0x07ff:
            out.extend((0xc0 | (u >> 6), 0x80 | (u & 0x3f)))
        else:
            out.extend((0xe0 | (u >> 12), 0x80 | ((u >> 6) & 0x3f), 0x80 | (u & 0x3f)))
    out.append(0)
    # utf16_size is the number of UTF-16 code units, not UTF-8 bytes.
    units = len(raw) // 2
    n = units
    leb = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            leb.append(b | 0x80)
        else:
            leb.append(b)
            break
    return bytes(leb) + bytes(out)


def dex_fix(dex):
    if not dex.startswith(b'dex\n'):
        raise RuntimeError('classes.dex is not a DEX file')
    string_count, string_off = struct.unpack_from('<II', dex, 56)
    ids = list(struct.unpack_from(f'<{string_count}I', dex, string_off))
    strings = [read_string(dex, off) for off in ids]

    if TARGET not in strings:
        raise RuntimeError('Target Russian string not found; refusing blind modification')
    target_idx = strings.index(TARGET)
    if target_idx != EXPECTED_BAD_INDEX:
        raise RuntimeError(f'Unexpected target index {target_idx}; expected {EXPECTED_BAD_INDEX}')

    # DEX string_ids must be sorted by modified-UTF-8 string ordering. For this APK,
    # the correct slot is immediately before the ellipsis at 42577.
    insertion = next(i for i, s in enumerate(strings) if s > TARGET)
    if insertion != EXPECTED_INSERT_INDEX or strings[insertion] != '…':
        raise RuntimeError(f'Unexpected insertion point {insertion}: {strings[insertion]!r}')

    # Keep all string indices stable. Redirect the correct slot to the existing Russian
    # string data, and replace the old out-of-order slot with a harmless sorted dummy.
    out = bytearray(dex)
    target_data_off = ids[target_idx]
    dummy_data_off = len(out)
    out += mutf8_encode(DUMMY)
    struct.pack_into('<I', out, string_off + insertion * 4, target_data_off)
    struct.pack_into('<I', out, string_off + target_idx * 4, dummy_data_off)

    # Known candidate has exactly one const-string (21c) reference to index 42753.
    needle = bytes((0x1a, target_idx & 0xff, (target_idx >> 8) & 0xff))
    hits = [i for i in range(len(out) - 2) if out[i:i+3] == needle]
    if len(hits) != 1:
        raise RuntimeError(f'Expected one const-string reference to {target_idx}; found {len(hits)}')
    ref = hits[0]
    struct.pack_into('<H', out, ref + 1, insertion)

    struct.pack_into('<I', out, 32, len(out))
    data_off = struct.unpack_from('<I', out, 108)[0]
    struct.pack_into('<I', out, 104, len(out) - data_off)
    out[12:32] = hashlib.sha1(out[32:]).digest()
    struct.pack_into('<I', out, 8, zlib.adler32(out[12:]) & 0xffffffff)

    # Full verification.
    ids2 = struct.unpack_from(f'<{string_count}I', out, string_off)
    strings2 = [read_string(out, off) for off in ids2]
    if any(strings2[i] > strings2[i + 1] for i in range(len(strings2) - 1)):
        raise RuntimeError('STRING_IDS_ORDER=FAIL')
    if strings2[insertion] != TARGET or strings2[target_idx] != DUMMY:
        raise RuntimeError('Patched string table does not match expected result')
    if out[12:32] != hashlib.sha1(out[32:]).digest():
        raise RuntimeError('DEX SHA-1 verification failed')
    if struct.unpack_from('<I', out, 8)[0] != (zlib.adler32(out[12:]) & 0xffffffff):
        raise RuntimeError('DEX Adler32 verification failed')
    print(f'DEX_REPAIR=PASS target_old_index={target_idx} target_new_index={insertion} const_string_ref={ref}')
    return bytes(out)


def main(apk):
    with zipfile.ZipFile(apk, 'r') as zin:
        bad = zin.testzip()
        if bad:
            raise RuntimeError(f'Input APK ZIP is corrupt: {bad}')
        dex = zin.read('classes.dex')
        repaired = dex_fix(dex)
        fd, tmp = tempfile.mkstemp(suffix='.apk', dir=os.path.dirname(apk))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, 'w') as zout:
                for info in zin.infolist():
                    if info.filename == 'classes.dex':
                        zout.writestr(info, repaired)
                    elif info.filename.startswith('META-INF/') and info.filename.upper().endswith(('.MF', '.SF', '.RSA', '.DSA')):
                        continue
                    else:
                        zout.writestr(info, zin.read(info.filename))
            shutil.move(tmp, apk)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    with zipfile.ZipFile(apk, 'r') as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f'Repaired APK ZIP is corrupt: {bad}')
    print('APK_DEX_REPAIR=PASS')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: repair_dex.py <apk>')
    main(sys.argv[1])
