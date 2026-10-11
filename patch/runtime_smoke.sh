#!/usr/bin/env bash
set -euo pipefail
APK="${1:?usage: runtime_smoke.sh candidate.apk}"
test -s "$APK"
mkdir -p runtime-report
adb wait-for-device
adb shell settings put system system_locales ru-RU || true
adb shell cmd locale set ru-RU >/dev/null 2>&1 || true
adb uninstall com.mi.healthresearch >/dev/null 2>&1 || true
adb install "$APK" | tee runtime-report/install.txt
adb logcat -c
adb shell monkey -p com.mi.healthresearch 1 | tee runtime-report/launch.txt
sleep 15
PID="$(adb shell pidof com.mi.healthresearch | tr -d '\r' || true)"
adb logcat -d -v threadtime > runtime-report/logcat.txt
if [[ -z "$PID" ]]; then
  echo "ANDROID_RUNTIME_PROCESS_NOT_RUNNING" | tee runtime-report/result.txt
  exit 1
fi
echo "ANDROID_RUNTIME_PROCESS_RUNNING pid=$PID" | tee runtime-report/result.txt
adb shell uiautomator dump /sdcard/mihealth-resource-only.xml >/dev/null 2>&1 || true
adb pull /sdcard/mihealth-resource-only.xml runtime-report/ui.xml >/dev/null 2>&1 || true
if grep -E "FATAL EXCEPTION|Fatal signal|Process: com\.mi\.healthresearch" runtime-report/logcat.txt; then
  echo "ANDROID_RUNTIME_FATAL_LOG_FOUND" | tee -a runtime-report/result.txt
  exit 1
fi
echo "ANDROID_RUNTIME_SMOKE=PASS" | tee -a runtime-report/result.txt
echo "MI_FITNESS_TRUST_KEY_EXCHANGE=NOT_TESTED_SIGNER_CHANGED" | tee -a runtime-report/result.txt
