"""The generation chain: user input -> keywords -> live research -> synthesized prompt.

Turns a plain-language brief into (a) focused search keywords, (b) a live YouTube
trend read on those keywords, and (c) an ORIGINAL, editable creative prompt the user
tweaks before the script is written. Every LLM step degrades to a transparent
built-in fallback, and the result records whether Gemini or a template produced it,
so the user always knows how a draft was made.
"""
from __future__ import annotations

import re

from . import llm, research
from .research import _STOPWORDS
from .settings import niche_tag


def _keywords_from_text(text: str, niche: str, limit: int = 6) -> list[str]:
    """No-LLM fallback: pull salient words from the brief (then the niche)."""
    seen: set[str] = set()
    out: list[str] = []
    for source in (text or "", niche or ""):
        for w in re.findall(r"[a-z0-9']+", source.lower()):
            if len(w) > 2 and w not in _STOPWORDS and w not in seen:
                seen.add(w)
                out.append(w)
    return out[:limit] or [(niche or "shorts").strip()]


def derive_keywords(cfg: dict, user_input: str) -> dict:
    """Turn the creator's brief into concrete YouTube search phrases + framing."""
    niche = cfg.get("niche") or "content"
    ui = (user_input or "").strip()
    if llm.available():
        prompt = (
            f"Niche: {niche}.\n"
            f"Creator's brief: {ui or niche}\n\n"
            "Plan the research for a short-form video on this brief. Return ONLY JSON:\n"
            '{"keywords": ["4-6 concrete YouTube search phrases people actually type"], '
            '"audience": "who this is for, one line", '
            '"promise": "the single payoff the viewer gets, one line", '
            '"angles": ["2-4 fresh angle seeds"]}\n'
            "Keywords must be specific to THIS brief (not generic niche words), 1-4 words each."
        )
        try:
            data = llm.generate_json(
                prompt, system=f"You are a short-form content researcher for a {niche} channel.",
                model=cfg["llm"]["model"], temperature=0.7,
            )
            kws = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
            if kws:
                return {
                    "keywords": kws[:6],
                    "audience": str(data.get("audience") or "").strip(),
                    "promise": str(data.get("promise") or "").strip(),
                    "angles": [str(a).strip() for a in (data.get("angles") or []) if str(a).strip()],
                    "used_llm": True,
                }
        except Exception as e:
            print(f"  (keyword derivation failed: {e}; using text extraction.)")
    return {"keywords": _keywords_from_text(ui, niche), "audience": "", "promise": "",
            "angles": [], "used_llm": False}


def _research_digest(report: dict | None) -> dict:
    """Compact, model- and UI-friendly summary of a scan report."""
    if not report:
        return {"title_words": [], "hashtags": [], "median_duration_s": 0, "top_titles": [], "sample_size": 0}
    p = report.get("patterns", {}) or {}
    titles = [v.get("title", "") for v in (report.get("videos") or [])[:8] if v.get("title")]
    return {
        "title_words": [w for w, _ in p.get("title_words", [])[:15]],
        "hashtags": [h for h, _ in p.get("hashtags", [])[:12]],
        "median_duration_s": p.get("median_duration_s", 0),
        "top_titles": titles,
        "sample_size": p.get("sample_size", 0),
    }


def _template_brief(niche: str, ui: str, derived: dict, target: int) -> dict:
    """No-LLM fallback brief — a clearly-labeled scaffold to edit, never canned motivation."""
    kws = derived.get("keywords", [])
    tag = niche_tag(niche)
    pool = ([tag] if tag else []) + ["#shorts", "#tips"]
    prompt_text = (
        f"Write an original faceless {niche} short about: {ui or niche}. "
        f"Speak to {derived.get('audience') or 'anyone starting out'}. "
        f"Deliver this payoff: {derived.get('promise') or 'one clear, useful takeaway'}. "
        "Open with a 1-second hook, make 3-4 concrete points, close with a memorable line. "
        "Keep it original — do not copy any trending title or phrasing."
    )
    return {
        "working_title": (ui[:60] or f"The truth about {niche}"),
        "hook_angle": f"A fresh, practical take on {ui or niche}.",
        "tone": "direct and encouraging",
        "structure": ["Hook (1s)", "Set up the problem", "Reveal the insight", "Make it concrete", "Strong close"],
        "key_points": kws[:5] or [ui or niche],
        "avoid": ["copying trending titles", "vague cliches", "padding"],
        "hashtag_pool": pool,
        "target_seconds": target,
        "prompt_text": prompt_text,
        "used_llm": False,
    }


