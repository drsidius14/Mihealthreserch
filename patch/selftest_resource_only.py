#!/usr/bin/env python3
"""Small isolated tests for overlay creation and placeholder preservation."""
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from localize_resources import main

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "decoded"
    values = root / "res" / "values"
    values.mkdir(parents=True)
    (values / "strings.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><resources>'
        '<string name="app_name">Health</string>'
        '<string name="count">Found %1$d items</string>'
        '<string name="html">Open &lt;a href="https://example.com"&gt;link&lt;/a&gt;</string>'
        '</resources>', encoding="utf-8")
    ru = root / "res" / "values-ru"
    ru.mkdir()
    (ru / "strings.xml").write_text(
        '<resources><string name="app_name">Old name</string><string name="keep">Keep me</string></resources>',
        encoding="utf-8")
    translations = Path(tmp) / "translations.json"
    translations.write_text(json.dumps({
        "app_name": "Исследование здоровья",
        "count": "Найдено элементов: %1$d",
        "html": 'Откройте <a href="https://example.com">ссылку</a>'
    }, ensure_ascii=False), encoding="utf-8")
    audit = Path(tmp) / "audit.json"
    main(str(root), str(translations), str(audit))
    parsed = ET.parse(ru / "strings.xml").getroot()
    by_name = {e.attrib["name"]: "".join(e.itertext()) for e in list(parsed) if e.attrib.get("name")}
    assert by_name["app_name"] == "Исследование здоровья"
    assert by_name["count"] == "Найдено элементов: %1$d"
    assert by_name["keep"] == "Keep me"
    assert by_name["html"] == 'Откройте <a href="https://example.com">ссылку</a>'
    print("RESOURCE_ONLY_SELFTEST=PASS")
