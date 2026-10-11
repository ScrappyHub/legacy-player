<#
 Installs the latest Legacy Player release for the current user (no administrator needed).

   irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex

 (or, with the repository cloned:  .\lp.cmd install)

 Options (run the file instead of piping):  .\install.ps1 -Tag v0.7.44  -NoLaunch  -Token <github token, for a private repo>
#>
param(
    [string]$Repo = 'Alpallyoop/legacy-player',
    [string]$Tag = '',
    [string]$Token = "",
    [switch]$NoLaunch,
    [string]$Dest = '',
    [switch]$Pause
)

# Run through `irm ... | iex` there is no script file. In that case a failure must never call `exit`
# (that would close the person's PowerShell window before they could read the message), and we
# always wait for Enter so the message stays on screen.
$lpViaIex = -not $PSCommandPath -and -not $MyInvocation.MyCommand.Path

function Install-LegacyPlayer {
    param([string]$Repo, [string]$Tag, [string]$Token, [switch]$NoLaunch, [string]$Dest, [switch]$Pause)
    # Function scope: these do not leak into the caller's session when run through iex.
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'      # Windows PowerShell 5.1 downloads many times slower while drawing the progress bar
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $headers = @{ 'User-Agent' = 'LegacyPlayer-installer'; 'Accept' = 'application/vnd.github+json' }
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }

    $api = if ($Tag) { "https://api.github.com/repos/$Repo/releases/tags/$Tag" } else { "https://api.github.com/repos/$Repo/releases/latest" }
    Write-Host "Looking up the release..."
    try { $release = Invoke-RestMethod -Uri $api -Headers $headers }
    catch { throw "Could not find a release at $api. If the repository is private, pass -Token. ($($_.Exception.Message))" }

    $zipAsset = $release.assets | Where-Object { $_.name -like 'LegacyPlayer-*-win64.zip' } | Select-Object -First 1
    $sumAsset = $release.assets | Where-Object { $_.name -like 'LegacyPlayer-*-win64.zip.sha256' } | Select-Object -First 1
    if (-not $zipAsset) { throw "Release $($release.tag_name) has no Windows package." }

    $tmp = Join-Path $env:TEMP ("legacyplayer-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $dl = @{ 'User-Agent' = 'LegacyPlayer-installer'; 'Accept' = 'application/octet-stream' }
        if ($Token) { $dl['Authorization'] = "Bearer $Token" }
        $zip = Join-Path $tmp $zipAsset.name
        Write-Host "Downloading $($zipAsset.name) ($([math]::Round($zipAsset.size / 1MB, 1)) MB)..."
        Invoke-WebRequest -Uri $zipAsset.url -Headers $dl -OutFile $zip -UseBasicParsing

        if ($sumAsset) {
            $sumFile = Join-Path $tmp $sumAsset.name
            Invoke-WebRequest -Uri $sumAsset.url -Headers $dl -OutFile $sumFile -UseBasicParsing
            $expected = ((Get-Content -LiteralPath $sumFile -Raw).Trim() -split '\s+')[0].ToLower()
            $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
            if ($expected -ne $actual) { throw "The download is damaged or was changed (checksum mismatch). Nothing was installed." }
            Write-Host "Checksum OK."
        } else { throw "This release has no checksum file, so I can not check the download. Nothing was installed." }

        # -Dest lets a caller install somewhere other than the usual per-user folder.
        $dest = if ($Dest) { $Dest } else { Join-Path $env:LOCALAPPDATA 'Programs\LegacyPlayer' }
        $stuck = @()
        foreach ($p in @(Get-Process -Name LegacyPlayer -ErrorAction SilentlyContinue)) {
            Write-Host "Closing the running Legacy Player (process $($p.Id))..."
            try {
                $p.CloseMainWindow() | Out-Null
                Start-Sleep 2
                if (-not $p.HasExited) { $p.Kill(); $p.WaitForExit(5000) | Out-Null }
                if (-not $p.HasExited) { $stuck += $p.Id }
            } catch { $stuck += $p.Id }
        }
        if ($stuck.Count) { Write-Host "Could not close Legacy Player process(es) $($stuck -join ', '). If copying fails, close it yourself and run this again." -ForegroundColor Yellow }
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        $stage = Join-Path $tmp 'unpacked'
        Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force          # unpack aside first, so a bad archive never leaves a half-installed app
        $sigExe = Join-Path $stage 'LegacyPlayer.exe'
        if (Test-Path -LiteralPath $sigExe) {
            $sig = Get-AuthenticodeSignature -LiteralPath $sigExe
            if ($sig.Status -eq 'Valid') { Write-Host "Code signature OK: $($sig.SignerCertificate.Subject)" }
            elseif ($sig.Status -eq 'NotSigned') { Write-Host "Note: this release is not code-signed, so only the download was checked, not who published it." }
            else { throw "The program's signature is $($sig.Status) (tampered or untrusted). Nothing was installed." }
        }
        Get-ChildItem -LiteralPath $stage -Force | Copy-Item -Destination $dest -Recurse -Force
        Get-ChildItem -LiteralPath $dest -Recurse -File | Unblock-File

        $release.tag_name | Set-Content -LiteralPath (Join-Path $dest 'VERSION.txt') -Encoding ASCII   # so `lp version` can say what is installed
        $exe = Join-Path $dest 'LegacyPlayer.exe'
        $shell = New-Object -ComObject WScript.Shell
        $lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Legacy Player.lnk'
        $shortcut = $shell.CreateShortcut($lnk); $shortcut.TargetPath = $exe; $shortcut.WorkingDirectory = $dest; $shortcut.Save()
        Write-Host "Installed Legacy Player $($release.tag_name) to $dest (Start menu: Legacy Player)."
        Write-Host "Windows may warn that the app is from an unknown publisher: choose More info > Run anyway."
        if ($Pause) { Write-Host "Now running $($release.tag_name). Starting it..."; Start-Sleep 2 }
        if (-not $NoLaunch) { Start-Process -FilePath $exe }
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$lpFailed = $false
try {
    Install-LegacyPlayer -Repo $Repo -Tag $Tag -Token $Token -NoLaunch:$NoLaunch -Dest $Dest -Pause:$Pause
} catch {
    $lpFailed = $true
    Write-Host ''
    Write-Host "The update did not finish: $($_.Exception.Message)" -ForegroundColor Red
    if ($Pause -or $lpViaIex) { Read-Host 'Press Enter to continue' | Out-Null }
}
# Only a script file may set an exit code; through iex `exit` would close the window.
if ($lpFailed -and -not $lpViaIex) { exit 1 }
