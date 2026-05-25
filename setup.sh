#!/usr/bin/env bash
set -euo pipefail

SIEE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_USER="siee-worker"
SHARED_GROUP="siee-shared"
CURRENT_USER="$(whoami)"
PYTHON="$SIEE_DIR/venv/bin/python"
GROUP_CHANGED=false

echo "=== SIEE Worker Isolation Setup ==="
echo "SIEE dir   : $SIEE_DIR"
echo "Worker user: $WORKER_USER"
echo "Server user: $CURRENT_USER"
echo "Python     : $PYTHON"
echo ""

# 1. venv must exist before proceeding
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: venv not found. Run first:"
    echo "  python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

# 2. create siee-worker system user
if id "$WORKER_USER" &>/dev/null; then
    echo "[1/6] User $WORKER_USER already exists, skipping."
else
    echo "[1/6] Creating system user $WORKER_USER..."
    sudo useradd -r -s /bin/false "$WORKER_USER"
fi

# 3. create shared group so server user and siee-worker can both read/write workspace and logs
if getent group "$SHARED_GROUP" &>/dev/null; then
    echo "[2/6] Group $SHARED_GROUP already exists, skipping."
else
    echo "[2/6] Creating shared group $SHARED_GROUP..."
    sudo groupadd "$SHARED_GROUP"
fi

# add users to group only if not already a member
if id -nG "$CURRENT_USER" | tr ' ' '\n' | grep -qx "$SHARED_GROUP"; then
    echo "  -> $CURRENT_USER already in $SHARED_GROUP"
else
    sudo usermod -aG "$SHARED_GROUP" "$CURRENT_USER"
    echo "  -> $CURRENT_USER added to $SHARED_GROUP"
    GROUP_CHANGED=true
fi
if id -nG "$WORKER_USER" | tr ' ' '\n' | grep -qx "$SHARED_GROUP"; then
    echo "  -> $WORKER_USER already in $SHARED_GROUP"
else
    sudo usermod -aG "$SHARED_GROUP" "$WORKER_USER"
    echo "  -> $WORKER_USER added to $SHARED_GROUP"
fi

# 4. workspace / logs: group=siee-shared, 770, no sticky bit
#    siee-worker can write files; server user can rmtree (group write, no sticky bit)
echo "[3/6] Setting workspace/ and logs/ permissions..."
mkdir -p "$SIEE_DIR/workspace" "$SIEE_DIR/logs"
sudo chown "$CURRENT_USER:$SHARED_GROUP" "$SIEE_DIR/workspace" "$SIEE_DIR/logs"
sudo chmod 770 "$SIEE_DIR/workspace" "$SIEE_DIR/logs"

# 5. make venv readable by siee-worker
echo "[4/6] Making venv readable by $WORKER_USER..."
chmod -R o+rX "$SIEE_DIR/venv"

# 6. sudoers: allow server user to run python as siee-worker without password
echo "[5/6] Configuring sudoers..."
SUDOERS_FILE="/etc/sudoers.d/siee"
SUDOERS_LINE="$CURRENT_USER ALL=($WORKER_USER) NOPASSWD: $PYTHON"
echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 440 "$SUDOERS_FILE"
echo "  -> $SUDOERS_LINE"

# 7. protect secret.txt — readable by server user only
echo "[6/6] Protecting secret.txt..."
touch "$SIEE_DIR/secret.txt"
chmod 600 "$SIEE_DIR/secret.txt"

echo ""
echo "=== Done ==="
echo ""
if [ "$GROUP_CHANGED" = true ]; then
    echo "NOTE: group membership takes effect on next login, or run:"
    echo "   newgrp $SHARED_GROUP"
    echo ""
fi
echo "Next steps:"
echo "  1. Edit secret.txt with your API keys"
if [ "$GROUP_CHANGED" = true ]; then
    echo "  2. newgrp $SHARED_GROUP  (or re-login)"
    echo "  3. python server.py"
else
    echo "  2. python server.py"
fi
