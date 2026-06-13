from collections.abc import Awaitable, Callable
import os

from fastapi import APIRouter, Depends

DatabaseProbe = Callable[[], Awaitable[bool]]

router = APIRouter()


async def database_is_reachable() -> bool:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False

    try:
        import psycopg
    except ModuleNotFoundError:
        return False

    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
        return True
    except Exception:
        return False


def get_database_probe() -> DatabaseProbe:
    return database_is_reachable


@router.get("/health")
async def health(database_probe: DatabaseProbe = Depends(get_database_probe)):
    database_ok = await database_probe()

    return {
        "status": "ok" if database_ok else "degraded",
        "service": "backend",
        "database": "ok" if database_ok else "unavailable",
    }
