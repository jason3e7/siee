#!/usr/bin/env bash
set -euo pipefail

SIEE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_USER="siee-worker"
CURRENT_USER="$(whoami)"
PYTHON="$SIEE_DIR/venv/bin/python"

echo "=== SIEE Worker Isolation Setup ==="
echo "SIEE dir   : $SIEE_DIR"
echo "Worker user: $WORKER_USER"
echo "Server user: $CURRENT_USER"
echo "Python     : $PYTHON"
echo ""

# 1. venv 必須先存在
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: venv not found. Run first:"
    echo "  python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

# 2. 建立 siee-worker system user
if id "$WORKER_USER" &>/dev/null; then
    echo "[1/5] User $WORKER_USER already exists, skipping."
else
    echo "[1/5] Creating system user $WORKER_USER..."
    sudo useradd -r -s /bin/false "$WORKER_USER"
fi

# 3. workspace / logs 給 siee-worker 寫入權限
echo "[2/5] Setting workspace/ and logs/ ownership to $WORKER_USER..."
mkdir -p "$SIEE_DIR/workspace" "$SIEE_DIR/logs"
sudo chown "$WORKER_USER:$WORKER_USER" "$SIEE_DIR/workspace" "$SIEE_DIR/logs"

# 4. venv 給 siee-worker 讀取權限
echo "[3/5] Making venv readable by $WORKER_USER..."
chmod -R o+rX "$SIEE_DIR/venv"

# 5. sudoers：讓 server user 可以免密碼 sudo -u siee-worker python
echo "[4/5] Configuring sudoers..."
SUDOERS_FILE="/etc/sudoers.d/siee"
SUDOERS_LINE="$CURRENT_USER ALL=($WORKER_USER) NOPASSWD: $PYTHON"
echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"
echo "  -> $SUDOERS_LINE"

# 6. secret.txt 只有 server user 可讀
echo "[5/5] Protecting secret.txt..."
touch "$SIEE_DIR/secret.txt"
chmod 600 "$SIEE_DIR/secret.txt"

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. 編輯 secret.txt，填入 API keys"
echo "  2. python server.py"
