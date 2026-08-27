"""Assemble the final vertical video with ffmpeg: b-roll + narration + burned-in captions.

Strategy (most robust on Windows): normalize each b-roll clip to a fixed
1080x1920/30fps segment of its beat duration, concat them, then mux narration and
burn the ASS captions in a single pass. Optional background music is mixed under.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import ffmpegutil


def compute_beat_durations(beats: list[dict], narration_dur: float, cfg: dict) -> tuple[list[float], float]:
    v = cfg["video"]
    target = max(narration_dur + v.get("tail_seconds", 1.2), v["min_seconds"])
    weights = [max(len(b.get("text", "")), 1) for b in beats]
    total = sum(weights) or 1
    durs = [target * w / total for w in weights]
    # make the sum exact by absorbing rounding into the last beat
    durs[-1] = max(target - sum(durs[:-1]), 1.0)
    if durs[-1] <= 0.5:  # pathological: split evenly
        durs = [target / len(beats)] * len(beats)
    return durs, target


def assemble_video(cfg: dict, broll_paths: list[str], beats: list[dict], narration_mp3: str,
                   ass_text: str, out_path: str) -> dict:
    if not ffmpegutil.has_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not on PATH — see README for the one-line install.")

    v = cfg["video"]
    narration_dur = ffmpegutil.probe_duration(narration_mp3)
    durs, target = compute_beat_durations(beats, narration_dur, cfg)

    tmp = Path(tempfile.mkdtemp(prefix="vca_", dir=cfg["paths"]["data"]))
    try:
        # 1) normalize each beat clip to exact duration + canonical format
        concat_lines = []
        for i, (src, dur) in enumerate(zip(broll_paths, durs)):
            seg = tmp / f"beat_{i:03d}.mp4"
            ffmpegutil.ff([
                "-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(src),
                "-vf", f"scale={v['width']}:{v['height']}:force_original_aspect_ratio=increase,"
                       f"crop={v['width']}:{v['height']},fps={v['fps']},setsar=1,format=yuv420p",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(seg),
            ])
            concat_lines.append(f"file '{seg.name}'")

        (tmp / "concat.txt").write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        (tmp / "captions.ass").write_text(ass_text, encoding="utf-8")

        out_abs = str(Path(out_path).resolve())
        music = cfg.get("music", {})
        music_path = music.get("path", "")
        use_music = bool(music.get("enabled") and music_path and Path(music_path).exists())

        common_tail = [
            "-t", f"{target:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(v["fps"]),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_abs,
        ]

        if use_music:
            fc = (
                "[0:v]ass=captions.ass[v];"
                "[1:a]apad[a1];"
                f"[2:a]volume={music['volume']}[a2];"
                "[a1][a2]amix=inputs=2:duration=first:dropout_transition=200[a]"
            )
            args = [
                "-f", "concat", "-safe", "0", "-i", "concat.txt",
                "-i", str(Path(narration_mp3).resolve()),
                "-i", str(Path(music_path).resolve()),
                "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            ] + common_tail
        else:
            args = [
                "-f", "concat", "-safe", "0", "-i", "concat.txt",
                "-i", str(Path(narration_mp3).resolve()),
                "-vf", "ass=captions.ass", "-map", "0:v:0", "-map", "1:a:0", "-af", "apad",
            ] + common_tail

        ffmpegutil.ff(args, cwd=str(tmp))
        return {"duration": round(target, 2), "narration_duration": round(narration_dur, 2)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
