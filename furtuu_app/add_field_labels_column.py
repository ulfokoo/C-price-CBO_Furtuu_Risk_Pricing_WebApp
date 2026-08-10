from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    ALTER TABLE products
    ADD COLUMN IF NOT EXISTS field_labels_json TEXT NOT NULL DEFAULT '{}';
""")
print("Column added.")
cur.close()
conn.close()