#!/usr/bin/env python3
"""Generate a large CSV and run full EDA through the sandbox tool chain."""

import base64
import csv
import io
import random
import sys

import docker

from mcp_code_sandbox.config import SandboxConfig
from mcp_code_sandbox.models import (
    ListArtifactsResult,
    ReadArtifactResult,
    RunResult,
    UploadResult,
)
from mcp_code_sandbox.session import SessionManager


def generate_large_csv(n_rows: int = 50_000) -> bytes:
    """Generate a realistic e-commerce transactions CSV."""
    random.seed(42)

    categories = [
        "Electronics", "Clothing", "Home & Garden", "Sports",
        "Books", "Toys", "Food & Beverage", "Health & Beauty",
        "Automotive", "Office Supplies",
    ]
    regions = ["North", "South", "East", "West", "Central"]
    channels = ["Online", "In-Store", "Mobile App", "Phone"]
    payment_methods = ["Credit Card", "Debit Card", "PayPal", "Cash", "Gift Card"]
    customer_segments = ["Regular", "Premium", "VIP", "New"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "transaction_id", "date", "customer_id", "customer_segment",
        "category", "product_name", "quantity", "unit_price",
        "discount_pct", "total_amount", "region", "channel",
        "payment_method", "rating", "return_flag",
    ])

    products_by_category = {
        "Electronics": ["Laptop", "Phone", "Tablet", "Headphones", "Camera", "Smartwatch", "Speaker", "Monitor"],
        "Clothing": ["T-Shirt", "Jeans", "Jacket", "Dress", "Sneakers", "Boots", "Hat", "Scarf"],
        "Home & Garden": ["Lamp", "Rug", "Planter", "Toolset", "Cushion", "Mirror", "Vase", "Candle"],
        "Sports": ["Yoga Mat", "Dumbbells", "Tennis Racket", "Football", "Bike Helmet", "Running Shoes", "Swim Goggles", "Jump Rope"],
        "Books": ["Novel", "Textbook", "Cookbook", "Biography", "Comic", "Journal", "Atlas", "Dictionary"],
        "Toys": ["Puzzle", "Board Game", "Action Figure", "Doll", "Lego Set", "RC Car", "Stuffed Animal", "Card Game"],
        "Food & Beverage": ["Coffee Beans", "Tea Set", "Chocolate Box", "Wine", "Olive Oil", "Spice Kit", "Protein Bar", "Juice Pack"],
        "Health & Beauty": ["Moisturizer", "Shampoo", "Vitamins", "Sunscreen", "Perfume", "Face Mask", "Lip Balm", "Hair Oil"],
        "Automotive": ["Car Charger", "Dash Cam", "Floor Mats", "Air Freshener", "Wiper Blades", "Phone Mount", "Seat Cover", "Tire Gauge"],
        "Office Supplies": ["Notebook", "Pen Set", "Stapler", "Desk Lamp", "Sticky Notes", "Binder", "Whiteboard", "Calculator"],
    }

    base_prices = {
        "Electronics": (30, 1200), "Clothing": (10, 200), "Home & Garden": (15, 300),
        "Sports": (10, 250), "Books": (5, 80), "Toys": (8, 150),
        "Food & Beverage": (5, 60), "Health & Beauty": (8, 120),
        "Automotive": (10, 200), "Office Supplies": (3, 80),
    }

    for i in range(n_rows):
        # Seasonal variation: more sales in Nov-Dec, dip in Jan-Feb
        day_of_year = i % 365
        month = (day_of_year // 30) % 12 + 1
        year = 2023 + (i // 365) % 2
        day = (day_of_year % 28) + 1
        date = f"{year}-{month:02d}-{day:02d}"

        category = random.choices(
            categories,
            weights=[15, 18, 10, 8, 12, 7, 10, 8, 5, 7],
        )[0]
        product = random.choice(products_by_category[category])
        region = random.choice(regions)
        channel = random.choices(channels, weights=[40, 30, 25, 5])[0]
        payment = random.choices(payment_methods, weights=[35, 25, 20, 10, 10])[0]
        segment = random.choices(customer_segments, weights=[50, 25, 10, 15])[0]

        lo, hi = base_prices[category]
        unit_price = round(random.uniform(lo, hi), 2)
        quantity = random.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]

        # Seasonal discount: higher in Jan (clearance), lower in Nov-Dec
        base_discount = random.uniform(0, 30)
        if month in (1, 2):
            base_discount += 10
        elif month in (11, 12):
            base_discount = max(0, base_discount - 10)
        discount_pct = round(min(base_discount, 50), 1)

        total = round(quantity * unit_price * (1 - discount_pct / 100), 2)

        # Rating: slightly correlated with discount (better deals = happier)
        base_rating = random.gauss(3.8, 0.8) + (discount_pct / 100)
        rating = round(max(1.0, min(5.0, base_rating)), 1)

        # Return: ~8% overall, higher for Electronics
        return_prob = 0.08 if category != "Electronics" else 0.14
        return_flag = 1 if random.random() < return_prob else 0

        customer_id = f"CUST_{random.randint(1, 5000):05d}"

        writer.writerow([
            f"TXN_{i + 1:07d}", date, customer_id, segment,
            category, product, quantity, unit_price,
            discount_pct, total, region, channel,
            payment, rating, return_flag,
        ])

    return buf.getvalue().encode()


def main() -> None:
    config = SandboxConfig()
    client = docker.from_env()
    mgr = SessionManager(config, client)

    print("=" * 70)
    print("LARGE CSV EDA TEST")
    print("=" * 70)

    # ── 1. Generate & upload CSV ─────────────────────────────────
    print("\n[1] Generating 50,000-row e-commerce CSV...")
    csv_bytes = generate_large_csv(50_000)
    csv_size_mb = len(csv_bytes) / (1024 * 1024)
    print(f"    Generated: {len(csv_bytes):,} bytes ({csv_size_mb:.1f} MB)")

    b64 = base64.b64encode(csv_bytes).decode()
    result = mgr.upload(None, "transactions.csv", b64)
    assert isinstance(result, UploadResult), f"Upload failed: {result}"
    sid = result.session_id
    print(f"    Uploaded to session: {sid}")

    # ── 2. Basic dataset overview ────────────────────────────────
    print("\n[2] Running dataset overview...")
    code_overview = """\
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('/mnt/data/transactions.csv')

print("=" * 60)
print("DATASET OVERVIEW")
print("=" * 60)
print(f"\\nShape: {df.shape[0]:,} rows x {df.shape[1]} columns")
print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")
print(f"\\nColumn types:\\n{df.dtypes.value_counts().to_string()}")
print(f"\\nFirst 5 rows:\\n{df.head().to_string()}")
print(f"\\nMissing values:\\n{df.isnull().sum().to_string()}")
print(f"\\nNumeric summary:\\n{df.describe().round(2).to_string()}")
print(f"\\nCategorical columns:")
for col in df.select_dtypes(include='object').columns:
    print(f"  {col}: {df[col].nunique()} unique values")
"""
    result = mgr.execute(sid, code_overview)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Error:\n{result.stderr}"
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout[:2000])}")

    # ── 3. Error iteration — intentional bug, fix, retry ────────
    print("\n[3] Error iteration (intentional bug → fix → retry in same session)...")

    # First attempt: wrong column name
    code_buggy = """\
import pandas as pd
df = pd.read_csv('/mnt/data/transactions.csv')
# BUG: column is 'total_amount', not 'amount'
print(f"Average order: ${df['amount'].mean():.2f}")
"""
    result = mgr.execute(sid, code_buggy)
    assert isinstance(result, RunResult)
    assert result.exit_code != 0, "Expected an error but got success"
    print(f"    Attempt 1 FAILED (expected):")
    print(f"      Exit code: {result.exit_code}")
    error_line = result.stderr.strip().splitlines()[-1]
    print(f"      Error: {error_line}")

    # Parse the error and "fix" the code — simulating LLM iteration
    assert "KeyError" in result.stderr, f"Expected KeyError, got: {result.stderr}"
    print("    -> LLM reads error, fixes column name to 'total_amount'")

    code_fixed = """\
import pandas as pd
df = pd.read_csv('/mnt/data/transactions.csv')
# FIXED: correct column name
print(f"Average order: ${df['total_amount'].mean():.2f}")
print(f"Median order: ${df['total_amount'].median():.2f}")
print(f"Std deviation: ${df['total_amount'].std():.2f}")
"""
    result = mgr.execute(sid, code_fixed)
    assert isinstance(result, RunResult)
    assert result.exit_code == 0, f"Fixed code still failed:\n{result.stderr}"
    print(f"    Attempt 2 SUCCEEDED:")
    print(f"      Exit code: {result.exit_code}")
    print(f"      Output:\n{_indent(result.stdout)}")

    # Second error: try to import a library that doesn't exist
    print("\n    Testing missing library error...")
    code_missing_lib = """\
import pandas as pd
import plotly.express as px  # not installed in sandbox
df = pd.read_csv('/mnt/data/transactions.csv')
fig = px.scatter(df, x='discount_pct', y='total_amount')
fig.write_html('/mnt/data/scatter.html')
"""
    result = mgr.execute(sid, code_missing_lib)
    assert isinstance(result, RunResult)
    assert result.exit_code != 0
    error_line = result.stderr.strip().splitlines()[-1]
    print(f"    Attempt 3 FAILED (expected):")
    print(f"      Error: {error_line}")
    print("    -> LLM reads error, falls back to matplotlib")

    code_fallback = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
