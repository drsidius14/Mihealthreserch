#!/usr/bin/env bash
set -uo pipefail
APK="${1:?APK path required}"
OUT="${2:?output directory required}"
mkdir -p "$OUT/screenshots"
REPORT="$OUT/TEST-REPORT.txt"
PASS=0; FAIL=0; WARN=0
record(){ printf '%s | %s\n' "$1" "$2" | tee -a "$REPORT"; case "$1" in PASS) PASS=$((PASS+1));; FAIL) FAIL=$((FAIL+1));; WARN) WARN=$((WARN+1));; esac; }
printf 'Mi Fitness 3.59.1 emulator deep test\nStarted UTC: %s\n' "$(date -u +%FT%TZ)" > "$REPORT"
command -v adb >/dev/null 2>&1 || { record FAIL 'adb unavailable'; exit 1; }
[ -s "$APK" ] || { record FAIL 'APK missing or empty'; exit 1; }
PKG="$(aapt dump badging "$APK" | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -n1)"
[ -n "$PKG" ] || { record FAIL 'Could not read package name from APK'; exit 1; }
printf 'Package: %s\nAPK SHA-256: %s\n' "$PKG" "$(sha256sum "$APK" | awk '{print $1}')" >> "$REPORT"
adb wait-for-device
adb shell getprop sys.boot_completed | grep -q 1 && record PASS 'Emulator boot completed' || record FAIL 'Emulator did not report boot completed'
adb shell settings put global window_animation_scale 0 >/dev/null 2>&1 || true
adb shell settings put global transition_animation_scale 0 >/dev/null 2>&1 || true
adb shell settings put global animator_duration_scale 0 >/dev/null 2>&1 || true
adb logcat -c >/dev/null 2>&1 || true
if adb install -r "$APK" > "$OUT/install.txt" 2>&1; then record PASS 'APK install succeeded'; else record FAIL "APK install failed: $(tr '\n' ' ' < "$OUT/install.txt")"; cat "$OUT/install.txt" >> "$REPORT"; fi
if [ "$FAIL" -gt 0 ]; then adb logcat -d -v threadtime > "$OUT/logcat-install-failure.txt"; fi
if adb shell pm path "$PKG" | grep -q 'package:'; then record PASS 'Package is registered in Package Manager'; else record FAIL 'Package not registered after install'; fi
# Launch via launcher intent and capture initial screen.
if adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 > "$OUT/launch.txt" 2>&1; then record PASS 'Launcher intent sent'; else record FAIL 'Monkey launch command failed'; fi
sleep 8
adb shell dumpsys activity activities > "$OUT/activity-after-launch.txt"
adb shell screencap -p /sdcard/mi-fitness-launch.png >/dev/null 2>&1 && adb pull /sdcard/mi-fitness-launch.png "$OUT/screenshots/launch.png" >/dev/null 2>&1 && record PASS 'Launch screenshot captured' || record WARN 'Could not capture launch screenshot'
adb shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 && adb pull /sdcard/window.xml "$OUT/window-launch.xml" >/dev/null 2>&1 && record PASS 'UI hierarchy captured on launch' || record WARN 'Could not dump launch UI hierarchy'
# Generic, bounded exploratory UI: click visible enabled clickable nodes and swipe between screens.
python3 - "$OUT/window-launch.xml" "$OUT/click-targets.txt" <<'PY2'
import sys,xml.etree.ElementTree as ET
src,dst=sys.argv[1:]
try:
 root=ET.parse(src).getroot(); rows=[]
 for n in root.iter('node'):
  if n.attrib.get('clickable')=='true' and n.attrib.get('enabled','true')=='true':
   b=n.attrib.get('bounds',''); text=n.attrib.get('text','') or n.attrib.get('content-desc','')
   import re
   m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',b)
   if m:
    x1,y1,x2,y2=map(int,m.groups()); rows.append((text,(x1+x2)//2,(y1+y2)//2,b))
 with open(dst,'w') as f:
  seen=set()
  for row in rows:
   key=(row[1],row[2])
   if key not in seen: seen.add(key); f.write(f'{row[1]} {row[2]} | {row[0][:100]} | {row[3]}\n')
except Exception as e:
 open(dst,'w').write('UI_PARSE_ERROR: '+repr(e)+'\n')
PY2
N=0
while read -r X Y REST; do
  [ -n "${X:-}" ] || continue
  [ "$N" -lt 12 ] || break
  N=$((N+1))
  adb shell input tap "$X" "$Y" >/dev/null 2>&1 || true
  sleep 2
  adb shell screencap -p "/sdcard/mi-fitness-tap-${N}.png" >/dev/null 2>&1 || true
  adb pull "/sdcard/mi-fitness-tap-${N}.png" "$OUT/screenshots/tap-${N}.png" >/dev/null 2>&1 || true
  adb shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  adb pull /sdcard/window.xml "$OUT/window-tap-${N}.xml" >/dev/null 2>&1 || true
done < "$OUT/click-targets.txt"
if [ "$N" -gt 0 ]; then record PASS "Exploratory UI taps executed: $N"; else record WARN 'No clickable nodes detected on first screen; exploratory taps skipped'; fi
# A bounded swipe sweep across the viewport to exercise scrollable surfaces.
for i in 1 2 3 4; do
 adb shell input swipe 500 1500 500 450 350 >/dev/null 2>&1 || true; sleep 1
 adb shell input swipe 500 450 500 1500 350 >/dev/null 2>&1 || true; sleep 1
done
record PASS 'Eight generic swipe gestures executed'
adb shell dumpsys activity activities > "$OUT/activity-after-exploration.txt"
# Restart stability
adb shell am force-stop "$PKG" >/dev/null 2>&1 || true
sleep 1
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 > "$OUT/relaunch.txt" 2>&1
sleep 6
if adb shell pm path "$PKG" | grep -q 'package:'; then record PASS 'Package remains installed after restart'; else record FAIL 'Package missing after restart'; fi
adb shell screencap -p /sdcard/mi-fitness-relaunch.png >/dev/null 2>&1 && adb pull /sdcard/mi-fitness-relaunch.png "$OUT/screenshots/relaunch.png" >/dev/null 2>&1 || true
adb logcat -d -v threadtime > "$OUT/logcat-full.txt"
# Fatal exceptions and native crash signatures from logcat.
if grep -E -i 'FATAL EXCEPTION|Fatal signal [0-9]+|am_crash|Process .* has died|ANR in ' "$OUT/logcat-full.txt" > "$OUT/crash-signatures.txt"; then
  record FAIL 'Crash/ANR signatures found in logcat'
else
  record PASS 'No obvious fatal crash/ANR signatures in captured logcat'
  : > "$OUT/crash-signatures.txt"
fi
# Ensure the tested package had a process/activity after relaunch; record rather than overclaiming if background-limited.
if grep -F "$PKG" "$OUT/activity-after-exploration.txt" > "$OUT/package-activity-evidence.txt"; then record PASS 'Package activity observed during test'; else record WARN 'No package activity line found in final activity dump'; fi
printf '\nSUMMARY\nPASS=%s\nFAIL=%s\nWARN=%s\nFinished UTC: %s\n' "$PASS" "$FAIL" "$WARN" "$(date -u +%FT%TZ)" | tee -a "$REPORT"
# Keep job red if hard failures were recorded.
[ "$FAIL" -eq 0 ]
