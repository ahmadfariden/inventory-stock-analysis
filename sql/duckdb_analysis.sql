-- ============================================================
-- DuckDB Analysis Pipeline: Stok Bahan Baku
-- ============================================================
-- Input : inventory_weekly_data.csv (hasil generate_inventory_data.py)
-- Output: folder powerbi_exports/ berisi 5 file CSV siap ditarik ke Power BI
--
-- Cara pakai via DuckDB CLI:
--   duckdb inventory.duckdb
--   .read duckdb_analysis.sql
--
-- Atau otomatis lewat: python run_pipeline.py
-- ============================================================

-- 1. STAGING: load & bersihkan data mentah, tambah kolom turunan
CREATE OR REPLACE TABLE stg_inventory AS
SELECT
    CAST(week_start_date AS DATE)              AS week_start_date,
    sku_id,
    sku_name,
    category,
    warehouse_id,
    supplier_id,
    beginning_stock,
    qty_received,
    qty_used,
    ending_stock,
    unit_cost,
    lead_time_days,
    min_order_qty,
    TRY_CAST(NULLIF(expiry_date, '') AS DATE)  AS expiry_date,
    ending_stock * unit_cost                   AS stock_value,
    CASE WHEN ending_stock = 0 THEN 1 ELSE 0 END AS is_stockout
FROM read_csv_auto('inventory_weekly_data.csv', header=True,
                    types={'expiry_date': 'VARCHAR'});

-- tanggal terakhir yang ada di data (dipakai sebagai "hari ini" simulasi)
CREATE OR REPLACE TABLE meta_last_date AS
SELECT MAX(week_start_date) AS last_date FROM stg_inventory;

-- ============================================================
-- 2. AGREGASI PER SKU (dasar untuk reorder point, EOQ, ABC)
-- ============================================================
CREATE OR REPLACE TABLE sku_agg AS
SELECT
    sku_id,
    ANY_VALUE(sku_name)         AS sku_name,
    ANY_VALUE(category)         AS category,
    ANY_VALUE(warehouse_id)     AS warehouse_id,
    ANY_VALUE(supplier_id)      AS supplier_id,
    ANY_VALUE(unit_cost)        AS unit_cost,
    AVG(qty_used)               AS avg_weekly_demand,
    STDDEV_SAMP(qty_used)       AS demand_std,
    AVG(lead_time_days)         AS lead_time_avg_days,
    STDDEV_SAMP(lead_time_days) AS lead_time_std_days,
    SUM(qty_used)               AS total_qty_used,
    SUM(qty_used * unit_cost)   AS total_value_used,
    SUM(is_stockout)            AS weeks_stockout_count,
    COUNT(*)                    AS weeks_recorded,
    AVG(ending_stock)           AS avg_stock_level
FROM stg_inventory
GROUP BY sku_id;

-- stok terkini (snapshot minggu terakhir) per SKU
CREATE OR REPLACE TABLE sku_current AS
SELECT s.sku_id, s.ending_stock AS current_stock
FROM stg_inventory s
INNER JOIN meta_last_date m ON s.week_start_date = m.last_date;

-- ============================================================
-- 3. SAFETY STOCK, REORDER POINT, EOQ
--    Asumsi: service level 95% (Z=1.65), biaya pesan Rp150.000/order,
--            biaya simpan = 20% dari unit_cost per tahun
-- ============================================================
CREATE OR REPLACE TABLE sku_summary AS
SELECT
    a.*,
    c.current_stock,
    (a.lead_time_avg_days / 7.0) AS lead_time_weeks,
    1.65 * COALESCE(a.demand_std, 0) * SQRT(a.lead_time_avg_days / 7.0) AS safety_stock,
    a.avg_weekly_demand * (a.lead_time_avg_days / 7.0)
        + 1.65 * COALESCE(a.demand_std, 0) * SQRT(a.lead_time_avg_days / 7.0) AS reorder_point,
    SQRT((2 * a.avg_weekly_demand * 52 * 150000) / NULLIF(a.unit_cost * 0.20, 0)) AS eoq,
    (a.total_qty_used / NULLIF(a.avg_stock_level, 0)) AS turnover_ratio,
    (c.current_stock / NULLIF(a.avg_weekly_demand / 7.0, 0)) AS days_of_stock_remaining
FROM sku_agg a
LEFT JOIN sku_current c ON a.sku_id = c.sku_id;

