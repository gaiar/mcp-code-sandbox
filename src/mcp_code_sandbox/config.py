"""Configuration via pydantic-settings with environment variable support."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class SandboxConfig(BaseSettings):
    """Sandbox server configuration. All values configurable via SANDBOX_* env vars."""

    model_config = {"env_prefix": "SANDBOX_"}

    # Container resource limits
    memory_limit: str = "512m"
    cpu_limit: float = 1.0

    # Execution
    exec_timeout_s: int = 60

    # Session management
    session_ttl_m: int = 30
    max_sessions: int = 10
    cleanup_interval_m: int = 5

    # Size limits
    max_upload_bytes: int = 50 * 1024 * 1024  # 50MB
    max_artifact_read_bytes: int = 10 * 1024 * 1024  # 10MB
    max_output_bytes: int = 100 * 1024  # 100KB
    max_code_bytes: int = 100 * 1024  # 100KB

    # Docker
    image: str = "llm-sandbox:latest"

    # HTTP artifact server
    http_host: str = "127.0.0.1"
    http_port: int = 8080

    # Logging
    log_level: str = "INFO"
    log_file: Path = Path("logs/sandbox.log")
    log_format: Literal["console", "json"] = "console"
