"""Integration tests for upload_file, artifact scanning, list_artifacts, read_artifact."""

import base64

import pytest

from mcp_code_sandbox.models import (
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)
from mcp_code_sandbox.session import SessionManager

pytestmark = pytest.mark.integration


def test_upload_file(session_manager: SessionManager) -> None:
    """Upload a file and verify it exists in the container."""
    csv_data = b"name,value\nalice,100\nbob,200\n"
    b64 = base64.b64encode(csv_data).decode()

    result = session_manager.upload(None, "sales.csv", b64)
    assert isinstance(result, UploadResult)
    assert result.path == "/mnt/data/sales.csv"
    sid = result.session_id

    # Verify file is readable in the container
    run = session_manager.execute(sid, "print(open('/mnt/data/sales.csv').read())")
    assert isinstance(run, RunResult)
    assert "alice" in run.stdout
    assert "bob" in run.stdout


def test_upload_file_exists_error(session_manager: SessionManager) -> None:
    """Uploading same filename twice without overwrite returns file_exists error."""
    b64 = base64.b64encode(b"data").decode()
    result = session_manager.upload(None, "test.txt", b64)
    assert isinstance(result, UploadResult)
    sid = result.session_id

    result2 = session_manager.upload(sid, "test.txt", b64, overwrite=False)
    assert isinstance(result2, ErrorResponse)
    assert result2.error == "file_exists"


def test_upload_file_overwrite(session_manager: SessionManager) -> None:
    """Uploading same filename with overwrite=True succeeds."""
    b64_v1 = base64.b64encode(b"version1").decode()
    b64_v2 = base64.b64encode(b"version2").decode()

    result = session_manager.upload(None, "data.txt", b64_v1)
    assert isinstance(result, UploadResult)
    sid = result.session_id

    result2 = session_manager.upload(sid, "data.txt", b64_v2, overwrite=True)
    assert isinstance(result2, UploadResult)

    # Verify content was replaced
    run = session_manager.execute(sid, "print(open('/mnt/data/data.txt').read())")
    assert isinstance(run, RunResult)
    assert "version2" in run.stdout


def test_upload_invalid_filename(session_manager: SessionManager) -> None:
    """Invalid filenames are rejected."""
    b64 = base64.b64encode(b"data").decode()
    result = session_manager.upload(None, "../etc/passwd", b64)
    assert isinstance(result, ErrorResponse)
    assert result.error == "invalid_filename"


def test_artifact_scanning(session_manager: SessionManager) -> None:
    """Upload CSV, run code that creates PNG, verify artifacts list."""
    csv_data = b"x,y\n1,2\n3,4\n5,6\n"
    b64 = base64.b64encode(csv_data).decode()

    upload = session_manager.upload(None, "data.csv", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    code = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv

with open('/mnt/data/data.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

x = [int(r['x']) for r in rows]
y = [int(r['y']) for r in rows]
plt.plot(x, y)
plt.savefig('/mnt/data/chart.png')
print('done')
"""
    run = session_manager.execute(sid, code)
    assert isinstance(run, RunResult)
    assert run.exit_code == 0
    assert run.stdout.strip() == "done"

    # Artifacts should contain chart.png (new file)
    artifact_names = [a.filename for a in run.artifacts]
    assert "chart.png" in artifact_names

    # The original CSV should NOT appear (it was pre-existing, unchanged)
    assert "data.csv" not in artifact_names


def test_list_artifacts(session_manager: SessionManager) -> None:
    """list_files returns all files in /mnt/data/."""
    b64 = base64.b64encode(b"hello").decode()
    upload = session_manager.upload(None, "hello.txt", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    result = session_manager.list_files(sid)
    assert isinstance(result, ListArtifactsResult)
    filenames = [a.filename for a in result.artifacts]
    assert "hello.txt" in filenames


def test_list_artifacts_nonexistent_session(session_manager: SessionManager) -> None:
    """list_files on nonexistent session returns error."""
    result = session_manager.list_files("sess_nonexistent")
    assert isinstance(result, ErrorResponse)
    assert result.error == "session_not_found"


def test_read_artifact(session_manager: SessionManager) -> None:
    """Read an uploaded file back as base64."""
    original = b"test content for reading"
    b64 = base64.b64encode(original).decode()

    upload = session_manager.upload(None, "readme.txt", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    read = session_manager.read_file(sid, "/mnt/data/readme.txt")
    assert isinstance(read, ReadArtifactResult)
    assert read.filename == "readme.txt"
    assert read.size_bytes == len(original)

    decoded = base64.b64decode(read.content_base64)
    assert decoded == original


def test_read_artifact_not_found(session_manager: SessionManager) -> None:
    """Reading nonexistent file returns not_found error."""
    # Create a session first
    run = session_manager.execute(None, "print('hi')")
    assert isinstance(run, RunResult)
    sid = run.session_id

    read = session_manager.read_file(sid, "/mnt/data/nonexistent.txt")
    assert isinstance(read, ErrorResponse)
    assert read.error == "not_found"


def test_full_pipeline(session_manager: SessionManager) -> None:
    """Full pipeline: upload CSV -> run analysis -> list artifacts -> read artifact."""
    csv_data = b"name,sales\nalice,100\nbob,200\ncharlie,300\n"
    b64 = base64.b64encode(csv_data).decode()

    # 1. Upload CSV
    upload = session_manager.upload(None, "sales.csv", b64)
    assert isinstance(upload, UploadResult)
    sid = upload.session_id

    # 2. Run analysis that creates a summary file
    code = """\
import csv
with open('/mnt/data/sales.csv') as f:
    reader = csv.DictReader(f)
    total = sum(int(r['sales']) for r in reader)
with open('/mnt/data/summary.txt', 'w') as f:
    f.write(f'Total sales: {total}')
print(f'Total: {total}')
"""
    run = session_manager.execute(sid, code)
    assert isinstance(run, RunResult)
    assert run.exit_code == 0
    assert "600" in run.stdout

    # 3. List artifacts
    listing = session_manager.list_files(sid)
    assert isinstance(listing, ListArtifactsResult)
    filenames = [a.filename for a in listing.artifacts]
    assert "sales.csv" in filenames
    assert "summary.txt" in filenames

    # 4. Read the summary
    read = session_manager.read_file(sid, "/mnt/data/summary.txt")
    assert isinstance(read, ReadArtifactResult)
    content = base64.b64decode(read.content_base64).decode()
    assert "Total sales: 600" in content
