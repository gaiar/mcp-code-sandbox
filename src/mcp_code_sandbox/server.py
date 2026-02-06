"""FastMCP server with tool definitions."""

import uuid
from datetime import UTC, datetime

from fastmcp import FastMCP

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.logging import configure_logging
from mcp_code_sandbox.models import (
    CloseSessionResult,
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)

config = SandboxConfig()
configure_logging(config)

mcp = FastMCP("mcp-code-sandbox")


def _generate_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def _generate_run_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:4]
    return f"run_{ts}_{short}"


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
        session_id and the path where the file was stored, or an error if the file already exists.
    """
    sid = session_id or _generate_session_id()
    _ = content_base64, overwrite  # stub: unused
    return UploadResult(session_id=sid, path=f"/mnt/data/{filename}")


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
    sid = session_id or _generate_session_id()
    rid = _generate_run_id()
    return RunResult(
        session_id=sid,
        run_id=rid,
        exit_code=0,
        stdout="Hello from stub\n",
        stderr="",
        artifacts=[],
        duration_ms=0,
    )


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
    filename = path.rsplit("/", 1)[-1]
    return ReadArtifactResult(
        path=path,
        filename=filename,
        mime_type="application/octet-stream",
        size_bytes=0,
        content_base64="c3R1Yg==",  # "stub" in base64
    )


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
    _ = session_id  # stub: unused
    return ListArtifactsResult(artifacts=[])


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
    _ = session_id  # stub: unused
    return CloseSessionResult(status="closed")


def main() -> None:
    """Entry point for the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
