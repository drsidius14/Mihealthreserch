XiaomiHealthResearch V15 localization repair

This patch fixes the confirmed V14 localization failure: Apktool 3's <Data> wrapper for encoded HTML strings. It preserves the original base resources and attributes, checks placeholders, and tests that consent links remain encoded and present.

It does not disable strict compiled-resource checks. The GitHub Actions workflow must still pass its semantic resource-table comparison and Android 15 emulator test before the APK can be considered complete.
