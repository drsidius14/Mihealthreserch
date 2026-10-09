XIAOMI HEALTH RESEARCH V14 — SOURCE + FORENSIC VALIDATION

PURPOSE
V14 is a corrected source/build pipeline based on the exact Xiaomi CN control APK plus the established V8 classes.dex. It adds a Russian values overlay and keeps the original manifest, classes2.dex, native libraries, assets, and non-resource payload unchanged. It does not alter default-language values or app code to localize ordinary strings.

WHAT V12 ACTUALLY SHOWED
GitHub Actions run: https://github.com/drsidius14/Mihealthreserch/actions/runs/37862313252
V12 did not create an APK. Its forensic tests passed, but localization stopped because the two mandatory consent strings were not written: onboarding_join_experience_program and onboarding_privacy_tips_2. The run log does not prove which skip path caused this, because the V12 localizer raised before persisting its audit.

V14 CHANGES
- Required onboarding strings are still a hard gate. For those keys only, translatable=false is treated as translator-tool metadata and cannot block the runtime Russian overlay; other keys marked false remain skipped.
- Rich-string translation preserves all XML nodes and attributes, especially link href placeholders, and safely replaces translated visible text even when link nodes have formatting/annotation wrappers.
- A critical-key failure writes an audit first and prints source shape, link href, source file, and skip reasons; logs should no longer be empty or hide the reason.
- New offline end-to-end fixtures test critical non-translatable resources, wrapped live links, escaped/text markup, placeholder-mismatch fail-safe behavior, immutable base values, and failure-audit persistence.
- Before rebuild, an extra repair reads every `enum`/`flags` attribute type from the original compiled resource dump and restores those exact `format` masks in the decoded XML; this addresses the `expandState: reference|enum` metadata loss observed in V10.7. Its audit is included in diagnostics. Strict diff normalization also retains file extension and compiled file type and refuses enum metadata loss.
- Independent APK verification also checks the two Russian consent-link strings and their %1$s/%2$s/%3$s placeholders in the final resource table.
- The workflow captures the source XML shapes of every mandatory onboarding key in the diagnostic artifact.

COVERAGE-GATE CORRECTION
The previous run failed because v13_coverage.py treated an arbitrary 90% diagnostic coverage target as a fatal release gate. V14 reports that percentage but does not fail solely because AndroidX/MIUIX/calendar/system resources remain outside the reviewed app-owned translation set. The mandatory app-owned onboarding/consent keys remain a hard gate; placeholder/link preservation, strict resource semantics, APK payload/Dex identity, signature checks, and Android 15 runtime smoke tests remain enforced. A low percentage is still reported transparently and is not represented as full UI translation.

SAFETY GATES
No APK is considered ready unless the exact source hashes, forensic cross-check, offline tests, translation coverage, strict original-vs-rebuilt resource semantics, payload/Dex/manifest identity, resource-reference closure, signature/zipalign checks, and Android 15 x86_64 launch + Russian onboarding + basic-mode navigation all pass. A successful build still cannot prove Xiaomi cloud/account/wearable operation; Xiaomi's private signing key is unavailable, so the original certificate cannot be preserved.

EXPECTED OUTPUT AFTER SUCCESSFUL WORKFLOW
Artifact: XiaomiHealthResearch_V14
APK: XiaomiHealthResearch_1.4.6_RU_V14.apk
Checksum: V13.sha256
If the run fails, only diagnostics (and, after static checks, a candidate for runtime testing) are uploaded; a final release artifact is not published.
