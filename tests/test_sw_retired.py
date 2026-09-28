"""frontend/sw.js is a retired, self-removing worker (2026-09-25).

The old offline-cache worker kept serving the removed "VECTOR Production" page from cache "vector-hud-v1" (as raw unstyled
HTML whenever the backend was starting or down). The replacement must never answer a request itself, and must clear the
stale caches, unregister and reload open HUD windows. Behaviour was also proven in a real Chromium (stale cache seeded ->
worker registered -> caches empty, no registrations)."""
from __future__ import annotations

from pathlib import Path

SW = (Path(__file__).resolve().parents[1] / "frontend" / "sw.js").read_text(encoding="utf-8")


def test_the_worker_never_intercepts_requests():
    assert 'addEventListener("fetch"' not in SW and "addEventListener('fetch'" not in SW
    assert "respondWith" not in SW


def test_the_worker_clears_caches_unregisters_and_reloads_windows():
    assert "caches.keys()" in SW and "caches.delete" in SW
    assert "registration.unregister()" in SW
    assert "clients.matchAll" in SW and "navigate" in SW
    assert "skipWaiting" in SW


def test_the_worker_does_not_reference_the_removed_page():
    body = "\n".join(l for l in SW.splitlines() if not l.strip().startswith("//"))
    assert "VECTOR.prod.html" not in body and "vector-hud.prod.js" not in body
