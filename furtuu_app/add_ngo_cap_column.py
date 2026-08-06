from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    ALTER TABLE pricing_inputs
    ADD COLUMN IF NOT EXISTS ngo_max_price_impact_pct DOUBLE PRECISION NOT NULL DEFAULT 0.05;
""")
print("Column added.")
cur.close()
conn.close()