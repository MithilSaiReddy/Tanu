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

# Check for Godot 4
GODOT=""
for bin in godot godot4; do
    if command -v "$bin" &>/dev/null; then
        GODOT="$bin"
        break
    fi
done

if [ -z "$GODOT" ]; then
    warn "Godot 4 not found in PATH."
    warn "  Download: https://godotengine.org/download"
    warn "  The desktop UI (python main.py desk) requires Godot."
else
    log "Godot:  $($GODOT --version 2>/dev/null || echo 'found')"
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
                sudo apt install -y portaudio19-dev pulseaudio
                ;;
            fedora)
                sudo dnf install -y portaudio-devel pulseaudio
                ;;
            arch|manjaro|endeavour)
                sudo pacman -S --needed portaudio pulseaudio
                ;;
            opensuse*|suse)
                sudo zypper install -y portaudio-devel pulseaudio
                ;;
            *)
                warn "Unknown distro. Install portaudio manually."
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
        warn "System deps: install manually if needed."
    fi
}

if [ "$OS" = "linux" ] && [ "${DISTRO:-}" != "unknown" ]; then
    install_sysdeps
elif [ "$OS" = "macos" ] || [ "$OS" = "windows" ]; then
    install_sysdeps
fi

# ─────────────────────────────────────────────────────────────
# 4. Initialize git submodules
# ─────────────────────────────────────────────────────────────
if [ -f .gitmodules ]; then
    info "Initializing git submodules..."
    git submodule update --init --recursive
    log "Submodules initialized"
fi

# ─────────────────────────────────────────────────────────────
# 5. Create Python virtual environment
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
# 6. Create local config if missing
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
# 7. Create workspace directories
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
# 8. Summary & next steps
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