df = pd.read_csv('/mnt/data/transactions.csv')
sample = df.sample(2000, random_state=42)
plt.figure(figsize=(10, 6))
plt.scatter(sample['discount_pct'], sample['total_amount'], alpha=0.3, s=10, c='#2196F3')
plt.title('Discount % vs Order Amount (fallback to matplotlib)')
plt.xlabel('Discount %')
plt.ylabel('Total Amount ($)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/mnt/data/scatter_fallback.png', dpi=100)
print("Scatter saved with matplotlib fallback")
"""
    result = mgr.execute(sid, code_fallback)
    assert isinstance(result, RunResult)
    assert result.exit_code == 0, f"Fallback failed:\n{result.stderr}"
    print(f"    Attempt 4 SUCCEEDED:")
    print(f"      Output: {result.stdout.strip()}")
    print(f"      Artifacts: {[a.filename for a in result.artifacts]}")

    # ── 4. Revenue analysis & visualizations ─────────────────────
    print("\n[4] Revenue analysis + 6-panel dashboard...")
    code_dashboard = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('/mnt/data/transactions.csv')

# Prepare data
df['date'] = pd.to_datetime(df['date'])
df['month'] = df['date'].dt.to_period('M')
df['month_str'] = df['date'].dt.strftime('%Y-%m')

fig, axes = plt.subplots(2, 3, figsize=(20, 12))
fig.suptitle('E-Commerce Transaction Dashboard (50K Transactions)', fontsize=18, fontweight='bold', y=1.02)

colors = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0',
          '#00BCD4', '#FF5722', '#607D8B', '#795548', '#3F51B5']

# 1. Monthly revenue trend
ax = axes[0, 0]
monthly_rev = df.groupby('month_str')['total_amount'].sum().reset_index()
ax.fill_between(range(len(monthly_rev)), monthly_rev['total_amount'], alpha=0.3, color=colors[0])
ax.plot(range(len(monthly_rev)), monthly_rev['total_amount'], color=colors[0], linewidth=2, marker='o', markersize=4)
ax.set_title('Monthly Revenue Trend', fontsize=13, fontweight='bold')
ax.set_xlabel('Month')
ax.set_ylabel('Revenue ($)')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
ax.set_xticks(range(0, len(monthly_rev), 3))
ax.set_xticklabels(monthly_rev['month_str'].iloc[::3], rotation=45, ha='right')
ax.grid(True, alpha=0.3)

# 2. Revenue by category (horizontal bar)
ax = axes[0, 1]
cat_rev = df.groupby('category')['total_amount'].sum().sort_values()
bars = ax.barh(cat_rev.index, cat_rev.values, color=colors[:len(cat_rev)])
ax.set_title('Revenue by Category', fontsize=13, fontweight='bold')
ax.set_xlabel('Total Revenue ($)')
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x/1000:.0f}K'))
for bar, val in zip(bars, cat_rev.values):
    ax.text(val + cat_rev.max() * 0.01, bar.get_y() + bar.get_height()/2,
            f'${val:,.0f}', va='center', fontsize=9)

# 3. Sales channel distribution (pie)
ax = axes[0, 2]
channel_counts = df['channel'].value_counts()
wedges, texts, autotexts = ax.pie(
    channel_counts.values, labels=channel_counts.index,
    autopct='%1.1f%%', colors=colors[:len(channel_counts)],
    startangle=90, textprops={'fontsize': 10}
)
ax.set_title('Sales by Channel', fontsize=13, fontweight='bold')

# 4. Rating distribution
ax = axes[1, 0]
ax.hist(df['rating'], bins=30, color=colors[1], alpha=0.7, edgecolor='white')
ax.axvline(df['rating'].mean(), color='red', linestyle='--', linewidth=2, label=f"Mean: {df['rating'].mean():.2f}")
ax.set_title('Customer Rating Distribution', fontsize=13, fontweight='bold')
ax.set_xlabel('Rating')
ax.set_ylabel('Count')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# 5. Discount vs Total Amount (scatter, sampled)
ax = axes[1, 1]
sample = df.sample(n=min(3000, len(df)), random_state=42)
scatter = ax.scatter(
    sample['discount_pct'], sample['total_amount'],
    c=sample['quantity'], cmap='viridis', alpha=0.4, s=15
)
plt.colorbar(scatter, ax=ax, label='Quantity')
ax.set_title('Discount % vs Total Amount', fontsize=13, fontweight='bold')
ax.set_xlabel('Discount (%)')
ax.set_ylabel('Total Amount ($)')
ax.grid(True, alpha=0.3)

# 6. Return rate by category
ax = axes[1, 2]
return_rate = df.groupby('category')['return_flag'].mean().sort_values(ascending=False) * 100
bars = ax.bar(range(len(return_rate)), return_rate.values, color=colors[:len(return_rate)])
ax.set_title('Return Rate by Category', fontsize=13, fontweight='bold')
ax.set_ylabel('Return Rate (%)')
ax.set_xticks(range(len(return_rate)))
ax.set_xticklabels(return_rate.index, rotation=45, ha='right', fontsize=9)
ax.grid(True, alpha=0.3, axis='y')
for bar, val in zip(bars, return_rate.values):
    ax.text(bar.get_x() + bar.get_width()/2, val + 0.2, f'{val:.1f}%',
            ha='center', fontsize=9)

plt.tight_layout()
plt.savefig('/mnt/data/dashboard.png', dpi=150, bbox_inches='tight')
print("Dashboard saved: dashboard.png")

# Print summary stats
total_rev = df['total_amount'].sum()
avg_order = df['total_amount'].mean()
print(f"\\nTotal Revenue: ${total_rev:,.2f}")
print(f"Average Order Value: ${avg_order:,.2f}")
print(f"Total Transactions: {len(df):,}")
print(f"Unique Customers: {df['customer_id'].nunique():,}")
print(f"Average Rating: {df['rating'].mean():.2f}")
print(f"Return Rate: {df['return_flag'].mean()*100:.1f}%")
"""
    result = mgr.execute(sid, code_dashboard)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Dashboard error:\n{result.stderr}"
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout)}")
    print(f"    Artifacts: {[a.filename for a in result.artifacts]}")

    # ── 5. Correlation heatmap + statistical analysis ────────────
    print("\n[5] Correlation heatmap + statistical tests...")
    code_stats = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('/mnt/data/transactions.csv')

