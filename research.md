# LLM Python Code Sandbox - Research Notes

## Goal

Build a self-hosted, Docker-based MCP server that provides a `run_python` tool for:
- **Input**: LLM sends Python code (as string)
- **Execution**: Code runs in sandboxed container with data science libraries
- **Output**: Returns stdout, stderr, exit_code, traceback, and artifact paths (charts, PDFs)
- **Iteration**: LLM inspects results, refines code, repeats until satisfied

**Use case**: Marketing data analysis (CSV/XLSX -> charts -> polished PDFs)
**Consumers**: Claude Code + n8n agents

---

## Existing Open Source Solutions

### 1. code-sandbox-mcp (Automata Labs)
- **URL**: https://github.com/Automata-Labs-team/code-sandbox-mcp
- **Language**: Go binary
- **Approach**: Docker containers with multi-step workflow
- **Transport**: stdio

**Tools provided**:
- `sandbox_initialize` - Create container (default: python:3.12-slim-bookworm)
- `write_file` - Write file to sandbox
- `copy_file` / `copy_project` - Copy files/directories
- `sandbox_exec` - Execute commands
- `sandbox_stop` - Stop and remove container

**Pros**:
- Mature, well-documented
- Multi-platform (Linux, macOS, Windows)
- Auto-updates

**Cons**:
- Written in Go (harder to customize)
- Multi-tool workflow (not single `run_python` call)
- No built-in artifact URL serving

---

### 2. mcp-run-python (Pydantic)
- **URL**: https://github.com/pydantic/mcp-run-python
- **Language**: Python + Deno
- **Approach**: Pyodide (WebAssembly) sandbox
- **Transport**: stdio, streamable-http

**Features**:
- Very secure (WASM isolation)
- Auto-detects and installs dependencies
- Captures stdout, stderr, return values
- Async support

**Pros**:
- Extremely secure (no Docker needed)
- Easy setup with uvx
- Pydantic AI integration

**Cons**:
- No persistent filesystem between calls
- Limited library support (no native C extensions)
- Some scientific libs may not work (e.g., certain PDF generators)

---

### 3. mcp-sandbox (JohanLi233)
- **URL**: https://github.com/JohanLi233/mcp-sandbox
- **Language**: Python
- **Approach**: Docker containers with SSE transport
- **Transport**: SSE (needs supergateway for stdio)

**Tools provided**:
- `create_sandbox` - Create new Docker sandbox
- `list_sandboxes` - List existing containers
- `execute_python_code` - Run Python code
- `install_package_in_sandbox` - Install packages
- `check_package_installation_status` - Check install status
- `execute_terminal_command` - Run shell commands
- `upload_file_to_sandbox` - Upload files

**Features**:
- File generation with HTTP links
- Web UI for management
- API key authentication
- Custom PyPI mirror support

**Pros**:
- Full-featured
- Returns file_links for artifacts
- Good for multi-user environments

**Cons**:
- SSE-only (needs adapter for Claude Code stdio)
- More complex architecture
- Multiple tools instead of single unified tool

---

### 4. BeeAI Code Interpreter (IBM)
- **URL**: https://github.com/i-am-bee/beeai-code-interpreter
- **Language**: Python
- **Approach**: HTTP API + Kubernetes
- **Transport**: HTTP REST API (not MCP native)

**API Endpoints**:
- `POST /v1/execute` - Execute Python code
- `POST /v1/parse-custom-tool` - Parse tool definition
- `POST /v1/execute-custom-tool` - Execute custom tool

**Features**:
- Auto-installs missing imports on-the-fly
- File I/O with hash-based storage
- Production-ready with gVisor/Kata support

**Pros**:
- Production-grade security
- Smart dependency detection
- Well-engineered

**Cons**:
- Kubernetes-focused (overkill for Docker-only)
- Not MCP native (would need wrapper)
- IBM project, may have different maintenance trajectory

---

### 5. Code Sandbox MCP (Phil Schmid)
- **URL**: https://www.philschmid.de/code-sandbox-mcp
- **Approach**: Uses llm-sandbox package for containerization
- **Transport**: stdio

**Features**:
- Lightweight
- Uses llm-sandbox library
- Container isolation with resource limits

