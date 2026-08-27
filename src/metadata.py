"""Build platform-tailored titles, descriptions, and hashtags for one video."""
from __future__ import annotations

from .settings import niche_tag


def _tags(hashtags: list[str]) -> list[str]:
    return [h.lstrip("#") for h in hashtags if h]


def build_metadata(script: dict, niche: str | None = None) -> dict:
    niche = (niche or "content").strip()
    tag = niche_tag(niche)
    default_tags = ([tag] if tag else []) + ["#shorts"]
    title = script["title"]
    hashtags = script.get("hashtags") or default_tags
    hook = script["beats"][0]["text"] if script.get("beats") else title
    tag_line = " ".join(hashtags)

    yt_title = title if len(title) <= 100 else title[:97] + "..."
    if "#shorts" not in [h.lower() for h in hashtags]:
        hashtags_yt = hashtags + ["#Shorts"]
    else:
        hashtags_yt = hashtags

    yt_desc = (
        f"{hook}\n\n"
        f"New {niche} shorts regularly — subscribe for more.\n\n"
        f"{' '.join(hashtags_yt)}"
    )

    return {
        "youtube": {
            "title": yt_title,
            "description": yt_desc,
            "tags": _tags(hashtags_yt),
            "made_for_kids": False,
            "category": "People & Blogs",
        },
        "tiktok": {"caption": f"{hook} {tag_line} #fyp #foryou"[:150]},
        "facebook": {"caption": f"{hook}\n\n{tag_line}"},
        "instagram": {"caption": f"{hook}\n\n{tag_line} #reels"},
    }
