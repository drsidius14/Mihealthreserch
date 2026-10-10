#!/usr/bin/env python3
"""Prepare the V17.03 GitHub Actions source branch locally; does not access the network."""
from pathlib import Path
import json
import re
import sys

ROOT = Path.cwd()
workflow_src = ROOT / ".github/workflows/v17.yml"
workflow_dst = ROOT / ".github/workflows/v17_03.yml"
dex_file = ROOT / "repair/v13_dex_translations.json"

def fail(message):
    print("V17.03 PREPARE ERROR:", message, file=sys.stderr)
    raise SystemExit(2)

if not workflow_src.is_file():
    fail("Не найден .github/workflows/v17.yml. Запусти команду из корня Mihealthreserch.")
if not dex_file.is_file():
    fail("Не найден repair/v13_dex_translations.json.")

src = workflow_src.read_text(encoding="utf-8")
if workflow_dst.exists():
    fail(".github/workflows/v17_03.yml уже существует — не перезаписываю неизвестные изменения.")

# Version identity: preserve build logic while creating an independent V17.03 workflow.
wf = src.replace("V17.01", "V17.03").replace("V17_01", "V17_03")
wf = wf.replace("v17.01-build", "v17.03-build").replace("v17-build, \"v17.03-build\"", "v17.03-build")
wf = wf.replace("Xiaomi Health Research V17.01", "Xiaomi Health Research V17.03")
wf = wf.replace("v17.01-${{ github.ref }}", "v17.03-${{ github.ref }}")
# Ensure this workflow only responds to the dedicated V17.03 branch (or manual dispatch).
wf = re.sub(
    r'  push:\n    branches: \[[^\n]*\]',
    '  push:\n    branches: [\"v17.03-build\"]',
    wf,
    count=1
)

# The emulator-runner action executes its script through /bin/sh. The test body uses
# Bash-only constructs (pipefail, [[ ]], process substitution), so explicitly invoke Bash.
needle = "          script: |\n            set -euo pipefail\n"
if needle not in wf:
    fail("Не найден ожидаемый блок emulator-runner script; файл workflow изменился. Автопатч отменён.")
wf = wf.replace(
    needle,
    "          script: |\n            bash -euo pipefail <<'V17_03_BASH'\n            set -euo pipefail\n",
    1
)
# Close heredoc before the next workflow step, so all test body runs under Bash.
boundary = "\n      - name: Upload Android runtime diagnostics\n"
if boundary not in wf:
    fail("Не найден конец emulator-runner шага; автопатч отменён.")
wf = wf.replace(boundary, "\n            V17_03_BASH\n\n      - name: Upload Android runtime diagnostics\n", 1)

# Make the UI tab probe fail when asked to check a tab that is actually empty.
probe = ROOT / "repair/v13_ui_probe.py"
if not probe.is_file():
    fail("Не найден repair/v13_ui_probe.py.")
probe_text = probe.read_text(encoding="utf-8")
old = """        if substantive:
            print('V16_TAB_NOT_VISIBLY_EMPTY=YES')
        else:
            print('V16_TAB_BLANK_SCREEN_SUSPECTED=YES')
        return
"""
new = """        if substantive:
            print('V16_TAB_NOT_VISIBLY_EMPTY=YES')
        else:
            print('V16_TAB_BLANK_SCREEN_SUSPECTED=YES')
            raise SystemExit('V17_03_TAB_EMPTY:' + needle)
        return
"""
if "V17_03_TAB_EMPTY:" not in probe_text:
    if old not in probe_text:
        fail("Не найден ожидаемый check-tab блок в v13_ui_probe.py; автопатч отменён.")
    probe.write_text(probe_text.replace(old, new, 1), encoding="utf-8")

# Add reviewed translations for the two Chinese card headings visible in the phone screenshots.
data = json.loads(dex_file.read_text(encoding="utf-8"))
translations = data.get("translations")
if not isinstance(translations, list):
    fail("Неверная структура JSON в v13_dex_translations.json.")
additions = [
    {"source": "睡眠呼吸暂停研究", "target": "Исследование апноэ сна"},
    {"source": "跑步损伤评估", "target": "Оценка риска беговых травм"},
]
existing = {item.get("source") for item in translations if isinstance(item, dict)}
for item in additions:
    if item["source"] not in existing:
        translations.append(item)
dex_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

workflow_dst.write_text(wf, encoding="utf-8")

# Structural guardrails: names must consistently say V17.03; heredoc must be closed.
if "V17_01" in wf or "V17.01" in wf or "v17.01-build" in wf:
    fail("В сгенерированном workflow остались метки V17.01.")
if wf.count("V17_03_BASH") != 2:
    fail("Проверка heredoc не прошла.")
if "branches: [\"v17.03-build\"]" not in wf:
    fail("Workflow не ограничен веткой v17.03-build.")
print("V17.03_WORKFLOW_CREATED=.github/workflows/v17_03.yml")
print("V17.03_TRANSLATIONS_ADDED=2 (only if absent)")
print("V17.03_TAB_EMPTY_CHECK=STRICT")
print("V17.03_NETWORK_ACTIONS=NONE")
print("Важно: это подготовка исходников; APK будет собран GitHub Actions после git push.")
