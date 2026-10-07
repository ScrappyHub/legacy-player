<#
 Builds the release zip on a Windows computer with Python 3.13+:   powershell -ExecutionPolicy Bypass -File tools\package_release.ps1
 Output (in dist\release):  LegacyPlayer-<version>-win64.zip  and  LegacyPlayer-<version>-win64.zip.sha256
#>
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$version = (Select-String -Path 'launcher\version.py' -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Packaging Legacy Player $version"

# build_exe.bat does the PyInstaller build (LP_LOGGED=1 skips its log-and-pause wrapper)
$env:LP_LOGGED = '1'
cmd /c "build_exe.bat"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path 'dist\LegacyPlayer.exe')) { throw 'The build failed; see the output above.' }

$out = 'dist\release'
$stage = Join-Path $out 'stage'
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item 'dist\LegacyPlayer.exe' $stage
Copy-Item 'LICENSE' $stage -ErrorAction SilentlyContinue
@"
Legacy Player $version
Double-click LegacyPlayer.exe. Windows may say it is from an unknown publisher (the app is not code-signed yet):
choose More info > Run anyway. Your data is kept in %USERPROFILE%\.legacy-player.
To play with a friend: Servers page > Start (leave "Let friends connect" ticked) > Make my server code, and send them the code.
"@ | Set-Content (Join-Path $stage 'READ ME FIRST.txt') -Encoding UTF8

$zip = Join-Path $out "LegacyPlayer-$version-win64.zip"
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $zip -Leaf)" | Set-Content "$zip.sha256" -Encoding ASCII
Write-Host "Built $zip"
Write-Host "SHA256 $hash"