---

### 6. FastMCP Framework
- **URL**: https://github.com/jlowin/fastmcp
- **Purpose**: Framework for building MCP servers in Python
- **Not a solution itself**, but a building block

**Key features**:
- Simple decorator-based tool definition
- Automatic schema generation from type hints
- Supports stdio and HTTP transports
- Resources and prompts support

**Example**:
```python
from fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

---

---

## Jupyter-Based MCP Servers

### 7. jupyter-mcp-server (Datalayer)
- **URL**: https://github.com/datalayer/jupyter-mcp-server
- **PyPI**: https://pypi.org/project/jupyter-mcp-server/
- **Docker**: https://hub.docker.com/r/datalayer/jupyter-mcp-server
- **Language**: Python
- **Approach**: MCP server that connects to running JupyterLab instance
- **Transport**: stdio, Streamable HTTP

**Tools provided**:

| Tool | Description |
|------|-------------|
| `list_files` | List files in Jupyter server filesystem |
| `list_kernels` | List available/running kernel sessions |
| `connect_to_jupyter` | Dynamic connection to Jupyter server |
| `use_notebook` | Connect/create/switch notebooks |
| `list_notebooks` | List all notebooks and status |
| `read_notebook` | Read notebook cells |
| `read_cell` | Read single cell (metadata, source, outputs) |
| `insert_cell` | Insert new cell |
| `delete_cell` | Delete cell |
| `overwrite_cell_source` | Modify cell source |
| `execute_cell` | Execute cell with timeout, multimodal output |
| `insert_execute_code_cell` | Insert and execute in one step |
| `execute_code` | Execute code directly in kernel |

**Features**:
- Real-time notebook control
- Smart execution with auto-adjust on failure
- Context-aware (understands full notebook)
- Multimodal output (images, plots, text)
- Multi-notebook support
- JupyterLab UI integration
- Works with Claude Desktop, Cursor, Windsurf

**Pros**:
- Full notebook semantics (cells, outputs, state)
- Persistent kernel state across calls
- Rich tool set
- Active development (JupyterCon 2025 presentation)
- Docker image available

**Cons**:
- Requires running JupyterLab instance
- More complex setup (JupyterLab + MCP server)
- Not a standalone sandbox (relies on Jupyter)

---

### 8. mcp-jupyter (Block, Inc.)
- **URL**: https://pypi.org/project/mcp-jupyter/
- **Version**: 2.0.2 (Sept 2025)
- **Language**: Python
- **Approach**: Alternative Jupyter MCP implementation

**Features**:
- Persistent variable state via JupyterLab Kernel
- Agent can install packages, fix errors
- Seamless collaboration with human handoff
- LLM performance comparison infrastructure

**Pros**:
- Simpler than datalayer version
- Good for agent collaboration workflows

**Cons**:
- Less feature-rich than datalayer version
- Still requires Jupyter infrastructure

---

## OpenAI ChatGPT Containers - Architecture Analysis

**Source**: [Simon Willison's Blog (Jan 26, 2026)](https://simonwillison.net/2026/Jan/26/chatgpt-containers/)

This is the most detailed public analysis of how OpenAI's code interpreter works internally.

### Key Architecture Details

**Container Environment**:
- Fully sandboxed virtual machine
- Persistent session for duration of chat (with timeout)
- Files persist in `/mnt/data/`
- Subsequent calls build on previous state
- Memory configurable (default 1GB, up to 4GB via API)

**Languages Supported** (as of Jan 2026):
- Python (primary)
- Bash (direct shell commands)
- Node.js / JavaScript
- Ruby, Perl, PHP, Go, Java, Swift, Kotlin, C, C++
- No Rust yet

**Network & Security**:
- No outbound network access from code
- Package installs work via internal proxy (`applied-caas-gateway1.internal.api.openai.org`)
- `pip install` and `npm install` work through this proxy
- File downloads via `container.download` tool (URL must be "viewed" first for security)

### OpenAI's Internal Tools

**`container.exec`** - Run commands in container:
```json
{
  "cmd": ["python", "script.py"],
  "session_name": "optional",
  "workdir": "/mnt/data",
  "timeout": 30,
  "env": {"KEY": "value"},
  "user": "root"
}
```

**`container.download`** - Download file from URL:
```json
{
  "url": "https://example.com/file.xlsx",
  "filepath": "/mnt/data/file.xlsx"
}
```

**`container.open_image`** - Display image from container:
```json
{
  "path": "/mnt/data/chart.png"
}
```

**`python_user_visible.exec`** - Execute Python code (shown to user):
- Tables, plots, generated files visible
- Internet disabled

**`python.exec`** - Execute Python for internal reasoning:
- Not shown to user
- Used for private computation

### Package Installation Mechanism

Environment variables configure package proxies:
```bash
PIP_INDEX_URL=https://reader:****@packages.applied-caas-gateway1.internal.api.openai.org/.../pypi-public/simple
NPM_CONFIG_REGISTRY=https://reader:****@packages.applied-caas-gateway1.internal.api.openai.org/.../npm-public
```

Registries available (suggests future features):
- PyPI (working)
- npm (working)
- Go modules
- Maven/Gradle
- Cargo (Rust) - not yet enabled
- Docker registry - not yet enabled

### Security Model

1. **URL Validation**: `container.download` only works for URLs "viewed in conversation before"
2. **No arbitrary network**: Code cannot make outbound requests
3. **Proxy-only packages**: Only PyPI/npm via internal proxy
4. **Session isolation**: Each chat gets isolated container
5. **Resource limits**: Memory/CPU constraints per session

### Data Flow (Critical for MCP Design)

**The LLM knows the file path BEFORE generating code.**

```
1. User uploads file (e.g., marketing_q4.csv)
           │
           ▼
