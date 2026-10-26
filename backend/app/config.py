"""
Central configuration for the backend.

Kupi returns shop names as free text scraped straight from the page
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

# How many Kupi search pages to scrape per tracked item.
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

# --- Fotky produktů (Open Food Facts) ----------------------------------------
# Celá tahle sekce platí pro app/image_service.py a app/image_cache.py.

# Open Food Facts povoluje 10 dotazů/min/IP na vyhledávání (/cgi/search.pl, /api/v*/search)
# a při překročení si vyhrazuje právo zablokovat IP:
# https://openfoodfacts.github.io/openfoodfacts-server/api/
# Minimální odstup mezi dvěma SKUTEČNÝMI dotazy na OFF z celého backendu.
# 6.5 s ~ 9.2 dotazu/min = bezpečně pod limitem. NEZKRACUJ ("aby to bylo rychlejší") - přesně
# tohle je cesta k banu, po kterém nepomůže žádná oprava v kódu.
OFF_SEARCH_MIN_INTERVAL_SECONDS = 6.5

# OFF chce v User-Agentu název aplikace + kontakt (jinak riskuješ, že tě bere jako bota).
# Hlavičky musí být čistě ASCII (žádná diakritika). DOPLŇ SVŮJ E-MAIL.
OFF_USER_AGENT = "MujAkcniLetak/1.0 (personal project; contact: replace-with-your-email@example.com)"

# How long (days) we trust a *negative* product-image lookup (i.e. Open Food
# Facts had nothing for that product) before the backend is allowed to ask
# again. Positive hits are cached indefinitely - see app/image_cache.py.
IMAGE_NEGATIVE_CACHE_TTL_DAYS = 30

# Verze algoritmu párování. Záznamy v cache zapsané JINOU verzí se ignorují (a při dalším
# hledání se přepíšou). Zvyš číslo pokaždé, když změníš pravidla párování níž - jinak ti v cache
# zůstanou (navždy) fotky vybrané starým, volnějším algoritmem (např. zelenina u koření).
IMAGE_MATCH_VERSION = 2

# Kolik "podstatných" slov z názvu produktu z kupi.cz musí najít OFF produkt (název + značka).
# 1.0 = všechna (jméno, značka, druh...). Nižší číslo = víc fotek, ale víc omylů.
# Příklad: "Paprika mletá sladká Kotányi" vs. OFF "Paprika červená" pokrývá 1/4 = 0.25 -> zamítnuto.
IMAGE_MATCH_MIN_QUERY_COVERAGE = 1.0

# Kolik slov v názvu OFF produktu musí vysvětlovat náš dotaz (brání tomu, aby obecné "Paprika"
# dostalo fotku "Paprika sladká mletá Kotányi 50 g"). 0.5 = nejvýš polovina slov navíc.
IMAGE_MATCH_MIN_CANDIDATE_COVERAGE = 0.5

# Volitelné přísnější párování fotek. Starý režim používá výše uvedené prahy;
# v režimu quality se požaduje užší shoda názvu a odstup od druhého kandidáta.
IMAGE_QUALITY_MIN_CANDIDATE_COVERAGE = 0.75
IMAGE_QUALITY_MIN_SCORE_MARGIN = 0.08
IMAGE_QUALITY_MATCH_VERSION = 1
