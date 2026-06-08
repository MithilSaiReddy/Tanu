#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

echo ""
echo "  ┌────────────────────────────────────┐"
echo "  │      Tanu — Dev Setup              │"
echo "  └────────────────────────────────────┘"
echo ""

# ─────────────────────────────────────────────────────────────
# 1. Detect OS
# ─────────────────────────────────────────────────────────────
OS=""
case "$(uname -s)" in
    Linux*)  OS="linux" ;;
    Darwin*) OS="macos" ;;
    MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
    *)       err "Unsupported OS: $(uname -s)"; exit 1 ;;
esac
info "Detected OS: ${OS}"

if [ "$OS" = "linux" ]; then
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO="$ID"
    else
        DISTRO="unknown"
    fi
    info "Detected distro: ${DISTRO}"
fi

# ─────────────────────────────────────────────────────────────
# 2. Check prerequisites
# ─────────────────────────────────────────────────────────────
info "Checking prerequisites..."

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        if awk "BEGIN { exit ($ver < 3.9) }"; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python >= 3.9 not found. Install it first."
    exit 1
fi
log "Python: $($PYTHON --version)"

if command -v rustc &>/dev/null; then
    log "Rust:   $(rustc --version)"
else
    RUST_INSTALLED=false
fi

if command -v cargo &>/dev/null; then
    log "Cargo:  $(cargo --version)"
fi

# ─────────────────────────────────────────────────────────────
# 3. Install system dependencies
# ─────────────────────────────────────────────────────────────
install_sysdeps() {
    info "Installing system dependencies..."
    if [ "$OS" = "linux" ]; then
        info "sudo access required for system packages"
        case "${DISTRO:-}" in
            debian|ubuntu|pop|mint|elementary|zorin)
                sudo apt update
                sudo apt install -y build-essential libwebkit2gtk-4.1-dev \
                    libgtk-3-dev libayatana-appindicator3-dev \
                    librsvg2-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev \
                    portaudio19-dev pulseaudio
                ;;
            fedora)
                sudo dnf groupinstall -y "C Development Tools and Libraries"
                sudo dnf install -y webkit2gtk4.1-devel gtk3-devel \
                    libappindicator-gtk3-devel librsvg2-devel \
                    libsoup3-devel javascriptcoregtk4.1-devel \
                    portaudio-devel pulseaudio
                ;;
            arch|manjaro|endeavour)
                sudo pacman -S --needed base-devel webkit2gtk-4.1 gtk3 \
                    libappindicator-gtk3 librsvg libsoup3 \
                    portaudio pulseaudio
                ;;
            opensuse*|suse)
                sudo zypper install -y -t pattern devel_basis
                sudo zypper install -y webkit2gtk4_1-devel gtk3-devel \
                    libappindicator-gtk3-devel librsvg-devel \
                    libsoup3-devel javascriptcoregtk4_1-devel \
                    portaudio-devel pulseaudio
                ;;
            *)
                warn "Unknown distro. Install Tauri deps manually:"
                warn "  https://v2.tauri.app/start/prerequisites/"
                ;;
        esac
    elif [ "$OS" = "macos" ]; then
        if ! command -v xcode-select &>/dev/null; then
            xcode-select --install
        fi
        if command -v brew &>/dev/null; then
            brew install portaudio
        fi
    elif [ "$OS" = "windows" ]; then
        warn "Skip system deps — install manually if needed:"
        warn "  1. Visual Studio Build Tools (with C++ workload)"
        warn "     https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        warn "  2. WebView2 (included in Win 10 1803+)"
        warn "     https://developer.microsoft.com/microsoft-edge/webview2/"
        warn ""
        warn "    Or install via winget (recommended):"
        warn "      winget install Microsoft.VisualStudio.2022.BuildTools"
    fi
}

if [ "$OS" = "linux" ] && [ "${DISTRO:-}" != "unknown" ]; then
    install_sysdeps
elif [ "$OS" = "macos" ] || [ "$OS" = "windows" ]; then
    install_sysdeps
