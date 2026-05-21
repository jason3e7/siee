import os
import httpx
from mcp.server.fastmcp import FastMCP

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
    return _deploy(files)


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
    return _exec_command(command, args)


@mcp.tool()
def get_log(exec_id: str) -> dict:
    """Get execution status and output for a given exec_id.

    Poll this until status is DONE or ERROR.

    Args:
        exec_id: the id returned by exec_command

    Returns:
        {"exec_id": "...", "status": "RUNNING|DONE|ERROR", "log": "..."}
    """
    return _get_log(exec_id)


if __name__ == "__main__":
    mcp.run(transport="sse")