-- ============================================================
-- 4. ABC CLASSIFICATION (Pareto 80/15/5 berdasarkan nilai pemakaian)
-- ============================================================
CREATE OR REPLACE TABLE sku_abc AS
WITH ranked AS (
    SELECT
        sku_id,
        total_value_used,
        SUM(total_value_used) OVER () AS grand_total,
        SUM(total_value_used) OVER (
            ORDER BY total_value_used DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM sku_summary
)
SELECT
    sku_id,
    running_total / grand_total AS cum_pct_value,
    CASE
        WHEN running_total / grand_total <= 0.80 THEN 'A'
        WHEN running_total / grand_total <= 0.95 THEN 'B'
        ELSE 'C'
    END AS abc_class
FROM ranked;

-- gabungkan semua metrik + status stok + flag slow-mover
CREATE OR REPLACE TABLE sku_summary_final AS
SELECT
    s.*,
    b.abc_class,
    b.cum_pct_value,
    (s.current_stock < (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY avg_weekly_demand) FROM sku_summary)
        AND s.current_stock > s.reorder_point * 2)                    AS is_slow_mover_flag_raw,
    CASE
        WHEN s.avg_weekly_demand <= (SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY avg_weekly_demand) FROM sku_summary)
             AND s.current_stock > s.reorder_point * 2
        THEN TRUE ELSE FALSE
    END AS is_slow_mover,
    CASE
        WHEN s.current_stock < s.reorder_point THEN 'Understock'
        WHEN s.current_stock > s.reorder_point * 2.5 THEN 'Overstock'
        ELSE 'Optimal'
    END AS stock_status
FROM sku_summary s
LEFT JOIN sku_abc b ON s.sku_id = b.sku_id;

ALTER TABLE sku_summary_final DROP COLUMN is_slow_mover_flag_raw;

-- ============================================================
-- 5. SUPPLIER PERFORMANCE
-- ============================================================
CREATE OR REPLACE TABLE supplier_performance AS
SELECT
    supplier_id,
    COUNT(DISTINCT sku_id)      AS sku_count,
    AVG(lead_time_days)         AS avg_lead_time_days,
    STDDEV_SAMP(lead_time_days) AS lead_time_std_days,
    MAX(lead_time_days)         AS max_lead_time_days
FROM stg_inventory
GROUP BY supplier_id
ORDER BY avg_lead_time_days;

-- ============================================================
-- 6. EXPIRY RISK (hanya item perishable, snapshot minggu terakhir)
-- ============================================================
CREATE OR REPLACE TABLE expiry_risk AS
SELECT
    s.sku_id, s.sku_name, s.category, s.warehouse_id,
    s.ending_stock AS current_stock,
    s.expiry_date,
    DATE_DIFF('day', m.last_date, s.expiry_date) AS days_to_expiry,
    s.stock_value AS potential_loss_value,
    CASE
        WHEN DATE_DIFF('day', m.last_date, s.expiry_date) <= 0  THEN 'Expired'
        WHEN DATE_DIFF('day', m.last_date, s.expiry_date) <= 30 THEN '0-30 hari'
        WHEN DATE_DIFF('day', m.last_date, s.expiry_date) <= 60 THEN '31-60 hari'
        WHEN DATE_DIFF('day', m.last_date, s.expiry_date) <= 90 THEN '61-90 hari'
        ELSE '90+ hari'
    END AS expiry_bucket
FROM stg_inventory s
INNER JOIN meta_last_date m ON s.week_start_date = m.last_date
WHERE s.expiry_date IS NOT NULL AND s.ending_stock > 0;

-- ============================================================
-- 7. TREN MINGGUAN NASIONAL (untuk halaman Executive Overview)
-- ============================================================
CREATE OR REPLACE TABLE weekly_trend_national AS
SELECT
    week_start_date,
    SUM(qty_used)          AS total_qty_used,
    SUM(qty_received)      AS total_qty_received,
    SUM(stock_value)       AS total_stock_value,
    SUM(is_stockout)       AS stockout_sku_count,
    COUNT(DISTINCT sku_id) AS active_sku_count
FROM stg_inventory
GROUP BY week_start_date
ORDER BY week_start_date;

-- ============================================================
-- 8. EXPORT SEMUA HASIL KE CSV UNTUK POWER BI
-- ============================================================
COPY sku_summary_final       TO 'powerbi_exports/dim_sku_summary.csv'          (HEADER, DELIMITER ',');
COPY supplier_performance    TO 'powerbi_exports/dim_supplier_performance.csv' (HEADER, DELIMITER ',');
COPY expiry_risk             TO 'powerbi_exports/fct_expiry_risk.csv'          (HEADER, DELIMITER ',');
COPY weekly_trend_national   TO 'powerbi_exports/fct_weekly_trend_national.csv'(HEADER, DELIMITER ',');
COPY stg_inventory           TO 'powerbi_exports/fct_inventory_weekly.csv'     (HEADER, DELIMITER ',');
