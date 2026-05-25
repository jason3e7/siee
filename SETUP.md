# setup.sh 說明

`setup.sh` 負責在 server 機器上建立 subprocess 隔離環境，讓 AI 部署的程式碼以低權限的 `siee-worker` 身份執行，無法直接存取 `secret.txt`。

## 執行方式

```bash
bash setup.sh
```

不需要 `sudo` 執行整個 script，內部需要特權的指令會自己加 `sudo`。可以重複跑，已設定好的步驟會顯示 `skipping` / `already exists`，不會重複操作。

---

## 步驟說明

### Step 1 — 確認 venv 存在

```bash
if [ ! -f "$PYTHON" ]; then exit 1; fi
```

`server.py` 要在 venv 環境下跑才有正確的套件。venv 不存在就直接停止，提示先建立。

---

### Step 2 — 建立 `siee-worker` system user

```bash
sudo useradd -r -s /bin/false siee-worker
```

- `-r`：system user，不會建立 home 目錄
- `-s /bin/false`：不能登入，只能被 `sudo -u` 切換

AI 部署的程式碼就是以這個 user 身份執行。

---

### Step 3 — 建立 `siee-shared` group

```
server user (user)  ─┐
                      ├── siee-shared group
siee-worker         ─┘
```

兩個 user 加入同一個 group 的目的：讓 `workspace/` 和 `logs/` 可以被雙方讀寫，同時又不需要開放給其他 user。

加入群組前會先檢查是否已經是成員，避免重複操作。

---

### Step 4 — 設定 `workspace/` 和 `logs/` 權限

```bash
sudo chown user:siee-shared workspace/ logs/
sudo chmod 770 workspace/ logs/
```

| 權限 | 說明 |
|------|------|
| `770` | 擁有者和 group 可讀寫執行，其他人完全沒有 |
| 無 sticky bit | server user 可以刪除 `siee-worker` 建立的檔案 |

**為什麼要沒有 sticky bit？**
有 sticky bit（像 `/tmp`）的目錄，只有檔案擁有者才能刪自己的檔案。`/deploy` 每次要清空 `workspace/`，server user 需要能刪 `siee-worker` 建立的舊檔案，所以不能有 sticky bit。

---

### Step 5 — 讓 `siee-worker` 可以讀 venv

```bash
chmod -R o+rX venv/
```

`siee-worker` 需要讀取 venv 裡的 Python 和套件（`requests` 等），否則 `import` 會失敗。`o+rX` 只開放讀取和進入目錄，不允許寫入。

---

### Step 6 — 設定 sudoers

```
user ALL=(siee-worker) NOPASSWD: SETENV: /path/to/venv/bin/python
```

| 部分 | 說明 |
|------|------|
| `user ALL=(siee-worker)` | server user 可以切換成 siee-worker 執行指令 |
| `NOPASSWD` | 不需要輸入密碼（server 是自動化流程） |
| `SETENV` | 允許 `sudo -E` 保留環境變數 |
| 指定 python 路徑 | 只有這一個指令可以被切換執行，不是所有指令 |

**為什麼需要 `SETENV`？**
`sudo` 預設會清掉環境變數。server 從 `secret.txt` 載入的 API key 透過 `sudo -E` 才能傳進 `siee-worker` 的 subprocess，否則 `os.environ.get('api_bearer')` 會拿到空值。

---

### Step 7 — 保護 `secret.txt`

```bash
chmod 600 secret.txt
```

只有 server user（擁有者）可以讀寫，`siee-worker` 讀不到。即使 AI 部署的程式碼試圖 `open('../secret.txt')`，OS 層就會擋住。

---

## 整體架構

```
secret.txt (600)
    │
    │ server 啟動時載入
    ▼
server.py (user)
    │
    │ sudo -E -u siee-worker python main.py
    │ (env var 透過 -E 傳入)
    ▼
subprocess (siee-worker)
    │  ✓ 可讀寫 workspace/、logs/
    │  ✓ 可讀 venv/
    │  ✗ 讀不到 secret.txt (600, 擁有者是 user)
    ▼
stdout / stderr → log 檔 → /logs/{exec_id} API 回傳
```

---

## 與 server.py 的對應關係

### `WORKER_USER`

```python
# server.py
WORKER_USER = "siee-worker"
```

對應 `setup.sh` 建立的 system user。設為 `None` 可停用隔離（測試用）。

---

### `secret.txt` 自動載入

```python
# server 啟動時執行
_secrets = _load_secrets("secret.txt")
for _k, _v in _secrets.items():
    os.environ.setdefault(_k, _v)   # 已有的 env var 優先
SECRET_ENV_KEYS = list(_secrets.keys())
```

server 啟動時讀 `secret.txt`，把每個 key 注入成自己的 env var。`SECRET_ENV_KEYS` 同步記錄所有 key，後面 log masking 會用到。

---

### `ALLOWED_COMMANDS` 的 `env` 控制

```python
ALLOWED_COMMANDS = {
    "pytest": {
        "cmd": [sys.executable, "-m", "pytest"],
        "env": [],      # 只傳 PATH/HOME/LANG，不帶任何 secret
    },
    "run": {
        "cmd": [sys.executable, "main.py"],
        "env": None,    # 傳全部 env var（含 secret.txt 注入的 key）
    },
}
```

`env: []` — subprocess 只拿到基本系統變數，完全看不到 secret。適合不需要 API key 的指令（如 pytest）。

`env: None` — 傳所有 env var，包含 `secret.txt` 注入的 key。適合需要呼叫真實 API 的指令。

---

### subprocess 的執行方式

```python
# _run_job 內部
if env_keys is None:
    env = os.environ.copy()          # 全部 env var
else:
    env = {PATH, HOME, LANG} + {指定的 key}

if WORKER_USER:
    cmd = ["sudo", "-E", "-u", WORKER_USER] + cmd
    #              ↑
    #   -E 讓 sudo 保留上面組好的 env，
    #   才能傳進 siee-worker 的 process
```

`-E` 是關鍵：沒有它，`sudo` 會清掉 env，`os.environ.get('api_bearer')` 在 subprocess 裡會拿到空值。`setup.sh` 的 sudoers 加了 `SETENV` 才允許 `-E` 生效。

---

### log masking

```python
# GET /logs/{exec_id} 回傳前
content = _mask_secrets(f.read())

def _mask_secrets(content):
    for key in SECRET_ENV_KEYS:
        value = os.environ.get(key, "")
        if value:
            content = content.replace(value, "***")
    return content
```

就算 subprocess 不小心把 secret 值印出來（例如 `print(api_key)`），回傳給 AI 之前會把已知的 secret 值替換成 `***`。`SECRET_ENV_KEYS` 是從 `secret.txt` 自動建立的，所以 `secret.txt` 裡有幾個 key，就會遮幾個。

---

### exec 前掃描

```python
SCAN_PATTERNS = [
    r"print\s*\(.*os\.environ",
    r"print\s*\(.*os\.getenv",
]
```

`/exec` 執行前會掃描 `workspace/` 裡所有 `.py` 檔，比對上面的 pattern。命中就拒絕執行（HTTP 400），不讓程式跑起來。這是防止 AI 部署探針腳本直接印出整個 env。

---

## newgrp 說明

`setup.sh` 跑完如果看到：

```
NOTE: 'siee-shared' is not active in this shell session.
```

代表這個 shell session 是在加入群組**之前**開的，群組的變更還沒生效。執行：

```bash
newgrp siee-shared
```

這會開啟一個新的 shell，`siee-shared` 就會在 group 清單裡，之後 `python server.py` 就能正常運作。
