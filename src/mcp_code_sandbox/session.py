"""SessionManager — Docker container lifecycle management."""

from __future__ import annotations

import base64
import io
import mimetypes
import re
import tarfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import structlog

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import (
    ArtifactInfo,
    CloseSessionResult,
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)

if TYPE_CHECKING:
    import docker
    from docker.models.containers import Container

log = structlog.get_logger("mcp_code_sandbox.session")

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,255}$")


def _validate_filename(filename: str) -> ErrorResponse | None:
    """Validate filename against allowlist. Return ErrorResponse if invalid."""
    if not _FILENAME_RE.match(filename):
        return ErrorResponse(
            error="invalid_filename",
            message=(
                f"Invalid filename '{filename}'. "
                "Only letters, numbers, dots, hyphens, and underscores allowed."
            ),
        )
    if ".." in filename:
        return ErrorResponse(
            error="invalid_path",
            message="Path traversal not allowed",
        )
    return None


def _validate_path(path: str) -> ErrorResponse | None:
    """Validate that path resolves within /mnt/data/."""
    resolved = str(PurePosixPath("/mnt/data").joinpath(PurePosixPath(path).name))
    if not resolved.startswith("/mnt/data/"):
        return ErrorResponse(
            error="invalid_path",
            message="Path outside /mnt/data/",
        )
    return None


def _build_tar(filename: str, data: bytes) -> bytes:
    """Build an in-memory tar archive containing a single file."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf.read()


def _extract_from_tar(tar_stream: Any) -> bytes:
    """Extract a single file's bytes from a docker get_archive tar stream."""
    buf = io.BytesIO()
    for chunk in tar_stream:
        buf.write(chunk)
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        members = tar.getmembers()
        if not members:
            return b""
        f = tar.extractfile(members[0])
        if f is None:
            return b""
        return f.read()


class _FileInfo:
    """Snapshot of a file in /mnt/data."""

    __slots__ = ("mtime", "name", "size")

    def __init__(self, name: str, size: int, mtime: str) -> None:
        self.name = name
        self.size = size
        self.mtime = mtime


