# MiHealth resource-only patch build

Upload this isolated workflow to branch `mihealth-resource-only` and let GitHub Actions run.
It imports no source code from `v17.03-build`: the workflow checks out only the approved
translation map and the original APK input, pins both by their Git blob/SHA-256, and performs
resource-only localization.

**Signing caveat:** the test APK uses a new signing key. The official Mi Fitness trust-key
exchange is not considered verified merely because the DEX and Binder-related code are
byte-identical. The build report explicitly states that limitation.
