"""End-to-end demo: marketing CSV analysis with charts and PDF report.

Uses SessionManager directly (not MCP client) to exercise the full workflow:
1. Upload marketing CSV
2. Run pandas analysis (summary stats)
3. Create seaborn chart
4. Generate PDF report via reportlab
5. Read artifact (chart.png)
6. List all artifacts
7. Demonstrate error iteration (intentional bug → fix → retry)
8. Close session
"""

import base64
import contextlib
from pathlib import Path

import docker

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import (
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

    try:
        _run_demo(mgr)
    finally:
        # Cleanup all sessions
        for _sid, container in list(mgr.sessions.items()):
            with contextlib.suppress(Exception):
                container.remove(force=True)

    print("\n=== Demo completed successfully ===")


def _run_demo(mgr: SessionManager) -> None:
    # --- Step 1: Upload CSV ---
    print("Step 1: Uploading marketing.csv...")
    csv_path = Path(__file__).parent / "data" / "marketing.csv"
    csv_b64 = base64.b64encode(csv_path.read_bytes()).decode()

    result = mgr.upload(None, "marketing.csv", csv_b64)
    assert isinstance(result, UploadResult), f"Upload failed: {result}"
    sid = result.session_id
    print(f"  Uploaded to {result.path} (session: {sid})")

    # --- Step 2: Run summary stats ---
    print("\nStep 2: Running pandas summary analysis...")
    code_stats = """\
import pandas as pd
df = pd.read_csv('/mnt/data/marketing.csv')
print("=== Marketing Data Summary ===")
print(f"Campaigns: {df['campaign'].nunique()}")
print(f"Channels: {df['channel'].unique().tolist()}")
print(f"Total Spend: ${df['spend'].sum():,.0f}")
print(f"Total Revenue: ${df['revenue'].sum():,.0f}")
print(f"Overall ROI: {(df['revenue'].sum() / df['spend'].sum() - 1) * 100:.1f}%")
print()
print("Revenue by Campaign:")
print(df.groupby('campaign')['revenue'].sum().sort_values(ascending=False).to_string())
print()
print("Revenue by Channel:")
print(df.groupby('channel')['revenue'].sum().sort_values(ascending=False).to_string())
"""
    run = mgr.execute(sid, code_stats)
    assert isinstance(run, RunResult), f"Execute failed: {run}"
    assert run.exit_code == 0, f"Code error: {run.stderr}"
    print(run.stdout)

    # --- Step 3: Create seaborn chart ---
    print("Step 3: Creating seaborn chart...")
    code_chart = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

df = pd.read_csv('/mnt/data/marketing.csv')

fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Revenue by campaign
campaign_rev = df.groupby('campaign')['revenue'].sum().sort_values(ascending=True)
sns.barplot(x=campaign_rev.values, y=campaign_rev.index, ax=axes[0], palette='viridis')
axes[0].set_title('Revenue by Campaign')
axes[0].set_xlabel('Revenue ($)')

# Revenue by channel
channel_rev = df.groupby('channel')['revenue'].sum().sort_values(ascending=True)
sns.barplot(x=channel_rev.values, y=channel_rev.index, ax=axes[1], palette='magma')
axes[1].set_title('Revenue by Channel')
axes[1].set_xlabel('Revenue ($)')

plt.tight_layout()
plt.savefig('/mnt/data/chart.png', dpi=150)
print('Chart saved as chart.png')
"""
    run = mgr.execute(sid, code_chart)
    assert isinstance(run, RunResult), f"Execute failed: {run}"
    assert run.exit_code == 0, f"Chart error: {run.stderr}"
    print(f"  {run.stdout.strip()}")
    print(f"  Artifacts detected: {[a.filename for a in run.artifacts]}")

    # --- Step 4: Generate PDF report ---
    print("\nStep 4: Generating PDF report via reportlab...")
    code_pdf = """\
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

df = pd.read_csv('/mnt/data/marketing.csv')
styles = getSampleStyleSheet()

doc = SimpleDocTemplate('/mnt/data/report.pdf', pagesize=letter)
elements = []

# Title
elements.append(Paragraph('Marketing Analysis Report', styles['Title']))
elements.append(Spacer(1, 0.3 * inch))

# Summary
total_spend = df['spend'].sum()
total_rev = df['revenue'].sum()
roi = (total_rev / total_spend - 1) * 100
elements.append(Paragraph(
    f'Total Spend: ${total_spend:,.0f} | Total Revenue: ${total_rev:,.0f} | ROI: {roi:.1f}%',
    styles['Normal']
))
elements.append(Spacer(1, 0.3 * inch))

# Table: Revenue by campaign
elements.append(Paragraph('Revenue by Campaign', styles['Heading2']))
campaign_data = [['Campaign', 'Spend', 'Revenue', 'ROI']]
for campaign, group in df.groupby('campaign'):
    s, r = group['spend'].sum(), group['revenue'].sum()
    campaign_data.append([campaign, f'${s:,.0f}', f'${r:,.0f}', f'{(r/s-1)*100:.0f}%'])

t = Table(campaign_data)
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
]))
elements.append(t)

doc.build(elements)
print('Report saved as report.pdf')
"""
    run = mgr.execute(sid, code_pdf)
    assert isinstance(run, RunResult), f"Execute failed: {run}"
    assert run.exit_code == 0, f"PDF error: {run.stderr}"
    print(f"  {run.stdout.strip()}")
    print(f"  Artifacts detected: {[a.filename for a in run.artifacts]}")

    # --- Step 5: Read artifact (chart.png) ---
    print("\nStep 5: Reading chart.png artifact...")
    read = mgr.read_file(sid, "/mnt/data/chart.png")
    assert isinstance(read, ReadArtifactResult), f"Read failed: {read}"
    print(f"  Filename: {read.filename}")
    print(f"  MIME type: {read.mime_type}")
    print(f"  Size: {read.size_bytes:,} bytes")
    # Verify it's valid PNG
    png_bytes = base64.b64decode(read.content_base64)
    assert png_bytes[:4] == b"\x89PNG", "Not a valid PNG file!"
    print("  Verified: valid PNG")

    # --- Step 6: List all artifacts ---
    print("\nStep 6: Listing all artifacts...")
    listing = mgr.list_files(sid)
    assert isinstance(listing, ListArtifactsResult)
    for artifact in listing.artifacts:
        print(f"  {artifact.filename} ({artifact.size_bytes:,} bytes, {artifact.mime_type})")

    # --- Step 7: Error iteration ---
    print("\nStep 7: Demonstrating error iteration...")
    # Intentional bug: wrong column name
    code_bug = """\
import pandas as pd
df = pd.read_csv('/mnt/data/marketing.csv')
print(df['sales_amount'].sum())  # Wrong column name!
"""
    run = mgr.execute(sid, code_bug)
    assert isinstance(run, RunResult)
    assert run.exit_code != 0
    print(f"  Error (expected): exit_code={run.exit_code}")
    print(f"  stderr snippet: {run.stderr.strip().splitlines()[-1]}")

    # Fix the bug
    code_fix = """\
import pandas as pd
df = pd.read_csv('/mnt/data/marketing.csv')
print(f"Total revenue: ${df['revenue'].sum():,.0f}")  # Fixed!
"""
    run = mgr.execute(sid, code_fix)
    assert isinstance(run, RunResult)
    assert run.exit_code == 0
    print(f"  Fixed: {run.stdout.strip()}")

    # --- Step 8: Close session ---
    print("\nStep 8: Closing session...")
    close = mgr.close(sid)
    print(f"  Result: {close}")


if __name__ == "__main__":
    main()
