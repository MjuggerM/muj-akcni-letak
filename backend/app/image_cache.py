"""Persistent cache for product image lookups."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("akcni_letak.cache")

CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.sqlite3"


def _connection() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CACHE_DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS product_image_cache (
            cache_key TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            image_url TEXT NOT NULL,
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
    """Vrací platnou URL z databáze. Jakékoliv prázdné nebo chybějící záznamy ignoruje."""
    try:
        with _connection() as connection:
            row = connection.execute(
                "SELECT image_url FROM product_image_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        # Pokud máme záznam A ZÁROVEŇ není prázdný, vrátíme ho
        if row and row[0]:
            logger.info(f"⚡ [BE Cache HIT] Našel jsem platnou URL pro '{cache_key}'")
            return row[0]

        logger.info(f"🍃 [BE Cache MISS] Klíč '{cache_key}' nemá uložený platný obrázek.")
        return None

    except Exception as exc:
        logger.error(f"❌ [BE Cache Error] Chyba při čtení z SQLite: {exc}")
        return None


def store_cached_image_url(cache_key: str, query: str, image_url: str | None, source: str = "openfoodfacts") -> None:
    """Ukládá pouze platné nalezené obrázky. Neúspěchy (None/prázdné) se do databáze už NEUKLÁDAJÍ."""
    if not image_url:
        return  # Zabrání permanentnímu zablokování (Negative Cache)

    logger.info(f"💾 [BE Cache STORE] Zapisuji platný obrázek pro '{cache_key}'")
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
                (cache_key, query, image_url, source),
            )
            connection.commit()
    except Exception as exc:
        logger.error(f"❌ [BE Cache Error] Chyba při zápisu do SQLite: {exc}")