#!/usr/bin/env python3
"""Regression tests for V17.01 Smali string decoding/encoding and audit paths."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from v17_01_smali_strings import decode_smali_literal, encode_smali_literal
from v13_localize_smali import localize
from v13_compare_smali import normalize_pair


def q(body: str) -> str:
    return '"' + body + '"'


def main() -> None:
    # Exact literal that caused the V17 build to stop: Smali uses backslash-apostrophe,
    # which is not a valid JSON escape.
    problem_literal = q("Couldn" + "\\" + "'t find a double value")
    assert decode_smali_literal(problem_literal) == "Couldn't find a double value"

    # Escapes used in Smali string literals.
    assert decode_smali_literal(q("apostrophe: " + "\\" + "'")) == "apostrophe: '"
    assert decode_smali_literal(q('double: ' + "\\" + '"')) == 'double: "'
    assert decode_smali_literal(q("slash: " + "\\\\")) == "slash: \\"
    assert decode_smali_literal(q("line\\nnext\\r\\tend")) == "line\nnext\r\tend"
    assert decode_smali_literal(q("CJK: \\u4e2d\\u6587")) == "CJK: 中文"
    assert decode_smali_literal(q("emoji: \\uD83D\\uDE00")) == "emoji: 😀"
    assert decode_smali_literal(q("controls: \\b\\f")) == "controls: \b\f"

    values = [
        "plain ASCII",
        "Couldn't find a double value",
        'quote " and apostrophe ' + "'" + " and backslash \\" + "\\",
        "line one\nline two\r\ntab\there",
        "Русский интерфейс — 中文",
        "emoji 😀",
        "control\b\f\x01",
    ]
    for value in values:
        encoded = encode_smali_literal(value)
        assert encoded[0] == encoded[-1] == '"', (value, encoded)
        assert decode_smali_literal(encoded) == value, (value, encoded, decode_smali_literal(encoded))

    # Fail closed on malformed quoting/escapes rather than silently rewriting them.
    invalid_values = [
        "not quoted",
        q("bad \\q escape"),
        q("short \\u12"),
        q("trailing \\"),
        '"unescaped\ncontrol"',
    ]
    for invalid in invalid_values:
        try:
            decode_smali_literal(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid Smali literal unexpectedly accepted: {invalid!r}")

    # Regression coverage for both actual localization and the DEX round-trip comparator.
    with tempfile.TemporaryDirectory(prefix="v17-01-smali-codec-") as td:
        base = Path(td)
        root = base / "smali"
        root.mkdir()
        source_literal = q("Couldn" + "\\" + "'t find a double value")
        source = (
            ".class public LExample;\n"
            ".super Ljava/lang/Object;\n"
            ".method public test()V\n"
            "    .locals 1\n"
            f"    const-string v0, {source_literal}\n"
            '    const-string v0, "第二行"\n'
            "    return-void\n"
            ".end method\n"
        )
        (root / "Example.smali").write_text(source, encoding="utf-8")
        mapping = base / "translations.json"
        audit = base / "audit.json"
        mapping.write_text(json.dumps({"schema": 1, "translations": [
            {"source": "第二行", "target": "Вторая строка"}
        ]}, ensure_ascii=False), encoding="utf-8")
        report = localize(root, mapping, audit)
        result = (root / "Example.smali").read_text(encoding="utf-8")
        assert report["status"] == "PASS"
        assert source_literal in result
        assert encode_smali_literal("Вторая строка") in result

        translated = source.replace('"第二行"', encode_smali_literal("Вторая строка"))
        ok, message = normalize_pair(
            source,
            translated,
            {"第二行": "Вторая строка"},
            {},
            "Example.smali",
        )
        assert ok, message

        # An unrelated opcode mutation must remain rejected by the comparator.
        unsafe = translated.replace("return-void", "nop\n    return-void")
        ok, message = normalize_pair(source, unsafe, {"第二行": "Вторая строка"}, {}, "Example.smali")
        assert not ok and "line-count" in message, "comparator failed to reject an unrelated code change"

    print("V17_01_SMALI_APOSTROPHE_REGRESSION=PASS")
    print("V17_01_SMALI_ESCAPE_ROUNDTRIPS=PASS")
    print("V17_01_SMALI_MALFORMED_INPUT_FAIL_CLOSED=PASS")
    print("V17_01_LOCALIZER_AND_COMPARATOR_INTEGRATION=PASS")
    print("V17_01_SMALI_CODEC_SELFTEST=PASS")


if __name__ == "__main__":
    main()
