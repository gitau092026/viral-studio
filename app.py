"""Local web dashboard for the Viral Content Agent.

A creator co-pilot UI over the existing pipeline:
    research -> ideas -> create -> REVIEW (human gate) -> publish / schedule

Run it:
    python app.py                # then open http://127.0.0.1:5177
    python run.py web            # same thing, opens your browser for you

Everything runs locally. Long jobs (research / render / upload) run on background
threads; the browser polls /api/jobs/<id> for live progress. Job outcomes, the
review-gate approval, the upload/schedule record, and analytics snapshots are
persisted in SQLite so they survive a restart.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from src import concept as concept_mod
from src import db
from src import ideas as ideas_mod
from src import llm
from src import logsetup
from src import pipeline
from src import render_styles
from src import research as research_mod
from src import voice as voice_mod
from src.ffmpegutil import ensure_on_path, probe_duration
from src.settings import env, load_config, save_user_settings

app = Flask(__name__, static_folder="static", template_folder="templates")
CFG = load_config()
logsetup.configure_logging(CFG)
db.init_db(CFG)
ensure_on_path()  # self-heal ffmpeg PATH so the app works from any shell
LOG = logging.getLogger("app")

# ---- job registry: in-memory for live step streaming, mirrored to SQLite -----
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _new_job(kind: str, topic: str | None = None) -> str:
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        JOBS[jid] = {"id": jid, "kind": kind, "status": "running",
                     "steps": [], "result": None, "error": None, "started": time.time()}
    db.create_job(jid, kind, topic)
    return jid


def _run(jid: str, fn):
    """Execute fn() on a worker thread, recording result/steps/errors (and persisting)."""
    def worker():
        try:
            result = fn(jid)
            with _LOCK:
                JOBS[jid]["result"] = result
                JOBS[jid]["status"] = "done"
            db.update_job(jid, "done", result_json=_safe_json(result))
        except Exception as e:  # surface the message to the UI, never crash the server
            LOG.exception("job %s (%s) failed", jid, JOBS.get(jid, {}).get("kind"))
            with _LOCK:
                JOBS[jid]["error"] = str(e)
                JOBS[jid]["status"] = "error"
            db.update_job(jid, "error", error=str(e))
    threading.Thread(target=worker, daemon=True).start()


def _push_step(jid: str, key: str, label: str):
    with _LOCK:
        if jid in JOBS:
            JOBS[jid]["steps"].append({"key": key, "label": label, "ts": round(time.time(), 2)})


def _safe_json(obj) -> str | None:
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return None


# ---- validation + safe errors ------------------------------------------------
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def _valid_topic(s) -> str | None:
    s = (s or "").strip()
    if not (1 <= len(s) <= 300) or _CONTROL.search(s):
        return None
    return s


def _valid_count(n, lo: int = 1, hi: int = 20) -> int | None:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _valid_prompt(s, max_len: int = 4000) -> str | None:
    """The edited creative prompt: a longer free-text field than a topic. Allows
    newlines/tabs (a prompt is multi-line), rejects other control chars, caps length.
    Empty -> None (absence is not an error; the direct render path sends no prompt)."""
    s = (s or "").strip()
    if not s:
        return None
    if len(s) > max_len or _CONTROL.search(s):
        return None
    return s


def _brief_meta_from_body(body: dict, edited_prompt: str | None) -> dict:
    """Bound + type-check the research provenance the client echoes back before it is
    written to the <stem>.brief.json sidecar and later shown verbatim in Review. Keeps
    the trace small and predictable regardless of what the client posts."""
    def _slist(v, n: int, cap: int) -> list:
        if not isinstance(v, list):
            return []
        return [str(x).strip()[:cap] for x in v if isinstance(x, str) and str(x).strip()][:n]

    def _int(v) -> int:
        return int(v) if isinstance(v, (int, float)) else 0

    r = body.get("research") if isinstance(body.get("research"), dict) else {}
    research = {
        "title_words": _slist(r.get("title_words"), 15, 40),
        "hashtags": _slist(r.get("hashtags"), 12, 40),
        "top_titles": _slist(r.get("top_titles"), 6, 120),
        "median_duration_s": _int(r.get("median_duration_s")),
        "sample_size": _int(r.get("sample_size")),
    }
    brief = body.get("brief") if isinstance(body.get("brief"), dict) else None
    return {
        "input": (str(body.get("input") or "").strip())[:300] or None,
        "edited_prompt": edited_prompt,
        "keywords": _slist(body.get("keywords"), 8, 60),
        "research": research,
        "brief": brief,
        "used_llm": bool(body.get("used_llm")),
        "research_used": bool(body.get("research_used")),
    }


# Curated edge-tts voices offered in the Settings modal. A hand-entered id is also
# accepted if it matches the edge-tts naming shape (see _valid_voice).
_VOICE_RE = re.compile(r"^[A-Za-z]{2}-[A-Za-z]{2}-[A-Za-z]+Neural$")
_VOICES = [
    {"id": "en-US-ChristopherNeural", "label": "Christopher — deep, confident (US male)"},
    {"id": "en-US-GuyNeural",         "label": "Guy — warm, natural (US male)"},
    {"id": "en-US-EricNeural",        "label": "Eric — calm, mature (US male)"},
    {"id": "en-US-AriaNeural",        "label": "Aria — friendly, clear (US female)"},
    {"id": "en-US-JennyNeural",       "label": "Jenny — casual, upbeat (US female)"},
    {"id": "en-GB-RyanNeural",        "label": "Ryan — refined (UK male)"},
    {"id": "en-GB-SoniaNeural",       "label": "Sonia — polished (UK female)"},
    {"id": "en-AU-NatashaNeural",     "label": "Natasha — bright (AU female)"},
]
_VOICE_IDS = {v["id"] for v in _VOICES}


def _valid_niche(s) -> str | None:
    s = (s or "").strip()
    if not (1 <= len(s) <= 80) or _CONTROL.search(s):
        return None
    return s


def _valid_keywords(v) -> list[str] | None:
    """A list of 1-12 non-empty keywords (<=40 chars each), de-duped case-insensitively."""
    if not isinstance(v, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in v:
        if not isinstance(item, str):
            return None
        k = item.strip()
        if not k:
            continue
        if len(k) > 40 or _CONTROL.search(k):
            return None
        low = k.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(k)
    return out if 1 <= len(out) <= 12 else None


def _valid_voice(s) -> str | None:
    """'' means 'leave the voice unchanged'; None means invalid. A real id must be
    curated or match the edge-tts shape (e.g. en-US-ChristopherNeural)."""
    s = (s or "").strip()
    if not s:
        return ""
    if s in _VOICE_IDS or _VOICE_RE.match(s):
        return s
    return None


def _safe_output_name(file) -> str | None:
    """Basename-only, must be an existing .mp4 in output/. Blocks path traversal."""
    if not file or not isinstance(file, str) or "/" in file or "\\" in file or ".." in file:
        return None
    name = Path(file).name
    if name != file or not name.lower().endswith(".mp4"):
        return None
    if not (Path(CFG["paths"]["output"]) / name).exists():
        return None
    return name


def _parse_future_iso(s) -> str | None:
    """Accept an ISO / datetime-local / RFC3339 string; return RFC3339 UTC if future."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # a naive datetime-local value is the user's local time
    dt_utc = dt.astimezone(timezone.utc)
    if dt_utc <= datetime.now(timezone.utc):
        return None
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _yt():
    """Import the YouTube module lazily. Returns (module, None) or (None, error_msg)."""
    try:
        from src import publish_youtube
        return publish_youtube, None
    except Exception as e:  # google libs not installed, etc.
        return None, f"YouTube libraries unavailable: {e}. Run: pip install -r requirements.txt"


