#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APK="${1:-}"
EXPECTED_SHA256="9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc"

if [[ -z "$APK" || ! -f "$APK" ]]; then
  echo "Usage: bash tools/preflight.sh /path/to/小米健康研究_1.4.6.apk" >&2
  exit 2
fi

for cmd in sha256sum unzip; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 3
  }
done

ACTUAL_SHA256="$(sha256sum "$APK" | awk '{print $1}')"
echo "APK: $APK"
echo "SHA-256: $ACTUAL_SHA256"

if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "ERROR: SHA-256 does not match the recorded original. Stop before patching." >&2
  exit 4
fi

echo "Checking APK ZIP integrity..."
unzip -t "$APK" >/dev/null
echo "PASS: SHA-256 and ZIP integrity verified."
