from database import DATABASE_URL
import psycopg

conn = psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT conname, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'users'::regclass AND contype = 'c'
""")
print("Current constraints:", cur.fetchall())

cur.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;')
cur.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'vp', 'director', 'manager', 'staff', 'user'));")
print("Fixed: users_role_check now allows 'admin' and 'user'.")

cur.close()
conn.close()