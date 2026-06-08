#!/usr/bin/env pwsh
#Requires -Version 7.0

param(
    [switch]$NoSystemDeps
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Log  { Write-Host "[✓] $args" -ForegroundColor Green }
function Warn { Write-Host "[!] $args" -ForegroundColor Yellow }
function Err  { Write-Host "[✗] $args" -ForegroundColor Red; exit 1 }
function Info { Write-Host "[i] $args" -ForegroundColor Cyan }

Write-Host ""
Write-Host "  ┌────────────────────────────────────┐"
Write-Host "  │      Tanu — Dev Setup (Windows)    │"
Write-Host "  └────────────────────────────────────┘"
Write-Host ""

# ────────────────────────────────────────────────────────────
# 1. Check prerequisites
# ────────────────────────────────────────────────────────────
Info "Checking prerequisites..."

$python = $null
foreach ($cmd in @("python3", "python")) {
    $ver = &$cmd --version 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver -match '(\d+)\.(\d+)') {
        if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 9) {
            $python = $cmd
            break
        }
    }
}
if (-not $python) {
    # Check Microsoft Store Python
    $storePy = Get-Command "python3.exe" -ErrorAction SilentlyContinue
    if ($storePy) { $python = "python3" }
}
if (-not $python) {
    Err "Python >= 3.9 not found. Install from: https://python.org"
}
Log "Python: $(& $python --version)"

if (Get-Command rustc -ErrorAction SilentlyContinue) {
    Log "Rust:   $(rustc --version)"
} else {
    $script:RustInstalled = $false
}

if (Get-Command cargo -ErrorAction SilentlyContinue) {
    Log "Cargo:  $(cargo --version)"
}

# ────────────────────────────────────────────────────────────
# 2. Install system dependencies
# ────────────────────────────────────────────────────────────
if (-not $NoSystemDeps) {
    Info "Checking system dependencies..."
    
    $hasVS = $false
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $vsPath = &$vswhere -latest -property installationPath 2>$null
        if ($vsPath) { $hasVS = $true }
    }

    if (-not $hasVS) {
        Warn "Visual Studio Build Tools not detected."
        Warn "  Install via winget (recommended):"
        Warn "    winget install Microsoft.VisualStudio.2022.BuildTools"
        Warn "  Or manually: https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        Warn "  (Select 'Desktop development with C++' workload)"
        Warn ""
        $choice = Read-Host "Attempt winget install? (y/N)"
        if ($choice -eq 'y') {
            winget install Microsoft.VisualStudio.2022.BuildTools --override "--add Microsoft.VisualStudio.Workload.VCTools;includeRecommended"
        }
    } else {
        Log "Visual Studio Build Tools detected"
    }
} else {
    Warn "Skipping system deps check (-NoSystemDeps)"
}

# ────────────────────────────────────────────────────────────
# 3. Install Rust + Tauri CLI
# ────────────────────────────────────────────────────────────
if ($script:RustInstalled -eq $false) {
    Info "Installing Rust via rustup..."
    Invoke-WebRequest -Uri https://sh.rustup.rs -OutFile "$env:TEMP\rustup-init.exe"
    & "$env:TEMP\rustup-init.exe" -y
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\.cargo\bin"
    Log "Rust installed: $(rustc --version)"
}

if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
    Info "Installing Tauri CLI (cargo install tauri-cli)..."
    cargo install tauri-cli --version "^2"
    Log "Tauri CLI installed: $(cargo tauri --version)"
} else {
    Log "Tauri CLI: $(cargo tauri --version)"
}

# ────────────────────────────────────────────────────────────
# 4. Initialize git submodules
# ────────────────────────────────────────────────────────────
if (Test-Path .gitmodules) {
    Info "Initializing git submodules..."
    git submodule update --init --recursive
    Log "Submodules initialized"
}

# ────────────────────────────────────────────────────────────
# 5. Create Python virtual environment
# ────────────────────────────────────────────────────────────
if (Test-Path venv) {
    Warn "Virtual environment 'venv' already exists (skipping)"
} else {
    Info "Creating Python virtual environment..."
    & $python -m venv venv
    Log "Virtual environment created"
}

$venvActivate = if ($IsWindows) { ".\venv\Scripts\Activate.ps1" } else { "./venv/bin/activate" }
. $venvActivate
Log "Virtual environment activated"

Info "Installing Python dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
Log "Python dependencies installed"

# ────────────────────────────────────────────────────────────
# 6. Create local config if missing
# ────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path config | Out-Null

if (-not (Test-Path config/config.json)) {
    Info "Creating default config/config.json..."
    @'
{
  "active_provider": "",
  "agents": {
    "defaults": {
      "workspace": "workspace",
      "model": "",
      "max_tokens": 8192,
      "temperature": 0.7,
      "max_tool_iterations": 20,
      "restrict_to_workspace": false
    }
  },
  "providers": {},
  "channels": {
    "telegram": { "enabled": false, "token": "", "allow_from": [] },
    "discord":  { "enabled": false, "token": "", "allow_from": [] }
  },
  "tool_paths": [
    { "path": "src/tanu/tools", "package": "tanu.tools" }
  ],
  "tools": {
    "web": { "search": { "api_key": "", "max_results": 5 } },
    "gmail": { "client_creds": "" }
  }
}
'@ | Set-Content -Path config/config.json
    Log "config/config.json created — run 'python main.py onboard' to configure"
} else {
    Warn "config/config.json already exists (keeping as-is)"
}

# ────────────────────────────────────────────────────────────
# 7. Create workspace directories
# ────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path workspace/tanu | Out-Null

foreach ($f in @("SOUL.md", "IDENTITY.md", "USER.md", "AGENT.md", "HEARTBEAT.md", "BACKSTORY.md")) {
    $path = "workspace/$f"
    if (-not (Test-Path $path)) {
        "# $f`r`n" | Set-Content -Path $path
    }
}

Log "Workspace directories ready"

# ────────────────────────────────────────────────────────────
# 8. Summary & next steps
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌────────────────────────────────────┐"
Write-Host "  │      Setup Complete!               │"
Write-Host "  └────────────────────────────────────┘"
Write-Host ""
Write-Host "  ${CYAN}Activate environment:${NC}"
Write-Host "    .\venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "  ${CYAN}Run configuration wizard:${NC}"
Write-Host "    python main.py onboard"
Write-Host ""
Write-Host "  ${CYAN}Launch desktop app:${NC}"
Write-Host "    python main.py desk"
Write-Host ""
Write-Host "  ${CYAN}Other commands:${NC}"
Write-Host "    python main.py serve    — Web UI only"
Write-Host "    python main.py agent   — Terminal chat"
Write-Host "    python main.py tanu    — Voice assistant"
Write-Host "    python main.py status  — Show config & status"
Write-Host ""
