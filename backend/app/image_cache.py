"""Persistent cache for product image lookups."""

import sqlite3
from pathlib import Path

CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.sqlite3"


def _connection() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CACHE_DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS product_image_cache (
            cache_key TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            image_url TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'openfoodfacts',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def get_cached_image_url(cache_key: str) -> str | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT image_url FROM product_image_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    return row[0] or None


def store_cached_image_url(cache_key: str, query: str, image_url: str | None, source: str = "openfoodfacts") -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO product_image_cache (cache_key, query, image_url, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                query = excluded.query,
                image_url = excluded.image_url,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (cache_key, query, image_url or "", source),
        )