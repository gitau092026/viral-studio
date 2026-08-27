"""Per-render creative controls: style presets + resolution + length target."""
from __future__ import annotations

import copy

STYLE_PRESETS: dict[str, dict] = {
    "classic": {"label": "Classic Center", "captions": {}},
    "impact": {
        "label": "Bold Impact",
        "captions": {"font_name": "Arial Black", "bold": True, "fontsize": 104,
                     "highlight_color": "#FFD400", "outline": 8, "shadow": 3,
                     "max_words": 3, "position": 0.70},
    },
    "clean": {
        "label": "Clean Minimal",
        "captions": {"font_name": "Arial", "bold": False, "fontsize": 78,
                     "primary_color": "#FFFFFF", "highlight_color": "#FFFFFF",
                     "outline": 4, "shadow": 1, "max_words": 4, "position": 0.82},
    },
    "neon": {
        "label": "Neon Pop",
        "captions": {"font_name": "Arial Black", "bold": True, "fontsize": 96,
                     "primary_color": "#FFFFFF", "highlight_color": "#43E6E0",
                     "outline": 7, "shadow": 3, "max_words": 2, "position": 0.66},
    },
}

RESOLUTIONS: dict[str, tuple[int, int, str]] = {
    "1080x1920": (1080, 1920, "1080×1920 · Full HD"),
    "720x1280": (720, 1280, "720×1280 · HD (faster)"),
}

DURATIONS: tuple[int, ...] = (30, 45, 60)

DEFAULTS = {"style": "classic", "resolution": "1080x1920", "duration": 45}

_SCALE_KEYS = ("fontsize", "outline", "shadow")


def options_payload() -> dict:
    return {
        "styles": [{"id": k, "label": v["label"]} for k, v in STYLE_PRESETS.items()],
        "resolutions": [{"id": k, "label": lbl, "width": w, "height": h}
                        for k, (w, h, lbl) in RESOLUTIONS.items()],
        "durations": list(DURATIONS),
        "defaults": dict(DEFAULTS),
    }


def build_render_cfg(base_cfg: dict, style, resolution, duration):
    if style not in STYLE_PRESETS or resolution not in RESOLUTIONS:
        return None
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        return None
    if duration not in DURATIONS:
        return None

    rc = copy.deepcopy(base_cfg)
    rc.setdefault("video", {})
    rc.setdefault("captions", {})

    rc["captions"].update(STYLE_PRESETS[style]["captions"])

    w, h, _ = RESOLUTIONS[resolution]
    rc["video"]["width"] = w
    rc["video"]["height"] = h
    scale = w / 1080.0
    if scale != 1.0:
        for k in _SCALE_KEYS:
            val = rc["captions"].get(k)
            if isinstance(val, (int, float)):
                rc["captions"][k] = max(1, round(val * scale))

    rc["video"]["min_seconds"] = duration
    rc["video"]["max_seconds"] = duration

    return rc, {"style": style, "width": w, "height": h, "duration": duration}
