"""Integration tests for HTTP artifact server."""

import base64
import contextlib
import socket
import threading
import time
from collections.abc import Generator

import docker
import httpx
import pytest

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.http_server import run_http_server
from mcp_code_sandbox.models import RunResult, UploadResult
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


def _find_free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_port() -> int:
    return _find_free_port()


@pytest.fixture(scope="module")
def http_session_manager(
    http_port: int,
) -> Generator[SessionManager, None, None]:
    """SessionManager with HTTP enabled and a running HTTP server."""
    client = docker.from_env()
    config = SandboxConfig(http_host="127.0.0.1", http_port=http_port)
    mgr = SessionManager(config, client)
    mgr.enable_http()

    # Start HTTP server in background
    thread = threading.Thread(
        target=run_http_server,
        args=(config, mgr),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)  # Wait for server to start

    yield mgr

    # Cleanup
    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True, v=True)
    mgr.sessions.clear()


@pytest.fixture
def limited_http_session_manager() -> Generator[tuple[SessionManager, int], None, None]:
    """SessionManager with tiny artifact read limit to validate HTTP size guard."""
    port = _find_free_port()
    client = docker.from_env()
    config = SandboxConfig(
        http_host="127.0.0.1",
        http_port=port,
        max_artifact_read_bytes=8,
    )
    mgr = SessionManager(config, client)
    mgr.enable_http()

    thread = threading.Thread(
        target=run_http_server,
        args=(config, mgr),
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)

    yield mgr, port

    for _sid, container in list(mgr.sessions.items()):
        with contextlib.suppress(Exception):
            container.remove(force=True, v=True)
    mgr.sessions.clear()


def test_download_url_in_artifacts(http_session_manager: SessionManager, http_port: int) -> None:
    """Verify run_python includes download_url when HTTP server is running."""
    csv_data = b"x,y\n1,2\n"
    b64 = base64.b64encode(csv_data).decode()

    upload = http_session_manager.upload(None, "data.csv", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    code = "with open('/mnt/data/out.txt', 'w') as f: f.write('hello')"
    run = http_session_manager.execute(sid, code)
    assert isinstance(run, RunResult)
    assert run.exit_code == 0

    artifact_urls = {a.filename: a.download_url for a in run.artifacts}
    assert "out.txt" in artifact_urls
    assert artifact_urls["out.txt"] is not None
    assert f"/files/{sid}/out.txt" in artifact_urls["out.txt"]  # type: ignore[operator]


def test_http_download(http_session_manager: SessionManager, http_port: int) -> None:
    """Download a file via HTTP and verify content."""
    original = b"hello from artifact"
    b64 = base64.b64encode(original).decode()

    upload = http_session_manager.upload(None, "test.txt", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    resp = httpx.get(f"http://127.0.0.1:{http_port}/files/{sid}/test.txt")
    assert resp.status_code == 200
    assert resp.content == original
    assert "text/plain" in resp.headers["content-type"]


def test_http_download_png(http_session_manager: SessionManager, http_port: int) -> None:
    """Download a generated PNG via HTTP."""
    run = http_session_manager.execute(
        None,
        """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.plot([1, 2, 3])
plt.savefig('/mnt/data/test.png')
""",
    )
    assert isinstance(run, RunResult)
    assert run.exit_code == 0
    sid = run.session_id

    resp = httpx.get(f"http://127.0.0.1:{http_port}/files/{sid}/test.png")
    assert resp.status_code == 200
    assert resp.content[:4] == b"\x89PNG"
    assert "image/png" in resp.headers["content-type"]


def test_http_404_missing_session(http_session_manager: SessionManager, http_port: int) -> None:
    """HTTP returns 404 for nonexistent session."""
    _ = http_session_manager  # ensure fixture runs
    resp = httpx.get(f"http://127.0.0.1:{http_port}/files/sess_nope/file.txt")
    assert resp.status_code == 404


def test_http_404_missing_file(http_session_manager: SessionManager, http_port: int) -> None:
    """HTTP returns 404 for nonexistent file in valid session."""
    run = http_session_manager.execute(None, "print('hi')")
    assert isinstance(run, RunResult)
    sid = run.session_id

    resp = httpx.get(f"http://127.0.0.1:{http_port}/files/{sid}/nope.txt")
    assert resp.status_code == 404


def test_http_413_for_oversized_artifact(
    limited_http_session_manager: tuple[SessionManager, int],
) -> None:
    """HTTP returns 413 when artifact exceeds configured read size limit."""
    mgr, port = limited_http_session_manager
    payload = base64.b64encode(b"this is bigger than 8 bytes").decode()

    upload = mgr.upload(None, "big.txt", payload)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    resp = httpx.get(f"http://127.0.0.1:{port}/files/{sid}/big.txt")
    assert resp.status_code == 413
