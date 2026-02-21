"""HTTP artifact server — serves files from sandbox containers."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import structlog
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from mcp_code_sandbox.models import ErrorResponse, ReadArtifactResult

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

        result = session_manager.read_file(session_id, path)
        if isinstance(result, ErrorResponse):
            if result.error == "artifact_too_large":
                return Response(content=result.message, status_code=413)
            if result.error in {"session_not_found", "not_found", "invalid_path"}:
                return Response(content=result.message, status_code=404)
            return Response(content=result.message, status_code=500)

        artifact = result
        assert isinstance(artifact, ReadArtifactResult)  # for type-narrowing
        file_bytes = base64.b64decode(artifact.content_base64)

        log.info(
            "artifact_download",
            session_id=session_id,
            filename=artifact.filename,
            size_bytes=len(file_bytes),
        )

        return Response(
            content=file_bytes,
            media_type=artifact.mime_type,
            headers={"Content-Disposition": f'inline; filename="{artifact.filename}"'},
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
