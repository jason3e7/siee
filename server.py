import os
import sys
import uuid
import shutil
import subprocess
import threading
import logging
from datetime import datetime

from flask import Flask, request, jsonify

_debug = os.environ.get("DEBUG", "").lower() in ("1", "true")
logging.basicConfig(
    level=logging.DEBUG if _debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("siee")

# Server owner configures allowed commands here
ALLOWED_COMMANDS = {
    "pytest": [sys.executable, "-m", "pytest"],
    "run":    [sys.executable, "main.py"],
}


def create_app(workspace: str = None, logs_dir: str = None) -> Flask:
    base = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__)
    app.config["WORKSPACE"] = workspace or os.path.join(base, "workspace")
    app.config["LOGS_DIR"]   = logs_dir   or os.path.join(base, "logs")
    app.config["JOBS"]       = {}

    os.makedirs(app.config["WORKSPACE"], exist_ok=True)
    os.makedirs(app.config["LOGS_DIR"],  exist_ok=True)

    def _run_job(exec_id: str, cmd: list, cwd: str, logs_dir: str, jobs: dict):
        log_path = os.path.join(logs_dir, f"{exec_id}.log")
        ts = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(log_path, "w") as f:
            f.write(f"[{ts()}] STATUS: RUNNING\n")
            f.flush()
            try:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                f.write(f"[{ts()}] STDOUT:\n{result.stdout}\n")
                f.write(f"[{ts()}] STDERR:\n{result.stderr}\n")
                f.write(f"[{ts()}] EXIT CODE: {result.returncode}\n")
                status = "DONE" if result.returncode == 0 else "ERROR"
            except subprocess.TimeoutExpired:
                f.write(f"[{ts()}] TIMEOUT\n")
                status = "ERROR"
            except Exception as e:
                f.write(f"[{ts()}] EXCEPTION: {e}\n")
                status = "ERROR"
            f.write(f"[{ts()}] STATUS: {status}\n")

        jobs[exec_id] = status
        log.info("job done: exec_id=%s status=%s", exec_id, status)

    @app.post("/deploy")
    def deploy():
        files = request.files.getlist("file")
        if not files or all(f.filename == "" for f in files):
            log.warning("deploy: no file provided")
            return jsonify({"error": "no file provided"}), 400

        ws = app.config["WORKSPACE"]
        shutil.rmtree(ws)
        os.makedirs(ws)

        saved = []
        for f in files:
            if f.filename:
                dest = os.path.join(ws, f.filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                f.save(dest)
                saved.append(f.filename)

        log.info("deploy: files=%s", saved)
        return jsonify({"status": "deployed", "files": saved})

    @app.post("/exec")
    def exec_cmd():
        data = request.get_json(silent=True) or {}
        command = data.get("command")
        args = data.get("args", [])

        if not command:
            log.warning("exec: command is required")
            return jsonify({"error": "command is required"}), 400
        if command not in ALLOWED_COMMANDS:
            log.warning("exec: command not allowed: %s", command)
            return jsonify({
                "error": "command not allowed",
                "available": list(ALLOWED_COMMANDS.keys()),
            }), 400

        cmd = ALLOWED_COMMANDS[command] + [str(a) for a in args]
        exec_id = str(uuid.uuid4())
        jobs = app.config["JOBS"]
        jobs[exec_id] = "RUNNING"

        log.info("exec: command=%s args=%s exec_id=%s", command, args, exec_id)
        threading.Thread(
            target=_run_job,
            args=(exec_id, cmd, app.config["WORKSPACE"], app.config["LOGS_DIR"], jobs),
            daemon=True,
        ).start()

        return jsonify({"exec_id": exec_id, "status": "RUNNING"})

    @app.get("/logs/<exec_id>")
    def get_logs(exec_id):
        jobs = app.config["JOBS"]
        if exec_id not in jobs:
            log.warning("get_logs: exec_id not found: %s", exec_id)
            return jsonify({"error": "exec_id not found"}), 404

        log_path = os.path.join(app.config["LOGS_DIR"], f"{exec_id}.log")
        content = ""
        if os.path.exists(log_path):
            with open(log_path) as f:
                content = f.read()

        status = jobs[exec_id]
        log.debug("get_logs: exec_id=%s status=%s", exec_id, status)
        return jsonify({"exec_id": exec_id, "status": status, "log": content})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
