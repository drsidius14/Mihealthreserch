#!/usr/bin/env python3
import hashlib
import os
import struct
import sys
import tempfile
import zipfile
import zlib

SOURCE_SHA256 = "70965b835b4574e77256b98953ff4374a29e58d74a5a5dfc4709d2dd19c30974"
TARGET = "Исслед. АД"
EXPECTED_BAD_INDEX = 42753
EXPECTED_NEW_INDEX = 42577
EXPECTED_ELLIPSIS_OLD_INDEX = 42577
EXPECTED_ELLIPSIS_NEW_INDEX = 42578


def uleb(data, off):
    value = 0
    shift = 0
    while True:
        if off >= len(data):
            raise RuntimeError("ULEB128 out of range")
        b = data[off]
        off += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, off
        shift += 7
        if shift > 35:
            raise RuntimeError("ULEB128 too long")


def read_mutf8(data, off):
    utf16_size, p = uleb(data, off)
    units = []
    while True:
        if p >= len(data):
            raise RuntimeError("unterminated MUTF-8 string")
        b0 = data[p]
        p += 1
        if b0 == 0:
            break
        if b0 < 0x80:
            units.append(b0)
        elif (b0 & 0xE0) == 0xC0:
            if p >= len(data):
                raise RuntimeError("truncated MUTF-8 string")
            b1 = data[p]
            p += 1
            if not (b1 & 0x80):
                raise RuntimeError("bad MUTF-8 continuation")
            units.append(((b0 & 0x1F) << 6) | (b1 & 0x3F))
        elif (b0 & 0xF0) == 0xE0:
            if p + 1 >= len(data):
                raise RuntimeError("truncated MUTF-8 string")
            b1 = data[p]
            b2 = data[p + 1]
            p += 2
            if not (b1 & 0x80 and b2 & 0x80):
                raise RuntimeError("bad MUTF-8 continuation")
            units.append(((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F))
        else:
            raise RuntimeError(f"unsupported MUTF-8 byte 0x{b0:02x} at 0x{p-1:x}")
    if len(units) != utf16_size:
        raise RuntimeError(f"MUTF-8 utf16_size mismatch {utf16_size} != {len(units)}")
    raw = b"".join(struct.pack("<H", u) for u in units)
    return raw.decode("utf-16-le", "surrogatepass"), p


def utf16_key(value):
    raw = value.encode("utf-16-le", "surrogatepass")
    return tuple(struct.unpack("<%dH" % (len(raw) // 2), raw))


def parse_dex(data):
    if not data.startswith(b"dex\n"):
        raise RuntimeError("not a DEX file")
    file_size = struct.unpack_from("<I", data, 0x20)[0]
    if file_size != len(data):
        raise RuntimeError(f"DEX file_size={file_size}, actual={len(data)}")
    string_count, string_off = struct.unpack_from("<II", data, 0x38)
    ids = list(struct.unpack_from(f"<{string_count}I", data, string_off))
    strings = []
    for off in ids:
        s, _ = read_mutf8(data, off)
        strings.append(s)
    return string_count, string_off, ids, strings


def map_items(data):
    map_off = struct.unpack_from("<I", data, 0x34)[0]
    count = struct.unpack_from("<I", data, map_off)[0]
    result = []
    for i in range(count):
        typ, _unused, size, off = struct.unpack_from("<HHII", data, map_off + 4 + 12 * i)
        result.append((typ, size, off))
    return result


def dex_integrity_ok(data):
    if struct.unpack_from("<I", data, 0x20)[0] != len(data):
        return False
    if data[12:32] != hashlib.sha1(data[32:]).digest():
        return False
    if struct.unpack_from("<I", data, 8)[0] != (zlib.adler32(data[12:]) & 0xFFFFFFFF):
        return False
    return True


def validate_order(data):
    _, _, _, strings = parse_dex(data)
    for i in range(1, len(strings)):
        if utf16_key(strings[i - 1]) >= utf16_key(strings[i]):
            raise RuntimeError(f"STRING_IDS_ORDER=FAIL at {i}")
    return strings


def patch_index_u32(data, off, old, mapping, limit):
    if old >= len(mapping):
        raise RuntimeError(f"string index {old} out of range")
    new = mapping[old]
    if new >= limit:
        raise RuntimeError(f"string index {new} overflows field width")
    if new != old:
        struct.pack_into("<I", data, off, new)
        return 1
    return 0


# Standard DEX instruction widths, in 16-bit code units.
def insn_width(data, p, end):
    if p + 2 > end:
        raise RuntimeError("instruction truncated")
    word = struct.unpack_from("<H", data, p)[0]
    op = word & 0xFF
    if op == 0x00:
        hi = word >> 8
        if hi == 0x00:
            return 1
        if hi == 0x01:
            if p + 4 > end:
                raise RuntimeError("packed-switch payload truncated")
            size = struct.unpack_from("<H", data, p + 2)[0]
            return 4 + 2 * size
        if hi == 0x02:
            if p + 4 > end:
                raise RuntimeError("sparse-switch payload truncated")
            size = struct.unpack_from("<H", data, p + 2)[0]
            return 2 + 4 * size
        if hi == 0x03:
            if p + 8 > end:
                raise RuntimeError("fill-array payload truncated")
            elem_width = struct.unpack_from("<H", data, p + 2)[0]
            size = struct.unpack_from("<I", data, p + 4)[0]
            return 4 + ((elem_width * size + 1) // 2)
        raise RuntimeError(f"unknown payload 0x{word:04x} at 0x{p:x}")
    one = {0x01,0x04,0x07,0x0A,0x0B,0x0C,0x0D,0x0E,0x0F,0x10,0x11,0x12,0x1D,0x1E,0x21,0x27,0x28}
    two = {0x02,0x05,0x08,0x13,0x15,0x16,0x19,0x1A,0x1C,0x1F,0x20,0x22,0x23,0x29,0x2D,0x2E,0x2F,0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x3A,0x3B,0x3C,0x3D}
    three = {0x03,0x06,0x14,0x17,0x1B,0x24,0x25,0x26,0x2A,0x2B,0x2C,0x6E,0x6F,0x70,0x71,0x72,0x74,0x75,0x76,0x77,0x78,0xFC,0xFD}
    if op in one:
        return 1
    if op in two:
        return 2
    if op in three:
        return 3
    if op == 0x18:
        return 5
    if 0x3E <= op <= 0x43 or op == 0x73 or 0x79 <= op <= 0x7A or 0xE3 <= op <= 0xF9:
        raise RuntimeError(f"unused opcode 0x{op:02x} at 0x{p:x}")
    if 0x44 <= op <= 0x6D:
        return 2
    if 0x7B <= op <= 0x8F:
        return 1
    if 0x90 <= op <= 0xAF:
        return 2
    if 0xB0 <= op <= 0xCF:
        return 1
    if 0xD0 <= op <= 0xE2:
        return 2
    if op in (0xFA, 0xFB):
        return 4
    if op in (0xFE, 0xFF):
        return 2
    raise RuntimeError(f"unknown opcode 0x{op:02x} at 0x{p:x}")


def patch_encoded_value(data, p, mapping, counters):
    header = data[p]
    p += 1
    typ = header & 0x1F
    arg = header >> 5
    if typ == 0x17:  # VALUE_STRING: fixed-width little endian index
        size = arg + 1
        if p + size > len(data):
            raise RuntimeError("VALUE_STRING truncated")
        old = int.from_bytes(data[p:p + size], "little")
        if old >= len(mapping):
            raise RuntimeError("VALUE_STRING index out of range")
        new = mapping[old]
        if new >= (1 << (8 * size)):
            raise RuntimeError("VALUE_STRING index width overflow")
        if new != old:
            data[p:p + size] = new.to_bytes(size, "little")
            counters["encoded_string"] += 1
        return p + size
    if typ in (0x1E, 0x1F):
        return p
    if typ == 0x1C:  # ARRAY
        size, p = uleb(data, p)
        for _ in range(size):
            p = patch_encoded_value(data, p, mapping, counters)
        return p
    if typ == 0x1D:  # ANNOTATION -- cannot safely rewrite variable ULEBs here
        # The exact V5 source was independently audited: no affected string index
        # occurs in annotation payloads. Keep them byte-identical.
        raise RuntimeError("unexpected annotation VALUE in static/call-site array")
    widths = {
        0x00: arg + 1, 0x02: arg + 1, 0x03: arg + 1, 0x04: arg + 1,
        0x06: arg + 1, 0x10: arg + 1, 0x11: arg + 1,
        0x15: arg + 1, 0x16: arg + 1, 0x18: arg + 1,
        0x19: arg + 1, 0x1A: arg + 1, 0x1B: arg + 1,
    }
    if typ in widths:
        size = widths[typ]
        if p + size > len(data):
            raise RuntimeError("encoded_value truncated")
        return p + size
    raise RuntimeError(f"unsupported encoded_value type 0x{typ:02x}")


def patch_encoded_array(data, off, mapping, counters):
    size, p = uleb(data, off)
    for _ in range(size):
        p = patch_encoded_value(data, p, mapping, counters)
    return p


def patch_code_item(data, off, mapping, counters):
    insns_size = struct.unpack_from("<I", data, off + 12)[0]
    p = off + 16
    end = p + insns_size * 2
    while p < end:
        word = struct.unpack_from("<H", data, p)[0]
        op = word & 0xFF
        if op == 0x1A:  # const-string, 21c, uint16 string index
            old = struct.unpack_from("<H", data, p + 2)[0]
            new = mapping[old]
            if new > 0xFFFF:
                raise RuntimeError("const-string index overflow")
            if new != old:
                struct.pack_into("<H", data, p + 2, new)
                counters["const_string"] += 1
        elif op == 0x1B:  # const-string/jumbo, 31c, uint32 string index
            old = struct.unpack_from("<I", data, p + 2)[0]
            new = mapping[old]
            if new != old:
                struct.pack_into("<I", data, p + 2, new)
                counters["const_string_jumbo"] += 1
        width = insn_width(data, p, end)
        p += width * 2
    if p != end:
        raise RuntimeError("code_item boundary mismatch")


def patch_all_string_refs(data, mapping):
    sc, _, _, _ = parse_dex(data)
    # type_ids contain type indexes, NOT string indexes; they must never be remapped here.
    counters = {"proto_shorty":0,"field_name":0,"method_name":0,"class_source":0,
                "const_string":0,"const_string_jumbo":0,"encoded_string":0,"static_array":0,"call_site":0}
    proto_count, proto_off = struct.unpack_from("<II", data, 0x48)
    for i in range(proto_count):
        old = struct.unpack_from("<I", data, proto_off + 12 * i)[0]
        counters["proto_shorty"] += patch_index_u32(data, proto_off + 12 * i, old, mapping, sc)
    field_count, field_off = struct.unpack_from("<II", data, 0x50)
    for i in range(field_count):
        pos = field_off + 8 * i + 4
        old = struct.unpack_from("<I", data, pos)[0]
        counters["field_name"] += patch_index_u32(data, pos, old, mapping, sc)
    method_count, method_off = struct.unpack_from("<II", data, 0x58)
    for i in range(method_count):
        pos = method_off + 8 * i + 4
        old = struct.unpack_from("<I", data, pos)[0]
        counters["method_name"] += patch_index_u32(data, pos, old, mapping, sc)
    class_count, class_off = struct.unpack_from("<II", data, 0x60)
    for i in range(class_count):
        pos = class_off + 32 * i + 16  # source_file_idx
        old = struct.unpack_from("<I", data, pos)[0]
        if old != 0xFFFFFFFF:
            counters["class_source"] += patch_index_u32(data, pos, old, mapping, sc)

    # Exact V5 audit established that no affected indices occur in debug_info or
    # annotation structures, so they remain byte-identical. Only code and the
    # encoded-array structures need rewriting below.
    for i in range(class_count):
        base = class_off + 32 * i
        class_data_off = struct.unpack_from("<I", data, base + 24)[0]
        static_values_off = struct.unpack_from("<I", data, base + 28)[0]
        if static_values_off:
            patch_encoded_array(data, static_values_off, mapping, counters)
            counters["static_array"] += 1
        if not class_data_off:
            continue
        p = class_data_off
        static_fields, p = uleb(data, p)
        instance_fields, p = uleb(data, p)
        direct_methods, p = uleb(data, p)
        virtual_methods, p = uleb(data, p)
        for _ in range(static_fields + instance_fields):
            _, p = uleb(data, p)
            _, p = uleb(data, p)
        for count in (direct_methods, virtual_methods):
            for _ in range(count):
                _, p = uleb(data, p)  # method_idx_diff
                _, p = uleb(data, p)  # access_flags
                code_off, p = uleb(data, p)
                if code_off:
                    patch_code_item(data, code_off, mapping, counters)

    for typ, size, off in map_items(data):
        if typ == 0x0007:  # call_site_id_item
            for i in range(size):
                array_off = struct.unpack_from("<I", data, off + 4 * i)[0]
                if array_off:
                    patch_encoded_array(data, array_off, mapping, counters)
                    counters["call_site"] += 1
    return counters


def rebuild_dex(data):
    sc, string_off, ids, strings = parse_dex(data)
    if strings.count(TARGET) != 1:
        raise RuntimeError("target string multiplicity is not 1")
    old_target = strings.index(TARGET)
    if old_target != EXPECTED_BAD_INDEX:
        raise RuntimeError(f"unexpected target index {old_target}")
    if strings[EXPECTED_ELLIPSIS_OLD_INDEX] != "…":
        raise RuntimeError("expected ellipsis at old index 42577")
    order = sorted(range(sc), key=lambda i: utf16_key(strings[i]))
    mapping = [0] * sc
    for new_idx, old_idx in enumerate(order):
        mapping[old_idx] = new_idx
    if mapping[old_target] != EXPECTED_NEW_INDEX:
        raise RuntimeError(f"unexpected repaired target index {mapping[old_target]}")
    if mapping[EXPECTED_ELLIPSIS_OLD_INDEX] != EXPECTED_ELLIPSIS_NEW_INDEX:
        raise RuntimeError("ellipsis mapping changed unexpectedly")

    counters = patch_all_string_refs(data, mapping)
    for new_idx, old_idx in enumerate(order):
        struct.pack_into("<I", data, string_off + 4 * new_idx, ids[old_idx])

    # DEX digest order matters: SHA-1 first, Adler-32 over bytes 12..end second.
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into("<I", data, 8, zlib.adler32(data[12:]) & 0xFFFFFFFF)
    if not dex_integrity_ok(data):
        raise RuntimeError("repaired DEX integrity check failed")
    new_strings = validate_order(data)
    if new_strings[EXPECTED_NEW_INDEX] != TARGET:
        raise RuntimeError("target not at repaired index")
    if new_strings[EXPECTED_ELLIPSIS_NEW_INDEX] != "…":
        raise RuntimeError("ellipsis reference was not preserved")
    if sorted(map(utf16_key, new_strings)) != sorted(map(utf16_key, strings)):
        raise RuntimeError("string multiset changed")
    return counters


def repair_apk(apk):
    with zipfile.ZipFile(apk, "r") as zin:
        if zin.testzip() is not None:
            raise RuntimeError("input APK ZIP is corrupt")
        source_sha = hashlib.sha256(open(apk, "rb").read()).hexdigest()
        if source_sha != SOURCE_SHA256:
            raise RuntimeError(f"wrong V5 source SHA-256: {source_sha}")
        dex = bytearray(zin.read("classes.dex"))
        counts = rebuild_dex(dex)
        fd, tmp = tempfile.mkstemp(prefix="v8-repaired-", suffix=".apk", dir=os.path.dirname(apk))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w") as zout:
                for info in zin.infolist():
                    name = info.filename
                    if name == "classes.dex":
                        zi = zipfile.ZipInfo(name, date_time=info.date_time)
                        zi.compress_type = zipfile.ZIP_STORED
                        zi.external_attr = info.external_attr
                        zout.writestr(zi, bytes(dex))
                    elif name.startswith("META-INF/") and name.upper().endswith((".MF", ".SF", ".RSA", ".DSA")):
                        continue
                    else:
                        zout.writestr(info, zin.read(name))
            os.replace(tmp, apk)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    with zipfile.ZipFile(apk, "r") as z:
        if z.testzip() is not None:
            raise RuntimeError("repaired APK ZIP is corrupt")
    print("DEX_REPAIR=PASS")
    print(f"TARGET_INDEX={EXPECTED_BAD_INDEX}->{EXPECTED_NEW_INDEX}")
    print(f"ELLIPSIS_INDEX={EXPECTED_ELLIPSIS_OLD_INDEX}->{EXPECTED_ELLIPSIS_NEW_INDEX}")
    print("REF_COUNTS=" + ",".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: repair_v8.py <apk>")
    repair_apk(sys.argv[1])