2. System communicates to LLM: "File available at /mnt/data/marketing_q4.csv"
           │
           ▼
3. LLM generates code with EXACT path:
   df = pd.read_csv('/mnt/data/marketing_q4.csv')
           │
           ▼
4. Code executes in container where file exists
```

The file path is part of the **prompt context** - the LLM writes code targeting that specific path.

### Implications for Our MCP Design

1. **File upload tool** - uploads file, returns exact path to LLM
2. **Path in context** - LLM receives path before generating code
3. **Code execution tool** - runs code that references the known path
4. **Persistent session** - files and state persist across calls
5. **Artifact output** - generated files (charts, PDFs) returned to LLM

---

## Updated Comparison Matrix

| Feature | code-sandbox-mcp | mcp-run-python | mcp-sandbox | BeeAI | jupyter-mcp-server | OpenAI |
|---------|-----------------|----------------|-------------|-------|-------------------|--------|
| Language | Go | Python+Deno | Python | Python | Python | Unknown |
| Isolation | Docker | WASM | Docker | K8s+Docker | Jupyter Kernel | VM |
| Transport | stdio | stdio/http | SSE | HTTP API | stdio/http | Proprietary |
| Single tool | No | Yes | No | Yes | No | Multiple |
| Persistent state | Yes | No | Yes | No | Yes | Yes |
| File artifacts | Manual | Limited | HTTP URLs | Hash storage | Notebook outputs | Built-in |
| Native libs | Yes | Limited | Yes | Yes | Yes | Yes |
| Multi-language | Bash only | Python only | Python | Python | Python | 11+ |
| Package install | Manual | Auto-detect | Manual | Auto-detect | pip in cell | Proxy |

---

## Recommended Approach

**Build with FastMCP + Docker** matching OpenAI's pattern.

### Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                          HOST MACHINE                              │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                       MCP Server                              │ │
│  │                                                               │ │
│  │  ┌─────────────────────┐    ┌─────────────────────────────┐  │ │
│  │  │  MCP Tools (stdio)  │    │  HTTP File Server (:8080)   │  │ │
│  │  │                     │    │                             │  │ │
│  │  │  - upload_file      │    │  GET /files/{sess}/{file}   │  │ │
│  │  │  - run_python       │    │  → download artifacts       │  │ │
│  │  │  - read_artifact    │    │  → for n8n/external access  │  │ │
│  │  │  - close_session    │    │                             │  │ │
│  │  └─────────────────────┘    └─────────────────────────────┘  │ │
│  │              │                          │                     │ │
│  │              └────────────┬─────────────┘                     │ │
│  │                           ▼                                   │ │
│  │                   Session Manager                             │ │
│  │                     (docker-py)                               │ │
│  │                           │                                   │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│               ┌──────────────┴──────────────┐                     │
│               ▼                             ▼                      │
│       ┌──────────────┐              ┌──────────────┐              │
│       │ sandbox_abc  │              │ sandbox_xyz  │              │
│       │ /mnt/data/   │              │ /mnt/data/   │              │
│       │  sales.csv   │              │  report.xlsx │              │
│       │  chart.png   │              │  analysis.pdf│              │
│       └──────────────┘              └──────────────┘              │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Components

1. **MCP Server** (FastMCP + docker-py):
   - Runs on host or in container with Docker socket access
   - Manages session → container mapping
   - Creates containers on-demand, destroys on timeout
   - Uses `docker-py` for all container operations

2. **Sandbox Containers** (pre-built image):
   - Created per session by MCP server
   - Pre-installed: pandas, numpy, matplotlib, seaborn, openpyxl, reportlab
   - Isolated `/mnt/data/` per container
   - No network access (security)

3. **MCP Tools** (session-aware):
   ```python
   @mcp.tool
   def upload_file(session_id: str, filename: str, content: str) -> str:
       """Upload file to session container. Returns path."""
       container = get_or_create_container(session_id)
       # Write file via container.put_archive()
       return f"/mnt/data/{filename}"

   @mcp.tool
   def run_python(session_id: str, code: str) -> dict:
       """Execute Python in session container."""
       container = get_or_create_container(session_id)
       result = container.exec_run(["python", "-c", code])
       return {"stdout": ..., "stderr": ..., "exit_code": ..., "artifacts": [...]}

   @mcp.tool
   def close_session(session_id: str) -> str:
       """Destroy session container and cleanup."""
       container = sessions.pop(session_id)
       container.remove(force=True)
       return "Session closed"
   ```

### Container Lifecycle

| Event | Action |
|-------|--------|
| First tool call with `session_id` | Create new container |
| Subsequent calls | Reuse existing container |
| Idle timeout (e.g., 30 min) | Auto-destroy container |
| `close_session()` call | Explicit destroy |
| MCP server restart | Cleanup orphaned containers |

### Artifact Handling

**Problem:** Code generates files inside container (`/mnt/data/chart.png`). How does LLM access them?

**Solution:** Two-step approach:

1. `run_python` returns **metadata** about generated files
2. `read_artifact` tool retrieves **content** when LLM needs to inspect

```python
@mcp.tool
def run_python(session_id: str, code: str) -> dict:
    """Execute Python code. Returns stdout/stderr and list of generated artifacts."""
    container = get_or_create_container(session_id)
    result = container.exec_run(["python", "-c", code])

    response = {
        "stdout": result.output.decode(),
        "stderr": result.stderr.decode() if result.stderr else "",
        "exit_code": result.exit_code,
    }

    # Only scan for artifacts on SUCCESS - fast failure feedback
    if result.exit_code == 0:
        artifacts = scan_for_artifacts(container, "/mnt/data/")
        response["artifacts"] = artifacts
    else:
        response["artifacts"] = []  # Don't waste time scanning on failure

    return response