# Correlation heatmap
numeric_cols = ['quantity', 'unit_price', 'discount_pct', 'total_amount', 'rating', 'return_flag']
corr = df[numeric_cols].corr()

fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# Heatmap
sns.heatmap(corr, annot=True, fmt='.3f', cmap='RdBu_r', center=0,
            vmin=-1, vmax=1, ax=axes[0], square=True,
            linewidths=0.5, cbar_kws={'shrink': 0.8})
axes[0].set_title('Correlation Matrix', fontsize=14, fontweight='bold')

# Box plot: total_amount by category
order = df.groupby('category')['total_amount'].median().sort_values(ascending=False).index
sns.boxplot(data=df, x='category', y='total_amount', order=order, ax=axes[1],
            palette='Set2', showfliers=False)
axes[1].set_title('Order Amount Distribution by Category', fontsize=14, fontweight='bold')
axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=45, ha='right')
axes[1].set_ylabel('Total Amount ($)')

plt.tight_layout()
plt.savefig('/mnt/data/correlation_analysis.png', dpi=150, bbox_inches='tight')
print("Correlation analysis saved: correlation_analysis.png")

# Statistical tests
print("\\n" + "=" * 60)
print("STATISTICAL ANALYSIS")
print("=" * 60)

# T-test: Online vs In-Store total amounts
online = df[df['channel'] == 'Online']['total_amount']
instore = df[df['channel'] == 'In-Store']['total_amount']
t_stat, p_val = stats.ttest_ind(online, instore)
print(f"\\nT-test (Online vs In-Store order values):")
print(f"  Online mean: ${online.mean():.2f}, In-Store mean: ${instore.mean():.2f}")
print(f"  t-statistic: {t_stat:.4f}, p-value: {p_val:.4f}")
print(f"  Significant (p<0.05): {'Yes' if p_val < 0.05 else 'No'}")

