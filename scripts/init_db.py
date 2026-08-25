import asyncio
from urllib.parse import unquote, urlparse

import asyncpg

from app.core.config import settings


async def main() -> None:
    parsed = urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    database = parsed.path.lstrip("/")
    connection = await asyncpg.connect(
        user=parsed.username,
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)",
            database,
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{database}"')
            print(f"Created database: {database}")
        else:
            print(f"Database already exists: {database}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
