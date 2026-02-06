"""Unit tests for input validation functions."""

import pytest

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import ErrorResponse
from mcp_code_sandbox.validation import (
    validate_code_size,
    validate_filename,
    validate_session_id,
    validate_upload_size,
)

# --- validate_session_id ---


def test_session_id_none_is_valid() -> None:
    """None means auto-generate — always valid."""
    assert validate_session_id(None) is None


@pytest.mark.parametrize(
    "sid",
    [
        "abc",
        "sess_a1b2c3d4e5f6",
        "my-session",
        "my_session",
        "A" * 64,
        "0",
    ],
)
def test_session_id_valid(sid: str) -> None:
    assert validate_session_id(sid) is None


@pytest.mark.parametrize(
    "sid",
    [
        "",
        "A" * 65,  # too long
        "has spaces",
        "has/slash",
        "has@sign",
        "hello!",
        "semi;colon",
    ],
)
def test_session_id_invalid(sid: str) -> None:
    result = validate_session_id(sid)
    assert isinstance(result, ErrorResponse)
    assert result.error == "invalid_session_id"


# --- validate_filename ---


@pytest.mark.parametrize(
    "name",
    [
        "data.csv",
        "report.pdf",
        "chart-v2.png",
        "my_file.txt",
        "a",
        "A" * 255,
    ],
)
def test_filename_valid(name: str) -> None:
    assert validate_filename(name) is None


@pytest.mark.parametrize(
    ("name", "expected_error"),
    [
        ("", "invalid_filename"),
        ("A" * 256, "invalid_filename"),
        ("has space.txt", "invalid_filename"),
        ("path/file.txt", "invalid_filename"),
        ("file@name.txt", "invalid_filename"),
        ("..hidden", "invalid_path"),
        ("foo..bar", "invalid_path"),
    ],
)
def test_filename_invalid(name: str, expected_error: str) -> None:
    result = validate_filename(name)
    assert isinstance(result, ErrorResponse)
    assert result.error == expected_error


# --- validate_code_size ---


def test_code_size_within_limit() -> None:
    config = SandboxConfig(max_code_bytes=1024)
    assert validate_code_size("print('hello')", config) is None


def test_code_size_at_limit() -> None:
    config = SandboxConfig(max_code_bytes=10)
    code = "a" * 10  # exactly 10 bytes
    assert validate_code_size(code, config) is None


def test_code_size_exceeds_limit() -> None:
    config = SandboxConfig(max_code_bytes=10)
    code = "a" * 11
    result = validate_code_size(code, config)
    assert isinstance(result, ErrorResponse)
    assert result.error == "code_too_large"
    assert "11 bytes" in result.message


def test_code_size_multibyte_chars() -> None:
    """Validation should count UTF-8 bytes, not characters."""
    config = SandboxConfig(max_code_bytes=10)
    # Each emoji is 4 bytes in UTF-8 → 3 emojis = 12 bytes > 10
    code = "\U0001f600" * 3
    result = validate_code_size(code, config)
    assert isinstance(result, ErrorResponse)
    assert result.error == "code_too_large"


# --- validate_upload_size ---


def test_upload_size_within_limit() -> None:
    config = SandboxConfig(max_upload_bytes=1024)
    # Small base64 string
    assert validate_upload_size("aGVsbG8=", config) is None


def test_upload_size_exceeds_limit() -> None:
    config = SandboxConfig(max_upload_bytes=10)
    # 10 bytes raw → ~16 chars base64. Generate oversized base64 content.
    big_b64 = "A" * 100
    result = validate_upload_size(big_b64, config)
    assert isinstance(result, ErrorResponse)
    assert result.error == "upload_too_large"
    assert "limit" in result.message.lower()