# ---- pages ------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ---- status -----------------------------------------------------------------
@app.route("/api/status")
def api_status():
    return jsonify({
        "niche": CFG["niche"],
        "ffmpeg": ensure_on_path(),
        "youtube": bool(env("YOUTUBE_API_KEY")),
        "pexels": bool(env("PEXELS_API_KEY")),
        "gemini": llm.available(),
    })


# ---- settings: niche / keywords / voice (hot-reloads CFG in place) -----------
@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify({
        "niche": CFG["niche"],
        "keywords": CFG["search"]["keywords"],
        "voice": CFG["voice"]["name"],
        "voices": _VOICES,
        "gemini": llm.available(),
    })


@app.route("/api/settings", methods=["POST"])
def api_settings_set():
    body = request.get_json(silent=True) or {}
    niche = _valid_niche(body.get("niche"))
    if niche is None:
        return _bad("Niche is required (1-80 characters, no control characters).")
    keywords = _valid_keywords(body.get("keywords"))
    if keywords is None:
        return _bad("Provide 1-12 keywords, each 1-40 characters.")
    voice = _valid_voice(body.get("voice"))
    if voice is None:
        return _bad("Invalid voice selection.")

    updates = {"niche": niche, "search": {"keywords": keywords}}
    if voice:
        updates["voice"] = {"name": voice}
    try:
        save_user_settings(CFG, updates)
    except Exception as e:
        LOG.exception("failed to persist settings")
        return _bad(f"Could not save settings: {e}", 500)

    # Hot-reload in place: every route reads the CFG module-global by name, so
    # mutating it here propagates to all later requests and in-flight job closures.
    # Never touch path / secret / db keys — those are frozen at startup.
    CFG["niche"] = niche
    CFG["search"]["keywords"] = keywords
    if voice:
        CFG["voice"]["name"] = voice

    # Invalidate the niche-specific caches so the UI nudges a fresh scan.
    data_dir = Path(CFG["paths"]["data"])
    for fname in ("trends.json", "trend_report.md", "ideas.json"):
        try:
            (data_dir / fname).unlink(missing_ok=True)
        except OSError as e:
            LOG.warning("could not remove stale cache %s: %s", fname, e)

    LOG.info("settings updated: niche=%r, %d keywords, voice=%r",
             niche, len(keywords), CFG["voice"]["name"])
    return jsonify({"niche": niche, "keywords": keywords, "voice": CFG["voice"]["name"]})


