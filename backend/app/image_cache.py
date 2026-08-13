"""Persistent cache for product image lookups."""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import IMAGE_NEGATIVE_CACHE_TTL_DAYS

logger = logging.getLogger("akcni_letak.cache")

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


def clear_empty_negative_cache() -> None:
    """Smaže z databáze staré prázdné záznamy, aby se mohly obrázky znovu načíst."""
    try:
        with _connection() as conn:
            conn.execute("DELETE FROM product_image_cache WHERE image_url = '' OR image_url IS NULL")
            conn.commit()
            logger.info("🧹 [BE Cache Reset] Vyčištěny staré prázdné záznamy z databáze keše.")
    except Exception as exc:
        logger.error(f"❌ [BE Cache Reset Error]: {exc}")


def get_cached_image_url(cache_key: str) -> str | None:
    """
    Look up a previously cached image lookup.

    Returns:
      - None  -> this key has never been looked up (caller should query the API)
      - ""    -> looked up before, confirmed NO image, and that result is still fresh
      - a URL -> a previously found image
    """
    try:
        with _connection() as connection:
            row = connection.execute(
                "SELECT image_url, updated_at FROM product_image_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        if row is None:
            logger.info(f"🍃 [BE Cache MISS] Klíč '{cache_key}' v databázi neexistuje.")
            return None

        image_url, updated_at = row
        if image_url:
            logger.info(f"⚡ [BE Cache HIT] Našel jsem platnou URL pro '{cache_key}' -> '{image_url}'")
            return image_url

        try:
            cached_at = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

        if datetime.now(timezone.utc) - cached_at > NEGATIVE_CACHE_TTL:
            logger.info(f"⏳ [BE Cache STALE] Negativní záznam pro '{cache_key}' vypršel.")
            return None

        logger.info(f"🛡️ [BE Cache FRESH NEGATIVE] Potvrzeno 'BEZ OBRÁZKU' pro '{cache_key}'. OFF nevolám.")
        return ""

    except Exception as exc:
        logger.error(f"❌ [BE Cache Error] Chyba při čtení z SQLite: {exc}")
        return None


def store_cached_image_url(cache_key: str, query: str, image_url: str | None, source: str = "openfoodfacts") -> None:
    saved_value = image_url or ""
    logger.info(f"💾 [BE Cache STORE] Zapisuji do SQLite klíč: '{cache_key}' -> '{saved_value or 'EMPTY'}'")
    try:
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
                (cache_key, query, saved_value, source),
            )
            connection.commit()
    except Exception as exc:
        logger.error(f"❌ [BE Cache Error] Chyba při zápisu do SQLite: {exc}")