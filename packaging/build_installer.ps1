<#
.SYNOPSIS
    Build UltronSetup.exe from this folder.

.DESCRIPTION
    Three steps, in order, each one able to stop the build with a sentence that
    says what to do next:

        1. read the version and the payload list;
        2. copy exactly what packaging/payload.txt names into build\stage;
        3. hand the folder to Inno Setup, which writes UltronSetup-<version>.exe.

    Nothing is downloaded and nothing is installed on this machine. The installer
    it produces needs no administrator password, because Ultron installs into the
    user's own folder.

.PARAMETER InnoSetup
    Path to ISCC.exe. If left out, the usual install locations are searched, and
    then the PATH.

.PARAMETER SkipStage
    Reuse the files already in build\stage instead of copying them again. Useful
    while editing the .iss file, which is the slow, fiddly part.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -InnoSetup 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'

.NOTES
    Inno Setup is free and separate from Python: https://jrsoftware.org/isdl.php
    Windows only. The .iss file cannot be compiled anywhere else.
#>

[CmdletBinding()]
param(
    [string]$InnoSetup = '',
    [switch]$SkipStage
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$packaging = Join-Path $root 'packaging'
$stage = Join-Path $root 'build\stage'
$output = Join-Path $root 'build\installer'

function Stop-With ([string]$message, [string]$next) {
    Write-Host ''
    Write-Host $message -ForegroundColor Red
    if ($next) { Write-Host $next -ForegroundColor Yellow }
    exit 1
}

# ── 1. version ────────────────────────────────────────────────────────────────
$versionFile = Join-Path $packaging 'version.txt'
if (-not (Test-Path -LiteralPath $versionFile)) {
    Stop-With 'packaging\version.txt is missing.' 'Restore it: it holds the one version number the installer reads.'
}
$version = (Get-Content -LiteralPath $versionFile -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    Stop-With "packaging\version.txt says '$version'." 'It must be three numbers, like 1.2.27.'
}
Write-Host "Building Ultron $version" -ForegroundColor Cyan

# ── 2. stage exactly what the payload list names ───────────────────────────────
$payloadFile = Join-Path $packaging 'payload.txt'
if (-not (Test-Path -LiteralPath $payloadFile)) {
    Stop-With 'packaging\payload.txt is missing.' 'It is the list of files the installer ships.'
}

if (-not $SkipStage) {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    $copied = 0
    foreach ($raw in Get-Content -LiteralPath $payloadFile) {
        $line = $raw.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith('#')) { continue }
        $relative = $line.TrimEnd('/')
        $source = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $source)) {
            Stop-With "payload.txt names '$relative', which is not in this folder." 'Fix the list, or restore the file. A build must not ship a half-folder.'
        }
        $target = Join-Path $stage $relative
        $parent = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        if (Test-Path -LiteralPath $source -PathType Container) {
            Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
        } else {
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
        $copied++
    }
    Write-Host "Staged $copied entries into build\stage" -ForegroundColor Cyan

    # A staged folder that grew a .git or a .venv means somebody copied too much.
    foreach ($unwanted in @('.git', '.venv', '__pycache__')) {
        $found = Get-ChildItem -LiteralPath $stage -Recurse -Force -Directory -Filter $unwanted -ErrorAction SilentlyContinue
        if ($found) {
            Stop-With "build\stage contains $unwanted." 'The payload list is copying too much. Fix it before shipping.'
        }
    }
}

# ── 3. compile ────────────────────────────────────────────────────────────────
if (-not $InnoSetup) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { $InnoSetup = $candidate; break }
    }
    if (-not $InnoSetup) {
        $onPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($onPath) { $InnoSetup = $onPath.Source }
    }
}
if (-not $InnoSetup -or -not (Test-Path -LiteralPath $InnoSetup)) {
    Stop-With 'Inno Setup was not found.' 'Install it from https://jrsoftware.org/isdl.php, then run this script again.'
}

if (-not (Test-Path -LiteralPath $output)) { New-Item -ItemType Directory -Path $output -Force | Out-Null }
$iss = Join-Path $packaging 'ultron.iss'
Write-Host "Compiling with $InnoSetup" -ForegroundColor Cyan
& $InnoSetup "/DAppVersion=$version" $iss
if ($LASTEXITCODE -ne 0) {
    Stop-With "Inno Setup exited with $LASTEXITCODE." 'Read the error above: it names the line in ultron.iss that is wrong.'
}

$built = Get-ChildItem -LiteralPath $output -Filter 'UltronSetup-*.exe' |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $built) {
    Stop-With 'Inno Setup reported success but no installer appeared.' "Look in $output."
}
$sizeMb = [math]::Round($built.Length / 1MB, 1)
Write-Host ''
Write-Host "Built $($built.Name) — $sizeMb MB" -ForegroundColor Green
Write-Host "  $($built.FullName)"
Write-Host ''
Write-Host 'To check it: run it on a machine that has never had Ultron.' -ForegroundColor Yellow
Write-Host 'It should install without an administrator prompt, then open the setup screen.'