@mcp.tool
def read_artifact(session_id: str, path: str) -> str:
    """Read artifact from container. Returns base64-encoded content."""
    container = get_container(session_id)
    content = read_file_from_container(container, path)
    return base64.b64encode(content).decode()
```

### Fast Iteration on Errors

**The core loop:** Code fails → LLM sees error → LLM fixes → Re-run

```
run_python(code_with_bug)
    ↓
{
    "exit_code": 1,
    "stdout": "",
    "stderr": "Traceback (most recent call last):\n  File ...\nKeyError: 'sales_amount'",
    "artifacts": []   ← empty, no time wasted scanning
}
    ↓
LLM reads error immediately, fixes code
    ↓
run_python(fixed_code)
    ↓
{
    "exit_code": 0,
    "stdout": "Processed 1500 rows...",
    "artifacts": [{"path": "/mnt/data/chart.png", ...}]
}
```

**Design principles for fast iteration:**

| Principle | Implementation |
|-----------|----------------|
| Fail fast | Return immediately on error, skip artifact scanning |
| Clear errors | Full traceback in stderr, not truncated |
| Lightweight failure response | No file transfers, just text |
| Container stays warm | No restart between attempts, state preserved |
| Stateful session | Variables/imports persist across calls |

**Why separate tools:**
- `run_python` stays fast (no large file transfers)
- LLM chooses which artifacts to inspect (e.g., verify chart looks correct)
- Images returned as base64 → Claude can "see" them (multimodal)
- Final PDF: LLM confirms it exists, user retrieves separately

**Artifact retrieval flow:**
```
run_python(code that creates chart.png)
    → {"artifacts": [{"path": "/mnt/data/chart.png", ...}]}
                 ↓
