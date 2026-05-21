import os
import logging
import httpx
from mcp.server.fastmcp import FastMCP

_debug = os.environ.get("DEBUG", "").lower() in ("1", "true")
logging.basicConfig(
    level=logging.DEBUG if _debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("siee.mcp")

SIEE_URL = os.environ.get("SIEE_URL", "http://localhost:5000")

mcp = FastMCP(
    "SIEE",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", 5001)),
)


def _deploy(files: dict[str, str], base_url: str = None) -> dict:
    url = base_url or SIEE_URL
    with httpx.Client() as client:
        r = client.post(
            f"{url}/deploy",
            files=[("file", (name, content.encode())) for name, content in files.items()],
        )
        r.raise_for_status()
        return r.json()


def _exec_command(command: str, args: list[str], base_url: str = None) -> dict:
    url = base_url or SIEE_URL
    with httpx.Client() as client:
        r = client.post(f"{url}/exec", json={"command": command, "args": args})
        r.raise_for_status()
        return r.json()


def _get_log(exec_id: str, base_url: str = None) -> dict:
    url = base_url or SIEE_URL
    with httpx.Client() as client:
        r = client.get(f"{url}/logs/{exec_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def deploy(files: dict[str, str]) -> dict:
    """Deploy files to the SIEE execution environment, replacing all previous files.

    Args:
        files: mapping of filename to file content, e.g. {"main.py": "print('hello')"}

    Returns:
        {"status": "deployed", "files": [...]}
    """
    log.info("tool deploy: files=%s", list(files.keys()))
    result = _deploy(files)
    log.debug("tool deploy result: %s", result)
    return result


@mcp.tool()
def exec_command(command: str, args: list[str] = []) -> dict:
    """Execute a whitelisted command in the SIEE execution environment.

    The execution is asynchronous. Use get_log(exec_id) to poll for results.

    Args:
        command: one of the allowed command names (e.g. "run", "pytest")
        args: optional extra arguments appended to the command

    Returns:
        {"exec_id": "...", "status": "RUNNING"}
    """
    log.info("tool exec_command: command=%s args=%s", command, args)
    result = _exec_command(command, args)
    log.debug("tool exec_command result: %s", result)
    return result


@mcp.tool()
def get_log(exec_id: str) -> dict:
    """Get execution status and output for a given exec_id.

    Poll this until status is DONE or ERROR.

    Args:
        exec_id: the id returned by exec_command

    Returns:
        {"exec_id": "...", "status": "RUNNING|DONE|ERROR", "log": "..."}
    """
    log.debug("tool get_log: exec_id=%s", exec_id)
    result = _get_log(exec_id)
    log.info("tool get_log: exec_id=%s status=%s", exec_id, result.get("status"))
    return result


if __name__ == "__main__":
    mcp.run(transport="sse")
