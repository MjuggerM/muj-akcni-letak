"""Hledání fotek produktů v Open Food Facts (OFF).

Tři vrstvy, které spolu záměrně nesouvisejí:

1. PÁROVÁNÍ (čisté funkce nahoře): rozhodne, jestli je produkt z OFF OPRAVDU ten samý produkt
   jako ten z kupi.cz. Žádné "něco podobného", žádná obecná kategorie - buď stejný produkt, nebo nic.
2. KLIENT s odstupem (_wait_for_slot / _search_once): jediné místo, odkud odchází dotazy na OFF.
3. FRONTA + WORKER: endpoint nikdy nečeká na OFF. Vrátí hotový výsledek z cache, nebo "pending"
   a produkt zařadí do fronty; jediný worker ji zpracovává tempem, které OFF snese.
"""

import asyncio
import logging
import math
import re
import time
import unicodedata
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from . import config
from .image_cache import get_cached_image_url, store_cached_image_url

logger = logging.getLogger("akcni_letak.images")

ImageLookupMode = Literal["legacy", "quality"]

OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_FIELDS = "product_name,brands,image_front_url,image_url"

MAX_ATTEMPTS = 3                          # celkový počet pokusů, včetně HTTP 429
FAILURE_COOLDOWN_SECONDS = 120            # po posledním neúspěchu se job chvíli znovu nezařazuje
RATE_LIMIT_BACKOFF_SECONDS = (60, 120, 300, 900)
TRANSIENT_RETRY_BACKOFF_SECONDS = (15, 30, 60)
MAX_RETRY_AFTER_SECONDS = 900
MAX_PENDING_IMAGE_JOBS = 250
PROVIDER_FAILURE_THRESHOLD = 3
PROVIDER_CIRCUIT_BACKOFF_SECONDS = (60, 120, 300, 900)
POLL_MIN_SECONDS = 5                      # co backend doporučí frontendu jako "zeptej se znovu za"
POLL_MAX_SECONDS = 60


# ==============================================================================
# 1) PÁROVÁNÍ
# ==============================================================================

# Slova, která NEJSOU identita produktu (marketing). Neposílají se do hledání a nevyžadují se
# při párování.
MARKETING_PHRASES = (
    "kupi", "delikátní", "delikatni",
    "nejvyšší jakosti", "nejvyssi jakosti", "výběrová", "vyberova", "standard", "poctivá", "poctiva",
    "z podestýlky", "z podestylky", "z poděbrad", "z podebrad", "od kosti", "na rohlik", "na rohlík",
    "akce", "sleva", "balení", "baleni",
)

# Značky, obchodní řady a obchody. Do HLEDÁNÍ se neposílají (OFF je v názvu často nemá, a široký
# dotaz vrátí víc kandidátů), ale při PÁROVÁNÍ se dál VYŽADUJÍ: "Tvaroh Madeta" a "Tvaroh Olma"
# jsou dva různé produkty a nesmí dostat tutéž fotku jen proto, že se z dotazu obě značky vyhodily.
BRAND_PHRASES = (
    "albertovo uzenářství", "albertovo uzenarstvi", "kostelecké uzeniny", "kostelecke uzeniny",
    "řezníkův talíř", "reznikov talir", "reznikuv talir", "srdce domova", "jihočeský", "jihocesky",
    "nature's promise", "natures promise", "billa bonvia", "karlova koruna", "česká farma", "ceska farma",
    "jaroměřický", "jaromericky", "yes plants", "grill party",
    "madeta", "olma", "milko", "albert", "billa", "penny", "lidl", "pilos", "pikok", "le&co", "le & co",
    "idema", "president", "dětská", "detska",
)

# Pokud je tohle v názvu OFF produktu a ne v našem dotazu, je to jiný druh zboží.
_MISMATCH_WORDS = ("tycinka", "snack", "krekr", "cracker", "chips", "protein bar")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUANTITY_RE = re.compile(r"^\d+(?:[a-z]{1,3})?$")        # 500g, 10, 1l, 250ml, 6ks
_UNIT_WORDS = frozenset({"ks", "kg", "g", "mg", "l", "ml", "cl", "dl", "kus", "kusy", "kusu", "bal", "baleni"})


def _phrase_regex(phrases: tuple[str, ...]) -> re.Pattern[str]:
    # Celá slova/fráze (ne podřetězce: "standard" nesmí rozbít "standardní"); delší fráze první.
    ordered = sorted(set(phrases), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(p) for p in ordered) + r")(?!\w)")


_MARKETING_RE = _phrase_regex(MARKETING_PHRASES)
_BRAND_RE = _phrase_regex(BRAND_PHRASES)


