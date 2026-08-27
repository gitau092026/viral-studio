"""Viral Content Agent — command line.

Usage:
    python run.py check                       # verify setup (ffmpeg + keys + youtube + paths)
    python run.py research                     # find what's going viral -> data/trend_report.md
    python run.py ideas                        # turn trends into original concepts -> data/ideas.json
    python run.py make --topic "discipline"    # make ONE video from a topic
    python run.py make --from-ideas 1          # make a video from ideas.json (rank 1 = top)
    python run.py batch --count 3              # make several videos for review
    python run.py publish --file output/x.mp4  # per-platform captions (manual posting)
    python run.py connect-youtube              # one-time OAuth sign-in (writes token.json)
    python run.py upload --file x.mp4 --approve --mode schedule --publish-at 2026-08-28T18:30
    python run.py schedule --file x.mp4 --at 2026-08-28T18:30   # upload Private + auto-go-public
    python run.py analytics --refresh          # pull views/likes for uploaded videos -> leaderboard
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows consoles default to cp1252 and crash on non-ASCII output; force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src import db
from src import ideas as ideas_mod
from src import llm
from src import logsetup
from src import pipeline
from src import research as research_mod
from src.ffmpegutil import has_ffmpeg
from src.settings import env, load_config

REVIEW_CHECKLIST = """
  --- Review before publishing (keeps you monetizable) ---
   [ ] Hook lands in the first 1 second
   [ ] Script says something with a genuine, original angle
   [ ] Captions are readable and synced
   [ ] No dead air; energy stays up
   [ ] Edit at least one line so it's truly YOURS (not templated)
  --------------------------------------------------------"""


def cmd_check(cfg, args):
    print("Setup check:")
    print(f"  ffmpeg + ffprobe on PATH : {'OK' if has_ffmpeg() else 'MISSING (see README)'}")
    print(f"  YOUTUBE_API_KEY          : {'set' if env('YOUTUBE_API_KEY') else 'not set (needed for `research`)'}")
    print(f"  PEXELS_API_KEY           : {'set' if env('PEXELS_API_KEY') else 'not set (b-roll -> color fallback)'}")
    print(f"  GEMINI_API_KEY           : {'set' if llm.available() else 'not set (uses built-in script bank)'}")
    try:
        import edge_tts  # noqa: F401
        print("  edge-tts import          : OK")
    except Exception as e:
        print(f"  edge-tts import          : FAILED ({e}) -> pip install -r requirements.txt")
    try:
        import waitress  # noqa: F401
        print("  waitress (web server)    : OK")
    except Exception:
        print("  waitress (web server)    : not installed (falls back to Flask dev server)")
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        print("  google API libs (upload) : OK")
    except Exception:
        print("  google API libs (upload) : not installed -> pip install -r requirements.txt")

    secrets = Path(cfg["paths"]["secrets"])
    cs = secrets / "client_secret.json"
    tok = secrets / "token.json"
    print(f"  OAuth client_secret.json : {'found' if cs.exists() else 'missing (see SETUP.md)'}")
    print(f"  YouTube token.json       : {'present (connected)' if tok.exists() else 'none (run: python run.py connect-youtube)'}")

    print("\nDurable state (kept OUT of OneDrive so secrets never sync):")
    print(f"  state dir : {cfg['paths']['state']}")
    print(f"  database  : {cfg['db_path']}")
    print(f"  logs      : {cfg['paths']['logs']}")
    print("\nYou can make a video right now with:  python run.py make --topic \"discipline\"")


def cmd_research(cfg, args):
    print("Researching what's going viral (this uses your free YouTube quota)...")
    report = research_mod.run_research(cfg)
    vids = report["videos"]
    print(f"\nAnalyzed {len(vids)} videos. Top 5 by view-velocity:\n")
    for v in vids[:5]:
        print(f"  {v['views_per_day']:>8,}/day  {v['duration_s']:>3}s  {v['title'][:60]}")
    print(f"\nFull report: {Path(cfg['paths']['data']) / 'trend_report.md'}")


def cmd_ideas(cfg, args):
    print("Generating original concepts...")
    ideas = ideas_mod.generate_ideas(cfg, count=args.count)
    for i, idea in enumerate(ideas, 1):
        print(f"  {i}. {idea['title']}")
        print(f"       hook: {idea.get('hook', '')}")
    print(f"\nSaved: {Path(cfg['paths']['data']) / 'ideas.json'}")
    print("Make one with:  python run.py make --from-ideas 1")


def _topic_from_ideas(cfg, rank: int) -> str | None:
    path = Path(cfg["paths"]["data"]) / "ideas.json"
    if not path.exists():
        print("No ideas.json yet — run `python run.py ideas` first, or use --topic.")
        return None
    ideas = json.loads(path.read_text(encoding="utf-8"))
    if not 1 <= rank <= len(ideas):
        print(f"--from-ideas must be 1..{len(ideas)}")
        return None
    idea = ideas[rank - 1]
    return f"{idea['title']} — {idea.get('angle', '')}".strip(" —")


def cmd_make(cfg, args):
    topic = args.topic
    if args.from_ideas:
        topic = _topic_from_ideas(cfg, args.from_ideas)
        if topic is None:
            return
    print("Making one video...")
    result = pipeline.make_video(cfg, topic)
    _print_result(result)
    print(REVIEW_CHECKLIST)


def cmd_batch(cfg, args):
    path = Path(cfg["paths"]["data"]) / "ideas.json"
    if path.exists():
        ideas = json.loads(path.read_text(encoding="utf-8"))
    else:
        ideas = ideas_mod.generate_ideas(cfg, count=args.count)
    topics = [f"{i['title']} — {i.get('angle', '')}".strip(" —") for i in ideas[:args.count]]
    print(f"Batch: making {len(topics)} videos...\n")
    made = []
    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] {topic[:70]}")
        try:
            made.append(pipeline.make_video(cfg, topic, verbose=False))
            print(f"    -> {made[-1]['video']}  ({made[-1]['duration']}s)")
        except Exception as e:
            print(f"    !! failed: {e}")
    print(f"\nDone. {len(made)} videos in {cfg['paths']['output']}")
    print(REVIEW_CHECKLIST)


def cmd_web(cfg, args):
    import os
    import threading
    import webbrowser

    port = args.port
    os.environ["PORT"] = str(port)
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Viral Content Studio at {url}")
    print("Leave this window open while you work. Press Ctrl+C to stop.")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    from app import main as web_main  # lazy: only needs Flask for this command
    web_main()


def cmd_publish(cfg, args):
    stem = Path(args.file).with_suffix("")
    meta_path = Path(str(stem) + ".metadata.json")
    if not meta_path.exists():
        print(f"No metadata found next to {args.file} (expected {meta_path}).")
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    print("=" * 64)
    print("PLATFORM-READY COPY (paste when uploading)")
    print("=" * 64)
    yt = meta["youtube"]
    print(f"\n> YOUTUBE SHORTS\n  Title: {yt['title']}\n  Description:\n    " + yt["description"].replace("\n", "\n    "))
    print(f"  Tags: {', '.join(yt['tags'])}")
    print(f"\n> TIKTOK\n  {meta['tiktok']['caption']}")
    print(f"\n> FACEBOOK / REELS\n  {meta['facebook']['caption']}")
    print("\nManual posting always works. To upload straight to YouTube (gated on approval):")
    print("  python run.py upload --file " + Path(args.file).name + " --approve")


# ---- YouTube: connect / upload / schedule / analytics -----------------------
def _resolve_output(cfg, file) -> str | None:
    """Normalize a --file arg to a basename that exists in output/."""
    name = Path(file).name
    if not name.lower().endswith(".mp4"):
        print("Provide a .mp4 file (in output/).")
        return None
    if not (Path(cfg["paths"]["output"]) / name).exists():
        print(f"Not found in output/: {name}")
        return None
    return name


def cmd_connect_youtube(cfg, args):
    from src import publish_youtube as yt
    if not yt.is_configured(cfg):
        print(f"client_secret.json not found in {cfg['paths']['secrets']}")
        print("Create a Desktop OAuth client (see SETUP.md), save it there, then re-run.")
        return
    print("Opening your browser to authorize YouTube (upload + read-only)...")
    yt.get_credentials(cfg)  # blocks on the browser consent screen; writes token.json
    print(f"Connected: {yt.channel_title(cfg)}")
    print(f"Token saved: {yt.token_path(cfg)}")


def cmd_upload(cfg, args):
    from src import publish_youtube as yt
    name = _resolve_output(cfg, args.file)
    if not name:
        return

    # THE GATE: never upload an unapproved video. --approve lets you clear it here.
    if not db.get_review(name)["approved"]:
        if not getattr(args, "approve", False):
            print("Refused: this video hasn't passed the review gate.")
            print("Approve it in the dashboard, or re-run with --approve to review it now.")
            return
        print(REVIEW_CHECKLIST)
        ans = input("\nDo all five hold true for THIS video? Type 'yes' to approve: ").strip().lower()
        if ans not in ("y", "yes"):
            print("Not approved — nothing uploaded.")
            return
        db.set_review(name, [True] * 5, approved=True)
        print("Approved (saved to the review gate).")

    if not yt.has_token(cfg):
        print("YouTube not connected. Run: python run.py connect-youtube")
        return

    mode = (getattr(args, "mode", None) or cfg["youtube"]["default_action"]).lower()
    if mode not in ("schedule", "private", "public"):
        print("--mode must be schedule, private, or public")
        return
    publish_at, privacy = None, "private"
    if mode == "schedule":
        if not getattr(args, "publish_at", None):
            print("Scheduling needs --publish-at <ISO>, e.g. 2026-08-28T18:30")
            return
        try:
            publish_at = yt.to_rfc3339_utc(args.publish_at)
        except Exception as e:
            print(f"Bad --publish-at: {e}")
            return
        when = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if when <= datetime.now(timezone.utc):
            print("--publish-at must be in the future.")
            return
    elif mode == "public":
        privacy = "public"

    meta_path = Path(cfg["paths"]["output"]) / (Path(name).stem + ".metadata.json")
    if not meta_path.exists():
        print(f"Metadata missing: {meta_path}")
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mp4 = str(Path(cfg["paths"]["output"]) / name)

    db.create_or_update_schedule(name, scheduled_for=publish_at, status="uploading", privacy=privacy)
    print(f"Uploading {name} (mode={mode})...")
    try:
        res = yt.upload_video(cfg, mp4, meta, privacy=privacy, publish_at=publish_at,
                              on_progress=lambda pct: print(f"  {pct}%", end="\r", flush=True))
    except Exception as e:
        db.create_or_update_schedule(name, status="failed", error=str(e))
        print(f"\nUpload failed: {e}")
        return
    status = "scheduled" if publish_at else ("published" if privacy == "public" else "uploaded")
    db.create_or_update_schedule(name, scheduled_for=publish_at, status=status,
                                 youtube_id=res["video_id"], privacy=privacy, url=res["url"])
    print(f"\nDone: {res['url']}  ({status}, {privacy})")
    if publish_at:
        print(f"Goes public at {publish_at} — your PC can be off.")


def cmd_schedule(cfg, args):
    args.mode = "schedule"
    args.publish_at = args.at
    cmd_upload(cfg, args)


def cmd_analytics(cfg, args):
    if getattr(args, "refresh", False):
        from src import publish_youtube as yt
        if not yt.has_token(cfg):
            print("YouTube not connected. Run: python run.py connect-youtube")
            return
        pairs = db.uploaded_video_ids()
        if not pairs:
            print("No uploaded videos to analyze yet.")
            return
        file_by_id = {vid: f for vid, f in pairs}
        ids = list(file_by_id.keys())
        print(f"Fetching stats for {len(ids)} video(s)...")
        stats = yt.fetch_statistics(cfg, ids)
        for s in stats:
            db.insert_analytics(s["id"], file_by_id.get(s["id"]), s["views"], s["likes"], s["comments"])
        print(f"Updated {len(stats)}.\n")

    board = db.leaderboard()
    if not board:
        print("No analytics yet. Upload a public/unlisted video, then: python run.py analytics --refresh")
        return
    print("What's working (by views):")
    for i, r in enumerate(board, 1):
        vpd = f"{r['views_per_day']:,}/day" if r.get("views_per_day") is not None else "-"
        title = (r.get("title") or r.get("file") or r["youtube_id"])[:52]
        print(f"  {i:>2}. {r['views']:>8,} views  {vpd:>12}  {title}")


def build_parser():
    p = argparse.ArgumentParser(prog="run.py", description="Faceless motivation Shorts — free stack")
    p.add_argument("--config", default=None, help="path to a config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify setup")
    sub.add_parser("research", help="find viral videos in your niche")

    pi = sub.add_parser("ideas", help="generate original concepts")
    pi.add_argument("--count", type=int, default=8)

    pm = sub.add_parser("make", help="make one video")
    pm.add_argument("--topic", default=None, help="topic/angle in your own words")
    pm.add_argument("--from-ideas", type=int, default=None, metavar="RANK", help="use ideas.json entry (1=top)")

    pb = sub.add_parser("batch", help="make several videos")
    pb.add_argument("--count", type=int, default=3)

    pp = sub.add_parser("publish", help="print platform copy for manual posting")
    pp.add_argument("--file", required=True, help="path to a rendered .mp4 in output/")

    pc = sub.add_parser("connect-youtube", help="one-time OAuth sign-in (writes token.json)")  # noqa: F841

    pu = sub.add_parser("upload", help="upload to YouTube (gated on review approval)")
    pu.add_argument("--file", required=True, help="a rendered .mp4 in output/ (name or path)")
    pu.add_argument("--mode", choices=["schedule", "private", "public"], default=None,
                    help="default: schedule (from config)")
    pu.add_argument("--publish-at", default=None, metavar="ISO",
                    help="for --mode schedule: local datetime, e.g. 2026-08-28T18:30")
    pu.add_argument("--approve", action="store_true",
                    help="review & approve this video now (interactive) before uploading")

    ps = sub.add_parser("schedule", help="upload Private now + auto-go-public later (gated)")
    ps.add_argument("--file", required=True, help="a rendered .mp4 in output/")
    ps.add_argument("--at", required=True, metavar="ISO", help="local datetime, e.g. 2026-08-28T18:30")
    ps.add_argument("--approve", action="store_true", help="review & approve now before scheduling")

    pa = sub.add_parser("analytics", help="show the what's-working leaderboard")
    pa.add_argument("--refresh", action="store_true", help="pull fresh views/likes from YouTube first")

    pw = sub.add_parser("web", help="launch the local web dashboard")
    pw.add_argument("--port", type=int, default=5177)
    return p


def _print_result(r: dict):
    print("\n  [OK] Video ready")
    print(f"    file      : {r['video']}")
    print(f"    duration  : {r['duration']}s (voice {r['narration_duration']}s)")
    print(f"    thumbnail : {r['thumbnail']}")
    print(f"    metadata  : {r['metadata']}")
    print(f"    script    : {r['script']}")


def main():
    args = build_parser().parse_args()
    cfg = load_config(args.config)
    logsetup.configure_logging(cfg)
    db.init_db(cfg)
    {
        "check": cmd_check,
        "research": cmd_research,
        "ideas": cmd_ideas,
        "make": cmd_make,
        "batch": cmd_batch,
        "publish": cmd_publish,
        "connect-youtube": cmd_connect_youtube,
        "upload": cmd_upload,
        "schedule": cmd_schedule,
        "analytics": cmd_analytics,
        "web": cmd_web,
    }[args.command](cfg, args)


if __name__ == "__main__":
    main()
