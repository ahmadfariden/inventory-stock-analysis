# 📦 Inventory Stock Analysis — DuckDB + Power BI

End-to-end inventory analytics pipeline simulating raw material stock management for a manufacturing company — from raw transactional data to an actionable 9-page Power BI dashboard, built with **Python, DuckDB (SQL), and Power BI**.

The goal: help a company avoid two costly mistakes — **stockouts** (running out of critical materials) and **overstock** (tying up cash in materials that sit unused) — by calculating reorder points, safety stock, EOQ, ABC classification, and expiry risk at scale.

> **Note on the data:** this project uses a synthetically generated dataset (not real company data), built to mimic realistic inventory patterns — seasonality, trend, fast/slow-moving SKUs, occasional stockouts, and supplier variability. See [Methodology & Assumptions](#-methodology--assumptions) below for details on how it was generated.

---

## 🧱 Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Data generation | Python (pandas, numpy) | Simulate 500,000 rows of realistic weekly inventory transactions |
| Data processing | DuckDB (SQL) | Cleaning, aggregation, and business-metric calculation at scale (~3 seconds for 500K rows) |
| Visualization | Power BI | 9-page interactive dashboard |

---

## 🏗️ Architecture

```
generate_inventory_data.py
        ↓
inventory_weekly_data.csv   (500,000 rows × 14 columns)
        ↓
duckdb_analysis.sql / run_pipeline.py   (DuckDB: cleaning, reorder point, EOQ, ABC classification)
        ↓
powerbi_exports/   (5 pre-aggregated CSV tables)
        ↓
Power BI   (9-page interactive dashboard)
```

Heavy computation (reorder point, safety stock, EOQ, ABC Pareto classification, expiry aging) is done **in DuckDB before the data ever touches Power BI** — Power BI is used purely for visualization, not for recalculating business logic with DAX on 500K rows.

---

## 📊 Dataset

**Scale:** 2,500 SKUs × 200 weeks (~3.8 years, weekly snapshots) = **500,000 rows × 14 columns**

| Column | Description |
|---|---|
| `week_start_date` | Week of the snapshot |
| `sku_id`, `sku_name` | SKU identifier and name |
| `category` | 6 raw material categories (Food, Chemical, Packaging, Textile, Metal, Electronics) |
| `warehouse_id` | 1 of 5 warehouse locations |
| `supplier_id` | 1 of 40 suppliers |
| `beginning_stock`, `qty_received`, `qty_used`, `ending_stock` | Weekly stock movement |
| `unit_cost` | Cost per unit (category-dependent range) |
| `lead_time_days` | Supplier delivery lead time (with weekly noise) |
| `min_order_qty` | Minimum order quantity per SKU |
| `expiry_date` | Only populated for perishable categories (Food, Chemical) |

The data is generated with intentional patterns rather than pure randomness — seasonality (sine wave per SKU), individual demand trends, lognormal demand distribution (a few fast-movers, many slow-movers — mirroring real Pareto-like inventory behavior), and a sequential week-by-week stock simulation (so stockouts and overstock emerge naturally from the replenishment logic, not from random draws).

---

## 📈 Dashboard — 9 Pages

### 1. Executive Overview
High-level KPIs: total active SKUs, inventory value, % understocked, weekly usage vs receipt trend, and stockout trend over time.

![Executive Overview](dashboard/screenshots/01_Executive_Overview.png)

### 2. Stock Health Monitor
Per-SKU stock status (Understock / Optimal / Overstock) against reorder point, with a days-of-stock-remaining breakdown.

![Stock Health Monitor](dashboard/screenshots/02_Stock_Health_Monitor.png)

### 3. ABC Analysis
Pareto chart and classification of SKUs into A/B/C tiers based on cumulative value contribution.

![ABC Analysis](dashboard/screenshots/03_ABC_Analysis.png)

### 4. Replenishment Planner
Actionable reorder recommendations — which SKUs need ordering, how much (EOQ), and how urgently.

![Replenishment Planner](dashboard/screenshots/04_Replenishment_Planner.png)

### 5. Slow-Moving & Dead Stock
Identifies capital tied up in low-turnover inventory — the "money sitting idle" that the whole analysis is meant to reduce.

![Slow-Moving & Dead Stock](dashboard/screenshots/05_Slow-Moving_Dead_Stock.png)

### 6. Waste & Expiry Tracking
Aging analysis for perishable categories, with potential financial loss from expiring stock.

![Waste & Expiry Tracking](dashboard/screenshots/06_Waste_Expiry_Tracking.png)

### 7. Supplier Performance
Lead time ranking and delivery consistency (reliability) per supplier.

![Supplier Performance](dashboard/screenshots/07_Ranking_Lead_Time_Supplier.png)

### 8. Demand Trend Detail
Interactive SKU-level usage trends and a category × month usage heatmap.

![Demand Trend Detail](dashboard/screenshots/08_Demand_Trend_Detail.png)

### 9. Methodology
Data pipeline diagram, formulas used, business assumptions, and known limitations — built directly into the dashboard so it's self-contained.

![Methodology](dashboard/screenshots/09_Methodology.png)

---

## 🧮 Methodology & Assumptions

**Formulas used** (calculated in DuckDB, not DAX):

```
Safety Stock    = Z × σ(demand) × √(lead time in weeks)
Reorder Point   = (avg weekly demand × lead time in weeks) + Safety Stock
EOQ             = √(2 × annual demand × ordering cost / holding cost per unit)
ABC Class       = Pareto classification (80/15/5) by cumulative value contribution
```

**Business assumptions:**
- Service level: 95% (Z = 1.65)
- Ordering cost: Rp150,000 per order
- Holding cost: 20% of unit cost per year

**Known limitations:**
- This is simulated data, not real company data — built for portfolio demonstration purposes.
- Expiry risk is calculated from a single latest-week snapshot; since shelf life is constant per category in this simulation, `days_to_expiry` is uniform within a category at any given point in time.
- The demand trend page uses a simple moving average rather than a formal time-series forecasting model (e.g., ARIMA, Prophet) — a natural next step for extending this project.

---

## 🔑 Key Findings

- **473 SKUs (18.9%)** fall into ABC Class A, contributing roughly 80% of total inventory value — confirming a Pareto-like concentration even with intentionally moderate (not extreme) skew in the simulated data.
- **945 SKUs (37.8%)** are currently understocked, with **532 SKUs** classified as urgent (less than 7 days of stock remaining).
- Approximately **Rp2 billion** is tied up in slow-moving/dead stock — capital that could be redeployed.
- **Rp10.55 billion** in potential loss identified from near-expiry perishable inventory.

---

## 🚀 How to Reproduce

```bash
# 1. Install dependencies
pip install pandas numpy duckdb

# 2. Generate the raw simulated dataset (500,000 rows)
python scripts/generate_inventory_data.py

# 3. Run the DuckDB pipeline (cleaning, reorder point, EOQ, ABC classification)
python scripts/run_pipeline.py

# 4. Open Power BI Desktop → Get Data → Folder → point to powerbi_exports/
#    Build relationships on sku_id / supplier_id / week_start_date in Model View
```

---

## 📁 Repository Structure

```
inventory-stock-analysis/
├── dashboard/
│   └── screenshots/          # 9 dashboard page screenshots
├── sql/
│   └── duckdb_analysis.sql   # Full DuckDB transformation pipeline
├── scripts/
│   ├── generate_inventory_data.py
│   └── run_pipeline.py
├── docs/
│   └── methodology.md        # Written version of formulas & assumptions
└── README.md
```

---

## 👤 Author

Ahmad Farid

Email: ahmad.fariden@gmail.com
LinkedIn: linkedin.com/in/ahmadfariden
GitHub: github.com/ahmadfariden