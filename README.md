# Xiaomi Health Research 1.4.6 — finalization input

This repository contains only the already-modified Russian APK candidate and the GitHub Actions finalization pipeline.

The workflow performs:
- Android SDK/build-tools setup
- zipalign
- temporary test-key generation
- V1/V2/V3 signing
- apksigner verification
- SHA-256
- APK artifact publication
- Android emulator install smoke test
