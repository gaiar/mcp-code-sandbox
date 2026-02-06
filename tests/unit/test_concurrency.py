"""Unit tests for concurrency guards (max_sessions)."""

from unittest.mock import MagicMock

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import ErrorResponse
from mcp_code_sandbox.session import SessionManager


def test_max_sessions_rejects_new_session() -> None:
    """When max_sessions is reached, get_or_create returns ErrorResponse."""
    config = SandboxConfig(max_sessions=2)
    mock_client = MagicMock()
    mgr = SessionManager(config, mock_client)

    # Simulate 2 existing sessions
    mgr._sessions["sess_aaa"] = MagicMock()
    mgr._sessions["sess_bbb"] = MagicMock()

    result = mgr.get_or_create("sess_new")
    assert isinstance(result, ErrorResponse)
    assert result.error == "max_sessions"
    assert "2" in result.message


def test_max_sessions_allows_existing_session_reuse() -> None:
    """Reusing an existing session doesn't count as a new session."""
    config = SandboxConfig(max_sessions=1)
    mock_client = MagicMock()
    mgr = SessionManager(config, mock_client)

    # Simulate 1 existing session
    mgr._sessions["sess_aaa"] = MagicMock()
    mgr._last_accessed["sess_aaa"] = 0.0

    result = mgr.get_or_create("sess_aaa")
    assert not isinstance(result, ErrorResponse)
    sid, _container = result
    assert sid == "sess_aaa"
