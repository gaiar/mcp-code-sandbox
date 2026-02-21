"""Integration tests for execution limits (timeout, truncation, concurrency)."""

import contextlib
import threading
from collections.abc import Generator

import docker
import pytest

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import ErrorResponse, RunResult
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


@pytest.fixture
def short_timeout_manager() -> Generator[SessionManager, None, None]:
    """SessionManager with a very short exec timeout for testing."""
    client = docker.from_env()
    config = SandboxConfig(exec_timeout_s=3)
    mgr = SessionManager(config, client)
    yield mgr
    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True, v=True)
    mgr.sessions.clear()


@pytest.fixture
def small_output_manager() -> Generator[SessionManager, None, None]:
    """SessionManager with a small output limit for testing truncation."""
    client = docker.from_env()
    config = SandboxConfig(max_output_bytes=100)
    mgr = SessionManager(config, client)
    yield mgr
    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True, v=True)
    mgr.sessions.clear()


def test_timeout_returns_exit_code_minus_1(
    short_timeout_manager: SessionManager,
) -> None:
    """Code exceeding exec_timeout_s returns exit_code=-1 with timeout message."""
    result = short_timeout_manager.execute(None, "import time; time.sleep(120)")
    assert isinstance(result, RunResult)
    assert result.exit_code == -1
    assert "timed out" in result.stderr.lower()


def test_stdout_truncation(small_output_manager: SessionManager) -> None:
    """stdout exceeding max_output_bytes is truncated with flag set."""
    # Print 500 bytes (well over 100-byte limit)
    code = "print('A' * 500)"
    result = small_output_manager.execute(None, code)
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert result.stdout_truncated is True
    assert len(result.stdout.encode("utf-8")) <= 100


def test_stderr_truncation(small_output_manager: SessionManager) -> None:
    """stderr exceeding max_output_bytes is truncated with flag set."""
    # Write 500 bytes to stderr
    code = "import sys; sys.stderr.write('E' * 500)"
    result = small_output_manager.execute(None, code)
    assert isinstance(result, RunResult)
    assert result.stderr_truncated is True
    assert len(result.stderr.encode("utf-8")) <= 100


def test_normal_output_not_truncated(session_manager: SessionManager) -> None:
    """Normal-sized output has truncation flags set to False."""
    result = session_manager.execute(None, "print('hello')")
    assert isinstance(result, RunResult)
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


def test_session_busy_rejects_concurrent_execution(
    short_timeout_manager: SessionManager,
) -> None:
    """Concurrent execute on the same session returns session_busy error."""
    # Create a session first with a quick command
    r = short_timeout_manager.execute(None, "print('init')")
    assert isinstance(r, RunResult)
    sid = r.session_id

    # Start a long-running command in a background thread
    results: list[RunResult | ErrorResponse] = []

    def long_run() -> None:
        result = short_timeout_manager.execute(sid, "import time; time.sleep(10)")
        results.append(result)

    t = threading.Thread(target=long_run)
    t.start()

    # Give the thread time to acquire the lock
    import time

    time.sleep(0.5)

    # Try concurrent execution on the same session — should be rejected
    concurrent_result = short_timeout_manager.execute(sid, "print('concurrent')")
    assert isinstance(concurrent_result, ErrorResponse)
    assert concurrent_result.error == "session_busy"

    # Wait for background thread to finish (it will timeout at 3s)
    t.join(timeout=10)
    assert len(results) == 1


def test_close_session_busy_when_execution_in_flight(
    short_timeout_manager: SessionManager,
) -> None:
    """close() returns session_busy while the same session is executing."""
    r = short_timeout_manager.execute(None, "print('init')")
    assert isinstance(r, RunResult)
    sid = r.session_id

    results: list[RunResult | ErrorResponse] = []
    t = threading.Thread(
        target=lambda: results.append(
            short_timeout_manager.execute(sid, "import time; time.sleep(10)")
        )
    )
    t.start()
    import time

    time.sleep(0.5)

    close_result = short_timeout_manager.close(sid)
    assert isinstance(close_result, ErrorResponse)
    assert close_result.error == "session_busy"

    t.join(timeout=10)
    assert len(results) == 1
