# Implementation Progress

Tracks completion of the implementation plan (PRD v2, Stages 0-5).

## Pre-Stage: Project Bootstrap

- [x] P.1 — Initialize git repository
- [x] P.2 — Create conda environment (`mcp-code-sandbox`, Python 3.12)
- [x] P.3 — Project scaffolding (src/, tests/, docker/, pyproject.toml)
- [x] P.4 — Initial commit

## Stage 0: MCP Server Skeleton (stubs, no Docker)

- [x] 0.1 — Configuration module (`config.py`) — `SandboxConfig(BaseSettings)` with all env vars
- [x] 0.2 — Response models (`models.py`) — all Pydantic models matching PRD schemas
- [x] 0.3 — Logging setup (`logging.py`) — structlog file-only, contextvars correlation
- [x] 0.4 — FastMCP server with stub tools (`server.py`) — 5 tools, stdio transport
- [x] 0.5 — Unit tests for Stage 0 — 17 tests pass, ruff/mypy clean
- [x] 0.6 — Commit Stage 0

## Stage 1: Container Execution

- [x] 1.1 — Sandbox Docker image (`docker/Dockerfile`) — python:3.12-slim + scientific packages
- [x] 1.2 — SessionManager class (`session.py`) — get_or_create, execute, close
- [x] 1.3 — Wire `run_python` tool to SessionManager
- [x] 1.4 — Wire `close_session` tool to SessionManager
- [x] 1.5 — Integration tests for Stage 1 — 6 tests pass (incl. network isolation)
- [x] 1.6 — Commit Stage 1

## Stage 2: File Upload & Artifacts

- [x] 2.1 — Implement `upload_file` in SessionManager (validate, base64 decode, put_archive)
- [x] 2.2 — Implement artifact scanning (before/after snapshot diff)
- [x] 2.3 — Implement `list_artifacts` in SessionManager
- [x] 2.4 — Implement `read_artifact` in SessionManager (get_archive, extract tar, base64)
- [ ] 2.5 — Stage 2 integration tests **<-- CURRENT**
- [ ] 2.6 — Commit Stage 2

## Stage 3: End-to-End Demo

- [ ] 3.1 — Create demo script (`examples/marketing_demo.py`)
- [ ] 3.2 — Error iteration in demo
- [ ] 3.3 — Commit Stage 3

## Stage 4: HTTP Artifact Server

- [ ] 4.1 — HTTP artifact download endpoint
- [ ] 4.2 — Wire `download_url` into artifact responses
- [ ] 4.3 — Stage 4 integration tests
- [ ] 4.4 — Commit Stage 4

## Stage 5: Hardening

- [ ] 5.1 — Input validation (session_id format, filename, path, code/upload size)
- [ ] 5.2 — Execution limits (timeout, output truncation)
- [ ] 5.3 — Concurrency guards (max sessions, per-session lock)
- [ ] 5.4 — Session TTL and orphan cleanup
- [ ] 5.5 — Structured logging integration
- [ ] 5.6 — Read-only root filesystem
- [ ] 5.7 — Full hardening test suite
- [ ] 5.8 — Commit Stage 5

## Notes

- Conda env: `mcp-code-sandbox` (activate with `source ~/miniforge3/etc/profile.d/conda.sh && conda activate mcp-code-sandbox`)
- Run unit tests: `pytest tests/unit/ -v`
- Run integration tests: `pytest tests/integration/ -m integration -v`
- Quality checks: `ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/`
- Docker image: `llm-sandbox:latest` (build from `docker/Dockerfile`)
