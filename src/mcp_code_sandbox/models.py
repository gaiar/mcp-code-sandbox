"""Pydantic response models matching PRD tool contracts."""

from pydantic import BaseModel


class ArtifactInfo(BaseModel):
    """Metadata for a file in /mnt/data/."""

    path: str
    filename: str
    size_bytes: int
    mime_type: str
    download_url: str | None = None


class UploadResult(BaseModel):
    """Response from upload_file tool."""

    session_id: str
    path: str


class RunResult(BaseModel):
    """Response from run_python tool."""

    session_id: str
    run_id: str
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    artifacts: list[ArtifactInfo] = []
    duration_ms: int


class ReadArtifactResult(BaseModel):
    """Response from read_artifact tool."""

    path: str
    filename: str
    mime_type: str
    size_bytes: int
    content_base64: str


class ListArtifactsResult(BaseModel):
    """Response from list_artifacts tool."""

    artifacts: list[ArtifactInfo] = []


class CloseSessionResult(BaseModel):
    """Response from close_session tool."""

    status: str


class ErrorResponse(BaseModel):
    """Structured error returned to the LLM."""

    error: str
    message: str
    size_bytes: int | None = None
    download_url: str | None = None
