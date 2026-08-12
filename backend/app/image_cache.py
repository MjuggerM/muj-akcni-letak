"""Persistent cache for product image lookups.

Three cached outcomes, not two:
  - a real image_url            -> cached indefinitely (kept until a food
                                    database change makes the row stale, at
                                    which point re-scraping is cheap anyway)
  - a confirmed "no image"      -> cached for MISS_TTL_SECONDS. Open Food
                                    Facts genuinely not having a product is
                                    common and stable; re-asking every render
                                    just to get an empty result again is pure
                                    waste.
  - a temporary failure (429/5xx/timeout) -> cached for FAILURE_TTL_SECONDS
                                    only. This is NOT the same as "no image":
                                    treating a rate limit as a permanent miss
                                    would mean a real image is never fetched
                                    again until the whole cache is cleared.

Without this split, a 429 from Open Food Facts used to be indistinguishable
from "no image", and neither was cached at all - so every re-render or page
reload re-issued the exact same request that just got rate-limited,
compounding the problem instead of backing off from it.
"""

import sqlite3
import time
from pathlib import Path

CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.sqlite3"

MISS_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days - "this product has no photo in OFF"
FAILURE_TTL_SECONDS = 90  # 1.5 minutes - "OFF rate-limited/errored us, retry soon"


def _connection() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CACHE_DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS product_image_cache (
            cache_key TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            image_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'found',
            source TEXT NOT NULL DEFAULT 'openfoodfacts',
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    # Older DBs (pre-TTL) declared `updated_at TEXT ... CURRENT_TIMESTAMP`.
    # That's not just old data - it's an old *column type* (TEXT affinity),
    # which silently coerces even a freshly-written time.time() float back
    # into a text string on every INSERT. So ALTER TABLE ADD COLUMN alone
    # does not fix this: the column itself has to be rebuilt as REAL, or
    # every future write keeps re-corrupting it. SQLite can't ALTER a
    # column's type directly, so we rebuild the table when this old shape
    # is detected. This only ever touches cache data - losing it just means
    # those entries get re-fetched once.
    columns = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(product_image_cache)")}
    needs_rebuild = columns.get("updated_at") == "TEXT"
    if needs_rebuild:
        connection.execute("ALTER TABLE product_image_cache RENAME TO product_image_cache_old")
        connection.execute(
            """
            CREATE TABLE product_image_cache (
                cache_key TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                image_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'found',
                source TEXT NOT NULL DEFAULT 'openfoodfacts',
                updated_at REAL NOT NULL DEFAULT 0
            )
            """
        )
        # Old rows have no usable numeric timestamp - rather than invent one
        # (which could wrongly look "fresh" or "expired"), they're dropped;
        # the next request for that product just re-fetches for real.
        connection.execute("DROP TABLE product_image_cache_old")
        connection.commit()
    elif "status" not in columns:
        # status-only upgrade path (updated_at was already REAL/unset).
        connection.execute("ALTER TABLE product_image_cache ADD COLUMN status TEXT NOT NULL DEFAULT 'found'")
        connection.commit()

    return connection


def get_cache_entry(cache_key: str) -> dict | None:
    """Return {'image_url': str|None, 'status': 'found'|'miss'|'failure'} if
    a still-valid cache entry exists, else None (meaning: go fetch fresh)."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT image_url, status, updated_at FROM product_image_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None

    image_url, status, updated_at = row
    ttl = FAILURE_TTL_SECONDS if status == "failure" else MISS_TTL_SECONDS
    if status != "found" and time.time() - updated_at > ttl:
        return None  # expired - treat as no cache entry, caller will re-fetch

    return {"image_url": image_url or None, "status": status}


def store_cached_image_url(
    cache_key: str,
    query: str,
    image_url: str | None,
    source: str = "openfoodfacts",
    status: str = "found",
) -> None:
    """status: 'found' (has image_url), 'miss' (confirmed no image),
    or 'failure' (rate-limited/errored - retry soon, don't treat as final)."""
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO product_image_cache (cache_key, query, image_url, status, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                query = excluded.query,
                image_url = excluded.image_url,
                status = excluded.status,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (cache_key, query, image_url or "", status, source, time.time()),
        )