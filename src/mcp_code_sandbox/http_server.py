"""HTTP artifact server — serves files from sandbox containers."""

from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING

import structlog
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

if TYPE_CHECKING:
    from mcp_code_sandbox.config import SandboxConfig
    from mcp_code_sandbox.session import SessionManager

log = structlog.get_logger("mcp_code_sandbox.http")


def _make_app(session_manager: SessionManager) -> Starlette:
    """Create Starlette app with artifact download route."""

    async def download_artifact(request: Request) -> Response:
        session_id = request.path_params["session_id"]
        filename = request.path_params["filename"]
        path = f"/mnt/data/{filename}"

        if session_id not in session_manager.sessions:
            return Response(
                content=f"Session {session_id} not found",
                status_code=404,
            )

        container = session_manager.sessions[session_id]

        try:
            tar_stream, _stat = container.get_archive(path)
        except Exception:
            return Response(
                content=f"File {filename} not found in session {session_id}",
                status_code=404,
            )

        # Extract file from tar
        import io
        import tarfile

        buf = io.BytesIO()
        for chunk in tar_stream:
            buf.write(chunk)
        buf.seek(0)

        with tarfile.open(fileobj=buf, mode="r") as tar:
            members = tar.getmembers()
            if not members:
                return Response(content="Empty archive", status_code=404)
            f = tar.extractfile(members[0])
            if f is None:
                return Response(content="Cannot read file", status_code=404)
            file_bytes = f.read()

        mime, _ = mimetypes.guess_type(filename)
        content_type = mime or "application/octet-stream"

        log.info(
            "artifact_download",
            session_id=session_id,
            filename=filename,
            size_bytes=len(file_bytes),
        )

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    routes = [
        Route(
            "/files/{session_id}/{filename}",
            download_artifact,
            methods=["GET"],
        ),
    ]

    return Starlette(routes=routes)


def run_http_server(
    config: SandboxConfig,
    session_manager: SessionManager,
) -> None:
    """Start the HTTP artifact server (blocking). Run in a thread."""
    app = _make_app(session_manager)
    log.info(
        "http_server_starting",
        host=config.http_host,
        port=config.http_port,
    )
    uvicorn.run(
        app,
        host=config.http_host,
        port=config.http_port,
        log_level="warning",
    )
