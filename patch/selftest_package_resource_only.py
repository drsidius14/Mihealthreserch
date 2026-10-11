#!/usr/bin/env python3
"""Synthetic package test: only resources.arsc may change."""
import tempfile
import zipfile
from pathlib import Path
from package_resource_only import main

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    original = root / "original.apk"
    rebuilt = root / "rebuilt.apk"
    output = root / "output.apk"
    original_dump = root / "original.dump"
    rebuilt_dump = root / "rebuilt.dump"
    entries = {
        "AndroidManifest.xml": b"manifest-bytes",
        "classes.dex": b"dex-bytes",
        "classes2.dex": b"dex2-bytes",
        "res/drawable/icon.png": b"image-bytes",
        "assets/config.json": b'{"ok":true}',
        "resources.arsc": b"old-table",
        "META-INF/MANIFEST.MF": b"old-signature-manifest",
        "META-INF/TEST.RSA": b"old-signature",
    }
    rebuilt_entries = dict(entries)
    rebuilt_entries["resources.arsc"] = b"new-table-with-ru"
    for path, payloads in ((original, entries), (rebuilt, rebuilt_entries)):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in payloads.items():
                z.writestr(name, data)
    dump = (
        "resource 0x7f010001 com.example:string/app_name\n"
        "resource 0x7f020001 com.example:drawable/icon\n"
        "  () (file) res/drawable/icon.png type=drawable\n"
    )
    original_dump.write_text(dump, encoding="utf-8")
    rebuilt_dump.write_text(dump, encoding="utf-8")
    main(str(original), str(rebuilt), str(original_dump), str(rebuilt_dump), str(output))
    with zipfile.ZipFile(original) as old, zipfile.ZipFile(output) as new:
        assert old.read("AndroidManifest.xml") == new.read("AndroidManifest.xml")
        assert old.read("classes.dex") == new.read("classes.dex")
        assert old.read("res/drawable/icon.png") == new.read("res/drawable/icon.png")
        assert new.read("resources.arsc") == b"new-table-with-ru"
        assert "META-INF/MANIFEST.MF" not in new.namelist()
        assert "META-INF/TEST.RSA" not in new.namelist()
print("RESOURCE_ONLY_PACKAGER_SELFTEST=PASS")
