"""Test SandboxConfig defaults and environment variable overrides."""

from pathlib import Path

import pytest

from mcp_code_sandbox.config import SandboxConfig


def test_defaults() -> None:
    config = SandboxConfig()
    assert config.memory_limit == "512m"
    assert config.cpu_limit == 1.0
    assert config.exec_timeout_s == 60
    assert config.session_ttl_m == 30
    assert config.max_sessions == 10
    assert config.cleanup_interval_m == 5
    assert config.max_upload_bytes == 50 * 1024 * 1024
    assert config.max_artifact_read_bytes == 10 * 1024 * 1024
    assert config.max_output_bytes == 100 * 1024
    assert config.max_code_bytes == 100 * 1024
    assert config.image == "llm-sandbox:latest"
    assert config.http_host == "127.0.0.1"
    assert config.http_port == 8080
    assert config.log_level == "INFO"
    assert config.log_file == Path("logs/sandbox.log")
    assert config.log_format == "console"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_EXEC_TIMEOUT_S", "30")
    monkeypatch.setenv("SANDBOX_MAX_SESSIONS", "5")
    monkeypatch.setenv("SANDBOX_IMAGE", "custom:v2")
    monkeypatch.setenv("SANDBOX_LOG_FORMAT", "json")
    config = SandboxConfig()
    assert config.exec_timeout_s == 30
    assert config.max_sessions == 5
    assert config.image == "custom:v2"
    assert config.log_format == "json"
