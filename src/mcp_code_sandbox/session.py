"""SessionManager — Docker container lifecycle management."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import (
    CloseSessionResult,
    ErrorResponse,
    RunResult,
)

if TYPE_CHECKING:
    import docker
    from docker.models.containers import Container

log = structlog.get_logger("mcp_code_sandbox.session")


class SessionManager:
    """Manage sandbox container lifecycle. All methods are synchronous."""

    def __init__(self, config: SandboxConfig, docker_client: docker.DockerClient) -> None:
        self._config = config
        self._client = docker_client
        self._sessions: dict[str, Container] = {}
        self._last_accessed: dict[str, float] = {}

    @staticmethod
    def generate_session_id() -> str:
        """Generate a new session ID in the format sess_<12hex>."""
        return f"sess_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def generate_run_id() -> str:
        """Generate a new run ID with timestamp."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        short = uuid.uuid4().hex[:4]
        return f"run_{ts}_{short}"

    def get_or_create(self, session_id: str | None = None) -> tuple[str, Container]:
        """Get existing container or create a new one.

        Returns (session_id, container).
        """
        sid = session_id or self.generate_session_id()

        if sid in self._sessions:
            self._last_accessed[sid] = time.monotonic()
            log.debug("session_reused", session_id=sid)
            return sid, self._sessions[sid]

        log.info("session_creating", session_id=sid, image=self._config.image)
        start = time.monotonic()

        container: Container = self._client.containers.create(
            image=self._config.image,
            command=["sleep", "infinity"],
            name=f"sandbox-{sid}",
            labels={"app": "mcp-code-sandbox", "session_id": sid},
            network_disabled=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            mem_limit=self._config.memory_limit,
            nano_cpus=int(self._config.cpu_limit * 1e9),
            detach=True,
        )
        container.start()

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("session_created", session_id=sid, duration_ms=duration_ms)

        self._sessions[sid] = container
        self._last_accessed[sid] = time.monotonic()
        return sid, container

    def execute(self, session_id: str | None, code: str) -> RunResult | ErrorResponse:
        """Execute Python code in the session container."""
        try:
            sid, container = self.get_or_create(session_id)
        except Exception as exc:
            return self._map_docker_error(exc, session_id or "unknown")

        run_id = self.generate_run_id()
        log.info("container_exec_start", session_id=sid, run_id=run_id, code_bytes=len(code))

        start = time.monotonic()
        try:
            exit_code, output = container.exec_run(
                ["python", "-c", code],
                workdir="/mnt/data",
                demux=True,
            )
        except Exception as exc:
            return self._map_docker_error(exc, sid)

        duration_ms = int((time.monotonic() - start) * 1000)

        stdout_bytes = output[0] if output[0] else b""
        stderr_bytes = output[1] if output[1] else b""

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        log.info(
            "container_exec_done",
            session_id=sid,
            run_id=run_id,
            exit_code=exit_code,
            stdout_bytes=len(stdout_bytes),
            stderr_bytes=len(stderr_bytes),
            duration_ms=duration_ms,
        )

        return RunResult(
            session_id=sid,
            run_id=run_id,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifacts=[],
            duration_ms=duration_ms,
        )

    def close(self, session_id: str) -> CloseSessionResult | ErrorResponse:
        """Destroy a session container."""
        if session_id not in self._sessions:
            return ErrorResponse(
                error="session_not_found",
                message=f"No active session with id {session_id}",
            )

        container = self._sessions.pop(session_id)
        self._last_accessed.pop(session_id, None)

        log.info("session_destroying", session_id=session_id)
        try:
            container.remove(force=True)
        except Exception as exc:
            log.error("session_destroy_failed", session_id=session_id, error=str(exc))
            return self._map_docker_error(exc, session_id)

        log.info("session_destroyed", session_id=session_id)
        return CloseSessionResult(status="closed")

    @property
    def sessions(self) -> dict[str, Any]:
        """Access to session dict for inspection."""
        return self._sessions

    @property
    def last_accessed(self) -> dict[str, float]:
        """Access to last_accessed timestamps."""
        return self._last_accessed

    def _map_docker_error(self, exc: Exception, session_id: str) -> ErrorResponse:
        """Map docker-py exceptions to structured ErrorResponse."""
        from docker.errors import APIError, DockerException, NotFound

        log.error(
            "docker_error",
            session_id=session_id,
            error=str(exc),
            exc_type=type(exc).__name__,
        )

        if isinstance(exc, NotFound):
            return ErrorResponse(
                error="session_not_found",
                message=f"Container for session {session_id} not found",
            )
        if isinstance(exc, APIError):
            return ErrorResponse(
                error="docker_error",
                message=f"Docker API error: {exc.explanation or str(exc)}",
            )
        if isinstance(exc, DockerException):
            return ErrorResponse(
                error="docker_unavailable",
                message=f"Docker unavailable: {exc}",
            )
        return ErrorResponse(
            error="execution_failed",
            message=str(exc),
        )
