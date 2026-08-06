import os
from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://neondb_owner:npg_6uwnM4APrvZY@ep-lucky-cherry-aywu7dlr.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require",
)