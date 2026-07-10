# Methodology

This document explains the data pipeline, formulas, and business assumptions behind the Inventory Stock Analysis dashboard — the written companion to the "Methodology" page built into the Power BI dashboard itself.

---

## 1. Data Pipeline

```
generate_inventory_data.py
        ↓
inventory_weekly_data.csv   (500,000 rows × 14 columns)
        ↓
duckdb_analysis.sql / run_pipeline.py
        ↓
powerbi_exports/   (5 pre-aggregated CSV tables)
        ↓
Power BI   (9-page dashboard)
```

**Why DuckDB instead of doing everything in Power BI/DAX?**
At 500,000 rows, recalculating reorder points, EOQ, and ABC classification live with DAX on every visual refresh is slow and hard to debug. DuckDB processes the entire pipeline — staging, aggregation, business-rule calculation, and export — in about 3 seconds. Power BI is then used purely for what it's best at: interactive visualization, not heavy computation.

---

## 2. Data Generation

The raw dataset is synthetic, generated with `generate_inventory_data.py`, simulating **2,500 SKUs across 200 weeks** (~3.8 years) of weekly inventory transactions across 6 categories, 5 warehouses, and 40 suppliers.

Rather than pure random generation, the data is built with intentional structure so the resulting analysis reflects realistic inventory dynamics:

- **Demand distribution:** lognormal, producing a small number of fast-moving SKUs and a long tail of slow-movers — mirroring the Pareto-like concentration seen in real inventory systems.
- **Seasonality:** each SKU has an independent sine-wave seasonal pattern (amplitude and phase vary per SKU).
- **Trend:** each SKU has a small independent weekly growth/decline trend.
- **Sequential simulation:** stock levels are simulated week-by-week (beginning stock → receive → consume → ending stock → reorder trigger), not generated independently per row. This means stockouts and overstock emerge naturally from the replenishment logic rather than being randomly assigned.
- **Supplier variability:** each supplier has its own baseline lead time and reliability (lead-time standard deviation), which flows into per-SKU lead time noise.
- **Expiry:** only two categories (Food, Chemical) carry an `expiry_date`, based on a fixed shelf life per category.

---

## 3. Core Formulas

All calculated in SQL (DuckDB), not in DAX.

### Safety Stock
```
Safety Stock = Z × σ(demand) × √(lead time in weeks)
```
Where `Z` is the z-score for the target service level, and `σ(demand)` is the standard deviation of weekly demand for that SKU.

### Reorder Point
```
Reorder Point = (avg weekly demand × lead time in weeks) + Safety Stock
```
The stock level at which a new order should be triggered — covers expected demand during lead time, plus a buffer for demand variability.

### Economic Order Quantity (EOQ)
```
EOQ = √(2 × annual demand × ordering cost / holding cost per unit)
```
The order quantity that minimizes total cost (ordering cost + holding cost).

### ABC Classification
SKUs are ranked by total value consumed (`qty_used × unit_cost`), then classified by cumulative contribution to total value:
- **Class A:** top SKUs contributing up to 80% of cumulative value
- **Class B:** next tier, up to 95% of cumulative value
- **Class C:** remaining SKUs (the long tail)

### Stock Coverage Ratio (dashboard-only metric)
```
Stock Coverage Ratio = current_stock / reorder_point
```
Used in the Replenishment Planner to color-code urgency — a ratio well below 1.0 indicates a SKU is significantly below its reorder point, regardless of the SKU's absolute stock volume. This avoids a common visualization pitfall where high-volume categories (e.g., electronics) appear "safer" than low-volume categories purely because their raw stock numbers are larger.

---

## 4. Business Assumptions

| Assumption | Value | Rationale |
|---|---|---|
| Service level | 95% (Z = 1.65) | Standard target service level for non-critical raw materials |
| Ordering cost | Rp150,000 / order | Fixed administrative cost assumption per purchase order |
| Holding cost | 20% of unit cost / year | Common industry rule-of-thumb for holding cost as % of inventory value |

These are illustrative assumptions for a portfolio project — a production deployment would derive these from actual company financial data (procurement overhead, warehousing cost, capital cost of carrying inventory).

---

## 5. Known Limitations

- **Synthetic data.** This is not real company data — it was generated specifically to demonstrate the analytical pipeline and produce data with realistic statistical properties (fast/slow movers, seasonality, occasional stockouts).
- **Expiry risk uses a single snapshot.** `days_to_expiry` is calculated from the most recent week only. Since shelf life is a fixed constant per category in this simulation, all SKUs within the same category share the same `days_to_expiry` at any given snapshot — a real dataset would show variation based on actual receipt dates per batch.
- **Demand forecasting is simplified.** The Demand Trend Detail page uses observed weekly trends and a moving-average view rather than a formal time-series model (ARIMA, Prophet, etc.). A natural extension of this project would be adding a proper forecasting layer.
- **EOQ assumptions are fixed constants** (ordering cost, holding cost %) applied uniformly across all SKUs and categories, rather than being category- or supplier-specific.

---

## 6. Suggested Extensions

- Replace the moving-average demand view with a proper forecasting model (Prophet, ARIMA) and add a forecast accuracy metric (MAPE) to the dashboard.
- Make ordering cost and holding cost category-specific rather than global constants.
- Add a supplier scorecard combining lead time reliability with fill rate / on-time delivery rate.
- Extend the expiry simulation to track batch-level receipt dates rather than a single category-wide shelf life.
