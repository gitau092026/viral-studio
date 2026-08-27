"""Config + environment loading. Everything has a default so nothing crashes on a missing key."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Defaults mirror config.yaml so the pipeline works even if config.yaml is deleted.
DEFAULTS = {
    "niche": "",
    "search": {
        "keywords": [],
        "region": "US",
        "language": "en",
        "max_results": 25,
        "published_within_days": 30,
        "min_views": 20000,
    },
    "voice": {"name": "en-US-ChristopherNeural", "rate": "+8%", "pitch": "+0Hz", "volume": "+0%"},
    "video": {"width": 1080, "height": 1920, "fps": 30, "min_seconds": 30, "max_seconds": 60, "tail_seconds": 1.2},
    "captions": {
        "font_name": "Arial", "bold": True, "fontsize": 92,
        "primary_color": "#FFFFFF", "highlight_color": "#FFD400", "outline_color": "#000000",
        "outline": 6, "shadow": 2, "max_words": 3, "position": 0.72,
    },
    "pexels": {"orientation": "portrait", "per_page": 8, "min_clip_seconds": 3},
    "music": {"enabled": False, "path": "", "volume": 0.12},
    "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0.95},
    "paths": {"data": "data", "output": "output", "broll_cache": "data/broll"},
    "server": {"host": "127.0.0.1", "threads": 8},
    "logging": {"level": "INFO", "max_bytes": 1048576, "backups": 5},
    "youtube": {"default_action": "schedule", "default_privacy": "private", "category_id": 22},
    "analytics": {"enabled": True},
    "scheduling": {"reconciler_enabled": False},
}


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


_SETTINGS_FILE = "settings.json"


def _sanitize_overlay(raw: dict) -> dict:
    """Whitelist the user-writable overlay to niche / search.keywords / voice.name.

    A hand-edited settings.json must never be able to redirect paths, secrets, or
    the DB location — only these three content keys are honoured.
    """
    out: dict = {}
    if isinstance(raw, dict):
        if isinstance(raw.get("niche"), str):
            out["niche"] = raw["niche"]
        search = raw.get("search")
        if isinstance(search, dict) and isinstance(search.get("keywords"), list):
            out["search"] = {"keywords": [str(k) for k in search["keywords"] if isinstance(k, str)]}
        voice = raw.get("voice")
        if isinstance(voice, dict) and isinstance(voice.get("name"), str):
            out["voice"] = {"name": voice["name"]}
    return out


def _read_overlay(state_dir) -> dict:
    p = Path(state_dir) / _SETTINGS_FILE
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load_config(path: str | None = None) -> dict:
    import copy
    cfg = copy.deepcopy(DEFAULTS)
    p = Path(path) if path else ROOT / "config.yaml"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(cfg, user)
    # resolve + create folders
    for key, rel in cfg["paths"].items():
        abs_path = (ROOT / rel).resolve()
        abs_path.mkdir(parents=True, exist_ok=True)
        cfg["paths"][key] = str(abs_path)

    # Durable state (SQLite DB, logs, OAuth secrets) must live OUTSIDE the project
    # dir: the project is inside OneDrive, which syncs to the cloud, and tokens /
    # client secrets / the DB must never sync. LOCALAPPDATA does not roam/sync.
    override = os.getenv("VIRAL_STATE_DIR") or cfg.get("state_dir")
    if override:
        state = Path(os.path.abspath(os.path.expanduser(str(override))))
    else:
        local = os.getenv("LOCALAPPDATA")
        base = (Path(local) / "ViralContent") if local else (Path.home() / ".viral-content")
        # abspath (not resolve): Microsoft Store Python redirects AppData\Local via a
        # reparse point that resolve() only follows once the dir exists, which would make
        # the path flip between sessions. abspath normalizes without following it.
        state = Path(os.path.abspath(base))
    for sub in ("", "logs", "secrets"):
        (state / sub).mkdir(parents=True, exist_ok=True)
    cfg["paths"]["state"] = str(state)
    cfg["paths"]["logs"] = str(state / "logs")
    cfg["paths"]["secrets"] = str(state / "secrets")
    cfg["db_path"] = str(state / "app.db")

    # User settings overlay (niche / keywords / voice) written from the dashboard.
    # Highest precedence — beats config.yaml and DEFAULTS. Whitelisted (above) so it
    # can never redirect paths, secrets, or the DB location.
    _deep_merge(cfg, _sanitize_overlay(_read_overlay(state)))
    return cfg


def env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name, default)
    return val.strip() if isinstance(val, str) else val


def slugify(text: str, max_len: int = 50) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "video").lower()).strip()
    text = re.sub(r"[\s_-]+", "-", text)
    return (text[:max_len].strip("-")) or "video"


def niche_tag(niche: str | None) -> str:
    """A safe single hashtag from a niche name: 'personal finance' -> '#personalfinance'. '' if empty."""
    s = re.sub(r"[^a-z0-9]", "", (niche or "").lower())
    return f"#{s}" if s else ""


def save_user_settings(cfg: dict, updates: dict) -> dict:
    """Merge validated updates into the on-disk settings overlay (atomic write).

    Returns the sanitized overlay that was written. Only niche / search.keywords /
    voice.name are ever persisted (see _sanitize_overlay). The overlay lives in the
    out-of-OneDrive state dir alongside the DB.
    """
    state_dir = Path(cfg["paths"]["state"])
    merged = _deep_merge(_sanitize_overlay(_read_overlay(state_dir)), _sanitize_overlay(updates))
    path = state_dir / _SETTINGS_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return merged
