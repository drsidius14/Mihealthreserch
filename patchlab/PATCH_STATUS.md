# Status

- [x] Isolated PatchLab scaffold and CI workflow
- [x] Automated apktool disassembly of Mi Fitness 3.59.1
- [x] Locate Validator/Binder method references and archive smali context
- [x] Record input SHA-256 and APK signer certificates
- [ ] Exact patch to accept V17.03 certificate — blocked until the CI artifact confirms the full method body and whitelist representation
- [ ] Rebuild, sign, install, and verify Binder data exchange

Do not label an output APK as patched until all steps above are completed and runtime checks pass.
