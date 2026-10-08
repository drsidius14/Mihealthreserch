#!/usr/bin/env python3
"""Package V10.7 with a consistent resources.arsc + compiled res/ directory.

V10.6 replaced resources.arsc from an Apktool rebuild but retained the original
obfuscated res/ ZIP entries. That made the resource table point at paths that
were not present in the APK. V10.7 replaces the whole compiled res/ payload as
well as resources.arsc, while preserving the original manifest, assets, libs,
classes2.dex, and all other non-resource payload; classes.dex comes from exact V8.
"""
import hashlib
import os
import sys
import tempfile
import zipfile

EXPECTED_ORIGINAL = "9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc"
EXPECTED_V8 = "c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0"
SIGNATURE_SUFFIXES = (".MF", ".SF", ".RSA", ".DSA", ".EC")
REQUIRED_PROVIDER_XML = "res/xml/appupgrade_provider_paths.xml"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_old_signature(name):
    return name.startswith("META-INF/") and name.upper().endswith(SIGNATURE_SUFFIXES)


def main(original, v8, compiled, out):
    if sha256(original) != EXPECTED_ORIGINAL:
        raise SystemExit("ORIGINAL_SHA256_MISMATCH")
    if sha256(v8) != EXPECTED_V8:
        raise SystemExit("V8_SHA256_MISMATCH")

    with zipfile.ZipFile(original, "r") as oz, zipfile.ZipFile(v8, "r") as vz, zipfile.ZipFile(compiled, "r") as cz:
        for label, z in (("ORIGINAL", oz), ("V8", vz), ("APKTOOL_COMPILED", cz)):
            bad = z.testzip()
            if bad:
                raise SystemExit(f"{label}_ZIP_CRC_FAILURE:{bad}")
        if "resources.arsc" not in cz.namelist():
            raise SystemExit("APKTOOL_COMPILED_MISSING_RESOURCES_ARSC")
        compiled_res = {}
        for info in cz.infolist():
            if info.filename.startswith("res/") and not info.is_dir():
                if info.filename in compiled_res:
                    raise SystemExit("DUPLICATE_COMPILED_RESOURCE:" + info.filename)
                compiled_res[info.filename] = (info, cz.read(info.filename))
        if len(compiled_res) < 1000:
            raise SystemExit(f"TOO_FEW_COMPILED_RES_FILES:{len(compiled_res)}")
        if REQUIRED_PROVIDER_XML not in compiled_res:
            raise SystemExit("APKTOOL_OUTPUT_MISSING_PROVIDER_XML:" + REQUIRED_PROVIDER_XML)
        provider_blob = compiled_res[REQUIRED_PROVIDER_XML][1]
        if len(provider_blob) < 8:
            raise SystemExit("PROVIDER_XML_EMPTY_OR_TRUNCATED")

        dex = vz.read("classes.dex")
        arsc = cz.read("resources.arsc")
        if not dex.startswith(b"dex\n"):
            raise SystemExit("V8_CLASSES_DEX_INVALID")
        if len(arsc) < 40:
            raise SystemExit("COMPILED_RESOURCES_ARSC_TOO_SMALL")

        output_dir = os.path.dirname(os.path.abspath(out))
        os.makedirs(output_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="v107-", suffix=".apk", dir=output_dir)
        os.close(fd)
        try:
            original_names = oz.namelist()
            if len(original_names) != len(set(original_names)):
                raise SystemExit("DUPLICATE_ORIGINAL_ZIP_ENTRY")
            written = set()
            with zipfile.ZipFile(tmp, "w") as zout:
                # Preserve original non-resource payload byte-for-byte. Drop only
                # stale resource files, the replaced DEX/ARSC, and old signatures.
                for info in oz.infolist():
                    name = info.filename
                    if is_old_signature(name) or name.startswith("res/") or name == "resources.arsc":
                        continue
                    if name in written:
                        raise SystemExit("DUPLICATE_OUTPUT_ZIP_ENTRY:" + name)
                    if name == "classes.dex":
                        payload = dex
                        ni = zipfile.ZipInfo(name, date_time=info.date_time)
                        ni.compress_type = zipfile.ZIP_STORED
                        ni.external_attr = info.external_attr
                        ni.comment = info.comment
                        zout.writestr(ni, payload)
                    else:
                        zout.writestr(info, oz.read(name))
                    written.add(name)
    
                # In case original had no classes.dex entry (not expected), fail closed.
                if "classes.dex" not in written:
                    raise SystemExit("ORIGINAL_APK_MISSING_CLASSES_DEX")
                # New resource table and every compiled resource file must travel together.
                ni = zipfile.ZipInfo("resources.arsc", date_time=(2026, 1, 1, 0, 0, 0))
                ni.compress_type = zipfile.ZIP_STORED
                zout.writestr(ni, arsc)
                written.add("resources.arsc")
                for name, (info, payload) in sorted(compiled_res.items()):
                    if name in written:
                        raise SystemExit("RESOURCE_PATH_COLLISION:" + name)
                    ni = zipfile.ZipInfo(name, date_time=info.date_time)
                    ni.compress_type = info.compress_type
                    ni.external_attr = info.external_attr
                    ni.comment = info.comment
                    zout.writestr(ni, payload)
                    written.add(name)
            os.replace(tmp, out)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    with zipfile.ZipFile(original, "r") as oz, zipfile.ZipFile(v8, "r") as vz, zipfile.ZipFile(out, "r") as final:
        bad = final.testzip()
        if bad:
            raise SystemExit("V10.7_OUTPUT_ZIP_CRC_FAILURE:" + bad)
        names = final.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("V10.7_DUPLICATE_ZIP_ENTRIES")
        if final.read("classes.dex") != vz.read("classes.dex"):
            raise SystemExit("V10.7_CLASSES_DEX_NOT_EXACT_V8")
        if final.read("classes2.dex") != oz.read("classes2.dex"):
            raise SystemExit("V10.7_CLASSES2_DEX_CHANGED")
        if final.read("AndroidManifest.xml") != oz.read("AndroidManifest.xml"):
            raise SystemExit("V10.7_MANIFEST_CHANGED")
        if final.read("res/xml/appupgrade_provider_paths.xml") != provider_blob:
            raise SystemExit("V10.7_PROVIDER_XML_MISMATCH")
        for info in oz.infolist():
            name = info.filename
            if is_old_signature(name) or name.startswith("res/") or name in ("classes.dex", "resources.arsc"):
                continue
            if name not in names or final.read(name) != oz.read(name):
                raise SystemExit("ORIGINAL_NON_RESOURCE_PAYLOAD_CHANGED:" + name)

    print("V10.7_ORIGINAL_NON_RESOURCE_PAYLOAD=PRESERVED")
    print("V10.7_CLASSES_DEX=EXACT_V8")
    print("V10.7_CLASSES2_DEX=EXACT_ORIGINAL")
    print("V10.7_MANIFEST=EXACT_ORIGINAL")
    print("V10.7_RESOURCES_ARSC_AND_RES_FILES=CONSISTENT_SET")
    print("V10.7_PROVIDER_PATHS_XML=PRESENT")
    print("V10.7_COMPILED_RES_FILES=" + str(len(compiled_res)))
    print("V10.7_UNSIGNED_SHA256=" + sha256(out))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: v10_7_package.py original.apk v8.apk apktool-compiled.apk unsigned.apk")
    main(*sys.argv[1:])
