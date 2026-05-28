import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run():
    sql = open('sql/schema.sql').read()
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute(sql)
    await conn.close()
    print('Schema created successfully')

asyncio.run(run())
