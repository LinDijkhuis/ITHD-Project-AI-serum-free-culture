"""Apply sql/schema.sql to the database configured in .env"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    url = os.environ["DATABASE_URL"]
    schema = open("sql/schema.sql").read()

    # Strip ?sslmode=require from URL — asyncpg needs ssl passed separately
    url = url.split("?")[0]
    is_local = any(h in url for h in ("localhost", "127.0.0.1"))
    ssl_setting = None if is_local else "require"
    conn = await asyncpg.connect(url, ssl=ssl_setting, timeout=30 if is_local else 120)
    try:
        await conn.execute(schema)
        print("Schema applied successfully.")
    finally:
        await conn.close()

asyncio.run(main())
