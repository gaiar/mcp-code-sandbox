# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Self-hosted MCP server that lets LLMs execute Python in isolated Docker containers, iterate on errors, and retrieve generated artifacts (charts, PDFs, reports). Exposes 5 MCP tools: `upload_file`, `run_python`, `read_artifact`, `list_artifacts`, `close_session`.

**Status:** Pre-implementation. Research and PRD complete, no code yet.

## Key Documents

- `prd-v2.md` — **Authoritative spec.** Tool contracts, architecture, security model, configuration defaults, implementation stages (0-5). Always consult this before implementing.
- `research.md` — Evaluated alternatives (code-sandbox-mcp, mcp-run-python, BeeAI, Jupyter MCP servers) and OpenAI Code Interpreter architecture analysis.
- `prd.md` — Original PRD (over-scoped with Kubernetes). Kept for reference only; `prd-v2.md` supersedes it.

## Resolved Decisions

- **Package name:** `mcp_code_sandbox` (import as `from mcp_code_sandbox import ...`)
- **Docker only** — no Kubernetes (separate future project)
- **Transport:** stdio for Claude Code (primary), streamable HTTP for n8n (post-MVP)
- **Framework:** FastMCP v2 (stable, 2.x) — already has streamable HTTP + bearer token auth + JWT verification for production HTTP exposure
- **State persistence:** Filesystem only via `/mnt/data/` (no kernel mode)
- **Packages:** Fixed Docker image, no pip install in sandbox
- **Artifact security:** Internal-only (same-machine, no auth) for MVP; bearer token auth via FastMCP for HTTP transport
- **Session ID:** Server auto-generates if omitted. Client can provide one to reuse a session. Format: `sess_<uuid4_hex[:12]>` (e.g., `sess_a1b2c3d4e5f6`)
- **Sandbox image packages:** pandas, numpy, matplotlib, seaborn, openpyxl, reportlab, pyarrow, scipy

## Architecture

MCP Server (FastMCP) → Session Manager (docker-py) → Sandbox Containers (one per session_id, `--network none`, `/mnt/data/` working dir). Optional HTTP artifact server on `:8080` for external download URLs.

## Implementation Stages

Follow `prd-v2.md` Section 6 strictly. Each stage must be testable before moving to the next:

0. **MCP Server Skeleton** — stub tools, no Docker
1. **Container Execution** — `run_python` + `close_session` against real containers
2. **File Upload & Artifacts** — `upload_file`, `read_artifact`, `list_artifacts`
3. **End-to-End Demo** — marketing CSV → charts → PDF workflow
4. **HTTP Artifact Server** — `download_url` support
5. **Hardening** — validation, limits, TTL cleanup, logging

## Tech Stack

- Python 3.12, FastMCP v2 (2.x stable), docker-py, structlog, pydantic-settings
- Sandbox image: pandas, numpy, matplotlib, seaborn, openpyxl, reportlab, pyarrow, scipy
- Dev tools: ruff, mypy, pytest, pytest-asyncio
- Config via environment variables (see `prd-v2.md` Section 5 for defaults)

## Container Security Defaults

All sandbox containers run with: `--network none`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--read-only` (with tmpfs `/tmp`, writable `/mnt/data/`), 512MB memory, 1.0 CPU, 60s timeout.

## Code Intelligence

When making code changes or searching the codebase, use Pyright diagnostics (if available in the environment) for type checking, import resolution, and catching errors early. Pay attention to Pyright diagnostic messages in tool results and fix reported issues promptly.

## Development Guidelines

### Tool Error Convention

Tools **never raise exceptions** to the LLM. Always return structured error dicts matching the PRD schemas:

```python
# Correct — LLM can parse error code and act on it
return {"error": "file_exists", "message": "sales.csv already exists. Set overwrite=true to replace."}

