# PRD v2: Self-Hosted LLM Python Sandbox (MCP)

## 1. Problem & Goals

LLMs lack the ability to execute code, inspect results, and deliver generated artifacts (charts, PDFs, reports). Commercial solutions (OpenAI Code Interpreter) exist but are not self-hosted. This project builds a **self-hosted MCP server** that lets an LLM run Python in isolated Docker containers, iterate on errors, and retrieve generated files.

**Target consumers:**
- **Claude Code** via MCP stdio transport (primary)
- **n8n** via streamable HTTP transport (post-MVP)

**Primary use case:** Marketing data analysis — upload CSV, run pandas/seaborn analysis, generate charts, produce PDF report, download artifacts.

**Success metrics:**
| Metric | Target |
|--------|--------|
| P50 execution latency (warm session) | < 2s for small scripts |
| Error iteration overhead | < 1s between attempts |
| Artifact retrieval | 100% of generated files accessible |
| Network egress from sandbox | Denied (verified by test) |

---

## 2. Tool Contracts

Five MCP tools, all session-scoped. `session_id` is **optional** on every tool — if omitted, the server auto-generates one (format: `sess_<uuid4_hex[:12]>`). The `session_id` is always included in the response so the client can reuse it.

### 2.1 `upload_file`

Upload a data file into the session container.

**Input:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | no | Server generates if omitted. Client can provide to reuse session. |
| `filename` | string | yes | Sanitized server-side; path traversal blocked |
| `content_base64` | string | yes | Base64-encoded file bytes |
| `overwrite` | bool | no | Default `false`; error if file exists |

**Success response:**
```json
{ "session_id": "sess_a1b2c3d4e5f6", "path": "/mnt/data/sales.csv" }
```

**Error response:**
```json
{ "error": "file_exists", "message": "sales.csv already exists. Set overwrite=true to replace." }
```

### 2.2 `run_python`

Execute Python code in the session container. Returns stdout, stderr, and artifact metadata.

**Input:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | no | Server generates if omitted |
| `code` | string | yes | Python source (max 100KB) |

**Success response (exit_code 0):**
```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "run_id": "run_20260206T123456Z_a1b2",
  "exit_code": 0,
  "stdout": "Processed 1500 rows\n",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "artifacts": [
    {
      "path": "/mnt/data/report.pdf",
      "filename": "report.pdf",
      "size_bytes": 120000,
      "mime_type": "application/pdf",
      "download_url": "http://<host>:8080/files/sess_123/report.pdf"
    }
  ],
  "duration_ms": 1340
}
```

**Error response (exit_code != 0):**
```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "run_id": "run_20260206T123500Z_c3d4",
  "exit_code": 1,
  "stdout": "",
  "stderr": "Traceback (most recent call last):\n  File \"<string>\", line 3\nKeyError: 'sales_amount'",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "artifacts": [],
  "duration_ms": 210
}
```

**Timeout response:**
```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "run_id": "run_20260206T123600Z_e5f6",
  "exit_code": -1,
  "stdout": "",
  "stderr": "Execution timed out after 60 seconds",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "artifacts": [],
  "duration_ms": 60000
}
```

**Design notes:**
- Artifact scan runs only on `exit_code == 0` (fail-fast)
- Artifact scan uses before/after diff of `/mnt/data` file listing
- `download_url` included only when HTTP artifact server is running (Stage 4+)
- `stdout`/`stderr` truncated at 100KB with `*_truncated: true` flag

### 2.3 `read_artifact`

Read artifact content from the session container as base64. For LLM inspection (e.g., Claude viewing a chart image).

**Input:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | yes | Required — must reference an existing session |
| `path` | string | yes | Absolute path within `/mnt/data/` |

**Success response:**
```json
{
  "path": "/mnt/data/chart.png",
  "filename": "chart.png",
  "mime_type": "image/png",
  "size_bytes": 45000,
  "content_base64": "<base64-encoded bytes>"
}
```

**Error response (too large):**
```json
{
  "error": "artifact_too_large",
  "message": "chart.png is 15MB, exceeds 10MB limit. Use download_url instead.",
  "size_bytes": 15000000,
  "download_url": "http://<host>:8080/files/sess_123/chart.png"
}
```

**Error response (not found):**
```json
{ "error": "not_found", "message": "No artifact at /mnt/data/chart.png" }
```

### 2.4 `list_artifacts`

List all files currently in the session's `/mnt/data/` directory.

**Input:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | yes | Required — must reference an existing session |

**Success response:**
```json
{
  "artifacts": [
    {
      "path": "/mnt/data/sales.csv",
      "filename": "sales.csv",
      "size_bytes": 24000,
      "mime_type": "text/csv"
    },
    {
      "path": "/mnt/data/chart.png",
      "filename": "chart.png",
      "size_bytes": 45000,
      "mime_type": "image/png"
    }
  ]
}
```