def normalize_str(text: str | None) -> str:
    """Bez diakritiky a malými písmeny."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def _tokens(text: str) -> list[str]:
    """Podstatná slova: bez diakritiky, bez množství/jednotek a krátkých zbytků, bez duplicit."""
    seen: set[str] = set()
    result: list[str] = []
    for token in _TOKEN_RE.findall(normalize_str(text)):
        if len(token) < 3 or _QUANTITY_RE.match(token) or token in _UNIT_WORDS or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def match_tokens(name: str) -> list[str]:
    """Slova, která MUSÍ sedět, aby šlo o tentýž produkt (značka i druh zůstávají)."""
    return _tokens(_MARKETING_RE.sub(" ", name.lower()))


def build_search_term(name: str) -> str:
    """Co se pošle do OFF: bez marketingu, značek a množství (zachovává diakritiku)."""
    text = _BRAND_RE.sub(" ", _MARKETING_RE.sub(" ", name.lower()))
    words = []
    for raw in re.split(r"[\s,;/()]+", text):
        norm = normalize_str(raw)
        if len(norm) >= 2 and not _QUANTITY_RE.match(norm) and norm not in _UNIT_WORDS:
            words.append(raw)
    term = " ".join(words)
    return term if len(term) >= 2 else " ".join(match_tokens(name))


def _same_word(a: str, b: str) -> bool:
    """Shoda slov s tolerancí českého skloňování: broskev/broskve, paprika/papriky, kuře/kuřecí."""
    if a == b:
        return True
    shortest = min(len(a), len(b))
    if shortest < 4:
        return False
    prefix = 0
    for x, y in zip(a, b):
        if x != y:
            break
        prefix += 1
    return prefix >= max(4, shortest - 2)


@dataclass(frozen=True)
class ProductMatch:
    name: str
    image_url: str
    query_coverage: float       # jaká část slov z našeho názvu je v OFF produktu (název + značka)
    candidate_coverage: float   # jaká část slov OFF názvu je vysvětlena naším názvem

    @property
    def score(self) -> float:
        return self.query_coverage + self.candidate_coverage


@dataclass(frozen=True)
class MatchDecision:
    match: ProductMatch | None             # přijatý kandidát, nebo None = žádný není ten samý produkt
    closest_rejected: ProductMatch | None  # nejbližší zamítnutý (do logu, ať jde ladit prahy)
    examined: int                          # kolik produktů s fotkou se posuzovalo


def _evaluate(query_tokens: list[str], product: dict) -> ProductMatch | None:
    image = product.get("image_front_url") or product.get("image_url")
    if not isinstance(image, str) or not image.lower().startswith(("http://", "https://")):
        return None
    name = str(product.get("product_name") or "")
    name_tokens = _tokens(name)
    if not name_tokens:
        return None
    pool = name_tokens + _tokens(str(product.get("brands") or "").replace(",", " "))
    covered = sum(1 for q in query_tokens if any(_same_word(q, c) for c in pool))
    explained = sum(1 for c in name_tokens if any(_same_word(c, q) for q in query_tokens))
    return ProductMatch(name, image, covered / len(query_tokens), explained / len(name_tokens))


def _is_confident(candidate: ProductMatch, query_norm: str) -> bool:
    if candidate.query_coverage + 1e-9 < config.IMAGE_MATCH_MIN_QUERY_COVERAGE:
        return False
    if candidate.candidate_coverage + 1e-9 < config.IMAGE_MATCH_MIN_CANDIDATE_COVERAGE:
        return False
    name_norm = normalize_str(candidate.name)
    return not any(bad in name_norm and bad not in query_norm for bad in _MISMATCH_WORDS)


def decide_match(name: str, products: list) -> MatchDecision:
    """Vybere z výsledků OFF produkt, který JE ten samý co `name`. Jinak nic (placeholder)."""
    query_tokens = match_tokens(name)
    if not query_tokens:
        return MatchDecision(None, None, 0)
    query_norm = " ".join(query_tokens)

    accepted: list[ProductMatch] = []
    rejected: list[ProductMatch] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        candidate = _evaluate(query_tokens, product)
        if candidate is None:
            continue
        (accepted if _is_confident(candidate, query_norm) else rejected).append(candidate)

    best = max(accepted, key=lambda m: m.score) if accepted else None
    closest = max(rejected, key=lambda m: m.score) if rejected else None
    return MatchDecision(best, closest, len(accepted) + len(rejected))


def decide_match_quality(name: str, products: list) -> MatchDecision:
    """Přísnější alternativa: odmítne širokou i nejednoznačnou shodu.

    Funkce `decide_match` zůstává beze změny jako původní režim. Quality režim
    vyžaduje užší shodu názvu a dostatečný odstup od dalšího odlišného obrázku.
    """
    query_tokens = match_tokens(name)
    if not query_tokens:
        return MatchDecision(None, None, 0)
    query_norm = " ".join(query_tokens)

    accepted: list[ProductMatch] = []
    rejected: list[ProductMatch] = []
    examined = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        candidate = _evaluate(query_tokens, product)
        if candidate is None:
            continue
        examined += 1
        confident = (
            candidate.query_coverage + 1e-9 >= config.IMAGE_MATCH_MIN_QUERY_COVERAGE
            and candidate.candidate_coverage + 1e-9 >= config.IMAGE_QUALITY_MIN_CANDIDATE_COVERAGE
            and _is_confident(candidate, query_norm)
        )
        (accepted if confident else rejected).append(candidate)

    # Více řádků se stejnou URL nepředstavuje více nezávislých možností.
    best_by_image: dict[str, ProductMatch] = {}
    for candidate in accepted:
        current = best_by_image.get(candidate.image_url)
        if current is None or candidate.score > current.score:
            best_by_image[candidate.image_url] = candidate
    ranked = sorted(best_by_image.values(), key=lambda candidate: candidate.score, reverse=True)

    best = ranked[0] if ranked else None
    if len(ranked) > 1 and best.score - ranked[1].score < config.IMAGE_QUALITY_MIN_SCORE_MARGIN:
        rejected.extend(ranked[:2])
        best = None

    closest = max(rejected, key=lambda candidate: candidate.score) if rejected else None
    return MatchDecision(best, closest, examined)


def cache_key_for(name: str, mode: ImageLookupMode = "legacy") -> str:
    normalized = " ".join(name.split()).lower()
    if mode == "legacy":
        # Zachová stávající klíče i již naplněnou cache.
        return f"name:{normalized}"
    return f"quality:v{config.IMAGE_QUALITY_MATCH_VERSION}:name:{normalize_str(normalized)}"


# ==============================================================================
# 2) + 3) KLIENT S ODSTUPEM, FRONTA A WORKER
# ==============================================================================

@dataclass(frozen=True)
class LookupResult:
    status: str                        # "found" | "missing" | "pending" | "error"
    image_url: str | None = None
    retry_after: int | None = None     # prodleva před dalším dotazem u pending/error


@dataclass(frozen=True)
class _SearchOutcome:
    kind: str                          # "ok" | "rate_limited" | "failed"
    products: list = field(default_factory=list)
    retry_after: float | None = None
    provider_unavailable: bool = False


@dataclass
class _ImageJob:
    key: str
    name: str
    retry_at: float
    attempts: int = 0
    state: str = "queued"
    mode: ImageLookupMode = "legacy"


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(min(int(raw), MAX_RETRY_AFTER_SECONDS))

    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    return min(max(0.0, seconds), MAX_RETRY_AFTER_SECONDS)


class ImageLookupService:
    def __init__(
        self,
        *,
        min_interval: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str | None = None,
        search_url: str = OFF_SEARCH_URL,
    ) -> None:
        self._min_interval = config.OFF_SEARCH_MIN_INTERVAL_SECONDS if min_interval is None else min_interval
        self._transport = transport
        self._user_agent = user_agent or config.OFF_USER_AGENT
        self._search_url = search_url
        self._queue: deque[str] = deque()
        self._jobs: dict[str, _ImageJob] = {}
        self._failed_until: dict[str, float] = {}
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._last_request_at = float("-inf")
        self._not_before = float("-inf")
        self._rate_limit_hits = 0
        self._provider_failure_streak = 0

    # --- veřejné API -----------------------------------------------------------

    def lookup(self, name: str, mode: ImageLookupMode = "legacy") -> LookupResult:
        """Rychlé a neblokující: cache, nebo zařazení do fronty. Na OFF NIKDY nečeká."""
        name = " ".join(name.split())
        key = cache_key_for(name, mode)

        cached = get_cached_image_url(key)
        if cached:
            return LookupResult("found", cached)
        if cached == "":
            return LookupResult("missing")

        if not match_tokens(name):          # nic podstatného, podle čeho by šlo hledat
            return LookupResult("missing")

        now = time.monotonic()
        self._prune_failed(now)
        failed_until = self._failed_until.get(key)
        if failed_until is not None:
            if now < failed_until:
                return LookupResult("error", retry_after=max(1, math.ceil(failed_until - now)))
            del self._failed_until[key]

        if key in self._jobs:
            self._ensure_worker()
            return LookupResult("pending", retry_after=self._retry_after(key))

        if len(self._jobs) >= MAX_PENDING_IMAGE_JOBS:
            self._ensure_worker()
            return LookupResult("pending", retry_after=POLL_MAX_SECONDS)

        self._jobs[key] = _ImageJob(key=key, name=name, retry_at=now, mode=mode)
        self._queue.append(key)
        self._wakeup.set()
        self._ensure_worker()
        return LookupResult("pending", retry_after=self._retry_after(key))

    async def start(self) -> None:
        self._ensure_worker()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- interní ---------------------------------------------------------------

    def _prune_failed(self, now: float) -> None:
        for key, expires_at in list(self._failed_until.items()):
            if expires_at <= now:
                del self._failed_until[key]

    def _retry_after(self, key: str) -> int:
        job = self._jobs[key]
        now = time.monotonic()
        try:
            position = list(self._queue).index(key)
        except ValueError:  # the worker is currently processing this job
            position = 0
        next_slot = max(job.retry_at, self._not_before, self._last_request_at + self._min_interval)
        seconds = max(0, next_slot - now) + position * self._min_interval
        return max(POLL_MIN_SECONDS, min(POLL_MAX_SECONDS, math.ceil(seconds)))

    def _take_ready_job(self) -> _ImageJob | None:
        now = time.monotonic()
        if max(self._not_before, self._last_request_at + self._min_interval) > now:
            return None

        for _ in range(len(self._queue)):
            key = self._queue.popleft()
            job = self._jobs.get(key)
            if job is None:
                continue
            if job.retry_at <= now:
                job.state = "running"
                return job
            self._queue.append(key)
        return None

    def _next_wakeup_delay(self) -> float | None:
        now = time.monotonic()
        ready_at = [
            max(job.retry_at, self._not_before, self._last_request_at + self._min_interval)
            for key in self._queue
            if (job := self._jobs.get(key)) is not None
        ]
        return max(0, min(ready_at) - now) if ready_at else None

    async def _wait_for_work(self) -> None:
        self._wakeup.clear()
        delay = self._next_wakeup_delay()
        if delay is None:
            await self._wakeup.wait()
            return
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=max(delay, 0.001))
        except asyncio.TimeoutError:
            pass

    def _ensure_worker(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._worker())

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=15.0,
                headers={"User-Agent": self._user_agent},
                transport=self._transport,
            )
        return self._client

    async def _worker(self) -> None:
        logger.info("🧵 [IMG worker] běží (max. 1 dotaz na OFF za %.1f s)", self._min_interval)
        while True:
            job = self._take_ready_job()
            if job is None:
                await self._wait_for_work()
                continue

            try:
                retry = await self._process(job)
            except asyncio.CancelledError:
                job.state = "queued"
                job.retry_at = time.monotonic()
                self._queue.appendleft(job.key)
                self._wakeup.set()
                raise
            except Exception:
                logger.exception("❌ [IMG worker] neočekávaná chyba u '%s'", job.name)
                self._failed_until[job.key] = time.monotonic() + FAILURE_COOLDOWN_SECONDS
                retry = False

            if retry:
                job.state = "retry_wait"
                self._queue.append(job.key)
            else:
                self._jobs.pop(job.key, None)

    async def _process(self, job: _ImageJob) -> bool:
        term = build_search_term(job.name)
        outcome = await self._search_once(term)

        if outcome.kind == "rate_limited":
            self._provider_failure_streak = 0
            self._rate_limit_hits += 1
            backoff = RATE_LIMIT_BACKOFF_SECONDS[
                min(self._rate_limit_hits - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
            ]
            wait = outcome.retry_after or backoff
            now = time.monotonic()
            self._not_before = max(self._not_before, now + wait)
            job.attempts += 1
            if job.attempts >= MAX_ATTEMPTS:
                logger.warning(
                    "🛑 [IMG OFF] '%s': rate limit po %d pokusech; další pokus nejdřív za %.0f s.",
                    term, job.attempts, wait,
                )
                self._failed_until[job.key] = now + FAILURE_COOLDOWN_SECONDS
                return False
            job.retry_at = self._not_before
            logger.warning(
                "🛑 [IMG OFF] HTTP 429 pro '%s'; job zůstává ve frontě, další pokus za %.0f s.",
                term, wait,
            )
            return True

        if outcome.kind == "failed":
            job.attempts += 1
            now = time.monotonic()
            if outcome.retry_after is not None:
                self._not_before = max(self._not_before, now + outcome.retry_after)
            if outcome.provider_unavailable:
                self._provider_failure_streak += 1
                if self._provider_failure_streak >= PROVIDER_FAILURE_THRESHOLD:
                    backoff_index = min(
                        self._provider_failure_streak - PROVIDER_FAILURE_THRESHOLD,
                        len(PROVIDER_CIRCUIT_BACKOFF_SECONDS) - 1,
                    )
                    circuit_wait = PROVIDER_CIRCUIT_BACKOFF_SECONDS[backoff_index]
                    self._not_before = max(self._not_before, now + circuit_wait)
                    logger.warning(
                        "⚠️ [IMG OFF] opakované chyby zdroje; společná fronta pozastavena na %.0f s.",
                        circuit_wait,
                    )
            if job.attempts >= MAX_ATTEMPTS:
                logger.warning(
                    "⚠️ [IMG OFF] '%s': %d neúspěšných pokusů; cooldown %d s. Výsledek se necachuje.",
                    term, job.attempts, FAILURE_COOLDOWN_SECONDS,
                )
                self._failed_until[job.key] = now + FAILURE_COOLDOWN_SECONDS
                return False
            backoff = TRANSIENT_RETRY_BACKOFF_SECONDS[
                min(job.attempts - 1, len(TRANSIENT_RETRY_BACKOFF_SECONDS) - 1)
            ]
            retry_delay = outcome.retry_after if outcome.retry_after is not None else backoff
            job.retry_at = max(self._not_before, now + retry_delay)
            logger.warning(
                "⚠️ [IMG OFF] '%s': pokus %d/%d selhal; job zůstává ve frontě, další pokus za %.0f s.",
                term, job.attempts, MAX_ATTEMPTS, job.retry_at - time.monotonic(),
            )
            return True

        # OFF skutečně odpověděl -> tohle je JISTÁ informace a smí se uložit (i "nic nenalezeno")
        self._rate_limit_hits = 0
        self._provider_failure_streak = 0
        matcher = decide_match_quality if job.mode == "quality" else decide_match
        decision = matcher(job.name, outcome.products)
        store_cached_image_url(job.key, job.name, decision.match.image_url if decision.match else None)
        if decision.match:
            match = decision.match
            logger.info(
                "✅ [IMG] '%s' -> '%s' (pokrytí dotazu %.2f, pokrytí názvu %.2f)",
                job.name, match.name, match.query_coverage, match.candidate_coverage,
            )
        elif decision.closest_rejected:
            match = decision.closest_rejected
            logger.info(
                "∅ [IMG] '%s': nic stejného (nejbližší '%s': dotaz %.2f / název %.2f) - bude placeholder",
                job.name, match.name, match.query_coverage, match.candidate_coverage,
            )
        else:
            logger.info("∅ [IMG] '%s': OFF nevrátil žádný produkt s fotkou - bude placeholder", job.name)
        return False

    async def _wait_for_slot(self) -> None:
        next_slot = max(self._last_request_at + self._min_interval, self._not_before)
        wait = next_slot - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_at = time.monotonic()

    async def _search_once(self, term: str) -> _SearchOutcome:
        await self._wait_for_slot()
        logger.info("📡 [IMG OFF] hledám '%s'", term)
        params = {
            "search_terms": term,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "24",     # nahoře v OFF bývá hodně produktů bez fotky, širší okno zvyšuje šanci
            "fields": OFF_FIELDS,
        }
        try:
            response = await self._get_client().get(self._search_url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("⚠️ [IMG OFF] %s při hledání '%s': %s", type(exc).__name__, term, exc)
            return _SearchOutcome("failed", provider_unavailable=True)

        if response.status_code == 429:
            return _SearchOutcome("rate_limited", retry_after=_parse_retry_after(response))
        if response.status_code != 200:
            logger.warning("⚠️ [IMG OFF] HTTP %s při hledání '%s'", response.status_code, term)
            provider_unavailable = response.status_code >= 500 or response.status_code in (403, 408)
            retry_after = _parse_retry_after(response) if provider_unavailable else None
            return _SearchOutcome("failed", retry_after=retry_after, provider_unavailable=provider_unavailable)

        try:
            payload = response.json()
        except ValueError:
            logger.warning("⚠️ [IMG OFF] odpověď na '%s' není JSON", term)
            return _SearchOutcome("failed")

        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list):
            # 200 bez seznamu produktů = degradovaná odpověď, ne "nic nenalezeno" (to by se uložilo na 30 dní)
            logger.warning("⚠️ [IMG OFF] odpověď na '%s' neobsahuje seznam 'products'", term)
            return _SearchOutcome("failed")
        return _SearchOutcome("ok", products=products)
