"""Test structured logging setup."""

from pathlib import Path

import pytest
import structlog

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.logging import configure_logging, session_id_var


def test_logging_writes_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    config = SandboxConfig(log_file=log_file, log_level="DEBUG")
    configure_logging(config)

    log = structlog.get_logger("test")
    log.info("test_event", key="value")

    content = log_file.read_text()
    assert "test_event" in content
    assert "key" in content


def test_logging_not_on_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_file = tmp_path / "test.log"
    config = SandboxConfig(log_file=log_file, log_level="DEBUG")
    configure_logging(config)

    log = structlog.get_logger("test")
    log.info("should_not_be_on_stdout")

    captured = capsys.readouterr()
    assert "should_not_be_on_stdout" not in captured.out
    assert "should_not_be_on_stdout" not in captured.err


def test_session_id_context_var(tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    config = SandboxConfig(log_file=log_file, log_level="DEBUG")
    configure_logging(config)

    token = session_id_var.set("sess_test123")
    try:
        log = structlog.get_logger("test")
        log.info("with_session")
        content = log_file.read_text()
        assert "sess_test123" in content
    finally:
        session_id_var.reset(token)
