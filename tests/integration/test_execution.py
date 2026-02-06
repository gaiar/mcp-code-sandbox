"""Integration tests for run_python and close_session (Stage 1)."""

import pytest

from mcp_code_sandbox.models import CloseSessionResult, ErrorResponse, RunResult
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


def test_run_python_simple(session_manager: SessionManager) -> None:
    """Run simple code and verify stdout."""
    result = session_manager.execute(None, "print(2 + 2)")
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert result.stdout.strip() == "4"
    assert result.stderr == ""
    assert result.session_id.startswith("sess_")
    assert result.run_id.startswith("run_")
    assert result.duration_ms >= 0


def test_run_python_stderr_and_error(session_manager: SessionManager) -> None:
    """Run code that raises an exception — exit_code=1 and stderr has traceback."""
    result = session_manager.execute(None, "raise ValueError('test error')")
    assert isinstance(result, RunResult)
    assert result.exit_code != 0
    assert "ValueError" in result.stderr
    assert "test error" in result.stderr


def test_session_reuse(session_manager: SessionManager) -> None:
    """Two execute calls with same session_id share the same container."""
    # First call creates session
    result1 = session_manager.execute(None, "print('first')")
    assert isinstance(result1, RunResult)
    sid = result1.session_id

    # Second call reuses session — write a file, then read it
    result2 = session_manager.execute(
        sid, "with open('/mnt/data/test.txt', 'w') as f: f.write('hello')"
    )
    assert isinstance(result2, RunResult)
    assert result2.exit_code == 0

    result3 = session_manager.execute(sid, "print(open('/mnt/data/test.txt').read())")
    assert isinstance(result3, RunResult)
    assert result3.stdout.strip() == "hello"


def test_close_session(session_manager: SessionManager) -> None:
    """Close a session and verify the container is removed."""
    result = session_manager.execute(None, "print('hi')")
    assert isinstance(result, RunResult)
    sid = result.session_id

    close_result = session_manager.close(sid)
    assert isinstance(close_result, CloseSessionResult)
    assert close_result.status == "closed"

    # Session should no longer exist
    assert sid not in session_manager.sessions


def test_close_nonexistent_session(session_manager: SessionManager) -> None:
    """Closing a non-existent session returns an error."""
    result = session_manager.close("sess_doesnotexist")
    assert isinstance(result, ErrorResponse)
    assert result.error == "session_not_found"


def test_network_disabled(session_manager: SessionManager) -> None:
    """Verify sandbox cannot make outbound network requests."""
    code = "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=5)"
    result = session_manager.execute(None, code)
    assert isinstance(result, RunResult)
    assert result.exit_code != 0
    assert "Network is unreachable" in result.stderr or "URLError" in result.stderr
