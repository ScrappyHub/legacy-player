<#
.SYNOPSIS
lp - one small command for Legacy Player. Run  .\lp help  for the list.
#>
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [Parameter(Position = 1)][string]$Tag = '',
    [string]$Repo = 'ScrappyHub/legacy-player',
    [string]$Token = "",
    [switch]$NoLaunch
)
$usage = @'
 lp - one small command for Legacy Player (Windows PowerShell or PowerShell 7).

   git clone https://github.com/ScrappyHub/legacy-player
   cd legacy-player
   .\lp install                 download the newest release, check its SHA-256, install it for you (no administrator)
   .\lp install v0.7.18          the same, for one exact version
   .\lp update                  install the newest release over the current one (your saves and settings stay)
   .\lp run                     start the installed app
   .\lp version                 what is installed, and what is the newest
   .\lp path                    where it is installed
   .\lp uninstall               remove the program and its Start menu shortcut (your data stays; the in-app doctor removes that)
   .\lp source                  run straight from this git checkout with Python 3.13+ (no download, for developers)
   .\lp help

 Add  -Repo owner/name  to use a fork, or  -Token <github token>  for a private repository.
'@
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$dest = Join-Path $env:LOCALAPPDATA 'Programs\LegacyPlayer'
$exe = Join-Path $dest 'LegacyPlayer.exe'
$programs = [Environment]::GetFolderPath('Programs')
$lnk = if ($programs) { Join-Path $programs 'Legacy Player.lnk' } else { '' }

function Get-Latest {
    $h = @{ 'User-Agent' = 'LegacyPlayer-lp'; 'Accept' = 'application/vnd.github+json' }
    if ($Token) { $h['Authorization'] = "Bearer $Token" }
    try { (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $h).tag_name } catch { $null }
}
function Get-Installed {
    $f = Join-Path $dest 'VERSION.txt'
    if (Test-Path $f) { (Get-Content $f -Raw).Trim() } elseif (Test-Path $exe) { 'unknown version' } else { $null }
}
function Invoke-Install {
    $script = Join-Path $PSScriptRoot 'install.ps1'
    if (-not (Test-Path $script)) { throw "install.ps1 is missing next to lp.ps1. Clone the repository again: git clone https://github.com/$Repo" }
    $args2 = @{ Repo = $Repo; Token = $Token }
    if ($Tag) { $args2['Tag'] = $Tag }
    if ($NoLaunch) { $args2['NoLaunch'] = $true }
    & $script @args2
}
function Stop-App { Get-Process -Name LegacyPlayer -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null; Start-Sleep 2; if (-not $_.HasExited) { $_.Kill() } } }

switch ($Command.ToLower()) {
    { $_ -in 'install', 'update', 'upgrade' } {
        Invoke-Install
    }
    'run' {
        if (-not (Test-Path $exe)) { throw "Legacy Player is not installed yet. Run:  .\lp install" }
        Start-Process $exe
    }
    'version' {
        $have = Get-Installed
        $latest = Get-Latest
        Write-Host ("Installed: " + $(if ($have) { $have } else { 'not installed' }))
        Write-Host ("Newest:    " + $(if ($latest) { $latest } else { 'could not reach GitHub' }))
        if ($have -and $latest -and $have -ne $latest -and $have -ne 'unknown version') { Write-Host "An update is available:  .\lp update" }
    }
    'path' { Write-Output $dest }
    'uninstall' {
        if (-not (Test-Path $dest)) { Write-Host 'Legacy Player is not installed.'; break }
        if ((Split-Path $dest -Leaf) -ne 'LegacyPlayer') { throw 'Refusing to remove an unexpected folder.' }
        Stop-App
        Remove-Item $dest -Recurse -Force
        if ($lnk) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }
        Write-Host "Removed the program. Your games, saves and settings were not touched."
        Write-Host "To remove those as well, use the doctor in the app (Uninstall Legacy Player) before running this."
    }
    'source' {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { throw 'Python 3.13+ was not found. Install it from python.org (tick "Add to PATH") and try again.' }
        Push-Location $PSScriptRoot                  # the repository folder, wherever the command was typed
        try { & python -m launcher } finally { Pop-Location }
    }
    default { Write-Host $usage }
}
