#Requires -Version 5.1
<#
.SYNOPSIS
    Ultron data collector - PowerShell launcher.

.DESCRIPTION
    Runs scripts\collect_install.py with the same flags the .bat launcher accepts.
    Flags are passed straight through, so every example in the docs works unchanged.

    The collector needs nothing but Python's standard library: no PyQt6, no
    third-party packages, no API key. It reads an install folder, classifies every
    file (code / doc / cache / config / data / unknown), fingerprints it so the next
    run can report NEW, CHANGED and GONE, and optionally writes a ZIP of the data
    files only, with credential values blanked.

    It never uploads anything, never deletes anything, never follows a symlink out
    of the folder it was given, and never prints the value of a key or the contents
    of a memory file.

.EXAMPLE
    .\collect-data.ps1

    Scan the default folder (D:\Downloads\mark-custom-jarvis) and remember fingerprints.

.EXAMPLE
    .\collect-data.ps1 --path "D:\Downloads\mark-custom-jarvis" --bundle data.zip

    Scan a specific folder and write one ZIP holding only the data files.

.EXAMPLE
    .\collect-data.ps1 --json | Set-Content -Encoding utf8 report.json

    Machine-readable report. Note the explicit -Encoding: Windows PowerShell 5.1
    writes UTF-16LE by default, which some tools then fail to read.

.EXAMPLE
    .\collect-data.ps1 --watch --interval 5

    Print files as they appear, until Ctrl+C. Useful while the app is running.

.NOTES
    If PowerShell refuses to run this file, that is the execution policy, not the
    script. Either of these is enough:

        powershell -ExecutionPolicy Bypass -File .\collect-data.ps1

        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

    If the ZIP came from a download, the extracted file may carry the mark of the
    web and be blocked even with the policy set:

        Unblock-File .\collect-data.ps1
#>

$ErrorActionPreference = 'Continue'

# Python's stdout on a Windows console is UTF-16-aware; this keeps redirected
# output (pipes, files) from falling back to a codepage the report cannot encode.
try {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
    $env:PYTHONIOENCODING = 'utf-8'
} catch {
    # A host without a real console (ISE, some CI runners) can refuse this. Harmless.
}

# $PSScriptRoot is empty only when the script is dot-sourced oddly; fall back.
$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Definition
}

$scriptPath = Join-Path (Join-Path $here 'scripts') 'collect_install.py'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    Write-Host 'collect_install.py is missing from scripts\.' -ForegroundColor Red
    Write-Host 'Extract the complete ZIP into one folder, then run this file from that folder.'
    exit 3
}

function Resolve-CollectorPython {
    # Prefer the app-local environment: it is the interpreter the app itself uses,
    # so what the collector sees is what Ultron sees.
    $venv = Join-Path $here '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venv -PathType Leaf) {
        return $venv
    }

    # Otherwise any working Python 3.8+ will do - the collector is stdlib only.
    $probe = 'import sys; sys.exit(not (sys.version_info[:2] >= (3, 8)))'
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'py'; Args = @('-3.11') },
        @{ Exe = 'py'; Args = @('-3') },
        @{ Exe = 'python'; Args = @() },
        @{ Exe = 'python3'; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }
        $command = $candidate.Exe
        $arguments = @($candidate.Args) + @('-c', $probe)
        try {
            & $command @arguments 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return $command
            }
        } catch {
            # A candidate that cannot even start is simply not the one.
        }
    }
    return $null
}

$python = Resolve-CollectorPython
if (-not $python) {
    Write-Host 'No usable Python was found.' -ForegroundColor Red
    Write-Host 'Install 64-bit Python 3.11-3.13 from https://www.python.org/downloads/windows/,'
    Write-Host 'tick "Add python.exe to PATH", then run this file again.'
    Write-Host 'Or run run.bat once: it creates the .venv this script prefers.'
    exit 3
}

Push-Location -LiteralPath $here
try {
    & $python $scriptPath @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

# A non-zero exit is the interesting case, so do not let it scroll away when this
# was launched by right-click > Run with PowerShell. Success never waits.
if ($code -ne 0) {
    Write-Host ''
    Write-Host "Collector exited with code $code." -ForegroundColor Yellow
    if ($Host.Name -eq 'ConsoleHost' -and -not [Console]::IsInputRedirected) {
        try { [void](Read-Host 'Press Enter to close') } catch { }
    }
}

exit $code
