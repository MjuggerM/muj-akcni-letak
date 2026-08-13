"""Persistent cache for product image lookups."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import IMAGE_NEGATIVE_CACHE_TTL_DAYS

CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.sqlite3"

NEGATIVE_CACHE_TTL = timedelta(days=IMAGE_NEGATIVE_CACHE_TTL_DAYS)


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
    """
    Look up a previously cached image lookup.

    Returns:
      - None  -> this key has never been looked up (caller should query the API)
      - ""    -> looked up before, confirmed NO image, and that result is
                 still fresh (caller should NOT query the API again)
      - a URL -> a previously found image

    IMPORTANT: the previous version of this function collapsed "" and None
    into the same thing (`row[0] or None`), which meant a confirmed "no
    image" result was indistinguishable from "never checked" - so every
    product Open Food Facts genuinely has no photo for got re-queried on
    every single request, forever. That's the main reason this app kept
    re-hitting (and getting rate-limited by) Open Food Facts. This version
    keeps "" and None distinct so a genuine negative result actually stays
    cached, while a *stale* negative (older than IMAGE_NEGATIVE_CACHE_TTL_DAYS)
    is treated as unchecked again, so products get retried occasionally in
    case Open Food Facts' data has grown since.
    """
    with _connection() as connection:
        row = connection.execute(
            "SELECT image_url, updated_at FROM product_image_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()

    if row is None:
        return None

    image_url, updated_at = row
    if image_url:
        return image_url

    try:
        cached_at = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
    except ValueError:
        # Unexpected timestamp format - treat as stale rather than fail.
        return None

    if datetime.now(timezone.utc) - cached_at > NEGATIVE_CACHE_TTL:
        return None

    return ""


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