#!/usr/bin/env python3
"""Strict Smali string-literal codec for audited DEX string localization.

Smali quoted strings are not JSON strings. This codec implements the escapes
emitted by smali/baksmali's DexFormattedWriter and accepts the common Java-style
b/f escapes defensively. It deliberately rejects unknown escapes rather than
silently changing bytecode string values.
"""
from __future__ import annotations

_SIMPLE_ESCAPES = {
    "\\": "\\",
    '"': '"',
    "'": "'",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
}
_HEX = frozenset("0123456789abcdefABCDEF")


def _combine_surrogate_pairs(chars: list[str]) -> str:
    r"""Convert valid UTF-16 surrogate pairs from \uXXXX escapes to code points."""
    out: list[str] = []
    i = 0
    while i < len(chars):
        first = ord(chars[i])
        if 0xD800 <= first <= 0xDBFF and i + 1 < len(chars):
            second = ord(chars[i + 1])
            if 0xDC00 <= second <= 0xDFFF:
                out.append(chr(0x10000 + ((first - 0xD800) << 10) + (second - 0xDC00)))
                i += 2
                continue
        out.append(chars[i])
        i += 1
    return "".join(out)


def decode_smali_literal(literal: str) -> str:
    """Decode one complete, double-quoted Smali string literal."""
    if not isinstance(literal, str) or len(literal) < 2 or literal[0] != '"' or literal[-1] != '"':
        raise ValueError(f"invalid quoted Smali string literal: {literal!r}")

    body = literal[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            if ch == '"':
                raise ValueError(f"unescaped double quote in Smali literal: {literal!r}")
            if ord(ch) < 0x20:
                raise ValueError(f"unescaped control character in Smali literal: {literal!r}")
            out.append(ch)
            i += 1
            continue

        if i + 1 >= len(body):
            raise ValueError(f"trailing backslash in Smali literal: {literal!r}")
        escape = body[i + 1]
        if escape in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[escape])
            i += 2
            continue
        if escape == "u":
            digits = body[i + 2:i + 6]
            if len(digits) != 4 or any(c not in _HEX for c in digits):
                raise ValueError(f"invalid Unicode escape in Smali literal: {literal!r}")
            out.append(chr(int(digits, 16)))
            i += 6
            continue
        raise ValueError(f"unsupported Smali escape \\{escape} in {literal!r}")

    return _combine_surrogate_pairs(out)


def encode_smali_literal(value: str) -> str:
    """Encode a Python string using canonical smali/baksmali-compatible escapes."""
    if not isinstance(value, str):
        raise TypeError("Smali string value must be str")
    out = ['"']
    for ch in value:
        cp = ord(ch)
        if ch in ('"', "'", "\\"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif 0x20 <= cp < 0x7F:
            out.append(ch)
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04x}")
        else:
            # Smali's canonical writer emits UTF-16 code units, not a single
            # non-BMP escape. Convert the code point into the corresponding pair.
            cp -= 0x10000
            high = 0xD800 + (cp >> 10)
            low = 0xDC00 + (cp & 0x3FF)
            out.append(f"\\u{high:04x}\\u{low:04x}")
    out.append('"')
    return "".join(out)
