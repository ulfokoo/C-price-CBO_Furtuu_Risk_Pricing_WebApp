from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    ALTER TABLE ngo_support_items
    ADD COLUMN IF NOT EXISTS max_price_impact_pct DOUBLE PRECISION NOT NULL DEFAULT 0;
""")
print("Column added.")
cur.close()
conn.close()