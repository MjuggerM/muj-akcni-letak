import asyncio
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx

from app import image_service
from app.image_service import ImageLookupService, _ImageJob, _SearchOutcome


def test_lookup_deduplicates_jobs_and_waits_for_queue_capacity(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    monkeypatch.setattr(image_service, "MAX_PENDING_IMAGE_JOBS", 1)
    service = ImageLookupService(min_interval=0)
    service._ensure_worker = lambda: None

    async def exercise_queue():
        first = service.lookup("Vejce M")
        duplicate = service.lookup("  vejce   m ")
        overflow = service.lookup("Tvaroh")

        assert first.status == duplicate.status == overflow.status == "pending"
        assert overflow.retry_after == image_service.POLL_MAX_SECONDS
        assert len(service._jobs) == 1
        assert len(service._queue) == 1

    asyncio.run(exercise_queue())


def test_transient_retry_moves_behind_ready_jobs(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    monkeypatch.setattr(image_service, "store_cached_image_url", lambda *_args: None)
    monkeypatch.setattr(image_service, "TRANSIENT_RETRY_BACKOFF_SECONDS", (0.02, 0.02, 0.02))
    service = ImageLookupService(min_interval=0)
    calls = []
    complete = asyncio.Event()

    async def fake_search(term):
        calls.append(term)
        if term == "vejce" and calls.count(term) == 1:
            return _SearchOutcome("failed")
        if len(calls) == 3:
            complete.set()
        return _SearchOutcome("ok", products=[])

    service._search_once = fake_search

    async def exercise_queue():
        await service.start()
        service.lookup("Vejce")
        service.lookup("Tvaroh")
        await asyncio.wait_for(complete.wait(), timeout=1)
        await service.stop()

    asyncio.run(exercise_queue())

    assert calls == ["vejce", "tvaroh", "vejce"]


def test_rate_limit_backoff_applies_before_next_job(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    monkeypatch.setattr(image_service, "store_cached_image_url", lambda *_args: None)
    monkeypatch.setattr(image_service, "RATE_LIMIT_BACKOFF_SECONDS", (0.03, 0.03, 0.03, 0.03))
    service = ImageLookupService(min_interval=0)
    calls = []
    started_at = None
    second_job_started_at = None
    complete = asyncio.Event()

    async def fake_search(term):
        nonlocal second_job_started_at
        calls.append(term)
        if term == "vejce" and calls.count(term) == 1:
            return _SearchOutcome("rate_limited")
        if term == "tvaroh":
            second_job_started_at = time.monotonic()
        if len(calls) == 3:
            complete.set()
        return _SearchOutcome("ok", products=[])

    service._search_once = fake_search

    async def exercise_queue():
        nonlocal started_at
        await service.start()
        started_at = time.monotonic()
        service.lookup("Vejce")
        service.lookup("Tvaroh")
        await asyncio.wait_for(complete.wait(), timeout=1)
        await service.stop()

    asyncio.run(exercise_queue())

    assert calls == ["vejce", "tvaroh", "vejce"]
    assert started_at is not None and second_job_started_at is not None
    assert second_job_started_at - started_at >= 0.02


def test_search_schedules_server_retry_after_for_503():
    def respond(_request):
        return httpx.Response(503, headers={"Retry-After": "17"})

    service = ImageLookupService(min_interval=0, transport=httpx.MockTransport(respond))

    async def make_request():
        try:
            return await service._search_once("vejce")
        finally:
            await service.stop()

    outcome = asyncio.run(make_request())

    assert outcome.kind == "failed"
    assert outcome.retry_after == 17


def test_server_retry_after_pauses_other_jobs_even_after_final_attempt(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    service = ImageLookupService(min_interval=0)
    service._ensure_worker = lambda: None

    async def fake_search(_term):
        return _SearchOutcome("failed", retry_after=17)

    service._search_once = fake_search
    job = _ImageJob("name:vejce", "Vejce", time.monotonic(), attempts=image_service.MAX_ATTEMPTS - 1)

    async def process_final_attempt():
        return await service._process(job)

    retry = asyncio.run(process_final_attempt())
    service.lookup("Tvaroh")

    assert retry is False
    assert service._not_before >= time.monotonic() + 16
    assert service._take_ready_job() is None


def test_parse_retry_after_accepts_http_date():
    target = datetime.now(timezone.utc) + timedelta(seconds=120)
    response = httpx.Response(503, headers={"Retry-After": format_datetime(target, usegmt=True)})

    retry_after = image_service._parse_retry_after(response)

    assert retry_after is not None
    assert 110 <= retry_after <= 120


def test_quality_matcher_keeps_legacy_and_rejects_extra_product_variant():
    query = "Mléčná čokoláda Orion"
    products = [{
        "product_name": "Mléčná čokoláda Orion s lískovými oříšky",
        "brands": "Orion",
        "image_front_url": "https://example.com/orion-hazelnut.jpg",
    }]

    assert image_service.decide_match(query, products).match is not None
    assert image_service.decide_match_quality(query, products).match is None


def test_quality_matcher_accepts_czech_inflection():
    products = [{
        "product_name": "Kompot broskev",
        "image_front_url": "https://example.com/peaches.jpg",
    }]

    decision = image_service.decide_match_quality("Broskve kompot", products)

    assert decision.match is not None
    assert decision.match.image_url == "https://example.com/peaches.jpg"


def test_quality_matcher_rejects_near_tied_distinct_images():
    products = [
        {
            "product_name": "Tvaroh",
            "brands": "Madeta",
            "image_front_url": "https://example.com/madeta-a.jpg",
        },
        {
            "product_name": "Tvaroh",
            "brands": "Madeta",
            "image_front_url": "https://example.com/madeta-b.jpg",
        },
    ]

    decision = image_service.decide_match_quality("Tvaroh Madeta", products)

    assert decision.match is None
    assert decision.closest_rejected is not None
    assert decision.examined == 2


def test_image_modes_keep_separate_queue_entries_and_cache_keys(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    service = ImageLookupService(min_interval=0)
    service._ensure_worker = lambda: None

    legacy = service.lookup("Vejce M", "legacy")
    legacy_duplicate = service.lookup(" vejce  m ", "legacy")
    quality = service.lookup("Vejce M", "quality")

    assert legacy.status == legacy_duplicate.status == quality.status == "pending"
    assert len(service._jobs) == 2
    assert image_service.cache_key_for("Vejce M") == "name:vejce m"
    assert image_service.cache_key_for("Vejce M", "quality").startswith("quality:v1:name:")


def test_worker_uses_matcher_selected_by_mode(monkeypatch):
    stored = {}
    products = [{
        "product_name": "Mléčná čokoláda Orion s lískovými oříšky",
        "brands": "Orion",
        "image_front_url": "https://example.com/orion-hazelnut.jpg",
    }]
    monkeypatch.setattr(image_service, "store_cached_image_url", lambda key, _name, url: stored.__setitem__(key, url))
    service = ImageLookupService(min_interval=0)

    async def fake_search(_term):
        return _SearchOutcome("ok", products=products)

    service._search_once = fake_search
    query = "Mléčná čokoláda Orion"
    legacy_job = _ImageJob(image_service.cache_key_for(query), query, time.monotonic(), mode="legacy")
    quality_job = _ImageJob(image_service.cache_key_for(query, "quality"), query, time.monotonic(), mode="quality")

    async def process_both_modes():
        await service._process(legacy_job)
        await service._process(quality_job)

    asyncio.run(process_both_modes())

    assert stored[legacy_job.key] == "https://example.com/orion-hazelnut.jpg"
    assert stored[quality_job.key] is None


def test_repeated_provider_failures_open_global_circuit(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    monkeypatch.setattr(image_service, "PROVIDER_FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(image_service, "PROVIDER_CIRCUIT_BACKOFF_SECONDS", (0.05, 0.1))
    service = ImageLookupService(min_interval=0)
    service._ensure_worker = lambda: None

    async def unavailable(_term):
        return _SearchOutcome("failed", provider_unavailable=True)

    service._search_once = unavailable

    async def process_failures():
        for index in range(3):
            job = _ImageJob(f"name:item-{index}", f"item {index}", time.monotonic())
            await service._process(job)

    asyncio.run(process_failures())
    service.lookup("Tvaroh")

    assert service._provider_failure_streak == 3
    assert service._not_before >= time.monotonic() + 0.04
    assert service._take_ready_job() is None


def test_temporary_error_includes_retry_after(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    service = ImageLookupService(min_interval=0)
    service._ensure_worker = lambda: None
    key = image_service.cache_key_for("Vejce")
    service._failed_until[key] = time.monotonic() + 20

    result = service.lookup("Vejce")

    assert result.status == "error"
    assert result.retry_after is not None
    assert 1 <= result.retry_after <= 20


def test_cancelled_running_job_is_requeued_and_resumes(monkeypatch):
    monkeypatch.setattr(image_service, "get_cached_image_url", lambda _key: None)
    monkeypatch.setattr(image_service, "store_cached_image_url", lambda *_args: None)
    service = ImageLookupService(min_interval=0)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def blocked_search(_term):
        started.set()
        await release.wait()
        return _SearchOutcome("ok", products=[])

    async def successful_search(term):
        calls.append(term)
        return _SearchOutcome("ok", products=[])

    service._search_once = blocked_search

    async def exercise_restart():
        service.lookup("Vejce")
        await asyncio.wait_for(started.wait(), timeout=1)
        await service.stop()

        key = "name:vejce"
        assert key in service._jobs
        assert list(service._queue) == [key]
        assert service._jobs[key].state == "queued"

        service._search_once = successful_search
        await service.start()
        async with asyncio.timeout(1):
            while key in service._jobs:
                await asyncio.sleep(0)
        await service.stop()

    asyncio.run(exercise_restart())

    assert calls == ["vejce"]
