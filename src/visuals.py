"""Fetch cinematic vertical b-roll from Pexels (free). Falls back to color clips."""
from __future__ import annotations

import hashlib
from pathlib import Path

import requests

from . import ffmpegutil
from .settings import env

_SEARCH = "https://api.pexels.com/videos/search"
# muted dark tones used when no b-roll is available (still renders a clean video)
_FALLBACK_COLORS = ["0x0B1220", "0x111827", "0x1F2937", "0x0F172A", "0x1E293B", "0x0C1A2B"]


def _pick_file(video: dict) -> dict | None:
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
    if not files:
        return None
    portrait = [f for f in files if (f.get("height") or 0) >= (f.get("width") or 0)]
    pool = portrait or files
    # prefer ~1080 wide, not gigantic
    pool.sort(key=lambda f: abs((f.get("width") or 0) - 1080))
    return pool[0]


def _download(url: str, dest: Path) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for block in r.iter_content(chunk_size=1 << 16):
                    f.write(block)
        return dest.stat().st_size > 1024
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


def _search_one(key: str, query: str, cfg: dict, cache: Path) -> str | None:
    try:
        r = requests.get(
            _SEARCH,
            headers={"Authorization": key},
            params={"query": query, "orientation": cfg["pexels"]["orientation"],
                    "per_page": cfg["pexels"]["per_page"], "size": "medium"},
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  (Pexels search failed for '{query}': {e})")
        return None

    for video in r.json().get("videos", []):
        if (video.get("duration") or 0) < cfg["pexels"]["min_clip_seconds"]:
            continue
        f = _pick_file(video)
        if not f:
            continue
        dest = cache / f"{video['id']}_{f.get('width')}x{f.get('height')}.mp4"
        if dest.exists() and dest.stat().st_size > 1024:
            return str(dest)
        if _download(f["link"], dest):
            return str(dest)
    return None


def fetch_broll(cfg: dict, beats: list[dict]) -> list[str]:
    """Return one local video-file path per beat (Pexels clip or color fallback)."""
    key = env("PEXELS_API_KEY")
    cache = Path(cfg["paths"]["broll_cache"])
    cache.mkdir(parents=True, exist_ok=True)
    fallback_dir = cache / "_fallback"
    fallback_dir.mkdir(exist_ok=True)

    paths: list[str] = []
    for i, beat in enumerate(beats):
        clip = None
        if key:
            query = beat.get("broll_query") or f"cinematic {cfg['niche']}"
            clip = _search_one(key, query, cfg, cache)
            if not clip:  # broaden the search once
                clip = _search_one(key, "cinematic slow motion background", cfg, cache)
        if not clip:
            color = _FALLBACK_COLORS[i % len(_FALLBACK_COLORS)]
            tag = hashlib.md5(f"{i}{color}".encode()).hexdigest()[:8]
            clip = str(fallback_dir / f"color_{tag}.mp4")
            if not Path(clip).exists():
                ffmpegutil.make_color_clip(clip, 4.0, f"{cfg['video']['width']}x{cfg['video']['height']}", color)
        paths.append(clip)

    if not key:
        print("  (No PEXELS_API_KEY set - using solid-color backgrounds. Add the free key for real b-roll.)")
    return paths
