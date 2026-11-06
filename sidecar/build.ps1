# sidecar/build.ps1 — build the compiled supervisor for this machine.
#
#   .\sidecar\build.ps1
#
# Needs Go installed: https://go.dev/dl/  (one download, one installer).
# The output lands in sidecar\bin\ and is NOT committed: a binary in a repository
# is a file nobody can audit, so the source and this script travel instead.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$sidecar = Join-Path $root "sidecar"
$out = Join-Path $sidecar "bin"

if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
    Write-Host "Go is not installed. Download it from https://go.dev/dl/ and run this again."
    Write-Host "Ultron works without this component; it only loses crash-proof watching."
    exit 1
}

New-Item -ItemType Directory -Force -Path $out | Out-Null
Push-Location $sidecar
try {
    Write-Host "Testing..."
    go test ./...
    if ($LASTEXITCODE -ne 0) { throw "the Go tests failed" }

    Write-Host "Building for Windows..."
    $env:CGO_ENABLED = "0"
    go build -trimpath -ldflags="-s -w" -o (Join-Path $out "watchd-windows.exe") ./watchd
    if ($LASTEXITCODE -ne 0) { throw "the build failed" }

    $exe = Join-Path $out "watchd-windows.exe"
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    $hash = (Get-FileHash $exe -Algorithm SHA256).Hash
    Write-Host "Built $exe ($size MB)"
    Write-Host "SHA256 $hash"
    Write-Host "Ultron will use it on the next start."
} finally {
    Pop-Location
}