fi

# ─────────────────────────────────────────────────────────────
# 4. Install Rust + Tauri CLI
# ─────────────────────────────────────────────────────────────
if [ "${RUST_INSTALLED:-}" = "false" ]; then
    info "Installing Rust via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    log "Rust installed: $(rustc --version)"
fi

if ! command -v cargo-tauri &>/dev/null; then
    info "Installing Tauri CLI (cargo install tauri-cli)..."
    cargo install tauri-cli --version "^2"
    log "Tauri CLI installed: $(cargo tauri --version)"
else
    log "Tauri CLI: $(cargo tauri --version)"
fi

# ─────────────────────────────────────────────────────────────
# 5. Initialize git submodules
# ─────────────────────────────────────────────────────────────
if [ -f .gitmodules ]; then
    info "Initializing git submodules..."
    git submodule update --init --recursive
    log "Submodules initialized"
fi

# ─────────────────────────────────────────────────────────────
# 6. Create Python virtual environment
# ─────────────────────────────────────────────────────────────
if [ -d venv ]; then
    warn "Virtual environment 'venv' already exists (skipping)"
else
    info "Creating Python virtual environment..."
    $PYTHON -m venv venv
    log "Virtual environment created"
fi

if [ "$OS" = "windows" ]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi
log "Virtual environment activated"

info "Installing Python dependencies (pip install -r requirements.txt)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
log "Python dependencies installed"

# ─────────────────────────────────────────────────────────────
# 7. Create local config if missing
# ─────────────────────────────────────────────────────────────
mkdir -p config

if [ ! -f config/config.json ]; then
    info "Creating default config/config.json..."
    cat > config/config.json << 'CONFIG_EOF'
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
CONFIG_EOF
    log "config/config.json created — run 'python3 main.py onboard' to configure"
else
    warn "config/config.json already exists (keeping as-is)"
fi

# ─────────────────────────────────────────────────────────────
# 8. Create workspace directories
# ─────────────────────────────────────────────────────────────
mkdir -p workspace/tanu

for f in SOUL.md IDENTITY.md USER.md AGENT.md HEARTBEAT.md BACKSTORY.md; do
    if [ ! -f "workspace/$f" ]; then
        echo "# $f" > "workspace/$f"
        echo "" >> "workspace/$f"
    fi
done

log "Workspace directories ready"

# ─────────────────────────────────────────────────────────────
# 9. Summary & next steps
# ─────────────────────────────────────────────────────────────
echo ""
echo "  ┌────────────────────────────────────┐"
echo "  │      Setup Complete!               │"
echo "  └────────────────────────────────────┘"
echo ""
if [ "$OS" = "windows" ]; then
    echo "  ${CYAN}Activate environment:${NC}"
    echo "    source venv/Scripts/activate"
    echo ""
    echo "  ${CYAN}Run configuration wizard:${NC}"
    echo "    python main.py onboard"
    echo ""
    echo "  ${CYAN}Launch desktop app:${NC}"
    echo "    python main.py desk"
    echo ""
    echo "  ${CYAN}Other commands:${NC}"
    echo "    python main.py serve    — Web UI only"
    echo "    python main.py agent   — Terminal chat"
    echo "    python main.py tanu    — Voice assistant"
    echo "    python main.py status  — Show config & status"
else
    echo "  ${CYAN}Activate environment:${NC}"
    echo "    source venv/bin/activate"
    echo ""
    echo "  ${CYAN}Run configuration wizard:${NC}"
    echo "    python3 main.py onboard"
    echo ""
    echo "  ${CYAN}Launch desktop app:${NC}"
    echo "    python3 main.py desk"
    echo ""
    echo "  ${CYAN}Other commands:${NC}"
    echo "    python3 main.py serve    — Web UI only"
    echo "    python3 main.py agent   — Terminal chat"
    echo "    python3 main.py tanu    — Voice assistant"
    echo "    python3 main.py status  — Show config & status"
fi
echo ""
