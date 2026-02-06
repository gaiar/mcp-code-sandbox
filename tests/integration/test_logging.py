"""Integration tests for structured logging — verify log events from real workflow."""

import contextlib
import tempfile
from collections.abc import Generator
from pathlib import Path

import docker
import pytest

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.logging import configure_logging
from mcp_code_sandbox.models import RunResult, UploadResult
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


@pytest.fixture
def logged_manager(tmp_path: Path) -> Generator[tuple[SessionManager, Path], None, None]:
    """SessionManager with logging to a temp file for inspection."""
    log_file = tmp_path / "test.log"
    config = SandboxConfig(log_file=log_file, log_level="DEBUG", log_format="console")
    configure_logging(config)

    client = docker.from_env()
    mgr = SessionManager(config, client)

    yield mgr, log_file

    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True, v=True)
    mgr.sessions.clear()


def test_execute_produces_log_events(
    logged_manager: tuple[SessionManager, Path],
) -> None:
    """Full execute workflow produces expected log events."""
    mgr, log_file = logged_manager

    result = mgr.execute(None, "print('hello')")
    assert isinstance(result, RunResult)
    sid = result.session_id

    log_content = log_file.read_text()

    # Session creation
    assert "session_creating" in log_content
    assert "session_created" in log_content
    assert sid in log_content

    # Execution events
    assert "container_exec_start" in log_content
    assert "container_exec_done" in log_content
    assert "duration_ms" in log_content


def test_upload_produces_log_events(
    logged_manager: tuple[SessionManager, Path],
) -> None:
    """Upload workflow produces expected log events."""
    import base64

    mgr, log_file = logged_manager

    data = base64.b64encode(b"test data").decode()
    result = mgr.upload(None, "test.txt", data)
    assert isinstance(result, UploadResult)
    sid = result.session_id

    log_content = log_file.read_text()

    assert "file_uploaded" in log_content
    assert sid in log_content
    assert "test.txt" in log_content


def test_close_produces_log_events(
    logged_manager: tuple[SessionManager, Path],
) -> None:
    """Close session produces expected log events."""
    mgr, log_file = logged_manager

    result = mgr.execute(None, "print('hi')")
    assert isinstance(result, RunResult)
    sid = result.session_id

    mgr.close(sid)

    log_content = log_file.read_text()

    assert "session_destroying" in log_content
    assert "session_destroyed" in log_content


def test_no_stdout_leak() -> None:
    """Verify logging does not write to stdout."""
    import io
    import sys

    # Capture stdout
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test.log"
            config = SandboxConfig(log_file=log_file, log_level="DEBUG", log_format="console")
            configure_logging(config)

            client = docker.from_env()
            mgr = SessionManager(config, client)

            result = mgr.execute(None, "print('should not leak')")
            assert isinstance(result, RunResult)

            for _sid, container in list(mgr.sessions.items()):
                with contextlib.suppress(Exception):
                    container.remove(force=True, v=True)
    finally:
        sys.stdout = old_stdout

    stdout_output = captured.getvalue()
    # stdout should be empty — no log lines leaked
    assert stdout_output == "", f"Unexpected stdout output: {stdout_output!r}"
