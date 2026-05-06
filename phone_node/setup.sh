#!/usr/bin/env bash
# VECTOR Phone Node — Termux bootstrap
# Run once on old Android phone:
#   1. Open Termux
#   2. paste: curl -sL https://raw.githubusercontent.com/ArghyadeepDeb/VECTOR/main/phone_node/setup.sh | bash
#
# What it installs:
#   - Python 3.11, pip
#   - termux-api (for battery/notifications access)
#   - httpx (HTTP client to poll brain server)
#   - llama.cpp Python bindings (optional local inference)

set -euo pipefail

echo "[VECTOR] Phone node setup starting..."

# ── System packages ────────────────────────────────────────────────────────────
pkg update -y
pkg install -y python python-pip termux-api curl clang

# Required for llama-cpp-python build
pkg install -y cmake libopenblas libandroid-execinfo

# ── Python deps ────────────────────────────────────────────────────────────────
pip install --upgrade pip
pip install httpx loguru

# Optional: local inference via llama.cpp
# Install only if >= 4GB free storage and phone has decent CPU
STORAGE_FREE=$(df -BG "$HOME" | awk 'NR==2{print $4}' | tr -d 'G')
if [ "${STORAGE_FREE:-0}" -ge 4 ]; then
    echo "[VECTOR] Sufficient storage — installing llama-cpp-python..."
    CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python
else
    echo "[VECTOR] Low storage — skipping local inference (will delegate to brain server)"
fi

# ── Config ─────────────────────────────────────────────────────────────────────
mkdir -p "$HOME/.vector"
cat > "$HOME/.vector/phone_config.env" << 'EOF'
VECTOR_BRAIN_URL=https://vector-brain.fly.dev
VECTOR_API_KEY=REPLACE_WITH_YOUR_KEY
VECTOR_NODE_ID=phone-ambient
HEARTBEAT_INTERVAL_SEC=60
LOCAL_PORT=7700
EOF

echo "[VECTOR] Config written to ~/.vector/phone_config.env"
echo "[VECTOR] Edit ~/.vector/phone_config.env to set VECTOR_API_KEY"

# ── Termux boot (auto-start) ───────────────────────────────────────────────────
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/vector_ambient.sh" << 'EOF'
#!/usr/bin/env bash
# Auto-start VECTOR ambient server on Termux boot
cd "$HOME/vector_phone_node"
python ambient_server.py >> "$HOME/.vector/ambient.log" 2>&1 &
EOF
chmod +x "$HOME/.termux/boot/vector_ambient.sh"

# ── Clone / copy phone node script ────────────────────────────────────────────
mkdir -p "$HOME/vector_phone_node"
# Copy ambient_server.py next to this script if running locally
if [ -f "$(dirname "$0")/ambient_server.py" ]; then
    cp "$(dirname "$0")/ambient_server.py" "$HOME/vector_phone_node/"
fi

echo ""
echo "[VECTOR] Setup complete."
echo "  1. Edit ~/.vector/phone_config.env (set VECTOR_API_KEY)"
echo "  2. Run: cd ~/vector_phone_node && python ambient_server.py"
echo "  3. Install Termux:Boot app to auto-start on reboot"