LLM wants to verify chart quality
                 ↓
read_artifact("sess_123", "/mnt/data/chart.png")
    → returns base64 PNG
    → Claude "sees" the image
                 ↓
LLM: "Chart looks good" or "Need to fix colors"
                 ↓
Iterate until satisfied
```

**Artifact access methods:**

| Consumer | Method | How |
|----------|--------|-----|
| Claude (multimodal) | `read_artifact` tool | Returns base64, Claude "sees" images |
| n8n workflows | HTTP download URL | `GET /files/{session_id}/{filename}` |
| Local user | Shared volume | Mount `~/outputs/` to see files directly |

**HTTP file server** (built into MCP server):

```
GET /files/{session_id}/{filename}
    → Returns file content from container's /mnt/data/
    → Content-Type based on file extension
    → 404 if session or file not found
```

**`run_python` returns download URLs for n8n:**

```python
{
    "stdout": "PDF saved successfully",
    "exit_code": 0,
    "artifacts": [
        {
            "path": "/mnt/data/report.pdf",
            "size": 120000,
            "type": "application/pdf",
            "download_url": "http://localhost:8080/files/sess_123/report.pdf"
        }
    ]
}
```

**n8n workflow example:**
```
1. HTTP Request → MCP upload_file (send CSV)
2. HTTP Request → MCP run_python (analysis code)
3. Response contains: artifacts[0].download_url
4. HTTP Request → GET download_url → PDF content
5. Send Email node → attach PDF
```

### Complete Tool Set

| Tool | Purpose |
|------|---------|
| `upload_file(session_id, filename, content)` | Upload data file, returns path |
| `run_python(session_id, code)` | Execute code, returns stdout/stderr/artifact list |
| `read_artifact(session_id, path)` | Get artifact content (base64) |
| `close_session(session_id)` | Destroy container, cleanup |

### Flow

```
upload_file("sess_123", "sales.csv", content)
    → creates container if needed
    → writes to /mnt/data/sales.csv
    → returns "/mnt/data/sales.csv"
                 ↓
LLM generates: df = pd.read_csv('/mnt/data/sales.csv')
                 ↓
run_python("sess_123", code)
    → executes in same container
    → returns stdout/stderr + artifact list
                 ↓
read_artifact("sess_123", "/mnt/data/chart.png")
    → LLM inspects chart, iterates if needed
                 ↓
run_python("sess_123", pdf_generation_code)
    → returns {"artifacts": [{"path": "/mnt/data/report.pdf", ...}]}
                 ↓
LLM confirms PDF created, returns path to user
                 ↓
close_session("sess_123") → container destroyed
```

---

## Open Questions

1. **Transport**: stdio (Claude Code) vs SSE (n8n) vs both?
2. **Starting point**: Fork existing (mcp-sandbox) vs build from scratch (FastMCP)?

---

## References

- MCP Specification: https://modelcontextprotocol.io/
- FastMCP Docs: https://gofastmcp.com/
- Docker SDK for Python: https://docker-py.readthedocs.io/
- llm-sandbox library: https://github.com/vndee/llm-sandbox
- Simon Willison on ChatGPT Containers: https://simonwillison.net/2026/Jan/26/chatgpt-containers/
- Jupyter MCP Server Docs: https://jupyter-mcp-server.datalayer.tech/
- OpenAI Code Interpreter Docs: https://platform.openai.com/docs/guides/tools-code-interpreter
