#!/usr/bin/env pwsh
#Requires -Version 7.0

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Log  { Write-Host "[✓] $args" -ForegroundColor Green }
function Warn { Write-Host "[!] $args" -ForegroundColor Yellow }
function Err  { Write-Host "[✗] $args" -ForegroundColor Red; exit 1 }
function Info { Write-Host "[i] $args" -ForegroundColor Cyan }

Write-Host ""
Write-Host "  ┌────────────────────────────────────┐"
Write-Host "  │      Tanu — Build App (Windows)    │"
Write-Host "  └────────────────────────────────────┘"
Write-Host ""

# ────────────────────────────────────────────────────────────
# 1. Detect target triple
# ────────────────────────────────────────────────────────────
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Err "Rust not found. Install it first: https://rustup.rs"
}

$targetTriple = &rustc -vV | Select-String "host" | ForEach-Object { $_ -replace 'host: ', '' }
Log "Target: $targetTriple"

$suffix = if ($targetTriple -match "windows") { ".exe" } else { "" }

# ────────────────────────────────────────────────────────────
# 2. Activate / create virtual environment
# ────────────────────────────────────────────────────────────
$python = "python"
if (-not (Test-Path venv)) {
    Info "Creating virtual environment..."
    & $python -m venv venv
}

. .\venv\Scripts\Activate.ps1
Log "Virtual environment activated"

# ────────────────────────────────────────────────────────────
# 3. Install build dependencies
# ────────────────────────────────────────────────────────────
Info "Installing build dependencies (pyinstaller)..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller -r requirements.txt
Log "Build dependencies installed"

# ────────────────────────────────────────────────────────────
# 4. Build Python server binary with PyInstaller
# ────────────────────────────────────────────────────────────
$sidecarDir = "src/ui/src-tauri/binaries"
$sidecarBin = "$sidecarDir/tanu-$targetTriple$suffix"

Info "Building Python server binary (PyInstaller)..."
New-Item -ItemType Directory -Force -Path $sidecarDir | Out-Null

$hiddenImports = @(
    "bujji.server",
    "bujji.agent",
    "bujji.session",
    "bujji.config",
    "bujji.identity",
    "bujji.tools.base",
    "bujji.tools.shell",
    "bujji.tools.web",
    "bujji.tools.file_ops",
    "bujji.tools.memory",
    "bujji.tools.subagents",
    "bujji.tools.todo",
    "bujji.tools.utils",
    "tanu.config",
    "tanu.tools.gmail",
    "tanu.tools.speak_tool",
    "tanu.tools.tanu_query",
    "tanu.tools.tanu_task",
    "tanu.tools.tanu_reminder"
)

$pyiArgs = @(
    "--noconfirm", "--clean",
    "--onefile",
    "--name", "tanu",
    "--distpath", $sidecarDir,
    "--paths", "src",
    "--paths", "bujji"
)
foreach ($hi in $hiddenImports) {
    $pyiArgs += "--hidden-import"
    $pyiArgs += $hi
}
$pyiArgs += "scripts/build_server.py"

pyinstaller @pyiArgs

# Rename to include target triple
$pyiOutput = "$sidecarDir/tanu$suffix"
if (Test-Path $pyiOutput -and $pyiOutput -ne $sidecarBin) {
    Move-Item -Force $pyiOutput $sidecarBin
}
Log "Server binary: $sidecarBin"

# ────────────────────────────────────────────────────────────
# 5. Build Tauri desktop app
# ────────────────────────────────────────────────────────────
Info "Building Tauri desktop app..."
Set-Location src/ui

if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
    Info "Installing Tauri CLI..."
    cargo install tauri-cli --version "^2"
}

cargo tauri build
Set-Location $RepoRoot
Log "Tauri desktop app built"

# ────────────────────────────────────────────────────────────
# 6. Collect artifacts to binary/
# ────────────────────────────────────────────────────────────
$bundleDir = "src/ui/src-tauri/target/release/bundle"
$outDir = "binary"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# Copy bundle artifacts
if (Test-Path $bundleDir) {
    foreach ($fmt in @("msi", "nsis", "wix")) {
        $fmtDir = "$bundleDir/$fmt"
        if (Test-Path $fmtDir) {
            Copy-Item -Path "$fmtDir/*" -Destination $outDir -Force -ErrorAction SilentlyContinue
        }
    }
    Log "Artifacts copied to $outDir/"
}

# Also copy the raw executable
$rawBin = "src/ui/src-tauri/target/release/tanu.exe"
if (Test-Path $rawBin) {
    Copy-Item -Path $rawBin -Destination $outDir/ -Force
    Log "Binary copied to $outDir/tanu.exe"
}

# Copy the sidecar server binary
if (Test-Path $sidecarBin) {
    Copy-Item -Path $sidecarBin -Destination $outDir/ -Force
    Log "Server binary copied to $outDir/"
}

# ────────────────────────────────────────────────────────────
# 7. Summary
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌────────────────────────────────────┐"
Write-Host "  │      Build Complete!               │"
Write-Host "  └────────────────────────────────────┘"
Write-Host ""
Write-Host "  ${CYAN}Output:${NC}"
Get-ChildItem $outDir | ForEach-Object { Write-Host "    $($_.Name) ($( [math]::Round($_.Length/1MB, 2) ) MB)" }
Write-Host ""
Write-Host "  ${CYAN}Install:${NC}"
Write-Host "    Install the package from binary\ on your target machine."
Write-Host ""