class SessionManager:
    """Manage sandbox container lifecycle. All methods are synchronous."""

    def __init__(self, config: SandboxConfig, docker_client: docker.DockerClient) -> None:
        self._config = config
        self._client = docker_client
        self._sessions: dict[str, Container] = {}
        self._last_accessed: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._http_enabled = False

    def enable_http(self) -> None:
        """Signal that the HTTP artifact server is running."""
        self._http_enabled = True

    def _download_url(self, session_id: str, filename: str) -> str | None:
        """Build download URL for an artifact, or None if HTTP server not running."""
        if not self._http_enabled:
            return None
        host = self._config.http_host
        if host in ("0.0.0.0", "127.0.0.1"):
            host = "localhost"
        return f"http://{host}:{self._config.http_port}/files/{session_id}/{filename}"

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

    def get_or_create(
        self, session_id: str | None = None
    ) -> tuple[str, Container] | ErrorResponse:
        """Get existing container or create a new one.

        Returns (session_id, container) or ErrorResponse if max_sessions reached.
        """
        sid = session_id or self.generate_session_id()

        if sid in self._sessions:
            self._last_accessed[sid] = time.monotonic()
            log.debug("session_reused", session_id=sid)
            return sid, self._sessions[sid]

        # Enforce max sessions limit
        if len(self._sessions) >= self._config.max_sessions:
            log.warning(
                "max_sessions_reached",
                current=len(self._sessions),
                limit=self._config.max_sessions,
            )
            return ErrorResponse(
                error="max_sessions",
                message=(
                    f"Maximum {self._config.max_sessions} concurrent sessions reached. "
                    "Close an existing session first."
                ),
            )

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
            read_only=True,
            tmpfs={"/tmp": "size=64m,uid=1000,gid=1000"},
            volumes=["/mnt/data"],
            mem_limit=self._config.memory_limit,
            nano_cpus=int(self._config.cpu_limit * 1e9),
            detach=True,
        )
        container.start()

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("session_created", session_id=sid, duration_ms=duration_ms)

        self._sessions[sid] = container
        self._last_accessed[sid] = time.monotonic()
        self._locks[sid] = threading.Lock()
        return sid, container

    # --- Upload ---

    def upload(
        self,
        session_id: str | None,
        filename: str,
        content_base64: str,
        overwrite: bool = False,
    ) -> UploadResult | ErrorResponse:
        """Upload a file into the session container at /mnt/data/<filename>."""
        err = _validate_filename(filename)
        if err:
            return err

        try:
            result = self.get_or_create(session_id)
        except Exception as exc:
            return self._map_docker_error(exc, session_id or "unknown")
        if isinstance(result, ErrorResponse):
            return result
        sid, container = result

        # Check if file exists (unless overwrite)
        if not overwrite:
            exit_code, _ = container.exec_run(
                ["test", "-f", f"/mnt/data/{filename}"],
                demux=True,
            )
            if exit_code == 0:
                return ErrorResponse(
                    error="file_exists",
                    message=f"{filename} already exists. Set overwrite=true to replace.",
                )

        try:
            data = base64.b64decode(content_base64)
        except Exception:
            return ErrorResponse(
                error="invalid_content",
                message="content_base64 is not valid base64",
            )

        tar_bytes = _build_tar(filename, data)
        container.put_archive("/mnt/data", tar_bytes)

        path = f"/mnt/data/{filename}"
        log.info(
            "file_uploaded",
            session_id=sid,
            filename=filename,
            size_bytes=len(data),
        )
        return UploadResult(session_id=sid, path=path)

    # --- Artifact scanning ---

    def _snapshot_files(self, container: Container) -> dict[str, _FileInfo]:
        """Snapshot current files in /mnt/data (name, size, mtime)."""
        exit_code, output = container.exec_run(
            [
                "find",
                "/mnt/data",
                "-maxdepth",
                "1",
                "-type",
                "f",
                "-printf",
                "%f\\t%s\\t%T@\\n",
            ],
            demux=True,
        )
        if exit_code != 0:
            return {}

        stdout = (output[0] or b"").decode("utf-8", errors="replace")
        files: dict[str, _FileInfo] = {}
        for line in stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                files[parts[0]] = _FileInfo(name=parts[0], size=int(parts[1]), mtime=parts[2])
        return files

    def _diff_snapshots(
        self,
        before: dict[str, _FileInfo],
        after: dict[str, _FileInfo],
        session_id: str,
    ) -> list[ArtifactInfo]:
        """Compute new/changed files between two snapshots."""
        artifacts: list[ArtifactInfo] = []
        for name, info in after.items():
            if name not in before or before[name].mtime != info.mtime:
                mime, _ = mimetypes.guess_type(name)
                artifacts.append(
                    ArtifactInfo(
                        path=f"/mnt/data/{name}",
                        filename=name,
                        size_bytes=info.size,
                        mime_type=mime or "application/octet-stream",
                        download_url=self._download_url(session_id, name),
                    )
                )
        return artifacts

    # --- Execute ---

    def execute(self, session_id: str | None, code: str) -> RunResult | ErrorResponse:
        """Execute Python code in the session container."""
        try:
            result = self.get_or_create(session_id)
        except Exception as exc:
            return self._map_docker_error(exc, session_id or "unknown")
        if isinstance(result, ErrorResponse):
            return result
        sid, container = result

        # Per-session lock — reject if already busy
        lock = self._locks.get(sid)
        if lock is None:
            lock = threading.Lock()
            self._locks[sid] = lock
        if not lock.acquire(blocking=False):
            return ErrorResponse(
                error="session_busy",
                message=(
                    f"Session {sid} is already executing code. Wait or use a different session."
                ),
            )
        try:
            return self._execute_locked(sid, container, code)
        finally:
            lock.release()

    def _execute_locked(
        self, sid: str, container: Container, code: str
    ) -> RunResult | ErrorResponse:
        """Execute code while holding the session lock."""
        run_id = self.generate_run_id()
        log.info("container_exec_start", session_id=sid, run_id=run_id, code_bytes=len(code))

        # Snapshot before execution
        before = self._snapshot_files(container)

        start = time.monotonic()
        try:
            exit_code, output = container.exec_run(
                ["timeout", str(self._config.exec_timeout_s), "python", "-c", code],
                workdir="/mnt/data",
                demux=True,
            )
        except Exception as exc:
            return self._map_docker_error(exc, sid)

        duration_ms = int((time.monotonic() - start) * 1000)

        # timeout(1) returns 124 when it kills the child process
        timed_out = exit_code == 124
        if timed_out:
            exit_code = -1

        stdout_bytes = output[0] if output[0] else b""
        stderr_bytes = output[1] if output[1] else b""

        # Truncate output if exceeding limit
        max_out = self._config.max_output_bytes
        stdout_truncated = len(stdout_bytes) > max_out
        stderr_truncated = len(stderr_bytes) > max_out
        if stdout_truncated:
            stdout_bytes = stdout_bytes[:max_out]
            log.warning(
                "stdout_truncated",
                session_id=sid,
                original_bytes=len(output[0] or b""),
                limit_bytes=max_out,
            )
        if stderr_truncated:
            stderr_bytes = stderr_bytes[:max_out]
            log.warning(
                "stderr_truncated",
                session_id=sid,
                original_bytes=len(output[1] or b""),
                limit_bytes=max_out,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if timed_out:
            stderr += f"\nExecution timed out after {self._config.exec_timeout_s}s"

        # Artifact scan only on success
        artifacts: list[ArtifactInfo] = []
        if exit_code == 0:
            after = self._snapshot_files(container)
            artifacts = self._diff_snapshots(before, after, sid)
            log.debug(
                "artifact_scan",
                session_id=sid,
                before_count=len(before),
                after_count=len(after),
                new_artifacts=[a.filename for a in artifacts],
            )

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
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            artifacts=artifacts,
            duration_ms=duration_ms,
        )

    # --- List artifacts ---

    def list_files(self, session_id: str) -> ListArtifactsResult | ErrorResponse:
        """List all files in /mnt/data/ for a session."""
        if session_id not in self._sessions:
            return ErrorResponse(
                error="session_not_found",
                message=f"No active session with id {session_id}",
            )

        container = self._sessions[session_id]
        self._last_accessed[session_id] = time.monotonic()

        snapshot = self._snapshot_files(container)
        artifacts = []
        for name, info in snapshot.items():
            mime, _ = mimetypes.guess_type(name)
            artifacts.append(
                ArtifactInfo(
                    path=f"/mnt/data/{name}",
                    filename=name,
                    size_bytes=info.size,
                    mime_type=mime or "application/octet-stream",
                    download_url=self._download_url(session_id, name),
                )
            )
        return ListArtifactsResult(artifacts=artifacts)

    # --- Read artifact ---

    def read_file(self, session_id: str, path: str) -> ReadArtifactResult | ErrorResponse:
        """Read a file from the session container as base64."""
        if session_id not in self._sessions:
            return ErrorResponse(
                error="session_not_found",
                message=f"No active session with id {session_id}",
            )

        err = _validate_path(path)
        if err:
            return err

        container = self._sessions[session_id]
        self._last_accessed[session_id] = time.monotonic()
        filename = PurePosixPath(path).name

        try:
            tar_stream, _stat = container.get_archive(path)
        except Exception:
            return ErrorResponse(
                error="not_found",
                message=f"No artifact at {path}",
            )

        file_bytes = _extract_from_tar(tar_stream)
        size = len(file_bytes)

        if size > self._config.max_artifact_read_bytes:
            return ErrorResponse(
                error="artifact_too_large",
                message=(
                    f"{filename} is {size // (1024 * 1024)}MB, "
                    f"exceeds {self._config.max_artifact_read_bytes // (1024 * 1024)}MB limit."
                ),
                size_bytes=size,
            )

        mime, _ = mimetypes.guess_type(filename)
        content_b64 = base64.b64encode(file_bytes).decode("ascii")

        return ReadArtifactResult(
            path=path,
            filename=filename,
            mime_type=mime or "application/octet-stream",
            size_bytes=size,
            content_base64=content_b64,
        )

    # --- Close ---

    def close(self, session_id: str) -> CloseSessionResult | ErrorResponse:
        """Destroy a session container."""
        if session_id not in self._sessions:
            return ErrorResponse(
                error="session_not_found",
                message=f"No active session with id {session_id}",
            )

        container = self._sessions.pop(session_id)
        self._last_accessed.pop(session_id, None)
        self._locks.pop(session_id, None)

        log.info("session_destroying", session_id=session_id)
        try:
            container.remove(force=True, v=True)
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
