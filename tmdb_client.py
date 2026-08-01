"""
Thin wrapper around the TMDB v3 API.
The API key lives only here (loaded from .env) — it is never sent to the browser.
"""
import os
import requests

BASE = "https://api.themoviedb.org/3"


def _key():
    key = os.getenv("TMDB_API_KEY")
    if not key:
        raise RuntimeError("TMDB_API_KEY is not set. Add it to your .env file.")
    return key


def _get(path: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["api_key"] = _key()
    resp = requests.get(f"{BASE}{path}", params=params, timeout=12)
    resp.raise_for_status()
    return resp.json()


def discover(media_type: str, params: dict) -> dict:
    return _get(f"/discover/{media_type}", params)


def search_multi(query: str) -> dict:
    return _get("/search/multi", {"query": query, "include_adult": "false"})


def trending() -> dict:
    return _get("/trending/all/week")


def details(media_type: str, item_id: int) -> dict:
    return _get(f"/{media_type}/{item_id}", {"append_to_response": "videos,watch/providers"})


def genres() -> dict:
    movie = _get("/genre/movie/list")
    tv = _get("/genre/tv/list")
    merged: dict[int, str] = {}
    for g in movie.get("genres", []):
        merged[g["id"]] = g["name"]
    for g in tv.get("genres", []):
        merged[g["id"]] = g["name"]
    return merged