# Chi-square: return_flag vs category
contingency = pd.crosstab(df['category'], df['return_flag'])
chi2, p_val, dof, expected = stats.chi2_contingency(contingency)
print(f"\\nChi-square test (Category vs Returns):")
print(f"  Chi2: {chi2:.2f}, p-value: {p_val:.6f}, dof: {dof}")
print(f"  Significant (p<0.05): {'Yes' if p_val < 0.05 else 'No'}")

# ANOVA: total_amount across customer segments
groups = [group['total_amount'].values for _, group in df.groupby('customer_segment')]
f_stat, p_val = stats.f_oneway(*groups)
print(f"\\nANOVA (Total amount across customer segments):")
for seg in df['customer_segment'].unique():
    seg_mean = df[df['customer_segment'] == seg]['total_amount'].mean()
    print(f"  {seg}: ${seg_mean:.2f}")
print(f"  F-statistic: {f_stat:.4f}, p-value: {p_val:.4f}")
print(f"  Significant (p<0.05): {'Yes' if p_val < 0.05 else 'No'}")

# Pearson correlation: discount vs rating
r, p = stats.pearsonr(df['discount_pct'], df['rating'])
print(f"\\nPearson correlation (Discount % vs Rating):")
print(f"  r = {r:.4f}, p-value = {p:.6f}")

