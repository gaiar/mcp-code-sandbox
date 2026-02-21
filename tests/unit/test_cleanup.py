"""Unit tests for session TTL cleanup and orphan removal."""

from unittest.mock import MagicMock, patch

from mcp_code_sandbox.cleanup import _expire_idle_sessions, remove_orphan_containers
from mcp_code_sandbox.models import CloseSessionResult, ErrorResponse


def test_remove_orphan_containers() -> None:
    """Orphan containers with matching label are removed."""
    mock_client = MagicMock()
    c1 = MagicMock(short_id="abc123", name="sandbox-sess_aaa")
    c2 = MagicMock(short_id="def456", name="sandbox-sess_bbb")
    mock_client.containers.list.return_value = [c1, c2]

    removed = remove_orphan_containers(mock_client)

    assert removed == 2
    c1.remove.assert_called_once_with(force=True)
    c2.remove.assert_called_once_with(force=True)
    mock_client.containers.list.assert_called_once_with(
        all=True,
        filters={"label": "app=mcp-code-sandbox"},
    )


def test_remove_orphan_containers_none() -> None:
    """No orphans means nothing removed."""
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []

    removed = remove_orphan_containers(mock_client)
    assert removed == 0


def test_expire_idle_sessions() -> None:
    """Sessions idle beyond TTL are closed."""
    mgr = MagicMock()
    mgr.last_accessed = {
        "sess_old": 0.0,  # Idle since time 0
        "sess_recent": 9999999999.0,  # Very recent
    }
    mgr.close.return_value = CloseSessionResult(status="closed")

    # With a TTL of 60s and current monotonic time >> 60s,
    # sess_old should expire but sess_recent should not
    with patch("mcp_code_sandbox.cleanup.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        _expire_idle_sessions(mgr, ttl_s=60.0)

    mgr.close.assert_called_once_with("sess_old")


def test_expire_idle_sessions_busy_deferred() -> None:
    """Busy sessions are retried in later cleanup cycles."""
    mgr = MagicMock()
    mgr.last_accessed = {"sess_busy": 0.0}
    mgr.close.return_value = ErrorResponse(error="session_busy", message="still running")

    with patch("mcp_code_sandbox.cleanup.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        _expire_idle_sessions(mgr, ttl_s=60.0)

    mgr.close.assert_called_once_with("sess_busy")
