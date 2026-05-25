#!/usr/bin/env bash
set -euo pipefail

SIEE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_USER="siee-worker"
SHARED_GROUP="siee-shared"
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
    echo "[1/6] User $WORKER_USER already exists, skipping."
else
    echo "[1/6] Creating system user $WORKER_USER..."
    sudo useradd -r -s /bin/false "$WORKER_USER"
fi

# 3. 建立 shared group，讓 server user 與 siee-worker 都能讀寫 workspace/logs
if getent group "$SHARED_GROUP" &>/dev/null; then
    echo "[2/6] Group $SHARED_GROUP already exists, skipping."
else
    echo "[2/6] Creating shared group $SHARED_GROUP..."
    sudo groupadd "$SHARED_GROUP"
fi
sudo usermod -aG "$SHARED_GROUP" "$CURRENT_USER"
sudo usermod -aG "$SHARED_GROUP" "$WORKER_USER"
echo "  -> $CURRENT_USER and $WORKER_USER added to $SHARED_GROUP"

# 4. workspace / logs：group = siee-shared, 770, no sticky bit
#    → siee-worker 可寫入，server user 可 rmtree（有 group write，無 sticky bit）
echo "[3/6] Setting workspace/ and logs/ permissions..."
mkdir -p "$SIEE_DIR/workspace" "$SIEE_DIR/logs"
sudo chown "$CURRENT_USER:$SHARED_GROUP" "$SIEE_DIR/workspace" "$SIEE_DIR/logs"
sudo chmod 770 "$SIEE_DIR/workspace" "$SIEE_DIR/logs"

# 5. venv 給 siee-worker 讀取權限
echo "[4/6] Making venv readable by $WORKER_USER..."
chmod -R o+rX "$SIEE_DIR/venv"

# 6. sudoers：讓 server user 可以免密碼 sudo -u siee-worker python
echo "[5/6] Configuring sudoers..."
SUDOERS_FILE="/etc/sudoers.d/siee"
SUDOERS_LINE="$CURRENT_USER ALL=($WORKER_USER) NOPASSWD: $PYTHON"
echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"
echo "  -> $SUDOERS_LINE"

# 7. secret.txt 只有 server user 可讀
echo "[6/6] Protecting secret.txt..."
touch "$SIEE_DIR/secret.txt"
chmod 600 "$SIEE_DIR/secret.txt"

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. 編輯 secret.txt，填入 API keys"
echo "  2. python server.py"
