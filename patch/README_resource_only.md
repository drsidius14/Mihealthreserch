# Mi Health — resource-only Russian patch

This is a new, isolated workflow. It does **not** import scripts, DEX translation maps,
Smali logic, or Mi Fitness patches from `v17.03-build`. At build time it reads only:
- the reviewed `repair/v13_translations.json` map (pinned by Git blob SHA);
- the original `input/XiaomiHealthResearch_1.4.6_CN_CONTROL.apk` source APK (pinned by SHA-256).

## Design
1. Decode the original APK with pinned Apktool 3.0.3.
2. Generate only `res/values-ru/strings.xml` from the reviewed map. Do not edit Smali,
   DEX, manifest, services, permissions, Binder code, assets, or native libraries.
3. Rebuild with Apktool to obtain a compiled resource table.
4. Compare all resource-table file references and resource-file sets against the original.
5. Build the candidate from the original APK ZIP, replacing **only `resources.arsc`**.
   Original `AndroidManifest.xml`, every `classes*.dex`, every `res/*` file, assets,
   native libraries, and other payloads must remain byte-identical. Signature metadata
   is removed and a test key signs the resulting APK.
6. Independently verify the APK payload and upload it as a **test-only artifact**.

## Important signing limitation
The original signing private key is not available. The output therefore has a different
certificate and cannot update the official app in place. More importantly, preserving DEX
and Binder code does **not** prove that official Mi Fitness accepts the repackaged app's
signer for its trust-key exchange. The workflow explicitly reports this as unverified;
it does not patch Mi Fitness and does not claim trust compatibility.

## Artifact
`MiHealth_RU_RESOURCE_ONLY_TEST.apk` is a diagnostic/test build, not a release build.
The GitHub Actions summary and artifact include hashes and a preservation audit.
