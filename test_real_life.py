#!/usr/bin/env python3
"""Real-life smoke test — exercises the full MCP tool chain against real containers."""

import base64
import sys

import docker

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import (
    CloseSessionResult,
    ErrorResponse,
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)
from mcp_code_sandbox.session import SessionManager


def main() -> None:
    config = SandboxConfig()
    client = docker.from_env()
    mgr = SessionManager(config, client)

    print("=" * 60)
    print("REAL-LIFE SMOKE TEST")
    print("=" * 60)

    # ── 1. Upload a CSV file ──────────────────────────────────
    print("\n[1] Uploading sample CSV...")
    csv_data = b"""date,product,revenue,units
2024-01-01,Widget A,1200,40
2024-01-01,Widget B,800,25
2024-02-01,Widget A,1500,50
2024-02-01,Widget B,950,30
2024-03-01,Widget A,1800,60
2024-03-01,Widget B,1100,35
2024-04-01,Widget A,2100,70
2024-04-01,Widget B,1300,42
"""
    b64 = base64.b64encode(csv_data).decode()
    result = mgr.upload(None, "sales.csv", b64)
    assert isinstance(result, UploadResult), f"Upload failed: {result}"
    sid = result.session_id
    print(f"    Session: {sid}")
    print(f"    Path: {result.path}")

    # ── 2. Run pandas analysis ────────────────────────────────
    print("\n[2] Running pandas analysis...")
    code_analysis = """\
import pandas as pd

df = pd.read_csv('/mnt/data/sales.csv')
print("=== Dataset Info ===")
print(f"Rows: {len(df)}, Columns: {list(df.columns)}")
print(f"\\nTotal revenue: ${df['revenue'].sum():,.0f}")
print(f"Total units: {df['units'].sum():,}")
print(f"\\n=== Revenue by Product ===")
print(df.groupby('product')['revenue'].sum().to_string())
print(f"\\n=== Monthly Trend ===")
monthly = df.groupby('date')['revenue'].sum()
print(monthly.to_string())
"""
    result = mgr.execute(sid, code_analysis)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Code error (exit {result.exit_code}):\n{result.stderr}"
    print(f"    Exit code: {result.exit_code}")
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout)}")

    # ── 3. Generate a chart ───────────────────────────────────
    print("\n[3] Generating matplotlib chart...")
    code_chart = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('/mnt/data/sales.csv')
fig, ax = plt.subplots(figsize=(10, 6))

for product in df['product'].unique():
    subset = df[df['product'] == product]
    ax.plot(subset['date'], subset['revenue'], marker='o', label=product, linewidth=2)

ax.set_title('Monthly Revenue by Product', fontsize=16, fontweight='bold')
ax.set_xlabel('Date')
ax.set_ylabel('Revenue ($)')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/mnt/data/revenue_chart.png', dpi=150)
print(f"Chart saved: revenue_chart.png")
"""
    result = mgr.execute(sid, code_chart)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Chart code error:\n{result.stderr}"
    print(f"    Exit code: {result.exit_code}")
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Artifacts: {[a.filename for a in result.artifacts]}")
    assert any(
        a.filename == "revenue_chart.png" for a in result.artifacts
    ), "Chart not in artifacts!"

    # ── 4. Generate a summary report (text file) ──────────────
    print("\n[4] Generating summary report...")
    code_report = """\
import pandas as pd

df = pd.read_csv('/mnt/data/sales.csv')

report = []
report.append("SALES SUMMARY REPORT")
report.append("=" * 40)
report.append(f"\\nPeriod: {df['date'].min()} to {df['date'].max()}")
report.append(f"Total Revenue: ${df['revenue'].sum():,.0f}")
report.append(f"Total Units Sold: {df['units'].sum():,}")
report.append(f"\\nTop Product by Revenue:")
top = df.groupby('product')['revenue'].sum().idxmax()
top_rev = df.groupby('product')['revenue'].sum().max()
report.append(f"  {top}: ${top_rev:,.0f}")
report.append(f"\\nMonthly Growth Rate:")
monthly_rev = df.groupby('date')['revenue'].sum()
for i in range(1, len(monthly_rev)):
    prev = monthly_rev.iloc[i-1]
    curr = monthly_rev.iloc[i]
    growth = (curr - prev) / prev * 100
    report.append(f"  {monthly_rev.index[i]}: {growth:+.1f}%")

text = "\\n".join(report)
with open('/mnt/data/report.txt', 'w') as f:
    f.write(text)
print(text)
"""
    result = mgr.execute(sid, code_report)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Report code error:\n{result.stderr}"
    print(f"    Exit code: {result.exit_code}")
    print(f"    Output:\n{_indent(result.stdout)}")

    # ── 5. List all artifacts ─────────────────────────────────
    print("\n[5] Listing all artifacts...")
    result = mgr.list_files(sid)
    assert isinstance(result, ListArtifactsResult), f"List failed: {result}"
    print(f"    Found {len(result.artifacts)} artifacts:")
    for a in result.artifacts:
        print(f"      {a.filename:25s} {a.size_bytes:>8,} bytes  ({a.mime_type})")

    # ── 6. Read artifact (chart PNG) ──────────────────────────
    print("\n[6] Reading chart artifact...")
    result = mgr.read_file(sid, "/mnt/data/revenue_chart.png")
    assert isinstance(result, ReadArtifactResult), f"Read failed: {result}"
    png_bytes = base64.b64decode(result.content_base64)
    assert png_bytes[:4] == b"\x89PNG", "Not a valid PNG!"
    print(f"    Filename: {result.filename}")
    print(f"    Size: {result.size_bytes:,} bytes")
    print(f"    MIME: {result.mime_type}")
    print(f"    PNG header verified: OK")

    # ── 7. Test error handling (intentional error) ────────────
    print("\n[7] Testing error handling (intentional NameError)...")
    result = mgr.execute(sid, "print(undefined_variable)")
    assert isinstance(result, RunResult)
    assert result.exit_code != 0
    assert "NameError" in result.stderr
    print(f"    Exit code: {result.exit_code}")
    print(f"    Error captured: {result.stderr.strip().splitlines()[-1]}")

    # ── 8. Test validation (bad session ID) ───────────────────
    print("\n[8] Testing input validation (invalid session ID)...")
    from mcp_code_sandbox.validation import validate_session_id

    err = validate_session_id("bad session!")
    assert isinstance(err, ErrorResponse)
    print(f"    Rejected: error={err.error}")

    # ── 9. Close session ──────────────────────────────────────
    print("\n[9] Closing session...")
    result = mgr.close(sid)
    assert isinstance(result, CloseSessionResult)
    assert result.status == "closed"
    print(f"    Status: {result.status}")
    assert sid not in mgr.sessions

    # ── Done ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.strip().splitlines())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        sys.exit(1)