# ---- voice preview: audition a narrator before you ever render ---------------
_VOICE_SAMPLE = ("This is how your voiceover will sound — clear, natural, "
                 "and ready to narrate your next short.")


@app.route("/api/voice/preview", methods=["POST"])
def api_voice_preview():
    """Synthesize a short sample of the requested voice and return it as mp3 bytes.

    Uses the *selected* voice with the configured rate/pitch/volume, so the preview
    matches how a real render will sound. Synchronous (one short sentence, ~1-2s) —
    the client shows a loading state and plays the returned audio."""
    body = request.get_json(silent=True) or {}
    voice = _valid_voice(body.get("voice"))
    if voice is None:
        return _bad("Invalid voice selection.")
    v = CFG["voice"]
    preview_cfg = {"voice": {
        "name": voice or v["name"],  # '' means "use the saved voice"
        "rate": v.get("rate", "+0%"),
        "pitch": v.get("pitch", "+0Hz"),
        "volume": v.get("volume", "+0%"),
    }}
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="voice-preview-")
        os.close(fd)  # narrate reopens the path; Windows can't share the handle
        voice_mod.narrate(preview_cfg, _VOICE_SAMPLE, tmp)
        data = Path(tmp).read_bytes()
    except Exception as e:  # network / edge-tts service error — surface, don't crash
        LOG.warning("voice preview failed for %r: %s", preview_cfg["voice"]["name"], e)
        return _bad(f"Could not synthesize a preview: {e}", 502)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return Response(data, mimetype="audio/mpeg", headers={"Cache-Control": "no-store"})


# ---- research ---------------------------------------------------------------
@app.route("/api/trends")
def api_trends():
    p = Path(CFG["paths"]["data"]) / "trends.json"
    if p.exists():
        return app.response_class(p.read_text(encoding="utf-8"), mimetype="application/json")
    return jsonify({"videos": [], "patterns": {}, "generated_at": None})


@app.route("/api/research", methods=["POST"])
def api_research():
    jid = _new_job("research")

    def job(_):
        _push_step(jid, "scan", "Scanning YouTube for view-velocity leaders...")
        report = research_mod.run_research(CFG)
        _push_step(jid, "done", f"Analyzed {len(report['videos'])} videos")
        return report

    _run(jid, job)
    return jsonify({"job_id": jid})


# ---- ideas ------------------------------------------------------------------
@app.route("/api/ideas")
def api_ideas():
    p = Path(CFG["paths"]["data"]) / "ideas.json"
    if p.exists():
        return app.response_class(p.read_text(encoding="utf-8"), mimetype="application/json")
    return jsonify([])


@app.route("/api/ideas", methods=["POST"])
def api_ideas_make():
    body = request.get_json(silent=True) or {}
    count = _valid_count(body.get("count", 8))
    if count is None:
        return _bad("count must be an integer 1-20.")
    brief = None
    raw = body.get("brief")
    if raw is not None and str(raw).strip():
        brief = _valid_topic(raw)
        if brief is None:
            return _bad("Brief must be 1-300 characters with no control characters.")
    jid = _new_job("ideas")

    def job(_):
        _push_step(jid, "think", "Turning trends into original concepts...")
        ideas = ideas_mod.generate_ideas(CFG, count=count, brief=brief)
        _push_step(jid, "done", f"{len(ideas)} concepts ready")
        return ideas

    _run(jid, job)
    return jsonify({"job_id": jid})


