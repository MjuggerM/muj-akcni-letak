from fastapi.testclient import TestClient

from app import main
from app.image_service import LookupResult


def test_proxy_image_defaults_to_legacy_and_accepts_quality(monkeypatch):
    calls = []

    class FakeImageService:
        async def start(self):
            pass

        async def stop(self):
            pass

        def lookup(self, name, mode="legacy"):
            calls.append((name, mode))
            return LookupResult("pending", retry_after=5)

    monkeypatch.setattr(main, "ImageLookupService", FakeImageService)

    with TestClient(main.app) as client:
        legacy = client.get("/api/proxy-image", params={"query": "Vejce M"})
        quality = client.get("/api/proxy-image", params={"query": "Vejce M", "mode": "quality"})
        invalid = client.get("/api/proxy-image", params={"query": "Vejce M", "mode": "unknown"})

    assert legacy.status_code == quality.status_code == 200
    assert legacy.json()["status"] == quality.json()["status"] == "pending"
    assert invalid.status_code == 422
    assert calls == [("Vejce M", "legacy"), ("Vejce M", "quality")]


def test_proxy_image_exposes_retry_delay_for_temporary_errors(monkeypatch):
    class FakeImageService:
        async def start(self):
            pass

        async def stop(self):
            pass

        def lookup(self, _name, _mode="legacy"):
            return LookupResult("error", retry_after=42)

    monkeypatch.setattr(main, "ImageLookupService", FakeImageService)

    with TestClient(main.app) as client:
        response = client.get("/api/proxy-image", params={"query": "Vejce"})

    assert response.status_code == 200
    assert response.json() == {"status": "error", "image_url": None, "retry_after": 42}