# Wrong — ToolError gives unstructured text the LLM can't reliably branch on
raise ToolError("file already exists")
```

### Tool Docstrings Are LLM-Facing

FastMCP uses docstrings as the tool's `description` in the MCP schema. Write them for LLM consumption — precise, actionable, describing inputs, outputs, and when to use the tool. Not standard Python API docs.

### Async + docker-py Bridge

docker-py is **entirely synchronous**. FastMCP tools must be `async`. Wrap every docker-py call in `asyncio.to_thread()`:

```python
@mcp.tool
async def run_python(session_id: str, code: str, ctx: Context) -> RunResult:
    """Execute Python code in session container. Returns stdout, stderr, exit_code, and artifacts."""
    result = await asyncio.to_thread(session_manager.execute, session_id, code)
    return result
```

### Container File Transfer

docker-py uses `put_archive()` / `get_archive()` which expect/return **tar streams**, not raw bytes. Never use `exec_run("cat ...")` for file I/O:

- `put_archive(path, tar_bytes)` — upload: build a tar-formatted `BytesIO`, then put
- `get_archive(path)` — download: returns `(tar_stream, stat)`, extract from tar

### exec_run with demux=True

Always use `container.exec_run(cmd, demux=True)` to get separate `(stdout_bytes, stderr_bytes)`. Without `demux=True`, stdout and stderr are interleaved and inseparable.

### Docker Error Mapping

Map docker-py exceptions to structured tool responses. Never expose raw Docker tracebacks to the LLM:

| docker-py Exception | Tool Response |
|---------------------|---------------|
| `NotFound` | `{"error": "session_not_found", ...}` |
| `APIError` | `{"error": "docker_error", ...}` |
| `DockerException` | `{"error": "docker_unavailable", ...}` |
| `ContainerError` | `{"error": "execution_failed", ...}` |

### Path Validation

Don't just reject `..` strings. **Resolve** the path and verify the prefix:

```python
from pathlib import PurePosixPath

resolved = PurePosixPath("/mnt/data").joinpath(PurePosixPath(filename).name)
if not str(resolved).startswith("/mnt/data/"):
    return {"error": "invalid_path", "message": "Path outside /mnt/data/"}
