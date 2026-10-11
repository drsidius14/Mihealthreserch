#!/usr/bin/env python3
"""Independent checks that the candidate differs from the original only in resources/signing."""
from __future__ import annotations
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

def signature_entry(name):
    if not name.upper().startswith("META-INF/"):
        return False
    base = name.rsplit("/", 1)[-1].upper()
    return (base == "MANIFEST.MF" or base.startswith("SIG-") or
            base.endswith((".SF", ".RSA", ".DSA", ".EC", ".SIG")))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main(original_path, candidate_path, audit_path, translation_path):
    with zipfile.ZipFile(original_path) as original, zipfile.ZipFile(candidate_path) as candidate:
        a, b = set(original.namelist()), set(candidate.namelist())
        a_payload = {n for n in a if not signature_entry(n)}
        b_payload = {n for n in b if not signature_entry(n)}
        if a_payload != b_payload:
            raise SystemExit("APK_ENTRY_SET_MISMATCH:" + repr({
                "missing": sorted(a_payload-b_payload)[:30],
                "added": sorted(b_payload-a_payload)[:30]
            }))
        changed = []
        for name in sorted(a_payload):
            old, new = original.read(name), candidate.read(name)
            if old != new:
                changed.append(name)
        if changed != ["resources.arsc"]:
            raise SystemExit("UNEXPECTED_CHANGED_APK_PAYLOADS:" + repr(changed))
        if original.read("AndroidManifest.xml") != candidate.read("AndroidManifest.xml"):
            raise SystemExit("MANIFEST_NOT_BYTE_IDENTICAL")
        dex_names = sorted(n for n in a if re.fullmatch(r"classes\d*\.dex", n))
        if not dex_names or any(original.read(n) != candidate.read(n) for n in dex_names):
            raise SystemExit("DEX_NOT_BYTE_IDENTICAL")
        if any(original.read(n) != candidate.read(n) for n in a if n.startswith("res/") and not n.endswith("/")):
            raise SystemExit("RES_FILE_PAYLOAD_CHANGED")
        print("VERIFY_MANIFEST_BYTE_IDENTICAL=PASS")
        print("VERIFY_ALL_DEX_BYTE_IDENTICAL=PASS")
        print("VERIFY_ALL_RES_FILE_PAYLOADS_BYTE_IDENTICAL=PASS")
        print("VERIFY_ONLY_RESOURCES_ARSC_PAYLOAD_CHANGED=PASS")
        print("ORIGINAL_DEX_SHA256=" + json.dumps({n: sha(original.read(n)) for n in dex_names}, sort_keys=True))
        print("CANDIDATE_DEX_SHA256=" + json.dumps({n: sha(candidate.read(n)) for n in dex_names}, sort_keys=True))

    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    translations = json.loads(Path(translation_path).read_text(encoding="utf-8"))
    if audit.get("translated_keys_written") != len(translations):
        raise SystemExit("TRANSLATION_AUDIT_COUNT_MISMATCH")
    if audit.get("dex_or_manifest_modified_by_localizer") is not False:
        raise SystemExit("LOCALIZER_MUTATION_POLICY_MISMATCH")
    print("VERIFY_TRANSLATION_KEYS=" + str(len(translations)))
    print("VERIFY_STATIC_RESOURCE_ONLY_GATE=PASS")
    print("WARNING_SIGNING_CERTIFICATE_CHANGED=YES_TEST_KEY")
    print("WARNING_ORIGINAL_MIFITNESS_TRUST_COMPATIBILITY=NOT_PROVEN")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: verify_resource_only.py ORIGINAL.apk CANDIDATE.apk audit.json translations.json")
    main(*sys.argv[1:])
