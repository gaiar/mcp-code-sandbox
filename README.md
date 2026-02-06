# mcp-code-sandbox

Self-hosted MCP server that lets LLMs execute Python in isolated Docker containers, iterate on errors, and retrieve generated artifacts (charts, PDFs, data files).

Built for use with Claude Code, n8n, and any MCP-compatible client.

## How it works

```
MCP Client (Claude Code, n8n, ...)
    │  stdio / streamable HTTP
    ▼
FastMCP Server (5 tools)
    │
    ▼
SessionManager (docker-py)
    │
    ▼
Sandbox Container (per session)
    --network none
    --cap-drop ALL
    --read-only rootfs
    /mnt/data/ (writable volume)
```

Each session gets a dedicated Docker container with pandas, numpy, matplotlib, seaborn, scipy, openpyxl, reportlab, and pyarrow pre-installed. Containers are fully isolated — no network, no capabilities, read-only root filesystem. Files persist in `/mnt/data/` across calls within the same session.

## MCP Tools

| Tool | Description |
|------|-------------|
| `sandbox_run_python` | Execute Python code and return stdout, stderr, exit code, and new artifacts |
| `sandbox_upload_file` | Upload a data file (CSV, Excel, JSON, etc.) into the session |
| `sandbox_read_artifact` | Read a generated file back as base64 |
| `sandbox_list_artifacts` | List all files in the session's `/mnt/data/` directory |
| `sandbox_close_session` | Destroy the session container and release resources |

All tools return structured responses — never exceptions. Errors include machine-readable codes (`file_exists`, `session_busy`, `code_too_large`, etc.) so the LLM can act on them programmatically.

## Quick Start

### Prerequisites

- Python 3.12+
- Docker daemon running
- conda (Miniforge recommended)

### Setup

```bash
# Clone
git clone https://github.com/gaiar/mcp-code-sandbox.git
cd mcp-code-sandbox

# Create conda environment
conda create -n mcp-code-sandbox python=3.12 -y
conda activate mcp-code-sandbox
pip install -e ".[dev]"

# Build the sandbox Docker image
docker build -t llm-sandbox:latest docker/
```

### Run

```bash
# Start the MCP server (stdio transport)
mcp-code-sandbox

# Or run as a module
python -m mcp_code_sandbox
```

### Claude Code Integration

Add to your Claude Code MCP config (`~/.claude/claude_code_config.json`):

```json
{
  "mcpServers": {
    "code-sandbox": {
      "command": "mcp-code-sandbox"
    }
  }
}
```

## Example Workflow

Upload a CSV, run analysis, generate a chart, and retrieve it — all in one session:

```
User: "Analyze sales.csv and create a revenue chart"

LLM calls: sandbox_upload_file(filename="sales.csv", content_base64="...")
  → {"session_id": "sess_a1b2c3d4e5f6", "path": "/mnt/data/sales.csv"}

LLM calls: sandbox_run_python(session_id="sess_a1b2c3d4e5f6", code="
    import pandas as pd
    import matplotlib.pyplot as plt
    df = pd.read_csv('/mnt/data/sales.csv')
    print(df.describe())
    df.groupby('month')['revenue'].sum().plot(kind='bar')
    plt.savefig('/mnt/data/chart.png')
")
  → {"exit_code": 0, "stdout": "...", "artifacts": [{"filename": "chart.png", ...}]}

LLM calls: sandbox_read_artifact(session_id="sess_a1b2c3d4e5f6", path="/mnt/data/chart.png")
  → {"content_base64": "iVBORw0KGgo...", "mime_type": "image/png"}

LLM calls: sandbox_close_session(session_id="sess_a1b2c3d4e5f6")
  → {"status": "closed"}
```

If code fails, the LLM reads the error, fixes the code, and retries — all within the same session. Files persist across calls.

## Configuration

