"""End-to-end: topic -> script -> voice -> b-roll -> captions -> assembled video + metadata."""
from __future__ import annotations

import json
from pathlib import Path

from . import assemble, captions, ffmpegutil, metadata, script as script_mod, visuals, voice
from .settings import slugify


def _unique_path(directory: Path, slug: str, ext: str) -> Path:
    p = directory / f"{slug}.{ext}"
    n = 2
    while p.exists():
        p = directory / f"{slug}-{n}.{ext}"
        n += 1
    return p


def make_video(cfg: dict, topic: str | None = None, verbose: bool = True, on_step=None,
               brief=None, brief_meta: dict | None = None) -> dict:
    def say(msg: str):
        if verbose:
            print(msg)

    def step(key: str, label: str):
        """Emit a machine-readable step for UIs, plus the human line for the CLI."""
        say(f"  - {label}")
        if on_step:
            on_step(key, label)

    out_dir = Path(cfg["paths"]["output"])
    data_dir = Path(cfg["paths"]["data"])

    step("script", "Writing script...")
    scr = script_mod.build_script(cfg, topic, brief=brief)
    beats = scr["beats"]
    narration_text = " ".join(b["text"] for b in beats)
    slug = slugify(scr["title"])
    say(f"    title: {scr['title']}  ({len(beats)} beats)")
    if on_step:
        on_step("script_done", scr["title"])

    narration_mp3 = str(data_dir / f"{slug}.narration.mp3")
    step("voice", "Generating voiceover (edge-tts)...")
    words = voice.narrate(cfg, narration_text, narration_mp3)

    step("broll", "Fetching b-roll...")
    broll = visuals.fetch_broll(cfg, beats)

    step("captions", "Building captions...")
    ass_text = captions.to_ass(words, cfg)

    out_mp4 = _unique_path(out_dir, slug, "mp4")
    step("assemble", "Assembling video with ffmpeg (this is the slow step)...")
    info = assemble.assemble_video(cfg, broll, beats, narration_mp3, ass_text, str(out_mp4))

    # thumbnail + review artifacts
    stem = out_mp4.with_suffix("")
    thumb = str(stem) + ".thumb.jpg"
    try:
        ffmpegutil.extract_thumbnail(str(out_mp4), thumb, at_seconds=1.0)
    except Exception:
        thumb = None

    meta = metadata.build_metadata(scr, cfg.get("niche"))
    meta_path = str(stem) + ".metadata.json"
    Path(meta_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    script_txt = str(stem) + ".script.txt"
    Path(script_txt).write_text(
        f"{scr['title']}\n\n"
        + "\n".join(f"- {b['text']}   [{b['broll_query']}]" for b in beats)
        + "\n\n"
        + " ".join(scr.get("hashtags", [])),
        encoding="utf-8",
    )

    # Provenance sidecar: how this draft was made (keywords, live research, the
    # synthesized brief, and whether Gemini or a template wrote it). Powers the
    # Review "how it was made" trace + the AI-vs-template badge.
    if brief_meta is not None:
        payload = dict(brief_meta)
        payload["generator"] = scr.get("generator")
        Path(str(stem) + ".brief.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "title": scr["title"],
        "video": str(out_mp4),
        "thumbnail": thumb,
        "metadata": meta_path,
        "script": script_txt,
        "duration": info["duration"],
        "narration_duration": info["narration_duration"],
    }
