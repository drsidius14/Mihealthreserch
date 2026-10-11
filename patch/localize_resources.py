#!/usr/bin/env python3
"""Create a Russian resource overlay only; never edit Smali, DEX, or the manifest."""
from __future__ import annotations
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
FORMAT = re.compile(
    r"%(?P<arg>\\d+\\$)?(?P<flags>[-+# 0,(<]*)?(?P<width>\\d+)?"
    r"(?:\\.(?P<precision>\\d+))?"
    r"(?:(?P<date>[tT])(?P<dateconv>[HIklMSLNpzZsQBbhAaCYyjmdeRTrDFc])|"
    r"(?P<conv>[bBhHsScCdoxXeEfgGaAn%]))"
)

def _valid_formatter_match(match):
    flags = match.group("flags") or ""
    conv = match.group("conv")
    if match.group("date"):
        return all(flag in "-<" for flag in flags)
    if conv in "sSbBhHcC":
        return all(flag in "-<" for flag in flags)
    if conv == "%":
        return not match.group("arg") and all(flag == "-" for flag in flags) and not match.group("precision")
    if conv == "n":
        return not match.group("arg") and not flags and not match.group("width") and not match.group("precision")
    return True


def tag_name(node):
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""

def resource_key(node):
    tag = tag_name(node)
    if tag == "item" and node.attrib.get("type") == "string":
        tag = "string"
    name = node.attrib.get("name")
    return (tag, name) if name else None

def formatter_tokens(text):
    # Compare formatter tokens rather than their order. The translated sentence
    # may reorder positional arguments but must retain every conversion exactly.
    return Counter(m.group(0) for m in FORMAT.finditer(text or "") if _valid_formatter_match(m))

def source_text(node):
    return "".join(node.itertext())

def load_translations(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not obj:
        raise ValueError("TRANSLATION_MAP_EMPTY_OR_INVALID")
    for key, value in obj.items():
        if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
            raise ValueError(f"TRANSLATION_MAP_INVALID_ENTRY:{key!r}")
    return obj

def collect_sources(decoded):
    found = {}
    for folder in sorted((decoded / "res").glob("values*")):
        if not folder.is_dir():
            continue
        for xml in sorted(folder.glob("*.xml")):
            try:
                root = ET.parse(xml).getroot()
            except ET.ParseError as exc:
                raise RuntimeError(f"RESOURCE_XML_PARSE_ERROR:{xml}:{exc}") from exc
            for node in list(root):
                key = resource_key(node)
                if not key or key[0] != "string":
                    continue
                full_text = source_text(node) + " " + " ".join(
                    str(value) for descendant in node.iter() for value in descendant.attrib.values()
                )
                found.setdefault(key[1], []).append({
                    "file": str(xml.relative_to(decoded)),
                    "node": node,
                    "text": full_text,
                    "attrs": dict(node.attrib),
                })
    return found

def remove_ru_duplicates(decoded, names):
    res = decoded / "res"
    for folder in res.glob("values-ru*"):
        if not folder.is_dir():
            continue
        for xml in folder.glob("*.xml"):
            try:
                tree = ET.parse(xml)
            except ET.ParseError as exc:
                raise RuntimeError(f"EXISTING_RU_XML_PARSE_ERROR:{xml}:{exc}") from exc
            root = tree.getroot()
            changed = False
            for node in list(root):
                key = resource_key(node)
                if key and key[0] == "string" and key[1] in names:
                    root.remove(node)
                    changed = True
            if changed:
                if not list(root):
                    xml.unlink()
                else:
                    tree.write(xml, encoding="utf-8", xml_declaration=True)

def main(decoded_path, translations_path, audit_path):
    decoded = Path(decoded_path)
    translations = load_translations(translations_path)
    sources = collect_sources(decoded)
    missing = sorted(set(translations) - set(sources))
    if missing:
        raise SystemExit("SOURCE_RESOURCE_KEYS_MISSING:" + ",".join(missing[:50]))

    rows = []
    for name, translated in translations.items():
        entries = sources[name]
        # Every locale variant must accept the same format tokens. If the APK has
        # divergent format signatures, fail closed rather than guess which variant wins.
        signatures = {tuple(sorted(formatter_tokens(entry["text"]).items())) for entry in entries}
        target_signature = tuple(sorted(formatter_tokens(translated).items()))
        if len(signatures) != 1 or target_signature not in signatures:
            detail = [{"file": e["file"], "tokens": dict(formatter_tokens(e["text"]))} for e in entries]
            raise SystemExit("FORMAT_SIGNATURE_MISMATCH:" + name + ":" + json.dumps({
                "target": dict(formatter_tokens(translated)), "sources": detail
            }, ensure_ascii=False))
        # Preserve source attributes that affect Android runtime formatting/selection.
        attrs = {}
        for attr in ("formatted", "translatable", "product"):
            if attr in entries[0]["attrs"]:
                attrs[attr] = entries[0]["attrs"][attr]
        rows.append({
            "name": name,
            "value": translated,
            "source_files": sorted({e["file"] for e in entries}),
            "format_tokens": dict(formatter_tokens(translated)),
            "contains_cjk": bool(CJK.search(translated)),
            "attrs": attrs,
        })

    remove_ru_duplicates(decoded, set(translations))
    target_dir = decoded / "res" / "values-ru"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "strings.xml"
    try:
        root = ET.parse(target).getroot() if target.exists() else ET.Element("resources")
    except ET.ParseError as exc:
        raise RuntimeError(f"RU_TARGET_XML_PARSE_ERROR:{target}:{exc}") from exc
    if tag_name(root) != "resources":
        raise RuntimeError("RU_TARGET_ROOT_NOT_RESOURCES")

    # Keep existing non-map entries; translated map keys are replaced by one canonical
    # entry each. ElementTree escapes literal HTML safely for Android string resources.
    for name, translated in translations.items():
        elem = ET.Element("string", {"name": name})
        sources_for_key = sources[name]
        for attr in ("formatted", "translatable", "product"):
            if attr in sources_for_key[0]["attrs"]:
                elem.set(attr, sources_for_key[0]["attrs"][attr])
        elem.text = translated
        root.append(elem)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)

    audit = {
        "mode": "resource-table-only-russian-overlay",
        "translation_map_entries": len(translations),
        "translated_keys_written": len(rows),
        "missing_source_keys": [],
        "format_mismatches": 0,
        "dex_or_manifest_modified_by_localizer": False,
        "overlay": str(target.relative_to(decoded)),
        "entries": rows,
    }
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    Path(audit_path).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESOURCE_ONLY_TRANSLATION_MAP_KEYS=" + str(len(translations)))
    print("RESOURCE_ONLY_TRANSLATED_KEYS_WRITTEN=" + str(len(rows)))
    print("RESOURCE_ONLY_FORMAT_CHECK=PASS")
    print("RESOURCE_ONLY_DEX_MANIFEST_TOUCHED=NO")
    print("RESOURCE_ONLY_OVERLAY=" + str(target))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: localize_resources.py DECODED_APK_DIR translations.json audit.json")
    main(*sys.argv[1:])
