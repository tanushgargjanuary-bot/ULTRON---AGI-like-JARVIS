#!/bin/sh
# sidecar/build.sh — build the compiled supervisor for this machine.
#
#   ./sidecar/build.sh
#
# Needs Go installed: https://go.dev/dl/
# The output lands in sidecar/bin/ and is not committed.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
out="$here/bin"

if ! command -v go >/dev/null 2>&1; then
    echo "Go is not installed. Get it from https://go.dev/dl/ and run this again."
    echo "Ultron works without this component; it only loses crash-proof watching."
    exit 1
fi

mkdir -p "$out"
cd "$here"

echo "Testing..."
go test ./...

echo "Building..."
CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o "$out/watchd-linux" ./watchd

size=$(du -h "$out/watchd-linux" | cut -f1)
echo "Built $out/watchd-linux ($size)"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$out/watchd-linux"
fi
