"""Test Pydantic response models construction and serialization."""

from mcp_code_sandbox.models import (
    ArtifactInfo,
    CloseSessionResult,
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)


def test_artifact_info() -> None:
    info = ArtifactInfo(
        path="/mnt/data/chart.png",
        filename="chart.png",
        size_bytes=45000,
        mime_type="image/png",
    )
    d = info.model_dump()
    assert d["path"] == "/mnt/data/chart.png"
    assert d["filename"] == "chart.png"
    assert d["size_bytes"] == 45000
    assert d["mime_type"] == "image/png"
    assert d["download_url"] is None


def test_artifact_info_with_download_url() -> None:
    info = ArtifactInfo(
        path="/mnt/data/chart.png",
        filename="chart.png",
        size_bytes=45000,
        mime_type="image/png",
        download_url="http://localhost:8080/files/sess_123/chart.png",
    )
    assert info.download_url == "http://localhost:8080/files/sess_123/chart.png"


def test_upload_result() -> None:
    result = UploadResult(session_id="sess_a1b2c3d4e5f6", path="/mnt/data/sales.csv")
    d = result.model_dump()
    assert d["session_id"] == "sess_a1b2c3d4e5f6"
    assert d["path"] == "/mnt/data/sales.csv"


def test_run_result_success() -> None:
    result = RunResult(
        session_id="sess_a1b2c3d4e5f6",
        run_id="run_20260206T123456Z_a1b2",
        exit_code=0,
        stdout="4\n",
        stderr="",
        artifacts=[],
        duration_ms=100,
    )
    d = result.model_dump()
    assert d["exit_code"] == 0
    assert d["stdout"] == "4\n"
    assert d["stdout_truncated"] is False
    assert d["stderr_truncated"] is False
    assert d["artifacts"] == []


def test_run_result_with_artifacts() -> None:
    artifact = ArtifactInfo(
        path="/mnt/data/report.pdf",
        filename="report.pdf",
        size_bytes=120000,
        mime_type="application/pdf",
    )
    result = RunResult(
        session_id="sess_abc",
        run_id="run_abc",
        exit_code=0,
        stdout="",
        stderr="",
        artifacts=[artifact],
        duration_ms=1340,
    )
    d = result.model_dump()
    assert len(d["artifacts"]) == 1
    assert d["artifacts"][0]["filename"] == "report.pdf"


def test_run_result_truncated() -> None:
    result = RunResult(
        session_id="sess_abc",
        run_id="run_abc",
        exit_code=0,
        stdout="truncated...",
        stderr="",
        stdout_truncated=True,
        artifacts=[],
        duration_ms=50,
    )
    assert result.stdout_truncated is True


def test_read_artifact_result() -> None:
    result = ReadArtifactResult(
        path="/mnt/data/chart.png",
        filename="chart.png",
        mime_type="image/png",
        size_bytes=45000,
        content_base64="iVBORw0KGgo=",
    )
    d = result.model_dump()
    assert d["content_base64"] == "iVBORw0KGgo="
    assert d["size_bytes"] == 45000


def test_list_artifacts_result_empty() -> None:
    result = ListArtifactsResult()
    assert result.artifacts == []


def test_list_artifacts_result_with_items() -> None:
    result = ListArtifactsResult(
        artifacts=[
            ArtifactInfo(
                path="/mnt/data/sales.csv",
                filename="sales.csv",
                size_bytes=24000,
                mime_type="text/csv",
            ),
        ]
    )
    assert len(result.artifacts) == 1


def test_close_session_result() -> None:
    result = CloseSessionResult(status="closed")
    assert result.model_dump() == {"status": "closed"}


def test_error_response() -> None:
    err = ErrorResponse(
        error="file_exists",
        message="sales.csv already exists. Set overwrite=true to replace.",
    )
    d = err.model_dump()
    assert d["error"] == "file_exists"
    assert d["size_bytes"] is None
    assert d["download_url"] is None


def test_error_response_with_optional_fields() -> None:
    err = ErrorResponse(
        error="artifact_too_large",
        message="chart.png is 15MB, exceeds 10MB limit.",
        size_bytes=15000000,
        download_url="http://localhost:8080/files/sess_123/chart.png",
    )
    assert err.size_bytes == 15000000
    assert err.download_url is not None
