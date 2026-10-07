<#
 Builds the release files on a Windows computer with Python 3.13+:   powershell -ExecutionPolicy Bypass -File tools\package_release.ps1
 Output (in dist\release):
   LegacyPlayer-<version>-win64.zip      the exe plus a READ ME, what the installer downloads
   LegacyPlayer-<version>-win64.exe      the bare exe, for people who just want the one file
   each of the two with a .sha256 next to it, and SHA256SUMS.txt listing both
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

$exe = Join-Path $out "LegacyPlayer-$version-win64.exe"
Copy-Item 'dist\LegacyPlayer.exe' $exe

$sums = @()
foreach ($f in @($zip, $exe)) {
    $hash = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
    $line = "$hash  $(Split-Path $f -Leaf)"
    $line | Set-Content "$f.sha256" -Encoding ASCII
    $sums += $line
    Write-Host $line
}
$sums | Set-Content (Join-Path $out 'SHA256SUMS.txt') -Encoding ASCII
Write-Host "Built $zip and $exe"