def synthesize_prompt(cfg: dict, user_input: str, derived: dict, report: dict | None) -> dict:
    """Combine the brief + derived keywords + live trend signal into an ORIGINAL, editable prompt."""
    niche = cfg.get("niche") or "content"
    ui = (user_input or "").strip()
    dg = _research_digest(report)
    target = int((cfg["video"]["min_seconds"] + cfg["video"]["max_seconds"]) / 2)
    if llm.available():
        prompt = (
            f"Niche: {niche}\n"
            f"Creator's brief: {ui or niche}\n"
            f"Derived keywords: {', '.join(derived.get('keywords', []))}\n"
            f"Audience: {derived.get('audience') or 'general'}\n"
            f"Promise: {derived.get('promise') or '(none given)'}\n\n"
            "LIVE trend signal on these keywords (STUDY the patterns, NEVER copy):\n"
            f"- Title words that keep appearing: {', '.join(dg['title_words']) or 'n/a'}\n"
            f"- Common hashtags: {', '.join(dg['hashtags']) or 'n/a'}\n"
            f"- Median top-performer length: {dg['median_duration_s']}s\n"
            f"- Example titles (do NOT reuse their wording): {' | '.join(dg['top_titles'][:6]) or 'n/a'}\n\n"
            "Synthesize an ORIGINAL creative brief for a faceless short. Return ONLY JSON:\n"
            '{"working_title": "<=60 chars, original (never copy an example title)", '
            '"hook_angle": "the fresh take + the 1-second hook idea", '
            '"tone": "e.g. urgent, calm-authoritative, playful", '
            '"structure": ["4-7 short beat-outline lines"], '
            '"key_points": ["3-5 substantive points to make"], '
            '"avoid": ["what NOT to do - cliches / anything that copies the examples"], '
            '"hashtag_pool": ["6-8 relevant tags"], '
            f'"target_seconds": {target}, '
            '"prompt_text": "a tight paragraph the scriptwriter will follow: the original angle, who it is for, '
            'the payoff, and the vibe"}\n'
            "prompt_text must be self-contained and ORIGINAL. Never instruct to copy any example title or phrasing."
        )
        try:
            data = llm.generate_json(
                prompt,
                system=f"You are a viral short-form strategist for a {niche} channel who creates ORIGINAL concepts, never copies.",
                model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"],
            )
            if isinstance(data, dict) and (data.get("prompt_text") or data.get("hook_angle")):
                for k in ("structure", "key_points", "avoid", "hashtag_pool"):
                    data[k] = [str(x).strip() for x in (data.get(k) or []) if str(x).strip()]
                data["working_title"] = str(data.get("working_title") or (ui[:60] or niche)).strip()
                data["hook_angle"] = str(data.get("hook_angle") or "").strip()
                data["tone"] = str(data.get("tone") or "").strip()
                data["prompt_text"] = str(data.get("prompt_text") or "").strip()
                try:
                    data["target_seconds"] = int(data.get("target_seconds") or target)
                except (TypeError, ValueError):
                    data["target_seconds"] = target
                data["used_llm"] = True
                return data
        except Exception as e:
            print(f"  (prompt synthesis failed: {e}; using template brief.)")
    return _template_brief(niche, ui, derived, target)


def research_and_synthesize(cfg: dict, user_input: str, on_step=None) -> dict:
    """Full step-1 chain: derive keywords -> live research -> synthesize an editable prompt.

    Never raises for a research failure: it records a warning and synthesizes from AI
    knowledge instead, so the user is never stuck at the checkpoint.
    """
    def step(key: str, label: str):
        if on_step:
            on_step(key, label)

    step("derive", "Deriving search keywords from your brief...")
    derived = derive_keywords(cfg, user_input)

    step("research", "Researching live YouTube trends for: " + ", ".join(derived["keywords"][:6]))
    report, research_used, warning = None, False, ""
    try:
        report = research.research_keywords(cfg, derived["keywords"])
        research_used = bool((report or {}).get("videos"))
        if not research_used:
            warning = "No trending videos matched those keywords — synthesized from AI knowledge."
    except Exception as e:
        warning = f"Live research unavailable ({e}) — synthesized from AI knowledge."

    step("synthesize", "Synthesizing an original creative prompt...")
    brief = synthesize_prompt(cfg, user_input, derived, report)

    step("compose_done", brief.get("working_title") or "Concept ready")
    return {
        "input": (user_input or "").strip(),
        "keywords": derived["keywords"],
        "audience": derived.get("audience", ""),
        "promise": derived.get("promise", ""),
        "research": _research_digest(report),
        "brief": brief,
        "used_llm": bool(brief.get("used_llm")),
        "research_used": research_used,
        "warning": warning,
    }
