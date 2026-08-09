from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    ALTER TABLE ngo_support_items
    ADD COLUMN IF NOT EXISTS selected_tier_id INTEGER REFERENCES ngo_support_tiers(id);
""")
print("Column added.")
cur.close()
conn.close()