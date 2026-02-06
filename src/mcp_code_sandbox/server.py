"""FastMCP server with tool definitions."""

import asyncio

import docker
import structlog
from fastmcp import FastMCP

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.logging import configure_logging, session_id_var
from mcp_code_sandbox.models import (
    CloseSessionResult,
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)
from mcp_code_sandbox.session import SessionManager
from mcp_code_sandbox.validation import (
    validate_code_size,
    validate_session_id,
    validate_upload_size,
)

config = SandboxConfig()
configure_logging(config)

log = structlog.get_logger("mcp_code_sandbox.server")

docker_client = docker.from_env()
session_manager = SessionManager(config, docker_client)

mcp = FastMCP("mcp-code-sandbox")


@mcp.tool
async def upload_file(
    filename: str,
    content_base64: str,
    session_id: str | None = None,
    overwrite: bool = False,
) -> UploadResult | ErrorResponse:
    """Upload a data file into the sandbox session for analysis.

    Use this to provide CSV, Excel, JSON, or other data files before running Python code.
    The file is placed at /mnt/data/<filename> inside the session container.

    Args:
        filename: Name for the file (e.g. "sales.csv"). Letters, numbers, dots,
            hyphens, underscores only.
        content_base64: File contents encoded as base64.
        session_id: Reuse an existing session. Omit to create a new one.
        overwrite: Set to true to replace an existing file with the same name.

    Returns:
        session_id and the path where the file was stored, or an error if the file exists.
    """
    if err := validate_session_id(session_id):
        return err
    if err := validate_upload_size(content_base64, config):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(
        session_manager.upload, session_id, filename, content_base64, overwrite
    )


@mcp.tool
async def run_python(
    code: str,
    session_id: str | None = None,
) -> RunResult | ErrorResponse:
    """Execute Python code in an isolated Docker sandbox and return the output.

    The sandbox has pandas, numpy, matplotlib, seaborn, openpyxl, reportlab, pyarrow,
    and scipy pre-installed. Files persist in /mnt/data/ across calls within the same session.
    Each call runs a fresh Python process — variables do not carry over, but files do.

    Args:
        code: Python source code to execute (max 100KB).
        session_id: Reuse an existing session. Omit to create a new one.

    Returns:
        stdout, stderr, exit_code, list of new/changed artifacts, and execution duration.
        On timeout, exit_code is -1 with a timeout message in stderr.
    """
    if err := validate_session_id(session_id):
        return err
    if err := validate_code_size(code, config):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.execute, session_id, code)


@mcp.tool
async def read_artifact(
    session_id: str,
    path: str,
) -> ReadArtifactResult | ErrorResponse:
    """Read a file from the sandbox session as base64-encoded content.

    Use this to inspect generated artifacts like charts (PNG), reports (PDF), or data files.
    The path must be within /mnt/data/.

    Args:
        session_id: The session containing the artifact.
        path: Absolute path to the file (e.g. "/mnt/data/chart.png").

    Returns:
        File content as base64 with metadata, or an error if not found or too large (>10MB).
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.read_file, session_id, path)


@mcp.tool
async def list_artifacts(
    session_id: str,
) -> ListArtifactsResult | ErrorResponse:
    """List all files currently in the sandbox session's /mnt/data/ directory.

    Use this to see what data files and generated artifacts are available for download
    or further processing.

    Args:
        session_id: The session to list artifacts for.

    Returns:
        List of artifacts with filename, size, MIME type, and optional download URL.
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.list_files, session_id)


@mcp.tool
async def close_session(
    session_id: str,
) -> CloseSessionResult | ErrorResponse:
    """Destroy the sandbox session container and release all resources.

    Call this when you are done with a session. All files in /mnt/data/ will be lost.
    Sessions also auto-close after 30 minutes of inactivity.

    Args:
        session_id: The session to close.

    Returns:
        Confirmation that the session was closed, or an error if not found.
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.close, session_id)


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    import threading

    from mcp_code_sandbox.cleanup import remove_orphan_containers, start_ttl_cleanup
    from mcp_code_sandbox.http_server import run_http_server

    # Remove orphan containers from previous runs
    remove_orphan_containers(docker_client)

    # Start HTTP artifact server in background thread
    session_manager.enable_http()
    http_thread = threading.Thread(
        target=run_http_server,
        args=(config, session_manager),
        daemon=True,
    )
    http_thread.start()

    # Start TTL cleanup background thread
    start_ttl_cleanup(config, session_manager)

    mcp.run()


if __name__ == "__main__":
    main()
