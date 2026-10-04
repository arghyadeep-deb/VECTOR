"""Spotify plugin — control playback, search, manage playlists."""

from loguru import logger
from typing import Optional


try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _SPOTIFY = True
except ImportError:
    _SPOTIFY = False


class SpotifyPlugin:
    def __init__(self, client_id: str = "", client_secret: str = "", redirect_uri: str = "http://localhost:8888"):
        self._sp = None
        self._config = {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}

    async def initialize(self):
        if not _SPOTIFY: return
        try:
            auth = SpotifyOAuth(**self._config, scope="user-read-playback-state user-modify-playback-state playlist-read-private")
            self._sp = spotipy.Spotify(auth_manager=auth)
        except Exception as e:
            logger.warning(f"Spotify init failed: {e}")

    async def current_track(self) -> dict:
        if not self._sp: return {"error": "not initialized"}
        try:
            playback = self._sp.current_playback()
            if playback and playback.get("item"):
                item = playback["item"]
                return {"track": item["name"], "artist": item["artists"][0]["name"], "playing": playback["is_playing"]}
            return {"status": "no playback"}
        except Exception as e:
            return {"error": str(e)}

    async def search(self, query: str, limit: int = 5) -> list:
        if not self._sp: return []
        results = self._sp.search(query, limit=limit, type="track")
        return [{"name": t["name"], "artist": t["artists"][0]["name"], "uri": t["uri"]} for t in results["tracks"]["items"]]

    async def play(self, uri: str = "") -> dict:
        if not self._sp: return {"error": "not initialized"}
        try:
            if uri: self._sp.start_playback(uris=[uri])
            else: self._sp.start_playback()
            return {"status": "playing"}
        except Exception as e:
            return {"error": str(e)}

    async def pause(self) -> dict:
        if not self._sp: return {"error": "not initialized"}
        self._sp.pause_playback()
        return {"status": "paused"}
