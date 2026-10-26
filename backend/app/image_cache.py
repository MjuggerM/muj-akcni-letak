"""Persistent cache for product image lookups.

Každý klíč je v jednom ze TŘÍ stavů a ty se nesmí slít dohromady:

    None  -> nevíme (nikdy nehledáno / záznam je zastaralý / zapsal ho jiný algoritmus)
    ""    -> VÍME, že fotka neexistuje (OFF odpověděl a nic odpovídajícího nemá)
    "http..." -> fotka existuje

Slití "nevíme" a "víme, že není" (dřív `row[0] or None`, pak úplné zrušení negativní cache)
vždycky skončilo stejně: buď se každý produkt bez fotky dotazoval znovu při každém requestu,
nebo se dočasná chyba (429, výpadek) uložila jako "fotka neexistuje".
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import IMAGE_MATCH_VERSION, IMAGE_NEGATIVE_CACHE_TTL_DAYS

logger = logging.getLogger("akcni_letak.cache")

CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "image_cache.sqlite3"

NEGATIVE_CACHE_TTL = timedelta(days=IMAGE_NEGATIVE_CACHE_TTL_DAYS)

# Zapisuje se do sloupce `source`. Řádky s jinou hodnotou (starší algoritmus párování, nebo
# řádky z doby, kdy sloupec obsahoval jen "openfoodfacts") se při čtení ignorují - ty staré
# obsahují i špatně spárované fotky (zelenina u koření) a nesmí zůstat v cache napořád.
CURRENT_SOURCE = f"openfoodfacts:v{IMAGE_MATCH_VERSION}"


def _connect() -> sqlite3.Connection:
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
    """Vrací None (nevíme), "" (potvrzeně bez fotky, ještě platí) nebo URL fotky."""
    try:
        with closing(_connect()) as connection:
            row = connection.execute(
                "SELECT image_url, updated_at, source FROM product_image_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
    except sqlite3.Error:
        logger.exception("❌ [IMG cache] čtení z SQLite selhalo")
        return None

    if row is None:
        logger.debug("🍃 [IMG cache MISS] %s", cache_key)
        return None

    image_url, updated_at, source = row
    if source != CURRENT_SOURCE:
        logger.debug("♻️ [IMG cache STALE-VERSION] %s (zapsal '%s', platí '%s')", cache_key, source, CURRENT_SOURCE)
        return None

    if image_url:
        logger.debug("⚡ [IMG cache HIT] %s", cache_key)
        return image_url

    try:
        cached_at = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    if datetime.now(timezone.utc) - cached_at > NEGATIVE_CACHE_TTL:
        logger.debug("⏰ [IMG cache STALE-NEGATIVE] %s", cache_key)
        return None

    logger.debug("🚫 [IMG cache HIT-NEGATIVE] %s", cache_key)
    return ""


def store_cached_image_url(cache_key: str, query: str, image_url: str | None) -> None:
    """Ulož VÝSLEDEK, který OFF skutečně potvrdil: URL, nebo None = "fotka neexistuje".

    Nikdy nevolej po 429, timeoutu, výpadku nebo neplatné odpovědi - to není "neexistuje",
    to je "nevíme", a nevíme se nezapisuje (viz ImageLookupService._process).
    """
    try:
        with closing(_connect()) as connection, connection:
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
                (cache_key, query, image_url or "", CURRENT_SOURCE),
            )
    except sqlite3.Error:
        logger.exception("❌ [IMG cache] zápis do SQLite selhal")
