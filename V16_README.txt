Xiaomi Health Research 1.4.6 — V16 source patch

Purpose
- Fix the confirmed V15 GitHub Actions failure in Android resource locale routing.
- Keep the original APK's code, manifest, native libraries, assets, and non-resource payload under the existing strict forensic gates.
- Preserve Russian translations, consent-link HTML, hrefs, and format placeholders.

What the single Termux command does
1. Unpacks this patch into a unique temporary directory.
2. Verifies the local repository is safe to modify and switches to the existing v13-build branch.
3. Applies the source patch, checks Python syntax, and runs offline regression tests.
4. Commits and pushes to v13-build, which triggers the existing GitHub Actions workflow.
5. GitHub fetches the exact original/V8 APKs, runs resource-table audits, compiles, signs and statically verifies the APK, then runs Android 15 emulator checks.

Release policy
- A compiled APK is a candidate until all strict resource-table, APK/DEX/manifest, signature and Android 15 runtime gates pass.
- The final downloadable artifact is XiaomiHealthResearch_V16 only after runtime tests pass.
- The workflow file and helper script filenames retain their historical v13 names to update the existing branch/workflow in place and avoid duplicate workflows.
- This package does not include the original APK or a compiled APK; GitHub obtains the exact input APKs from the repository and performs the Android build.

APK alignment
- Native-library alignment is checked at 16 KiB page boundaries (`zipalign -P 16`) before signing; the signed APK is checked again. Android documents that alignment must happen before `apksigner`, because post-signing APK edits invalidate the signature.

Signing limitation
- The workflow signs with a fresh test key when it runs. The original Xiaomi private signing key is unavailable, so the output cannot retain Xiaomi's original signature or guarantee backend acceptance. Because the test key is generated per run, Android may require uninstalling an earlier custom-signed build before installing a new one; back up any local app data first. A stable signing key would need to be managed separately as a private GitHub Actions secret and is deliberately not embedded in this public patch.