All settings via environment variables with `SANDBOX_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_IMAGE` | `llm-sandbox:latest` | Docker image for sandbox containers |
| `SANDBOX_MEMORY_LIMIT` | `512m` | Container memory limit |
| `SANDBOX_CPU_LIMIT` | `1.0` | Container CPU cores |
| `SANDBOX_EXEC_TIMEOUT_S` | `60` | Code execution timeout (seconds) |
| `SANDBOX_SESSION_TTL_M` | `30` | Session idle timeout (minutes) |
| `SANDBOX_MAX_SESSIONS` | `10` | Max concurrent sessions |
| `SANDBOX_MAX_UPLOAD_BYTES` | `52428800` | Max file upload size (50 MB) |
| `SANDBOX_MAX_OUTPUT_BYTES` | `102400` | Max stdout/stderr per execution (100 KB) |
| `SANDBOX_MAX_CODE_BYTES` | `102400` | Max code length (100 KB) |
| `SANDBOX_HTTP_HOST` | `127.0.0.1` | HTTP artifact server bind address |
| `SANDBOX_HTTP_PORT` | `8080` | HTTP artifact server port |
| `SANDBOX_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `SANDBOX_LOG_FILE` | `logs/sandbox.log` | Log file path |
| `SANDBOX_LOG_FORMAT` | `console` | Log format (`console` or `json`) |

## Container Security

Every sandbox container runs with:

- **No network** — `--network none` prevents all outbound connections
- **No capabilities** — `--cap-drop ALL` removes all Linux capabilities
- **No privilege escalation** — `--security-opt no-new-privileges`
- **Read-only root** — `--read-only` with tmpfs `/tmp` (64 MB) and writable `/mnt/data/` volume
- **Non-root user** — runs as `sandbox` (uid 1000)
- **Resource limits** — configurable memory (512 MB) and CPU (1.0 core)
- **Execution timeout** — killed after 60s (configurable)
- **Automatic cleanup** — idle sessions expire after 30 min; orphan containers removed on startup

## Sandbox Packages

The Docker image includes:

| Package | Use |
|---------|-----|
| pandas | Data manipulation and analysis |
| numpy | Numerical computing |
| matplotlib | Charts and plots |
| seaborn | Statistical visualization |
| scipy | Statistical tests and scientific computing |
| openpyxl | Excel file reading/writing |
| reportlab | PDF generation |
| pyarrow | Parquet and Arrow format support |

## HTTP Artifact Server

An optional HTTP server runs alongside the MCP server for direct artifact downloads:

```
GET http://localhost:8080/files/{session_id}/{filename}
```

Artifacts in `RunResult` include a `download_url` field when the HTTP server is active.

## Development

```bash
# Activate environment
conda activate mcp-code-sandbox

# Run all tests (88 total)
pytest tests/ -v

# Unit tests only (no Docker needed)
pytest tests/unit/ -v

# Integration tests (requires Docker)
pytest tests/integration/ -m integration -v

# Code quality
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

# Run smoke test
python test_real_life.py

# Run large-scale EDA test (50K rows)
python test_eda_large.py
```

## Architecture

```
src/mcp_code_sandbox/
├── server.py          # FastMCP server + 5 tool definitions
├── session.py         # SessionManager: container lifecycle, exec, artifacts
├── models.py          # Pydantic response models (RunResult, ErrorResponse, etc.)
├── config.py          # SandboxConfig with env var parsing
├── validation.py      # Input validation (session IDs, filenames, sizes)
├── logging.py         # structlog file-only setup with contextvars
├── cleanup.py         # TTL cleanup thread + orphan removal
├── http_server.py     # Starlette/uvicorn artifact download server
└── __main__.py        # python -m entry point

tests/
├── unit/              # 55 tests (no Docker required)
└── integration/       # 33 tests (requires Docker daemon)

docker/
└── Dockerfile         # Sandbox image with scientific Python packages
```

## License

MIT
