from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
cur = conn.cursor()
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'scoring_options'
    ORDER BY ordinal_position
""")
print("scoring_options columns:", [r[0] for r in cur.fetchall()])

cur.execute("SELECT current_database(), current_schema()")
print("connected to:", cur.fetchone())
cur.close()
conn.close()