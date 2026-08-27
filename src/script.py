"""Generate a 30-60s narration script broken into beats, each with a b-roll query.

Uses Gemini when available, otherwise the built-in original script bank.
Output shape (stable contract for the rest of the pipeline):
    {"title": str, "hashtags": [str], "beats": [{"text": str, "broll_query": str}]}
"""
from __future__ import annotations

from . import fallback_scripts, llm
from .settings import niche_tag


def _system(niche: str) -> str:
    return (
        f"You are a scriptwriter for faceless {niche} Shorts. You write punchy, original, spoken-word "
        "scripts with a 1-second hook, a clear through-line, a satisfying build, and a memorable closing "
        "line. Every line is short enough to say in one breath. You never plagiarize."
    )


def _normalize(data: dict, niche: str) -> dict:
    default_q = f"cinematic {niche}"
    beats = []
    for b in data.get("beats", []):
        if isinstance(b, dict) and b.get("text"):
            beats.append({"text": str(b["text"]).strip(),
                          "broll_query": str(b.get("broll_query") or b.get("query") or default_q).strip()})
        elif isinstance(b, str) and b.strip():
            beats.append({"text": b.strip(), "broll_query": default_q})
    tag = niche_tag(niche)
    return {
        "title": (data.get("title") or "Untitled").strip(),
        "hashtags": data.get("hashtags") or (([tag] if tag else []) + ["#shorts"]),
        "beats": beats,
    }


def build_script(cfg: dict, topic: str | None = None, brief: str | None = None) -> dict:
    niche = cfg.get("niche") or "content"
    if llm.available():
        v = cfg["video"]
        target = int((v["min_seconds"] + v["max_seconds"]) / 2)
        lo, hi = round(target * 2.3), round(target * 2.7)
        prompt = (
            f"Write an ORIGINAL faceless {niche} Short script.\n"
            f"Topic / angle: {topic or niche}\n"
            f"Target spoken length: about {target}s (~{lo}-{hi} words).\n"
            "Return ONLY JSON:\n"
            '{"title": "<60 chars, curiosity or bold claim", '
            '"hashtags": ["#..", "5-6 relevant tags"], '
            '"beats": [{"text": "one spoken line", "broll_query": "2-4 words to find cinematic vertical stock video"}]}\n'
            "Rules: 6-8 beats. Beat 1 is the hook (grabs in 1 second). Last beat is a strong close. "
            "Each text line 4-14 words. broll_query must be concrete and filmable."
        )
        if brief:
            prompt = f"Creative brief:\n{brief}\n\n" + prompt
        try:
            data = llm.generate_json(prompt, system=_system(niche), model=cfg["llm"]["model"],
                                     temperature=cfg["llm"]["temperature"])
            script = _normalize(data, niche)
            if len(script["beats"]) >= 3:
                return script
            print("  (Gemini returned too few beats; using built-in script.)")
        except Exception as e:
            print(f"  (Gemini script generation failed: {e}; using built-in script.)")

    return fallback_scripts.pick(topic, niche)