```

Filename allowlist: `[a-zA-Z0-9._-]` only. Check sizes **before** decoding (validate base64 length before `b64decode`).

### SessionManager Separation

Tools never call docker-py directly. All Docker operations go through a `SessionManager` class that owns the docker client and session dict. Tools receive `SessionManager` at module level or via FastMCP dependency injection. This enables unit testing by mocking `SessionManager` without a Docker daemon.

### Response Models (Pydantic)

Define Pydantic models for every response type matching the PRD schemas: `ArtifactInfo`, `RunResult`, `UploadResult`, `ListArtifactsResult`, `ErrorResponse`. Use as return type hints so FastMCP auto-generates output schemas. Reuse in tests for validation.

### Configuration

Use `pydantic-settings` `BaseSettings` for env var parsing with typed defaults (see `prd-v2.md` Section 5 for all settings). Validate at startup — fail fast if Docker daemon unreachable or sandbox image missing.

### Testing Strategy

- **Unit tests** (no Docker): validation, path safety, config parsing, response models. Run with `pytest tests/unit/`
- **Integration tests** (need Docker daemon): mark with `@pytest.mark.integration`. Run with `pytest tests/integration/ -m integration`
- Container lifecycle: fixtures with `force=True` removal in teardown to prevent leaks
- Test network isolation: actual outbound request attempt from sandbox must fail
- Test timeout: actual `time.sleep()` exceeding limit must return timeout response

### Sandbox Dockerfile

Located at `docker/Dockerfile`. Base: `python:3.12-slim`. Pre-install all scientific packages. Create `/mnt/data/` as working directory. Run as non-root user. No `CMD` — containers are created idle, code runs via `exec_run`.

### Logging

#### The stdio constraint

MCP stdio transport owns stdout — any stray `print()` or `StreamHandler(sys.stdout)` corrupts the protocol and silently kills the connection. Never write to stdout. All server logs go to file. Use `tail -f logs/sandbox.log` in a second terminal for live debugging.

#### Three channels, never mixed

| Channel | What it's for | Example |
|---------|---------------|---------|
| **Server log** (structlog → file) | Developer debugging the server | `container_created session_id=sess_123 image=llm-sandbox:latest duration_ms=820` |
| **MCP Context** (`ctx.info/warning`) | LLM-facing progress the model can act on | `"Executing 2.4KB of Python code"` |
| **Container stdout/stderr** (tool response) | The sandboxed code's own output | `"Processed 1500 rows\n"` |

Ask: "Who reads this?" — if the developer, use server log. If the LLM, use MCP Context. If it's the user's code output, it belongs in the tool response.

#### Logger names

One logger per component. Name matches the module path under `src/`:

```
llm_sandbox.server       → server startup, shutdown, config
llm_sandbox.tools        → tool call entry/exit
llm_sandbox.session      → session create, reuse, destroy, TTL expiry
llm_sandbox.docker       → docker-py operations
llm_sandbox.artifacts    → scan, read, size checks
llm_sandbox.validation   → input rejection reasons
llm_sandbox.cleanup      → background TTL sweep, orphan removal
```

Get the logger at module top: `log = structlog.get_logger("llm_sandbox.session")`. When debugging, filter by logger name to isolate a subsystem: `grep "llm_sandbox.docker" logs/sandbox.log`.

#### What goes at each level

| Level | Rule of thumb | Examples |
|-------|---------------|----------|
| `DEBUG` | Every operation you'd want to see when something is subtly wrong | `exec_run cmd=["python","-c",...] duration_ms=1340`, `artifact_scan before=3_files after=5_files new=["chart.png","report.pdf"]` |
| `INFO` | Events you'd want in a normal production log — one per tool call, one per lifecycle event | `tool_call tool=run_python session_id=sess_123 exit_code=0 duration_ms=1380`, `session_created session_id=sess_123` |
| `WARNING` | Something degraded but the request still succeeded | `stdout_truncated session_id=sess_123 original_bytes=204800 limit_bytes=102400`, `orphans_found count=2` |
| `ERROR` | Something failed and the tool returned an error response | `container_create_failed session_id=sess_123 error="image not found"`, `exec_timeout session_id=sess_123 timeout_s=60` |

Don't log at ERROR for expected user mistakes (bad filename, file not found). Those are INFO — the tool returned a structured error, everything worked correctly.

#### Log message format

Use **snake_case event names** as the first field, then key=value pairs. No sentences, no punctuation at the end:

```
# Good — scannable, greppable, consistent
tool_call tool=upload_file session_id=sess_123 filename=sales.csv size_bytes=24000 duration_ms=45
session_destroyed session_id=sess_123 reason=ttl_expired idle_minutes=31
container_exec session_id=sess_123 exit_code=1 duration_ms=210

# Bad — inconsistent, hard to parse, hard to grep
INFO: Uploading file sales.csv to session sess_123...
Session sess_123 was destroyed because it expired after 31 minutes.
Running code in container for session sess_123, exit code was 1
```

#### Correlation fields

Every log line automatically includes `session_id` and `run_id` (when applicable) via contextvars. Set them once at tool entry, structlog attaches them to every subsequent log line in that call stack — including across `asyncio.to_thread()` boundaries.

#### What never goes in logs

- Base64 content (file uploads, artifact reads) — log `filename` and `size_bytes` instead
- Full code strings — log `code_bytes=len(code)` instead
- Full stdout/stderr from containers — log `stdout_bytes`, `stderr_bytes`, `truncated=true/false`
- Docker socket paths or internal hostnames

#### MCP Context messages (LLM-facing)

Short, present tense, no internal details. The LLM reads these to understand progress, not to debug:

```python
await ctx.info(f"Executing {len(code)} bytes of Python code")
await ctx.info(f"Found {len(artifacts)} new artifacts")
await ctx.warning("stdout truncated at 100KB")
```

Never send DEBUG-level detail through Context. Never send container IDs, Docker errors, or timing info — those go to the server log.

#### Debugging workflow

```bash
# Terminal 1: Claude Code talks to MCP server via stdio
claude

# Terminal 2: live server logs
tail -f logs/sandbox.log

# Filter to one session
grep "sess_123" logs/sandbox.log

# Filter to one subsystem
grep "llm_sandbox.docker" logs/sandbox.log

# See only errors and warnings
grep -E "level=(error|warning)" logs/sandbox.log
```