# Top 10 customers by total spend
print(f"\\nTop 10 Customers by Total Spend:")
top_customers = df.groupby('customer_id').agg(
    total_spend=('total_amount', 'sum'),
    num_orders=('transaction_id', 'count'),
    avg_rating=('rating', 'mean'),
).sort_values('total_spend', ascending=False).head(10)
print(top_customers.to_string())
"""
    result = mgr.execute(sid, code_stats)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Stats error:\n{result.stderr}"
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout)}")
    print(f"    Artifacts: {[a.filename for a in result.artifacts]}")

    # ── 6. Customer segmentation visualization ───────────────────
    print("\n[6] Customer segmentation & time-series analysis...")
    code_segment = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('/mnt/data/transactions.csv')
df['date'] = pd.to_datetime(df['date'])

fig, axes = plt.subplots(2, 2, figsize=(18, 14))
fig.suptitle('Customer Segmentation & Time Analysis', fontsize=16, fontweight='bold')

colors_seg = {'Regular': '#2196F3', 'Premium': '#4CAF50', 'VIP': '#FF9800', 'New': '#E91E63'}

# 1. Revenue by segment over time
ax = axes[0, 0]
monthly_seg = df.groupby([df['date'].dt.to_period('M'), 'customer_segment'])['total_amount'].sum().unstack(fill_value=0)
monthly_seg.index = monthly_seg.index.astype(str)
monthly_seg.plot(kind='area', ax=ax, alpha=0.7, color=[colors_seg.get(c, '#999') for c in monthly_seg.columns])
ax.set_title('Revenue by Segment Over Time', fontsize=13, fontweight='bold')
ax.set_ylabel('Revenue ($)')
ax.legend(title='Segment', loc='upper left')
ax.grid(True, alpha=0.3)
# Rotate x-axis labels
for label in ax.get_xticklabels():
    label.set_rotation(45)
    label.set_ha('right')

# 2. Average order value by segment and channel
ax = axes[0, 1]
seg_channel = df.groupby(['customer_segment', 'channel'])['total_amount'].mean().unstack()
seg_channel.plot(kind='bar', ax=ax, width=0.7)
ax.set_title('Avg Order Value: Segment x Channel', fontsize=13, fontweight='bold')
ax.set_ylabel('Average Order ($)')
ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
ax.legend(title='Channel', fontsize=9)
ax.grid(True, alpha=0.3, axis='y')

# 3. Heatmap: category preference by segment
ax = axes[1, 0]
cat_seg = pd.crosstab(df['category'], df['customer_segment'], normalize='columns') * 100
sns.heatmap(cat_seg, annot=True, fmt='.1f', cmap='YlOrRd', ax=ax,
            cbar_kws={'label': '% of Segment Orders'})
ax.set_title('Category Preference by Segment (%)', fontsize=13, fontweight='bold')

# 4. Day-of-week pattern
ax = axes[1, 1]
df['day_of_week'] = df['date'].dt.day_name()
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
dow_rev = df.groupby('day_of_week')['total_amount'].agg(['sum', 'count']).reindex(day_order)
ax2 = ax.twinx()
bars = ax.bar(range(7), dow_rev['sum'], alpha=0.6, color='#2196F3', label='Revenue')
line = ax2.plot(range(7), dow_rev['count'], color='#E91E63', marker='o', linewidth=2, label='# Transactions')
ax.set_title('Revenue & Transactions by Day of Week', fontsize=13, fontweight='bold')
ax.set_xticks(range(7))
ax.set_xticklabels([d[:3] for d in day_order])
ax.set_ylabel('Revenue ($)', color='#2196F3')
ax2.set_ylabel('# Transactions', color='#E91E63')
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('/mnt/data/segmentation.png', dpi=150, bbox_inches='tight')
print("Segmentation analysis saved: segmentation.png")

# Summary stats by segment
print("\\nCustomer Segment Summary:")
seg_summary = df.groupby('customer_segment').agg(
    customers=('customer_id', 'nunique'),
    transactions=('transaction_id', 'count'),
    total_revenue=('total_amount', 'sum'),
    avg_order=('total_amount', 'mean'),
    avg_rating=('rating', 'mean'),
    return_rate=('return_flag', 'mean'),
).round(2)
seg_summary['return_rate'] = (seg_summary['return_rate'] * 100).round(1)
print(seg_summary.to_string())
"""
    result = mgr.execute(sid, code_segment)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"Segment error:\n{result.stderr}"
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout)}")
    print(f"    Artifacts: {[a.filename for a in result.artifacts]}")

    # ── 7. Generate PDF report ───────────────────────────────────
    print("\n[7] Generating PDF summary report...")
    code_pdf = """\
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('/mnt/data/transactions.csv')

doc = SimpleDocTemplate('/mnt/data/eda_report.pdf', pagesize=A4,
                        topMargin=0.5*inch, bottomMargin=0.5*inch)
styles = getSampleStyleSheet()
title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=20, spaceAfter=20)
heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, spaceAfter=10, spaceBefore=15)
body_style = ParagraphStyle('CustomBody', parent=styles['Normal'], fontSize=10, spaceAfter=8)

elements = []

# Title
elements.append(Paragraph('E-Commerce EDA Report', title_style))
elements.append(Paragraph(f'Dataset: 50,000 transactions | Generated from sandbox analysis', body_style))
elements.append(Spacer(1, 20))

# Key metrics
elements.append(Paragraph('Key Metrics', heading_style))
total_rev = df['total_amount'].sum()
metrics_data = [
    ['Metric', 'Value'],
    ['Total Revenue', f'${total_rev:,.2f}'],
    ['Total Transactions', f'{len(df):,}'],
    ['Unique Customers', f'{df["customer_id"].nunique():,}'],
    ['Average Order Value', f'${df["total_amount"].mean():,.2f}'],
    ['Average Rating', f'{df["rating"].mean():.2f} / 5.0'],
    ['Return Rate', f'{df["return_flag"].mean()*100:.1f}%'],
    ['Top Category', df.groupby("category")["total_amount"].sum().idxmax()],
    ['Top Channel', df["channel"].value_counts().index[0]],
]
t = Table(metrics_data, colWidths=[200, 250])
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
]))
elements.append(t)
elements.append(Spacer(1, 20))

# Revenue by category table
elements.append(Paragraph('Revenue by Category', heading_style))
cat_data = df.groupby('category').agg(
    revenue=('total_amount', 'sum'),
    orders=('transaction_id', 'count'),
    avg_order=('total_amount', 'mean'),
    avg_rating=('rating', 'mean'),
).sort_values('revenue', ascending=False)

table_data = [['Category', 'Revenue', 'Orders', 'Avg Order', 'Avg Rating']]
for cat, row in cat_data.iterrows():
    table_data.append([
        str(cat),
        f'${row["revenue"]:,.0f}',
        f'{int(row["orders"]):,}',
        f'${row["avg_order"]:.2f}',
        f'{row["avg_rating"]:.2f}',
    ])

t = Table(table_data, colWidths=[120, 90, 70, 80, 80])
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
elements.append(t)
elements.append(Spacer(1, 20))

# Embed charts if available
import os
for img_name in ['dashboard.png', 'correlation_analysis.png', 'segmentation.png']:
    img_path = f'/mnt/data/{img_name}'
    if os.path.exists(img_path):
        elements.append(Paragraph(img_name.replace('.png', '').replace('_', ' ').title(), heading_style))
        img = Image(img_path, width=6.5*inch, height=4*inch)
        elements.append(img)
        elements.append(Spacer(1, 10))

doc.build(elements)
print("PDF report saved: eda_report.pdf")
print(f"Report size: {os.path.getsize('/mnt/data/eda_report.pdf'):,} bytes")
"""
    result = mgr.execute(sid, code_pdf)
    assert isinstance(result, RunResult), f"Execute failed: {result}"
    assert result.exit_code == 0, f"PDF error:\n{result.stderr}"
    print(f"    Duration: {result.duration_ms}ms")
    print(f"    Output:\n{_indent(result.stdout)}")
    print(f"    Artifacts: {[a.filename for a in result.artifacts]}")

    # ── 8. List all artifacts ────────────────────────────────────
    print("\n[8] Listing all artifacts...")
    result = mgr.list_files(sid)
    assert isinstance(result, ListArtifactsResult), f"List failed: {result}"
    total_size = sum(a.size_bytes for a in result.artifacts)
    print(f"    Found {len(result.artifacts)} artifacts ({total_size:,} bytes total):")
    for a in sorted(result.artifacts, key=lambda x: x.filename):
        print(f"      {a.filename:30s} {a.size_bytes:>10,} bytes  ({a.mime_type})")

    # ── 9. Read back the PDF to verify ───────────────────────────
    print("\n[9] Reading PDF artifact to verify...")
    result = mgr.read_file(sid, "/mnt/data/eda_report.pdf")
    assert isinstance(result, ReadArtifactResult), f"Read failed: {result}"
    pdf_bytes = base64.b64decode(result.content_base64)
    assert pdf_bytes[:5] == b"%PDF-", "Not a valid PDF!"
    print(f"    Filename: {result.filename}")
    print(f"    Size: {result.size_bytes:,} bytes")
    print(f"    PDF header verified: OK")

    # ── 10. Cleanup ──────────────────────────────────────────────
    print("\n[10] Closing session...")
    close_result = mgr.close(sid)
    print(f"    Status: {close_result.status}")

    print("\n" + "=" * 70)
    print("ALL EDA TESTS PASSED")
    print("=" * 70)


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.strip().splitlines())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
