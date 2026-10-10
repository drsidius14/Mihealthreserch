#!/usr/bin/env python3
"""Apply a narrow SHA-1 allowlist patch to two Mi Fitness 3.59.1 checks."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RESEARCH_SHA1 = "86666FD4C4EF99A2EDBA2A50595DC223D0F42B11"
DATA_PROVIDER_OLD_1 = "7B6DC7079C34739CE81159719FB5EB61D2A03225"
DATA_PROVIDER_OLD_2 = "B3D1CE9C2C6403E9685324BCD57F677B13A53174"


def method_span(text: str, header: str) -> tuple[int, int]:
    start = text.find(header)
    if start < 0:
        raise ValueError(f"missing target method: {header}")
    end = text.find(".end method", start)
    if end < 0:
        raise ValueError(f"unterminated target method: {header}")
    return start, end + len(".end method")


def patch_data_provider(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    start, end = method_span(text, ".method static constructor <clinit>()V")
    block = text[start:end]
    original = re.compile(
        r'const-string v0, "' + re.escape(DATA_PROVIDER_OLD_1) + r'"\s+'
        r'const-string v1, "' + re.escape(DATA_PROVIDER_OLD_2) + r'"\s+'
        r'filled-new-array \{v0, v1\}, \[Ljava/lang/String;'
    )
    replacement = (
        f'const-string v0, "{DATA_PROVIDER_OLD_1}"\n\n'
        f'    const-string v1, "{RESEARCH_SHA1}"\n\n'
        f'    const-string v2, "{DATA_PROVIDER_OLD_2}"\n\n'
        '    filled-new-array {v0, v1, v2}, [Ljava/lang/String;'
    )
    if len(original.findall(block)) != 1:
        raise ValueError("DataProviderManager internal signature array differs from expected original")
    if block.count("    .locals 2") != 1:
        raise ValueError("DataProviderManager initializer register count differs from expected original")
    block = original.sub(replacement, block, count=1)
    block = block.replace("    .locals 2", "    .locals 3", 1)
    if block.count(RESEARCH_SHA1) != 1:
        raise ValueError("Research signature was not inserted exactly once in DataProviderManager initializer")
    path.write_text(text[:start] + block + text[end:], encoding="utf-8")


def patch_binder_validator(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    start, end = method_span(text, ".method static constructor <clinit>()V")
    block = text[start:end]
    old = (
        '    new-instance v0, Ljava/util/ArrayList;\n\n'
        '    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V\n\n'
        '    sput-object v0, Lcom/xiaomi/fitness/service/Validator;->sInternalSignatures:Ljava/util/ArrayList;'
    )
    new = (
        '    new-instance v0, Ljava/util/ArrayList;\n\n'
        '    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V\n\n'
        f'    const-string v1, "{RESEARCH_SHA1}"\n\n'
        '    invoke-virtual {v0, v1}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z\n\n'
        '    move-result v1\n\n'
        '    sput-object v0, Lcom/xiaomi/fitness/service/Validator;->sInternalSignatures:Ljava/util/ArrayList;'
    )
    if block.count(old) != 1:
        raise ValueError("Validator signature-list initializer differs from expected original")
    if block.count("    .locals 1") != 1:
        raise ValueError("Validator initializer register count differs from expected original")
    block = block.replace("    .locals 1", "    .locals 2", 1)
    block = block.replace(old, new, 1)
    if block.count(RESEARCH_SHA1) != 1:
        raise ValueError("Research signature was not inserted exactly once in Validator initializer")
    path.write_text(text[:start] + block + text[end:], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    root = args.decoded_root
    provider = root / "smali_classes10/com/xiaomi/fitness/dataprovider/DataProviderManager.smali"
    validator = root / "smali_classes12/com/xiaomi/fitness/service/Validator.smali"
    try:
        if not provider.is_file() or not validator.is_file():
            raise ValueError("APK decoded layout differs from Mi Fitness 3.59.1; no files patched")
        patch_data_provider(provider)
        patch_binder_validator(validator)
        report = (
            "PATCH=APPLIED\n"
            f"RESEARCH_SIGNER_SHA1={RESEARCH_SHA1}\n"
            "TARGET_1=DataProviderManager.sInternalSignatures\n"
            "TARGET_2=Validator.sInternalSignatures\n"
            "SCOPE=two signature allowlists only; no authorization branches removed\n"
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
        print(report, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