# ---- create / render --------------------------------------------------------
@app.route("/api/render-options")
def api_render_options():
    """Style presets + resolutions + length targets for the Create pickers."""
    return jsonify(render_styles.options_payload())


@app.route("/api/compose/research", methods=["POST"])
def api_compose_research():
    """Step 1 of the generation chain: your brief -> derived keywords -> live YouTube
    research -> an editable creative prompt. Streams derive/research/synthesize steps;
    never auto-writes a draft (the user edits the prompt, then calls /api/make)."""
    body = request.get_json(silent=True) or {}
    user_input = _valid_topic(body.get("input"))
    if user_input is None:
        return _bad("Tell me what the video should be about (1-300 characters).")
    jid = _new_job("compose", user_input)

    def job(_):
        return concept_mod.research_and_synthesize(
            CFG, user_input, on_step=lambda key, label: _push_step(jid, key, label),
        )

    _run(jid, job)
    return jsonify({"job_id": jid})


@app.route("/api/make", methods=["POST"])
def api_make():
    body = request.get_json(silent=True) or {}
    raw = body.get("topic")
    topic = None
    if raw is not None and str(raw).strip():
        topic = _valid_topic(raw)
        if topic is None:
            return _bad("Topic must be 1-300 characters with no control characters.")

    # Optional generation-chain inputs. The edited creative prompt (when present) is the
    # PRIMARY instruction the scriptwriter follows; keywords/research/brief ride along as
    # provenance for the <stem>.brief.json trace + the Review AI-vs-template badge.
    prompt = None
    if body.get("prompt") is not None and str(body.get("prompt")).strip():
        prompt = _valid_prompt(body.get("prompt"))
        if prompt is None:
            return _bad("The prompt must be under 4000 characters with no control characters.")
    brief_meta = _brief_meta_from_body(body, prompt) if (prompt or body.get("brief")) else None

    d = render_styles.DEFAULTS
    built = render_styles.build_render_cfg(
        CFG, body.get("style", d["style"]), body.get("resolution", d["resolution"]),
        body.get("duration", d["duration"]),
    )
    if built is None:
        return _bad("Invalid style, resolution, or length.")
    render_cfg, rmeta = built

    jid = _new_job("make", topic or (prompt[:60] if prompt else None))

    def job(_):
        result = pipeline.make_video(
            render_cfg, topic, verbose=False,
            on_step=lambda key, label: _push_step(jid, key, label),
            brief=prompt, brief_meta=brief_meta,
        )
        result["file"] = Path(result["video"]).name
        db.upsert_video(result["file"], title=result.get("title"), topic=topic,
                        duration_s=int(round(result.get("duration", 0))),
                        style=rmeta["style"], width=rmeta["width"], height=rmeta["height"])
        _push_step(jid, "done", "Render complete")
        return result

    _run(jid, job)
    return jsonify({"job_id": jid})


# ---- jobs -------------------------------------------------------------------
@app.route("/api/jobs/<jid>")
def api_job(jid):
    with _LOCK:
        job = JOBS.get(jid)
        if job:
            return jsonify(dict(job))
    rec = db.get_job(jid)  # fall back to the durable record (survives restart)
    if not rec:
        return jsonify({"error": "unknown job"}), 404
    result = json.loads(rec["result_json"]) if rec.get("result_json") else None
    return jsonify({"id": rec["id"], "kind": rec["kind"], "status": rec["status"],
                    "steps": [], "result": result, "error": rec.get("error"),
                    "started": rec.get("started_at")})


