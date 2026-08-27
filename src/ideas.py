"""Turn trend patterns into ORIGINAL video concepts (not copies of what's trending)."""
from __future__ import annotations

import json
from pathlib import Path

from . import fallback_scripts, llm


def _system(niche: str) -> str:
    return (
        f"You are a viral short-form content strategist for a faceless {niche} "
        "channel. You produce ORIGINAL concepts inspired by trends — never copies. Every idea must have "
        "a fresh angle, a scroll-stopping hook, and real substance so it stays monetizable under YouTube's "
        "originality rules."
    )


def generate_ideas(cfg: dict, count: int = 8, brief: str | None = None) -> list[dict]:
    trends_path = Path(cfg["paths"]["data"]) / "trends.json"
    trend_hint = ""
    if trends_path.exists():
        try:
            t = json.loads(trends_path.read_text(encoding="utf-8"))
            words = ", ".join(w for w, _ in t.get("patterns", {}).get("title_words", [])[:15])
            titles = "\n".join(f"- {v['title']}" for v in t.get("videos", [])[:15])
            trend_hint = f"\nTrending title words: {words}\nExamples of what's working (do NOT copy):\n{titles}\n"
        except Exception:
            pass

    brief = (brief or "").strip()
    brief_hint = (f"\nCreator's direction for this batch (lean into it, stay original): {brief}\n"
                  if brief else "")

    ideas: list[dict] = []
    if llm.available():
        prompt = (
            f"Niche: {cfg['niche']}.{brief_hint}{trend_hint}\n"
            f"Generate {count} ORIGINAL short-video concepts. Return ONLY a JSON array; each item:\n"
            '{"title": "...", "hook": "first spoken line, must grab in 1 second", '
            '"angle": "the fresh take / why it is different", '
            '"hashtags": ["#..", ".."]}\n'
            "Titles under 60 chars. No numbering. No commentary."
        )
        try:
            data = llm.generate_json(prompt, system=_system(cfg["niche"]), model=cfg["llm"]["model"],
                                     temperature=cfg["llm"]["temperature"])
            if isinstance(data, list):
                ideas = [d for d in data if isinstance(d, dict) and d.get("title")]
        except Exception as e:
            print(f"  (Gemini idea generation failed: {e}; using built-in concepts.)")

    if not ideas:
        ideas = fallback_scripts.fallback_ideas(cfg["niche"], count)

    (Path(cfg["paths"]["data"]) / "ideas.json").write_text(json.dumps(ideas, indent=2), encoding="utf-8")
    return ideas
