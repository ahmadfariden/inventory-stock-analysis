"""
Generator Data Simulasi Stok Bahan Baku
=========================================
Membuat data mingguan stok bahan baku yang REALISTIS (bukan random murni),
lengkap dengan pola musiman, tren, SKU cepat/lambat bergerak, kadang stockout,
kadang overstock, expiry date untuk kategori perishable, dan variasi lead time
supplier — supaya saat diolah di DuckDB + Power BI, hasil analisisnya
(reorder point, EOQ, ABC analysis, forecast, dead stock, dsb) kelihatan natural.

Cara pakai:
    pip install pandas numpy
    python generate_inventory_data.py

Atur N_SKUS dan N_WEEKS di bawah untuk mengubah total jumlah baris.
Total baris = N_SKUS x N_WEEKS
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# KONFIGURASI — ubah sesuai kebutuhan
# ============================================================
SEED = 42
N_SKUS = 2500          # jumlah jenis bahan baku
N_WEEKS = 200          # jumlah minggu (200 minggu ~ 3.8 tahun)
START_DATE = datetime(2022, 1, 3)  # Senin pertama
OUTPUT_FILE = "inventory_weekly_data.csv"

np.random.seed(SEED)

# ============================================================
# 1. MASTER DATA KATEGORI & SUPPLIER
# ============================================================
CATEGORIES = {
    "Bahan Pangan":   {"perishable": True,  "shelf_life_days": 30,  "cost_range": (5_000, 50_000)},
    "Bahan Kimia":    {"perishable": True,  "shelf_life_days": 180, "cost_range": (20_000, 300_000)},
    "Kemasan":        {"perishable": False, "shelf_life_days": None, "cost_range": (500, 15_000)},
    "Tekstil":        {"perishable": False, "shelf_life_days": None, "cost_range": (10_000, 150_000)},
    "Logam":          {"perishable": False, "shelf_life_days": None, "cost_range": (30_000, 500_000)},
    "Elektronik":     {"perishable": False, "shelf_life_days": None, "cost_range": (15_000, 800_000)},
}
CAT_NAMES = list(CATEGORIES.keys())
CAT_SHORT = {"Bahan Pangan": "PGN", "Bahan Kimia": "KIM", "Kemasan": "KMS",
             "Tekstil": "TKS", "Logam": "LGM", "Elektronik": "ELK"}

N_SUPPLIERS = 40
supplier_ids = np.arange(1, N_SUPPLIERS + 1)

WAREHOUSES = ["WH-Jakarta", "WH-Surabaya", "WH-Bandung", "WH-Medan", "WH-Makassar"]
# tiap supplier punya "karakter": ada yang reliable (lead time stabil), ada yang tidak
supplier_base_lead_time = np.random.uniform(3, 21, N_SUPPLIERS)      # hari
supplier_reliability = np.random.uniform(0.5, 3.0, N_SUPPLIERS)      # std deviasi lead time (makin besar makin ga reliable

# ============================================================
# 2. BANGUN MASTER SKU (karakteristik tiap bahan baku)
# ============================================================
sku_category = np.random.choice(CAT_NAMES, size=N_SKUS, p=[0.20, 0.15, 0.20, 0.15, 0.15, 0.15])
sku_supplier = np.random.choice(supplier_ids, size=N_SKUS)
sku_warehouse = np.random.choice(WAREHOUSES, size=N_SKUS, p=[0.35, 0.20, 0.20, 0.15, 0.10])

# demand dasar: distribusi lognormal -> banyak SKU slow-mover, sedikit fast-mover (mirip Pareto/ABC asli)
base_demand = np.random.lognormal(mean=3.0, sigma=1.1, size=N_SKUS)   # unit/minggu
base_demand = np.clip(base_demand, 2, 2000)

# volatilitas demand (noise) sebagai persentase dari base_demand
demand_volatility = np.random.uniform(0.10, 0.45, N_SKUS)

# tren mingguan (sebagian naik, sebagian turun, sebagian datar) -> untuk simulasi produk yang mulai discontinue / growing
trend_pct_per_week = np.random.normal(0, 0.003, N_SKUS)

# amplitudo musiman (0 = tidak musiman sama sekali, 0.5 = sangat musiman)
seasonal_amplitude = np.random.uniform(0.0, 0.5, N_SKUS)
seasonal_phase = np.random.uniform(0, 2 * np.pi, N_SKUS)

# unit cost sesuai kategori
unit_cost = np.zeros(N_SKUS)
for i, cat in enumerate(sku_category):
    lo, hi = CATEGORIES[cat]["cost_range"]
    unit_cost[i] = np.random.uniform(lo, hi)

# lead time & min order qty per SKU (berdasarkan supplier-nya)
sup_idx = sku_supplier - 1
lead_time_mean = supplier_base_lead_time[sup_idx]
lead_time_std = supplier_reliability[sup_idx]

min_order_qty = np.round(base_demand * np.random.uniform(2, 6, N_SKUS)).astype(int)
min_order_qty = np.clip(min_order_qty, 10, None)

sku_ids = [f"{CAT_SHORT[sku_category[i]]}-{i+1:05d}" for i in range(N_SKUS)]
sku_names = [f"{sku_category[i]} Tipe {chr(65 + (i % 6))}-{i+1:04d}" for i in range(N_SKUS)]

# ============================================================
# 3. SIMULASI MINGGUAN (demand, stok, replenishment)
# ============================================================
weeks = np.arange(N_WEEKS)
week_dates = [START_DATE + timedelta(weeks=int(w)) for w in weeks]

# --- generate matrix demand (N_SKUS x N_WEEKS) dengan tren + musiman + noise ---
t = weeks.reshape(1, -1)  # (1, N_WEEKS)
trend_factor = (1 + trend_pct_per_week.reshape(-1, 1)) ** t
seasonal_factor = 1 + seasonal_amplitude.reshape(-1, 1) * np.sin(
    2 * np.pi * t / 52 + seasonal_phase.reshape(-1, 1)
)
noise = np.random.normal(1.0, 1.0, size=(N_SKUS, N_WEEKS)) * demand_volatility.reshape(-1, 1) + 1
noise = np.clip(noise, 0.1, None)

demand_matrix = base_demand.reshape(-1, 1) * trend_factor * seasonal_factor * noise
demand_matrix = np.clip(np.round(demand_matrix), 0, None)

# --- reorder point per SKU (dipakai untuk trigger replenishment saat simulasi) ---
lead_time_weeks = np.clip(np.round(lead_time_mean / 7), 1, 6).astype(int)
avg_weekly_demand = base_demand
reorder_point = avg_weekly_demand * lead_time_weeks * 1.5  # safety factor 1.5x

# --- simulasi sequential stock (beginning, in, out, ending) ---
stock = reorder_point * 1.3  # stok awal
incoming = np.zeros((N_SKUS, N_WEEKS + 8))  # buffer untuk order yang akan datang

records = {
    "week_start_date": [], "sku_id": [], "sku_name": [], "category": [],
    "warehouse_id": [], "supplier_id": [], "beginning_stock": [], "qty_received": [],
    "qty_used": [], "ending_stock": [], "unit_cost": [], "lead_time_days": [],
    "min_order_qty": [], "expiry_date": [],
}

for w in range(N_WEEKS):
    beginning_stock = stock.copy()
    qty_received = incoming[:, w].copy()

    demand = demand_matrix[:, w]
    available = beginning_stock + qty_received
    qty_used = np.minimum(demand, available)          # tidak bisa pakai lebih dari yang tersedia (stockout tersimulasi)
    ending_stock = available - qty_used

    # trigger replenishment kalau ending_stock di bawah reorder point
    need_reorder = ending_stock < reorder_point
    order_qty = np.maximum(min_order_qty, reorder_point * 1.8 - ending_stock)
    order_qty = np.where(need_reorder, order_qty, 0)

    # lead time actual minggu ini (dengan noise supplier reliability)
    actual_lead_time_days = np.clip(
        np.random.normal(lead_time_mean, lead_time_std), 1, 45
    )
    arrival_week = w + np.clip(np.round(actual_lead_time_days / 7), 1, 8).astype(int)
    for idx in np.where(need_reorder)[0]:
        aw = arrival_week[idx]
        if aw < incoming.shape[1]:
            incoming[idx, aw] += order_qty[idx]

    # simpan record minggu ini
    records["week_start_date"].extend([week_dates[w]] * N_SKUS)
    records["sku_id"].extend(sku_ids)
    records["sku_name"].extend(sku_names)
    records["category"].extend(sku_category)
    records["warehouse_id"].extend(sku_warehouse)
    records["supplier_id"].extend(sku_supplier)
    records["beginning_stock"].extend(np.round(beginning_stock, 1))
    records["qty_received"].extend(np.round(qty_received, 1))
    records["qty_used"].extend(np.round(qty_used, 1))
    records["ending_stock"].extend(np.round(ending_stock, 1))
    records["unit_cost"].extend(np.round(unit_cost, 0))
    records["lead_time_days"].extend(np.round(actual_lead_time_days, 1))
    records["min_order_qty"].extend(min_order_qty)

    expiry = []
    for i, cat in enumerate(sku_category):
        shelf = CATEGORIES[cat]["shelf_life_days"]
        if shelf is not None and ending_stock[i] > 0:
            expiry.append((week_dates[w] + timedelta(days=int(shelf))).date().isoformat())
        else:
            expiry.append("")
    records["expiry_date"].extend(expiry)

    stock = ending_stock  # lanjut ke minggu berikutnya

# ============================================================
# 4. SIMPAN KE CSV
# ============================================================
df = pd.DataFrame(records)
df["week_start_date"] = pd.to_datetime(df["week_start_date"]).dt.date
df.to_csv(OUTPUT_FILE, index=False)

print(f"Selesai! {len(df):,} baris x {df.shape[1]} kolom disimpan ke '{OUTPUT_FILE}'")
print(df.head(10))
