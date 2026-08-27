"""Viral research via the YouTube Data API v3 (REST, free 10k units/day).

Finds recent, fast-growing videos in your niche, ranks them by VIEW VELOCITY
(views per day since upload), and extracts the patterns worth copying: title
formulas, common hooks/words, hashtags, and ideal duration.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .settings import env

_SEARCH = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"

_STOPWORDS = set(
    "the a an and or but for to of in on at is are be you your my our their this that with "
    "how why what when it its from as by no not do does can will just get got make made i me "
    "we they he she his her them if so up out about into more most than then now new vs".split()
)


def _iso_duration_to_seconds(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mn, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mn * 60 + s


def _search_ids(key: str, keyword: str, cfg: dict) -> list[str]:
    s = cfg["search"]
    published_after = (datetime.now(timezone.utc) - timedelta(days=s["published_within_days"])).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    params = {
        "key": key, "part": "snippet", "q": keyword, "type": "video",
        "order": "viewCount", "maxResults": min(s["max_results"], 50),
        "publishedAfter": published_after, "regionCode": s["region"],
        "relevanceLanguage": s["language"], "videoDuration": "short",
    }
    r = requests.get(_SEARCH, params=params, timeout=30)
    r.raise_for_status()
    return [it["id"]["videoId"] for it in r.json().get("items", []) if it.get("id", {}).get("videoId")]


def _video_details(key: str, ids: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        r = requests.get(
            _VIDEOS,
            params={"key": key, "part": "statistics,contentDetails,snippet", "id": ",".join(chunk)},
            timeout=30,
        )
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out


def run_research(cfg: dict) -> dict:
    key = env("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError(
            "YOUTUBE_API_KEY not set. Add it to your .env (see .env.example for the free setup steps)."
        )

    seen: dict[str, dict] = {}
    now = datetime.now(timezone.utc)
    for kw in cfg["search"]["keywords"]:
        try:
            ids = _search_ids(key, kw, cfg)
        except requests.HTTPError as e:
            raise RuntimeError(f"YouTube API error while searching '{kw}': {e}") from e
        for v in _video_details(key, ids):
            vid = v["id"]
            if vid in seen:
                continue
            stats, snip, cd = v.get("statistics", {}), v.get("snippet", {}), v.get("contentDetails", {})
            views = int(stats.get("viewCount", 0))
            if views < cfg["search"]["min_views"]:
                continue
            published = datetime.fromisoformat(snip["publishedAt"].replace("Z", "+00:00"))
            days = max((now - published).total_seconds() / 86400, 0.5)
            dur = _iso_duration_to_seconds(cd.get("duration", ""))
            title = snip.get("title", "")
            desc = snip.get("description", "")
            seen[vid] = {
                "id": vid,
                "url": f"https://youtube.com/watch?v={vid}",
                "title": title,
                "channel": snip.get("channelTitle", ""),
                "views": views,
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_s": dur,
                "days_old": round(days, 1),
                "views_per_day": int(views / days),
                "is_short": dur <= 180 and ("#shorts" in (title + desc).lower() or dur <= 60),
                "hashtags": re.findall(r"#\w+", (title + " " + desc).lower()),
                "matched_keyword": kw,
            }

    videos = sorted(seen.values(), key=lambda x: x["views_per_day"], reverse=True)
    patterns = _extract_patterns(videos)
    report = {"generated_at": now.isoformat(), "niche": cfg["niche"], "videos": videos, "patterns": patterns}

    data_dir = Path(cfg["paths"]["data"])
    (data_dir / "trends.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (data_dir / "trend_report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def research_keywords(cfg: dict, keywords: list[str]) -> dict:
    """Research specific keywords (used by the generation chain)."""
    import copy
    cfg2 = copy.deepcopy(cfg)
    cfg2["search"]["keywords"] = keywords
    return run_research(cfg2)


def _extract_patterns(videos: list[dict]) -> dict:
    if not videos:
        return {"title_words": [], "hashtags": [], "median_duration_s": 0, "sample_size": 0}
    words = Counter()
    tags = Counter()
    durations = []
    for v in videos:
        for w in re.findall(r"[a-z']+", v["title"].lower()):
            if len(w) > 2 and w not in _STOPWORDS:
                words[w] += 1
        tags.update(v["hashtags"])
        if v["duration_s"]:
            durations.append(v["duration_s"])
    durations.sort()
    median = durations[len(durations) // 2] if durations else 0
    return {
        "title_words": words.most_common(20),
        "hashtags": tags.most_common(15),
        "median_duration_s": median,
        "sample_size": len(videos),
    }


def _render_markdown(report: dict) -> str:
    p = report["patterns"]
    lines = [
        f"# Viral trend report — {report['niche']}",
        f"_Generated {report['generated_at']}  •  {p['sample_size']} videos analyzed_",
        "",
        "## What's working right now",
        f"- **Ideal length:** ~{p['median_duration_s']}s (median of top performers)",
        "- **Title words that keep appearing:** " + ", ".join(f"`{w}` ({n})" for w, n in p["title_words"][:12]),
        "- **Top hashtags:** " + (", ".join(f"{t} ({n})" for t, n in p["hashtags"][:12]) or "—"),
        "",
        "## Top videos by view-velocity (views/day)",
        "",
        "| Views/day | Views | Age (d) | Len | Title | Channel |",
        "|---:|---:|---:|---:|---|---|",
    ]
    for v in report["videos"][:30]:
        title = v["title"].replace("|", "\\|")[:70]
        lines.append(
            f"| {v['views_per_day']:,} | {v['views']:,} | {v['days_old']} | {v['duration_s']}s "
            f"| [{title}]({v['url']}) | {v['channel'][:20]} |"
        )
    lines += ["", "> Study the top hooks, then create something ORIGINAL in that lane — never copy.",]
    return "\n".join(lines)