# ---- library / review -------------------------------------------------------
def _video_entry(mp4: Path) -> dict:
    stem = mp4.with_suffix("")
    meta_path = Path(str(stem) + ".metadata.json")
    script_path = Path(str(stem) + ".script.txt")
    thumb = Path(str(stem) + ".thumb.jpg")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    title = (meta or {}).get("youtube", {}).get("title") or mp4.stem
    review = db.get_review(mp4.name)
    sched = db.get_schedule_for(mp4.name)
    vrow = db.get_video(mp4.name) or {}

    # Provenance trace (how the draft was made) — present only for research/prompt renders.
    brief_meta, source = None, None
    brief_path = Path(str(stem) + ".brief.json")
    if brief_path.exists():
        try:
            brief_meta = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            brief_meta = None
    if isinstance(brief_meta, dict):
        gen_ai = bool(brief_meta.get("used_llm")) or brief_meta.get("generator") == "gemini"
        source = ("ai-research" if gen_ai and brief_meta.get("research_used")
                  else "ai" if gen_ai else "template")
    return {
        "file": mp4.name,
        "title": title,
        "duration": round(probe_duration(str(mp4))),
        "thumb": thumb.name if thumb.exists() else None,
        "script": script_path.read_text(encoding="utf-8") if script_path.exists() else "",
        "meta": meta,
        "mtime": mp4.stat().st_mtime,
        # legacy rows (pre-migration) were all rendered at the config resolution
        "style": vrow.get("style"),
        "width": vrow.get("width") or CFG["video"]["width"],
        "height": vrow.get("height") or CFG["video"]["height"],
        "brief": brief_meta,
        "source": source,
        "approved": review["approved"],
        "checks": review["checks"],
        "schedule": ({"status": sched["status"], "privacy": sched["privacy"],
                      "scheduled_for": sched["scheduled_for"], "youtube_id": sched["youtube_id"],
                      "url": sched["url"]} if sched else None),
    }


