<#
 Builds the release files on a Windows computer with Python 3.13+:   powershell -ExecutionPolicy Bypass -File tools\package_release.ps1
 Output (in dist\release):
   LegacyPlayer-<version>-win64.zip      the exe plus a READ ME, what the installer downloads
   LegacyPlayer-<version>-win64.exe      the bare exe, for people who just want the one file
   each of the two with a .sha256 next to it, and SHA256SUMS.txt listing both
#>
param([switch]$BuildOnly, [switch]$SkipBuild)     # the release workflow builds, signs the exe with Azure, then packages
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$version = (Select-String -Path 'launcher\version.py' -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Packaging Legacy Player $version"

# build_exe.bat does the PyInstaller build (LP_LOGGED=1 skips its log-and-pause wrapper)
if (-not $SkipBuild) {
    $env:LP_LOGGED = '1'
    cmd /c "build_exe.bat"
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path 'dist\LegacyPlayer.exe')) { throw 'The build failed; see the output above.' }
if ($BuildOnly) { Write-Host 'Built dist\LegacyPlayer.exe (not packaged yet).'; exit 0 }

# Code signing: when a certificate is supplied (LP_SIGN_PFX_BASE64 = the .pfx file as base64, LP_SIGN_PFX_PASSWORD), the exe is
# signed and time-stamped BEFORE it is zipped and hashed. Without one the build still works and is plainly marked unsigned.
$signed = $false
$already = (Get-AuthenticodeSignature 'dist\LegacyPlayer.exe').SignerCertificate -ne $null     # build_exe.bat signs when LP_SIGN_PFX is set
if ($already) {
    $signed = $true
    Write-Host 'The exe was already signed by the build.'
} elseif ($env:LP_SIGN_PFX_BASE64) {
    $pfx = Join-Path $env:RUNNER_TEMP 'lp-sign.pfx'
    if (-not $env:RUNNER_TEMP) { $pfx = Join-Path ([IO.Path]::GetTempPath()) 'lp-sign.pfx' }
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:LP_SIGN_PFX_BASE64))
    try {
        $cert = Get-PfxCertificate -FilePath $pfx -Password (ConvertTo-SecureString $env:LP_SIGN_PFX_PASSWORD -AsPlainText -Force)
        $sig = Set-AuthenticodeSignature -FilePath 'dist\LegacyPlayer.exe' -Certificate $cert -HashAlgorithm SHA256 `
               -TimestampServer ($(if ($env:LP_SIGN_TIMESTAMP_URL) { $env:LP_SIGN_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }))
        $check = Get-AuthenticodeSignature 'dist\LegacyPlayer.exe'
        if ($check.SignerCertificate -eq $null -or $check.TimeStamperCertificate -eq $null) { throw "Signing failed: $($sig.StatusMessage)" }
        $signed = $true
        Write-Host "Signed by $($check.SignerCertificate.Subject) (status: $($check.Status))"
    } finally { Remove-Item $pfx -Force -ErrorAction SilentlyContinue }
} else {
    Write-Host 'No signing certificate given: the exe is NOT code-signed (Windows will show "unknown publisher").'
}

$out = 'dist\release'
$stage = Join-Path $out 'stage'
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item 'dist\LegacyPlayer.exe' $stage
Copy-Item 'LICENSE' $stage -ErrorAction SilentlyContinue
$signNote = if ($signed) { 'This build is code-signed.' } else { 'Windows may say it is from an unknown publisher (this build is not code-signed): choose More info > Run anyway. You can check the file against SHA256SUMS.txt on the release page.' }
@"
Legacy Player $version
Double-click LegacyPlayer.exe. $signNote Your data is kept in %USERPROFILE%\.legacy-player.
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
