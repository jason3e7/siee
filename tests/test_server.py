import io
import os
import time

import pytest

import server
from server import create_app


@pytest.fixture
def app(tmp_path):
    instance = create_app(
        workspace=str(tmp_path / "workspace"),
        logs_dir=str(tmp_path / "logs"),
    )
    instance.config["TESTING"] = True
    return instance


@pytest.fixture
def client(app):
    return app.test_client()


def _deploy(client, filename: str, code: bytes):
    return client.post(
        "/deploy",
        data={"file": (io.BytesIO(code), filename)},
        content_type="multipart/form-data",
    )


def _wait(client, exec_id: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/logs/{exec_id}")
        data = r.get_json()
        if data["status"] != "RUNNING":
            return data
        time.sleep(0.05)
    return client.get(f"/logs/{exec_id}").get_json()


# ── deploy ────────────────────────────────────────────────────────────────────

class TestDeploy:
    def test_single_file(self, client, app):
        r = _deploy(client, "main.py", b"print('hello')")
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "deployed"
        assert "main.py" in body["files"]
        assert os.path.exists(os.path.join(app.config["WORKSPACE"], "main.py"))

    def test_replaces_workspace(self, client, app):
        _deploy(client, "old.py", b"")
        _deploy(client, "new.py", b"")
        ws = app.config["WORKSPACE"]
        assert not os.path.exists(os.path.join(ws, "old.py"))
        assert os.path.exists(os.path.join(ws, "new.py"))

    def test_multiple_files(self, client, app):
        r = client.post(
            "/deploy",
            data={
                "file": [
                    (io.BytesIO(b"a"), "a.py"),
                    (io.BytesIO(b"b"), "b.py"),
                ]
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        assert set(r.get_json()["files"]) == {"a.py", "b.py"}

    def test_no_file_returns_400(self, client):
        r = client.post("/deploy", data={}, content_type="multipart/form-data")
        assert r.status_code == 400


# ── exec ──────────────────────────────────────────────────────────────────────

class TestExec:
    def test_missing_command_returns_400(self, client):
        r = client.post("/exec", json={})
        assert r.status_code == 400
        assert "command is required" in r.get_json()["error"]

    def test_unknown_command_returns_400(self, client):
        r = client.post("/exec", json={"command": "rm"})
        assert r.status_code == 400
        body = r.get_json()
        assert "not allowed" in body["error"]
        assert "available" in body

    def test_returns_exec_id(self, client):
        r = client.post("/exec", json={"command": "run"})
        assert r.status_code == 200
        body = r.get_json()
        assert "exec_id" in body
        assert body["status"] == "RUNNING"


# ── logs ──────────────────────────────────────────────────────────────────────

class TestLogs:
    def test_unknown_exec_id_returns_404(self, client):
        r = client.get("/logs/does-not-exist")
        assert r.status_code == 404


# ── integration ───────────────────────────────────────────────────────────────

class TestIntegration:
    def test_run_success(self, client):
        _deploy(client, "main.py", b"print('test passed')")
        exec_id = client.post("/exec", json={"command": "run"}).get_json()["exec_id"]
        result = _wait(client, exec_id)
        assert result["status"] == "DONE"
        assert "test passed" in result["log"]
        assert "EXIT CODE: 0" in result["log"]

    def test_run_error_exit_code(self, client):
        _deploy(client, "main.py", b"import sys; sys.exit(2)")
        exec_id = client.post("/exec", json={"command": "run"}).get_json()["exec_id"]
        result = _wait(client, exec_id)
        assert result["status"] == "ERROR"
        assert "EXIT CODE: 2" in result["log"]

    def test_exec_multiple_times_independent(self, client):
        _deploy(client, "main.py", b"print('ok')")
        ids = [
            client.post("/exec", json={"command": "run"}).get_json()["exec_id"]
            for _ in range(3)
        ]
        assert len(set(ids)) == 3
        for eid in ids:
            assert _wait(client, eid)["status"] == "DONE"

    def test_pytest_command_with_args(self, client):
        code = b"def test_always_pass():\n    assert True\n"
        _deploy(client, "test_sample.py", code)
        exec_id = client.post(
            "/exec", json={"command": "pytest", "args": ["-v"]}
        ).get_json()["exec_id"]
        result = _wait(client, exec_id)
        assert result["status"] == "DONE"
        assert "passed" in result["log"]

    def test_log_contains_stdout_and_stderr(self, client):
        code = b"import sys\nprint('out')\nprint('err', file=sys.stderr)\n"
        _deploy(client, "main.py", code)
        exec_id = client.post("/exec", json={"command": "run"}).get_json()["exec_id"]
        result = _wait(client, exec_id)
        assert "out" in result["log"]
        assert "err" in result["log"]


# ── scan ──────────────────────────────────────────────────────────────────────

class TestScan:
    def test_environ_print_rejected(self, client):
        _deploy(client, "main.py", b"import os\nprint(os.environ)\n")
        r = client.post("/exec", json={"command": "run"})
        assert r.status_code == 400
        body = r.get_json()
        assert "scan rejected" in body["error"]
        assert len(body["violations"]) > 0

    def test_getenv_print_rejected(self, client):
        _deploy(client, "main.py", b"import os\nprint(os.getenv('KEY'))\n")
        r = client.post("/exec", json={"command": "run"})
        assert r.status_code == 400

    def test_legitimate_environ_access_allowed(self, client):
        code = b"import os\nval = os.environ.get('HOME', '')\nprint('home:', val)\n"
        _deploy(client, "main.py", code)
        r = client.post("/exec", json={"command": "run"})
        assert r.status_code == 200


# ── log masking ───────────────────────────────────────────────────────────────

class TestLogMasking:
    def test_secret_masked_in_log(self, client, monkeypatch):
        monkeypatch.setenv("_SIEE_TEST_SECRET", "supersecret_xyz_123")
        server.SECRET_ENV_KEYS.append("_SIEE_TEST_SECRET")
        try:
            # val is read from env then printed — passes scan, but value must be masked
            code = b"import os\nval = os.environ.get('_SIEE_TEST_SECRET', '')\nprint('got:', val)\n"
            _deploy(client, "main.py", code)
            exec_id = client.post("/exec", json={"command": "run"}).get_json()["exec_id"]
            result = _wait(client, exec_id)
            assert result["status"] == "DONE"
            assert "supersecret_xyz_123" not in result["log"]
            assert "***" in result["log"]
        finally:
            server.SECRET_ENV_KEYS.remove("_SIEE_TEST_SECRET")
