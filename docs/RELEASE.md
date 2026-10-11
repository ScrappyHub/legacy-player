# Releasing and installing Legacy Player

## Checklist before tagging
1. `launcher/version.py` `VERSION` is the number you are about to tag (the workflow refuses a tag that does not match it).
2. The tests pass: `python -m unittest discover -s tests` (or `python tools/release_check.py`).
3. `.github/workflows/release.yml` and `tools/release.workflow.yml` are identical (a test checks this; GitHub only reads the first).
4. `docs/WINDOWS_CHECKLIST.md` has been walked on a real Windows computer for anything that changed.


## Build and publish (on GitHub)
1. Merge the work into `main`, then tag a commit **on `main`**. The workflow refuses a tag whose commit is not on `main`
   (the installer one-liner below also reads `install.ps1` from `main`). Installed copies of Legacy Player update themselves
   to the newest release (`releases/latest`), so a bad release reaches everyone who has the app: tag only what you would
   install yourself.
   ```
   git tag v0.7.44
   git push origin v0.7.44
   ```
2. The `release` workflow (GitHub > Actions), on a Windows runner: checks the tagged commit is on `main` and the tag
   matches `VERSION` in `launcher/version.py`; runs `python tools/release_check.py` (all tests and the repository check;
   nothing is built if they fail); builds `LegacyPlayer.exe`; signs it when signing is set up; then starts the built exe
   three ways as a smoke check (the app's own page server, the friends service's `/health`, and the multiplayer server's
   port) and only then publishes `LegacyPlayer-<version>-win64.zip` (what the installer downloads), the bare
   `LegacyPlayer-<version>-win64.exe`, a `.sha256` for each and `SHA256SUMS.txt`. The release is created as a draft, the
   files are uploaded, and only then is it made public; re-running the workflow for a tag that already has a release
   replaces its files.
3. To try a build without publishing: Actions > release > Run workflow; the zip is attached to that run.

## Install on another computer (PowerShell, no administrator needed)
```
irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex
```
It downloads the latest release, checks its SHA-256, installs to `%LOCALAPPDATA%\Programs\LegacyPlayer`, adds a Start
menu shortcut and starts the app. Pin a version: save the script and run `.\install.ps1 -Tag v0.7.44`.
If the repository is private, the one-liner cannot download it: use `-Token <GitHub token with repo read access>` on a saved
copy of the script, or make the repository public first.

## Install through git (the `lp` command)
```
git clone https://github.com/Alpallyoop/legacy-player
cd legacy-player
.\lp.cmd install      # or: .\lp.cmd install v0.7.44     (update / run / version / path / uninstall / source / help)
```
In PowerShell use `.\lp.cmd`: a plain `.\lp` runs `lp.ps1` directly, which the default execution policy (Restricted)
blocks; `lp.cmd` starts it with `-ExecutionPolicy Bypass`. From cmd.exe `lp install` is enough. Without `lp.cmd`:
`powershell -ExecutionPolicy Bypass -File .\lp.ps1 install`. `lp source` runs straight from the checkout with Python (for developers).

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
  `gh attestation verify LegacyPlayer-<version>-win64.exe --repo Alpallyoop/legacy-player`; and `SHA256SUMS.txt` lists the hashes.
- Hosting the shared server and report receiver: `deploy/README.md`; check a deployment with `python tools/check_deployment.py`.
- Data lives in `%USERPROFILE%\.legacy-player`; the log is `%LOCALAPPDATA%\LegacyPlayer\app.log`.
- The build has run on GitHub's `windows-latest` runners (releases 0.7.35 to 0.7.37 and 0.7.43). The parts listed in
  `docs/WINDOWS_CHECKLIST.md` still need a real Windows computer. If the workflow fails, the Actions log shows which step.
