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


def _brief_block(brief) -> str:
    """Render a synthesized creative brief (dict) or edited prompt (str) as the primary instruction."""
    if not brief:
        return ""
    if isinstance(brief, str):
        return f"\nFollow this creative brief — it is your PRIMARY instruction:\n{brief.strip()}\n"
    lines = []
    if brief.get("prompt_text"):
        lines.append(brief["prompt_text"].strip())
    if brief.get("hook_angle"):
        lines.append(f"Angle / hook: {brief['hook_angle']}")
    if brief.get("tone"):
        lines.append(f"Tone: {brief['tone']}")
    if brief.get("structure"):
        lines.append("Structure: " + " | ".join(brief["structure"]))
    if brief.get("key_points"):
        lines.append("Key points: " + "; ".join(brief["key_points"]))
    if brief.get("avoid"):
        lines.append("Avoid: " + "; ".join(brief["avoid"]))
    if brief.get("hashtag_pool"):
        lines.append("Hashtag pool (choose 5-6): " + " ".join(brief["hashtag_pool"]))
    body = "\n".join(f"- {ln}" for ln in lines if ln)
    return f"\nFollow this creative brief — it is your PRIMARY instruction:\n{body}\n" if body else ""


def build_script(cfg: dict, topic: str | None = None, brief=None) -> dict:
    """topic is a plain idea string or an ideas.json title; brief (optional) is a
    synthesized creative brief dict or an edited prompt string that dominates the write.

    The returned script carries a private "generator" key ("gemini" | "fallback") so
    callers can honestly report how the draft was produced.
    """
    niche = cfg.get("niche") or "content"
    if llm.available():
        v = cfg["video"]
        target = int((v["min_seconds"] + v["max_seconds"]) / 2)  # seconds
        lo, hi = round(target * 2.3), round(target * 2.7)         # ~2.3-2.7 words/sec spoken
        prompt = (
            f"Write an ORIGINAL faceless {niche} Short script.\n"
            f"Topic / angle: {topic or niche}\n"
            f"{_brief_block(brief)}"
            f"Target spoken length: about {target}s (~{lo}-{hi} words).\n"
            "Return ONLY JSON:\n"
            '{"title": "<60 chars, curiosity or bold claim", '
            '"hashtags": ["#..", "5-6 relevant tags"], '
            '"beats": [{"text": "one spoken line", "broll_query": "2-4 words to find cinematic vertical stock video"}]}\n'
            "Rules: 6-8 beats. Beat 1 is the hook (grabs in 1 second). Last beat is a strong close. "
            "Each text line 4-14 words. broll_query must be concrete and filmable — a specific visible "
            "scene, not an abstract word."
        )
        try:
            data = llm.generate_json(prompt, system=_system(niche), model=cfg["llm"]["model"],
                                     temperature=cfg["llm"]["temperature"])
            script = _normalize(data, niche)
            if len(script["beats"]) >= 3:
                script["generator"] = "gemini"
                return script
            print("  (Gemini returned too few beats; using built-in script.)")
        except Exception as e:
            print(f"  (Gemini script generation failed: {e}; using built-in script.)")

    script = dict(fallback_scripts.pick(topic, niche))  # copy so we never mutate the shared bank
    script["generator"] = "fallback"
    return script
