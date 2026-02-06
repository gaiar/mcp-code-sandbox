"""FastMCP server with tool definitions."""

import asyncio
import sys

import docker
import structlog
from fastmcp import Context, FastMCP

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

mcp = FastMCP("code_sandbox_mcp")


@mcp.tool(
    name="sandbox_upload_file",
    annotations={
        "title": "Upload File to Sandbox",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sandbox_upload_file(
    filename: str,
    content_base64: str,
    session_id: str | None = None,
    overwrite: bool = False,
    ctx: Context | None = None,
) -> UploadResult | ErrorResponse:
    """Upload a data file into the sandbox session for analysis.

    Use this to provide CSV, Excel, JSON, or other data files before running Python code.
    The file is placed at /mnt/data/<filename> inside the session container.

    Args:
        filename: Name for the file (e.g. "sales.csv"). Letters, numbers, dots,
            hyphens, underscores only. Max 255 characters.
        content_base64: File contents encoded as base64. Max 50MB decoded.
        session_id: Reuse an existing session. Omit to create a new one.
            Format: 1-64 chars of letters, numbers, hyphens, underscores.
        overwrite: Set to true to replace an existing file with the same name.

    Returns:
        Success — UploadResult:
        {
            "session_id": "sess_a1b2c3d4e5f6",
            "path": "/mnt/data/sales.csv"
        }

        Error — ErrorResponse:
        {
            "error": "file_exists|invalid_filename|upload_too_large|invalid_session_id",
            "message": "Human-readable description"
        }
    """
    if err := validate_session_id(session_id):
        return err
    if err := validate_upload_size(content_base64, config):
        return err
    session_id_var.set(session_id)
    if ctx:
        await ctx.info(f"Uploading {filename} ({len(content_base64)} bytes base64)")
    result = await asyncio.to_thread(
        session_manager.upload, session_id, filename, content_base64, overwrite
    )
    if ctx and isinstance(result, UploadResult):
        await ctx.info(f"Uploaded to {result.path} in session {result.session_id}")
    return result


@mcp.tool(
    name="sandbox_run_python",
    annotations={
        "title": "Run Python in Sandbox",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sandbox_run_python(
    code: str,
    session_id: str | None = None,
    ctx: Context | None = None,
) -> RunResult | ErrorResponse:
    """Execute Python code in an isolated Docker sandbox and return the output.

    The sandbox has pandas, numpy, matplotlib, seaborn, openpyxl, reportlab, pyarrow,
    and scipy pre-installed. Files persist in /mnt/data/ across calls within the same
    session. Each call runs a fresh Python process — variables do not carry over,
    but files do.

    Args:
        code: Python source code to execute (max 100KB).
        session_id: Reuse an existing session. Omit to create a new one.
            Format: 1-64 chars of letters, numbers, hyphens, underscores.

    Returns:
        Success — RunResult:
        {
            "session_id": "sess_a1b2c3d4e5f6",
            "run_id": "run_20240115T103000Z_a1b2",
            "exit_code": 0,
            "stdout": "output text...",
            "stderr": "",
            "stdout_truncated": false,
            "stderr_truncated": false,
            "artifacts": [
                {
                    "path": "/mnt/data/chart.png",
                    "filename": "chart.png",
                    "size_bytes": 45000,
                    "mime_type": "image/png",
                    "download_url": "http://localhost:8080/files/sess_.../chart.png"
                }
            ],
            "duration_ms": 1340
        }

        Error — ErrorResponse:
        {
            "error": "code_too_large|invalid_session_id|max_sessions|session_busy",
            "message": "Human-readable description"
        }

        On timeout (60s default), exit_code is -1 with a timeout message in stderr.
    """
    if err := validate_session_id(session_id):
        return err
    if err := validate_code_size(code, config):
        return err
    session_id_var.set(session_id)
    if ctx:
        await ctx.info(f"Executing {len(code)} bytes of Python code")
        await ctx.report_progress(0.1, 1.0, "Starting execution")
    result = await asyncio.to_thread(session_manager.execute, session_id, code)
    if ctx and isinstance(result, RunResult):
        artifact_count = len(result.artifacts)
        msg = f"Done in {result.duration_ms}ms, exit_code={result.exit_code}"
        if artifact_count:
            msg += f", {artifact_count} new artifact(s)"
        await ctx.info(msg)
        await ctx.report_progress(1.0, 1.0, "Complete")
        if result.stdout_truncated:
            await ctx.warning("stdout truncated at 100KB")
        if result.stderr_truncated:
            await ctx.warning("stderr truncated at 100KB")
    return result


@mcp.tool(
    name="sandbox_read_artifact",
    annotations={
        "title": "Read Artifact from Sandbox",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sandbox_read_artifact(
    session_id: str,
    path: str,
) -> ReadArtifactResult | ErrorResponse:
    """Read a file from the sandbox session as base64-encoded content.

    Use this to inspect generated artifacts like charts (PNG), reports (PDF),
    or data files. The path must be within /mnt/data/.

    Args:
        session_id: The session containing the artifact.
        path: Absolute path to the file (e.g. "/mnt/data/chart.png").

    Returns:
        Success — ReadArtifactResult:
        {
            "path": "/mnt/data/chart.png",
            "filename": "chart.png",
            "mime_type": "image/png",
            "size_bytes": 45000,
            "content_base64": "iVBORw0KGgo..."
        }

        Error — ErrorResponse:
        {
            "error": "not_found|artifact_too_large|invalid_path|session_not_found",
            "message": "Human-readable description",
            "size_bytes": 15000000  // only for artifact_too_large
        }
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.read_file, session_id, path)


@mcp.tool(
    name="sandbox_list_artifacts",
    annotations={
        "title": "List Sandbox Artifacts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def sandbox_list_artifacts(
    session_id: str,
) -> ListArtifactsResult | ErrorResponse:
    """List all files currently in the sandbox session's /mnt/data/ directory.

    Use this to see what data files and generated artifacts are available
    for download or further processing.

    Args:
        session_id: The session to list artifacts for.

    Returns:
        Success — ListArtifactsResult:
        {
            "artifacts": [
                {
                    "path": "/mnt/data/sales.csv",
                    "filename": "sales.csv",
                    "size_bytes": 1024,
                    "mime_type": "text/csv",
                    "download_url": "http://localhost:8080/files/sess_.../sales.csv"
                }
            ]
        }

        Error — ErrorResponse:
        {
            "error": "session_not_found|invalid_session_id",
            "message": "Human-readable description"
        }
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.list_files, session_id)


@mcp.tool(
    name="sandbox_close_session",
    annotations={
        "title": "Close Sandbox Session",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def sandbox_close_session(
    session_id: str,
) -> CloseSessionResult | ErrorResponse:
    """Destroy the sandbox session container and release all resources.

    Call this when you are done with a session. All files in /mnt/data/
    will be permanently lost. Sessions also auto-close after 30 minutes
    of inactivity.

    Args:
        session_id: The session to close.

    Returns:
        Success — CloseSessionResult:
        {
            "status": "closed"
        }

        Error — ErrorResponse:
        {
            "error": "session_not_found|invalid_session_id",
            "message": "Human-readable description"
        }
    """
    if err := validate_session_id(session_id):
        return err
    session_id_var.set(session_id)
    return await asyncio.to_thread(session_manager.close, session_id)


def _validate_startup() -> None:
    """Check Docker daemon and sandbox image are available. Exit on failure."""
    try:
        docker_client.ping()
    except Exception as exc:
        log.error("startup_failed", reason="Docker daemon unreachable", error=str(exc))
        print(f"ERROR: Docker daemon unreachable: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        docker_client.images.get(config.image)
    except docker.errors.ImageNotFound:
        log.error("startup_failed", reason="Sandbox image not found", image=config.image)
        print(
            f"ERROR: Sandbox image '{config.image}' not found. "
            "Build it with: docker build -t llm-sandbox:latest docker/",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        log.error("startup_failed", reason="Cannot check image", error=str(exc))
        print(f"ERROR: Cannot check Docker image: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    import threading

    from mcp_code_sandbox.cleanup import remove_orphan_containers, start_ttl_cleanup
    from mcp_code_sandbox.http_server import run_http_server

    # Fail fast if Docker or image not available
    _validate_startup()

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