@app.route("/api/videos")
def api_videos():
    out = Path(CFG["paths"]["output"])
    vids = sorted(out.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify([_video_entry(v) for v in vids])


@app.route("/api/videos/<file>", methods=["DELETE"])
def api_video_delete(file):
    name = _safe_output_name(file)
    if not name:
        return _bad("Unknown video.", 404)
    sched = db.get_schedule_for(name)
    if sched and sched.get("youtube_id"):
        return _bad("This draft is already on YouTube — remove it there; deleting the "
                    "local file won't unpublish it.", 409)
    out = Path(CFG["paths"]["output"])
    stem = (out / name).with_suffix("")
    for p in (out / name, Path(str(stem) + ".metadata.json"),
              Path(str(stem) + ".script.txt"), Path(str(stem) + ".thumb.jpg"),
              Path(str(stem) + ".brief.json")):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            LOG.warning("could not delete %s", p)
    # narration is a regenerable intermediate in data/ (keyed by slug == stem here)
    try:
        (Path(CFG["paths"]["data"]) / (stem.name + ".narration.mp3")).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete_video(name)
    return jsonify({"ok": True})


@app.route("/api/review/<file>", methods=["GET"])
def api_review_get(file):
    name = _safe_output_name(file)
    if not name:
        return _bad("Unknown video.", 404)
    return jsonify(db.get_review(name))


@app.route("/api/review/<file>", methods=["POST"])
def api_review_set(file):
    name = _safe_output_name(file)
    if not name:
        return _bad("Unknown video.", 404)
    checks = (request.get_json(silent=True) or {}).get("checks")
    if not isinstance(checks, list) or len(checks) != 5 or not all(isinstance(c, bool) for c in checks):
        return _bad("checks must be a list of 5 booleans.")
    db.set_review(name, checks, approved=all(checks))
    return jsonify(db.get_review(name))


# ---- YouTube: connect + gated upload/schedule -------------------------------
@app.route("/api/youtube/status")
def api_youtube_status():
    yt, err = _yt()
    if err:
        return jsonify({"configured": False, "connected": False, "channel": None, "error": err})
    connected = yt.has_token(CFG)
    channel = None
    if connected:
        try:
            channel = yt.channel_title(CFG)
        except Exception as e:
            LOG.warning("channel_title failed: %s", e)
            connected = False
    return jsonify({"configured": yt.is_configured(CFG), "connected": connected, "channel": channel})


@app.route("/api/youtube/connect", methods=["POST"])
def api_youtube_connect():
    yt, err = _yt()
    if err:
        return _bad(err, 409)
    if not yt.is_configured(CFG):
        return _bad("client_secret.json not found in your secrets folder. See the setup steps.", 409)
    jid = _new_job("connect")

    def job(_):
        _push_step(jid, "auth", "Opening your browser to authorize YouTube...")
        yt.get_credentials(CFG)  # blocks until the browser flow completes; writes token.json
        title = yt.channel_title(CFG)
        _push_step(jid, "done", f"Connected: {title}")
        return {"channel": title}

    _run(jid, job)
    return jsonify({"job_id": jid})


@app.route("/api/publish/youtube", methods=["POST"])
def api_publish_youtube():
    body = request.get_json(silent=True) or {}
    name = _safe_output_name(body.get("file"))
    if not name:
        return _bad("Unknown video.", 404)
    # THE GATE: nothing uploads unless the review checklist was fully approved.
    if not db.get_review(name)["approved"]:
        return _bad("This video hasn't passed the review gate. Approve it first.", 403)

    yt, err = _yt()
    if err:
        return _bad(err, 409)
    if not yt.has_token(CFG):
        return _bad("YouTube is not connected. Click Connect YouTube first.", 409)

    mode = (body.get("mode") or CFG["youtube"]["default_action"]).lower()
    if mode not in ("schedule", "private", "public"):
        return _bad("mode must be schedule, private, or public.")
    publish_at, privacy = None, "private"
    if mode == "schedule":
        publish_at = _parse_future_iso(body.get("publish_at"))
        if not publish_at:
            return _bad("Scheduling requires a valid future date/time.")
    elif mode == "public":
        privacy = "public"

    meta_path = Path(CFG["paths"]["output"]) / (Path(name).stem + ".metadata.json")
    if not meta_path.exists():
        return _bad("Metadata file missing for this video.", 409)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mp4 = str(Path(CFG["paths"]["output"]) / name)

    jid = _new_job("upload", name)
    db.create_or_update_schedule(name, scheduled_for=publish_at, status="uploading", privacy=privacy)

    def job(_):
        _push_step(jid, "upload", "Starting upload...")
        try:
            res = yt.upload_video(CFG, mp4, meta, privacy=privacy, publish_at=publish_at,
                                  on_progress=lambda pct: _push_step(jid, "upload", f"Uploading {pct}%"))
        except Exception as e:
            db.create_or_update_schedule(name, status="failed", error=str(e))
            raise
        status = "scheduled" if publish_at else ("published" if privacy == "public" else "uploaded")
        db.create_or_update_schedule(name, scheduled_for=publish_at, status=status,
                                     youtube_id=res["video_id"], privacy=privacy, url=res["url"])
        _push_step(jid, "done", f"Uploaded: {res['url']}")
        return res

    _run(jid, job)
    return jsonify({"job_id": jid})


# ---- schedule / analytics ---------------------------------------------------
@app.route("/api/schedule")
def api_schedule():
    return jsonify(db.list_schedule())


@app.route("/api/analytics")
def api_analytics():
    return jsonify(db.leaderboard())


@app.route("/api/analytics/refresh", methods=["POST"])
def api_analytics_refresh():
    yt, err = _yt()
    if err:
        return _bad(err, 409)
    if not yt.has_token(CFG):
        return _bad("YouTube is not connected.", 409)
    pairs = db.uploaded_video_ids()
    if not pairs:
        return _bad("No uploaded videos to analyze yet.", 409)
    jid = _new_job("analytics")

    def job(_):
        file_by_id = {vid: f for vid, f in pairs}
        ids = list(file_by_id.keys())
        _push_step(jid, "fetch", f"Fetching stats for {len(ids)} videos...")
        stats = yt.fetch_statistics(CFG, ids)
        for s in stats:
            db.insert_analytics(s["id"], file_by_id.get(s["id"]), s["views"], s["likes"], s["comments"])
        _push_step(jid, "done", f"Updated {len(stats)} videos")
        return {"updated": len(stats)}

    _run(jid, job)
    return jsonify({"job_id": jid})


# ---- media ------------------------------------------------------------------
@app.route("/media/<path:name>")
def media(name):
    # serves rendered mp4s + thumbnails from output/, with HTTP range for scrubbing
    return send_from_directory(CFG["paths"]["output"], name, conditional=True)


# ---- error envelopes (never leak a stack trace to the client) ---------------
@app.errorhandler(404)
def _handle_404(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(Exception)
def _handle_500(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    LOG.exception("Unhandled server error")
    return jsonify({"error": "Internal server error"}), 500


def main():
    host = CFG["server"]["host"]
    port = int(os.getenv("PORT", "5177"))
    banner = f"\n  Viral Content Studio -> http://{host}:{port}\n  (Ctrl+C to stop)\n"
    if os.getenv("FORCE_DEV_SERVER"):
        LOG.info("FORCE_DEV_SERVER set -> Flask dev server on %s:%d", host, port)
        print(banner)
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        return
    try:
        from waitress import serve
        LOG.info("Serving via waitress on http://%s:%d", host, port)
        print(banner)
        serve(app, host=host, port=port, threads=CFG["server"]["threads"])
    except ImportError:
        LOG.warning("waitress not installed -> Flask dev server (pip install -r requirements.txt)")
        print(banner)
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
