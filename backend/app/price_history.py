"""Small SQLite store used to recognise the best unit prices seen by the app."""

import sqlite3
from pathlib import Path

HISTORY_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "price_history.sqlite3"


def _connection() -> sqlite3.Connection:
    HISTORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(HISTORY_DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_price_history (
            tracked_item TEXT NOT NULL,
            product_name TEXT NOT NULL,
            shop_raw TEXT NOT NULL,
            unit TEXT NOT NULL,
            unit_price REAL NOT NULL,
            observed_on TEXT NOT NULL DEFAULT CURRENT_DATE,
            PRIMARY KEY (tracked_item, product_name, shop_raw, unit, observed_on)
        )
        """
    )
    return connection


def annotate_historical_bests(offers: list[dict]) -> None:
    """Attach historical best-price metadata and save today's lowest observation.

    Unit price comparisons never cross units: Kč/kg, Kč/l and Kč/ks are all
    independent series. The history is deliberately local and needs no third-
    party data source.
    """
    comparable = [offer for offer in offers if offer.get("unit_price") is not None and offer.get("unit")]
    if not comparable:
        return

    with _connection() as connection:
        for offer in comparable:
            history_key = offer.get("tracking_rule_id") or offer["tracked_item"]
            previous = connection.execute(
                """
                SELECT MIN(unit_price) FROM daily_price_history
                WHERE tracked_item = ? AND unit = ?
                """,
                (history_key, offer["unit"]),
            ).fetchone()[0]
            current = offer["unit_price"]
            best = current if previous is None else min(current, previous)
            offer["historical_best_unit_price"] = round(best, 2)
            offer["is_historical_best"] = previous is None or current <= previous

            connection.execute(
                """
                INSERT INTO daily_price_history
                    (tracked_item, product_name, shop_raw, unit, unit_price)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tracked_item, product_name, shop_raw, unit, observed_on)
                DO UPDATE SET unit_price = MIN(unit_price, excluded.unit_price)
                """,
                (
                    history_key,
                    offer.get("product_name") or "",
                    offer["shop_raw"],
                    offer["unit"],
                    current,
                ),
            )
