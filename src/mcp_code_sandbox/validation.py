"""Input validation — all validators return ErrorResponse or None."""

from __future__ import annotations

import re

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import ErrorResponse

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,255}$")


def validate_session_id(session_id: str | None) -> ErrorResponse | None:
    """Validate client-provided session_id format. None means auto-generate (valid)."""
    if session_id is None:
        return None
    if not _SESSION_ID_RE.match(session_id):
        return ErrorResponse(
            error="invalid_session_id",
            message=(
                f"Invalid session_id '{session_id}'. "
                "Must be 1-64 characters: letters, numbers, hyphens, underscores."
            ),
        )
    return None


def validate_filename(filename: str) -> ErrorResponse | None:
    """Validate filename against allowlist."""
    if not _FILENAME_RE.match(filename):
        return ErrorResponse(
            error="invalid_filename",
            message=(
                f"Invalid filename '{filename}'. "
                "Only letters, numbers, dots, hyphens, and underscores allowed (max 255 chars)."
            ),
        )
    if ".." in filename:
        return ErrorResponse(
            error="invalid_path",
            message="Path traversal not allowed.",
        )
    return None


def validate_code_size(code: str, config: SandboxConfig) -> ErrorResponse | None:
    """Reject code exceeding max_code_bytes."""
    if len(code.encode("utf-8")) > config.max_code_bytes:
        return ErrorResponse(
            error="code_too_large",
            message=(
                f"Code is {len(code.encode('utf-8'))} bytes, "
                f"exceeds {config.max_code_bytes} byte limit."
            ),
        )
    return None


def validate_upload_size(content_base64: str, config: SandboxConfig) -> ErrorResponse | None:
    """Reject upload exceeding max_upload_bytes (check base64 length before decoding)."""
    # Base64 encodes 3 bytes as 4 chars, so max base64 length is ceil(max_bytes * 4/3)
    max_b64_len = int(config.max_upload_bytes * 4 / 3) + 4  # padding
    if len(content_base64) > max_b64_len:
        return ErrorResponse(
            error="upload_too_large",
            message=(f"Upload exceeds {config.max_upload_bytes // (1024 * 1024)}MB limit."),
        )
    return None
