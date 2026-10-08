#!/usr/bin/env python3
"""Verify V10.7 APK identity and closure of compiled resource file paths."""
import hashlib
import re
import sys
import zipfile

EXPECTED_ORIGINAL_SHA256 = "9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc"
EXPECTED_V8_SHA256 = "c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0"
EXPECTED_TRANSLATIONS = {
    "Последний результат",
    "Анкета оценки риска",
    "Не удалось подключиться к сети, повторите попытку",
}
REQUIRED_PROVIDER_XML = "res/xml/appupgrade_provider_paths.xml"
SIGNATURE_SUFFIXES = (".MF", ".SF", ".RSA", ".DSA", ".EC")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def entries(path):
    with zipfile.ZipFile(path, "r") as z:
        bad = z.testzip()
        if bad:
            raise SystemExit("ZIP_CRC_FAILURE:" + bad)
        if len(z.namelist()) != len(set(z.namelist())):
            raise SystemExit("DUPLICATE_ZIP_ENTRY_NAMES")
        return {name: z.read(name) for name in z.namelist()}


def read_len8(blob, p):
    x = blob[p]
    p += 1
    if x & 0x80:
        x = ((x & 0x7f) << 8) | blob[p]
        p += 1
    return x, p


def read_len16(blob, p):
    import struct
    x = struct.unpack_from("<H", blob, p)[0]
    p += 2
    if x & 0x8000:
        y = struct.unpack_from("<H", blob, p)[0]
        p += 2
        x = ((x & 0x7fff) << 16) | y
    return x, p


def parse_global_string_pool(blob):
    import struct
    if len(blob) < 40:
        raise SystemExit("BAD_RESOURCES_ARSC_TOO_SMALL")
    root_type, root_header, root_size = struct.unpack_from("<HHI", blob, 0)
    if root_type != 2 or root_header < 12 or root_size != len(blob):
        raise SystemExit("BAD_RESOURCES_ARSC_ROOT")
    off = root_header
    typ, hs, size = struct.unpack_from("<HHI", blob, off)
    if typ != 1 or hs < 28 or size < hs or size > len(blob) - off:
        raise SystemExit("BAD_RESOURCES_ARSC_GLOBAL_STRING_POOL")
    count, style_count, flags, strings_start, styles_start = struct.unpack_from("<5I", blob, off + 8)
    if strings_start < hs or count > (size - hs) // 4:
        raise SystemExit("BAD_RESOURCES_ARSC_STRING_POOL_BOUNDS")
    offsets = struct.unpack_from(f"<{count}I", blob, off + hs) if count else ()
    utf8 = bool(flags & 0x100)
    values = []
    for rel in offsets:
        p = off + strings_start + rel
        if p >= off + size:
            raise SystemExit("BAD_RESOURCES_ARSC_STRING_OFFSET")
        if utf8:
            _, p = read_len8(blob, p)
            byte_len, p = read_len8(blob, p)
            end = p + byte_len
            if end >= off + size or blob[end] != 0:
                raise SystemExit("BAD_RESOURCES_ARSC_UTF8_STRING_TRUNCATED")
            values.append(blob[p:end].decode("utf-8", "replace"))
        else:
            unit_len, p = read_len16(blob, p)
            end = p + unit_len * 2
            if end + 2 > off + size or blob[end:end + 2] != b"\0\0":
                raise SystemExit("BAD_RESOURCES_ARSC_UTF16_STRING_TRUNCATED")
            values.append(blob[p:end].decode("utf-16-le", "surrogatepass"))
    return values


def main(original, v8, final, resource_dump):
    if sha256(original) != EXPECTED_ORIGINAL_SHA256:
        raise SystemExit("ORIGINAL_SHA256_MISMATCH")
    if sha256(v8) != EXPECTED_V8_SHA256:
        raise SystemExit("V8_SHA256_MISMATCH")
    A, B, C = entries(original), entries(v8), entries(final)

    for name in sorted(set(A) | set(C)):
        if name in {"classes.dex", "resources.arsc"} or name.startswith("res/") or (name.startswith("META-INF/") and name.upper().endswith(SIGNATURE_SUFFIXES)):
            continue
        if A.get(name) != C.get(name):
            raise SystemExit("ORIGINAL_NON_RESOURCE_PAYLOAD_CHANGED:" + name)
    if C.get("classes.dex") != B.get("classes.dex"):
        raise SystemExit("V10.7_CLASSES_DEX_NOT_EXACT_V8")
    if C.get("classes2.dex") != A.get("classes2.dex"):
        raise SystemExit("V10.7_CLASSES2_DEX_CHANGED")
    if C.get("AndroidManifest.xml") != A.get("AndroidManifest.xml"):
        raise SystemExit("V10.7_MANIFEST_CHANGED")
    if REQUIRED_PROVIDER_XML not in C or len(C[REQUIRED_PROVIDER_XML]) < 8:
        raise SystemExit("V10.7_PROVIDER_XML_MISSING_OR_INVALID")
    res_files = {n for n in C if n.startswith("res/") and not n.endswith("/")}
    if len(res_files) < 1000:
        raise SystemExit("V10.7_TOO_FEW_RESOURCE_FILES:" + str(len(res_files)))

    with open(resource_dump, "r", encoding="utf-8", errors="replace") as f:
        dump = f.read()
    referenced_paths = set(re.findall(r"\(file\)\s+(res/\S+?)\s+type=", dump))
    missing_paths = sorted(referenced_paths - set(C))
    if not referenced_paths:
        raise SystemExit("AAPT2_DUMP_CONTAINED_NO_RESOURCE_FILE_PATHS")
    if missing_paths:
        preview = " | ".join(missing_paths[:20])
        raise SystemExit(f"V10.7_RESOURCE_PATHS_MISSING_FROM_APK:{len(missing_paths)}:{preview}")
    if REQUIRED_PROVIDER_XML not in referenced_paths:
        raise SystemExit("V10.7_PROVIDER_XML_NOT_REFERENCED_BY_RESOURCE_TABLE")

    strings = parse_global_string_pool(C["resources.arsc"])
    missing = sorted(EXPECTED_TRANSLATIONS - set(strings))
    if missing:
        raise SystemExit("RU_TRANSLATIONS_MISSING:" + " | ".join(missing))

    print("V10.7_ORIGINAL_NON_RESOURCE_PAYLOAD=PASS")
    print("V10.7_CLASSES_DEX_EXACT_V8=PASS")
    print("V10.7_CLASSES2_DEX_EXACT_ORIGINAL=PASS")
    print("V10.7_MANIFEST_EXACT_ORIGINAL=PASS")
    print("V10.7_PROVIDER_PATHS_XML_PRESENT=PASS")
    print("V10.7_RESOURCE_PATH_CLOSURE=PASS")
    print("V10.7_RESOURCE_FILES=" + str(len(res_files)))
    print("V10.7_RESOURCE_FILE_REFERENCES=" + str(len(referenced_paths)))
    print("V10.7_RUSSIAN_OVERRIDES=PASS")
    print("V10.7_SHA256=" + sha256(final))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: v10_7_verify.py original.apk v8.apk final.apk aapt2-resources-dump.txt")
    main(*sys.argv[1:])
