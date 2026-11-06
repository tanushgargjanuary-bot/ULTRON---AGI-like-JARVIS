#Requires -Version 5.1
<#
.SYNOPSIS
    Ultron launcher for PowerShell.

.DESCRIPTION
    The same job run.bat does, in PowerShell: make sure this folder holds a usable
    app-local Python environment (.venv), install whatever is missing, then start
    Ultron. Nothing is installed outside this folder, and no system Python is
    modified.

    If .venv already exists it is reused as-is - this launcher never upgrades an
    existing environment, because "it worked yesterday" is worth more than "it is
    current today".

.EXAMPLE
    .\run.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run.ps1

.NOTES
    If PowerShell refuses to run this file, that is the execution policy:

        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

    If the ZIP came from a download, the extracted file may be blocked:

        Unblock-File .\run.ps1

    PyQt6 is pinned below 6.12 in requirements.txt on purpose: Qt 6.12 crashes while
    building the HUD's audio output on machines with no working audio backend.
#>

$ErrorActionPreference = 'Continue'

try {
    $Host.UI.RawUI.WindowTitle = 'Ultron - built on MARK LVI'
} catch {
    # Hosts without a title bar (ISE, remoting) reject this. Not worth failing over.
}

$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
Set-Location -LiteralPath $here

$supported = '3.11 through 3.13'

if (-not (Test-Path -LiteralPath (Join-Path $here 'main.py') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path (Join-Path $here 'scripts') 'bootstrap.py') -PathType Leaf)) {
    Write-Host 'Extract the complete ZIP into a folder before running run.ps1.' -ForegroundColor Red
    Write-Host 'Startup failed. Read the message above. Do not share logs containing API keys.'
    exit 1
}

$venvPython = Join-Path $here '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host "Creating the app-local environment (Python $supported)."

    $probe = 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))'
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'py'; Args = @('-3.11') },
        @{ Exe = 'python'; Args = @() }
    )

    $creator = $null
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) {
            continue
        }
        $command = $candidate.Exe
        $arguments = @($candidate.Args) + @('-c', $probe)
        try {
            & $command @arguments 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $creator = $candidate
                break
            }
        } catch {
            # A candidate that cannot start is simply not the one.
        }
    }

    if (-not $creator) {
        Write-Host 'Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/' -ForegroundColor Red
        Write-Host 'Enable "Add python.exe to PATH", then run this file again.'
        Write-Host 'Python 3.14 is not supported by this launcher; it will not try a risky setup.'
        Write-Host 'Startup failed. Read the message above. Do not share logs containing API keys.'
        exit 1
    }

    $command = $creator.Exe
    $arguments = @($creator.Args) + @('-m', 'venv', '.venv')
    try {
        & $command @arguments
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
    }

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host 'Could not create the app-local environment. Extract into a writable folder.' -ForegroundColor Red
        Write-Host 'Startup failed. Read the message above. Do not share logs containing API keys.'
        exit 1
    }
}

try {
    & $venvPython (Join-Path (Join-Path $here 'scripts') 'bootstrap.py')
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host ''
        Write-Host 'Startup failed. Read the message above. Do not share logs containing API keys.' -ForegroundColor Red
        exit $code
    }

    & $venvPython (Join-Path $here 'main.py')
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host ''
        Write-Host 'Ultron exited with an error. Read the message above.' -ForegroundColor Red
        Write-Host 'Do not share logs containing API keys.'
        exit $code
    }
} finally {
    # Keep the window legible when launched from Explorer rather than a shell.
    if ($Host.Name -eq 'ConsoleHost' -and -not [Console]::IsInputRedirected) {
        $failed = $false
        try { $failed = ($LASTEXITCODE -ne 0) } catch { $failed = $false }
        if ($failed) {
            try { [void](Read-Host 'Press Enter to close') } catch { }
        }
    }
}

exit 0
