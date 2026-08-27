"""Per-render creative controls: style presets + resolution + length target.

The whole render pipeline is cfg-driven (see src/pipeline.py, src/assemble.py,
src/captions.py), so a render "look" is just a modified copy of the config. This
module owns the small option tables the Create UI offers and the pure function
that turns a (style, resolution, duration) choice into a deep-copied cfg with the
right video/caption overrides — WITHOUT touching the shared global CFG.

Design note: caption sizes are in ASS PlayResY pixels (= video height), so when
the resolution drops below 1080-wide we scale fontsize/outline/shadow by
width/1080, or the captions render proportionally huge.
"""
from __future__ import annotations

import copy

# Up to 4 styles. "classic" carries no caption overrides -> keeps whatever the
# user has configured (today's look), so it is the safe default.
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

# id -> (width, height, label)
RESOLUTIONS: dict[str, tuple[int, int, str]] = {
    "1080x1920": (1080, 1920, "1080×1920 · Full HD"),
    "720x1280": (720, 1280, "720×1280 · HD (faster)"),
}

DURATIONS: tuple[int, ...] = (30, 45, 60)  # seconds; all >= the 30s monetization floor

DEFAULTS = {"style": "classic", "resolution": "1080x1920", "duration": 45}

_SCALE_KEYS = ("fontsize", "outline", "shadow")


def options_payload() -> dict:
    """Everything the Create UI needs to build the three pickers."""
    return {
        "styles": [{"id": k, "label": v["label"]} for k, v in STYLE_PRESETS.items()],
        "resolutions": [{"id": k, "label": lbl, "width": w, "height": h}
                        for k, (w, h, lbl) in RESOLUTIONS.items()],
        "durations": list(DURATIONS),
        "defaults": dict(DEFAULTS),
    }


def build_render_cfg(base_cfg: dict, style, resolution, duration):
    """Validate a (style, resolution, duration) choice and return a deep-copied
    cfg with video/caption overrides applied, plus a small meta dict to persist.

    Returns (render_cfg, meta) or None if any choice is invalid. NEVER mutates
    base_cfg — the shared global CFG must stay untouched (routes + in-flight jobs
    read it by name).
    """
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

    # 1) style — layer preset captions over the configured ones (classic = no-op)
    rc["captions"].update(STYLE_PRESETS[style]["captions"])

    # 2) resolution — drives both the ffmpeg scale/crop and the ASS PlayResX/Y
    w, h, _ = RESOLUTIONS[resolution]
    rc["video"]["width"] = w
    rc["video"]["height"] = h
    scale = w / 1080.0
    if scale != 1.0:
        for k in _SCALE_KEYS:
            val = rc["captions"].get(k)
            if isinstance(val, (int, float)):
                rc["captions"][k] = max(1, round(val * scale))

    # 3) length target — min_seconds is the real assemble floor; max_seconds feeds
    #    the script word-count band. Actual length still tracks narration (no hard cap).
    rc["video"]["min_seconds"] = duration
    rc["video"]["max_seconds"] = duration

    return rc, {"style": style, "width": w, "height": h, "duration": duration}
