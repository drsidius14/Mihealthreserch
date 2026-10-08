XIAOMI HEALTH RESEARCH V11 — SOURCE + FORENSIC VALIDATION

PURPOSE
V11 starts from the exact Xiaomi China control APK and the proven V8 classes.dex, adds a Russian values overlay, and preserves the original manifest, classes2.dex, native libraries, assets, and non-resource payload. It never edits the original/default string values or application code to translate interface strings. The compiled resource table and the compiled res/ files are packaged as one consistent set.

WHAT THE OFFLINE BYTE AUDIT FOUND IN V10.7
Original APK SHA-256:
9e872f2d75e4ec1d509216d8caa998c2957d797c57b8ecc1ed8c92054f53c4bc
V10.7 APK SHA-256:
5f3c9ea4eec8a7260324669fe8fe789f1f789c5de0ffb3fc34257407df00a92e
V8 reference APK SHA-256:
c3bd649826febc1e40895e4f9e7d30b3a7b2b27b989cd5917cb560e72de3c5b0

The independent Python byte comparator checked every ZIP entry byte-for-byte and stores a path/size/SHA-256 manifest for every file in reference_local_v10_7.json. It found 3,521 entries on each side; 2,728 resource paths were renamed/replaced during Apktool resource rebuilding, 177 common entries differed (174 res entries, resources.arsc, classes.dex and signature metadata). AndroidManifest.xml, classes2.dex, assets and native libraries were exact matches. V10.7 classes.dex is byte-for-byte the V8 classes.dex; its visible DEX string delta against the Chinese original is 血压健康研究 -> Исслед. АД, and both DEX checksum sets pass.

IMPORTANT LIMITS/RISKS
1. Xiaomi's original signing certificate cannot be preserved without Xiaomi's private key. The audit extracted certificate fingerprints from the APKs and confirmed the original and V10.7 certificates differ. A service that checks package/signing identity may reject network/account operations. This cannot be fixed by translating resources. GitHub emulator checks cannot certify Xiaomi backend/account/wearable services.
2. V10.7's Android 15 test failed before installing the APK because its ARM64 emulator did not boot on the x86 runner. That was not an app crash test. V11 explicitly uses an x86_64 Android 15 emulator and tests first launch, Russian onboarding, FileProvider startup, and the “continue in basic mode” route.
3. The local environment cannot run Android/Apktool; local checks are byte-level analysis, translation-map/XML fixture tests, placeholder checks, and workflow/YAML validation. The GitHub Actions result is still required for the APK build and Android runtime test.
4. Each build generates a new signing key because no private release key is stored in the public repository. Therefore V11 will generally not install as an update over V10.7 (different certificate). Uninstall V10.7 before installing V11. The V11 app data will be reset. Do not uninstall the original Xiaomi-signed app unless you knowingly accept losing its local data.

RUSSIAN LOCALIZATION
v11_translations.json currently contains 1,137 reviewed resource-key translations. The offline projection covered 1,137 of 1,227 default strings containing Chinese (92.7%). GitHub recomputes the count from the original APK's actual aapt2 resource dump; the build fails below 90% and reports every remaining key. Chinese lunar-calendar/date-pattern resources are intentionally excluded rather than translated incorrectly. Rich links retain their href values and placeholders. Non-Russian base resources remain unmodified. Every written translation is cross-checked against the translation map and resource-table semantics. The app's V8 DEX contains 303 unique literals with Chinese characters (a mixture of possible UI labels, logs, and internal text). V11 preserves that DEX byte-for-byte rather than risk changing program behavior; the workflow includes all of them in a follow-up audit report. Therefore, 92.7% is coverage of default Chinese resource strings, not a claim that absolutely every hard-coded label is translated.

CHECKS IN THE WORKFLOW
- exact SHA-256 verification of original and V8 source APKs and pinned Apktool 2.10.0;
- an independent GitHub-side full-byte forensic audit of original vs V10.7 plus a comparison of its hashes/counts against the locally generated reference report;
- a report of Chinese literals still embedded in DEX (not rewritten without safe call-site/reference analysis);
- a semantic resource-table diff of V10.7 vs original, for diagnosis;
- XML overlay checks, placeholder/attribute preservation, and translation coverage;
- a strict original-vs-V11 aapt2 resource semantic comparison allowing only reviewed Russian values;
- exact preservation checks for manifest, classes2.dex, native libs/assets/non-resource payload, and V8 classes.dex;
- zip integrity, zipalign, APK signature, resource-file path closure, Russian app label and onboarding checks;
- Android 15 x86_64 emulator launch, Russian onboarding text checks, FileProvider regression checks, and basic-mode navigation.

EXPECTED OUTPUT
Artifact name: XiaomiHealthResearch_V11
APK: output/XiaomiHealthResearch_1.4.6_RU_V11.apk
SHA-256: output/V11.sha256
Coverage/forensic/runtime reports are uploaded as workflow artifacts.