### 2.5 `close_session`

Destroy the session container and release all resources.

**Input:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | yes | Required — must reference an existing session |

**Success response:**
```json
{ "status": "closed" }
```

**Error response (already closed / not found):**
```json
{ "error": "session_not_found", "message": "No active session with id sess_123" }
```

---

## 3. Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        HOST MACHINE                           │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                     MCP Server (FastMCP)                │  │
│  │                                                         │  │
│  │  MCP Tools (stdio)        HTTP Artifact Server (:8080)  │  │
│  │  ─────────────────        ────────────────────────────  │  │
│  │  upload_file              GET /files/{session}/{file}   │  │
│  │  run_python               → serves artifact bytes       │  │
│  │  read_artifact            → correct Content-Type        │  │
│  │  list_artifacts           → 404 for missing files       │  │
│  │  close_session                                          │  │
│  │           │                          │                  │  │
│  │           └──────────┬───────────────┘                  │  │
│  │                      ▼                                  │  │
│  │              Session Manager (docker-py)                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                         │                                     │
│          ┌──────────────┴──────────────┐                      │
│          ▼                             ▼                      │
│  ┌──────────────┐              ┌──────────────┐               │
│  │ sandbox_abc  │              │ sandbox_xyz  │               │
│  │ --net none   │              │ --net none   │               │
│  │ /mnt/data/   │              │ /mnt/data/   │               │
│  │  sales.csv   │              │  report.xlsx │               │
│  │  chart.png   │              │  analysis.pdf│               │
│  └──────────────┘              └──────────────┘               │
└───────────────────────────────────────────────────────────────┘
```

**Components:**
| Component | Technology | Responsibility |
|-----------|------------|----------------|
| MCP Server | FastMCP (Python) | Expose tools via stdio, manage sessions |
| Session Manager | docker-py | Map `session_id` → container, lifecycle management |
| Sandbox Containers | Pre-built Docker image | Isolated Python execution with `/mnt/data/` |
| HTTP Artifact Server | Built-in (Starlette/uvicorn) | Serve artifact downloads for n8n/external |

**Container lifecycle:**
| Event | Action |
|-------|--------|
| First tool call with new `session_id` | Create container (on-demand) |
| Subsequent calls with same `session_id` | Reuse existing container |
| Idle timeout (30 min default) | Auto-destroy container |
| `close_session()` call | Explicit destroy |
| MCP server startup | Cleanup orphaned containers (by label `app=llm-sandbox`) |

**Concurrency model:**
- **Max concurrent sessions:** 10 containers (configurable). When exceeded, tools return `{"error": "max_sessions", "message": "Maximum 10 concurrent sessions reached. Close an existing session first."}`.
- **Concurrent exec per session:** Serialized. Only one `run_python` call executes at a time per session. If a second call arrives while one is in-flight, it returns `{"error": "session_busy", "message": "A run is already in progress for this session. Wait for it to complete."}`. This prevents interleaved artifact scans and ambiguous `/mnt/data/` state.

**Artifact scanning algorithm:**
1. Before `run_python` execution: snapshot file listing of `/mnt/data/` (names + mtimes + sizes)
2. After successful execution: snapshot again
3. Diff: new files and files with changed mtime/size are reported as artifacts
4. On failure (`exit_code != 0`): skip scan entirely

---

## 4. Security Model

| Control | Implementation |
|---------|----------------|
| Network isolation | `--network none` on every sandbox container |
| Path traversal | Reject any `filename` or `path` containing `..` or absolute paths outside `/mnt/data/` |
| Fixed image | No `pip install` in sandbox; all packages baked into image |
| Capabilities | Drop all Linux capabilities (`--cap-drop ALL`) |
| Privilege escalation | `--security-opt no-new-privileges` |
| Read-only root | `--read-only` with tmpfs for `/tmp` and writable `/mnt/data/` |
| Resource limits | CPU, memory, and execution timeout enforced (see Section 5) |
| Session isolation | Each `session_id` maps to exactly one container; no cross-session access |
| Container labels | `app=llm-sandbox`, `session_id=<id>` for discovery and orphan cleanup |

---

## 5. Configuration Defaults

All values configurable via environment variables.

| Setting | Default | Env Variable |
|---------|---------|-------------|
| Container memory limit | 512MB | `SANDBOX_MEMORY_LIMIT` |
| Container CPU limit | 1.0 core | `SANDBOX_CPU_LIMIT` |
| Execution timeout | 60s | `SANDBOX_EXEC_TIMEOUT_S` |
| Session idle TTL | 30 min | `SANDBOX_SESSION_TTL_M` |
| Max upload file size | 50MB | `SANDBOX_MAX_UPLOAD_BYTES` |
| Max artifact read size | 10MB | `SANDBOX_MAX_ARTIFACT_READ_BYTES` |
| Max stdout/stderr size | 100KB | `SANDBOX_MAX_OUTPUT_BYTES` |
| Max code length | 100KB | `SANDBOX_MAX_CODE_BYTES` |
| HTTP artifact server port | 8080 | `SANDBOX_HTTP_PORT` |
| Sandbox Docker image | `llm-sandbox:latest` | `SANDBOX_IMAGE` |
| Max concurrent sessions | 10 | `SANDBOX_MAX_SESSIONS` |
| Orphan cleanup interval | 5 min | `SANDBOX_CLEANUP_INTERVAL_M` |
| Log level | `INFO` | `SANDBOX_LOG_LEVEL` |
| Log file | `logs/sandbox.log` | `SANDBOX_LOG_FILE` |
| Log format | `console` | `SANDBOX_LOG_FORMAT` (`console` or `json`) |

---

## 6. Implementation Stages

Each stage produces a testable increment. Complete one stage before starting the next.

### Stage 0: MCP Server Skeleton

**Goal:** FastMCP server with stub tools, no Docker dependency.

**Deliverables:**
- Project scaffolding (conda env, pyproject.toml, src/ layout)
- FastMCP server with all 5 tools returning hardcoded stub responses
- stdio transport working

**Test criterion:** Claude Code connects to server, discovers all 5 tools, calls each tool, receives stub JSON responses.

### Stage 1: Container Execution

**Goal:** `run_python` and `close_session` work against real Docker containers.

**Deliverables:**
- Sandbox Docker image (Python 3.12 + pandas, numpy, matplotlib, seaborn, openpyxl, reportlab, pyarrow, scipy)
- Session Manager: create container on first call, reuse on subsequent calls
- `run_python`: execute code via `container.exec_run`, capture stdout/stderr/exit_code
- `close_session`: remove container
- Container security: `--network none`, `--cap-drop ALL`, resource limits

**Test criterion:** `run_python(session_id, "print(2+2)")` returns `{"exit_code": 0, "stdout": "4\n"}` from a real Docker container.

### Stage 2: File Upload & Artifacts

**Goal:** Full file lifecycle — upload, process, discover, read.

**Deliverables:**
- `upload_file`: write base64-decoded file into container via `put_archive`
- Artifact scanning: before/after diff of `/mnt/data/`
- `read_artifact`: read file from container, return base64 (with size limit)
- `list_artifacts`: list all files in `/mnt/data/`

**Test criterion:** Upload CSV → `run_python` with pandas analysis that saves PNG → `list_artifacts` shows both CSV and PNG → `read_artifact` returns base64-encoded PNG.

### Stage 3: End-to-End Demo

**Goal:** Complete marketing analysis workflow.

**Deliverables:**
- Demo script exercising full workflow
- Error iteration verified (intentional bug → fix → re-run)

**Test criterion:** Upload marketing CSV → seaborn charts → PDF report via reportlab → `read_artifact` returns PDF. At least one error-fix-retry cycle demonstrated.

### Stage 4: HTTP Artifact Server

**Goal:** Artifacts downloadable via HTTP URL for n8n integration.

**Deliverables:**
- HTTP server (`GET /files/{session_id}/{filename}`)
- `download_url` field populated in `run_python` artifact responses
- Correct `Content-Type` headers

**Test criterion:** `download_url` from `run_python` response opens in browser and downloads the correct file.

### Stage 5: Hardening

**Goal:** Production-ready validation, limits, cleanup, and logging.

**Deliverables:**
- Input validation: `session_id` format, filename sanitization, path traversal rejection
- Execution limits enforced: timeout, max output, max code size, max upload size
- Session TTL: background cleanup of idle containers
- Orphan cleanup on server startup
- Structured JSON logging (session_id, run_id, duration_ms, exit_code per call)
- Read-only root filesystem with tmpfs for `/tmp`

**Test criterion:** Path traversal attempt blocked with clear error. Execution exceeding 60s timeout returns timeout response. Idle container cleaned up after TTL. Orphaned containers cleaned on restart.

---

## 7. Known Limitations & Future Work

**Limitations (by design):**
- No in-memory Python state persistence — each `run_python` call starts a fresh `python -c` process. Variables do not carry over between calls. Filesystem state in `/mnt/data/` persists.
- No `pip install` in sandbox — all packages must be baked into the Docker image.
- No outbound network from sandbox — code cannot fetch URLs or call APIs.
- Artifact download URLs are internal-only (same-machine access, no auth).

**Future work (separate projects):**
- **Kernel mode**: Long-running ipykernel process per session for in-memory state persistence across calls.
- **Kubernetes backend**: `ExecutionBackend` abstraction with `K8sBackend` using gVisor/Kata, NetworkPolicy, and S3 artifact store.
- **Package proxy**: Allow controlled `pip install` via allowlisted internal PyPI mirror.
- **Streamable HTTP transport**: Enable n8n to call MCP tools directly over HTTP.
