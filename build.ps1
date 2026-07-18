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
# 1. Find Godot binary
# ────────────────────────────────────────────────────────────
$godot = $null
foreach ($name in @("godot", "godot4")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $godot = $cmd.Source; break }
}

if (-not $godot) {
    # Check common install paths
    $patterns = @(
        "$env:USERPROFILE\Documents\Godot_v4*windows_x86_64.exe",
        "$env:USERPROFILE\Documents\Godot_v4*win64.exe",
        "$env:LOCALAPPDATA\Godot\godot.exe"
    )
    foreach ($pat in $patterns) {
        $match = Get-Item $pat -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) { $godot = $match.FullName; break }
    }
}

if (-not $godot) {
    Err "Godot 4 not found. Install from: https://godotengine.org/download"
}
Log "Using Godot: $godot"

# ────────────────────────────────────────────────────────────
# 2. Export the Godot project
# ────────────────────────────────────────────────────────────
$godotDir = "src/godot"
$buildDir = "build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Info "Exporting Godot project..."

# Check if export preset exists
if (-not (Test-Path "$godotDir/export_presets.cfg")) {
    Info "Creating export_presets.cfg..."
    @'
[preset.0]

name="Windows"
platform="Windows"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""

export_path="tanu.exe"

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=1
binary_format/embed_pck=true
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
ssh_remote_deploy/enabled=false
'@ | Set-Content -Path "$godotDir/export_presets.cfg"
}

& $godot --headless --path $godotDir --export-release "Windows" "$buildDir/tanu-godot.exe"
if ($LASTEXITCODE -ne 0) {
    Err "Export failed. Make sure you have export templates installed.`n  Godot Editor -> Manage Export Templates -> Download"
}

Log "Binary: $buildDir/tanu-godot.exe"

# ────────────────────────────────────────────────────────────
# 3. Summary
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌────────────────────────────────────┐"
Write-Host "  │      Build Complete!               │"
Write-Host "  └────────────────────────────────────┘"
Write-Host ""
Write-Host "  Output: $buildDir/tanu-godot.exe"
Write-Host "  Run:    python main.py desk"
Write-Host ""
