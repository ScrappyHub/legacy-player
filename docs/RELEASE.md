# Releasing and installing Legacy Player

## Build and publish (on GitHub)
1. Merge the work into `main` (the installer one-liner below reads `install.ps1` from `main`), then:
   ```
   git tag v0.7.0
   git push origin v0.7.0
   ```
2. The `release` workflow (GitHub > Actions) builds `LegacyPlayer.exe` on a Windows runner, starts it once as a smoke
   check, and publishes `LegacyPlayer-0.7.0-win64.zip` plus its `.sha256` as a release. The tag should match `VERSION`
   in `launcher/version.py`.
3. To try a build without publishing: Actions > release > Run workflow; the zip is attached to that run.

## Install on another computer (PowerShell, no administrator needed)
```
irm https://raw.githubusercontent.com/ScrappyHub/legacy-player/main/install.ps1 | iex
```
It downloads the latest release, checks its SHA-256, installs to `%LOCALAPPDATA%\Programs\LegacyPlayer`, adds a Start
menu shortcut and starts the app. Pin a version: save the script and run `.\install.ps1 -Tag v0.7.0`.
If the repository is private, the one-liner cannot download it: use `-Token <GitHub token with repo read access>` on a saved
copy of the script, or make the repository public first.

## Without GitHub
On a Windows computer with Python 3.13+: `powershell -ExecutionPolicy Bypass -File tools\package_release.ps1`.
It writes `dist\release\LegacyPlayer-<version>-win64.zip` and a `.sha256`. Copy the zip to the other computer, unzip, and
double-click `LegacyPlayer.exe`.

## First-run notes
- The exe is not code-signed, so Windows SmartScreen says "unknown publisher": More info > Run anyway. Set `LP_SIGN_PFX`
  and `LP_SIGN_PASS` before building to sign it.
- Data lives in `%USERPROFILE%\.legacy-player`; the log is `%LOCALAPPDATA%\LegacyPlayer\app.log`.
- Nothing about the build has been run on Windows yet. If the workflow fails, the Actions log shows which step.
