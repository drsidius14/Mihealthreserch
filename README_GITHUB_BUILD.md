# Xiaomi Health Research 1.4.6 — GitHub build pipeline

This package continues the v1–v5 Termux workflow, but moves the actual APK build to GitHub Actions.

Pipeline:
1. deterministic repair of `classes.dex`;
2. DEX integrity verification;
3. Android SDK / build-tools 35.0.0;
4. zipalign;
5. apksigner V1/V2/V3;
6. signature verification;
7. ARM64 Android emulator install/launch smoke test through ADB;
8. artifact with APK, SHA-256 and diagnostics.

The candidate APK is the v5 APK. No manual APK rebuild is performed on the workstation.
