from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()

cur.execute("DROP SCHEMA public CASCADE;")
cur.execute("CREATE SCHEMA public;")
print("Schema reset: all tables removed.")

cur.close()
conn.close()