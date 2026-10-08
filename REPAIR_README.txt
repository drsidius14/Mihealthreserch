Repair pack for Mihealthreserch.

Replaces the failed finalize.yml.

The previous run failed in android-actions/setup-android@v3 because that action attempted to install the obsolete SDK package "tools".
This workflow avoids that failure and prepares the Android SDK directly with sdkmanager.

It also adds:
- APK ZIP integrity preflight
- signature-file preflight
- package metadata check
- zipalign before signing and after signing
- V1/V2/V3 signature verification
- SHA-256 reports
- fresh Android 35 emulator smoke test
- emulator diagnostics artifact

The existing APK in the repository is intentionally not included here.
