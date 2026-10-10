#!/usr/bin/env python3
"""Verify that both allowlist changes survived the APK rebuild/decode cycle."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

SHA1 = "86666FD4C4EF99A2EDBA2A50595DC223D0F42B11"


def method_block(text: str, header: str) -> str:
    start = text.find(header)
    if start < 0:
        raise ValueError(f"missing method: {header}")
    end = text.find(".end method", start)
    if end < 0:
        raise ValueError(f"unterminated method: {header}")
    return text[start:end + len(".end method")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        root = args.decoded_root
        provider_file = root / "smali_classes10/com/xiaomi/fitness/dataprovider/DataProviderManager.smali"
        validator_file = root / "smali_classes12/com/xiaomi/fitness/service/Validator.smali"
        provider = method_block(provider_file.read_text(encoding="utf-8"), ".method static constructor <clinit>()V")
        validator = method_block(validator_file.read_text(encoding="utf-8"), ".method static constructor <clinit>()V")
        if SHA1 not in provider:
            raise ValueError("Research SHA-1 absent from rebuilt DataProviderManager initializer")
        if "Arrays;->binarySearch" not in provider_file.read_text(encoding="utf-8"):
            raise ValueError("DataProviderManager binary-search authorization path changed unexpectedly")
        if SHA1 not in validator:
            raise ValueError("Research SHA-1 absent from rebuilt Binder Validator initializer")
        result = (
            "DEX_VALIDATION=PASS\n"
            "DataProviderManager allowlist SHA-1 present after rebuild\n"
            "Validator allowlist SHA-1 present after rebuild\n"
            "Original authorization branches retained\n"
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(result, encoding="utf-8")
        print(result, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
