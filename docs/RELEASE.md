# Releasing and installing Legacy Player

## Checklist before tagging
1. `launcher/version.py` `VERSION` is the number you are about to tag (the workflow refuses a tag that does not match it).
2. The tests pass: `python -m unittest discover -s tests` (or `python tools/release_check.py`).
3. `.github/workflows/release.yml` and `tools/release.workflow.yml` are identical (a test checks this; GitHub only reads the first).
4. `docs/WINDOWS_CHECKLIST.md` has been walked on a real Windows computer for anything that changed.


## Build and publish (on GitHub)
1. Merge the work into `main` (the installer one-liner below reads `install.ps1` from `main`), then:
   ```
   git tag v0.7.14
   git push origin v0.7.14
   ```
2. The `release` workflow (GitHub > Actions) builds `LegacyPlayer.exe` on a Windows runner, starts it once as a smoke
   check, and publishes the release files: `LegacyPlayer-0.7.0-win64.zip` (what the installer downloads), the bare `LegacyPlayer-0.7.0-win64.exe`, a `.sha256` for each and `SHA256SUMS.txt`. The tag should match `VERSION`
   in `launcher/version.py`.
3. To try a build without publishing: Actions > release > Run workflow; the zip is attached to that run.

## Install on another computer (PowerShell, no administrator needed)
```
irm https://raw.githubusercontent.com/ScrappyHub/legacy-player/main/install.ps1 | iex
```
It downloads the latest release, checks its SHA-256, installs to `%LOCALAPPDATA%\Programs\LegacyPlayer`, adds a Start
menu shortcut and starts the app. Pin a version: save the script and run `.\install.ps1 -Tag v0.7.14`.
If the repository is private, the one-liner cannot download it: use `-Token <GitHub token with repo read access>` on a saved
copy of the script, or make the repository public first.

## Install through git (the `lp` command)
```
git clone https://github.com/ScrappyHub/legacy-player
cd legacy-player
.\lp install      # or: .\lp install v0.7.14     (update / run / version / path / uninstall / source / help)
```
`lp.cmd` lets it run from cmd.exe too. `lp source` runs straight from the checkout with Python (for developers).

## Without GitHub
On a Windows computer with Python 3.13+: `powershell -ExecutionPolicy Bypass -File tools\package_release.ps1`.
It writes the zip, the bare exe, their `.sha256` files and `SHA256SUMS.txt` into `dist\release`. Copy the zip to the other computer, unzip, and
double-click `LegacyPlayer.exe`.

## First-run notes
- Signing with Azure Artifact Signing (no stored key): see docs/AZURE_SIGNING.md.
- Signing with your own certificate: the exe is signed only if you supply a code-signing certificate, which has to be bought from a certificate
  authority (this is the one thing that cannot be done for you). On GitHub add repository secrets `WINDOWS_SIGN_PFX_BASE64`
  (the .pfx file as base64: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`) and `WINDOWS_SIGN_PFX_PASSWORD`;
  the next tag is then signed and time-stamped before it is zipped and hashed. Locally set `LP_SIGN_PFX` and `LP_SIGN_PASS`
  before `build_exe.bat`. Without a certificate the release says so in its read-me and Windows SmartScreen shows "unknown
  publisher": More info > Run anyway. A new certificate also needs time (or an EV certificate) to build SmartScreen reputation.
- Every tagged release also gets a GitHub build-provenance attestation (where the repository supports it). Check a download:
  `gh attestation verify LegacyPlayer-<version>-win64.exe --repo ScrappyHub/legacy-player`; and `SHA256SUMS.txt` lists the hashes.
- Hosting the shared server and report receiver: `deploy/README.md`; check a deployment with `python tools/check_deployment.py`.
- Data lives in `%USERPROFILE%\.legacy-player`; the log is `%LOCALAPPDATA%\LegacyPlayer\app.log`.
- Nothing about the build has been run on Windows yet. If the workflow fails, the Actions log shows which step.
