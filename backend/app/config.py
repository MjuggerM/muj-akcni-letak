"""
Central configuration for the backend.

kupiapi returns shop names as free text scraped straight from the page
(e.g. "Albert hypermarket", "Penny Market", "BILLA"), not a shop ID and
not a logo. To let the frontend filter by "Lidl / Penny / Billa / Albert"
and show a consistent icon, we map each raw shop name to one of our own
store IDs by substring match (case-insensitive). Extend MATCH lists here
if kupi.cz uses another spelling for a store.
"""

STORES: dict[str, dict] = {
    "lidl": {"label": "Lidl", "match": ["lidl"]},
    "penny": {"label": "Penny Market", "match": ["penny"]},
    "billa": {"label": "Billa", "match": ["billa"]},
    "albert": {"label": "Albert", "match": ["albert"]},
}

# How many result pages kupiapi should scrape per tracked item.
# 0 = all pages, which can be slow for broad search terms. Keep this low
# for an interactive app; raise it if you find items get cut off.
DEFAULT_MAX_PAGES = 2

# How long (seconds) a search result is kept in the in-memory cache
# before we re-scrape kupi.cz for it. Keeps repeated frontend polling
# fast and avoids hammering kupi.cz on every page reload.
CACHE_TTL_SECONDS = 20 * 60

# A user may track at most this many search phrases. Keep the limit in the
# API as well as in the UI so a direct API caller cannot trigger an excessive
# number of scraper requests.
MAX_TRACKED_ITEMS = 50

# How long (days) we trust a *negative* product-image lookup (i.e. Open Food
# Facts had nothing for that product name/EAN) before the backend is allowed
# to ask again. Positive hits are cached indefinitely - see app/image_cache.py.
IMAGE_NEGATIVE_CACHE_TTL_DAYS = 30