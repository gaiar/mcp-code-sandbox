"""Shared test fixtures."""

import contextlib
from collections.abc import Generator

import docker
import pytest

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.session import SessionManager


@pytest.fixture
def sandbox_config() -> SandboxConfig:
    """Provide default sandbox config for tests."""
    return SandboxConfig()


@pytest.fixture
def docker_client() -> docker.DockerClient:
    """Provide a Docker client (requires Docker daemon)."""
    return docker.from_env()


@pytest.fixture
def session_manager(
    sandbox_config: SandboxConfig,
    docker_client: docker.DockerClient,
) -> Generator[SessionManager, None, None]:
    """Provide a SessionManager with cleanup of all sessions on teardown."""
    mgr = SessionManager(sandbox_config, docker_client)
    yield mgr
    # Cleanup: force-remove all containers created during the test
    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True)
    mgr.sessions.clear()
