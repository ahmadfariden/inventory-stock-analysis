"""
Runner Pipeline DuckDB — Analisis Stok Bahan Baku
====================================================
Menjalankan seluruh query di duckdb_analysis.sql secara otomatis:
staging -> reorder point/EOQ -> ABC classification -> supplier performance
-> expiry risk -> export CSV siap ditarik ke Power BI.

Cara pakai:
    pip install duckdb
    python run_pipeline.py

Pastikan inventory_weekly_data.csv ada di folder yang sama.
Hasil akan muncul di folder ./powerbi_exports/
"""

import duckdb
import os
import time

SQL_FILE = "duckdb_analysis.sql"
DB_FILE = "inventory.duckdb"
OUTPUT_DIR = "powerbi_exports"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Menghubungkan ke DuckDB...")
con = duckdb.connect(DB_FILE)

with open(SQL_FILE, "r", encoding="utf-8") as f:
    raw_lines = f.readlines()

# buang semua baris komentar dulu, baru split per statement
code_only = "\n".join(line for line in raw_lines if not line.strip().startswith("--"))
statements = [s.strip() for s in code_only.split(";") if s.strip()]

start = time.time()
for i, stmt in enumerate(statements, 1):
    con.execute(stmt)
    print(f"  [{i}/{len(statements)}] OK")

elapsed = time.time() - start
print(f"\nSelesai dalam {elapsed:.1f} detik.")

# ringkasan cepat buat verifikasi
print("\n=== Ringkasan hasil ===")
print(con.execute("SELECT abc_class, COUNT(*) AS jumlah_sku, SUM(total_value_used) AS total_nilai "
                   "FROM sku_summary_final GROUP BY abc_class ORDER BY abc_class").df())
print()
print(con.execute("SELECT stock_status, COUNT(*) AS jumlah_sku FROM sku_summary_final "
                   "GROUP BY stock_status").df())
print()
print(f"File CSV hasil olahan tersimpan di folder: ./{OUTPUT_DIR}/")
for fname in os.listdir(OUTPUT_DIR):
    size_kb = os.path.getsize(os.path.join(OUTPUT_DIR, fname)) / 1024
    print(f"  - {fname} ({size_kb:,.0f} KB)")

con.close()
