"""Background cleanup — session TTL expiry and orphan removal."""

from __future__ import annotations

import contextlib
import threading
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import docker

    from mcp_code_sandbox.config import SandboxConfig
    from mcp_code_sandbox.session import SessionManager

log = structlog.get_logger("mcp_code_sandbox.cleanup")


def remove_orphan_containers(docker_client: docker.DockerClient) -> int:
    """Remove any leftover sandbox containers from a previous server run.

    Returns the number of orphans removed.
    """
    containers = docker_client.containers.list(
        all=True,
        filters={"label": "app=mcp-code-sandbox"},
    )
    removed = 0
    for container in containers:
        with contextlib.suppress(Exception):
            log.info(
                "orphan_removing",
                container_id=container.short_id,
                name=container.name,
            )
            container.remove(force=True)
            removed += 1
    if removed:
        log.warning("orphans_found", count=removed)
    return removed


def start_ttl_cleanup(
    config: SandboxConfig,
    session_manager: SessionManager,
) -> threading.Thread:
    """Start a daemon thread that periodically expires idle sessions.

    Returns the thread (already started).
    """

    def _cleanup_loop() -> None:
        interval_s = config.cleanup_interval_m * 60
        ttl_s = config.session_ttl_m * 60

        while True:
            time.sleep(interval_s)
            _expire_idle_sessions(session_manager, ttl_s)

    thread = threading.Thread(target=_cleanup_loop, daemon=True)
    thread.start()
    log.info(
        "ttl_cleanup_started",
        interval_m=config.cleanup_interval_m,
        ttl_m=config.session_ttl_m,
    )
    return thread


def _expire_idle_sessions(session_manager: SessionManager, ttl_s: float) -> None:
    """Check all sessions and destroy those idle longer than ttl_s."""
    now = time.monotonic()
    expired: list[str] = []

    for sid, last_access in list(session_manager.last_accessed.items()):
        idle_s = now - last_access
        if idle_s > ttl_s:
            expired.append(sid)

    for sid in expired:
        idle_m = int((now - session_manager.last_accessed.get(sid, now)) / 60)
        log.info("session_ttl_expired", session_id=sid, idle_minutes=idle_m)
        session_manager.close(sid)
