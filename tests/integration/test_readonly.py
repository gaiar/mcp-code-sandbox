"""Integration tests for read-only root filesystem hardening."""

import pytest

from mcp_code_sandbox.models import RunResult
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


def test_mnt_data_writable(session_manager: SessionManager) -> None:
    """Code can write files to /mnt/data/ (tmpfs mount)."""
    result = session_manager.execute(
        None,
        "with open('/mnt/data/test.txt', 'w') as f: f.write('ok'); print('written')",
    )
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert "written" in result.stdout


def test_tmp_writable(session_manager: SessionManager) -> None:
    """Code can write to /tmp (tmpfs mount)."""
    result = session_manager.execute(
        None,
        "with open('/tmp/test.txt', 'w') as f: f.write('ok'); print('written')",
    )
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert "written" in result.stdout


def test_root_fs_read_only(session_manager: SessionManager) -> None:
    """Code cannot write to root filesystem (read-only)."""
    result = session_manager.execute(
        None,
        "with open('/home/test.txt', 'w') as f: f.write('fail')",
    )
    assert isinstance(result, RunResult)
    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr or "Permission" in result.stderr
