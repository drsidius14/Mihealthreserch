#!/usr/bin/env python3
"""Combine Apktool's compiled resource table with the original APK payload."""
from __future__ import annotations
import re
import sys
import zipfile
from pathlib import Path

RESOURCE_ID = re.compile(r"^\s*resource\s+(0x[0-9a-fA-F]+)\s+(.+?)\s*$", re.M)
FILE_REF = re.compile(r"^\s*(?:\([^)]*\)\s*)?\(file\)\s+(res/\S+?)\s+type=", re.M)

def signature_entry(name):
    if not name.upper().startswith("META-INF/"):
        return False
    base = name.rsplit("/", 1)[-1].upper()
    return (base == "MANIFEST.MF" or base.startswith("SIG-") or
            base.endswith((".SF", ".RSA", ".DSA", ".EC", ".SIG")))

def resource_id_map(dump_path):
    text = Path(dump_path).read_text(encoding="utf-8", errors="replace")
    pairs = {
        (resource_id.lower(), re.sub(r"\s+PUBLIC$", "", name.strip()))
        for resource_id, name in RESOURCE_ID.findall(text)
    }
    if not pairs:
        raise SystemExit("RESOURCE_TABLE_ID_MAP_PARSE_EMPTY:" + str(dump_path))
    return pairs

def referenced_files(dump_path):
    text = Path(dump_path).read_text(encoding="utf-8", errors="replace")
    current_id = None
    refs = set()
    for line in text.splitlines():
        id_match = RESOURCE_ID.match(line)
        if id_match:
            current_id = id_match.group(1).lower()
            continue
        file_match = FILE_REF.match(line)
        if file_match:
            if not current_id:
                raise SystemExit("RESOURCE_FILE_REFERENCE_WITHOUT_ID:" + line.strip())
            refs.add((current_id, file_match.group(1)))
    if not refs:
        raise SystemExit("RESOURCE_TABLE_FILE_REFERENCE_PARSE_EMPTY:" + str(dump_path))
    return refs

def main(original_path, rebuilt_path, original_dump, rebuilt_dump, output_path):
    original_path, rebuilt_path, output_path = map(Path, (original_path, rebuilt_path, output_path))
    old_ids = resource_id_map(original_dump)
    new_ids = resource_id_map(rebuilt_dump)
    if old_ids != new_ids:
        raise SystemExit("RESOURCE_ID_MAP_CHANGED:" + repr({
            "removed": sorted(old_ids-new_ids)[:30],
            "added": sorted(new_ids-old_ids)[:30]
        }))
    old_refs = referenced_files(original_dump)
    new_refs = referenced_files(rebuilt_dump)
    if old_refs != new_refs:
        raise SystemExit("RESOURCE_FILE_REFERENCES_CHANGED:" + repr({
            "removed": sorted(old_refs-new_refs)[:30],
            "added": sorted(new_refs-old_refs)[:30]
        }))
    with zipfile.ZipFile(original_path, "r") as old, zipfile.ZipFile(rebuilt_path, "r") as new:
        old_names = old.namelist()
        new_names = set(new.namelist())
        if old_names.count("resources.arsc") != 1 or "resources.arsc" not in new_names:
            raise SystemExit("RESOURCES_ARSC_MISSING_OR_DUPLICATED")
        old_payloads = {n for n in old_names if n.startswith("res/") and not n.endswith("/")}
        new_payloads = {n for n in new_names if n.startswith("res/") and not n.endswith("/")}
        if old_payloads != new_payloads:
            raise SystemExit("REBUILT_RES_FILE_SET_CHANGED:" + repr({
                "removed": sorted(old_payloads-new_payloads)[:30],
                "added": sorted(new_payloads-old_payloads)[:30]
            }))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as out:
            for info in old.infolist():
                name = info.filename
                if name == "resources.arsc":
                    out.writestr(info, new.read("resources.arsc"))
                elif signature_entry(name):
                    continue
                else:
                    out.writestr(info, old.read(name))
    with zipfile.ZipFile(original_path) as old, zipfile.ZipFile(output_path) as out:
        old_names = set(old.namelist())
        out_names = set(out.namelist())
        if set(old_names) - {n for n in old_names if signature_entry(n)} != out_names:
            raise SystemExit("OUTPUT_ENTRY_SET_CHANGED_OUTSIDE_SIGNATURE_METADATA")
        for name in old_names:
            if name == "resources.arsc" or signature_entry(name):
                continue
            if old.read(name) != out.read(name):
                raise SystemExit("ORIGINAL_PAYLOAD_CHANGED:" + name)
        if old.read("resources.arsc") == out.read("resources.arsc"):
            raise SystemExit("RESOURCE_TABLE_UNCHANGED")
    print("RESOURCE_ONLY_PACKAGE=PASS")
    print("RESOURCE_ONLY_CHANGED_PAYLOAD=resources.arsc")
    print("RESOURCE_ONLY_ORIGINAL_NONRESOURCE_ENTRIES=BYTE_IDENTICAL")
    print("RESOURCE_ONLY_RESOURCE_ID_MAP=UNCHANGED")
    print("RESOURCE_ONLY_FILE_REFERENCES=UNCHANGED")
    print("RESOURCE_ONLY_UNSIGNED_APK=" + str(output_path))

if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit("usage: package_resource_only.py ORIGINAL.apk APKTOOL_REBUILT.apk original.dump rebuilt.dump OUTPUT.apk")
    main(*sys.argv[1:])
