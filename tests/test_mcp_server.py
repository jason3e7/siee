import time
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

import httpx
import pytest

from server import create_app
from mcp_server import _deploy, _exec_command, _get_log


class _QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass

    def log_error(self, *args, **kwargs):
        pass


@pytest.fixture(scope="module")
def siee_url(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("siee")
    app = create_app(
        workspace=str(tmp / "workspace"),
        logs_dir=str(tmp / "logs"),
    )
    srv = make_server("127.0.0.1", 0, app, handler_class=_QuietHandler)
    port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def _wait(exec_id: str, siee_url: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _get_log(exec_id, base_url=siee_url)
        if result["status"] != "RUNNING":
            return result
        time.sleep(0.05)
    return _get_log(exec_id, base_url=siee_url)


# ── deploy ────────────────────────────────────────────────────────────────────

class TestDeploy:
    def test_single_file(self, siee_url):
        r = _deploy({"main.py": "print('hello')"}, base_url=siee_url)
        assert r["status"] == "deployed"
        assert "main.py" in r["files"]

    def test_multiple_files(self, siee_url):
        r = _deploy({"a.py": "x=1", "b.py": "y=2"}, base_url=siee_url)
        assert set(r["files"]) == {"a.py", "b.py"}

    def test_replaces_workspace(self, siee_url):
        _deploy({"old.py": ""}, base_url=siee_url)
        r = _deploy({"new.py": ""}, base_url=siee_url)
        assert "new.py" in r["files"]
        assert "old.py" not in r["files"]


# ── exec_command ──────────────────────────────────────────────────────────────

class TestExecCommand:
    def test_unknown_command_raises(self, siee_url):
        with pytest.raises(httpx.HTTPStatusError):
            _exec_command("rm", [], base_url=siee_url)

    def test_returns_exec_id(self, siee_url):
        r = _exec_command("run", [], base_url=siee_url)
        assert "exec_id" in r
        assert r["status"] == "RUNNING"


# ── get_log ───────────────────────────────────────────────────────────────────

class TestGetLog:
    def test_unknown_exec_id_raises(self, siee_url):
        with pytest.raises(httpx.HTTPStatusError):
            _get_log("nonexistent-id", base_url=siee_url)


# ── integration ───────────────────────────────────────────────────────────────

class TestIntegration:
    def test_full_flow(self, siee_url):
        _deploy({"main.py": "print('hello from mcp')"}, base_url=siee_url)
        r = _exec_command("run", [], base_url=siee_url)
        result = _wait(r["exec_id"], siee_url)
        assert result["status"] == "DONE"
        assert "hello from mcp" in result["log"]

    def test_exec_error(self, siee_url):
        _deploy({"main.py": "import sys; sys.exit(1)"}, base_url=siee_url)
        r = _exec_command("run", [], base_url=siee_url)
        result = _wait(r["exec_id"], siee_url)
        assert result["status"] == "ERROR"

    def test_pytest_with_args(self, siee_url):
        code = "def test_ok():\n    assert True\n"
        _deploy({"test_x.py": code}, base_url=siee_url)
        r = _exec_command("pytest", ["-v"], base_url=siee_url)
        result = _wait(r["exec_id"], siee_url)
        assert result["status"] == "DONE"
        assert "passed" in result["log"]

    def test_exec_multiple_independent(self, siee_url):
        _deploy({"main.py": "print('ok')"}, base_url=siee_url)
        ids = [_exec_command("run", [], base_url=siee_url)["exec_id"] for _ in range(3)]
        assert len(set(ids)) == 3
        for eid in ids:
            assert _wait(eid, siee_url)["status"] == "DONE"
