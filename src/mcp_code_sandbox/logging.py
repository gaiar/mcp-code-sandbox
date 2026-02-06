"""Structured logging setup with structlog — file handler only, never stdout."""

import logging
import logging.handlers
from contextvars import ContextVar

import structlog

from mcp_code_sandbox.config import SandboxConfig

# Correlation context vars — set once at tool entry, auto-attached to all log lines
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)


def _add_context_vars(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Inject session_id and run_id from contextvars into every log line."""
    sid = session_id_var.get()
    if sid is not None:
        event_dict.setdefault("session_id", sid)
    rid = run_id_var.get()
    if rid is not None:
        event_dict.setdefault("run_id", rid)
    return event_dict


def configure_logging(config: SandboxConfig) -> None:
    """Set up structlog with file-only output. Never writes to stdout."""
    config.log_file.parent.mkdir(parents=True, exist_ok=True)

    # File handler — RotatingFileHandler to prevent unbounded growth
    file_handler = logging.handlers.RotatingFileHandler(
        config.log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
    )
    file_handler.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # Remove all existing handlers to prevent stdout leaks
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # Choose renderer based on format
    if config.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()  # type: ignore[assignment]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_context_vars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    file_handler.setFormatter(formatter)
