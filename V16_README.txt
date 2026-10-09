Xiaomi Health Research 1.4.6 — V16 repair source package

Purpose
- Correct the exact styled-string localization defect that stopped the previous V16 static audit.
- Translate the four Chinese home-card descriptions and user-visible Mi Fitness hand-off dialog strings while minimizing any executable-code change. The new build derives `classes.dex` from the exact ORIGINAL APK—not the older V8 binary—and changes only an allow-list of eleven string literals.
- Verify Smali changes against the V8 baseline and preserve original non-resource payload, including the original DEX baseline apart from reviewed visible-text literals.
- Capture comparative original / V10.7 / candidate UI, screenshots, and logcat for the Device/Profile blank-screen investigation.

Applying the package
- Download `XiaomiHealthResearch_V16_REPAIR.zip` to the Android Download folder.
- Run the single Termux command provided in the chat.
- The applicator verifies the package checksum manifest and local Python regression tests, applies only this source patch, and commits/pushes to the existing `v13-build` branch. GitHub Actions builds and validates the Android APK.

Release policy
- The source ZIP is not an APK and does not contain the original APK. GitHub Actions retrieves the exact original and V8 inputs from the repository.
- A candidate APK must pass resource semantic comparison, APK/DEX/manifest/resource-reference checks, signature verification, and the Android 15 smoke test before it is called the final artifact.
- Additional Device/Profile tab captures are diagnostic. The emulator does not contain Xiaomi Mi Fitness or a real account/backend session, so it cannot prove authorization or wearable-data functionality.

Signing limitation
- The build generates a test signing key for each run; it cannot retain Xiaomi's original signature because the original private key is not available. Xiaomi account/backend acceptance may therefore differ from the original app. A successful local static audit does not prove online authorization works.
